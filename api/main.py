"""FastAPI backend wrapping core.* — runs alongside the existing Streamlit
app on its own port (see .claude/js-migration-plan.md, Phase 1). Nothing
here is wired into the Streamlit UI yet; it exists to prove core.* works as
a real HTTP service ahead of a JS frontend actually calling it.

Run with: uv run uvicorn api.main:app --reload --port 8000
"""

import asyncio
import json
import queue

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from core.airports import METRO_AREAS, METRO_MEMBERS, load_airports
from core.charts import MAP_STYLE, NEON_BG, build_route_map, find_plottable_routes
from core.config import CURRENCY_CODES, DEFAULT_CURRENCY, MAX_STOPS_OPTIONS
from core.flights import (
    cheapest_direct_flight,
    fetch_price_trend,
    price_trend_stats,
    search_flights,
)
from core.format import CURRENCY_SYMBOLS, leg_datetime

app = FastAPI(title="AeroQuery API")


def serialize_flight(flight) -> dict:
    return {
        "price": flight.price,
        "airlines": flight.airlines,
        "stops": len(flight.flights) - 1,
        "legs": [
            {
                "from_airport": leg.from_airport.code,
                "to_airport": leg.to_airport.code,
                "departure": leg_datetime(leg.departure).isoformat(),
                "arrival": leg_datetime(leg.arrival).isoformat(),
                "duration_minutes": leg.duration,
                "plane_type": leg.plane_type,
            }
            for leg in flight.flights
        ],
    }


@app.get("/api/airports")
def get_airports():
    """Every known airport plus metro-area groupings — meant to be fetched
    once and cached client-side, not re-fetched per search (see
    build_route_map's include_all_airports for the other half of that
    tradeoff)."""
    airports = load_airports()
    return {
        "airports": {
            code: {
                "city": info.get("city"),
                "country": info.get("country"),
                "name": info.get("name"),
                "lat": info.get("lat"),
                "lon": info.get("lon"),
            }
            for code, info in airports.items()
        },
        "metro_areas": {
            code: {"city": city, "country": country, "members": METRO_MEMBERS.get(code, [])}
            for code, (city, country) in METRO_AREAS.items()
        },
    }


@app.get("/api/config")
def get_config():
    """Search-form configuration: every currency fast_flights supports (not
    just the ones with a nice symbol), the symbol table for formatting
    prices client-side, the max-stops filter options, and the color theme
    (map_style/neon_bg) so a client-built chart — see /api/trend, whose
    price-trend chart is built in JS rather than sent as figure JSON —
    matches build_route_map's colors exactly. Static for the life of the
    process — fetch once, same as /api/airports."""
    return {
        "currencies": CURRENCY_CODES,
        "default_currency": DEFAULT_CURRENCY,
        "currency_symbols": CURRENCY_SYMBOLS,
        "max_stops_options": MAX_STOPS_OPTIONS,
        "map_style": MAP_STYLE,
        "neon_bg": NEON_BG,
    }


@app.get("/api/search")
def get_search(
    origin: str,
    destination: str,
    date: str,
    max_stops: int | None = None,
    currency: str = "EUR",
):
    """One date's sorted itinerary list plus a ready-to-render route map
    figure (Plotly JSON — a JS frontend can hand this straight to
    Plotly.js). The all-airports trace is deliberately left out here; a
    client already holding /api/airports can overlay it itself."""
    airports = load_airports()
    results = sorted(
        search_flights(origin, destination, date, max_stops, currency), key=lambda f: f.price
    )
    plottable, skipped = find_plottable_routes(results, airports, MAP_STYLE)
    fig = build_route_map(
        plottable, MAP_STYLE, set(), currency, airports, include_all_airports=False
    )
    return {
        "date": date,
        "currency": currency,
        "results": [serialize_flight(f) for f in results],
        "skipped_for_map": skipped,
        "map_figure": json.loads(fig.to_json()),
        # Route i in map_figure (i.e. halo trace i / real trace n+i) is
        # results[route_result_indices[i]] — lets a client map a clicked
        # route back to the itinerary it belongs to. Mirrors plottable's own
        # (idx, flight, codes, coords) tuples, just the idx half.
        "route_result_indices": [idx for idx, *_ in plottable],
    }


@app.get("/api/trend")
async def get_trend(
    origin: str,
    destination: str,
    date: str,
    max_stops: int | None = None,
    currency: str = "EUR",
):
    """Server-Sent Events stream of the same progressive sweep app.py's
    stream_update/stream_progress render into Streamlit placeholders — here
    each on_update/on_progress firing becomes one `data: {...}` event
    instead. fetch_price_trend itself is synchronous (it runs its own
    thread pool internally), so it's offloaded to FastAPI's default
    executor and its callbacks relay through a plain thread-safe Queue into
    this async generator.

    The stream ends with an explicit {"type": "done"} event rather than
    just closing the connection — plain EventSource treats a closed
    connection as "reconnect", not "finished", so without a terminal event
    a client has no reliable signal to call .close() on before the browser
    tries to reopen it (which would silently kick off a second, redundant
    180-day sweep).
    """

    async def event_stream():
        events: queue.Queue = queue.Queue()
        done = object()

        def on_progress(completed, total, eta_seconds):
            events.put(
                {
                    "type": "progress",
                    "completed": completed,
                    "total": total,
                    "eta_seconds": eta_seconds,
                }
            )

        def on_update(results_by_date):
            events.put(
                {
                    "type": "trend",
                    "stats": price_trend_stats(results_by_date),
                    "cheapest_direct": cheapest_direct_flight(results_by_date),
                }
            )

        def run():
            try:
                fetch_price_trend(
                    origin,
                    destination,
                    date,
                    max_stops,
                    currency,
                    on_update=on_update,
                    on_progress=on_progress,
                )
            finally:
                events.put(done)

        loop = asyncio.get_event_loop()
        run_future = loop.run_in_executor(None, run)

        while True:
            item = await loop.run_in_executor(None, events.get)
            if item is done:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

        await run_future  # surface any exception raised inside run()
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
