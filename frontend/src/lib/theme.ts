// ─── Theme knob ──────────────────────────────────────────────────────────
// Single source of truth for the app's visual skin. Switch the whole look
// from ONE place: change DEFAULT_THEME, or pick a theme in the UI.
//
// A theme only adds a `data-theme="<id>"` attribute on <html>. All the actual
// styling lives in CSS scoped under `[data-theme="<id>"]` (see index.css).
// Components never reference a theme — they read `brand-*` CSS vars + the
// shared `.card` / `.t-*` classes, so adding a theme touches zero components.
//
// Light/dark is orthogonal: it stays on the `.dark` class. A theme may
// override tokens for both modes via `[data-theme=x]` and `[data-theme=x].dark`.

// A theme carries BOTH a CSS skin (data-theme attr → index.css) and a layout
// preset. `layout` is the only thing components branch on; everything visual
// stays in CSS. Add a theme = one entry here + one scoped CSS block.
type LayoutId = 'topnav' | 'sidebar'

export interface Theme {
  id: string
  label: string
  layout: LayoutId
}

// AEGOV (UAE Federal Design System) is the single, canonical theme.
// Classic + Mihrab were deprecated/removed. The theme infra is kept so charts
// can read live tokens via useTheme()/chartTheme(); add a theme here + a token
// block in index.css to reintroduce switching.
const THEMES = [
  { id: 'aegov', label: 'AEGOV (UAE)', layout: 'topnav' },
] as const satisfies readonly Theme[]

export type ThemeId = (typeof THEMES)[number]['id']

const DEFAULT_THEME: ThemeId = 'aegov'

export function themeConfig(id: ThemeId): Theme {
  return THEMES.find((t) => t.id === id) ?? THEMES[0]
}

const STORAGE_KEY = 'ui-theme'

export function getTheme(): ThemeId {
  const saved = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY)) as ThemeId | null
  return THEMES.some((t) => t.id === saved) ? (saved as ThemeId) : DEFAULT_THEME
}

export function applyTheme(theme: ThemeId): void {
  document.documentElement.setAttribute('data-theme', theme)
}

export function setTheme(theme: ThemeId): void {
  localStorage.setItem(STORAGE_KEY, theme)
  applyTheme(theme)
}
