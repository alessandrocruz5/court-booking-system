from datetime import timedelta

import pytest
from django.utils import timezone

from bookings import holds, pricing, rules
from bookings.models import Court
from storefront.payloads import catalog_payload

# Matches `config.settings_test`.
AUTH = {"Authorization": "Bearer " + "t" * 40}


def tomorrow():
    return rules.local_today(timezone.now()) + timedelta(days=1)


def get_availability(client, **params):
    return client.get("/api/v1/availability", params, headers=AUTH)


def sport(payload: dict, sport_id: str) -> dict:
    (entry,) = [s for s in payload["sports"] if s["id"] == sport_id]
    return entry


def test_catalog_lists_sports_in_order_with_title_case_labels():
    payload = catalog_payload()

    ids = [s["id"] for s in payload["sports"]]
    assert ids == ["basketball", "volleyball", "tennis", "badminton", "pickleball"]
    assert [s["label"] for s in payload["sports"]] == [i.title() for i in ids]


def test_volleyball_only_offers_full():
    payload = catalog_payload()

    assert sport(payload, "volleyball")["coverages"] == ["full"]
    assert list(sport(payload, "volleyball")["rates"]) == ["full"]
    assert sport(payload, "basketball")["coverages"] == ["full", "half"]


@pytest.mark.django_db
def test_catalog_counts_courts_without_querying(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get("/api/v1/catalog", headers=AUTH)

    assert response.status_code == 200
    counts = [s["court_count"] for s in response.json()["sports"]]
    assert counts == [2, 2, 4, 12, 12]
    # The constants still match the seeded courts.
    assert Court.objects.filter(kind="basketball").count() == 2
    assert Court.objects.filter(kind="tennis").count() == 4
    assert Court.objects.filter(kind="multi").count() == 12


@pytest.mark.django_db
def test_availability_lists_the_sports_courts(client):
    day = tomorrow()
    response = get_availability(
        client, date=day.isoformat(), sport="basketball", coverage="half", hours="2"
    )

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert (body["date"], body["sport"], body["coverage"], body["hours"]) == (
        day.isoformat(),
        "basketball",
        "half",
        2,
    )
    assert [c["code"] for c in body["courts"]] == ["bb-1", "bb-2"]
    assert body["courts"][0]["starts"][0] == {
        "hour": 7,
        "price_centavos": pricing.quote("basketball", "half", day, 7, 2),
        "peak": pricing.is_peak(day, 7),
    }


@pytest.mark.django_db
def test_defaults_to_full_coverage_and_one_hour(client):
    body = get_availability(client, date=tomorrow().isoformat(), sport="tennis").json()

    assert (body["coverage"], body["hours"]) == ("full", 1)
    assert [s["hour"] for s in body["courts"][0]["starts"]] == list(range(7, 23))


@pytest.mark.django_db
def test_three_hours_never_start_after_20(client):
    body = get_availability(client, date=tomorrow().isoformat(), sport="tennis", hours="3").json()

    for court in body["courts"]:
        hours = [s["hour"] for s in court["starts"]]
        assert hours
        assert max(hours) == 20


@pytest.mark.django_db
def test_a_booked_hour_disappears(client):
    day = tomorrow()
    holds.create_staff_booking(
        source="walk_in",
        court=Court.objects.get(code="tn-2"),
        sport="tennis",
        coverage="full",
        half=None,
        day=day,
        start_hour=10,
        hours=1,
        created_by=None,
    )

    body = get_availability(client, date=day.isoformat(), sport="tennis").json()

    starts = {c["code"]: [s["hour"] for s in c["starts"]] for c in body["courts"]}
    assert 10 not in starts["tn-2"]
    assert 9 in starts["tn-2"] and 11 in starts["tn-2"]
    assert 10 in starts["tn-1"]


@pytest.mark.django_db
def test_a_date_past_the_window_is_a_rule_error(client):
    last = rules.local_today(timezone.now()) + timedelta(days=rules.WINDOW_DAYS)

    response = get_availability(client, date=last.isoformat(), sport="tennis")

    assert response.status_code == 400
    assert response.json() == {"error": "outside_window"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_half_volleyball_is_a_rule_error(client):
    response = get_availability(
        client, date=tomorrow().isoformat(), sport="volleyball", coverage="half"
    )

    assert response.status_code == 400
    assert response.json() == {"error": "coverage_not_allowed"}


@pytest.mark.django_db
def test_too_many_hours_is_a_rule_error(client):
    response = get_availability(client, date=tomorrow().isoformat(), sport="tennis", hours="4")

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_hours"}


def test_an_unknown_sport_names_the_field_without_its_value(client):
    response = get_availability(client, date=tomorrow().isoformat(), sport="curling")

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request", "fields": ["sport"]}
    assert b"curling" not in response.content
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("params", "fields"),
    [
        ({}, ["date", "sport"]),
        ({"date": "2026-02-30", "sport": "tennis"}, ["date"]),
        ({"date": "20261103", "sport": "tennis"}, ["date"]),
        ({"date": "2026-11-03", "sport": "tennis", "coverage": "quarter"}, ["coverage"]),
        ({"date": "2026-11-03", "sport": "tennis", "hours": "two"}, ["hours"]),
        ({"date": "2026-11-03", "sport": "tennis", "hours": "-1"}, ["hours"]),
    ],
)
def test_bad_fields_are_named_in_order(client, params, fields):
    response = get_availability(client, **params)

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request", "fields": fields}
