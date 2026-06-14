import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { getTheme, setTheme as persistTheme, themeConfig, type Theme, type ThemeId } from './theme'

interface ThemeCtx {
  theme: Theme
  themeId: ThemeId
  setTheme: (id: ThemeId) => void
}

const Ctx = createContext<ThemeCtx | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeId] = useState<ThemeId>(() => getTheme())

  const setTheme = useCallback((id: ThemeId) => {
    persistTheme(id) // localStorage + data-theme attr
    setThemeId(id)
  }, [])

  return (
    <Ctx.Provider value={{ theme: themeConfig(themeId), themeId, setTheme }}>{children}</Ctx.Provider>
  )
}

// Read the active theme anywhere. Components branch on `theme.layout`; all
// purely-visual differences stay in CSS (no need to touch this).
export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
