import type * as Plotly from 'plotly.js'
import { formatPrice } from './format'
import type { CheapestDirect, MapStyle, TrendStat } from './types'

function toDateOnly(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function addDays(dateIso: string, days: number): string {
  const d = new Date(`${dateIso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return toDateOnly(d)
}

// Mirrors core.flights.price_trend_window — plain date arithmetic, so it's
// ported directly rather than fetched from the backend. `totalDays` is the
// number of dates the sweep covers (config.price_trend_days; 1 by default,
// meaning start === end). ISO "YYYY-MM-DD" strings sort lexicographically
// the same as chronologically, so string comparison stands in for Python's
// max(today, ...) without needing Date object comparisons at all.
export function priceTrendWindow(centerDateIso: string, totalDays: number): [string, string] {
  const span = Math.max(0, totalDays - 1)
  const today = toDateOnly(new Date())
  const centerShifted = addDays(centerDateIso, -Math.floor(span / 2))
  const start = centerShifted > today ? centerShifted : today
  return [start, addDays(start, span)]
}

// Round 1-2-5-per-decade tick values spanning [lo, hi] for the log y-axis.
// (Was core.charts.nice_log_ticks in Python, dropped when the price-trend
// chart moved entirely client-side.)
export function niceLogTicks(lo: number, hi: number): number[] {
  if (lo <= 0 || hi <= 0 || lo > hi) return []
  const startPow = Math.floor(Math.log10(lo))
  const endPow = Math.ceil(Math.log10(hi))
  const ticks = new Set<number>()
  for (let p = startPow; p <= endPow; p++) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** p
      if (lo * 0.9 <= v && v <= hi * 1.1) ticks.add(v)
    }
  }
  return Array.from(ticks).sort((a, b) => a - b)
}

function notNull<T>(v: T | null): v is T {
  return v !== null
}

// Builds the price-trend chart figure client-side (rather than reusing
// backend-built figure JSON, the way RouteMap does) because /api/trend
// deliberately streams pre-aggregated stats instead of a figure per event —
// see api/main.py's get_trend docstring. This logic used to have a Python
// twin in core.charts.build_price_trend_chart; that was removed once the
// Streamlit UI was retired and this became the only renderer. Kept as
// loosely-typed plain objects rather than fighting Plotly's (quite
// restrictive) generated trace/shape/annotation unions for an exact match;
// Plotly.js accepts this shape at runtime regardless of how strictly TS
// would type it.
export function buildPriceTrendChartFigure(
  trend: TrendStat[],
  centerDate: string,
  currency: string,
  style: MapStyle,
  currencySymbols: Record<string, string>,
  neonBg: string,
  direct: CheapestDirect | null,
  xRange: [string, string] | null,
): { data: Plotly.Data[]; layout: Partial<Plotly.Layout> } {
  const dates = trend.map((r) => r.date)
  const means = trend.map((r) => r.mean)
  const mins = trend.map((r) => r.min)
  const maxes = trend.map((r) => r.max)
  const allPrices = [...means, ...mins, ...maxes].filter(notNull)

  const maxReach = trend.map((r) => (r.mean !== null && r.max !== null ? r.max - r.mean : 0))
  const minReach = trend.map((r) => (r.mean !== null && r.min !== null ? r.mean - r.min : 0))
  const zeros = trend.map(() => 0)

  const avgColor = style.route_colors[0]
  const knownMeans = means.filter(notNull)
  const priceScale = [
    [0.0, style.stop_ok],
    [0.5, style.stop_warn],
    [1.0, style.stop_bad],
  ]
  const markerColors = means.map((m) => m ?? 0)
  const gold = '#ffd700'

  const data: Record<string, unknown>[] = [
    {
      type: 'scatter',
      x: dates,
      y: means,
      mode: 'markers',
      marker: { size: 0, color: style.stop_bad },
      error_y: {
        type: 'data',
        array: maxReach,
        arrayminus: zeros,
        color: style.stop_bad,
        thickness: 1.25,
        width: 2,
      },
      opacity: 0.7,
      name: 'Highest fare',
      customdata: maxes,
      hovertemplate: `Highest: %{customdata:.0f} ${currency}<extra></extra>`,
    },
    {
      type: 'scatter',
      x: dates,
      y: means,
      mode: 'markers',
      marker: { size: 0, color: style.stop_ok },
      error_y: {
        type: 'data',
        array: zeros,
        arrayminus: minReach,
        color: style.stop_ok,
        thickness: 1.25,
        width: 2,
      },
      opacity: 0.7,
      name: 'Lowest fare',
      customdata: mins,
      hovertemplate: `Lowest: %{customdata:.0f} ${currency}<extra></extra>`,
    },
    {
      type: 'scatter',
      x: dates,
      y: means,
      mode: 'lines+markers',
      name: 'Average price',
      line: { color: avgColor, width: 2 },
      marker: {
        size: 9,
        color: markerColors,
        colorscale: priceScale,
        cmin: knownMeans.length ? Math.min(...knownMeans) : 0,
        cmax: knownMeans.length ? Math.max(...knownMeans) : 1,
        line: { width: 1, color: neonBg },
      },
      hovertemplate: `Average: %{y:.0f} ${currency}<extra></extra>`,
    },
  ]

  if (knownMeans.length) {
    const cheapest = trend
      .filter((r) => r.mean !== null)
      .reduce((best, row) => (row.mean! < best.mean! ? row : best))
    const label = `Cheapest average fare: ${formatPrice(Math.round(cheapest.mean!), currency, currencySymbols)}`
    data.push({
      type: 'scatter',
      x: [cheapest.date],
      y: [cheapest.mean],
      mode: 'markers',
      marker: { symbol: 'star', size: 16, color: gold, line: { width: 1, color: neonBg } },
      name: label,
      hovertemplate: `${label}<extra></extra>`,
    })
  }

  const knownMinRows = trend.filter((r) => r.min !== null)
  if (knownMinRows.length) {
    const cheapestFare = knownMinRows.reduce((best, row) => (row.min! < best.min! ? row : best))
    const label = `Cheapest fare: ${formatPrice(Math.round(cheapestFare.min!), currency, currencySymbols)}`
    data.push({
      type: 'scatter',
      x: [cheapestFare.date],
      y: [cheapestFare.min],
      mode: 'markers',
      marker: { symbol: 'diamond', size: 13, color: gold, line: { width: 1, color: neonBg } },
      name: label,
      hovertemplate: `${label}<extra></extra>`,
    })
  }

  if (direct !== null) {
    const label = `Cheapest direct flight: ${formatPrice(direct.price, currency, currencySymbols)}`
    data.push({
      type: 'scatter',
      x: [direct.date],
      y: [direct.price],
      mode: 'markers',
      marker: { symbol: 'hexagram', size: 15, color: gold, line: { width: 1, color: neonBg } },
      name: label,
      hovertemplate: `${label}<extra></extra>`,
    })
  }

  const searchColor = '#00f0ff'
  const shapes = [
    {
      type: 'line',
      xref: 'x',
      yref: 'paper',
      x0: centerDate,
      x1: centerDate,
      y0: 0,
      y1: 1,
      line: { color: 'rgba(0,240,255,0.25)', width: 8 },
      layer: 'below',
    },
    {
      type: 'line',
      xref: 'x',
      yref: 'paper',
      x0: centerDate,
      x1: centerDate,
      y0: 0,
      y1: 1,
      line: { color: searchColor, width: 2 },
    },
  ]
  const annotations = [
    {
      x: centerDate,
      y: 1,
      yref: 'paper',
      yanchor: 'bottom',
      text: '<b>Searched date</b>',
      showarrow: false,
      font: { color: searchColor, size: 12 },
      bgcolor: neonBg,
      bordercolor: searchColor,
      borderwidth: 1,
      borderpad: 4,
    },
  ]

  let logRange: [number, number] | undefined
  let tickvals: number[] | undefined
  let ticktext: string[] | undefined
  if (allPrices.length) {
    const lo = Math.min(...allPrices)
    const hi = Math.max(...allPrices)
    logRange = [Math.log10(lo * 0.85), Math.log10(hi * 1.15)]
    tickvals = niceLogTicks(lo, hi)
    ticktext = tickvals.map((v) => formatPrice(Math.round(v), currency, currencySymbols))
  }

  const layout: Record<string, unknown> = {
    height: 340,
    margin: { l: 10, r: 10, t: 30, b: 10 },
    hovermode: 'x unified',
    legend: {
      orientation: 'h',
      yanchor: 'bottom',
      y: 1.02,
      xanchor: 'left',
      x: 0,
      font: { color: style.legend_font },
      bgcolor: 'rgba(0,0,0,0)',
    },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    shapes,
    annotations,
    xaxis: {
      showgrid: false,
      color: style.legend_font,
      tickfont: { color: style.legend_font },
      range: xRange ?? undefined,
    },
    yaxis: {
      title: { text: `Price (${currency})`, font: { color: style.legend_title_font } },
      type: 'log',
      range: logRange,
      tickmode: 'array',
      tickvals,
      ticktext,
      gridcolor: 'rgba(255,255,255,0.08)',
      color: style.legend_font,
      tickfont: { color: style.legend_font },
    },
  }

  return { data: data as Plotly.Data[], layout: layout as Partial<Plotly.Layout> }
}
