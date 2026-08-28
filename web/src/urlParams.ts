import type { AirportsResponse, ConfigResponse, FormState } from './types'

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Reads origin/destination/date/max_stops/currency from the URL's query
 * string, validating each against known airports/metro codes and the
 * loaded config — mirrors app.py's handling of st.query_params (an
 * unrecognized value is silently dropped rather than erroring, same as
 * Streamlit's origin_index/default_max_stops/default_currency fallbacks).
 */
export function readFormStateFromUrl(
  airportsData: AirportsResponse,
  config: ConfigResponse,
): Partial<FormState> {
  const params = new URLSearchParams(window.location.search)
  const patch: Partial<FormState> = {}

  const isKnownLocation = (code: string) =>
    code in airportsData.airports || code in airportsData.metro_areas

  const origin = params.get('origin')
  if (origin && isKnownLocation(origin)) patch.origin = origin

  const destination = params.get('destination')
  if (destination && isKnownLocation(destination)) patch.destination = destination

  const date = params.get('date')
  if (date && DATE_RE.test(date)) patch.date = date

  const maxStops = params.get('max_stops')
  if (maxStops && maxStops in config.max_stops_options) patch.maxStopsLabel = maxStops

  const currency = params.get('currency')
  if (currency && config.currencies.includes(currency)) patch.currency = currency

  return patch
}

/**
 * Mirrors app.py setting st.query_params right when origin/destination are
 * both known-good, before the fetch even starts — via replaceState (not
 * pushState) since Streamlit's own query-param assignment doesn't add
 * browser history entries either; a reload replays the last search, same
 * as the "reload resends query params" behavior in the original.
 */
export function writeFormStateToUrl(state: FormState): void {
  const params = new URLSearchParams({
    origin: state.origin,
    destination: state.destination,
    date: state.date,
    max_stops: state.maxStopsLabel,
    currency: state.currency,
  })
  window.history.replaceState(null, '', `?${params.toString()}`)
}
