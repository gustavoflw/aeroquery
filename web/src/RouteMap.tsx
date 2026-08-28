import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import type * as Plotly from 'plotly.js'
import { formatLocation } from './format'
import type { AirportInfo, MetroArea, SearchResponse } from './types'

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
  const allAirportsTrace = useMemo(
    () => buildAllAirportsTrace(airports, metroAreas),
    [airports, metroAreas],
  )
  const allAirportsCurve = mapFigure.data.length

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
      layout={{ ...mapFigure.layout, autosize: true }}
      style={{ width: '100%', height: '600px' }}
      useResizeHandler
      config={{ displaylogo: false }}
      onClick={handleClick}
    />
  )
}
