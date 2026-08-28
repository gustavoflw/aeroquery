"""Flight search against Google Flights (via fast_flights) and the
price-trend sweep built on top of it.

No framework dependency — safe to call from Streamlit, a future API
service, or tests. UI concerns (progress bars, incremental chart redraws)
are surfaced purely through the on_update/on_progress callbacks below, so
this module never has to know what's rendering its results.
"""

import datetime as dt
import statistics
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from cachetools import TTLCache, cached
from fast_flights import FlightQuery, Passengers, create_query, get_flights
from fast_flights.exceptions import FlightsNotFound
from fast_flights.integrations.base import FetchIntegration
from fast_flights.querying import Query
from primp import Client

# Google shows a cookie-consent wall instead of results to requests from the
# EU/EEA. Sending an already-accepted SOCS cookie skips it.
EU_CONSENT_COOKIE = "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiA_LyaBg"

# Every search also fetches one day of prices at a time across a
# PRICE_TREND_TOTAL_DAYS span centered on the chosen date — shifted forward
# whenever that centering would reach before today, since Google Flights has
# no fares for past dates, so the trend always covers a full
# PRICE_TREND_TOTAL_DAYS days into the future.
PRICE_TREND_TOTAL_DAYS = 180
PRICE_TREND_MAX_WORKERS = 8
# Minimum time between progressive on_update callbacks while the sweep below
# is still running — firing on every single day would be far faster than a
# caller (e.g. a chart) could usefully redraw in response.
CHART_STREAM_INTERVAL_SECONDS = 0.5


class EuConsentFetch(FetchIntegration):
    def fetch_html(self, q: Query | str, /) -> str:
        client = Client(
            impersonate="chrome_145", impersonate_os="macos", referer=True, cookie_store=True
        )
        client.set_cookies("https://www.google.com", {"SOCS": EU_CONSENT_COOKIE})
        params = q.params() if isinstance(q, Query) else {"q": q}
        return client.get("https://www.google.com/travel/flights", params=params).text


def fetch_flights_with_retry(query: Query) -> list:
    """Fetch flights for an already-built query, retrying once on a
    malformed/incomplete response.

    fast_flights' parser assumes a "no flights" response always shapes up a
    specific way (e.g. payload[3] == [None]), but Google sends other
    malformed/truncated payloads too — including, apparently, pages that
    omit the ds:1 script tag it expects to find entirely (parser.py's
    script.text() then raises AttributeError on None). The library crashes
    on those instead of raising FlightsNotFound. Metro/city searches (e.g.
    "Stockholm — All airports") return a much larger payload than a single
    airport, which is more likely to get cut off mid-transfer under this
    app's concurrent thread pool — so before treating a parse failure as
    "nothing to show", it's worth one retry in case it was just a transient
    truncated fetch. FlightsNotFound is not retried: that's the library's
    own confident "no flights" signal, not a parse failure.
    """
    for attempt in range(2):
        try:
            return get_flights(query, integration=EuConsentFetch())
        except FlightsNotFound:
            return []
        except (TypeError, IndexError, AttributeError):
            if attempt == 1:
                return []
    return []  # unreachable


# Shared, process-wide TTL cache: keyed on every argument below (route
# "cities", date, stops, currency), so each day/route/filter combination is
# fetched from Google at most once every 24h — a search's 180-day sweep
# mostly hits cache after the first time, and re-running the same search
# later the same day is instant. maxsize is generous headroom over one
# search's own footprint (up to ~2 fetches/day * 181 days) so a handful of
# concurrent searches don't evict each other's entries. The lock only guards
# the cache dict itself (see cachetools' _locked wrapper) — it's released
# before the wrapped function runs, so the thread pool below stays fully
# concurrent; it just means two threads racing on the exact same cache miss
# can occasionally both fetch once, with cachetools keeping whichever result
# lands first. That's the same characteristic st.cache_data had before this
# module existed, not a new risk.
_search_cache: TTLCache = TTLCache(maxsize=10_000, ttl=86400)


@cached(cache=_search_cache, lock=threading.Lock())
def search_flights(
    origin: str, destination: str, date_iso: str, max_stops: int | None, currency: str
):
    query = create_query(
        flights=[
            FlightQuery(
                date=date_iso,
                from_airport=origin,
                to_airport=destination,
                max_stops=max_stops,
            ),
        ],
        seat="economy",
        trip="one-way",
        passengers=Passengers(adults=1),
        language="en-US",
        currency=currency,
    )
    results = fetch_flights_with_retry(query)

    if max_stops != 0:
        # Google's own "Best flights" ranking can quietly drop a genuinely
        # cheaper nonstop fare from an unrestricted-stops query — confirmed
        # live: OPO→MLA on 2026-09-18 returns 8 flights with no Ryanair
        # under max_stops=None, but the same €33 Ryanair nonstop shows up
        # the moment the query is restricted to max_stops=0. So always also
        # fetch nonstop-only and fold in anything missing from the main
        # result (the recursive call hits this same cache, keyed on its own
        # max_stops=0, so it's free on any repeat search). Wrapped in its own
        # try/except — this second request doubles our odds of a transient
        # network/parsing hiccup on any given day, and one day's nonstop
        # fetch failing shouldn't take out that day's whole result.
        try:
            nonstop = search_flights(origin, destination, date_iso, 0, currency)
        except Exception:
            nonstop = []
        seen = {flight_identity(f) for f in results if len(f.flights) == 1}
        results = results + [f for f in nonstop if flight_identity(f) not in seen]

    return results


def flight_identity(flight) -> tuple:
    """Best-effort identity for a nonstop flight, used to dedupe the merge
    above — fast_flights results carry no id of their own."""
    leg = flight.flights[0]
    return (flight.price, tuple(flight.airlines), leg.departure.time, leg.arrival.time)


def price_trend_window(center_date_iso: str) -> tuple[dt.date, dt.date]:
    """The (start, end) date bounds fetch_price_trend sweeps for a given
    searched date — see fetch_price_trend for why this isn't always
    centered. Shared with the chart builder so the x-axis can be pinned to
    the same fixed range from the first render instead of growing with
    however much data has streamed in so far."""
    center = dt.date.fromisoformat(center_date_iso)
    start = max(dt.date.today(), center - dt.timedelta(days=PRICE_TREND_TOTAL_DAYS // 2))
    return start, start + dt.timedelta(days=PRICE_TREND_TOTAL_DAYS)


def fetch_price_trend(
    origin: str,
    destination: str,
    center_date_iso: str,
    max_stops: int | None,
    currency: str,
    on_update: Callable[[dict[str, list]], None] | None = None,
    on_progress: Callable[[int, int, float | None], None] | None = None,
) -> dict[str, list]:
    """Fetch every day across a PRICE_TREND_TOTAL_DAYS span centered on the
    searched date. The span shifts forward whenever centering it would start
    before today, so it always covers a full PRICE_TREND_TOTAL_DAYS days
    from wherever it starts. Each date is independently cached by
    search_flights, so this is only ever slow on a genuine cache miss.

    The searched date itself is fetched first, synchronously, and handed to
    on_update alone before the rest of the window is even submitted to the
    thread pool — so a caller can render it immediately rather than waiting
    on the full sweep. on_update then fires again periodically (throttled to
    CHART_STREAM_INTERVAL_SECONDS) as the remaining days stream in, and once
    more at the end with the complete result.

    on_progress(completed, total, eta_seconds), if given, fires on the same
    cadence — once after the searched date resolves (completed=1,
    eta_seconds=None) and once per remaining day after that (eta_seconds is
    None again once nothing is left). It reports raw numbers rather than
    formatted text so a caller can present them however it likes (a
    Streamlit progress bar, an SSE payload, a plain log line, ...).

    Returns {date_iso: [Flight, ...]}.
    """
    start, _ = price_trend_window(center_date_iso)
    dates = [start + dt.timedelta(days=offset) for offset in range(PRICE_TREND_TOTAL_DAYS + 1)]
    total = len(dates)

    results_by_date: dict[str, list] = {
        center_date_iso: search_flights(origin, destination, center_date_iso, max_stops, currency)
    }
    if on_update:
        on_update(dict(results_by_date))
    if on_progress:
        on_progress(1, total, None)

    remaining_dates = [d for d in dates if d.isoformat() != center_date_iso]
    started = time.monotonic()
    last_update = started
    with ThreadPoolExecutor(max_workers=PRICE_TREND_MAX_WORKERS) as pool:
        futures = {
            pool.submit(search_flights, origin, destination, d.isoformat(), max_stops, currency): d
            for d in remaining_dates
        }
        # as_completed (rather than iterating futures in submission order)
        # so progress advances as results actually arrive, and the ETA below
        # is based on real elapsed-per-result pace rather than the order
        # requests happened to be submitted in.
        for completed, future in enumerate(as_completed(futures), start=2):
            d = futures[future]
            try:
                results_by_date[d.isoformat()] = future.result()
            except Exception:
                # A single date failing (network hiccup, an unexpected
                # payload shape) shouldn't take down the whole comparison —
                # treat it the same as "no flights found that day".
                results_by_date[d.isoformat()] = []
            remaining = total - completed
            if on_progress:
                eta = (
                    (time.monotonic() - started) / (completed - 1) * remaining
                    if remaining
                    else None
                )
                on_progress(completed, total, eta)
            now = time.monotonic()
            if on_update and (now - last_update >= CHART_STREAM_INTERVAL_SECONDS or not remaining):
                on_update(dict(results_by_date))
                last_update = now
    return results_by_date


def price_trend_stats(results_by_date: dict[str, list]) -> list[dict]:
    """Per-day price stats across a fetch_price_trend result, sorted by date."""
    stats = []
    for date_iso in sorted(results_by_date):
        prices = [f.price for f in results_by_date[date_iso]]
        stats.append(
            dict(
                date=dt.date.fromisoformat(date_iso),
                mean=statistics.fmean(prices) if prices else None,
                min=min(prices) if prices else None,
                max=max(prices) if prices else None,
                count=len(prices),
            )
        )
    return stats


def cheapest_direct_flight(results_by_date: dict[str, list]) -> dict | None:
    """The single cheapest nonstop flight found anywhere in the trend
    window, or None if no nonstop flights turned up on any sampled day."""
    best = None
    for date_iso, flights in results_by_date.items():
        for flight in flights:
            if len(flight.flights) != 1:
                continue
            if best is None or flight.price < best["price"]:
                best = dict(date=dt.date.fromisoformat(date_iso), price=flight.price)
    return best
