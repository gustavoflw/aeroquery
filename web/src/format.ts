import type { AirportInfo, MetroArea } from './types'

// Mirrors core/format.py's format_price — the symbol table itself comes
// from /api/config (core.format.CURRENCY_SYMBOLS) rather than being
// duplicated here, so it can't drift from the Python source of truth.
export function formatPrice(
  price: number,
  currency: string,
  symbols: Record<string, string>,
): string {
  const symbol = symbols[currency]
  return symbol ? `${symbol}${price}` : `${price} ${currency}`
}

export function formatDurationMinutes(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours}h ${String(minutes).padStart(2, '0')}m`
}

// Mirrors core/airports.py's format_location.
export function formatLocation(
  code: string,
  airports: Record<string, AirportInfo>,
  metroAreas: Record<string, MetroArea>,
): string {
  const metro = metroAreas[code]
  if (metro) return `${code} — ${metro.city}, ${metro.country} · All airports`
  const info = airports[code]
  if (!info) return code
  return `${code} — ${info.city}, ${info.country} · ${info.name}`
}
