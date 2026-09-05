"""Pure formatting and per-flight derivation helpers.

No framework dependency — safe to import from the API service or tests.
"""

import datetime as dt

# Symbols for commonly-used currencies; anything else falls back to a
# trailing ISO code (e.g. "275 ALL") in format_price.
CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥", "INR": "₹",
    "BRL": "R$", "KRW": "₩", "RUB": "₽", "AUD": "A$", "CAD": "C$", "MXN": "MX$",
    "ZAR": "R", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł", "TRY": "₺",
    "THB": "฿", "VND": "₫", "HKD": "HK$", "SGD": "S$", "NZD": "NZ$", "ILS": "₪",
    "IDR": "Rp", "MYR": "RM", "PHP": "₱", "CHF": "CHF",
}


def leg_datetime(sdt) -> dt.datetime:
    return dt.datetime(*sdt.date, *sdt.time)


def format_duration(td: dt.timedelta) -> str:
    minutes = int(td.total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def format_price(price: int, currency: str) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency)
    return f"{symbol}{price}" if symbol else f"{price} {currency}"


def route_layovers(flight) -> list[tuple[str, dt.timedelta]]:
    legs = flight.flights
    return [
        (
            legs[i].to_airport.code,
            leg_datetime(legs[i + 1].departure) - leg_datetime(legs[i].arrival),
        )
        for i in range(len(legs) - 1)
    ]


def route_total_duration(flight) -> dt.timedelta:
    legs = flight.flights
    return leg_datetime(legs[-1].arrival) - leg_datetime(legs[0].departure)


def stops_label(stops: int) -> str:
    return "Direct" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"


def route_summary(flight, currency: str) -> str:
    layovers = route_layovers(flight)
    total = format_duration(route_total_duration(flight))
    lines = [
        f"<b>{'/'.join(flight.airlines)} — {format_price(flight.price, currency)}</b>",
        f"{stops_label(len(layovers))} · Total time: {total}",
    ]
    for code, wait in layovers:
        lines.append(f"Layover at {code}: {format_duration(wait)}")
    return "<br>".join(lines)
