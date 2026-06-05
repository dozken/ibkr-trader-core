import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, BrainCircuit, Clock, TrendingUp } from 'lucide-react'
import React, { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Page, PageHeader, CardGrid, InfoRow, Stack } from '@/components/ui/layout'
import { Heading } from '@/components/ui/primitives'
import { Text, Eyebrow } from '@/components/ui/text'
import { ErrorBoundary } from '../../components/ErrorBoundary'
import { ROUTES } from '../../shared/routes'

interface SignalLogRow {
  symbol: string
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  outcome_7d_pct: number | null
  outcome_30d_pct: number | null
  created_at: string
  t_score: number | null
  f_score: number | null
  s_score: number | null
  signal_price: number | null
}

interface FactorGroup {
  count: number
  avg_f_score: number | null
  avg_t_score: number | null
  avg_s_score: number | null
  avg_confidence: number | null
  avg_7d_return: number | null
}

interface StrategyAudit {
  model_type: string
  model_loaded: boolean
  snapshot_count: number
  n_resolved_signals: number
  min_for_learned_weights: number
  learned_weights: { fw: number; tw: number; sw: number; n_outcomes: number } | null
  factor_analysis: { wins: FactorGroup; losses: FactorGroup } | null
}

type ActionFilter = 'ALL' | 'BUY' | 'SELL' | 'HOLD'

function outcomeClass(value: number | null, action: 'BUY' | 'SELL' | 'HOLD'): string {
  if (value === null) return 'text-zinc-400'
  if (action === 'BUY') return value > 0 ? 'text-green-400' : 'text-red-400'
  if (action === 'SELL') return value < 0 ? 'text-green-400' : 'text-red-400'
  return 'text-zinc-400'
}

function isWin(row: SignalLogRow): boolean {
  if (row.outcome_7d_pct === null) return false
  if (row.action === 'BUY') return row.outcome_7d_pct > 0
  if (row.action === 'SELL') return row.outcome_7d_pct < 0
  return false
}

function actionBadgeVariant(action: 'BUY' | 'SELL' | 'HOLD') {
  if (action === 'BUY') return 'success' as const
  if (action === 'SELL') return 'danger' as const
  return 'secondary' as const
}

const OutcomeCell: React.FC<{ value: number | null; action: 'BUY' | 'SELL' | 'HOLD' }> = ({
  value,
  action,
}) => {
  if (value === null) {
    return (
      <span className="inline-flex items-center gap-1 text-zinc-500 text-xs">
        <Clock size={10} />
        Pending
      </span>
    )
  }
  const cls = outcomeClass(value, action)
  const sign = value >= 0 ? '+' : ''
  return (
    <span className={`font-mono text-xs font-semibold ${cls}`}>
      {sign}
      {value.toFixed(2)}%
    </span>
  )
}

const StatCard: React.FC<{
  label: string
  value: string | number
  sub?: string
  accent?: string
}> = ({ label, value, sub, accent = 'text-brand-light' }) => (
  <div className="card p-5 border-l-4 border-l-brand-primary">
    <Eyebrow className="mb-1 block">{label}</Eyebrow>
    <p className={`text-2xl font-bold t-num ${accent}`}>{value}</p>
    {sub && <Text variant="tiny" className="mt-1">{sub}</Text>}
  </div>
)

const SignalQualityPage: React.FC = () => {
  const [actionFilter, setActionFilter] = useState<ActionFilter>('ALL')
  const [symbolFilter, setSymbolFilter] = useState('')

  const { data = [], isLoading, isError } = useQuery<SignalLogRow[]>({
    queryKey: ['signal-log'],
    queryFn: () => fetch(ROUTES.AI_SIGNAL_LOG).then((r) => r.json()),
    staleTime: 60_000,
  })

  const { data: audit } = useQuery<StrategyAudit>({
    queryKey: ['strategy-audit'],
    queryFn: () => fetch(ROUTES.AI_STRATEGY_AUDIT).then((r) => r.json()),
    staleTime: 120_000,
  })

  const filtered = data.filter((row) => {
    if (actionFilter !== 'ALL' && row.action !== actionFilter) return false
    if (symbolFilter && !row.symbol.toLowerCase().includes(symbolFilter.toLowerCase())) return false
    return true
  })

  // Stats computed from full data, not filtered view
  const resolved = data.filter((r) => r.outcome_7d_pct !== null)
  const pending = data.filter((r) => r.outcome_7d_pct === null)
  const wins = resolved.filter(isWin)
  const winRate = resolved.length > 0 ? (wins.length / resolved.length) * 100 : 0
  const avg7d =
    resolved.length > 0
      ? resolved.reduce((s, r) => s + (r.outcome_7d_pct ?? 0), 0) / resolved.length
      : null
  const resolved30 = data.filter((r) => r.outcome_30d_pct !== null)
  const avg30d =
    resolved30.length > 0
      ? resolved30.reduce((s, r) => s + (r.outcome_30d_pct ?? 0), 0) / resolved30.length
      : null

  const oldestPendingTime = pending.length > 0 
    ? Math.min(...pending.map(p => new Date(p.created_at).getTime()))
    : Date.now()
  const statsDate = new Date(oldestPendingTime + 7 * 86_400_000)

  return (
    <Page>
      <PageHeader>
        <Stack gap="xs">
          <Heading icon={TrendingUp}>Signal Quality</Heading>
          <Text tone="muted">
            Track AI signal accuracy over 7-day and 30-day horizons
          </Text>
        </Stack>
      </PageHeader>

      {/* Pending outcomes notice */}
      {pending.length > 0 && resolved.length === 0 && (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-zinc-700/50 bg-zinc-900/60 px-4 py-3">
          <Clock size={14} className="text-zinc-400 mt-0.5 shrink-0" />
          <p className="text-xs text-zinc-400">
            <span className="font-semibold text-zinc-200">{pending.length} signals</span> logged — outcomes fill automatically once 7 days have passed.
            Win-rate stats will appear from <span className="font-semibold text-zinc-200">{statsDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>.
          </p>
        </div>
      )}

      {/* Stats bar */}
      <CardGrid cols={4} className="mb-8">
        <StatCard label="Total Signals" value={data.length} sub="in log" />
        <StatCard
          label="Win Rate (7d)"
          value={resolved.length > 0 ? `${winRate.toFixed(1)}%` : '—'}
          sub={`${wins.length} of ${resolved.length} resolved`}
          accent={winRate >= 50 ? 'text-green-400' : 'text-red-400'}
        />
        <StatCard
          label="Avg 7d Return"
          value={avg7d !== null ? `${avg7d >= 0 ? '+' : ''}${avg7d.toFixed(2)}%` : '—'}
          sub="resolved signals only"
          accent={
            avg7d !== null ? (avg7d >= 0 ? 'text-green-400' : 'text-red-400') : 'text-zinc-100'
          }
        />
        <StatCard
          label="Avg 30d Return"
          value={avg30d !== null ? `${avg30d >= 0 ? '+' : ''}${avg30d.toFixed(2)}%` : '—'}
          sub={`${pending.length} pending`}
          accent={
            avg30d !== null ? (avg30d >= 0 ? 'text-green-400' : 'text-red-400') : 'text-zinc-100'
          }
        />
        <StatCard
          label="Signals Analyzed"
          value={data.filter(r => r.t_score !== null).length}
          sub="have AI score data"
        />
      </CardGrid>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="flex bg-zinc-900 p-1 rounded-lg border border-zinc-800">
          {(['ALL', 'BUY', 'SELL', 'HOLD'] as ActionFilter[]).map((a) => (
            <button
              key={a}
              type="button"
              onClick={() => setActionFilter(a)}
              className={`px-3 py-1 text-[10px] font-bold uppercase rounded-md transition-all ${
                actionFilter === a
                  ? 'bg-brand-primary text-white shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-100'
              }`}
            >
              {a}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="Filter by symbol…"
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          className="h-8 px-3 text-sm bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-brand-primary/60 w-40"
        />
        {(actionFilter !== 'ALL' || symbolFilter) && (
          <button
            type="button"
            onClick={() => {
              setActionFilter('ALL')
              setSymbolFilter('')
            }}
            className="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors uppercase tracking-wider"
          >
            Clear
          </button>
        )}
        <span className="text-xs text-zinc-500 ml-auto">{filtered.length} signals</span>
      </div>

      {/* Table */}
      <div className="table-container">
        {isLoading ? (
          <div className="p-12 text-center text-zinc-500 text-sm">Loading signal log…</div>
        ) : isError ? (
          <div className="p-12 text-center">
            <AlertTriangle size={24} className="mx-auto mb-2 text-brand-warning opacity-50" />
            <p className="text-zinc-500 text-sm">Failed to load signal log.</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-zinc-500 text-sm italic">
            No signals match your filter.
          </div>
        ) : (
          <table className="w-full text-left">
            <thead className="table-header">
              <tr>
                <th className="table-cell">Symbol</th>
                <th className="table-cell">Action</th>
                <th className="table-cell">Confidence</th>
                <th className="table-cell">Trend Score</th>
                <th className="table-cell">Signal Price</th>
                <th className="table-cell">7d Outcome</th>
                <th className="table-cell">30d Outcome</th>
                <th className="table-cell">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {filtered.map((row, i) => (
                <tr key={i} className="table-row hover:bg-zinc-900/40 transition-colors">
                  <td className="table-cell font-bold text-zinc-100">{row.symbol}</td>
                  <td className="table-cell">
                    <Badge variant={actionBadgeVariant(row.action)} className="text-[10px]">
                      {row.action}
                    </Badge>
                  </td>
                  <td className="table-cell">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden max-w-[60px]">
                        <div
                          className={`h-full rounded-full ${
                            row.action === 'BUY'
                              ? 'bg-green-500'
                              : row.action === 'SELL'
                                ? 'bg-red-500'
                                : 'bg-zinc-500'
                          }`}
                          style={{ width: `${row.confidence}%` }}
                        />
                      </div>
                      <span className="font-mono text-xs text-zinc-400">
                        {row.confidence.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="table-cell font-mono text-xs text-zinc-400">
                    {row.t_score !== null ? row.t_score.toFixed(0) : '—'}
                  </td>
                  <td className="table-cell font-mono text-xs text-zinc-400">
                    {row.signal_price !== null ? `$${row.signal_price.toFixed(2)}` : '—'}
                  </td>
                  <td className="table-cell">
                    <OutcomeCell value={row.outcome_7d_pct} action={row.action} />
                  </td>
                  <td className="table-cell">
                    <OutcomeCell value={row.outcome_30d_pct} action={row.action} />
                  </td>
                  <td className="table-cell text-xs text-zinc-500 font-mono">
                    {new Date(row.created_at).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Per-symbol breakdown */}
      {resolved.length > 0 && (() => {
        const bySymbol: Record<string, { wins: number; total: number; avg7d: number }> = {}
        for (const r of resolved) {
          if (!bySymbol[r.symbol]) bySymbol[r.symbol] = { wins: 0, total: 0, avg7d: 0 }
          bySymbol[r.symbol].total++
          bySymbol[r.symbol].avg7d += r.outcome_7d_pct ?? 0
          if (isWin(r)) bySymbol[r.symbol].wins++
        }
        const rows = Object.entries(bySymbol)
          .map(([sym, s]) => ({ sym, ...s, winRate: (s.wins / s.total) * 100, avgReturn: s.avg7d / s.total }))
          .sort((a, b) => b.winRate - a.winRate)
        return (
          <div className="mt-8">
            <h2 className="text-sm font-bold text-zinc-300 mb-3 uppercase tracking-widest">Per-Symbol Accuracy</h2>
            <div className="table-container">
              <table className="w-full text-left">
                <thead className="table-header">
                  <tr>
                    <th className="table-cell">Symbol</th>
                    <th className="table-cell">Signals</th>
                    <th className="table-cell">Win Rate</th>
                    <th className="table-cell">Avg 7d Return</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {rows.map((r) => (
                    <tr key={r.sym} className="table-row">
                      <td className="table-cell font-bold text-zinc-100">{r.sym}</td>
                      <td className="table-cell text-xs text-zinc-400 font-mono">{r.total}</td>
                      <td className="table-cell">
                        <span className={`font-mono text-xs font-semibold ${r.winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                          {r.winRate.toFixed(0)}%
                        </span>
                      </td>
                      <td className="table-cell">
                        <span className={`font-mono text-xs font-semibold ${r.avgReturn >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {r.avgReturn >= 0 ? '+' : ''}{r.avgReturn.toFixed(2)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })()}

      {/* Strategy Audit */}
      {audit && (
        <section className="mt-8">
          <Text variant="h3" className="mb-3 flex items-center gap-2 t-eyebrow !text-brand-light/60">
            <BrainCircuit size={14} />
            Strategy Audit
          </Text>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="card p-4">
              <Eyebrow className="mb-1 block">Model</Eyebrow>
              <p className={`text-base font-bold t-num ${audit.model_loaded ? 'text-brand-success' : 'text-brand-warning'}`}>
                {audit.model_type}
              </p>
              <Text variant="tiny" className="mt-1">{audit.model_loaded ? 'loaded' : 'not loaded'}</Text>
            </div>
            <div className="card p-4">
              <Eyebrow className="mb-1 block">Snapshots</Eyebrow>
              <p className="text-base font-bold t-num text-brand-light">{audit.snapshot_count.toLocaleString()}</p>
              <Text variant="tiny" className="mt-1">feature data points</Text>
            </div>
            <div className="card p-4">
              <Eyebrow className="mb-1 block">Learned Weights</Eyebrow>
              {audit.learned_weights ? (
                <>
                  <p className="text-base font-bold t-num text-brand-primary">Active</p>
                  <Text variant="tiny" className="mt-1 t-num">
                    F:{audit.learned_weights.fw}% T:{audit.learned_weights.tw}% S:{audit.learned_weights.sw}%
                  </Text>
                </>
              ) : (
                <>
                  <p className="text-base font-bold t-num text-brand-warning">
                    {audit.n_resolved_signals}/{audit.min_for_learned_weights}
                  </p>
                  <Text variant="tiny" className="mt-1">outcomes needed to activate</Text>
                </>
              )}
            </div>
            <div className="card p-4">
              <Eyebrow className="mb-1 block">Resolved Signals</Eyebrow>
              <p className="text-base font-bold t-num text-brand-light">{audit.n_resolved_signals}</p>
              <Text variant="tiny" className="mt-1">BUY outcomes tracked</Text>
            </div>
          </div>
        </section>
      )}

      {/* Loss analysis: factor scores wins vs losses */}
      {audit?.factor_analysis && audit.factor_analysis.wins.count + audit.factor_analysis.losses.count >= 4 && (
        <div className="mt-8">
          <h2 className="text-sm font-bold text-brand-light/60 mb-1 uppercase tracking-widest">Loss Diagnosis</h2>
          <p className="text-xs text-brand-light/40 mb-3">Average factor scores for winning vs losing signals — low score = weak signal component.</p>
          <div className="table-container">
            <table className="w-full text-left">
              <thead className="table-header">
                <tr>
                  <th className="table-cell">Factor</th>
                  <th className="table-cell text-brand-success">Winning signals ({audit.factor_analysis.wins.count})</th>
                  <th className="table-cell text-brand-danger">Losing signals ({audit.factor_analysis.losses.count})</th>
                  <th className="table-cell">Δ Gap</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-divider/40">
                {[
                  { label: 'Fundamental (F)', wval: audit.factor_analysis.wins.avg_f_score, lval: audit.factor_analysis.losses.avg_f_score },
                  { label: 'Technical (T)', wval: audit.factor_analysis.wins.avg_t_score, lval: audit.factor_analysis.losses.avg_t_score },
                  { label: 'Sentiment (S)', wval: audit.factor_analysis.wins.avg_s_score, lval: audit.factor_analysis.losses.avg_s_score },
                  { label: 'Confidence', wval: audit.factor_analysis.wins.avg_confidence, lval: audit.factor_analysis.losses.avg_confidence },
                  { label: 'Avg 7d Return', wval: audit.factor_analysis.wins.avg_7d_return, lval: audit.factor_analysis.losses.avg_7d_return },
                ].map(({ label, wval, lval }) => {
                  const gap = wval !== null && lval !== null ? wval - lval : null
                  return (
                    <tr key={label} className="table-row">
                      <td className="table-cell text-xs font-semibold text-brand-light">{label}</td>
                      <td className="table-cell font-mono text-xs text-brand-success">{wval !== null ? wval.toFixed(1) : '—'}</td>
                      <td className="table-cell font-mono text-xs text-brand-danger">{lval !== null ? lval.toFixed(1) : '—'}</td>
                      <td className={`table-cell font-mono text-xs font-semibold ${gap !== null && gap > 0 ? 'text-brand-success' : gap !== null && gap < 0 ? 'text-brand-danger' : 'text-brand-light/40'}`}>
                        {gap !== null ? `${gap > 0 ? '+' : ''}${gap.toFixed(1)}` : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-brand-light/30 mt-2">
            Large negative Δ gap = that factor is weaker in losing trades. Focus tuning on the factor with the biggest gap.
          </p>
        </div>
      )}

      {/* Confidence-bucketed win rate */}
      {resolved.length >= 4 && (() => {
        const buckets = [
          { label: '0–40%', min: 0, max: 40 },
          { label: '40–60%', min: 40, max: 60 },
          { label: '60–80%', min: 60, max: 80 },
          { label: '80–100%', min: 80, max: 101 },
        ]
        const bucketed = buckets.map((b) => {
          const inBucket = resolved.filter((r) => r.confidence >= b.min && r.confidence < b.max)
          const wins = inBucket.filter(isWin).length
          const wr = inBucket.length > 0 ? (wins / inBucket.length) * 100 : null
          return { ...b, count: inBucket.length, wr }
        }).filter(b => b.count > 0)
        if (bucketed.length < 2) return null
        return (
          <div className="mt-8">
            <h2 className="text-sm font-bold text-zinc-300 mb-3 uppercase tracking-widest">Win Rate by Confidence Band</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {bucketed.map((b) => (
                <div key={b.label} className="card p-4 text-center">
                  <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest mb-1">{b.label}</p>
                  <p className={`text-2xl font-bold font-mono ${b.wr !== null && b.wr >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                    {b.wr !== null ? `${b.wr.toFixed(0)}%` : '—'}
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">{b.count} signals</p>
                </div>
              ))}
            </div>
          </div>
        )
      })()}
    </Page>
  )
}

export default function SignalQualityPageWithBoundary() {
  return (
    <ErrorBoundary title="Signal Quality page unavailable">
      <SignalQualityPage />
    </ErrorBoundary>
  )
}
