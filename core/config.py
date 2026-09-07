"""Shared search-form configuration.

Not business logic, but small and used by enough consumers (Streamlit,
the API) that it belongs here rather than being duplicated in each.
"""

from typing import get_args

from fast_flights.types import Currency

MAX_STOPS_OPTIONS = {"Any": None, "Nonstop": 0, "1 stop": 1, "2 stops": 2}

# Price-trend window sizes offered in the search form (label -> number of
# consecutive dates the sweep covers, centered on the searched date). 1 =
# off: just the searched date, no sweep. Bigger values fire that many
# Google Flights lookups, so the choices stay coarse.
TREND_DAYS_OPTIONS = {
    "Off": 1,
    "7 days": 7,
    "15 days": 15,
    "30 days": 30,
    "60 days": 60,
    "90 days": 90,
    "180 days": 180,
}
DEFAULT_TREND_DAYS = 1

CURRENCY_CODES = sorted(get_args(Currency))
DEFAULT_CURRENCY = "EUR"
