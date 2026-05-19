import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { AlertTriangle, CheckCircle2, Plus, Server, ShieldCheck, Trash2, Edit2, Check, X, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Page, PageSection } from '@/components/ui/layout'
import { Text, Eyebrow } from '@/components/ui/text'
import { ROUTES, API_KEY } from '../../shared/routes'

interface Account {
  id: number
  label: string
  host: string
  port: number
  client_id: number
  ibkr_account_id: string | null
  is_paper: boolean
  is_active: boolean
  created_at: string
}

interface AccountCreate {
  label: string
  host: string
  port: number
  client_id: number
  ibkr_account_id: string
  is_paper: boolean
}

interface ReadinessGates {
  ibkr_connected: boolean
  port_type: 'PAPER' | 'LIVE'
  loops_healthy: boolean
  drawdown_not_triggered: boolean
  trade_error_rate_ok: boolean
  audit_integrity_ok: boolean
  enough_signal_outcomes: boolean
  win_rate_ok: boolean
  avg_return_ok: boolean
  paper_days_ok: boolean
}

interface ReadinessPerformance {
  n_resolved_signals: number
  min_resolved_required: number
  win_rate_pct: number | null
  min_win_rate_pct: number
  avg_7d_return_pct: number | null
  min_avg_return_pct: number
  paper_trading_days: number
  min_paper_days: number
}

interface RecentError {
  symbol: string
  side: string
  exchange: string
  created_at: string | null
}

interface ReadinessData {
  ready: boolean
  port_type: 'PAPER' | 'LIVE'
  trade_count: number
  error_rate_pct: number | null
  gates: ReadinessGates
  blockers: string[]
  performance: ReadinessPerformance
  recent_errors?: RecentError[]
  note: string | null
}

function GateRow({ pass, label, detail }: { pass: boolean; label: string; detail?: string }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-brand-divider/40 last:border-0">
      {pass ? (
        <CheckCircle2 size={15} className="text-brand-success mt-0.5 shrink-0" />
      ) : (
        <XCircle size={15} className="text-brand-danger mt-0.5 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <Text variant="body" className={pass ? 'font-medium' : 'font-medium text-brand-danger'}>{label}</Text>
        {detail && <Text variant="tiny" className="mt-0.5 opacity-80">{detail}</Text>}
      </div>
    </div>
  )
}

function GoLiveReadiness() {
  const { data, isLoading, isError } = useQuery<ReadinessData>({
    queryKey: ['system-readiness'],
    queryFn: () => fetch(ROUTES.SYSTEM_READINESS).then((r) => r.json()),
    refetchInterval: 30_000,
  })

  if (isLoading) return <div className="card p-5"><Text variant="meta">Checking readiness…</Text></div>
  if (isError || !data) return null

  const { ready, gates, blockers, performance, port_type } = data

  const perfGates = [
    {
      pass: gates.enough_signal_outcomes,
      label: 'Signal history',
      detail: `${performance.n_resolved_signals} of ${performance.min_resolved_required} resolved BUY outcomes`,
    },
    {
      pass: gates.win_rate_ok,
      label: 'Win rate',
      detail: performance.win_rate_pct !== null
        ? `${performance.win_rate_pct}% (need ≥${performance.min_win_rate_pct}%)`
        : `Not enough data yet (need ${performance.min_resolved_required} resolved signals)`,
    },
    {
      pass: gates.avg_return_ok,
      label: 'Avg 7d signal return',
      detail: performance.avg_7d_return_pct !== null
        ? `${performance.avg_7d_return_pct >= 0 ? '+' : ''}${performance.avg_7d_return_pct}% (floor: ${performance.min_avg_return_pct}%)`
        : 'No resolved signals yet',
    },
    {
      pass: gates.paper_days_ok,
      label: 'Paper trading duration',
      detail: `${performance.paper_trading_days} days (need ≥${performance.min_paper_days})`,
    },
  ]

  const infraGates = [
    { pass: gates.ibkr_connected, label: 'IBKR connected' },
    { pass: gates.loops_healthy, label: 'All loops healthy' },
    { pass: gates.drawdown_not_triggered, label: 'No drawdown circuit breaker' },
    { pass: gates.trade_error_rate_ok, label: 'Trade error rate ≤10%', detail: data.error_rate_pct !== null ? `${data.error_rate_pct}%` : undefined },
    { pass: gates.audit_integrity_ok, label: 'Audit log integrity OK' },
  ]

  return (
    <div className="card p-0 overflow-hidden mb-6">
      <header className={`px-6 py-4 flex items-center gap-4 border-b border-brand-divider/50 ${
        ready ? 'bg-brand-success/8' : 'bg-brand-danger/5'
      }`}>
        {ready ? (
          <ShieldCheck size={22} className="text-brand-success shrink-0" />
        ) : (
          <AlertTriangle size={22} className="text-brand-danger shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <Text variant="h3" className={ready ? 'text-brand-success' : 'text-brand-danger'}>
            {ready ? 'Ready for live trading' : 'Not ready for live trading'}
          </Text>
          <Text variant="tiny" className="mt-0.5">
            {port_type === 'PAPER'
              ? 'Currently on paper. Switch port to 4001 (IB Gateway live) when all gates pass.'
              : 'Currently on LIVE account.'}
          </Text>
        </div>
        <span className={`t-eyebrow px-2.5 py-1 rounded-full border ${
          port_type === 'PAPER'
            ? 'text-brand-warning border-brand-warning/40 bg-brand-warning/10'
            : 'text-brand-danger border-brand-danger/40 bg-brand-danger/10'
        }`}>
          {port_type}
        </span>
      </header>

      <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-brand-divider/40">
        <section className="px-6 py-4">
          <Eyebrow className="mb-3 block">Performance</Eyebrow>
          {perfGates.map((g) => (
            <GateRow key={g.label} {...g} />
          ))}
        </section>
        <section className="px-6 py-4">
          <Eyebrow className="mb-3 block">Infrastructure</Eyebrow>
          {infraGates.map((g) => (
            <GateRow key={g.label} {...g} />
          ))}
        </section>
      </div>

      {blockers.length > 0 && (
        <div className="px-6 py-3 bg-brand-danger/5 border-t border-brand-danger/15">
          <Eyebrow className="mb-1.5 block text-brand-danger/70">What to fix</Eyebrow>
          <ul className="space-y-0.5">
            {blockers.map((b) => (
              <li key={b} className="t-tiny text-brand-danger/80 flex items-start gap-1.5">
                <span className="mt-1 shrink-0">·</span>
                {b}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.recent_errors && data.recent_errors.length > 0 && (
        <div className="px-6 py-3 border-t border-brand-divider/40">
          <Eyebrow className="mb-2 block">Recent IBKR errors (last 7d)</Eyebrow>
          {(() => {
            const byEx: Record<string, number> = {}
            const bySide: Record<string, number> = {}
            for (const e of data.recent_errors) {
              byEx[e.exchange] = (byEx[e.exchange] ?? 0) + 1
              bySide[e.side] = (bySide[e.side] ?? 0) + 1
            }
            return (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-2">
                {Object.entries(byEx).map(([ex, n]) => (
                  <Text key={ex} variant="tiny" as="span" className="t-num">
                    <span className="opacity-50">{ex}:</span> <span className="font-bold text-brand-danger">{n}</span>
                  </Text>
                ))}
                <span className="text-brand-light/20">·</span>
                {Object.entries(bySide).map(([s, n]) => (
                  <Text key={s} variant="tiny" as="span" className="t-num">
                    <span className="opacity-50">{s}:</span> <span className="font-bold text-brand-danger">{n}</span>
                  </Text>
                ))}
              </div>
            )
          })()}
          <ul className="space-y-0.5 max-h-32 overflow-y-auto">
            {data.recent_errors.map((e, i) => (
              <li key={i} className="t-tiny flex items-center gap-2 t-num">
                <span className="text-brand-light/40 w-32 shrink-0">
                  {e.created_at ? new Date(e.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                </span>
                <span className="font-bold text-brand-light w-16">{e.symbol}</span>
                <span className={`w-12 ${e.side === 'BUY' ? 'text-brand-success' : 'text-brand-danger'}`}>{e.side}</span>
                <span className="opacity-50">{e.exchange}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

const EMPTY_FORM: AccountCreate = {
  label: '',
  host: '127.0.0.1',
  port: 7497,
  client_id: 1,
  ibkr_account_id: '',
  is_paper: true,
}

export default function AccountsPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<AccountCreate>(EMPTY_FORM)
  const [editId, setEditId] = useState<number | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: accounts = [], isLoading } = useQuery<Account[]>({
    queryKey: ['accounts'],
    queryFn: () => fetch(`${ROUTES.ACCOUNTS}?include_inactive=false`).then((r) => r.json()),
  })

  const createMutation = useMutation({
    mutationFn: (body: AccountCreate) =>
      fetch(ROUTES.ACCOUNTS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify(body),
      }).then(async (r) => {
        if (!r.ok) {
          const data = await r.json()
          throw new Error(data.detail || `Error ${r.status}`)
        }
        return r.json()
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
      setShowForm(false)
      setForm(EMPTY_FORM)
      setError(null)
      toast.success('Account created')
    },
    onError: (e: Error) => {
      setError(e.message)
      toast.error(e.message || 'Request failed')
    },
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, label }: { id: number; label: string }) =>
      fetch(`${ROUTES.ACCOUNTS}/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify({ label }),
      }).then((r) => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
      setEditId(null)
      toast.success('Account renamed')
    },
    onError: (e: Error) => toast.error(e.message || 'Request failed'),
  })

  const deactivateMutation = useMutation({
    mutationFn: (id: number) =>
      fetch(`${ROUTES.ACCOUNTS}/${id}`, {
        method: 'DELETE',
        headers: { 'X-API-Key': API_KEY },
      }).then((r) => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
      toast.success('Account deactivated')
    },
    onError: (e: Error) => toast.error(e.message || 'Request failed'),
  })

  function set(k: keyof AccountCreate, v: string | number | boolean) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  return (
    <Page>
      <header className="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="heading-1 flex items-center gap-2">
            <Server className="text-brand-primary" size={22} />
            IBKR Accounts
          </h1>
          <p className="text-brand-light/80 text-sm mt-1">Manage connected Interactive Brokers accounts</p>
        </div>
        <Button onClick={() => setShowForm((s) => !s)} size="sm">
          <Plus size={14} className="mr-1" />
          Add Account
        </Button>
      </header>

      <GoLiveReadiness />

      {showForm && (
        <PageSection>
          <div className="bg-brand-elevated border border-brand-divider rounded-xl p-5 space-y-4">
            <h3 className="text-brand-light font-semibold text-sm">New Account</h3>

            {error && (
              <div className="text-red-400 text-xs bg-red-900/20 border border-red-800/40 rounded px-3 py-2">
                {error}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Label</Label>
                <Input value={form.label} onChange={(e) => set('label', e.target.value)} placeholder="e.g. Paper Trading" />
              </div>
              <div>
                <Label>IBKR Account ID</Label>
                <Input value={form.ibkr_account_id} onChange={(e) => set('ibkr_account_id', e.target.value)} placeholder="e.g. DU1234567" />
              </div>
              <div>
                <Label>Host</Label>
                <Input value={form.host} onChange={(e) => set('host', e.target.value)} />
              </div>
              <div>
                <Label>Port</Label>
                <Input type="number" value={form.port} onChange={(e) => set('port', Number(e.target.value))} />
              </div>
              <div>
                <Label>Client ID</Label>
                <Input type="number" value={form.client_id} onChange={(e) => set('client_id', Number(e.target.value))} />
              </div>
              <div className="flex items-end gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.is_paper}
                    onChange={(e) => set('is_paper', e.target.checked)}
                    className="accent-brand-primary"
                  />
                  <span className="text-brand-light text-sm">Paper trading</span>
                </label>
              </div>
            </div>

            <div className="flex gap-2 justify-end">
              <Button variant="ghost" size="sm" onClick={() => { setShowForm(false); setError(null) }}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!form.label || createMutation.isPending}
                onClick={() => createMutation.mutate(form)}
              >
                {createMutation.isPending ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </div>
        </PageSection>
      )}

      <PageSection>
        {isLoading ? (
          <Text variant="meta">Loading…</Text>
        ) : accounts.length === 0 ? (
          <Text variant="meta">No accounts configured. Add one above.</Text>
        ) : (
          <div className="space-y-3">
            {accounts.map((acc) => (
              <div
                key={acc.id}
                className="bg-brand-elevated border border-brand-divider rounded-xl p-4 flex items-center justify-between gap-4"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Server size={18} className="text-brand-primary shrink-0" />
                  <div className="min-w-0">
                    {editId === acc.id ? (
                      <div className="flex items-center gap-2">
                        <Input
                          value={editLabel}
                          onChange={(e) => setEditLabel(e.target.value)}
                          className="h-7 text-sm w-40"
                          autoFocus
                        />
                        <button onClick={() => renameMutation.mutate({ id: acc.id, label: editLabel })} className="text-brand-primary hover:opacity-80">
                          <Check size={14} />
                        </button>
                        <button onClick={() => setEditId(null)} className="text-brand-light/50 hover:opacity-80">
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <Text variant="body" as="span" className="font-semibold truncate">{acc.label}</Text>
                        <button
                          onClick={() => { setEditId(acc.id); setEditLabel(acc.label) }}
                          className="text-brand-light/40 hover:text-brand-light/80"
                        >
                          <Edit2 size={12} />
                        </button>
                      </div>
                    )}
                    <Text variant="tiny" className="mt-0.5 t-num">
                      {acc.host}:{acc.port} · client_id={acc.client_id}
                      {acc.ibkr_account_id && ` · ${acc.ibkr_account_id}`}
                    </Text>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <Badge variant={acc.is_paper ? 'warning' : 'success'}>
                    {acc.is_paper ? 'Paper' : 'Live'}
                  </Badge>
                  <button
                    onClick={() => {
                      if (window.confirm(`Deactivate account "${acc.label}"? Active positions remain open in IBKR.`)) {
                        deactivateMutation.mutate(acc.id)
                      }
                    }}
                    className="text-brand-light/40 hover:text-red-400 transition-colors"
                    title="Remove account"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </PageSection>
    </Page>
  )
}
