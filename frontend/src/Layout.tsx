import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Outlet, useRouterState } from '@tanstack/react-router'
import {
  Bell,
  BellOff,
  BrainCircuit,
  ClipboardList,
  Coins,
  LayoutDashboard,
  Lock,
  Moon,
  ScanSearch,
  Server,
  Settings as SettingsIcon,
  Sun,
  Unlock,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import CommandPalette from './components/CommandPalette'
import { Logo } from './components/Logo'
import { API_KEY, ROUTES, withAccount } from './shared/routes'
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
  read_only: boolean
  ibkr_account_id: string | null
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

const isActive = (pathname: string, to: string) =>
  to === '/' ? pathname === '/' : pathname.startsWith(to)

export default function Layout() {
  const { location } = useRouterState()
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const [cmdOpen, setCmdOpen] = useState(false)
  const [accountToArm, setAccountToArm] = useState<Account | null>(null)
  const { selectedAccountId, setSelectedAccountId } = useAccount()
  const qc = useQueryClient()

  const { data: portfolio } = useQuery<PortfolioValue>({
    queryKey: ['portfolio-value', selectedAccountId],
    queryFn: () => fetch(withAccount(ROUTES.PORTFOLIO_VALUE, selectedAccountId)).then((r) => r.json()),
    refetchInterval: 60_000,
  })

  const { data: accounts } = useQuery<Account[]>({
    queryKey: ['accounts'],
    queryFn: () => fetch(ROUTES.ACCOUNTS).then((r) => r.json()),
    staleTime: 30_000,
  })

  // The chip shows one account: the selected one, or the only one there is.
  const chipAccount =
    accounts?.find((a) => a.id === selectedAccountId) ??
    (accounts?.length === 1 ? accounts[0] : null) ??
    null

  const armMutation = useMutation({
    mutationFn: ({ id, read_only }: { id: number; read_only: boolean }) =>
      fetch(`${ROUTES.ACCOUNTS}/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify({ read_only }),
      }).then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Request failed')
        return r.json() as Promise<Account>
      }),
    onSuccess: (acc) => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
      setAccountToArm(null)
      toast.success(acc.read_only ? `${acc.label} set to read-only` : `${acc.label} ARMED — orders will be sent`)
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Request failed')
      setAccountToArm(null)
    },
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

  useEffect(() => {
    const p = location.pathname
    const routeName =
      p === '/' ? 'Dashboard' :
      p.startsWith('/signals') ? 'Signals' :
      p.startsWith('/screening') ? 'Screening' :
      p.startsWith('/audit') ? 'Audit' :
      p.startsWith('/zakat') ? 'Zakat' :
      p.startsWith('/accounts') ? 'Accounts' :
      p.startsWith('/settings') ? 'Settings' :
      p.startsWith('/backtest') ? 'Backtest' :
      p.startsWith('/signal-quality') ? 'Signal Quality' :
      p.startsWith('/signal-log') ? 'Signal Log' :
      p.startsWith('/scanner') ? 'Scanner' :
      p.startsWith('/growth') ? 'Growth' :
      p.startsWith('/faq') ? 'Guide' : 'App'

    document.title = `${routeName} - IBKR Shariah`
  }, [location.pathname])

  const brand = (
    <Link to="/" className="flex items-center gap-3">
      <Logo size={32} />
      <div className="flex flex-col">
        <h2 className="text-brand-light font-bold text-sm sm:text-base tracking-tight whitespace-nowrap leading-none">
          IBKR <span className="text-brand-primary">Shariah</span>
        </h2>
        <span
          className={`text-[8px] sm:text-[9px] font-black uppercase tracking-tighter mt-0.5 sm:mt-1 leading-none ${portfolio?.account_type === 'LIVE' ? 'text-brand-success' : 'text-brand-warning'}`}
        >
          {portfolio?.account_type === 'LIVE' ? 'Live Trading' : 'Paper Trading'}
        </span>
      </div>
    </Link>
  )

  const controls = (
    <div className="flex items-center gap-2">
      {chipAccount && (
        <span
          className={`flex items-center gap-1.5 text-[11px] font-bold px-2 py-0.5 rounded border ${chipAccount.is_paper ? 'bg-brand-warning/10 border-brand-warning/30 text-brand-warning' : 'bg-brand-danger/10 border-brand-danger/30 text-brand-danger'}`}
          title={chipAccount.ibkr_account_id || undefined}
        >
          {chipAccount.label} · {chipAccount.is_paper ? 'PAPER' : 'LIVE'}
          <span
            className={`flex items-center gap-1 px-1.5 rounded ${chipAccount.read_only ? 'bg-brand-light/10 text-brand-light/80' : 'bg-brand-danger text-white'}`}
            title={chipAccount.read_only ? 'Read-only — no orders are sent' : 'ARMED — the bot can place real orders'}
          >
            {chipAccount.read_only ? <Lock size={10} /> : <Unlock size={10} />}
            {chipAccount.read_only ? 'READ-ONLY' : 'ARMED'}
          </span>
          <button
            onClick={() =>
              chipAccount.read_only
                ? setAccountToArm(chipAccount)
                : armMutation.mutate({ id: chipAccount.id, read_only: true })
            }
            disabled={armMutation.isPending}
            className="underline decoration-dotted underline-offset-2 opacity-80 hover:opacity-100 disabled:opacity-40"
            title={chipAccount.read_only ? 'Enable trading on this account' : 'Return this account to read-only'}
          >
            {armMutation.isPending ? '…' : chipAccount.read_only ? 'Arm' : 'Disarm'}
          </button>
        </span>
      )}
      {accounts && accounts.length > 1 && (
        <select
          value={selectedAccountId ?? ''}
          onChange={(e) => setSelectedAccountId(e.target.value ? Number(e.target.value) : null)}
          className="text-xs font-semibold bg-brand-elevated border-2 border-brand-primary/40 text-brand-light rounded-lg px-3 py-1.5 cursor-pointer focus:outline-none focus:border-brand-primary shadow-sm"
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
        onClick={async () => {
          if (!('Notification' in window)) return
          if (Notification.permission === 'granted') return
          await Notification.requestPermission()
        }}
        className="text-brand-light/70 hover:text-brand-light transition-all"
        title={typeof Notification !== 'undefined' && Notification.permission === 'granted' ? 'Notifications enabled' : 'Enable notifications'}
      >
        {typeof Notification !== 'undefined' && Notification.permission === 'granted' ? <Bell size={18} /> : <BellOff size={18} />}
      </Button>

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
  )

  return (
    <div className="flex flex-col min-h-screen bg-brand-base">
      <Toaster position="top-right" toastOptions={{ style: { background: '#1e2530', color: '#e2e8f0', border: '1px solid #2d3748', fontSize: '13px' } }} />

      <nav className="bg-brand-surface/90 backdrop-blur-md sticky top-0 z-50 border-b border-brand-divider px-4 py-2 flex items-center justify-between h-14">
        {brand}

        <div className="hidden md:flex gap-1 items-center">
          {NAV.map(({ to, label, Icon }) => {
            const active = isActive(location.pathname, to)
            return (
              <Link
                key={to}
                to={to}
                className={`relative flex items-center gap-1.5 lg:gap-2 px-2 lg:px-3 py-2 rounded-lg text-[13px] lg:text-sm transition-all duration-200 whitespace-nowrap border border-transparent ${
                  active
                    ? 'text-brand-primary bg-brand-primary/10 font-bold border-brand-primary/20'
                    : 'text-brand-light/70 hover:text-brand-light hover:bg-brand-elevated'
                }`}
              >
                <Icon size={14} className={active ? 'text-brand-primary' : ''} />
                {label}
              </Link>
            )
          })}
        </div>

        {controls}
      </nav>

      <main className="flex-1 pb-24 md:pb-8">
        <div key={location.pathname} className="animate-in fade-in duration-200">
          <Outlet />
        </div>
      </main>

      <nav
        className="md:hidden fixed bottom-0 left-0 right-0 bg-brand-surface/95 backdrop-blur-lg border-t border-brand-divider flex z-50 shadow-[0_-4px_20px_rgba(0,0,0,0.2)]"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {MOBILE_NAV.map(({ to, label, Icon }) => {
          const active = isActive(location.pathname, to)
          return (
            <Link
              key={to}
              to={to}
              className={`flex-1 flex flex-col items-center justify-center py-2 transition-all relative ${active ? 'text-brand-primary' : 'text-brand-light/70'}`}
            >
              <div className={`p-1 rounded-lg transition-all ${active ? 'bg-brand-primary/10' : ''}`}>
                <Icon size={18} strokeWidth={active ? 2.5 : 2} />
              </div>
              <span className={`text-[9px] font-bold uppercase tracking-tighter mt-0.5 ${active ? 'opacity-100' : 'opacity-70'}`}>
                {label}
              </span>
            </Link>
          )
        })}
      </nav>

      <Dialog open={!!accountToArm} onOpenChange={(open) => !open && setAccountToArm(null)}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader>
            <DialogTitle>
              Arm trading on {accountToArm?.label}?
            </DialogTitle>
            <DialogDescription>
              {accountToArm?.is_paper
                ? 'This paper account will start placing simulated orders.'
                : `This lifts the order block on ${accountToArm?.ibkr_account_id || 'this account'} — the bot will place orders with REAL money, unattended, until you disarm it.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4 gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setAccountToArm(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={() => accountToArm && armMutation.mutate({ id: accountToArm.id, read_only: false })}
              disabled={armMutation.isPending}
            >
              {armMutation.isPending ? 'Arming...' : 'Arm trading'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </div>
  )
}
