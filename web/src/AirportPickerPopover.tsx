import { useEffect, useRef } from 'react'
import { formatLocation } from './format'
import type { AirportInfo, MetroArea } from './types'

interface AirportPickerPopoverProps {
  code: string
  x: number
  y: number
  airports: Record<string, AirportInfo>
  metroAreas: Record<string, MetroArea>
  onSetOrigin: () => void
  onSetDestination: () => void
  onDismiss: () => void
}

// Unlike Streamlit (which had no way to anchor UI to a Plotly click's pixel
// position, so app.py's render_airport_picker_panel fell back to a fixed
// box below the map), this renders exactly where the map was clicked.
export function AirportPickerPopover({
  code,
  x,
  y,
  airports,
  metroAreas,
  onSetOrigin,
  onSetDestination,
  onDismiss,
}: AirportPickerPopoverProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onDismiss()
    }
    // Skip the click that opened the popover — it fires just before this
    // effect (re)runs on the same event loop turn.
    const id = requestAnimationFrame(() => {
      document.addEventListener('mousedown', handleClickOutside)
    })
    return () => {
      cancelAnimationFrame(id)
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [onDismiss])

  return (
    <div
      ref={ref}
      className="airport-picker-popover"
      style={{ left: x + 12, top: y + 12 }}
    >
      <div className="airport-picker-label">{formatLocation(code, airports, metroAreas)}</div>
      <div className="airport-picker-actions">
        <button type="button" onClick={onSetOrigin}>
          Set as origin
        </button>
        <button type="button" onClick={onSetDestination}>
          Set as destination
        </button>
        <button type="button" className="dismiss" onClick={onDismiss} aria-label="Dismiss">
          ✕
        </button>
      </div>
    </div>
  )
}
