import { formatDurationMinutes, formatPrice } from './format'
import type { FlightLeg, FlightResult } from './types'

interface ItineraryCardProps {
  flight: FlightResult
  currency: string
  currencySymbols: Record<string, string>
}

function stopsLabel(stops: number): string {
  return stops === 0 ? 'Direct' : `${stops} stop${stops === 1 ? '' : 's'}`
}

function stopsColor(stops: number): string {
  if (stops === 0) return '#1a7f37'
  if (stops === 1) return '#9a6700'
  return '#cf222e'
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

type ScheduleRow =
  | { kind: 'leg'; leg: FlightLeg }
  | { kind: 'layover'; at: string; minutes: number }
  | { kind: 'total'; minutes: number }

// One itinerary = one <tbody> in the shared table in App.tsx. The Price and
// Company cells rowspan the whole itinerary; the Schedule column carries one
// row per leg, a layover row between consecutive legs, and a closing total
// row.
export function ItineraryCard({ flight, currency, currencySymbols }: ItineraryCardProps) {
  const first = flight.legs[0]
  const last = flight.legs[flight.legs.length - 1]
  const color = stopsColor(flight.stops)

  const rows: ScheduleRow[] = []
  flight.legs.forEach((leg, i) => {
    rows.push({ kind: 'leg', leg })
    const next = flight.legs[i + 1]
    if (next) {
      rows.push({ kind: 'layover', at: leg.to_airport, minutes: minutesBetween(leg.arrival, next.departure) })
    }
  })
  rows.push({ kind: 'total', minutes: minutesBetween(first.departure, last.arrival) })

  return (
    <tbody className="itinerary" style={{ ['--card-glow' as string]: color }}>
      {rows.map((row, i) => (
        <tr key={i} className={`sched-${row.kind}`}>
          {i === 0 && (
            <>
              <td className="col-price" rowSpan={rows.length}>
                <span className="price">{formatPrice(flight.price, currency, currencySymbols)}</span>
                <span className="stops" style={{ color }}>
                  {stopsLabel(flight.stops)}
                </span>
              </td>
              <td className="col-company" rowSpan={rows.length}>
                {flight.airlines.join(' / ')}
              </td>
            </>
          )}
          <td className="col-schedule">
            {row.kind === 'leg' && (
              <>
                <span className="leg-line">
                  <b>{row.leg.from_airport}</b> {clockTime(row.leg.departure)}
                  <span className="arrow"> → </span>
                  <b>{row.leg.to_airport}</b> {clockTime(row.leg.arrival)}
                </span>
                <span className="leg-meta">
                  {row.leg.duration_minutes} min · {row.leg.plane_type}
                </span>
              </>
            )}
            {row.kind === 'layover' && (
              <span className="layover">
                layover at {row.at} · {formatDurationMinutes(row.minutes)}
              </span>
            )}
            {row.kind === 'total' && (
              <span className="total">
                <span className="total-label">Total</span> {formatDurationMinutes(row.minutes)}
              </span>
            )}
          </td>
        </tr>
      ))}
    </tbody>
  )
}
