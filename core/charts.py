"""Plotly figure builders for the route map and price-trend chart.

No framework dependency — these build plain go.Figure objects (which are
just JSON), so a future JS frontend can render the exact same figures via
Plotly.js without porting any of this logic. The only "framework" input
either function takes is a plain `style: dict` of color values, supplied by
the caller.
"""

import datetime as dt
import math

import plotly.graph_objects as go

from core.airports import all_airport_codes, format_location
from core.format import format_price, route_summary, stops_label

# Full neon theme: one fixed dark cyberpunk look. Route colors are the same
# eight-hue fixed order as the muted default, re-stepped for high chroma on a
# near-black surface and validated with the dataviz skill's
# validate_palette.js --mode dark --surface "#0a0118": lightness band,
# chroma floor, and contrast all pass; worst adjacent CVD ΔE 11.6, worst
# adjacent normal-vision ΔE 16.6 (both clear the 8/15 targets). Used directly
# here (rather than threaded through `style`) since it's specifically the
# dark backdrop these two chart functions draw markers/annotations against,
# not a themable color like the ones in `style`.
NEON_BG = "#0a0118"

# The canonical default style dict both build_route_map and
# build_price_trend_chart take as `style` — lives here (rather than in
# app.py or api/) so both the Streamlit UI and the API build figures against
# the exact same theme instead of risking two copies drifting apart.
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

ARC_POINTS_PER_LEG = 24
"""Interpolated points per leg: enough to bow lines apart and give a hover
target along the whole path, not just at the endpoint markers."""


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


def find_plottable_routes(
    results, airports: dict, style: dict
) -> tuple[list[tuple[int, object, list[str], list[dict]]], int]:
    """Find itineraries (up to one per style["route_colors"] entry, so every
    plotted route gets a distinct color) with fully known airport
    coordinates, in results order.

    Returns a list of (result_index, flight, airport_codes, airport_coords)
    tuples plus a count of routes skipped for missing coordinates.
    """
    max_routes = len(style["route_colors"])
    plottable = []
    skipped = 0
    for idx, flight in enumerate(results):
        if len(plottable) >= max_routes:
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


def build_route_map(
    plottable,
    style: dict,
    highlighted_indices: set[int],
    currency: str,
    airports: dict,
    include_all_airports: bool = True,
) -> go.Figure:
    """Build a route map from itineraries already resolved by
    find_plottable_routes, with every known airport also plotted as a small
    clickable dot so a route can be picked visually instead of just via the
    origin/destination dropdowns (see app.render_route_map for the click
    handling this trace's curve_number is reserved for).

    include_all_airports=False skips that trace entirely — the API uses
    this, since the ~7,884-airport trace (with a hover string per airport)
    would otherwise get re-sent on every single search response; a client
    that already has /api/airports cached can overlay it itself instead."""
    all_lats = [info["lat"] for _, _, _, coords in plottable for info in coords]
    all_lons = [info["lon"] for _, _, _, coords in plottable for info in coords]
    lat_span = (max(all_lats) - min(all_lats)) if all_lats else 0.0
    lon_span = (max(all_lons) - min(all_lons)) if all_lons else 0.0
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

    # Every known airport, small and muted, so any of them can be clicked to
    # pick a new origin/destination (see app.render_route_map) — sits at
    # curve_number == 2 * len(plottable), right after the halo and real
    # route traces above. Ordered via all_airport_codes so the click handler
    # can map a clicked point_index back to a code the same way.
    if include_all_airports:
        all_codes = all_airport_codes(airports)
        fig.add_trace(
            go.Scattergeo(
                lon=[airports[c]["lon"] for c in all_codes],
                lat=[airports[c]["lat"] for c in all_codes],
                mode="markers",
                marker=dict(size=4, color=style["airport_dot"], opacity=0.35),
                hovertext=[format_location(c, airports) for c in all_codes],
                hoverinfo="text",
                name="All airports",
                showlegend=False,
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
    # fitbounds="locations" would fit to *every* trace including the
    # all-airports one above, which spans nearly the whole globe — so with
    # it on, the view would always zoom out to the world regardless of how
    # local the found route is. Explicit lat/lon ranges padded around just
    # the route's own extent restore the "zoom to your results" behavior;
    # with no route to zoom to (plottable empty — pure airport-picker view),
    # leaving both unset falls back to natural earth's own default framing,
    # which already shows the whole world with no extra work.
    geo_range = {}
    if all_lats and all_lons:
        lat_pad = max(lat_span * 0.25, 8.0)
        lon_pad = max(lon_span * 0.25, 8.0)
        lat_lo = max(min(all_lats) - lat_pad, -85)
        lat_hi = min(max(all_lats) + lat_pad, 85)
        geo_range = dict(
            lataxis=dict(range=[lat_lo, lat_hi]),
            lonaxis=dict(range=[min(all_lons) - lon_pad, max(all_lons) + lon_pad]),
        )
    fig.update_geos(
        projection_type="natural earth",
        **geo_range,
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


def nice_log_ticks(lo: float, hi: float) -> list[float]:
    """Round 1-2-5-per-decade values spanning [lo, hi] (e.g. 200, 300, 500,
    1000, 2000) — Plotly's own log-axis minor ticks label as bare digits
    ("7", "6", "5"...) with no indication of scale, which reads as noise
    without the surrounding decade context."""
    if lo <= 0 or hi <= 0 or lo > hi:
        return []
    start_pow = math.floor(math.log10(lo))
    end_pow = math.ceil(math.log10(hi))
    ticks = {
        m * 10**p
        for p in range(start_pow, end_pow + 1)
        for m in (1, 2, 5)
        if lo * 0.9 <= m * 10**p <= hi * 1.1
    }
    return sorted(ticks)


def build_price_trend_chart(
    trend: list[dict],
    center_date: dt.date,
    currency: str,
    style: dict,
    direct: dict | None = None,
    x_range: tuple[dt.date, dt.date] | None = None,
) -> go.Figure:
    """Average price per day across the search window, with each day's
    actual lowest/highest observed fare drawn as vertical bars extending
    up/down from the average.

    x_range, if given, pins the x-axis to that (start, end) span regardless
    of which days in it actually have data yet — used while the trend is
    still streaming in so the axis stays put and days visibly fill in
    against a fixed width, instead of the axis growing on every redraw."""
    dates = [row["date"] for row in trend]
    means = [row["mean"] for row in trend]
    mins = [row["min"] for row in trend]
    maxes = [row["max"] for row in trend]
    all_prices = [v for v in (*means, *mins, *maxes) if v is not None]
    # error_y needs numeric magnitudes, not None, for days with no fares —
    # 0 draws a zero-length (invisible) bar, matching how means/mins/maxes
    # are already None for those days.
    max_reach = [
        (mx - m) if (m is not None and mx is not None) else 0
        for m, mx in zip(means, maxes, strict=True)
    ]
    min_reach = [
        (m - mn) if (m is not None and mn is not None) else 0
        for m, mn in zip(means, mins, strict=True)
    ]
    zeros = [0] * len(dates)

    avg_color = style["route_colors"][0]
    # Cheap→pricey color scale reusing the app's existing status hues (the
    # same green/amber/red already used for stop counts), so the Average
    # line's markers double as a heatmap and the lowest day pops out without
    # having to read the axis.
    known_means = [m for m in means if m is not None]
    price_scale = [[0.0, style["stop_ok"]], [0.5, style["stop_warn"]], [1.0, style["stop_bad"]]]
    # marker.color can't mix None with numbers the way y can (None there just
    # opens a gap) — days with no fares get a 0 placeholder that's never
    # actually drawn, since their y is None too.
    marker_colors = [m if m is not None else 0 for m in means]

    fig = go.Figure()
    # Highest/lowest fare drawn as vertical bars reaching up/down from the
    # average, rather than lines of their own — two invisible-marker traces
    # anchored at the average price, each carrying a one-directional error
    # bar (Plotly can't color a single error_y's plus/minus sides
    # differently, hence two traces). Colored green/red to match the
    # cheap→pricey scale used elsewhere on this chart (the Average markers,
    # the cheapest callout).
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=means,
            mode="markers",
            # size=0 hides the marker on the chart itself (the error bar is
            # the whole point) while keeping full opacity, so the legend
            # swatch — which mirrors color/opacity, not marker size — still
            # renders in this color instead of going invisible too.
            marker=dict(size=0, color=style["stop_bad"]),
            error_y=dict(
                type="data",
                array=max_reach,
                arrayminus=zeros,
                color=style["stop_bad"],
                thickness=1.25,
                width=2,
            ),
            opacity=0.7,
            name="Highest fare",
            customdata=maxes,
            hovertemplate=f"Highest: %{{customdata:.0f}} {currency}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=means,
            mode="markers",
            marker=dict(size=0, color=style["stop_ok"]),
            error_y=dict(
                type="data",
                array=zeros,
                arrayminus=min_reach,
                color=style["stop_ok"],
                thickness=1.25,
                width=2,
            ),
            opacity=0.7,
            name="Lowest fare",
            customdata=mins,
            hovertemplate=f"Lowest: %{{customdata:.0f}} {currency}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=means,
            mode="lines+markers",
            name="Average price",
            line=dict(color=avg_color, width=2),
            marker=dict(
                size=9,
                color=marker_colors,
                colorscale=price_scale,
                cmin=min(known_means) if known_means else 0,
                cmax=max(known_means) if known_means else 1,
                line=dict(width=1, color=NEON_BG),
            ),
            hovertemplate=f"Average: %{{y:.0f}} {currency}<extra></extra>",
        )
    )

    # These callouts are all real marker traces sitting exactly on the point
    # they describe (rather than a floating text annotation, which can land
    # in an unpredictable spot and get lost against 180 days of data), with
    # their price in the legend and on hover. Same gold "cheapest" color for
    # all three, but a distinct shape per category so they don't read as one
    # mark when they land close together.
    gold = "#ffd700"
    avg_star = dict(symbol="star", size=16, color=gold, line=dict(width=1, color=NEON_BG))
    fare_diamond = dict(symbol="diamond", size=13, color=gold, line=dict(width=1, color=NEON_BG))
    direct_hexagram = dict(
        symbol="hexagram", size=15, color=gold, line=dict(width=1, color=NEON_BG)
    )
    if known_means:
        cheapest = min((row for row in trend if row["mean"] is not None), key=lambda r: r["mean"])
        fig.add_trace(
            go.Scatter(
                x=[cheapest["date"]],
                y=[cheapest["mean"]],
                mode="markers",
                marker=avg_star,
                name=f"Cheapest average fare: {format_price(round(cheapest['mean']), currency)}",
                hovertemplate=(
                    f"Cheapest average fare: {format_price(round(cheapest['mean']), currency)}"
                    "<extra></extra>"
                ),
            )
        )

    known_min_rows = [row for row in trend if row["min"] is not None]
    if known_min_rows:
        cheapest_fare = min(known_min_rows, key=lambda row: row["min"])
        fig.add_trace(
            go.Scatter(
                x=[cheapest_fare["date"]],
                y=[cheapest_fare["min"]],
                mode="markers",
                marker=fare_diamond,
                name=f"Cheapest fare: {format_price(round(cheapest_fare['min']), currency)}",
                hovertemplate=(
                    f"Cheapest fare: {format_price(round(cheapest_fare['min']), currency)}"
                    "<extra></extra>"
                ),
            )
        )

    if direct is not None:
        fig.add_trace(
            go.Scatter(
                x=[direct["date"]],
                y=[direct["price"]],
                mode="markers",
                marker=direct_hexagram,
                name=f"Cheapest direct flight: {format_price(round(direct['price']), currency)}",
                hovertemplate=(
                    f"Cheapest direct flight: {format_price(round(direct['price']), currency)}"
                    "<extra></extra>"
                ),
            )
        )

    # add_vline chokes on date-typed x-axes in some Plotly versions — a shape
    # anchored to the x axis (yref="paper" spans the full plot height) is the
    # version-safe way to mark the searched date. A wider, translucent copy
    # underneath gives it a glow halo, the same technique the route map uses
    # for its highlighted flight paths — makes it read as "the" reference
    # point rather than just another gridline.
    center_iso = center_date.isoformat()
    search_color = "#00f0ff"
    fig.add_shape(
        type="line",
        xref="x",
        yref="paper",
        x0=center_iso,
        x1=center_iso,
        y0=0,
        y1=1,
        line=dict(color="rgba(0,240,255,0.25)", width=8),
        layer="below",
    )
    fig.add_shape(
        type="line",
        xref="x",
        yref="paper",
        x0=center_iso,
        x1=center_iso,
        y0=0,
        y1=1,
        line=dict(color=search_color, width=2),
    )
    fig.add_annotation(
        x=center_iso,
        y=1,
        yref="paper",
        yanchor="bottom",
        text="<b>Searched date</b>",
        showarrow=False,
        font=dict(color=search_color, size=12),
        bgcolor=NEON_BG,
        bordercolor=search_color,
        borderwidth=1,
        borderpad=4,
    )

    # Plotly's log-axis autorange miscomputes badly when combined with
    # error_y bars (observed: a legitimate price range blew up to a
    # 10^0–10^264 axis) — setting the range explicitly from our own data
    # sidesteps that entirely. range values for a log axis are log10 of the
    # displayed bounds, not the bounds themselves.
    if all_prices:
        log_range = [math.log10(min(all_prices) * 0.85), math.log10(max(all_prices) * 1.15)]
        tick_values = nice_log_ticks(min(all_prices), max(all_prices))
        tick_text = [format_price(round(v), currency) for v in tick_values]
    else:
        log_range = None
        tick_values = tick_text = None

    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(color=style["legend_font"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            color=style["legend_font"],
            tickfont=dict(color=style["legend_font"]),
            range=[x_range[0].isoformat(), x_range[1].isoformat()] if x_range else None,
        ),
        yaxis=dict(
            title=dict(text=f"Price ({currency})", font=dict(color=style["legend_title_font"])),
            type="log",
            range=log_range,
            tickmode="array",
            tickvals=tick_values,
            ticktext=tick_text,
            gridcolor="rgba(255,255,255,0.08)",
            color=style["legend_font"],
            tickfont=dict(color=style["legend_font"]),
        ),
    )
    return fig
