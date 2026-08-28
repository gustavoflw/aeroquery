import type * as Plotly from 'plotly.js'

export interface AirportInfo {
  city: string | null
  country: string | null
  name: string | null
  lat: number | null
  lon: number | null
}

export interface MetroArea {
  city: string
  country: string
  members: string[]
}

export interface AirportsResponse {
  airports: Record<string, AirportInfo>
  metro_areas: Record<string, MetroArea>
}

// Matches core/charts.py's MAP_STYLE — the fields build_price_trend_chart
// (ported client-side, see trendChartMath.ts) and build_route_map both
// read from a style dict of this shape.
export interface MapStyle {
  route_colors: string[]
  landcolor: string
  countrycolor: string
  airport_dot: string
  airport_text: string
  legend_font: string
  legend_title_font: string
  panel_bg: string
  panel_border: string
  stop_ok: string
  stop_warn: string
  stop_bad: string
  layover_accent: string
}

export interface ConfigResponse {
  currencies: string[]
  default_currency: string
  currency_symbols: Record<string, string>
  max_stops_options: Record<string, number | null>
  map_style: MapStyle
  neon_bg: string
}

export interface FlightLeg {
  from_airport: string
  to_airport: string
  departure: string // ISO datetime, naive (airport-local wall clock, no offset)
  arrival: string
  duration_minutes: number
  plane_type: string
}

export interface FlightResult {
  price: number
  airlines: string[]
  stops: number
  legs: FlightLeg[]
}

export interface SearchResponse {
  date: string
  currency: string
  results: FlightResult[]
  skipped_for_map: number
  map_figure: { data: Plotly.Data[]; layout: Partial<Plotly.Layout> }
  // route_result_indices[i] is the index into `results` that map_figure's
  // route i (halo trace i / real trace n+i, n = route_result_indices.length)
  // corresponds to.
  route_result_indices: number[]
}

export interface SearchParams {
  origin: string
  destination: string
  date: string
  maxStops: number | null
  currency: string
}

// The search form's fields, lifted up to App so the airport-picker popover
// (RouteMap -> App) can set origin/destination and trigger a new search,
// mirroring how Streamlit's version set st.query_params and reran.
export interface FormState {
  origin: string
  destination: string
  date: string
  maxStopsLabel: string
  currency: string
}

// Mirrors core.flights.price_trend_stats's per-day row shape.
export interface TrendStat {
  date: string // ISO date
  mean: number | null
  min: number | null
  max: number | null
  count: number
}

// Mirrors core.flights.cheapest_direct_flight's return shape.
export interface CheapestDirect {
  date: string
  price: number
}

export interface TrendProgressEvent {
  type: 'progress'
  completed: number
  total: number
  eta_seconds: number | null
}

export interface TrendDataEvent {
  type: 'trend'
  stats: TrendStat[]
  cheapest_direct: CheapestDirect | null
}

export interface TrendDoneEvent {
  type: 'done'
}

export type TrendEvent = TrendProgressEvent | TrendDataEvent | TrendDoneEvent
