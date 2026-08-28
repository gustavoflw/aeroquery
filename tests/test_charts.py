import datetime as dt

from core.charts import (
    build_price_trend_chart,
    build_route_map,
    find_plottable_routes,
    nice_log_ticks,
    route_colors_by_index,
)
from tests.conftest import make_flight, make_leg

STYLE = dict(
    route_colors=["red", "green", "blue"],
    landcolor="#000",
    countrycolor="#000",
    airport_dot="#000",
    airport_text="#000",
    legend_font="#000",
    legend_title_font="#000",
    stop_ok="#000",
    stop_warn="#000",
    stop_bad="#000",
)

AIRPORTS = {
    "AAA": {"lat": 0.0, "lon": 0.0, "city": "Alpha City", "country": "AA", "name": "Alpha Intl"},
    "BBB": {"lat": 10.0, "lon": 10.0, "city": "Bravo City", "country": "BB", "name": "Bravo Intl"},
    "CCC": {
        "lat": 20.0, "lon": 20.0, "city": "Charlie City", "country": "CC", "name": "Charlie Intl"
    },
}


def test_find_plottable_routes_caps_at_style_route_color_count():
    results = [make_flight(price=p, legs=[make_leg("AAA", "BBB")]) for p in range(5)]
    plottable, skipped = find_plottable_routes(results, AIRPORTS, STYLE)
    assert len(plottable) == len(STYLE["route_colors"])  # capped at 3
    assert skipped == 0


def test_find_plottable_routes_skips_unknown_airport_codes():
    results = [
        make_flight(price=1, legs=[make_leg("AAA", "BBB")]),
        make_flight(price=2, legs=[make_leg("AAA", "ZZZ")]),  # ZZZ not in AIRPORTS
    ]
    plottable, skipped = find_plottable_routes(results, AIRPORTS, STYLE)
    assert len(plottable) == 1
    assert skipped == 1


def test_route_colors_by_index_cycles_through_style_colors():
    plottable = [(0, None, None, None), (1, None, None, None), (2, None, None, None)]
    colors = route_colors_by_index(plottable, STYLE)
    assert colors == {0: "red", 1: "green", 2: "blue"}


def test_nice_log_ticks_covers_range_with_round_values():
    ticks = nice_log_ticks(150, 3000)
    assert ticks == sorted(ticks)
    assert all(t > 0 for t in ticks)
    assert 200 in ticks or 300 in ticks


def test_nice_log_ticks_empty_for_invalid_range():
    assert nice_log_ticks(0, 100) == []
    assert nice_log_ticks(100, 50) == []


def test_build_route_map_trace_count_matches_formula():
    results = [make_flight(price=p, legs=[make_leg("AAA", "BBB")]) for p in range(2)]
    plottable, _ = find_plottable_routes(results, AIRPORTS, STYLE)
    fig = build_route_map(plottable, STYLE, set(), "EUR", AIRPORTS)

    n_routes = len(plottable)
    # halo + real route traces, then all-airports, then seen-airport dot + label
    assert len(fig.data) == 2 * n_routes + 3
    all_airports_trace = fig.data[2 * n_routes]
    assert len(all_airports_trace.lon) == len(AIRPORTS)


def test_build_route_map_handles_no_plottable_routes():
    fig = build_route_map([], STYLE, set(), "EUR", AIRPORTS)
    assert len(fig.data) == 3  # just all-airports + seen-airport dot + label (both empty)


def test_build_price_trend_chart_smoke():
    trend = [
        dict(date=dt.date(2026, 9, 18), mean=100, min=80, max=150, count=3),
        dict(date=dt.date(2026, 9, 19), mean=None, min=None, max=None, count=0),
    ]
    fig = build_price_trend_chart(trend, dt.date(2026, 9, 18), "EUR", STYLE)
    # Highest fare, Lowest fare, Average price, + cheapest-average-fare star,
    # + cheapest-single-fare diamond (no "direct" marker since none was passed)
    assert len(fig.data) == 5
