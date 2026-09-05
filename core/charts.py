"""Plotly figure builders for the route map.

No framework dependency — these build plain go.Figure objects (which are
just JSON), so the JS frontend renders the exact same figure via Plotly.js
without porting any of this logic. The only "framework" input build_route_map
takes is a plain `style: dict` of color values, supplied by the caller.

(The price-trend chart is built client-side instead — see
web/src/trendChartMath.ts — since /api/trend streams pre-aggregated stats
rather than a figure per event.)
"""

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
# dark backdrop build_route_map draws markers/annotations against, not a
# themable color like the ones in `style`. Also sent over /api/config so the
# client-built trend chart draws against the same backdrop.
NEON_BG = "#0a0118"

# The canonical style dict build_route_map takes as `style` — lives here
# (rather than in api/) so the map figure and the /api/config colors the
# frontend rebuilds its trend chart from stay in lockstep instead of risking
# two copies drifting apart.
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
        lon_lo = min(all_lons) - lon_pad
        lon_hi = max(all_lons) + lon_pad
        # The map renders in a landscape box (~600px tall, far wider), but a
        # mostly north-south route (e.g. Lisbon→São Paulo) has a lon span far
        # smaller than its lat span — Plotly then fits that tall-narrow
        # window into the box and letterboxes it into a thin central strip.
        # Widen the lon range toward the box's own aspect so the content
        # actually fills the width; the route just sits in more surrounding
        # ocean, which reads as intentional rather than broken.
        min_lon_range = (lat_hi - lat_lo) * 1.6
        if (lon_hi - lon_lo) < min_lon_range:
            mid = (lon_lo + lon_hi) / 2
            lon_lo = max(mid - min_lon_range / 2, -180)
            lon_hi = min(mid + min_lon_range / 2, 180)
        geo_range = dict(
            lataxis=dict(range=[lat_lo, lat_hi]),
            lonaxis=dict(range=[lon_lo, lon_hi]),
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
