import { useEffect, useMemo, useRef, useState } from 'react'
import Plot from 'react-plotly.js'
import type * as Plotly from 'plotly.js'
import { formatLocation } from './format'
import type { AirportInfo, MetroArea, SearchResponse } from './types'

interface RouteMapProps {
  mapFigure: SearchResponse['map_figure']
  routeResultIndices: number[]
  // Neon colour per result index (from itineraryColor) — overrides the
  // backend figure's palette so a route matches its list card.
  resultColors: string[]
  airports: Record<string, AirportInfo>
  metroAreas: Record<string, MetroArea>
  highlightedIndices: Set<number>
  onToggleHighlight: (resultIndex: number) => void
  onAirportClick: (code: string, clientX: number, clientY: number) => void
}

// Ordering is only load-bearing within this component (built here, read
// back here on click) — unlike the Python version, nothing outside this
// file needs to agree on it.
function allAirportCodes(airports: Record<string, AirportInfo>): string[] {
  return Object.keys(airports).sort()
}

function buildAllAirportsTrace(
  airports: Record<string, AirportInfo>,
  metroAreas: Record<string, MetroArea>,
): Plotly.Data {
  const codes = allAirportCodes(airports)
  return {
    type: 'scattergeo',
    lon: codes.map((c) => airports[c].lon),
    lat: codes.map((c) => airports[c].lat),
    mode: 'markers',
    marker: { size: 4, color: '#ffffff', opacity: 0.3 },
    hovertext: codes.map((c) => formatLocation(c, airports, metroAreas)),
    hoverinfo: 'text',
    name: 'All airports',
    showlegend: false,
  }
}

// Mirrors build_route_map's per-route halo/real-trace styling formulas
// (core/charts.py) so a click can restyle instantly, client-side, instead
// of asking the backend to rebuild the figure the way Streamlit had to.
function applyHighlighting(
  baseData: Plotly.Data[],
  routeResultIndices: number[],
  resultColors: string[],
  highlightedIndices: Set<number>,
): Plotly.Data[] {
  const n = routeResultIndices.length
  const anyHighlighted = highlightedIndices.size > 0

  return baseData.map((trace, curveNumber) => {
    let routeSlot = -1
    let isHalo = false
    if (curveNumber < n) {
      routeSlot = curveNumber
      isHalo = true
    } else if (curveNumber < 2 * n) {
      routeSlot = curveNumber - n
      isHalo = false
    } else {
      return trace
    }

    const resultIndex = routeResultIndices[routeSlot]
    const isSelected = highlightedIndices.has(resultIndex)
    const isDimmed = anyHighlighted && !isSelected
    // Traces are heterogeneous JSON from the backend, not a value built
    // against plotly.js's (quite restrictive) generated trace unions — a
    // small local shape for just the fields mutated here is more robust
    // than fighting that union for an exact match. `color` is forced to the
    // itinerary's shared neon colour, replacing the backend palette.
    const line = { ...(trace as { line?: { width?: number; color?: string } }).line }
    line.color = resultColors[resultIndex] ?? line.color

    if (isHalo) {
      line.width = isSelected ? 14 : 8
      return {
        ...trace,
        line,
        opacity: (isSelected ? 0.4 : 0.14) * (isDimmed ? 0.3 : 1.0),
      }
    }
    line.width = isSelected ? 4 : 2
    return { ...trace, line, opacity: isDimmed ? 0.2 : 1.0 }
  })
}

export function RouteMap({
  mapFigure,
  routeResultIndices,
  resultColors,
  airports,
  metroAreas,
  highlightedIndices,
  onToggleHighlight,
  onAirportClick,
}: RouteMapProps) {
  const allAirportsTrace = useMemo(
    () => buildAllAirportsTrace(airports, metroAreas),
    [airports, metroAreas],
  )
  const allAirportsCurve = mapFigure.data.length

  // react-plotly.js's useResizeHandler only listens for *window* resize, so
  // in a flex layout the plot keeps whatever width it measured on mount and
  // leaves blank space when its column is resized. Observe the wrapper and
  // pass the size to Plotly explicitly instead.
  const wrapRef = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState<{ w: number; h: number } | null>(null)
  useEffect(() => {
    const el = wrapRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setBox({ w: Math.round(width), h: Math.round(height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const layout = useMemo((): Partial<Plotly.Layout> => {
    const base: Record<string, unknown> = { ...mapFigure.layout }
    if (!box) return { ...base, autosize: true }
    base.width = box.w
    base.height = box.h
    base.autosize = false

    // The backend pins both lat and lon ranges, so Plotly fits the tighter
    // one and letterboxes the other. When the frame is wider than the route,
    // widen the longitude range to match so the map fills the frame's width
    // (the route just sits in more surrounding ocean). We only ever widen
    // longitude — never shrink the route to fill vertical space; a bit of
    // top/bottom letterbox is fine (the legend lives there anyway). `k` is
    // the rough horizontal squash of "natural earth" at the region's mid
    // latitude.
    const geo = { ...((base.geo as Record<string, unknown>) ?? {}) }
    const lonAxis = geo.lonaxis as { range?: [number, number] } | undefined
    const latR = (geo.lataxis as { range?: [number, number] } | undefined)?.range
    const lonR = lonAxis?.range
    if (latR && lonR) {
      const latW = latR[1] - latR[0]
      const lonW = lonR[1] - lonR[0]
      const lonMid = (lonR[0] + lonR[1]) / 2
      const latMid = (latR[0] + latR[1]) / 2
      const k = Math.min(1, Math.max(0.35, Math.cos((latMid * Math.PI) / 180)))
      const boxAspect = box.w / box.h
      const regionAspect = (lonW * k) / latW
      if (boxAspect > regionAspect) {
        const target = Math.min(350, (boxAspect * latW) / k)
        geo.lonaxis = { ...lonAxis, range: [lonMid - target / 2, lonMid + target / 2] }
        base.geo = geo
      }
    }
    return base as Partial<Plotly.Layout>
  }, [mapFigure.layout, box])

  const data = useMemo(
    () => [
      ...applyHighlighting(mapFigure.data, routeResultIndices, resultColors, highlightedIndices),
      allAirportsTrace,
    ],
    [mapFigure.data, routeResultIndices, resultColors, highlightedIndices, allAirportsTrace],
  )

  function handleClick(event: Readonly<Plotly.PlotMouseEvent>) {
    const point = event.points[0]
    if (!point) return
    const n = routeResultIndices.length

    if (point.curveNumber >= n && point.curveNumber < 2 * n) {
      onToggleHighlight(routeResultIndices[point.curveNumber - n])
      return
    }
    if (point.curveNumber === allAirportsCurve) {
      const code = allAirportCodes(airports)[point.pointIndex]
      onAirportClick(code, event.event.clientX, event.event.clientY)
    }
  }

  return (
    <div className="route-map" ref={wrapRef}>
      <Plot
        data={data}
        layout={layout}
        style={{ width: '100%', height: '100%' }}
        config={{ displaylogo: false }}
        onClick={handleClick}
      />
    </div>
  )
}
