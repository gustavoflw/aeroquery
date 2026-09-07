import { useEffect, useRef, useState } from 'react'

interface DatePickerProps {
  id: string
  value: string // ISO YYYY-MM-DD
  onChange: (iso: string) => void
  min?: string // ISO — days before this are disabled
}

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

function toIso(y: number, m: number, d: number): string {
  return `${y}-${pad(m + 1)}-${pad(d)}`
}

function parseIso(iso: string): { y: number; m: number; d: number } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!match) return null
  return { y: +match[1], m: +match[2] - 1, d: +match[3] }
}

function formatDisplay(iso: string): string {
  const p = parseIso(iso)
  return p ? `${MONTHS[p.m]} ${p.d}, ${p.y}` : 'Select a date'
}

// A themed calendar the field opens as a dropdown — a custom control (like
// LocationInput) rather than the browser's native <input type=date>, so it
// carries the app's neon styling.
export function DatePicker({ id, value, onChange, min }: DatePickerProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const now = new Date()
  const selected = parseIso(value) ?? { y: now.getFullYear(), m: now.getMonth(), d: now.getDate() }
  const [view, setView] = useState({ y: selected.y, m: selected.m })

  // Jump the calendar back to the selected month when the popover opens.
  function toggle() {
    const next = !open
    setOpen(next)
    if (next) {
      const p = parseIso(value)
      if (p) setView({ y: p.y, m: p.m })
    }
  }

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const firstWeekday = (new Date(view.y, view.m, 1).getDay() + 6) % 7 // Monday-first
  const daysInMonth = new Date(view.y, view.m + 1, 0).getDate()
  const cells: (number | null)[] = [
    ...Array<null>(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ]

  const isDisabled = (day: number) => (min ? toIso(view.y, view.m, day) < min : false)

  function shiftMonth(delta: number) {
    setView((v) => {
      const raw = v.m + delta
      return { y: v.y + Math.floor(raw / 12), m: ((raw % 12) + 12) % 12 }
    })
  }

  return (
    <div className="date-picker" ref={containerRef}>
      <button
        type="button"
        id={id}
        className="date-picker-field"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={toggle}
      >
        <span>{formatDisplay(value)}</span>
        <span className="date-picker-caret" aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div className="date-picker-popover" role="dialog" aria-label="Choose departure date">
          <div className="date-picker-nav">
            <button type="button" aria-label="Previous month" onClick={() => shiftMonth(-1)}>
              ‹
            </button>
            <span className="date-picker-title">
              {MONTHS[view.m]} {view.y}
            </span>
            <button type="button" aria-label="Next month" onClick={() => shiftMonth(1)}>
              ›
            </button>
          </div>
          <div className="date-picker-grid">
            {WEEKDAYS.map((w) => (
              <span key={w} className="date-picker-weekday">
                {w}
              </span>
            ))}
            {cells.map((day, i) =>
              day === null ? (
                <span key={`pad-${i}`} />
              ) : (
                <button
                  key={day}
                  type="button"
                  className={
                    'date-picker-day' +
                    (toIso(view.y, view.m, day) === value ? ' selected' : '')
                  }
                  disabled={isDisabled(day)}
                  onClick={() => {
                    onChange(toIso(view.y, view.m, day))
                    setOpen(false)
                  }}
                >
                  {day}
                </button>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  )
}
