import { Fragment } from 'react'
import { formatDurationMinutes, formatPrice } from './format'
import type { FlightResult } from './types'

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

export function ItineraryCard({ flight, currency, currencySymbols }: ItineraryCardProps) {
  const first = flight.legs[0]
  const last = flight.legs[flight.legs.length - 1]
  const totalMinutes = minutesBetween(first.departure, last.arrival)
  const color = stopsColor(flight.stops)

  return (
    <div
      className="itinerary-card"
      style={{ borderColor: color, ['--card-glow' as string]: color }}
    >
      <div className="itinerary-header">
        <span className="itinerary-airlines">
          {flight.airlines.join('/')} — {formatPrice(flight.price, currency, currencySymbols)}
        </span>
        <span className="itinerary-stops" style={{ color }}>
          {stopsLabel(flight.stops)}
        </span>
      </div>
      <table className="itinerary-legs">
        <tbody>
          {flight.legs.map((leg, index) => {
            const nextLeg = flight.legs[index + 1]
            return (
              <Fragment key={`${leg.from_airport}-${leg.departure}`}>
                <tr>
                  <td>
                    <b>{leg.from_airport}</b> {clockTime(leg.departure)}
                  </td>
                  <td className="arrow">→</td>
                  <td>
                    <b>{leg.to_airport}</b> {clockTime(leg.arrival)}
                  </td>
                  <td className="leg-meta">
                    {leg.duration_minutes} min · {leg.plane_type}
                  </td>
                </tr>
                {nextLeg && (
                  <tr className="layover-row">
                    <td colSpan={4}>
                      layover at {leg.to_airport}:{' '}
                      {formatDurationMinutes(minutesBetween(leg.arrival, nextLeg.departure))}
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
          <tr className="total-row">
            <td colSpan={3} />
            <td>Total: {formatDurationMinutes(totalMinutes)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}
