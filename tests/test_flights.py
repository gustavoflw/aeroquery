import datetime as dt

import core.flights as flights
from tests.conftest import make_flight, make_leg


def connecting_legs():
    return [make_leg(from_code="OPO", to_code="LIS"), make_leg(from_code="LIS", to_code="MLA")]


def test_flight_identity_matches_for_identical_flights():
    a = make_flight(price=100, airlines=["Ryanair"])
    b = make_flight(price=100, airlines=["Ryanair"])
    assert flights.flight_identity(a) == flights.flight_identity(b)


def test_flight_identity_differs_on_price():
    a = make_flight(price=100, airlines=["Ryanair"])
    b = make_flight(price=101, airlines=["Ryanair"])
    assert flights.flight_identity(a) != flights.flight_identity(b)


def test_price_trend_window_is_a_single_day_by_default():
    # $AEROQUERY_PRICE_TREND_DAYS unset -> PRICE_TREND_TOTAL_DAYS == 1, so
    # the "window" is just the searched date itself.
    center = dt.date.today() + dt.timedelta(days=365)
    start, end = flights.price_trend_window(center.isoformat())
    assert start == center
    assert end == center


def test_price_trend_window_is_centered_when_far_in_the_future(monkeypatch):
    monkeypatch.setattr(flights, "PRICE_TREND_TOTAL_DAYS", 181)
    center = dt.date.today() + dt.timedelta(days=365)
    start, end = flights.price_trend_window(center.isoformat())
    assert start == center - dt.timedelta(days=90)
    assert end == start + dt.timedelta(days=180)


def test_price_trend_window_clamps_to_today_near_now(monkeypatch):
    monkeypatch.setattr(flights, "PRICE_TREND_TOTAL_DAYS", 181)
    center = dt.date.today() + dt.timedelta(days=1)
    start, end = flights.price_trend_window(center.isoformat())
    assert start == dt.date.today()
    assert end == start + dt.timedelta(days=180)


def test_price_trend_stats_aggregates_mean_min_max_count():
    results_by_date = {
        "2026-09-18": [make_flight(price=100), make_flight(price=200)],
        "2026-09-19": [make_flight(price=50)],
        "2026-09-20": [],
    }
    stats = {row["date"].isoformat(): row for row in flights.price_trend_stats(results_by_date)}

    assert stats["2026-09-18"]["mean"] == 150
    assert stats["2026-09-18"]["min"] == 100
    assert stats["2026-09-18"]["max"] == 200
    assert stats["2026-09-18"]["count"] == 2

    assert stats["2026-09-20"]["mean"] is None
    assert stats["2026-09-20"]["count"] == 0


def test_cheapest_direct_flight_ignores_connections():
    results_by_date = {
        "2026-09-18": [make_flight(price=33, legs=[make_leg()])],  # nonstop
        "2026-09-19": [
            make_flight(price=10, legs=connecting_legs())
        ],  # cheaper, but a connection — should be ignored
    }
    best = flights.cheapest_direct_flight(results_by_date)
    assert best == {"date": dt.date(2026, 9, 18), "price": 33}


def test_cheapest_direct_flight_returns_none_when_no_nonstop_exists():
    results_by_date = {"2026-09-18": [make_flight(price=10, legs=connecting_legs())]}
    assert flights.cheapest_direct_flight(results_by_date) is None


def test_search_flights_caches_identical_calls(monkeypatch):
    flights._search_cache.clear()
    calls = []

    def fake_fetch(query):
        calls.append(query)
        return [make_flight(price=42, legs=[make_leg()])]

    monkeypatch.setattr(flights, "fetch_flights_with_retry", fake_fetch)

    flights.search_flights("AAA", "BBB", "2030-01-01", 0, "EUR")
    flights.search_flights("AAA", "BBB", "2030-01-01", 0, "EUR")

    assert len(calls) == 1


def test_search_flights_merges_missing_nonstop_fare(monkeypatch):
    flights._search_cache.clear()

    connecting = make_flight(
        price=123,
        legs=[make_leg(from_code="AAA", to_code="XXX"), make_leg(from_code="XXX", to_code="BBB")],
    )
    nonstop = make_flight(
        price=33, airlines=["Ryanair"], legs=[make_leg(from_code="AAA", to_code="BBB")]
    )

    # search_flights makes the unrestricted call first, then (since
    # max_stops != 0) recurses once more with max_stops=0 — Query objects
    # don't expose max_stops as a plain attribute, so call order is the
    # simplest way to tell the two fetches apart here.
    calls = []

    def fake_fetch(query):
        calls.append(query)
        if len(calls) == 1:
            # The unrestricted query "misses" the cheap nonstop, mirroring
            # what Google's own Best-flights ranking does.
            return [connecting]
        return [nonstop]

    monkeypatch.setattr(flights, "fetch_flights_with_retry", fake_fetch)

    results = flights.search_flights("AAA", "BBB", "2030-02-02", None, "EUR")

    prices = sorted(f.price for f in results)
    assert prices == [33, 123]


def test_fetch_price_trend_is_a_single_search_by_default(monkeypatch):
    # Default PRICE_TREND_TOTAL_DAYS == 1: no sweep, just the searched date.
    center_iso = (dt.date.today() + dt.timedelta(days=20)).isoformat()
    searched = []

    def fake_search_flights(origin, destination, date_iso, max_stops, currency):
        searched.append(date_iso)
        return [make_flight(price=100, legs=[make_leg()])]

    monkeypatch.setattr(flights, "search_flights", fake_search_flights)

    result = flights.fetch_price_trend("AAA", "BBB", center_iso, None, "EUR")

    assert list(result.keys()) == [center_iso]
    assert searched == [center_iso]


def test_fetch_price_trend_streams_center_date_before_the_rest(monkeypatch):
    monkeypatch.setattr(flights, "PRICE_TREND_TOTAL_DAYS", 5)
    center_iso = (dt.date.today() + dt.timedelta(days=20)).isoformat()

    def fake_search_flights(origin, destination, date_iso, max_stops, currency):
        return [make_flight(price=100, legs=[make_leg()])]

    monkeypatch.setattr(flights, "search_flights", fake_search_flights)

    updates = []
    progresses = []
    result = flights.fetch_price_trend(
        "AAA",
        "BBB",
        center_iso,
        None,
        "EUR",
        on_update=lambda partial: updates.append(dict(partial)),
        on_progress=lambda completed, total, eta: progresses.append((completed, total, eta)),
    )

    assert len(result) == flights.PRICE_TREND_TOTAL_DAYS
    assert list(updates[0].keys()) == [center_iso]
    assert [len(u) for u in updates] == sorted(len(u) for u in updates)
    assert progresses[0] == (1, flights.PRICE_TREND_TOTAL_DAYS, None)
    assert progresses[-1][2] is None
