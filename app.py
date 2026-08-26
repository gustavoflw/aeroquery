import datetime as dt
import math
from typing import get_args

import airportsdata
import plotly.graph_objects as go
import streamlit as st
from fast_flights import FlightQuery, Passengers, create_query, get_flights
from fast_flights.exceptions import FlightsNotFound
from fast_flights.integrations.base import FetchIntegration
from fast_flights.querying import Query
from fast_flights.types import Currency
from primp import Client

# Google shows a cookie-consent wall instead of results to requests from the
# EU/EEA. Sending an already-accepted SOCS cookie skips it.
EU_CONSENT_COOKIE = "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiA_LyaBg"

# Full neon theme: one fixed dark cyberpunk look, not toggled by the viewer's
# light/dark preference (see current_map_style). Route colors are the same
# eight-hue fixed order as the muted default, re-stepped for high chroma on a
# near-black surface and validated with the dataviz skill's
# validate_palette.js --mode dark --surface "#0a0118": lightness band,
# chroma floor, and contrast all pass; worst adjacent CVD ΔE 11.6, worst
# adjacent normal-vision ΔE 16.6 (both clear the 8/15 targets).
NEON_BG = "#0a0118"
MAP_STYLE = dict(
    route_colors=[
        "#0095ff",  # blue
        "#e86c00",  # orange
        "#00ad8b",  # aqua
        "#b09300",  # yellow
        "#fc00ca",  # magenta
        "#00b31e",  # green
        "#7700ff",  # violet
        "#ff002b",  # red
    ],
    landcolor="#140a24",
    countrycolor="#3d2a63",
    airport_dot="#00f0ff",
    airport_text="#e7e6f5",
    legend_font="#e7e6f5",
    legend_title_font="#a79fd1",
    panel_bg="rgba(14,7,28,0.82)",
    panel_border="rgba(0,240,255,0.35)",
    stop_ok="#00ad8b",
    stop_warn="#b09300",
    stop_bad="#ff002b",
    layover_accent="#ffcc4d",
)
MAX_ROUTES_ON_MAP = len(MAP_STYLE["route_colors"])

MAX_STOPS_OPTIONS = {"Any": None, "Nonstop": 0, "1 stop": 1, "2 stops": 2}

CURRENCY_CODES = sorted(get_args(Currency))
DEFAULT_CURRENCY = "EUR"
# Symbols for commonly-used currencies; anything else falls back to a
# trailing ISO code (e.g. "275 ALL") in format_price.
CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥", "INR": "₹",
    "BRL": "R$", "KRW": "₩", "RUB": "₽", "AUD": "A$", "CAD": "C$", "MXN": "MX$",
    "ZAR": "R", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł", "TRY": "₺",
    "THB": "฿", "VND": "₫", "HKD": "HK$", "SGD": "S$", "NZD": "NZ$", "ILS": "₪",
    "IDR": "Rp", "MYR": "RM", "PHP": "₱", "CHF": "CHF",
}

ARC_POINTS_PER_LEG = 24
"""Interpolated points per leg: enough to bow lines apart and give a hover
target along the whole path, not just at the endpoint markers."""


class EuConsentFetch(FetchIntegration):
    def fetch_html(self, q: Query | str, /) -> str:
        client = Client(
            impersonate="chrome_145", impersonate_os="macos", referer=True, cookie_store=True
        )
        client.set_cookies("https://www.google.com", {"SOCS": EU_CONSENT_COOKIE})
        params = q.params() if isinstance(q, Query) else {"q": q}
        return client.get("https://www.google.com/travel/flights", params=params).text


@st.cache_resource
def load_airports() -> dict:
    return airportsdata.load("IATA")


@st.cache_data
def airport_codes(_airports: dict) -> list[str]:
    return sorted(_airports)


def format_airport(code: str, airports: dict) -> str:
    info = airports.get(code)
    if not info:
        return code
    return f"{code} — {info['city']}, {info['country']} · {info['name']}"


@st.cache_data(ttl=600, show_spinner="Searching flights...")
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
    try:
        return get_flights(query, integration=EuConsentFetch())
    except FlightsNotFound:
        return []
    except (TypeError, IndexError):
        # fast_flights' parser assumes a "no flights" response always shapes
        # up a specific way (e.g. payload[3] == [None]), but Google sends
        # other malformed/truncated payloads for "no results" too (payload[3]
        # as bare None, payload[7] missing entries, etc). The library crashes
        # on those instead of raising FlightsNotFound — every shape we've
        # hit means the same thing for us: nothing to show.
        return []


def current_map_style() -> dict:
    return MAP_STYLE


def inject_neon_theme() -> None:
    """Global chrome for the full neon theme: dark gradient backdrop, glowing
    title/button/inputs. Targets Streamlit's data-testid hooks (stable across
    releases) rather than its auto-generated emotion classes."""
    background_css = f"""
        [data-testid="stApp"] {{
            background:
                radial-gradient(1200px 600px at 12% -10%, rgba(0,240,255,0.12), transparent 60%),
                radial-gradient(1000px 700px at 105% 15%, rgba(255,43,214,0.12), transparent 55%),
                linear-gradient(180deg, {NEON_BG} 0%, #050010 100%);
        }}
    """
    st.markdown(
        """<style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&display=swap');
        """
        + background_css
        + """
        [data-testid="stApp"], [data-testid="stApp"] p, [data-testid="stApp"] label,
        [data-testid="stApp"] span {
            color: #e7e6f5;
        }
        [data-testid="stHeader"] {
            background: rgba(8,2,20,0.65) !important;
            backdrop-filter: blur(8px);
        }
        [data-testid="stHeader"] svg { color: #e7e6f5 !important; fill: currentColor !important; }

        [data-testid="stHeading"] h1 {
            font-family: 'Orbitron', sans-serif;
            font-weight: 800;
            color: #f5f3ff;
            text-shadow:
                0 0 8px rgba(0,240,255,0.85),
                0 0 22px rgba(0,240,255,0.45),
                0 0 46px rgba(255,43,214,0.35);
            letter-spacing: 0.5px;
        }

        [data-testid="stForm"] {
            background: rgba(18,10,36,0.55) !important;
            border: 1px solid rgba(0,240,255,0.30) !important;
            border-radius: 16px !important;
            box-shadow: 0 0 24px rgba(0,240,255,0.12), 0 0 60px rgba(255,43,214,0.08) !important;
            backdrop-filter: blur(10px);
        }

        [data-testid="stSelectbox"] div[role="group"],
        [data-testid="stDateInputField"] {
            background: rgba(18,10,36,0.65) !important;
            border: 1px solid rgba(0,240,255,0.30) !important;
            border-radius: 10px !important;
            transition: box-shadow 0.15s ease, border-color 0.15s ease;
        }
        [data-testid="stSelectbox"] div[role="group"]:focus-within,
        [data-testid="stDateInputField"]:focus-within {
            border-color: rgba(0,240,255,0.9) !important;
            box-shadow: 0 0 0 1px rgba(0,240,255,0.35), 0 0 14px rgba(0,240,255,0.55) !important;
        }
        [data-testid="stSelectbox"] input { color: #f2f0ff !important; }

        [data-testid="stFormSubmitButton"] button {
            background: linear-gradient(
                135deg, rgba(0,240,255,0.20), rgba(255,43,214,0.20)
            ) !important;
            border: 1px solid rgba(0,240,255,0.65) !important;
            color: #f5f3ff !important;
            box-shadow: 0 0 10px rgba(0,240,255,0.45), 0 0 24px rgba(255,43,214,0.20) !important;
            transition: box-shadow 0.15s ease, border-color 0.15s ease;
        }
        [data-testid="stFormSubmitButton"] button:hover {
            border-color: rgba(255,43,214,0.85) !important;
            box-shadow: 0 0 16px rgba(0,240,255,0.75), 0 0 40px rgba(255,43,214,0.5) !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )


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


def stops_color(stops: int, style: dict) -> str:
    if stops == 0:
        return style["stop_ok"]
    if stops == 1:
        return style["stop_warn"]
    return style["stop_bad"]


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


def find_plottable_routes(
    results, airports: dict
) -> tuple[list[tuple[int, object, list[str], list[dict]]], int]:
    """Find itineraries (up to MAX_ROUTES_ON_MAP) with fully known airport
    coordinates, in results order.

    Returns a list of (result_index, flight, airport_codes, airport_coords)
    tuples plus a count of routes skipped for missing coordinates.
    """
    plottable = []
    skipped = 0
    for idx, flight in enumerate(results):
        if len(plottable) >= MAX_ROUTES_ON_MAP:
            break
        codes = [
            flight.flights[0].from_airport.code,
            *(leg.to_airport.code for leg in flight.flights),
        ]
        coords = [airports[c] for c in codes if c in airports]
        if len(coords) != len(codes):
            skipped += 1
            continue
        plottable.append((idx, flight, codes, coords))
    return plottable, skipped


def route_colors_by_index(plottable, style: dict) -> dict[int, str]:
    """Map each plottable route's result-list index to its map line color,
    so the itinerary cards can show a matching swatch."""
    route_colors = style["route_colors"]
    return {idx: route_colors[i % len(route_colors)] for i, (idx, *_rest) in enumerate(plottable)}


def render_highlight_dot(idx: int, color: str, highlighted: bool) -> bool:
    """A small round button colored like the route's map line — click to
    toggle it in/out of the highlighted set. Styled via Streamlit's
    st.button(key=...) → .st-key-<key> CSS hook rather than a labeled
    button, so it reads as a dot next to the title, not a separate control."""
    fill = color if highlighted else "transparent"
    glow = f"0 0 10px {color}, 0 0 20px {color}66" if highlighted else "none"
    st.markdown(
        f"""<style>
        .st-key-swatch_{idx} button {{
            min-width: 20px !important; width: 20px !important;
            min-height: 20px !important; height: 20px !important;
            padding: 0 !important; border-radius: 50% !important;
            background: {fill} !important; border: 1.5px solid {color} !important;
            box-shadow: {glow} !important;
            line-height: 1;
        }}
        .st-key-swatch_{idx} button:hover {{
            background: {color} !important; border-color: {color} !important;
            box-shadow: 0 0 10px {color}, 0 0 20px {color}66 !important;
        }}
        .st-key-swatch_{idx} button p {{ display: none; }}
        </style>""",
        unsafe_allow_html=True,
    )
    return st.button(
        "●", key=f"swatch_{idx}", width="content", type="tertiary", help="Highlight on map"
    )


def render_itinerary_card(
    idx: int, flight, color: str | None, highlighted: bool, style: dict, currency: str
) -> None:
    legs = flight.flights
    layovers = dict(route_layovers(flight))
    total = format_duration(route_total_duration(flight))
    layover_color = style["layover_accent"]

    # Streamlit's default markdown-table CSS puts a faint border on every
    # <td>; with border-collapse those merge into a full grid, so each cell
    # below explicitly opts back out with border:none.
    rows = []
    for leg in legs:
        dep = f"{leg.departure.time[0]:02d}:{leg.departure.time[1]:02d}"
        arr = f"{leg.arrival.time[0]:02d}:{leg.arrival.time[1]:02d}"
        rows.append(
            '<tr style="font-size:0.85rem;">'
            f'<td style="border:none;padding:1px 8px 1px 0;white-space:nowrap;">'
            f"<b>{leg.from_airport.code}</b> {dep}</td>"
            '<td style="border:none;padding:1px 6px;opacity:0.5;">→</td>'
            f'<td style="border:none;padding:1px 12px 1px 0;white-space:nowrap;">'
            f"<b>{leg.to_airport.code}</b> {arr}</td>"
            f'<td style="border:none;padding:1px 0;opacity:0.6;font-size:0.78rem;'
            f'white-space:nowrap;">{leg.duration} min · {leg.plane_type}</td>'
            "</tr>"
        )
        wait = layovers.get(leg.to_airport.code)
        if wait is not None:
            rows.append(
                '<tr><td colspan="4" style="border:none;padding:1px 0 5px 0;'
                f'font-size:0.78rem;text-align:center;color:{layover_color};">'
                f"⋯ layover at {leg.to_airport.code}: {format_duration(wait)} ⋯</td></tr>"
            )
    # Total time closes out the same right-hand column the per-leg
    # duration/aircraft text sits in, with a hairline over it enclosing the
    # legs above like a table footer.
    hairline = "border:none;border-top:1px solid rgba(128,128,128,0.25);"
    rows.append(
        "<tr>"
        f'<td colspan="3" style="{hairline}"></td>'
        f'<td style="{hairline}padding:4px 0 0 0;font-size:0.8rem;font-weight:600;'
        f'opacity:0.85;white-space:nowrap;">Total: {total}</td>'
        "</tr>"
    )
    table_style = "border-collapse:collapse;width:100%;margin-top:4px;"
    table_html = f'<table style="{table_style}">{"".join(rows)}</table>'

    stops = len(legs) - 1
    badge_color = stops_color(stops, style)

    # Cards without a plottable route (color is None) fall back to a neutral
    # violet glow instead of losing the neon border entirely.
    card_glow = color or "#7a5cff"
    border_alpha, shadow_alpha, shadow_reach = ("aa", "66", "26px") if highlighted else (
        "55",
        "33",
        "14px",
    )
    st.markdown(
        f"""<style>
        .st-key-card_{idx} {{
            background: rgba(18,10,36,0.55) !important;
            border: 1px solid {card_glow}{border_alpha} !important;
            border-radius: 12px !important;
            box-shadow: 0 0 {shadow_reach} {card_glow}{shadow_alpha} !important;
            transition: box-shadow 0.15s ease, border-color 0.15s ease;
        }}
        .st-key-card_{idx}:hover {{
            border-color: {card_glow}cc !important;
            box-shadow: 0 0 22px {card_glow}55 !important;
        }}
        </style>""",
        unsafe_allow_html=True,
    )
    with st.container(border=True, key=f"card_{idx}"):
        dot_col, title_col, meta_col = st.columns(
            [0.3, 3, 1], vertical_alignment="center", gap="small"
        )
        with dot_col:
            if color and render_highlight_dot(idx, color, highlighted):
                indices = st.session_state.highlighted_indices
                indices.symmetric_difference_update({idx})
                st.rerun()
        title_col.markdown(
            f"**{'/'.join(flight.airlines)} — {format_price(flight.price, currency)}**"
        )
        meta_col.markdown(
            f'<div style="text-align:right;font-size:0.85rem;font-weight:600;'
            f'color:{badge_color};">{stops_label(stops)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(table_html, unsafe_allow_html=True)


def bowed_leg_points(
    lon1: float, lat1: float, lon2: float, lat2: float, bow: float
) -> tuple[list[float], list[float]]:
    """Interpolate a leg into points that bow sideways by `bow` degrees at
    the midpoint and taper to zero at both ends, so the curve still touches
    the real airport coordinates but clears other routes sharing the leg."""
    dlon, dlat = lon2 - lon1, lat2 - lat1
    length = math.hypot(dlon, dlat)
    perp_lon, perp_lat = (-dlat / length, dlon / length) if length else (0.0, 0.0)

    lons, lats = [], []
    for i in range(ARC_POINTS_PER_LEG):
        t = i / (ARC_POINTS_PER_LEG - 1)
        offset = math.sin(math.pi * t) * bow
        lons.append(lon1 + dlon * t + perp_lon * offset)
        lats.append(lat1 + dlat * t + perp_lat * offset)
    return lons, lats


def build_route_map(
    plottable, style: dict, highlighted_indices: set[int], currency: str
) -> go.Figure | None:
    """Build a route map from itineraries already resolved by find_plottable_routes."""
    if not plottable:
        return None

    all_lats = [info["lat"] for _, _, _, coords in plottable for info in coords]
    all_lons = [info["lon"] for _, _, _, coords in plottable for info in coords]
    lat_span = max(all_lats) - min(all_lats)
    lon_span = max(all_lons) - min(all_lons)
    # Bow magnitude scales with the plotted area so it separates overlapping
    # legs without visibly distorting routes at any zoom level.
    bow_unit = max(lat_span, lon_span, 1.0) * 0.015

    fig = go.Figure()
    seen_airports: dict[str, tuple[float, float]] = {}
    routes = []

    for i, (idx, flight, codes, coords) in enumerate(plottable):
        for code, info in zip(codes, coords, strict=True):
            seen_airports[code] = (info["lat"], info["lon"])

        lane = i - (len(plottable) - 1) / 2
        bow = bow_unit * lane
        lons: list[float] = []
        lats: list[float] = []
        for leg_start, leg_end in zip(coords, coords[1:], strict=False):
            # Cap the bow to a fraction of the leg's own length so short
            # hops (e.g. between nearby regional airports) don't loop back
            # on themselves — only long legs get the full lane offset.
            leg_length = math.hypot(
                leg_end["lon"] - leg_start["lon"], leg_end["lat"] - leg_start["lat"]
            )
            leg_bow = max(-leg_length * 0.12, min(leg_length * 0.12, bow))
            leg_lons, leg_lats = bowed_leg_points(
                leg_start["lon"], leg_start["lat"], leg_end["lon"], leg_end["lat"], leg_bow
            )
            lons.extend(leg_lons)
            lats.extend(leg_lats)

        route_colors = style["route_colors"]
        routes.append(
            dict(
                lons=lons,
                lats=lats,
                color=route_colors[i % len(route_colors)],
                hover=route_summary(flight, currency),
                name=f"{format_price(flight.price, currency)} · {stops_label(len(codes) - 2)}",
                is_selected=idx in highlighted_indices,
                is_dimmed=bool(highlighted_indices) and idx not in highlighted_indices,
            )
        )

    # Neon glow halo: a wider, low-opacity line behind each route, brighter
    # when selected. Halo traces carry no markers, so Plotly's on_select
    # (which needs marker hit-targets — see the real trace below) never
    # fires on them; they only shift every later curve_number by len(routes),
    # a fixed offset render_route_map accounts for.
    for r in routes:
        fig.add_trace(
            go.Scattergeo(
                lon=r["lons"],
                lat=r["lats"],
                mode="lines",
                line=dict(width=14 if r["is_selected"] else 8, color=r["color"]),
                opacity=(0.4 if r["is_selected"] else 0.14) * (0.3 if r["is_dimmed"] else 1.0),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    for r in routes:
        fig.add_trace(
            go.Scattergeo(
                lon=r["lons"],
                lat=r["lats"],
                # Plotly's on_select needs actual selectable points, and a
                # bare "lines" trace doesn't offer any — hover still works
                # on it via a generous nearest-point search, but clicking
                # never resolves to a selection. Invisible markers (opacity
                # 0) at every interpolated point make the whole path
                # clickable while keeping the visible line unchanged.
                mode="lines+markers",
                line=dict(width=4 if r["is_selected"] else 2, color=r["color"]),
                marker=dict(size=14, color=r["color"], opacity=0),
                opacity=0.2 if r["is_dimmed"] else 1.0,
                name=r["name"],
                hovertext=[r["hover"]] * len(r["lons"]),
                hoverinfo="text",
            )
        )

    airport_lons = [lon for _, lon in seen_airports.values()]
    airport_lats = [lat for lat, _ in seen_airports.values()]
    fig.add_trace(
        go.Scattergeo(
            lon=airport_lons,
            lat=airport_lats,
            mode="markers",
            marker=dict(size=20, color=style["airport_dot"]),
            opacity=0.25,
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scattergeo(
            lon=airport_lons,
            lat=airport_lats,
            mode="markers+text",
            marker=dict(size=8, color=style["airport_dot"]),
            text=list(seen_airports.keys()),
            textposition="top center",
            textfont=dict(color=style["airport_text"], size=11),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    map_height = 600
    # fitbounds="locations" fits the projection to the plotted points in the
    # browser at render time, using the map's *actual* rendered pixel size —
    # unlike a fixed lataxis/lonaxis range computed here in Python, this
    # adapts correctly to any container width (and stays correct if the
    # window resizes) instead of guessing a pixel width up front.
    fig.update_geos(
        projection_type="natural earth",
        fitbounds="locations",
        bgcolor="rgba(0,0,0,0)",
        showframe=False,
        showland=True,
        landcolor=style["landcolor"],
        showocean=True,
        oceancolor="rgba(0,0,0,0)",
        showlakes=True,
        lakecolor="rgba(0,0,0,0)",
        showcountries=True,
        countrycolor=style["countrycolor"],
        coastlinecolor=style["countrycolor"],
    )
    fig.update_layout(
        height=map_height,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            title=dict(text="Price · stops", font=dict(color=style["legend_title_font"])),
            font=dict(color=style["legend_font"]),
            orientation="h",
            yanchor="bottom",
            y=0,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render_route_map(
    plottable,
    skipped: int,
    total_results: int,
    style: dict,
    highlighted_indices: set[int],
    currency: str,
) -> None:
    fig = build_route_map(plottable, style, highlighted_indices, currency)
    if fig is None:
        st.info("No airport coordinates available to plot a map for these results.")
        return
    event = st.plotly_chart(
        fig,
        width="stretch",
        on_select="rerun",
        selection_mode="points",
        key="route_map",
    )

    # Plotly's own selection stays "on" for a curve until something else is
    # clicked, so only react when the clicked curve actually changes —
    # otherwise every unrelated rerun (e.g. clicking a dot) would re-toggle
    # whatever route was last clicked on the map. build_route_map adds one
    # non-selectable glow-halo trace per route before the real (clickable)
    # ones, so the real traces sit at [n_routes, 2*n_routes) — offset by
    # n_routes to get back to plottable's index.
    n_routes = len(plottable)
    points = event.selection.points if event else []
    clicked_curve = points[-1]["curve_number"] if points else None
    if (
        clicked_curve is not None
        and n_routes <= clicked_curve < 2 * n_routes
        and clicked_curve != st.session_state.last_map_click_curve
    ):
        st.session_state.last_map_click_curve = clicked_curve
        clicked_idx = plottable[clicked_curve - n_routes][0]
        highlighted_indices.symmetric_difference_update({clicked_idx})
        st.rerun()

    plotted = len(plottable)
    noun = "itinerary" if plotted == 1 else "itineraries"
    caption = f"Showing the {plotted} cheapest {noun} on the map"
    if total_results > plotted + skipped:
        caption += f" (of {total_results} found)"
    if skipped:
        caption += f" · {skipped} skipped for missing airport coordinates"
    st.caption(caption + ".")


def render_results(
    results,
    plottable,
    skipped: int,
    style: dict,
    colors_by_index: dict[int, str],
    currency: str,
) -> None:
    """Itinerary list and map in one frame: the map fills the whole width,
    and the list floats over its left side as a scrollable, translucent
    panel — the map is always centered by build_route_map's own padding,
    so the left side rarely has route lines worth covering."""
    with st.container(key="map_overlay"):
        st.markdown(
            f"""<style>
            .st-key-map_overlay {{ position: relative; }}
            .st-key-list_panel {{
                position: absolute; top: 12px; left: 12px; z-index: 10;
                width: 340px; max-width: 40%; max-height: 550px;
                overflow-y: auto; padding: 12px 14px;
                background: {style["panel_bg"]}; border: 1px solid {style["panel_border"]};
                border-radius: 12px; backdrop-filter: blur(6px);
                box-shadow: 0 0 26px rgba(0,240,255,0.10), 0 0 60px rgba(255,43,214,0.06);
            }}
            </style>""",
            unsafe_allow_html=True,
        )
        with st.container(key="list_panel"):
            st.markdown("**All itineraries**")
            for idx, flight in enumerate(results):
                highlighted = idx in st.session_state.highlighted_indices
                render_itinerary_card(
                    idx, flight, colors_by_index.get(idx), highlighted, style, currency
                )

        highlighted_indices = st.session_state.highlighted_indices
        render_route_map(plottable, skipped, len(results), style, highlighted_indices, currency)


st.set_page_config(page_title="Aeroquery", page_icon="✈️", layout="wide")
inject_neon_theme()
st.title("✈️ Flight Search")

if "highlighted_indices" not in st.session_state:
    st.session_state.highlighted_indices = set()
if "last_map_click_curve" not in st.session_state:
    st.session_state.last_map_click_curve = None

airports = load_airports()
codes = airport_codes(airports)

query_params = st.query_params
default_origin = query_params.get("origin", "")
default_destination = query_params.get("destination", "")
origin_index = codes.index(default_origin) if default_origin in codes else None
destination_index = codes.index(default_destination) if default_destination in codes else None
try:
    default_date = dt.date.fromisoformat(query_params.get("date", ""))
except ValueError:
    default_date = dt.date.today() + dt.timedelta(days=7)
default_max_stops = query_params.get("max_stops", "Any")
if default_max_stops not in MAX_STOPS_OPTIONS:
    default_max_stops = "Any"
default_currency = query_params.get("currency", DEFAULT_CURRENCY)
if default_currency not in CURRENCY_CODES:
    default_currency = DEFAULT_CURRENCY

with st.form("search_form"):
    col1, col2 = st.columns(2)
    origin = col1.selectbox(
        "Origin airport",
        codes,
        index=origin_index,
        format_func=lambda c: format_airport(c, airports),
        placeholder="Search by code, city, or airport name",
    )
    destination = col2.selectbox(
        "Destination airport",
        codes,
        index=destination_index,
        format_func=lambda c: format_airport(c, airports),
        placeholder="Search by code, city, or airport name",
    )
    date_col, stops_col, currency_col = st.columns(3)
    date = date_col.date_input("Departure date", value=default_date)
    max_stops_choice = stops_col.selectbox(
        "Max stops",
        list(MAX_STOPS_OPTIONS),
        index=list(MAX_STOPS_OPTIONS).index(default_max_stops),
    )
    currency = currency_col.selectbox(
        "Currency",
        CURRENCY_CODES,
        index=CURRENCY_CODES.index(default_currency),
    )
    submitted = st.form_submit_button("Search")

# A page reload (F5) resends the last-set query params, so re-running
# whenever they're present replays the same search without a click.
run_search = submitted or bool(default_origin and default_destination)

if run_search:
    if not origin or not destination:
        st.error("Please enter both an origin and a destination airport.")
    else:
        st.query_params["origin"] = origin
        st.query_params["destination"] = destination
        st.query_params["date"] = date.isoformat()
        st.query_params["max_stops"] = max_stops_choice
        st.query_params["currency"] = currency

        results = search_flights(
            origin, destination, date.isoformat(), MAX_STOPS_OPTIONS[max_stops_choice], currency
        )
        if not results:
            st.warning("No flights found for that route and date.")
        else:
            results = sorted(results, key=lambda f: f.price)
            style = current_map_style()
            plottable, skipped = find_plottable_routes(results, airports)
            colors_by_index = route_colors_by_index(plottable, style)

            render_results(results, plottable, skipped, style, colors_by_index, currency)
