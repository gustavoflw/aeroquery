import { useEffect, useMemo, useState } from 'react'
import Plot from 'react-plotly.js'
import type * as Plotly from 'plotly.js'
import { formatLocation } from './format'
import type { AirportInfo, MetroArea, SearchResponse } from './types'

function readViewport(): number {
  return typeof window === 'undefined' ? 1280 : window.innerWidth
}

function useViewportWidth(): number {
  const [width, setWidth] = useState(readViewport)
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return width
}

// Width of the map's own box, matching App.css: `main` is
// `max-width: 2200px` with `padding: 0 clamp(1rem, 3vw, 3rem)`, and the map
// spans it fully.
function mapBoxWidth(viewportWidth: number): number {
  const pad = Math.min(48, Math.max(16, viewportWidth * 0.03))
  return Math.min(2200, viewportWidth) - 2 * pad
}

// Below 40rem the itinerary list drops to a plain stack (App.css media
// query) and the map gets its full width; above it the list floats over the
// map's left edge, so shift the geo subplot right to clear it. The shift
// tracks the panel's actual fraction of the box (.itinerary-list is 440px +
// a ~24px gutter), capped so the map never loses more than 40%.
function geoDomainStart(viewportWidth: number): number {
  if (viewportWidth < 640) return 0
  return Math.min(0.4, 464 / mapBoxWidth(viewportWidth))
}

interface RouteMapProps {
  mapFigure: SearchResponse['map_figure']
  routeResultIndices: number[]
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
    marker: { size: 4, color: '#00f0ff', opacity: 0.35 },
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
    // small local shape for just the two fields mutated here is more
    // robust than fighting that union for an exact match.
    const line = { ...(trace as { line?: { width?: number } }).line }

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
  airports,
  metroAreas,
  highlightedIndices,
  onToggleHighlight,
  onAirportClick,
}: RouteMapProps) {
  const viewportWidth = useViewportWidth()
  const allAirportsTrace = useMemo(
    () => buildAllAirportsTrace(airports, metroAreas),
    [airports, metroAreas],
  )
  const allAirportsCurve = mapFigure.data.length

  // Pull the geo subplot into the portion of the box the floating itinerary
  // list doesn't cover, so the drawn map isn't half-hidden behind the panel
  // and uses what would otherwise be dead letterbox margin.
  const layout = useMemo((): Partial<Plotly.Layout> => {
    const base = { ...mapFigure.layout, autosize: true }
    const domainStart = geoDomainStart(viewportWidth)
    if (domainStart === 0) return base
    const geo = (base as { geo?: Record<string, unknown> }).geo ?? {}
    return { ...base, geo: { ...geo, domain: { x: [domainStart, 1], y: [0, 1] } } }
  }, [mapFigure.layout, viewportWidth])

  const data = useMemo(
    () => [
      ...applyHighlighting(mapFigure.data, routeResultIndices, highlightedIndices),
      allAirportsTrace,
    ],
    [mapFigure.data, routeResultIndices, highlightedIndices, allAirportsTrace],
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
    <Plot
      data={data}
      layout={layout}
      style={{ width: '100%', height: '600px' }}
      useResizeHandler
      config={{ displaylogo: false }}
      onClick={handleClick}
    />
  )
}
