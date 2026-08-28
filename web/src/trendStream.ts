import type { CheapestDirect, SearchParams, TrendEvent, TrendStat } from './types'

/**
 * Opens /api/trend as an SSE stream. Returns a close() function — call it
 * on unmount/new search to stop listening (the backend keeps running its
 * sweep either way, same as a browser tab closing on Streamlit never
 * stopped the thread pool there either).
 *
 * The stream ends with an explicit {"type": "done"} event (see
 * api/main.py's get_trend) — plain EventSource treats a closed connection
 * as "reconnect", so onDone calls source.close() synchronously to pre-empt
 * that before it can fire off a second, redundant 180-day sweep.
 */
export function streamTrend(
  params: SearchParams,
  handlers: {
    onProgress: (completed: number, total: number, etaSeconds: number | null) => void
    onTrend: (stats: TrendStat[], cheapestDirect: CheapestDirect | null) => void
    onDone: () => void
    onError: (message: string) => void
  },
): () => void {
  const query = new URLSearchParams({
    origin: params.origin,
    destination: params.destination,
    date: params.date,
    currency: params.currency,
  })
  if (params.maxStops !== null) query.set('max_stops', String(params.maxStops))

  const source = new EventSource(`/api/trend?${query.toString()}`)

  source.onmessage = (event) => {
    const payload = JSON.parse(event.data) as TrendEvent
    if (payload.type === 'progress') {
      handlers.onProgress(payload.completed, payload.total, payload.eta_seconds)
    } else if (payload.type === 'trend') {
      handlers.onTrend(payload.stats, payload.cheapest_direct)
    } else if (payload.type === 'done') {
      source.close()
      handlers.onDone()
    }
  }

  source.onerror = () => {
    // A genuine mid-stream failure looks identical to this from the
    // client's perspective (EventSource gives no status/body on error) —
    // close rather than let the browser auto-reconnect and restart the
    // whole sweep.
    source.close()
    handlers.onError('Connection to /api/trend was lost')
  }

  return () => source.close()
}
