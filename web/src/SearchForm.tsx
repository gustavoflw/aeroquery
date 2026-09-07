import { DatePicker } from './DatePicker'
import { LocationInput } from './LocationInput'
import type { AirportInfo, ConfigResponse, FormState, MetroArea } from './types'

// Local-time YYYY-MM-DD (en-CA formats exactly that way).
function todayIso(): string {
  return new Date().toLocaleDateString('en-CA')
}

interface SearchFormProps {
  airports: Record<string, AirportInfo>
  metroAreas: Record<string, MetroArea>
  config: ConfigResponse
  formState: FormState
  onFormStateChange: (patch: Partial<FormState>) => void
  onSubmit: () => void
  isSearching: boolean
}

export function SearchForm({
  airports,
  metroAreas,
  config,
  formState,
  onFormStateChange,
  onSubmit,
  isSearching,
}: SearchFormProps) {
  const { origin, destination, date, maxStopsLabel, trendDaysLabel } = formState

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!origin || !destination) return
    onSubmit()
  }

  return (
    <form onSubmit={handleSubmit} className="panel search-form">
      <div className="search-row">
        <LocationInput
          id="origin"
          label="Origin airport or city"
          airports={airports}
          metroAreas={metroAreas}
          value={origin}
          onChange={(code) => onFormStateChange({ origin: code })}
        />
        <LocationInput
          id="destination"
          label="Destination airport or city"
          airports={airports}
          metroAreas={metroAreas}
          value={destination}
          onChange={(code) => onFormStateChange({ destination: code })}
        />
      </div>
      <div className="search-row">
        <label className="field">
          Departure date
          <DatePicker
            id="departure-date"
            value={date}
            min={todayIso()}
            onChange={(iso) => onFormStateChange({ date: iso })}
          />
        </label>
        <label className="field">
          Max stops
          <select
            value={maxStopsLabel}
            onChange={(event) => onFormStateChange({ maxStopsLabel: event.target.value })}
          >
            {Object.keys(config.max_stops_options).map((optionLabel) => (
              <option key={optionLabel} value={optionLabel}>
                {optionLabel}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Price trend
          <select
            value={trendDaysLabel}
            onChange={(event) => onFormStateChange({ trendDaysLabel: event.target.value })}
          >
            {Object.keys(config.trend_days_options).map((optionLabel) => (
              <option key={optionLabel} value={optionLabel}>
                {optionLabel}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button type="submit" disabled={!origin || !destination || isSearching}>
        {isSearching ? 'Searching…' : 'Search'}
      </button>
    </form>
  )
}
