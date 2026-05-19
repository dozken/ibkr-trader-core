import { useQuery } from '@tanstack/react-query'
import { Link, Outlet, useRouterState } from '@tanstack/react-router'
import {
  BrainCircuit,
  ClipboardList,
  Coins,
  LayoutDashboard,
  Moon,
  ScanSearch,
  Server,
  Settings as SettingsIcon,
  Sun,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Toaster } from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import CommandPalette from './components/CommandPalette'
import { Logo } from './components/Logo'
import { ROUTES } from './shared/routes'
import { useAccount } from './features/trading/context/AccountContext'

interface PortfolioValue {
  available_funds: number
  connected: boolean
  account_type: 'PAPER' | 'LIVE'
}

interface Account {
  id: number
  label: string
  is_paper: boolean
  port: number
}

const NAV = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/signals', label: 'Signals', Icon: BrainCircuit },
  { to: '/screening', label: 'Screening', Icon: ScanSearch },
  { to: '/audit', label: 'Audit', Icon: ClipboardList },
  { to: '/zakat', label: 'Zakat', Icon: Coins },
  { to: '/accounts', label: 'Accounts', Icon: Server },
  { to: '/settings', label: 'Settings', Icon: SettingsIcon },
] as const

const MOBILE_NAV = [
  { to: '/', label: 'Home', Icon: LayoutDashboard },
  { to: '/signals', label: 'AI', Icon: BrainCircuit },
  { to: '/screening', label: 'Screen', Icon: ScanSearch },
  { to: '/audit', label: 'Audit', Icon: ClipboardList },
  { to: '/settings', label: 'Config', Icon: SettingsIcon },
] as const

export default function Layout() {
  const { location } = useRouterState()
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const [cmdOpen, setCmdOpen] = useState(false)
  const { selectedAccountId, setSelectedAccountId } = useAccount()

  const { data: portfolio } = useQuery<PortfolioValue>({
    queryKey: ['portfolio-value'],
    queryFn: () => fetch(ROUTES.PORTFOLIO_VALUE).then((r) => r.json()),
    refetchInterval: 60_000,
  })

  const { data: accounts } = useQuery<Account[]>({
    queryKey: ['accounts'],
    queryFn: () => fetch(ROUTES.ACCOUNTS).then((r) => r.json()),
    staleTime: 30_000,
  })

  useEffect(() => {
    let lastShift = 0
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'p') {
        e.preventDefault()
        setCmdOpen((o) => !o)
        return
      }
      if (e.key === 'Shift' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const now = Date.now()
        if (now - lastShift < 300) {
          setCmdOpen((o) => !o)
          lastShift = 0
        } else lastShift = now
      }
      // ? → open command palette (when not typing in an input)
      if (e.key === '?' && !e.metaKey && !e.ctrlKey) {
        const tag = (e.target as HTMLElement).tagName.toLowerCase()
        if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') {
          e.preventDefault()
          setCmdOpen((o) => !o)
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => {
    if (dark) {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [dark])

  return (
    <div className="flex flex-col min-h-screen bg-brand-base">
      <Toaster position="top-right" toastOptions={{ style: { background: '#1e2530', color: '#e2e8f0', border: '1px solid #2d3748', fontSize: '13px' } }} />
      <nav className="bg-brand-surface/90 backdrop-blur-md sticky top-0 z-50 border-b border-brand-divider px-4 py-2 flex items-center justify-between h-14">
        <div className="flex items-center gap-3">
          <Logo size={32} className="shadow-glow-primary" />
          <div className="flex flex-col">
            <h2 className="text-brand-light font-bold text-sm sm:text-base tracking-tight whitespace-nowrap leading-none">
              IBKR <span className="text-brand-primary">Shariah</span>
            </h2>
            {portfolio?.account_type === 'PAPER' && (
              <span className="text-[8px] sm:text-[9px] font-black text-brand-warning uppercase tracking-tighter mt-0.5 sm:mt-1 leading-none">
                Paper Trading
              </span>
            )}
          </div>
        </div>

        {/* Desktop/Tablet Nav - Show all 8 items when there is space */}
        <div className="hidden md:flex gap-1 items-center">
          {NAV.map(({ to, label, Icon }) => {
            const active = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)
            return (
              <Link
                key={to}
                to={to}
                className={`relative flex items-center gap-1.5 lg:gap-2 px-2 lg:px-3 py-2 rounded-lg text-[13px] lg:text-sm transition-all duration-200 whitespace-nowrap border border-transparent ${
                  active
                    ? 'text-brand-primary bg-brand-primary/10 font-bold border-brand-primary/20 shadow-[0_0_12px_rgba(45,212,191,0.1)]'
                    : 'text-brand-light/70 hover:text-brand-light hover:bg-brand-elevated'
                }`}
              >
                <Icon size={14} className={active ? 'text-brand-primary' : ''} />
                {label}
                {active && (
                  <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-brand-primary animate-pulse" />
                )}
              </Link>
            )
          })}
        </div>

        <div className="flex items-center gap-2">
          {/* Mobile indicator - small screens only */}
          <div className="md:hidden flex items-center gap-2 px-2.5 py-1 rounded-full bg-brand-primary/10 border border-brand-primary/20 text-[10px] font-black text-brand-primary uppercase tracking-[0.2em] shadow-[0_0_15px_rgba(45,212,191,0.1)]">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-primary animate-pulse" />
            {NAV.find((n) =>
              n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to),
            )?.label || 'Menu'}
          </div>

          {accounts && accounts.length === 1 && (
            <span className={`text-[11px] font-bold px-2 py-0.5 rounded border ${accounts[0].is_paper ? 'bg-brand-warning/10 border-brand-warning/30 text-brand-warning' : 'bg-brand-danger/10 border-brand-danger/30 text-brand-danger'}`}>
              {accounts[0].label} · {accounts[0].is_paper ? 'PAPER' : 'LIVE'}
            </span>
          )}
          {accounts && accounts.length > 1 && (
            <select
              value={selectedAccountId ?? ''}
              onChange={(e) => setSelectedAccountId(e.target.value ? Number(e.target.value) : null)}
              className="text-[11px] bg-brand-elevated border border-brand-divider text-brand-light rounded-md px-2 py-1 cursor-pointer focus:outline-none focus:border-brand-primary"
              title="Switch account"
            >
              <option value="">All accounts</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label} {a.is_paper ? '(Paper)' : '(Live)'}
                </option>
              ))}
            </select>
          )}

          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setDark((d) => !d)}
            className="text-brand-light/70 hover:text-brand-light transition-all"
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </Button>
        </div>
      </nav>

      <main className="flex-1 pb-24 md:pb-8">
        <div key={location.pathname} className="animate-in fade-in duration-200">
          <Outlet />
        </div>
      </main>

      {/* Mobile Bottom Nav - Only on small screens */}
      <nav
        className="md:hidden fixed bottom-0 left-0 right-0 bg-brand-surface/95 backdrop-blur-lg border-t border-brand-divider flex z-50 shadow-[0_-4px_20px_rgba(0,0,0,0.2)]"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {MOBILE_NAV.map(({ to, label, Icon }) => {
          const active = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)
          return (
            <Link
              key={to}
              to={to}
              className={`flex-1 flex flex-col items-center justify-center py-2 transition-all relative ${
                active ? 'text-brand-primary' : 'text-brand-light/70'
              }`}
            >
              <div
                className={`p-1 rounded-lg transition-all ${active ? 'bg-brand-primary/10' : ''}`}
              >
                <Icon size={18} strokeWidth={active ? 2.5 : 2} />
              </div>
              <span
                className={`text-[9px] font-bold uppercase tracking-tighter mt-0.5 ${active ? 'opacity-100' : 'opacity-70'}`}
              >
                {label}
              </span>
              {active && (
                <span className="absolute top-1 right-1/4 w-1 h-1 rounded-full bg-brand-primary animate-pulse" />
              )}
            </Link>
          )
        })}
      </nav>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </div>
  )
}
