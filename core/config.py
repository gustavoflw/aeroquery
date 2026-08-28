"""Shared search-form configuration.

Not business logic, but small and used by enough consumers (Streamlit,
the API) that it belongs here rather than being duplicated in each.
"""

from typing import get_args

from fast_flights.types import Currency

MAX_STOPS_OPTIONS = {"Any": None, "Nonstop": 0, "1 stop": 1, "2 stops": 2}

CURRENCY_CODES = sorted(get_args(Currency))
DEFAULT_CURRENCY = "EUR"
