import { useQuery } from '@tanstack/react-query'
import {
  ChevronDown,
  ChevronRight,
  ClipboardList,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import type React from 'react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Page, PageHeader, PageSection, CardGrid, ActionRow, InfoRow, Stack } from '@/components/ui/layout'
import { InfoTip, TextTip } from '../../components/Tooltip'
import { ROUTES } from '../../shared/routes'
import { SOURCE_COLORS, type SourceDetail, verdictColor } from './components'

interface AuditEntry {
  id: number
  symbol: string
  timestamp: string
  action: 'BUY' | 'SELL'
  shariah_status: 'COMPLIANT' | 'NON_COMPLIANT'
  business_activity: string | null
  ibkr_order_id: number | null
  data_source: string | null
  metrics: {
    debt_to_market_cap: number
    cash_to_market_cap: number
    impure_revenue_ratio: number
  }
  sources_detail: SourceDetail[]
}

const threshold = (val: number, limit: number) => ({
  label: `${(val * 100).toFixed(2)}%`,
  fail: val >= limit,
})

const AuditRow: React.FC<{ entry: AuditEntry }> = ({ entry: e }) => {
  const [open, setOpen] = useState(false)
  const compliant = e.shariah_status === 'COMPLIANT'
  const m = e.metrics
  const debt = threshold(m.debt_to_market_cap, 0.33)
  const cash = threshold(m.cash_to_market_cap, 0.33)
  const impure = threshold(m.impure_revenue_ratio, 0.05)

  return (
    <>
      {/* Mobile card */}
      <tr className="md:hidden">
        <td
          colSpan={7}
          className={`p-0 border-b border-brand-divider/40 ${!compliant ? 'bg-brand-danger/5' : ''}`}
        >
          <div className="p-4 cursor-pointer select-none" onClick={() => setOpen((o) => !o)}>
            <div className="flex items-center justify-between mb-1">
              <InfoRow className="">
                <span className="font-bold text-brand-light">{e.symbol}</span>
                <span
                  className={`text-[10px] font-bold px-1 rounded ${e.action === 'BUY' ? 'bg-brand-success/10 text-brand-success border border-brand-success/20' : 'bg-brand-danger/10 text-brand-danger border border-brand-danger/20'}`}
                >
                  {e.action}
                </span>
              </InfoRow>
              <InfoRow className="">
                <Badge
                  variant={compliant ? 'success' : 'destructive'}
                  className="h-5 px-1.5 gap-1 font-bold"
                >
                  {compliant ? <ShieldCheck size={11} /> : <ShieldAlert size={11} />}
                  {compliant ? 'HALAL' : 'BLOCKED'}
                </Badge>
                {open ? (
                  <ChevronDown size={14} className="text-brand-light/70" />
                ) : (
                  <ChevronRight size={14} className="text-brand-light/70" />
                )}
              </InfoRow>
            </div>
            <p className="text-[10px] text-brand-light/70 font-mono">
              {new Date(e.timestamp).toLocaleString()}
            </p>
            {open && (
              <div className="mt-3 space-y-2">
                {[
                  { label: 'Debt/MktCap', val: debt.label, fail: debt.fail },
                  { label: 'Cash/MktCap', val: cash.label, fail: cash.fail },
                  { label: 'Impure Rev', val: impure.label, fail: impure.fail },
                ].map((r) => (
                  <div
                    key={r.label}
                    className={`flex justify-between p-2 rounded-lg border text-xs ${r.fail ? 'bg-brand-danger/5 border-brand-danger/20 text-brand-danger' : 'bg-brand-surface/50 border-brand-divider/30 text-brand-light'}`}
                  >
                    <span className="text-[10px] font-bold uppercase tracking-wider opacity-70">
                      {r.label}
                    </span>
                    <span className="font-mono font-bold">{r.val}</span>
                  </div>
                ))}
                {e.ibkr_order_id && (
                  <p className="text-[10px] text-brand-light/70 font-mono mt-1 text-right">
                    IBKR: {e.ibkr_order_id}
                  </p>
                )}
              </div>
            )}
          </div>
        </td>
      </tr>

      {/* Desktop summary row */}
      <tr
        className={`hidden md:table-row table-row cursor-pointer select-none ${!compliant ? 'bg-brand-danger/5' : ''}`}
        onClick={() => setOpen((o) => !o)}
      >
        <td className="table-cell w-6">
          {open ? (
            <ChevronDown size={14} className="text-brand-light/70" />
          ) : (
            <ChevronRight size={14} className="text-brand-light/70" />
          )}
        </td>
        <td className="table-cell text-[11px] text-brand-light/70 font-mono whitespace-nowrap">
          {new Date(e.timestamp).toLocaleString()}
        </td>
        <td className="table-cell font-bold text-brand-light">{e.symbol}</td>
        <td className="table-cell">
          <span
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${e.action === 'BUY' ? 'bg-brand-success/10 text-brand-success border border-brand-success/20' : 'bg-brand-danger/10 text-brand-danger border border-brand-danger/20'}`}
          >
            {e.action}
          </span>
        </td>
        <td className="table-cell">
          <Badge
            variant={compliant ? 'success' : 'destructive'}
            className="h-5 px-1.5 gap-1 font-bold"
          >
            {compliant ? <ShieldCheck size={11} /> : <ShieldAlert size={11} />}
            {compliant ? 'HALAL' : 'BLOCKED'}
          </Badge>
        </td>
        <td className="table-cell text-xs text-brand-light/70 truncate max-w-[150px]">
          {e.business_activity ?? '—'}
        </td>
        <td className="table-cell text-[11px] font-mono text-brand-light/70">
          {e.ibkr_order_id ?? '—'}
        </td>
      </tr>

      {open && (
        <tr
          className={`hidden md:table-row ${!compliant ? 'bg-brand-danger/5' : 'bg-brand-surface/30'}`}
        >
          <td colSpan={7} className="px-8 pb-6 pt-2">
            <CardGrid className="gap-6 text-sm">
              <div className="space-y-2">
                <p className="text-brand-light/70 text-[10px] font-bold uppercase tracking-[0.15em] mb-3 opacity-80">
                  AAOIFI Ratios
                </p>
                <div
                  className={`flex justify-between items-center p-2.5 rounded-lg border ${debt.fail ? 'bg-brand-danger/5 border-brand-danger/20 text-brand-danger' : 'bg-brand-surface border-brand-divider/40 text-brand-light'}`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider opacity-70">
                    Debt / Mkt Cap
                  </span>
                  <span className="font-mono font-bold">{debt.label}</span>
                </div>
                <div
                  className={`flex justify-between items-center p-2.5 rounded-lg border ${cash.fail ? 'bg-brand-danger/5 border-brand-danger/20 text-brand-danger' : 'bg-brand-surface border-brand-divider/40 text-brand-light'}`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider opacity-70">
                    Cash / Mkt Cap
                  </span>
                  <span className="font-mono font-bold">{cash.label}</span>
                </div>
                <div
                  className={`flex justify-between items-center p-2.5 rounded-lg border ${impure.fail ? 'bg-brand-danger/5 border-brand-danger/20 text-brand-danger' : 'bg-brand-surface border-brand-divider/40 text-brand-light'}`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider opacity-70">
                    Impure Revenue
                  </span>
                  <span className="font-mono font-bold">{impure.label}</span>
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-brand-light/70 text-[10px] font-bold uppercase tracking-[0.15em] mb-3 opacity-80">
                  Classification
                </p>
                <div className="bg-brand-surface border border-brand-divider/40 p-2.5 rounded-lg text-brand-light">
                  <span className="text-brand-light/70 text-[10px] font-bold uppercase tracking-wider opacity-70">
                    Sector
                  </span>
                  <p className="font-medium mt-1 leading-relaxed">
                    {e.business_activity ?? 'Unknown'}
                  </p>
                </div>
                <div className="bg-brand-surface border border-brand-divider/40 p-2.5 rounded-lg text-brand-light">
                  <span className="text-brand-light/70 text-[10px] font-bold uppercase tracking-wider opacity-70">
                    Data Sources
                  </span>
                  {e.sources_detail && e.sources_detail.length > 0 ? (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {e.sources_detail.map((s, i) => (
                        <div
                          key={i}
                          title={s.note ?? ''}
                          className={`flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-[10px] ${SOURCE_COLORS[s.source] ?? 'bg-brand-base text-brand-light/70 border-brand-divider'}`}
                        >
                          <span className="font-bold">{s.source}</span>
                          <span className={`font-black ${verdictColor(s.verdict)}`}>
                            {s.verdict}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="font-medium mt-1">{e.data_source ?? 'Unknown'}</p>
                  )}
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-brand-light/70 text-[10px] font-bold uppercase tracking-[0.15em] mb-3 opacity-80">
                  Decision
                </p>
                <div
                  className={`p-3 rounded-lg border ${compliant ? 'bg-brand-success/5 border-brand-success/20 text-brand-success' : 'bg-brand-danger/5 border-brand-danger/20 text-brand-danger'}`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider opacity-70">
                    Verdict
                  </span>
                  <p className="font-bold mt-1 text-sm">
                    {compliant ? 'HALAL CERTIFIED — Order Submitted' : 'BLOCKED — Did Not Trade'}
                  </p>
                </div>
                {e.ibkr_order_id && (
                  <div className="bg-brand-surface border border-brand-divider/40 p-2.5 rounded-lg text-brand-light">
                    <span className="text-brand-light/70 text-[10px] font-bold uppercase tracking-wider opacity-70">
                      IBKR Order ID
                    </span>
                    <p className="font-mono font-medium mt-1">{e.ibkr_order_id}</p>
                  </div>
                )}
              </div>
            </CardGrid>
          </td>
        </tr>
      )}
    </>
  )
}

const AuditPage = () => {
  const [filter, setFilter] = useState<'ALL' | 'COMPLIANT' | 'NON_COMPLIANT'>('ALL')

  const {
    data: entries = [],
    isFetching,
    refetch,
  } = useQuery<AuditEntry[]>({
    queryKey: ['audit'],
    queryFn: () => fetch(ROUTES.COMPLIANCE_AUDIT).then((r) => r.json()),
  })

  const filtered = filter === 'ALL' ? entries : entries.filter((e) => e.shariah_status === filter)

  return (
    <Page>
      <PageHeader>
        <div>
          <h1 className="heading-1">
            <ClipboardList className="text-brand-primary" />
            Shariah Audit Trail
          </h1>
          <p className="text-brand-light/70">Click any row to see full evidence</p>
        </div>
        <ActionRow className="flex-wrap">
          <div className="flex gap-1 bg-brand-elevated/50 p-1 rounded-lg border border-brand-divider">
            {(['ALL', 'COMPLIANT', 'NON_COMPLIANT'] as const).map((f) => (
              <Button
                key={f}
                size="xs"
                variant={filter === f ? 'secondary' : 'ghost'}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-all ${
                  filter === f
                    ? 'bg-brand-primary/10 text-brand-primary'
                    : 'text-brand-light/70 hover:text-brand-light'
                }`}
              >
                {f.replace('_', ' ')}
              </Button>
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            className="border-brand-divider hover:border-brand-primary/50 hover:bg-brand-primary/5 transition-all gap-2"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
            Refresh
          </Button>
        </ActionRow>
      </PageHeader>

      <div className="table-container">
        <table className="w-full text-left">
          <thead className="table-header">
            <tr>
              <th className="table-cell w-6" />
              <th className="table-cell">Time</th>
              <th className="table-cell">Symbol</th>
              <th className="table-cell">Action</th>
              <th className="table-cell">
                <TextTip text="The final decision from the Shariah Guard. HALAL means the trade passed all checks and was sent to IBKR. BLOCKED means a violation was found.">
                  Verdict
                </TextTip>
              </th>
              <th className="table-cell">Sector</th>
              <th className="table-cell">
                <TextTip text="The unique order ID from Interactive Brokers. This proves the trade was actually executed on the exchange.">
                  IBKR Order
                </TextTip>
              </th>
            </tr>
          </thead>
          <tbody>
            {isFetching && entries.length === 0 ? (
              <tr>
                <td colSpan={7} className="table-cell text-center text-brand-light/70 italic py-8">
                  Loading...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="table-cell text-center text-brand-light/70 italic py-8">
                  No audit records found
                </td>
              </tr>
            ) : (
              filtered.map((e) => <AuditRow key={e.id} entry={e} />)
            )}
          </tbody>
        </table>
      </div>
    </Page>
  )
}

import { ErrorBoundary } from '../../components/ErrorBoundary'

export default function AuditPageWithBoundary() {
  return (
    <ErrorBoundary title="Audit log unavailable">
      <AuditPage />
    </ErrorBoundary>
  )
}
