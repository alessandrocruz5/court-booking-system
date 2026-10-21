"""Staff dashboard pages. Each view is wrapped in `@staff_required`; the data, already masked for
the viewer's role, comes only from `dashboard.queries`."""

from django.shortcuts import render
from django.views.decorators.http import require_GET

from accounts.decorators import staff_required

from . import queries


# `staff_required` is outermost, so an anonymous request is sent to sign-in whatever its method.
@staff_required
@require_GET
def overview_view(request):
    return render(
        request,
        "dashboard/overview.html",
        {"overview": queries.overview(role=request.staff_role)},
    )
