import type { AirportsResponse, ConfigResponse, SearchParams, SearchResponse } from './types'

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export function fetchAirports(): Promise<AirportsResponse> {
  return getJson('/api/airports')
}

export function fetchConfig(): Promise<ConfigResponse> {
  return getJson('/api/config')
}

export function fetchSearch(params: SearchParams): Promise<SearchResponse> {
  const query = new URLSearchParams({
    origin: params.origin,
    destination: params.destination,
    date: params.date,
    currency: params.currency,
  })
  if (params.maxStops !== null) query.set('max_stops', String(params.maxStops))
  return getJson(`/api/search?${query.toString()}`)
}
