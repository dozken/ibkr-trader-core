import { ErrorBoundary } from '../../components/ErrorBoundary'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { AlertCircle, Coins, ExternalLink, Heart, Info, RefreshCw, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Page, PageHeader, PageSection, CardGrid, ActionRow, InfoRow, Stack } from '@/components/ui/layout'
import { Heading } from '@/components/ui/primitives'
import { Text } from '@/components/ui/text'
import { Input } from '@/components/ui/input'
import { InfoTip, TextTip } from '../../components/Tooltip'
import { ROUTES, withAccount } from '../../shared/routes'
import { useAccount } from '../trading/context/AccountContext'

interface ZakatResult {
  zakatable_assets_value: number
  rate: number
  nisab: number
  zakat_due: number
  below_nisab: boolean
}

interface Position {
  symbol: string
  quantity: number
  avg_cost: number
  market_value: number
  unrealized_pnl: number
}

interface PortfolioValue {
  available_funds: number
  connected: boolean
}

interface PositionComplianceRecord {
  symbol: string
  shariah_status: string
  metrics: {
    impure_revenue_pct: number
    company_name?: string
  }
  timestamp: string
}

interface DividendData {
  symbol: string
  past12_per_share: number | null
  quantity: number
  total_received: number | null
}

interface PurificationRecord {
  id: number
  symbol: string
  dividend_amount: number
  purification_amount: number
  donation_receipt_link: string | null
  timestamp: string
}

interface PurificationLiability {
  symbol: string
  realized_profit: number
  impure_revenue_pct: number
  purification_due: number
  purified_already: number
  remaining_liability: number
}

interface HawlStatus {
  hawl_start: string | null
  hawl_end: string | null
  days_elapsed: number
  days_remaining: number
  is_due: boolean
  is_overdue: boolean
  above_nisab: boolean
  nisab_usd: number
  portfolio_value: number
  lunar_year_days: number
  pct_complete: number
}

const fmt = (n: number) =>
  n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const pct = (n: number) => `${(n * 100).toFixed(2)}%`

function ZakatPage() {
  const qc = useQueryClient()
  const { selectedAccountId } = useAccount()

  // ── Portfolio data ──────────────────────────────────────────────────────────
  const { data: portfolioValue } = useQuery<PortfolioValue>({
    queryKey: ['portfolio-value', selectedAccountId],
    queryFn: () => fetch(withAccount(ROUTES.PORTFOLIO_VALUE, selectedAccountId)).then((r) => r.json()),
  })

  const { data: positions = [] } = useQuery<Position[]>({
    queryKey: ['portfolio-positions', selectedAccountId],
    queryFn: () => fetch(withAccount(ROUTES.PORTFOLIO_POSITIONS, selectedAccountId)).then((r) => r.json()),
  })

  const { data: compliancePositions = [] } = useQuery<PositionComplianceRecord[]>({
    queryKey: ['compliance-positions'],
    queryFn: () => fetch(ROUTES.COMPLIANCE_POSITIONS).then((r) => r.json()),
  })

  // ── IBKR dividend data ─────────────────────────────────────────────────────
  const { data: ibkrDividends = [], isFetching: estimatesLoading } = useQuery<DividendData[]>({
    queryKey: ['portfolio-dividends'],
    queryFn: () => fetch(ROUTES.PORTFOLIO_DIVIDENDS).then((r) => r.json()),
    enabled: !!portfolioValue?.connected,
    staleTime: 1000 * 60 * 60,
  })

  // Auto-fill dividend inputs from IBKR data (only if user hasn't typed yet)
  useEffect(() => {
    if (!ibkrDividends.length) return
    setDividends((prev) => {
      const next = { ...prev }
      for (const d of ibkrDividends) {
        if (!next[d.symbol] && d.total_received != null && d.total_received > 0) {
          next[d.symbol] = d.total_received.toFixed(2)
        }
      }
      return next
    })
    setEstimatedSymbols(
      ibkrDividends
        .filter((d) => d.total_received != null && d.total_received > 0)
        .map((d) => d.symbol),
    )
  }, [ibkrDividends])

  // ── Zakat ──────────────────────────────────────────────────────────────────
  const [zakatResult, setZakatResult] = useState<ZakatResult | null>(null)
  const [zakatError, setZakatError] = useState<string | null>(null)
  const [zakatLoading, setZakatLoading] = useState(false)

  const positionsTotal = positions.reduce((s, p) => s + p.market_value, 0)
  const cash = portfolioValue?.available_funds ?? 0
  const zakatableTotal = cash + positionsTotal

  const calcZakat = async () => {
    setZakatLoading(true)
    setZakatError(null)
    try {
      const res = await fetch(ROUTES.ZAKAT_CALCULATE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zakatable_assets_value: zakatableTotal }),
      })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      setZakatResult(await res.json())
    } catch (e) {
      setZakatError(e instanceof Error ? e.message : 'Failed to calculate')
    } finally {
      setZakatLoading(false)
    }
  }

  // ── Per-position purification ──────────────────────────────────────────────
  const [dividends, setDividends] = useState<Record<string, string>>({})
  const [estimatedSymbols, setEstimatedSymbols] = useState<string[]>([]) // symbols where value is estimated
  const [recordingSymbol, setRecordingSymbol] = useState<string | null>(null)
  const [receiptLinks, setReceiptLinks] = useState<Record<string, string>>({})

  const setDividend = (symbol: string, val: string) =>
    setDividends((d) => ({ ...d, [symbol]: val }))
  const setReceiptLink = (symbol: string, val: string) =>
    setReceiptLinks((l) => ({ ...l, [symbol]: val }))

  const recordMutation = useMutation({
    mutationFn: (row: {
      symbol: string
      dividend: number
      purification: number
      receipt: string
    }) =>
      fetch(ROUTES.ZAKAT_PURIFICATION_RECORD, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: row.symbol,
          dividend_amount: row.dividend,
          purification_amount: row.purification,
          donation_receipt_link: row.receipt || null,
        }),
      }).then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}))
          throw new Error(body.detail || 'Failed to record purification donation')
        }
        return r.json()
      }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['purification-history'] })
      qc.invalidateQueries({ queryKey: ['purification-liabilities'] })
      setDividends((d) => {
        const n = { ...d }
        delete n[vars.symbol]
        return n
      })
      setReceiptLinks((l) => {
        const n = { ...l }
        delete n[vars.symbol]
        return n
      })
      setRecordingSymbol(null)
      toast.success(`Purification of ${vars.symbol} recorded successfully`)
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Failed to record purification donation')
    },
  })

  // ── History ────────────────────────────────────────────────────────────────
  const {
    data: history = [],
    isFetching,
    refetch,
  } = useQuery<PurificationRecord[]>({
    queryKey: ['purification-history'],
    queryFn: () => fetch(ROUTES.ZAKAT_PURIFICATION_HISTORY).then((r) => r.json()),
  })

  const { data: liabilities = [] } = useQuery<PurificationLiability[]>({
    queryKey: ['purification-liabilities'],
    queryFn: () => fetch(ROUTES.ZAKAT_PURIFICATION_LIABILITIES).then((r) => r.json()),
  })

  const { data: hawl, refetch: refetchHawl } = useQuery<HawlStatus>({
    queryKey: ['zakat-hawl'],
    queryFn: () => fetch(ROUTES.ZAKAT_HAWL).then((r) => r.json()),
    refetchInterval: 60_000,
  })

  const hawlResetMutation = useMutation({
    mutationFn: () =>
      fetch(ROUTES.ZAKAT_HAWL_RESET, { method: 'POST' }).then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}))
          throw new Error(body.detail || 'Failed to reset Hawl period')
        }
        return r.json()
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['zakat-hawl'] })
      toast.success('Zakat Hawl period reset successfully')
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Failed to reset Zakat Hawl')
    },
  })

  const [historySymbolFilter, setHistorySymbolFilter] = useState('')

  const totalPurified = history.reduce((s, r) => s + r.purification_amount, 0)
  const totalLiability = liabilities.reduce((s, l) => s + l.remaining_liability, 0)
  const filteredHistory = historySymbolFilter
    ? history.filter((r) => r.symbol.includes(historySymbolFilter.toUpperCase()))
    : history

  // build map: symbol → compliance record
  const _complianceMap = Object.fromEntries(compliancePositions.map((c) => [c.symbol, c]))

  // rows = all compliance positions (screened holdings)
  const purRows = compliancePositions.map((c) => {
    const pos = positions.find((p) => p.symbol === c.symbol)
    const dividend = parseFloat(dividends[c.symbol] ?? '') || 0
    const impurePct = c.metrics.impure_revenue_pct ?? 0
    const purificationAmount = dividend * impurePct
    return { ...c, pos, dividend, impurePct, purificationAmount }
  })

  return (
    <Page>
      <PageHeader>
        <Stack gap="xs">
          <Heading icon={Coins} iconTone="warning">Zakat &amp; Purification</Heading>
          <Text tone="muted">
            Auto-calculated from your portfolio. Enter dividends received to get purification
            amounts.
          </Text>
        </Stack>
        <div className="bg-brand-surface border border-brand-divider rounded-lg px-4 py-3 text-sm flex gap-6">
          <div>
            <InfoRow className="">
              <TextTip text="Sum of all purification (Tazkiyah) payments you have recorded in the app this year.">
                <p className="text-brand-light/70 text-xs">Total Purified YTD</p>
              </TextTip>
            </InfoRow>
            <p className="font-bold text-brand-success">${fmt(totalPurified)}</p>
          </div>
          <div>
            <InfoRow className="">
              <TextTip text="The total value of your cash and holdings that may be subject to Zakat. Zakat is only due if this stays above the Nisab for a full lunar year (Hawl).">
                <p className="text-brand-light/70 text-xs">Zakatable Assets</p>
              </TextTip>
            </InfoRow>
            <p className="font-bold text-brand-warning">${fmt(zakatableTotal)}</p>
          </div>
        </div>
      </PageHeader>

      {/* ── Hawl Status ──────────────────────────────────────────────────────── */}
      {hawl && (
        <div className={`mb-6 rounded-xl border p-5 ${
          hawl.is_due
            ? 'border-brand-danger bg-brand-danger/10'
            : hawl.hawl_start
              ? 'border-brand-warning/50 bg-brand-warning/5'
              : 'border-brand-divider bg-brand-surface'
        }`}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className={`text-2xl ${hawl.is_due ? 'animate-pulse' : ''}`}>
                {hawl.is_due ? '🕌' : hawl.hawl_start ? '⏳' : '🌙'}
              </div>
              <div>
                <h2 className={`font-bold text-sm uppercase tracking-widest mb-1 ${
                  hawl.is_due ? 'text-brand-danger' : hawl.hawl_start ? 'text-brand-warning' : 'text-brand-light/70'
                }`}>
                  {hawl.is_due
                    ? 'ZAKAT IS DUE — Pay Now'
                    : hawl.hawl_start
                      ? 'Hawl in Progress — Counting Toward Zakat Due Date'
                      : hawl.above_nisab
                        ? 'Above Nisab — Hawl Starting'
                        : 'Below Nisab — No Zakat Due Yet'}
                </h2>
                {hawl.hawl_start && (
                  <p className="text-xs text-brand-light/70">
                    Hawl started: <strong className="text-brand-light">{hawl.hawl_start}</strong>
                    {' · '}
                    {hawl.is_due
                      ? <span className="text-brand-danger font-bold">Due date passed ({hawl.hawl_end})</span>
                      : <>Due: <strong className="text-brand-warning">{hawl.hawl_end}</strong> · <strong className="text-brand-light">{hawl.days_remaining} days remaining</strong></>
                    }
                  </p>
                )}
                {!hawl.hawl_start && hawl.above_nisab && (
                  <p className="text-xs text-brand-light/70">
                    Portfolio ${hawl.portfolio_value.toLocaleString(undefined, {maximumFractionDigits: 0})} above Nisab ${hawl.nisab_usd.toLocaleString(undefined, {maximumFractionDigits: 0})}.
                    Hawl clock starts today and runs for 354 days.
                  </p>
                )}
                {!hawl.above_nisab && (
                  <p className="text-xs text-brand-light/70">
                    Portfolio ${hawl.portfolio_value.toLocaleString(undefined, {maximumFractionDigits: 0})} · Nisab threshold: ${hawl.nisab_usd.toLocaleString(undefined, {maximumFractionDigits: 0})} (85g gold).
                    Hawl begins once portfolio stays above Nisab.
                  </p>
                )}
                {hawl && (
                  <div className="mt-3 space-y-1.5">
                    <div className="flex justify-between text-xs text-brand-light/60">
                      <span>Portfolio vs Nisab</span>
                      <span className="font-mono">
                        ${hawl.portfolio_value?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? '—'}
                        {' / '}
                        ${hawl.nisab_usd?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? '—'}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-brand-divider/30 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${hawl.above_nisab ? 'bg-brand-success' : 'bg-brand-warning'}`}
                        style={{ width: `${Math.min(((hawl.portfolio_value ?? 0) / (hawl.nisab_usd ?? 1)) * 100, 100)}%` }}
                      />
                    </div>
                    {!hawl.above_nisab && (
                      <p className="text-[11px] text-brand-warning">
                        ${((hawl.nisab_usd ?? 0) - (hawl.portfolio_value ?? 0)).toLocaleString(undefined, { maximumFractionDigits: 0 })} more to reach Nisab
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Progress bar + action */}
            <div className="flex flex-col items-end gap-2 shrink-0 min-w-[180px]">
              {hawl.hawl_start && (
                <>
                  <div className="w-full">
                    <div className="flex justify-between text-[10px] text-brand-light/50 mb-1">
                      <span>{hawl.days_elapsed}d elapsed</span>
                      <span>{hawl.pct_complete}%</span>
                    </div>
                    <div className="h-2 bg-brand-divider/40 rounded-full overflow-hidden w-full">
                      <div
                        className={`h-full rounded-full transition-all ${hawl.is_due ? 'bg-brand-danger' : 'bg-brand-warning'}`}
                        style={{ width: `${hawl.pct_complete}%` }}
                      />
                    </div>
                    <div className="text-[10px] text-brand-light/50 mt-1 text-right">
                      of {hawl.lunar_year_days} days (1 lunar year)
                    </div>
                  </div>
                  {hawl.is_due && (
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => hawlResetMutation.mutate()}
                      disabled={hawlResetMutation.isPending}
                      className="text-xs"
                    >
                      Mark Zakat as Paid — Reset Hawl
                    </Button>
                  )}
                </>
              )}
              {!hawl.hawl_start && (
                <div className="text-right text-xs text-brand-light/50">
                  <div className="font-mono text-brand-light/30 text-[10px]">354 days needed</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Zakat ────────────────────────────────────────────────────────────── */}
      <PageSection className="card">
        <div className="flex items-center justify-between mb-4">
          <InfoRow className="">
            <Zap size={16} className="text-brand-warning" />
            <h2 className="font-semibold">Zakat Calculator</h2>
          </InfoRow>
          <Button
            onClick={calcZakat}
            disabled={zakatLoading || zakatableTotal === 0}
            className="px-4"
          >
            {zakatLoading ? (
              <RefreshCw size={14} className="animate-spin" />
            ) : (
              'Calculate from Portfolio'
            )}
          </Button>
        </div>

        <div className="flex items-start gap-1 mb-4 text-xs text-brand-light/70">
          <Info size={12} className="mt-0.5 shrink-0" />
          <span>
            Hawl (lunar year) obligation: zakat is only due on assets held for a full lunar year
            (~354 days). Verify your holding period before paying.
          </span>
        </div>

        {/* Portfolio breakdown */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4 text-sm">
          <div className="bg-brand-base rounded p-3">
            <InfoRow className=" mb-1">
              <TextTip text="Liquid cash sitting in your IBKR account ready to be traded or withdrawn.">
                <p className="text-brand-light/70 text-xs">Cash / Available Funds</p>
              </TextTip>
            </InfoRow>
            <p className="font-mono font-bold">${fmt(cash)}</p>
            {!portfolioValue?.connected && (
              <p className="text-xs text-brand-warning mt-1">Not connected to IBKR</p>
            )}
          </div>
          <div className="bg-brand-base rounded p-3">
            <InfoRow className=" mb-1">
              <TextTip text="The current total value of all your open stock positions.">
                <p className="text-brand-light/70 text-xs">Holdings Market Value</p>
              </TextTip>
            </InfoRow>
            <p className="font-mono font-bold">${fmt(positionsTotal)}</p>
            <p className="text-xs text-brand-light/70 mt-1">
              {positions.length} position{positions.length !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="bg-brand-base rounded p-3 border border-brand-warning/30">
            <InfoRow className=" mb-1">
              <TextTip text="Sum of Cash + Holdings. This is the amount used to calculate your Zakat obligation.">
                <p className="text-brand-light/70 text-xs">Total Zakatable</p>
              </TextTip>
            </InfoRow>
            <p className="font-mono font-bold text-brand-warning">${fmt(zakatableTotal)}</p>
          </div>
        </div>

        {zakatError && <p className="text-brand-danger text-sm mb-3">{zakatError}</p>}

        {zakatResult && (
          <div className="space-y-2 text-sm border-t border-brand-divider pt-4">
            <div className="flex justify-between p-2 rounded bg-brand-base">
              <span className="text-brand-light/70">Nisab (live gold price)</span>
              <span className="font-mono">${fmt(zakatResult.nisab)}</span>
            </div>
            {zakatResult.below_nisab ? (
              <div className="p-3 rounded bg-brand-primary/10 text-brand-primary text-center font-medium">
                Below nisab threshold — no zakat due
              </div>
            ) : (
              <div className="flex justify-between p-3 rounded bg-brand-warning/10 border border-brand-warning/30">
                <span className="font-semibold text-brand-warning">Zakat Due (2.5%)</span>
                <span className="font-mono font-bold text-brand-warning text-xl">
                  ${fmt(zakatResult.zakat_due)}
                </span>
              </div>
            )}
          </div>
        )}
      </PageSection>

      {/* ── Per-position Purification ─────────────────────────────────────────── */}
      <div className="mb-8">
        <InfoRow className=" mb-2">
          <Heart size={16} className="text-brand-danger" />
          <h2 className="font-semibold">Purification by Position</h2>
        </InfoRow>
        <div className="flex items-start gap-1 mb-4 text-xs text-brand-light/70">
          <Info size={12} className="mt-0.5 shrink-0" />
          <span>
            Impure % auto-filled from compliance data. Dividend amounts pulled from IBKR (past 12
            months per share × quantity).{' '}
            {portfolioValue?.connected ? (
              <strong className="text-brand-success">Connected — values from IBKR</strong>
            ) : (
              <strong className="text-brand-warning">
                Not connected — connect IBKR to auto-fill dividends
              </strong>
            )}
            . Always verify against{' '}
            <strong className="text-brand-light">Account Management → Reports → Activity</strong>.
          </span>
        </div>
        {estimatesLoading && (
          <InfoRow className=" text-xs text-brand-light/70 mb-3">
            <RefreshCw size={12} className="animate-spin" /> Fetching dividend data from IBKR…
          </InfoRow>
        )}

        {compliancePositions.length === 0 ? (
          <div className="card text-center text-brand-light/70 italic py-8">
            No screened positions found. Screen your holdings on the Compliance page first.
          </div>
        ) : (
          <div className="table-container">
            <table className="w-full text-left">
              <thead className="table-header">
                <tr>
                  <th className="table-cell">Symbol</th>
                  <th className="table-cell">Status</th>
                  <th className="table-cell">
                    <TextTip text="The percentage of this company's revenue that comes from non-compliant sources (e.g. interest). This portion of your dividends must be purified.">
                      Impure %
                    </TextTip>
                  </th>
                  <th className="table-cell">Market Value</th>
                  <th className="table-cell">
                    <TextTip text="The total cash dividend you received for this position. This is used to calculate the dollar amount to donate.">
                      Dividend Received
                    </TextTip>
                  </th>
                  <th className="table-cell">
                    <TextTip text="Calculated as (Dividend Received × Impure %). This is the 'Tazkiyah' amount you should donate to charity.">
                      Purification Due
                    </TextTip>
                  </th>
                  <th className="table-cell">Action</th>
                </tr>
              </thead>
              <tbody>
                {purRows.map((row) => {
                  const compliant = row.shariah_status === 'COMPLIANT'
                  const hasDividend = row.dividend > 0
                  const isRecording = recordingSymbol === row.symbol

                  return (
                    <tr key={row.symbol} className="table-row">
                      <td className="table-cell font-bold">{row.symbol}</td>
                      <td className="table-cell">
                        <span
                          className={`text-xs font-medium ${compliant ? 'text-brand-success' : 'text-brand-danger'}`}
                        >
                          {row.shariah_status}
                        </span>
                      </td>
                      <td className="table-cell font-mono text-sm">
                        {row.impurePct > 0 ? (
                          <span className="text-brand-warning">{pct(row.impurePct)}</span>
                        ) : (
                          <span className="text-brand-success">0.00%</span>
                        )}
                      </td>
                      <td className="table-cell font-mono text-sm text-brand-light/70">
                        {row.pos ? `$${fmt(row.pos.market_value)}` : '—'}
                      </td>
                      <td className="table-cell">
                        <div className="flex flex-col gap-1">
                          <div className="relative">
                            <Input
                              type="number"
                              placeholder="0.00"
                              value={dividends[row.symbol] ?? ''}
                              onChange={(e) => {
                                setDividend(row.symbol, e.target.value)
                                setEstimatedSymbols((s) => s.filter((x) => x !== row.symbol))
                              }}
                              className="w-32 h-8 text-sm font-mono"
                              min="0"
                              step="0.01"
                            />
                          </div>

                          {estimatedSymbols.includes(row.symbol) && (
                            <span className="flex items-center gap-1 text-[10px] text-brand-warning">
                              <AlertCircle size={10} /> est. — verify in IBKR
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="table-cell font-mono font-semibold">
                        {hasDividend ? (
                          <span
                            className={
                              row.purificationAmount > 0
                                ? 'text-brand-danger'
                                : 'text-brand-success'
                            }
                          >
                            ${fmt(row.purificationAmount)}
                          </span>
                        ) : (
                          <span className="text-brand-light/70">—</span>
                        )}
                      </td>
                      <td className="table-cell">
                        {hasDividend &&
                          row.purificationAmount > 0 &&
                          (isRecording ? (
                            <InfoRow className="">
                              <Input
                                type="url"
                                placeholder="Receipt URL (optional)"
                                value={receiptLinks[row.symbol] ?? ''}
                                onChange={(e) => setReceiptLink(row.symbol, e.target.value)}
                                className="text-xs w-40 font-mono h-8"
                              />
                              <Button
                                size="sm"
                                onClick={() =>
                                  recordMutation.mutate({
                                    symbol: row.symbol,
                                    dividend: row.dividend,
                                    purification: row.purificationAmount,
                                    receipt: receiptLinks[row.symbol] ?? '',
                                  })
                                }
                                disabled={recordMutation.isPending}
                                className="text-xs"
                              >
                                {recordMutation.isPending ? (
                                  <RefreshCw size={12} className="animate-spin" />
                                ) : (
                                  'Save'
                                )}
                              </Button>
                              <Button
                                variant="ghost"
                                size="xs"
                                onClick={() => setRecordingSymbol(null)}
                                className="text-brand-light/70 hover:text-brand-danger transition-colors font-bold uppercase tracking-tight"
                              >
                                Cancel
                              </Button>
                            </InfoRow>
                          ) : (
                            <Button
                              size="sm"
                              onClick={() => setRecordingSymbol(row.symbol)}
                              className="text-xs"
                            >
                              Record
                            </Button>
                          ))}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Realized Gains Purification ─────────────────────────────────────── */}
      <div className="mb-8">
        <InfoRow className=" mb-2">
          <Heart size={16} className="text-brand-primary" />
          <h2 className="font-semibold">Realized Capital Gains Purification</h2>
        </InfoRow>
        <div className="flex items-start gap-1 mb-4 text-xs text-brand-light/70">
          <Info size={12} className="mt-0.5 shrink-0" />
          <span>
            Accumulated liability from closed trades. Calculated as (Realized Profit × Impure
            Revenue %). This ensures that even the tiny portion of growth derived from non-compliant
            income is purified.
          </span>
        </div>

        {liabilities.length === 0 ? (
          <div className="card text-center text-brand-light/70 italic py-8">
            No realized gains found in your trade history.
          </div>
        ) : (
          <div className="table-container">
            <table className="w-full text-left">
              <thead className="table-header">
                <tr>
                  <th className="table-cell">Symbol</th>
                  <th className="table-cell">
                    <TextTip text="The net profit you made from selling this stock.">
                      Realized Profit
                    </TextTip>
                  </th>
                  <th className="table-cell">Impure %</th>
                  <th className="table-cell">
                    <TextTip text="Even for capital gains, we purify the portion of growth that may be attributed to impure income while you held the stock.">
                      Purification Due
                    </TextTip>
                  </th>
                  <th className="table-cell">Already Paid</th>
                  <th className="table-cell">Remaining</th>
                  <th className="table-cell">Action</th>
                </tr>
              </thead>
              <tbody>
                {liabilities.map((row) => {
                  const isRecording = recordingSymbol === `liability-${row.symbol}`
                  return (
                    <tr key={row.symbol} className="table-row">
                      <td className="table-cell font-bold">{row.symbol}</td>
                      <td className="table-cell font-mono text-sm text-brand-success">
                        ${fmt(row.realized_profit)}
                      </td>
                      <td className="table-cell font-mono text-sm text-brand-warning">
                        {pct(row.impure_revenue_pct)}
                      </td>
                      <td className="table-cell font-mono text-sm">${fmt(row.purification_due)}</td>
                      <td className="table-cell font-mono text-sm text-brand-success">
                        ${fmt(row.purified_already)}
                      </td>
                      <td
                        className={`table-cell font-mono font-bold ${row.remaining_liability > 0 ? 'text-brand-danger' : 'text-brand-success'}`}
                      >
                        ${fmt(row.remaining_liability)}
                      </td>
                      <td className="table-cell">
                        {row.remaining_liability > 0 &&
                          (isRecording ? (
                            <InfoRow className="">
                              <Input
                                type="url"
                                placeholder="Receipt URL (optional)"
                                value={receiptLinks[row.symbol] ?? ''}
                                onChange={(e) => setReceiptLink(row.symbol, e.target.value)}
                                className="text-xs w-40 font-mono h-8"
                              />
                              <Button
                                size="sm"
                                onClick={() =>
                                  recordMutation.mutate({
                                    symbol: row.symbol,
                                    dividend: 0,
                                    purification: row.remaining_liability,
                                    receipt: receiptLinks[row.symbol] ?? '',
                                  })
                                }
                                disabled={recordMutation.isPending}
                                className="text-xs"
                              >
                                {recordMutation.isPending ? (
                                  <RefreshCw size={12} className="animate-spin" />
                                ) : (
                                  'Save'
                                )}
                              </Button>
                              <Button
                                variant="ghost"
                                size="xs"
                                onClick={() => setRecordingSymbol(null)}
                                className="text-brand-light/70 hover:text-brand-danger transition-colors font-bold uppercase tracking-tight"
                              >
                                Cancel
                              </Button>
                            </InfoRow>
                          ) : (
                            <Button
                              size="sm"
                              onClick={() => setRecordingSymbol(`liability-${row.symbol}`)}
                              className="text-xs"
                            >
                              Record Donation
                            </Button>
                          ))}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot className="bg-brand-surface/30">
                <tr>
                  <td colSpan={5} className="table-cell text-right font-semibold">
                    Total Remaining Liability:
                  </td>
                  <td className="table-cell font-mono font-bold text-brand-danger text-lg">
                    ${fmt(totalLiability)}
                  </td>
                  <td className="table-cell"></td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {/* ── Donation History ───────────────────────────────────────────────────── */}
      <div className="flex justify-between items-center mb-4">
        <h2 className="font-semibold">Donation History</h2>
        <ActionRow>
          <Input
            type="text"
            placeholder="Filter by symbol…"
            value={historySymbolFilter}
            onChange={(e) => setHistorySymbolFilter(e.target.value)}
            className="text-sm w-36 font-mono"
          />
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
      </div>

      <div className="table-container">
        <table className="w-full text-left">
          <thead className="table-header">
            <tr>
              <th className="table-cell">Date</th>
              <th className="table-cell">Symbol</th>
              <th className="table-cell">Dividend</th>
              <th className="table-cell">Purification</th>
              <th className="table-cell">Receipt</th>
            </tr>
          </thead>
          <tbody>
            {isFetching && history.length === 0 ? (
              <tr>
                <td colSpan={5} className="table-cell text-center text-brand-light/70 italic py-8">
                  Loading…
                </td>
              </tr>
            ) : filteredHistory.length === 0 ? (
              <tr>
                <td colSpan={5} className="table-cell text-center text-brand-light/70 italic py-8">
                  No donations recorded
                </td>
              </tr>
            ) : (
              filteredHistory.map((r) => (
                <tr key={r.id} className="table-row">
                  <td className="table-cell text-xs text-brand-light/70 font-mono whitespace-nowrap">
                    {new Date(r.timestamp).toLocaleString()}
                  </td>
                  <td className="table-cell font-bold">{r.symbol}</td>
                  <td className="table-cell font-mono">${fmt(r.dividend_amount)}</td>
                  <td className="table-cell font-mono text-brand-danger font-semibold">
                    ${fmt(r.purification_amount)}
                  </td>
                  <td className="table-cell">
                    {r.donation_receipt_link ? (
                      <a
                        href={r.donation_receipt_link}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-1 text-brand-primary text-xs hover:underline"
                      >
                        <ExternalLink size={12} /> View
                      </a>
                    ) : (
                      <span className="text-brand-light/70">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Page>
  )
}

export default function ZakatPageWithBoundary() {
  return (
    <ErrorBoundary title="Zakat calculator unavailable">
      <ZakatPage />
    </ErrorBoundary>
  )
}
