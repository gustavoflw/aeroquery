import datetime as dt
import math

import airportsdata
import plotly.graph_objects as go
import streamlit as st
from fast_flights import FlightQuery, Passengers, create_query, get_flights
from fast_flights.exceptions import FlightsNotFound
from fast_flights.integrations.base import FetchIntegration
from fast_flights.querying import Query
from primp import Client

# Google shows a cookie-consent wall instead of results to requests from the
# EU/EEA. Sending an already-accepted SOCS cookie skips it.
EU_CONSENT_COOKIE = "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiA_LyaBg"

# Fixed categorical order, validated for CVD/normal-vision separation in both
# modes — see the dataviz skill. Routes are capped at this length so every
# route on the map gets a distinct, distinguishable color.
MAP_STYLES = {
    "light": dict(
        route_colors=[
            "#2a78d6",  # blue
            "#eb6834",  # orange
            "#1baf7a",  # aqua
            "#eda100",  # yellow
            "#e87ba4",  # magenta
            "#008300",  # green
            "#4a3aa7",  # violet
            "#e34948",  # red
        ],
        landcolor="#f0efec",
        countrycolor="#c3c2b7",
        airport_dot="#898781",
        airport_text="#52514e",
        legend_font="#0b0b0b",
        legend_title_font="#52514e",
        panel_bg="rgba(252,252,251,0.92)",
        panel_border="rgba(11,11,11,0.10)",
    ),
    "dark": dict(
        route_colors=[
            "#3987e5",  # blue
            "#d95926",  # orange
            "#199e70",  # aqua
            "#c98500",  # yellow
            "#d55181",  # magenta
            "#008300",  # green
            "#9085e9",  # violet
            "#e66767",  # red
        ],
        landcolor="#2c2c2a",
        countrycolor="#383835",
        airport_dot="#898781",
        airport_text="#c3c2b7",
        legend_font="#c3c2b7",
        legend_title_font="#898781",
        panel_bg="rgba(26,26,25,0.92)",
        panel_border="rgba(255,255,255,0.10)",
    ),
}
MAX_ROUTES_ON_MAP = len(MAP_STYLES["light"]["route_colors"])

MAX_STOPS_OPTIONS = {"Any": None, "Nonstop": 0, "1 stop": 1, "2 stops": 2}

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


@st.cache_data(ttl=600, show_spinner="Searching flights...")
def search_flights(origin: str, destination: str, date_iso: str, max_stops: int | None):
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
    try:
        theme_type = st.context.theme.type
    except Exception:
        theme_type = None
    return MAP_STYLES.get(theme_type, MAP_STYLES["dark"])


def leg_datetime(sdt) -> dt.datetime:
    return dt.datetime(*sdt.date, *sdt.time)


def format_duration(td: dt.timedelta) -> str:
    minutes = int(td.total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


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


def route_summary(flight) -> str:
    layovers = route_layovers(flight)
    total = format_duration(route_total_duration(flight))
    lines = [
        f"<b>{'/'.join(flight.airlines)} — ${flight.price}</b>",
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
    st.markdown(
        f"""<style>
        .st-key-swatch_{idx} button {{
            min-width: 20px !important; width: 20px !important;
            min-height: 20px !important; height: 20px !important;
            padding: 0 !important; border-radius: 50% !important;
            background: {fill} !important; border: 1.5px solid {color} !important;
            line-height: 1;
        }}
        .st-key-swatch_{idx} button:hover {{
            background: {color} !important; border-color: {color} !important;
        }}
        .st-key-swatch_{idx} button p {{ display: none; }}
        </style>""",
        unsafe_allow_html=True,
    )
    return st.button(
        "●", key=f"swatch_{idx}", width="content", type="tertiary", help="Highlight on map"
    )


def render_itinerary_card(idx: int, flight, color: str | None, highlighted: bool) -> None:
    legs = flight.flights
    layovers = dict(route_layovers(flight))
    total = format_duration(route_total_duration(flight))

    rows = []
    for leg in legs:
        dep = f"{leg.departure.time[0]:02d}:{leg.departure.time[1]:02d}"
        arr = f"{leg.arrival.time[0]:02d}:{leg.arrival.time[1]:02d}"
        rows.append(
            '<tr style="font-size:0.85rem;">'
            f'<td style="padding:1px 8px 1px 0;white-space:nowrap;">'
            f"<b>{leg.from_airport.code}</b> {dep}</td>"
            '<td style="padding:1px 6px;opacity:0.5;">→</td>'
            f'<td style="padding:1px 12px 1px 0;white-space:nowrap;">'
            f"<b>{leg.to_airport.code}</b> {arr}</td>"
            f'<td style="padding:1px 0;opacity:0.6;font-size:0.78rem;white-space:nowrap;">'
            f"{leg.duration} min · {leg.plane_type}</td>"
            "</tr>"
        )
        wait = layovers.get(leg.to_airport.code)
        if wait is not None:
            rows.append(
                '<tr><td colspan="4" style="padding:1px 0 5px 0;opacity:0.55;font-size:0.78rem;">'
                f"⋯ layover at {leg.to_airport.code}: {format_duration(wait)} ⋯</td></tr>"
            )
    # Total time closes out the same right-hand column the per-leg
    # duration/aircraft text sits in, with a hairline over it enclosing the
    # legs above like a table footer.
    rows.append(
        '<tr style="border-top:1px solid rgba(128,128,128,0.25);">'
        '<td colspan="3"></td>'
        '<td style="padding:4px 0 0 0;font-size:0.8rem;font-weight:600;opacity:0.85;'
        f'white-space:nowrap;">Total: {total}</td>'
        "</tr>"
    )
    table_style = "border-collapse:collapse;width:100%;margin-top:4px;"
    table_html = f'<table style="{table_style}">{"".join(rows)}</table>'

    with st.container(border=True):
        dot_col, title_col, meta_col = st.columns(
            [0.3, 3, 1], vertical_alignment="center", gap="small"
        )
        with dot_col:
            if color and render_highlight_dot(idx, color, highlighted):
                indices = st.session_state.highlighted_indices
                indices.symmetric_difference_update({idx})
                st.rerun()
        title_col.markdown(f"**{'/'.join(flight.airlines)} — ${flight.price}**")
        meta_col.markdown(
            f'<div style="text-align:right;opacity:0.65;font-size:0.85rem;">'
            f"{stops_label(len(legs) - 1)}</div>",
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


def build_route_map(plottable, style: dict, highlighted_indices: set[int]) -> go.Figure | None:
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

        hover = route_summary(flight)
        route_colors = style["route_colors"]
        color = route_colors[i % len(route_colors)]
        stops = len(codes) - 2
        is_selected = idx in highlighted_indices
        is_dimmed = bool(highlighted_indices) and not is_selected
        fig.add_trace(
            go.Scattergeo(
                lon=lons,
                lat=lats,
                # Plotly's on_select needs actual selectable points, and a
                # bare "lines" trace doesn't offer any — hover still works
                # on it via a generous nearest-point search, but clicking
                # never resolves to a selection. Invisible markers (opacity
                # 0) at every interpolated point make the whole path
                # clickable while keeping the visible line unchanged.
                mode="lines+markers",
                line=dict(width=4 if is_selected else 2, color=color),
                marker=dict(size=14, color=color, opacity=0),
                opacity=0.2 if is_dimmed else 1.0,
                name=f"${flight.price} · {stops_label(stops)}",
                hovertext=[hover] * len(lons),
                hoverinfo="text",
            )
        )

    fig.add_trace(
        go.Scattergeo(
            lon=[lon for _, lon in seen_airports.values()],
            lat=[lat for lat, _ in seen_airports.values()],
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
    plottable, skipped: int, total_results: int, style: dict, highlighted_indices: set[int]
) -> None:
    fig = build_route_map(plottable, style, highlighted_indices)
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
    # whatever route was last clicked on the map. Each route is exactly one
    # trace, so curve_number maps straight onto plottable's index.
    points = event.selection.points if event else []
    clicked_curve = points[-1]["curve_number"] if points else None
    if (
        clicked_curve is not None
        and clicked_curve < len(plottable)
        and clicked_curve != st.session_state.last_map_click_curve
    ):
        st.session_state.last_map_click_curve = clicked_curve
        clicked_idx = plottable[clicked_curve][0]
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
    results, plottable, skipped: int, style: dict, colors_by_index: dict[int, str]
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
            }}
            </style>""",
            unsafe_allow_html=True,
        )
        with st.container(key="list_panel"):
            st.markdown("**All itineraries**")
            for idx, flight in enumerate(results):
                highlighted = idx in st.session_state.highlighted_indices
                render_itinerary_card(idx, flight, colors_by_index.get(idx), highlighted)

        highlighted_indices = st.session_state.highlighted_indices
        render_route_map(plottable, skipped, len(results), style, highlighted_indices)


st.set_page_config(page_title="MyFlights", page_icon="✈️", layout="wide")
st.title("✈️ Flight Search")

if "highlighted_indices" not in st.session_state:
    st.session_state.highlighted_indices = set()
if "last_map_click_curve" not in st.session_state:
    st.session_state.last_map_click_curve = None

query_params = st.query_params
default_origin = query_params.get("origin", "")
default_destination = query_params.get("destination", "")
try:
    default_date = dt.date.fromisoformat(query_params.get("date", ""))
except ValueError:
    default_date = dt.date.today() + dt.timedelta(days=7)
default_max_stops = query_params.get("max_stops", "Any")
if default_max_stops not in MAX_STOPS_OPTIONS:
    default_max_stops = "Any"

with st.form("search_form"):
    col1, col2 = st.columns(2)
    origin = (
        col1.text_input("Origin airport", value=default_origin, placeholder="LIS").strip().upper()
    )
    destination = (
        col2.text_input("Destination airport", value=default_destination, placeholder="CWB")
        .strip()
        .upper()
    )
    date_col, stops_col = st.columns(2)
    date = date_col.date_input("Departure date", value=default_date)
    max_stops_choice = stops_col.selectbox(
        "Max stops",
        list(MAX_STOPS_OPTIONS),
        index=list(MAX_STOPS_OPTIONS).index(default_max_stops),
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

        results = search_flights(
            origin, destination, date.isoformat(), MAX_STOPS_OPTIONS[max_stops_choice]
        )
        if not results:
            st.warning("No flights found for that route and date.")
        else:
            results = sorted(results, key=lambda f: f.price)
            airports = load_airports()
            style = current_map_style()
            plottable, skipped = find_plottable_routes(results, airports)
            colors_by_index = route_colors_by_index(plottable, style)

            render_results(results, plottable, skipped, style, colors_by_index)
