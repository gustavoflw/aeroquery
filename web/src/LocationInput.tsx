import { useEffect, useMemo, useRef, useState } from 'react'
import { formatLocation } from './format'
import type { AirportInfo, MetroArea } from './types'

interface LocationItem {
  code: string
  label: string
  searchText: string
}

interface LocationInputProps {
  id: string
  label: string
  airports: Record<string, AirportInfo>
  metroAreas: Record<string, MetroArea>
  value: string
  onChange: (code: string) => void
}

const MAX_SUGGESTIONS = 50

function buildItems(
  airports: Record<string, AirportInfo>,
  metroAreas: Record<string, MetroArea>,
): LocationItem[] {
  const items: LocationItem[] = []
  for (const [code, info] of Object.entries(airports)) {
    items.push({
      code,
      label: formatLocation(code, airports, metroAreas),
      searchText: `${code} ${info.city ?? ''} ${info.country ?? ''} ${info.name ?? ''}`.toLowerCase(),
    })
  }
  for (const [code, metro] of Object.entries(metroAreas)) {
    items.push({
      code,
      label: formatLocation(code, airports, metroAreas),
      searchText: `${code} ${metro.city} ${metro.country}`.toLowerCase(),
    })
  }
  return items
}

// Ranks code-prefix matches first, then any-word-prefix matches, then bare
// substring matches — plain "includes" alone would bury e.g. "CDG" behind
// unrelated airports whose name happens to contain the query mid-word.
function rankMatches(items: LocationItem[], query: string): LocationItem[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const scored: { item: LocationItem; score: number }[] = []
  for (const item of items) {
    if (item.code.toLowerCase().startsWith(q)) {
      scored.push({ item, score: 0 })
    } else if (item.searchText.split(' ').some((word) => word.startsWith(q))) {
      scored.push({ item, score: 1 })
    } else if (item.searchText.includes(q)) {
      scored.push({ item, score: 2 })
    }
  }
  scored.sort((a, b) => a.score - b.score)
  return scored.slice(0, MAX_SUGGESTIONS).map((s) => s.item)
}

export function LocationInput({
  id,
  label,
  airports,
  metroAreas,
  value,
  onChange,
}: LocationInputProps) {
  const items = useMemo(() => buildItems(airports, metroAreas), [airports, metroAreas])
  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const selectedLabel = value ? formatLocation(value, airports, metroAreas) : ''
  const matches = isOpen ? rankMatches(items, query) : []

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function select(code: string) {
    onChange(code)
    setQuery('')
    setIsOpen(false)
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen || matches.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlighted((h) => Math.min(h + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlighted((h) => Math.max(h - 1, 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      select(matches[highlighted].code)
    } else if (event.key === 'Escape') {
      setIsOpen(false)
      setQuery('')
    }
  }

  return (
    <div className="location-input" ref={containerRef}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        autoComplete="off"
        placeholder="Search by code, city, or airport name"
        value={isOpen ? query : selectedLabel}
        onFocus={() => {
          setIsOpen(true)
          setQuery('')
        }}
        onChange={(event) => {
          setQuery(event.target.value)
          setHighlighted(0)
        }}
        onKeyDown={handleKeyDown}
      />
      {isOpen && matches.length > 0 && (
        <ul className="location-suggestions">
          {matches.map((item, index) => (
            <li
              key={item.code}
              className={index === highlighted ? 'highlighted' : undefined}
              onMouseDown={(event) => {
                // Prevent the input's blur (which would close the list)
                // from firing before this click is registered.
                event.preventDefault()
                select(item.code)
              }}
              onMouseEnter={() => setHighlighted(index)}
            >
              {item.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
