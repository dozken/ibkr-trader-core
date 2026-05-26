import { useQuery } from '@tanstack/react-query'
import { AIModuleGate } from './AIModuleGate'
import { AlertTriangle, Clock } from 'lucide-react'
import React, { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Page, PageHeader, InfoRow } from '@/components/ui/layout'
import { ErrorBoundary } from '../../components/ErrorBoundary'
import { ROUTES } from '../../shared/routes'

interface SignalLogRow {
  symbol: string
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  f_score: number | null
  t_score: number | null
  s_score: number | null
  signal_price: number | null
  outcome_7d_pct: number | null
  outcome_30d_pct: number | null
  created_at: string
}

type ActionFilter = 'ALL' | 'BUY' | 'SELL' | 'HOLD'

function actionBadgeVariant(action: 'BUY' | 'SELL' | 'HOLD') {
  if (action === 'BUY') return 'success' as const
  if (action === 'SELL') return 'danger' as const
  return 'secondary' as const
}

function OutcomeCell({ value, action }: { value: number | null; action: 'BUY' | 'SELL' | 'HOLD' }) {
  if (value === null)
    return <span className="inline-flex items-center gap-1 text-zinc-500 text-xs"><Clock size={10} />—</span>
  const win = action === 'BUY' ? value > 0 : action === 'SELL' ? value < 0 : null
  const cls = win === null ? 'text-zinc-400' : win ? 'text-green-400' : 'text-red-400'
  return <span className={`font-mono text-xs font-semibold ${cls}`}>{value >= 0 ? '+' : ''}{value.toFixed(2)}%</span>
}

function ScoreCell({ value }: { value: number | null }) {
  if (value === null || value === 0) return <span className="text-zinc-600 text-xs">—</span>
  const cls = value >= 60 ? 'text-green-400' : value >= 40 ? 'text-yellow-400' : 'text-red-400'
  return <span className={`font-mono text-xs ${cls}`}>{value.toFixed(0)}</span>
}

const SignalLogPage: React.FC = () => {
  const [actionFilter, setActionFilter] = useState<ActionFilter>('ALL')
  const [symbolFilter, setSymbolFilter] = useState('')

  const { data = [], isLoading, isError } = useQuery<SignalLogRow[]>({
    queryKey: ['signal-log'],
    queryFn: () => fetch(ROUTES.AI_SIGNAL_LOG).then((r) => r.json()),
    staleTime: 60_000,
  })

  const filtered = data.filter((row) => {
    if (actionFilter !== 'ALL' && row.action !== actionFilter) return false
    if (symbolFilter && !row.symbol.toLowerCase().includes(symbolFilter.toLowerCase())) return false
    return true
  })

  return (
    <Page>
      <PageHeader>
        <div className="flex flex-col gap-1">
          <InfoRow>
            <h1 className="heading-1 mb-0">Signal Log</h1>
          </InfoRow>
          <p className="text-zinc-500 text-sm">
            Raw chronological record of every AI signal — sub-scores, entry price, outcomes.
          </p>
        </div>
      </PageHeader>

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
            onClick={() => { setActionFilter('ALL'); setSymbolFilter('') }}
            className="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors uppercase tracking-wider"
          >
            Clear
          </button>
        )}
        <span className="text-xs text-zinc-500 ml-auto">{filtered.length} signals</span>
      </div>

      <div className="table-container">
        {isLoading ? (
          <div className="p-12 text-center text-zinc-500 text-sm">Loading…</div>
        ) : isError ? (
          <div className="p-12 text-center">
            <AlertTriangle size={24} className="mx-auto mb-2 text-brand-warning opacity-50" />
            <p className="text-zinc-500 text-sm">Failed to load signal log.</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-zinc-500 text-sm italic">No signals match your filter.</div>
        ) : (
          <table className="w-full text-left">
            <thead className="table-header">
              <tr>
                <th className="table-cell">Symbol</th>
                <th className="table-cell">Action</th>
                <th className="table-cell">Conf</th>
                <th className="table-cell text-center" title="Fundamental score">F</th>
                <th className="table-cell text-center" title="Technical score">T</th>
                <th className="table-cell text-center" title="Sentiment score">S</th>
                <th className="table-cell">Entry $</th>
                <th className="table-cell">7d</th>
                <th className="table-cell">30d</th>
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
                  <td className="table-cell font-mono text-xs text-zinc-300">{row.confidence.toFixed(0)}%</td>
                  <td className="table-cell text-center"><ScoreCell value={row.f_score} /></td>
                  <td className="table-cell text-center"><ScoreCell value={row.t_score} /></td>
                  <td className="table-cell text-center"><ScoreCell value={row.s_score} /></td>
                  <td className="table-cell font-mono text-xs text-zinc-400">
                    {row.signal_price != null ? `$${row.signal_price.toFixed(2)}` : '—'}
                  </td>
                  <td className="table-cell"><OutcomeCell value={row.outcome_7d_pct} action={row.action} /></td>
                  <td className="table-cell"><OutcomeCell value={row.outcome_30d_pct} action={row.action} /></td>
                  <td className="table-cell text-xs text-zinc-500 font-mono">
                    {new Date(row.created_at).toLocaleDateString(undefined, {
                      month: 'short', day: 'numeric',
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Page>
  )
}

export default function SignalLogPageWithBoundary() {
  return (
    <AIModuleGate pageTitle="Signal Log">
      <ErrorBoundary title="Signal Log unavailable">
        <SignalLogPage />
      </ErrorBoundary>
    </AIModuleGate>
  )
}
