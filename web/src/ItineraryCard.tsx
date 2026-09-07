import { Fragment } from 'react'
import { formatDurationMinutes, formatPrice } from './format'
import { companyColor } from './itineraryColor'
import type { FlightResult } from './types'

interface ItineraryCardProps {
  flight: FlightResult
  color: string
  currency: string
  currencySymbols: Record<string, string>
  repricing?: boolean
}

function stopsLabel(stops: number): string {
  return stops === 0 ? 'Direct' : `${stops} stop${stops === 1 ? '' : 's'}`
}

// Departure/arrival are naive ISO datetimes (airport-local wall clock, no
// offset) — new Date() parses those as local time and getTime() diffs them
// consistently, so this reproduces core/format.py's route_layovers /
// route_total_duration without needing timezone data at all.
function minutesBetween(fromIso: string, toIso: string): number {
  return Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60000)
}

function clockTime(iso: string): string {
  return new Date(iso).toTimeString().slice(0, 5)
}

// One itinerary = one bordered card laid out on a shared Price / Company /
// Schedule grid (the header lives in App.tsx). The Company and Schedule
// columns run one row per leg, aligned, with a rule between legs; the
// backend has no per-leg carrier, so when there are fewer airlines than
// legs (one carrier flying several segments) the last airline carries
// forward. `color` is the company-derived neon colour shared with this
// itinerary's route on the map — it paints the border and glow.
export function ItineraryCard({
  flight,
  color,
  currency,
  currencySymbols,
  repricing = false,
}: ItineraryCardProps) {
  const first = flight.legs[0]
  const last = flight.legs[flight.legs.length - 1]
  const totalMinutes = minutesBetween(first.departure, last.arrival)

  const companyForLeg = (i: number) =>
    flight.airlines[Math.min(i, flight.airlines.length - 1)] ?? '—'

  return (
    <div className="itinerary" style={{ ['--itin-color' as string]: color }}>
      <div className="col-price">
        {repricing ? (
          <span className="price-loading" aria-label="Updating price" />
        ) : (
          <span className="price">{formatPrice(flight.price, currency, currencySymbols)}</span>
        )}
        <span className="stops">{stopsLabel(flight.stops)}</span>
      </div>

      <div className="details">
        {flight.legs.map((leg, i) => {
          const next = flight.legs[i + 1]
          return (
            <Fragment key={i}>
              {i > 0 && <div className="leg-sep" />}
              <div className="leg-company" style={{ color: companyColor(companyForLeg(i)) }}>
                {companyForLeg(i)}
              </div>
              <div className="leg-sched">
                <span className="leg-line">
                  <b>{leg.from_airport}</b> {clockTime(leg.departure)}
                  <span className="arrow"> → </span>
                  <b>{leg.to_airport}</b> {clockTime(leg.arrival)}
                </span>
                <span className="leg-meta">
                  {leg.duration_minutes} min · {leg.plane_type}
                </span>
                {next && (
                  <span className="layover">
                    layover at {leg.to_airport} ·{' '}
                    {formatDurationMinutes(minutesBetween(leg.arrival, next.departure))}
                  </span>
                )}
              </div>
            </Fragment>
          )
        })}

        <div className="total">
          <span className="total-label">Total</span>{' '}
          <span className="total-time">{formatDurationMinutes(totalMinutes)}</span>
        </div>
      </div>
    </div>
  )
}
