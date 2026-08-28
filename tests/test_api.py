import json

from fastapi.testclient import TestClient

import api.main as api_main
from tests.conftest import make_flight, make_leg


def test_get_airports_returns_real_data():
    client = TestClient(api_main.app)
    resp = client.get("/api/airports")

    assert resp.status_code == 200
    body = resp.json()
    assert body["airports"]["CDG"]["city"] == "Paris"
    assert body["metro_areas"]["STO"] == {
        "city": "Stockholm",
        "country": "SE",
        "members": ["ARN", "BMA"],
    }


def test_get_config_exposes_currencies_symbols_and_stop_options():
    client = TestClient(api_main.app)
    resp = client.get("/api/config")

    assert resp.status_code == 200
    body = resp.json()
    assert "EUR" in body["currencies"]
    assert body["default_currency"] == "EUR"
    assert body["currency_symbols"]["EUR"] == "€"
    assert body["max_stops_options"] == {"Any": None, "Nonstop": 0, "1 stop": 1, "2 stops": 2}
    assert len(body["map_style"]["route_colors"]) == 8
    assert body["neon_bg"] == "#0a0118"


def test_get_search_returns_sorted_results_and_map_figure_without_all_airports(monkeypatch):
    def fake_search_flights(origin, destination, date_iso, max_stops, currency):
        return [
            make_flight(price=200, legs=[make_leg("CDG", "JFK")]),
            make_flight(price=100, legs=[make_leg("CDG", "JFK")]),
        ]

    monkeypatch.setattr(api_main, "search_flights", fake_search_flights)

    client = TestClient(api_main.app)
    resp = client.get(
        "/api/search",
        params=dict(origin="CDG", destination="JFK", date="2026-09-18", currency="EUR"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert [r["price"] for r in body["results"]] == [100, 200]
    assert body["results"][0]["stops"] == 0
    assert body["map_figure"]["data"]
    # include_all_airports=False — the ~7,884-point trace shouldn't ship here.
    assert all(trace.get("name") != "All airports" for trace in body["map_figure"]["data"])
    # Both CDG/JFK flights have real coordinates, so both plot, in
    # price-sorted order — route 0 in the figure is results[0], etc.
    assert body["route_result_indices"] == [0, 1]


def test_get_trend_streams_progress_then_trend_events(monkeypatch):
    def fake_fetch_price_trend(
        origin, destination, date, max_stops, currency, on_update=None, on_progress=None
    ):
        on_progress(1, 2, None)
        on_update({date: [make_flight(price=99, legs=[make_leg("CDG", "JFK")])]})
        on_progress(2, 2, None)
        return {}

    monkeypatch.setattr(api_main, "fetch_price_trend", fake_fetch_price_trend)

    client = TestClient(api_main.app)
    with client.stream(
        "GET",
        "/api/trend",
        params=dict(origin="CDG", destination="JFK", date="2026-09-18", currency="EUR"),
    ) as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    events = [json.loads(line[len("data: ") :]) for line in lines]
    assert [e["type"] for e in events] == ["progress", "trend", "progress", "done"]
    assert events[0] == {"type": "progress", "completed": 1, "total": 2, "eta_seconds": None}
    assert events[1]["stats"][0]["mean"] == 99
    assert events[1]["cheapest_direct"]["price"] == 99
