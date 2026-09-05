import { LocationInput } from './LocationInput'
import type { AirportInfo, ConfigResponse, FormState, MetroArea } from './types'

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
  const { origin, destination, date, maxStopsLabel, currency } = formState

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
          <input
            type="date"
            value={date}
            onChange={(event) => onFormStateChange({ date: event.target.value })}
            required
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
          Currency
          <select
            value={currency}
            onChange={(event) => onFormStateChange({ currency: event.target.value })}
          >
            {config.currencies.map((code) => (
              <option key={code} value={code}>
                {code}
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
