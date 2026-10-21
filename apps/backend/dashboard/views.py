"""Staff dashboard pages. Each view is wrapped in `@staff_required`; the data, already masked for
the viewer's role, comes only from `dashboard.queries` (or `dashboard.schedule` for the grid).

Schedule writes go only through `bookings.holds`, with the permission checked here on the server
(`accounts.roles`); the templates only reflect it. The demo viewer's writes are rate-limited per
client IP, capped in number while live, and marked `is_demo`, so the nightly reseed tidies them
away. Cancelling a pending online hold expires its PayMongo checkout session once the cancel has
committed, never inside a transaction.
"""

from datetime import date, timedelta
from functools import partial

from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.decorators import staff_required
from accounts.roles import Role, can_cancel, can_create_staff_booking
from bookings import holds
from bookings.rules import TIME_ZONE, BookingRuleError, Status, local_today
from core.http import client_ip
from core.ratelimit import hit
from payments.confirm import expire_session

from . import queries, schedule
from .forms import RULE_ERROR_DEFAULT, RULE_ERRORS, SLOT_TAKEN, StaffBookingForm

SCHEDULE = "dashboard/schedule.html"
BOOKINGS = "dashboard/bookings.html"
# The viewer's writes (creates and cancels) per client IP. Must stay within the nightly prune's
# `RATE_LIMIT_MAX_AGE` (10 minutes).
WRITE_LIMIT = 20
WRITE_WINDOW_SECONDS = 600
# The viewer is one shared, public account: without a cap on its live (confirmed, not yet ended)
# demo bookings, one visitor could fill the storefront's 7-day inventory until the nightly reseed.
DEMO_LIVE_CAP = 50

CANT_CANCEL = "You can't cancel this booking."
CANT_CREATE = "You can't add bookings."
DEMO_LIMIT = "Demo limit reached. Try again in a few minutes."
DEMO_FULL = (
    "The demo has enough bookings for now. Try cancelling one of yours, or come back tomorrow."
)
CANCEL_TOASTS = {
    Status.CANCELLED: "Booking cancelled.",
    Status.NEEDS_REFUND: (
        "Booking cancelled. It was paid: refund it in the PayMongo dashboard (test mode)."
    ),
    None: "That booking was already cancelled.",
}


# `staff_required` is outermost, so an anonymous request is sent to sign-in whatever its method.
@staff_required
@require_GET
def overview_view(request):
    return render(
        request,
        "dashboard/overview.html",
        {"overview": queries.overview(role=request.staff_role)},
    )


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _requested_day(value: str | None, now) -> date:
    """`?date=YYYY-MM-DD`, clamped to the browsable range; today (Manila) when absent or invalid."""
    try:
        day = date.fromisoformat(value or "")
    except ValueError:
        return local_today(now)
    first, last = schedule.browse_bounds(now)
    return min(max(day, first), last)


def _render_fragment(request, name: str, context: dict, *, status: int = 200) -> HttpResponse:
    """A schedule partial for htmx; anyone else gets it inside the dashboard shell, never bare."""
    if _is_htmx(request):
        return render(request, f"{SCHEDULE}#{name}", context, status=status)
    return render(
        request,
        "dashboard/fragment_page.html",
        {**context, "fragment": f"{SCHEDULE}#{name}"},
        status=status,
    )


def _panel_message(request, message: str, status: int) -> HttpResponse:
    """A refusal shown in the side panel, whatever element the request targeted. The htmx config
    in `dashboard/base.html` swaps 403 and 429 responses."""
    response = _render_fragment(request, "panel", {"message": message}, status=status)
    response["HX-Retarget"] = "#panel"
    response["HX-Reswap"] = "innerHTML"
    return response


def _grid_response(request, day: date, now, *, toast: str) -> HttpResponse:
    """The refreshed grid partial, with an out-of-band toast and an emptied side panel. Without
    htmx, back to that day's schedule."""
    if not _is_htmx(request):
        return HttpResponseRedirect(
            f"{reverse('dashboard:schedule')}?date={day.isoformat()}", status=303
        )
    grid = schedule.build_grid(day, role=request.staff_role, now=now)
    return render(request, f"{SCHEDULE}#grid", {"grid": grid, "toast": toast})


def _viewer_write_allowed(request) -> bool:
    """The demo viewer's write budget. The owner is never limited."""
    if request.staff_role != Role.VIEWER:
        return True
    return hit(
        "staff_write",
        client_ip(request),
        limit=WRITE_LIMIT,
        window_seconds=WRITE_WINDOW_SECONDS,
    )


def _demo_until(role, now) -> date | None:
    if role != Role.VIEWER:
        return None
    return local_today(now) + timedelta(days=schedule.VIEWER_DAYS_AHEAD)


@staff_required
@require_GET
def schedule_view(request):
    now = timezone.now()
    day = _requested_day(request.GET.get("date"), now)
    context = {"grid": schedule.build_grid(day, role=request.staff_role, now=now)}
    # A history restore (back button with no history cache) needs the whole page.
    partial = _is_htmx(request) and request.headers.get("HX-History-Restore-Request") != "true"
    return render(request, f"{SCHEDULE}#grid" if partial else SCHEDULE, context)


def _to_detail(request, reference: str) -> HttpResponse:
    """After a cancel from the detail page: back to that page, not to a grid partial."""
    url = reverse("dashboard:booking_detail", args=[reference])
    if _is_htmx(request):
        response = HttpResponse()
        response["HX-Redirect"] = url
        return response
    return HttpResponseRedirect(url, status=303)


@staff_required
@require_GET
def bookings_view(request):
    params = queries.parse_list_params(request.GET)
    context = {
        "params": params,
        "page": queries.list_bookings(role=request.staff_role, params=params),
        "status_choices": queries.STATUS_CHOICES,
        "sport_choices": queries.SPORT_CHOICES,
        "source_choices": queries.SOURCE_CHOICES,
        "sort_choices": tuple(queries.SORTS.items()),
    }
    # A history restore (back button with no history cache) needs the whole page.
    partial = _is_htmx(request) and request.headers.get("HX-History-Restore-Request") != "true"
    return render(request, f"{BOOKINGS}#results" if partial else BOOKINGS, context)


@staff_required
@require_GET
def booking_detail_view(request, reference):
    detail = queries.get_booking(role=request.staff_role, reference=reference, now=timezone.now())
    if detail is None:
        raise Http404
    # The list's state, re-validated, so the back link restores it and nothing else gets through.
    back_query = queries.parse_list_params(request.GET).query_string()
    return render(
        request, "dashboard/booking_detail.html", {"detail": detail, "back_query": back_query}
    )


@staff_required
@require_GET
def booking_panel(request, reference):
    booking = schedule.get_booking(reference)
    if booking is None:
        raise Http404
    if not _is_htmx(request):
        return HttpResponseRedirect(reverse("dashboard:booking_detail", args=[reference]))
    detail = schedule.booking_detail(booking, role=request.staff_role, now=timezone.now())
    return render(request, f"{SCHEDULE}#panel", {"detail": detail})


@staff_required
@require_POST
def cancel_view(request, reference):
    booking = schedule.get_booking(reference)
    if booking is None:
        raise Http404
    role = request.staff_role
    now = timezone.now()
    if not can_cancel(role, booking, now=now):
        return _panel_message(request, CANT_CANCEL, 403)
    if not _viewer_write_allowed(request):
        return _panel_message(request, DEMO_LIMIT, 429)
    was_pending = booking.status == Status.PENDING
    status = holds.cancel_booking(booking, by_role=role, now=now)
    if status == Status.CANCELLED and was_pending and booking.checkout_session_id:
        # The HTTP call runs after the cancel commits, outside any transaction.
        transaction.on_commit(partial(expire_session, booking.checkout_session_id))
    if request.POST.get("return") == "detail":
        return _to_detail(request, reference)
    day = booking.starts_at.astimezone(TIME_ZONE).date()
    return _grid_response(request, day, now, toast=CANCEL_TOASTS[status])


@staff_required
@require_http_methods(["GET", "POST"])
def new_view(request):
    """GET: the add form for a clicked cell, in the side panel. POST: create the booking."""
    if not can_create_staff_booking(request.staff_role):
        return _panel_message(request, CANT_CREATE, 403)
    if request.method == "POST":
        return _create(request)
    return _new_panel(request)


def _new_panel(request):
    now = timezone.now()
    if not _is_htmx(request):
        day = _requested_day(request.GET.get("date"), now)
        return HttpResponseRedirect(f"{reverse('dashboard:schedule')}?date={day.isoformat()}")
    try:
        hour = int(request.GET.get("hour", ""))
    except ValueError:
        raise Http404 from None
    form = StaffBookingForm.for_cell(
        court_code=request.GET.get("court", ""),
        space=request.GET.get("space", ""),
        hour=hour,
        day=_requested_day(request.GET.get("date"), now),
        demo_until=_demo_until(request.staff_role, now),
        preset_notes=request.staff_role == Role.VIEWER,
    )
    if form is None:
        raise Http404
    return render(request, f"{SCHEDULE}#form", {"form": form})


def _form_response(request, form) -> HttpResponse:
    response = _render_fragment(request, "form", {"form": form})
    response["HX-Retarget"] = "#panel"
    response["HX-Reswap"] = "innerHTML"
    return response


def _create(request):
    role = request.staff_role
    now = timezone.now()
    form = StaffBookingForm(
        request.POST, demo_until=_demo_until(role, now), preset_notes=role == Role.VIEWER
    )
    # Invalid requests don't count against the budget, so validate before charging it.
    if not form.is_valid():
        return _form_response(request, form)
    if not _viewer_write_allowed(request):
        return _panel_message(request, DEMO_LIMIT, 429)
    if role == Role.VIEWER and schedule.viewer_live_bookings(request.user, now) >= DEMO_LIVE_CAP:
        return _panel_message(request, DEMO_FULL, 429)
    data = form.cleaned_data
    try:
        holds.create_staff_booking(
            source=data["kind"],
            court=data["court"],
            sport=data["sport"],
            coverage=data["coverage"],
            half=data["half"],
            day=data["date"],
            start_hour=data["start_hour"],
            hours=data["hours"],
            created_by=request.user,
            customer_name=data["customer_name"],
            note=data["note"],
            # The viewer's bookings are demo data: the nightly reseed cleans them up.
            is_demo=role == Role.VIEWER,
            now=now,
        )
    except holds.SlotTaken:
        form.add_error(None, SLOT_TAKEN)
        return _form_response(request, form)
    except BookingRuleError as error:
        form.add_error(None, RULE_ERRORS.get(error.code, RULE_ERROR_DEFAULT))
        return _form_response(request, form)
    return _grid_response(request, data["date"], now, toast="Booking added.")
