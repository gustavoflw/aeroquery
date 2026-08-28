import { useEffect, useRef, useState } from 'react'
import './App.css'
import { AirportPickerPopover } from './AirportPickerPopover'
import { fetchAirports, fetchConfig, fetchSearch } from './api'
import { ItineraryCard } from './ItineraryCard'
import { PriceTrendChart } from './PriceTrendChart'
import { priceTrendWindow } from './trendChartMath'
import { ProgressBar } from './ProgressBar'
import { RouteMap } from './RouteMap'
import { SearchForm } from './SearchForm'
import { streamTrend } from './trendStream'
import { readFormStateFromUrl, writeFormStateToUrl } from './urlParams'
import type {
  AirportsResponse,
  CheapestDirect,
  ConfigResponse,
  FormState,
  SearchParams,
  SearchResponse,
  TrendStat,
} from './types'

function defaultDate(): string {
  const d = new Date()
  d.setDate(d.getDate() + 7)
  return d.toISOString().slice(0, 10)
}

const INITIAL_FORM_STATE: FormState = {
  origin: '',
  destination: '',
  date: defaultDate(),
  maxStopsLabel: 'Any',
  currency: 'EUR',
}

interface AirportPickerState {
  code: string
  x: number
  y: number
}

interface TrendProgress {
  completed: number
  total: number
  etaSeconds: number | null
}

// Phase 3-5 (see .claude/js-migration-plan.md): search form, itinerary
// list, route map (click a route to highlight it, click any airport dot to
// pick a new origin/destination via a popover anchored at the click point),
// and now the price-trend chart, streamed progressively over SSE the same
// way app.py's stream_update/stream_progress fill in Streamlit placeholders
// — the searched date resolves first, then the rest of the window streams
// in behind it. Not linked from the live Streamlit app.
function App() {
  const [airportsData, setAirportsData] = useState<AirportsResponse | null>(null)
  const [config, setConfig] = useState<ConfigResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [formState, setFormState] = useState<FormState>(INITIAL_FORM_STATE)
  const [results, setResults] = useState<SearchResponse | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  const [highlightedIndices, setHighlightedIndices] = useState<Set<number>>(new Set())
  const [airportPicker, setAirportPicker] = useState<AirportPickerState | null>(null)

  const [trendCenterDate, setTrendCenterDate] = useState<string | null>(null)
  const [trendStats, setTrendStats] = useState<TrendStat[]>([])
  const [cheapestDirect, setCheapestDirect] = useState<CheapestDirect | null>(null)
  const [trendProgress, setTrendProgress] = useState<TrendProgress | null>(null)
  const [trendError, setTrendError] = useState<string | null>(null)
  const closeTrendStreamRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    Promise.all([fetchAirports(), fetchConfig()])
      .then(([airports, cfg]) => {
        setAirportsData(airports)
        setConfig(cfg)
        // Mirrors app.py's "a page reload resends the last-set query
        // params, so re-running whenever origin+destination are present
        // replays the same search" — the URL patch is validated against
        // the just-loaded airports/config before being applied.
        const merged: FormState = {
          ...INITIAL_FORM_STATE,
          currency: cfg.default_currency,
          ...readFormStateFromUrl(airports, cfg),
        }
        setFormState(merged)
        if (merged.origin && merged.destination) runSearchWithConfig(merged, cfg)
      })
      .catch((err) => setLoadError(String(err)))
    // Stop listening (not: stop the backend sweep — same tradeoff Streamlit
    // had, where a closed tab didn't stop its thread pool either) if the
    // page itself unmounts mid-stream.
    return () => closeTrendStreamRef.current?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function runSearch(state: FormState) {
    if (!config) return
    runSearchWithConfig(state, config)
  }

  // Split out of runSearch so the initial mount effect can call this with
  // the just-fetched config directly — calling setConfig() then runSearch()
  // in the same tick would still read the old (null) config from the React
  // state closure, since the update hasn't committed yet.
  function runSearchWithConfig(state: FormState, cfg: ConfigResponse) {
    writeFormStateToUrl(state)
    const params: SearchParams = {
      origin: state.origin,
      destination: state.destination,
      date: state.date,
      maxStops: cfg.max_stops_options[state.maxStopsLabel] ?? null,
      currency: state.currency,
    }

    setIsSearching(true)
    setSearchError(null)
    setResults(null)
    setHighlightedIndices(new Set())
    fetchSearch(params)
      .then(setResults)
      .catch((err) => setSearchError(String(err)))
      .finally(() => setIsSearching(false))

    closeTrendStreamRef.current?.()
    setTrendCenterDate(params.date)
    setTrendStats([])
    setCheapestDirect(null)
    setTrendProgress(null)
    setTrendError(null)
    closeTrendStreamRef.current = streamTrend(params, {
      onProgress: (completed, total, etaSeconds) => setTrendProgress({ completed, total, etaSeconds }),
      onTrend: (stats, direct) => {
        setTrendStats(stats)
        setCheapestDirect(direct)
      },
      onDone: () => setTrendProgress(null),
      onError: (message) => {
        setTrendError(message)
        setTrendProgress(null)
      },
    })
  }

  function handleFormStateChange(patch: Partial<FormState>) {
    setFormState((prev) => ({ ...prev, ...patch }))
  }

  function handleToggleHighlight(resultIndex: number) {
    setHighlightedIndices((prev) => {
      const next = new Set(prev)
      if (next.has(resultIndex)) next.delete(resultIndex)
      else next.add(resultIndex)
      return next
    })
  }

  function handleAirportClick(code: string, x: number, y: number) {
    setAirportPicker({ code, x, y })
  }

  function applyAirportPick(field: 'origin' | 'destination') {
    if (!airportPicker) return
    const next = { ...formState, [field]: airportPicker.code }
    setFormState(next)
    setAirportPicker(null)
    // Mirrors app.py's "a page reload resends the last-set query params, so
    // re-running whenever origin+destination are both present replays the
    // search" — picking an airport here immediately searches the new route.
    if (next.origin && next.destination) runSearch(next)
  }

  if (loadError) {
    return (
      <main className="status">
        <p>Couldn't reach the API: {loadError}</p>
        <p>
          Is it running? <code>uv run uvicorn api.main:app --reload --port 8000</code>
        </p>
      </main>
    )
  }

  if (!airportsData || !config) {
    return (
      <main className="status">
        <p>Loading…</p>
      </main>
    )
  }

  return (
    <main>
      <h1>✈️ AeroQuery</h1>
      <SearchForm
        airports={airportsData.airports}
        metroAreas={airportsData.metro_areas}
        config={config}
        formState={formState}
        onFormStateChange={handleFormStateChange}
        onSubmit={() => runSearch(formState)}
        isSearching={isSearching}
      />
      {searchError && <p className="error">Search failed: {searchError}</p>}

      {trendProgress && (
        <ProgressBar
          completed={trendProgress.completed}
          total={trendProgress.total}
          etaSeconds={trendProgress.etaSeconds}
        />
      )}
      {trendError && <p className="error">{trendError}</p>}
      {trendCenterDate && trendStats.length > 0 && (
        <PriceTrendChart
          trend={trendStats}
          centerDate={trendCenterDate}
          currency={formState.currency}
          config={config}
          cheapestDirect={cheapestDirect}
          xRange={priceTrendWindow(trendCenterDate)}
        />
      )}

      {results && (
        <section className="results">
          <p className="results-summary">
            {results.results.length} itinerar{results.results.length === 1 ? 'y' : 'ies'} found for{' '}
            {results.date} · click any airport on the map to pick a new origin or destination
          </p>
          <RouteMap
            mapFigure={results.map_figure}
            routeResultIndices={results.route_result_indices}
            airports={airportsData.airports}
            metroAreas={airportsData.metro_areas}
            highlightedIndices={highlightedIndices}
            onToggleHighlight={handleToggleHighlight}
            onAirportClick={handleAirportClick}
          />
          {results.results.map((flight, index) => (
            <ItineraryCard
              key={index}
              flight={flight}
              currency={results.currency}
              currencySymbols={config.currency_symbols}
            />
          ))}
        </section>
      )}
      {airportPicker && (
        <AirportPickerPopover
          code={airportPicker.code}
          x={airportPicker.x}
          y={airportPicker.y}
          airports={airportsData.airports}
          metroAreas={airportsData.metro_areas}
          onSetOrigin={() => applyAirportPick('origin')}
          onSetDestination={() => applyAirportPick('destination')}
          onDismiss={() => setAirportPicker(null)}
        />
      )}
    </main>
  )
}

export default App
