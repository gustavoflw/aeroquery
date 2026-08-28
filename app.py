import datetime as dt

import streamlit as st
import streamlit.components.v1 as components

from core.airports import (
    METRO_AREAS,
    METRO_MEMBERS,
    all_airport_codes,
    format_location,
    load_airports,
    location_codes,
)
from core.charts import (
    MAP_STYLE,
    NEON_BG,
    build_price_trend_chart,
    build_route_map,
    find_plottable_routes,
    route_colors_by_index,
)
from core.config import CURRENCY_CODES, DEFAULT_CURRENCY, MAX_STOPS_OPTIONS
from core.flights import (
    PRICE_TREND_TOTAL_DAYS,
    cheapest_direct_flight,
    fetch_price_trend,
    price_trend_stats,
    price_trend_window,
)
from core.format import (
    format_duration,
    format_eta,
    format_price,
    route_layovers,
    route_total_duration,
    stops_color,
    stops_label,
)


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

        /* The glow panel now wraps both the reactive origin/destination
        pickers and the submit-gated form beneath them (see search_panel in
        the main script), so the form itself renders borderless/transparent
        inside it instead of getting a second nested box. */
        .st-key-search_panel {
            background: rgba(18,10,36,0.55) !important;
            border: 1px solid rgba(0,240,255,0.30) !important;
            border-radius: 16px !important;
            box-shadow: 0 0 24px rgba(0,240,255,0.12), 0 0 60px rgba(255,43,214,0.08) !important;
            backdrop-filter: blur(10px);
            padding: 1.5rem 1.5rem 0.5rem 1.5rem;
        }
        [data-testid="stForm"] {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
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


def inject_dropdown_scroll_fix() -> None:
    """The airport selectboxes hold ~7,900 options in a virtualized listbox;
    once one has a value (true after the first search, since the last pick
    is restored from the URL), reopening it auto-scrolls the popup to that
    value's position deep in the alphabetical list instead of the top — so
    every reopen lands somewhere random instead of ready to type a new
    search. That scroll is applied by a React effect that runs shortly
    *after* the popup mounts (confirmed empirically: settles ~20ms after
    open and never moves again), not at insertion time — so resetting
    scrollTop immediately on mount just gets overwritten a beat later.
    Streamlit's selectbox exposes no option to disable this, so the fix
    reaches past it: a MutationObserver reports that *something* changed
    under <body>, then a debounced sweep (well after React's own scroll has
    settled) forces every open listbox back to the top. st.markdown can't
    run <script> tags (HTML inserted that way is inert in browsers);
    components.html renders a real iframe, whose script can reach
    window.parent.document since everything here is same-origin."""
    components.html(
        """<script>
        (function () {
            const doc = window.parent.document;
            if (doc.__aeroqueryScrollFixInstalled) return;
            doc.__aeroqueryScrollFixInstalled = true;

            let pending = null;
            function scheduleReset() {
                if (pending) return;
                pending = setTimeout(() => {
                    pending = null;
                    doc.querySelectorAll("[role='listbox']").forEach((box) => {
                        box.scrollTop = 0;
                    });
                }, 100);
            }

            new MutationObserver(scheduleReset).observe(doc.body, {
                childList: true,
                subtree: true,
            });
        })();
        </script>""",
        height=0,
    )


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
                f"layover at {leg.to_airport.code}: {format_duration(wait)}</td></tr>"
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


def render_route_map(
    plottable,
    skipped: int,
    total_results: int,
    style: dict,
    highlighted_indices: set[int],
    currency: str,
    airports: dict,
) -> None:
    fig = build_route_map(plottable, style, highlighted_indices, currency, airports)
    event = st.plotly_chart(
        fig,
        width="stretch",
        on_select="rerun",
        selection_mode="points",
        key="route_map",
    )

    # Plotly's own selection stays "on" for a curve until something else is
    # clicked, so only react when the clicked curve/point actually changes —
    # otherwise every unrelated rerun (e.g. clicking a dot) would re-fire
    # whatever was last clicked on the map. build_route_map adds one
    # non-selectable glow-halo trace per route before the real (clickable)
    # ones, so the real route traces sit at [n_routes, 2*n_routes) — offset
    # by n_routes to get back to plottable's index. The all-airports trace
    # comes right after, at exactly 2*n_routes.
    n_routes = len(plottable)
    all_airports_curve = 2 * n_routes
    points = event.selection.points if event else []
    clicked = points[-1] if points else None
    clicked_curve = clicked["curve_number"] if clicked else None

    if (
        clicked_curve is not None
        and n_routes <= clicked_curve < 2 * n_routes
        and clicked_curve != st.session_state.last_map_click_curve
    ):
        st.session_state.last_map_click_curve = clicked_curve
        clicked_idx = plottable[clicked_curve - n_routes][0]
        highlighted_indices.symmetric_difference_update({clicked_idx})
        st.rerun()

    if clicked_curve == all_airports_curve:
        click_point = (clicked_curve, clicked["point_index"])
        if click_point != st.session_state.last_airport_click_point:
            st.session_state.last_airport_click_point = click_point
            st.session_state.map_selected_airport = all_airport_codes(airports)[
                clicked["point_index"]
            ]
            st.rerun()

    plotted = len(plottable)
    if plotted == 0:
        caption = "No itineraries could be plotted — showing all airports instead"
    else:
        noun = "itinerary" if plotted == 1 else "itineraries"
        caption = f"Showing the {plotted} cheapest {noun} on the map"
        if total_results > plotted + skipped:
            caption += f" (of {total_results} found)"
    if skipped:
        caption += f" · {skipped} skipped for missing airport coordinates"
    st.caption(caption + " · click any airport to pick a new origin or destination.")


def render_price_trend(
    trend: list[dict],
    center_date: dt.date,
    currency: str,
    style: dict,
    direct: dict | None = None,
    x_range: tuple[dt.date, dt.date] | None = None,
) -> None:
    found_days = sum(1 for row in trend if row["mean"] is not None)
    st.subheader(f"📈 Price trend — {PRICE_TREND_TOTAL_DAYS} days")
    if found_days == 0:
        st.info("No price data found in this date window.")
        return
    fig = build_price_trend_chart(trend, center_date, currency, style, direct, x_range)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"{found_days} of {len(trend)} days had available fares · "
        "vertical bars reach from the average up to that day's highest fare "
        "and down to its lowest · "
        "marker color scales from cheapest (green) to priciest (red)."
    )
    if direct is None:
        st.caption("No nonstop flights found anywhere in this window.")


def render_airport_picker_panel(airports: dict) -> None:
    """A small fixed panel (not a context menu at the click point — Streamlit
    has no way to anchor UI to a Plotly click's pixel position) that appears
    once an airport dot on the map has been clicked, letting it be applied
    as the new origin or destination for another search."""
    code = st.session_state.map_selected_airport
    if not code:
        return
    with st.container(key="airport_picker_panel", border=True):
        label_col, origin_col, dest_col, dismiss_col = st.columns([4, 1, 1, 1])
        label_col.markdown(f"**Selected on map:** {format_location(code, airports)}")
        if origin_col.button("Set as origin", key="set_origin_from_map"):
            st.query_params["origin"] = code
            st.session_state.map_selected_airport = None
            st.rerun()
        if dest_col.button("Set as destination", key="set_destination_from_map"):
            st.query_params["destination"] = code
            st.session_state.map_selected_airport = None
            st.rerun()
        if dismiss_col.button("✕", key="dismiss_airport_picker", help="Dismiss"):
            st.session_state.map_selected_airport = None
            st.rerun()


def render_results(
    results,
    plottable,
    skipped: int,
    style: dict,
    colors_by_index: dict[int, str],
    currency: str,
    airports: dict,
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
        render_route_map(
            plottable, skipped, len(results), style, highlighted_indices, currency, airports
        )

    render_airport_picker_panel(airports)


st.set_page_config(page_title="Aeroquery", page_icon="✈️", layout="wide")
inject_neon_theme()
inject_dropdown_scroll_fix()
st.title("✈️ Aeroquery")

if "highlighted_indices" not in st.session_state:
    st.session_state.highlighted_indices = set()
if "last_map_click_curve" not in st.session_state:
    st.session_state.last_map_click_curve = None
if "last_airport_click_point" not in st.session_state:
    st.session_state.last_airport_click_point = None
if "map_selected_airport" not in st.session_state:
    st.session_state.map_selected_airport = None

airports = load_airports()
codes = location_codes(airports)

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

with st.container(key="search_panel"):
    # Origin/destination live outside the form so picking a metro city can
    # immediately reveal its "narrow to a specific airport" dropdown — forms
    # only rerun on submit, so nested widgets inside one can't react to each
    # other's current value until then. The date/stops/currency/submit stay
    # inside the form below so adjusting them doesn't re-trigger anything
    # until "Search" is actually pressed.
    col1, col2 = st.columns(2)
    origin_choice = col1.selectbox(
        "Origin airport or city",
        codes,
        index=origin_index,
        format_func=lambda c: format_location(c, airports),
        placeholder="Search by code, city, or airport name",
    )
    origin = origin_choice
    if origin_choice in METRO_AREAS:
        origin_narrowed = col1.selectbox(
            f"Narrow to a specific {METRO_AREAS[origin_choice][0]} airport (optional)",
            ["All airports", *METRO_MEMBERS[origin_choice]],
            format_func=lambda c: c if c == "All airports" else format_location(c, airports),
        )
        if origin_narrowed != "All airports":
            origin = origin_narrowed

    destination_choice = col2.selectbox(
        "Destination airport or city",
        codes,
        index=destination_index,
        format_func=lambda c: format_location(c, airports),
        placeholder="Search by code, city, or airport name",
    )
    destination = destination_choice
    if destination_choice in METRO_AREAS:
        destination_narrowed = col2.selectbox(
            f"Narrow to a specific {METRO_AREAS[destination_choice][0]} airport (optional)",
            ["All airports", *METRO_MEMBERS[destination_choice]],
            format_func=lambda c: c if c == "All airports" else format_location(c, airports),
        )
        if destination_narrowed != "All airports":
            destination = destination_narrowed

    with st.form("search_form"):
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
        st.error("Please enter both an origin and a destination airport or city.")
    else:
        st.query_params["origin"] = origin
        st.query_params["destination"] = destination
        st.query_params["date"] = date.isoformat()
        st.query_params["max_stops"] = max_stops_choice
        st.query_params["currency"] = currency

        max_stops = MAX_STOPS_OPTIONS[max_stops_choice]
        style = current_map_style()

        # progress_slot is created first so it stays pinned above the chart
        # and results as they fill in below it — otherwise it'd render
        # wherever the on_progress callback happens to first fire, which is
        # after both of those already have content on screen. The searched
        # date resolves before the rest of the window (see
        # core.flights.fetch_price_trend), so results_slot fills in on the
        # very first callback and never touches again — chart_slot instead
        # redraws on every callback, so the graph visibly grows as the
        # remaining days of the window stream in behind the searched date.
        progress_slot = st.empty()
        chart_slot = st.empty()
        results_slot = st.empty()
        results_rendered = [False]
        trend_window = price_trend_window(date.isoformat())

        def stream_update(results_by_date: dict[str, list]) -> None:
            with chart_slot.container():
                render_price_trend(
                    price_trend_stats(results_by_date),
                    date,
                    currency,
                    style,
                    cheapest_direct_flight(results_by_date),
                    trend_window,
                )

            if not results_rendered[0] and date.isoformat() in results_by_date:
                results_rendered[0] = True
                results = sorted(results_by_date[date.isoformat()], key=lambda f: f.price)
                with results_slot.container():
                    if not results:
                        st.warning("No flights found for that route and date.")
                    else:
                        plottable, skipped = find_plottable_routes(results, airports, style)
                        colors_by_index = route_colors_by_index(plottable, style)
                        render_results(
                            results, plottable, skipped, style, colors_by_index, currency, airports
                        )

        def stream_progress(completed: int, total: int, eta_seconds: float | None) -> None:
            eta_text = f" · ~{format_eta(eta_seconds)} left" if eta_seconds is not None else ""
            progress_slot.progress(
                completed / total, text=f"Searched {completed} of {total} days{eta_text}"
            )

        fetch_price_trend(
            origin,
            destination,
            date.isoformat(),
            max_stops,
            currency,
            on_update=stream_update,
            on_progress=stream_progress,
        )
        progress_slot.empty()
