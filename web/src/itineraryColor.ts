// A deterministic neon colour per airline, derived only from its name
// (upper-cased) so a company looks the same everywhere — the list border and
// its route on the map. An itinerary flown by more than one carrier blends
// its companies' colours.

// FNV-1a over the char codes — small, fast, and stable across runs.
function hashString(s: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

// Saturation is pinned to the max so every colour is equally "neon" and any
// blend of them stays vivid; hue is the main per-company signal, with a
// small lightness jitter (a second, rotated hash) so two companies that land
// on nearby hues still read apart.
const NEON_SAT = 1

function companyHash(name: string): number {
  return hashString(name.trim().toUpperCase())
}

function companyHue(name: string): number {
  return companyHash(name) % 360
}

function companyLight(name: string): number {
  return 0.6 + ((companyHash(name) >>> 9) % 12) / 100 // 0.60 – 0.71
}

// The single company's own neon colour — used for its name in the list and,
// for a one-carrier itinerary, effectively the same as itineraryColor().
export function companyColor(airline: string): string {
  const name = airline.trim().toUpperCase() || '—'
  return hslToHex(companyHue(name), NEON_SAT, companyLight(name))
}

// Circular mean of the hues (average of unit vectors on the colour wheel),
// so a two-airline itinerary lands on a hue genuinely between its carriers
// rather than an arbitrary RGB midpoint. When the carriers sit near-opposite
// on the wheel the mean is undefined (vector ~0) — fall back to the first.
function mergeHues(hues: number[]): number {
  let x = 0
  let y = 0
  for (const hue of hues) {
    const rad = (hue * Math.PI) / 180
    x += Math.cos(rad)
    y += Math.sin(rad)
  }
  if (Math.hypot(x, y) < 1e-6) return hues[0]
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
}

function hslToHex(h: number, s: number, l: number): string {
  const c = (1 - Math.abs(2 * l - 1)) * s
  const hp = (((h % 360) + 360) % 360) / 60
  const x = c * (1 - Math.abs((hp % 2) - 1))
  const [r1, g1, b1] =
    hp < 1
      ? [c, x, 0]
      : hp < 2
        ? [x, c, 0]
        : hp < 3
          ? [0, c, x]
          : hp < 4
            ? [0, x, c]
            : hp < 5
              ? [x, 0, c]
              : [c, 0, x]
  const m = l - c / 2
  const hex = (v: number) =>
    Math.round((v + m) * 255)
      .toString(16)
      .padStart(2, '0')
  return `#${hex(r1)}${hex(g1)}${hex(b1)}`
}

export function itineraryColor(airlines: string[]): string {
  const names = [...new Set((airlines.length ? airlines : ['—']).map((n) => n.trim().toUpperCase()))]
  const hue = mergeHues(names.map(companyHue))
  const light = names.reduce((sum, n) => sum + companyLight(n), 0) / names.length
  return hslToHex(hue, NEON_SAT, light)
}
