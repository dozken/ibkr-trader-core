// Single source for recharts colors. Reads the live CSS vars set by the active
// theme (see index.css), so charts follow the knob instead of hardcoding hex.
// Call inside a component that also reads useTheme() so it re-runs on switch.

function v(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return raw ? `rgb(${raw})` : fallback // vars hold "r g b" triplets
}

export interface ChartTheme {
  grid: string
  axis: string
  primary: string
  success: string
  danger: string
  accent: string
  surface: string
  text: string
  series: string[]
}

export function chartTheme(): ChartTheme {
  const primary = v('--color-primary', '#2dd4bf')
  const success = v('--color-success', '#22c55e')
  const accent = v('--color-accent', '#a78bfa')
  const danger = v('--color-danger', '#ef4444')
  return {
    grid: v('--color-divider', '#334155'),
    axis: v('--color-muted', '#94a3b8'),
    primary,
    success,
    danger,
    accent,
    surface: v('--color-surface', '#1e2530'),
    text: v('--color-light', '#e2e8f0'),
    series: [primary, accent, success, danger],
  }
}
