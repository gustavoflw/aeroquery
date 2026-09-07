import datetime as dt

from core.format import (
    format_duration,
    format_price,
    route_layovers,
    route_summary,
    route_total_duration,
    stops_label,
)
from tests.conftest import make_flight, make_leg


def test_format_price_known_currency_uses_symbol():
    assert format_price(100, "EUR") == "€100"
    assert format_price(50, "USD") == "$50"


def test_format_price_unknown_currency_falls_back_to_code():
    assert format_price(275, "ALL") == "275 ALL"


def test_format_duration():
    assert format_duration(dt.timedelta(hours=2, minutes=5)) == "2h 05m"
    assert format_duration(dt.timedelta(minutes=45)) == "0h 45m"


def test_stops_label():
    assert stops_label(0) == "Direct"
    assert stops_label(1) == "1 stop"
    assert stops_label(2) == "2 stops"


def test_route_layovers_and_total_duration_for_a_connection():
    legs = [
        make_leg(
            from_code="OPO",
            to_code="LIS",
            dep=(2026, 9, 18, 8, 0),
            arr=(2026, 9, 18, 9, 0),
        ),
        make_leg(
            from_code="LIS",
            to_code="MLA",
            dep=(2026, 9, 18, 11, 30),
            arr=(2026, 9, 18, 14, 0),
        ),
    ]
    flight = make_flight(price=200, legs=legs)

    layovers = route_layovers(flight)
    assert layovers == [("LIS", dt.timedelta(hours=2, minutes=30))]
    assert route_total_duration(flight) == dt.timedelta(hours=6)


def test_route_summary_includes_price_stops_and_layover():
    legs = [
        make_leg(from_code="OPO", to_code="LIS", dep=(2026, 9, 18, 8, 0), arr=(2026, 9, 18, 9, 0)),
        make_leg(
            from_code="LIS", to_code="MLA", dep=(2026, 9, 18, 11, 0), arr=(2026, 9, 18, 13, 30)
        ),
    ]
    flight = make_flight(price=150, airlines=["TAP"], legs=legs)

    summary = route_summary(flight, "EUR")
    assert "€150" in summary
    assert "1 stop" in summary
    assert "Layover at LIS" in summary
