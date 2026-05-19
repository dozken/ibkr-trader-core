import { useNavigate, useRouterState } from '@tanstack/react-router'
import {
  BookOpen,
  BrainCircuit,
  ClipboardList,
  Coins,
  FlaskConical,
  History,
  LayoutDashboard,
  Radar,
  ScanSearch,
  Search,
  Server,
  Settings,
  TrendingUp,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

const ITEMS = [
  { label: 'Dashboard', to: '/', Icon: LayoutDashboard, keywords: 'home portfolio positions' },
  { label: 'Signals', to: '/signals', Icon: BrainCircuit, keywords: 'ai scanner trade buy' },
  {
    label: 'Screening',
    to: '/screening',
    Icon: ScanSearch,
    keywords: 'shariah halal compliance check',
  },
  { label: 'Scanner', to: '/scanner', Icon: Radar, keywords: 'scan region market watchlist' },
  { label: 'Audit Trail', to: '/audit', Icon: ClipboardList, keywords: 'log history trades audit' },
  { label: 'Settings', to: '/settings', Icon: Settings, keywords: 'config api key broker' },
  { label: 'Backtest', to: '/backtest', Icon: FlaskConical, keywords: 'portfolio backtest simulate history' },
  { label: 'Signal Quality', to: '/signal-quality', Icon: TrendingUp, keywords: 'accuracy win rate outcomes' },
  { label: 'Signal Log', to: '/signal-log', Icon: History, keywords: 'signal history log ai' },
  { label: 'Zakat', to: '/zakat', Icon: Coins, keywords: 'purification zakat hawl charity' },
  { label: 'Accounts', to: '/accounts', Icon: Server, keywords: 'ibkr account paper live' },
  { label: 'Guide', to: '/faq', Icon: BookOpen, keywords: 'faq help shariah halal guide' },
]

interface Props {
  open: boolean
  onClose: () => void
}

export default function CommandPalette({ open, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const { location } = useRouterState()

  const filtered = ITEMS.filter((item) =>
    `${item.label} ${item.keywords}`.toLowerCase().includes(query.toLowerCase()),
  )

  const isActive = (to: string) =>
    to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)

  useEffect(() => {
    if (open) {
      setQuery('')
      const activeIdx = filtered.findIndex((item) => isActive(item.to))
      setCursor(activeIdx >= 0 ? activeIdx : 0)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  const go = (to: string) => {
    navigate({ to })
    onClose()
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => (c + 1) % filtered.length)
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => (c - 1 + filtered.length) % filtered.length)
    }
    if (e.key === 'Enter' && filtered[cursor]) go(filtered[cursor].to)
    if (e.key === 'Escape') onClose()
  }

  if (!open) return null

  return (
    // biome-ignore lint/a11y/useSemanticElements: overlay contains interactive content
    <div
      className="modal-overlay"
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      role="button"
      tabIndex={-1}
      aria-label="Close modal"
    >
      <div
        className="modal-content w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKey}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
      >
        <div className="flex items-center gap-3 p-4 border-b border-brand-divider">
          <Search size={16} className="text-brand-light/70 shrink-0" />
          <input
            ref={inputRef}
            className="flex-1 bg-transparent outline-none text-brand-light text-sm font-mono placeholder:text-brand-light/70"
            placeholder="Go to…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd className="text-brand-light/70 text-xs border border-brand-divider rounded px-1.5 py-0.5">
            esc
          </kbd>
        </div>
        <ul className="py-2 max-h-72 overflow-y-auto">
          {filtered.length === 0 && (
            <li className="px-4 py-3 text-sm text-brand-light/70">No results</li>
          )}
          {filtered.map((item, i) => {
            const active = isActive(item.to)
            return (
              <li key={item.to}>
                <button
                  type="button"
                  className={`w-full flex items-center gap-3 px-4 py-3 text-sm transition-colors text-left ${
                    i === cursor
                      ? 'bg-brand-primary/15 text-brand-primary'
                      : 'text-brand-light hover:bg-brand-divider/30'
                  }`}
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => go(item.to)}
                >
                  <item.Icon
                    size={16}
                    className={i === cursor ? 'text-brand-primary' : 'text-brand-light/70'}
                  />
                  <span className="font-medium">{item.label}</span>
                  <span className="text-brand-light/70 text-xs ml-auto flex items-center gap-2">
                    {active && (
                      <span className="text-[10px] font-bold text-brand-primary/70 uppercase tracking-wider">here</span>
                    )}
                    {item.to}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
