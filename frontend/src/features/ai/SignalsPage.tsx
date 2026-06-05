import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  HelpCircle,
  Loader,
  Minus,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Users,
  XCircle,
  Zap,
  Cpu,
} from 'lucide-react'
import type React from 'react'
import { useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Page, PageHeader, PageSection, CardGrid, ActionRow, InfoRow, Stack } from '@/components/ui/layout'
import { Tooltip, TextTip } from '../../components/Tooltip'
import { API_BASE, API_KEY, ROUTES } from '../../shared/routes'
import { useAccount } from '../trading/context/AccountContext'
import { useTrading } from '../trading/hooks/useTrading'
import { useTheme } from '../../lib/ThemeContext'
import { chartTheme } from '../../lib/chartTheme'

interface AnalystConsensus {
  symbol: string
  recommendation: string
  mean_score: number
  num_analysts: number
  target_high: number | null
  target_low: number | null
  target_mean: number | null
  buy_count: number
  hold_count: number
  sell_count: number
}

interface TradeSignal {
  symbol: string
  sentiment_score: number
  confidence: number
  action: 'BUY' | 'SELL' | 'HOLD'
  reasoning: string
  f_score?: number
  t_score?: number
  s_score?: number
  vix_tier?: 'CALM' | 'ELEVATED' | 'CRISIS'
  timestamp: string
}

interface DiscoveryResponse {
  signals: TradeSignal[]
  scanned_at: string | null
  stale: boolean
}

const formatAgo = (iso: string | null): string => {
  if (!iso) return 'never'
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

interface BacktestResult {
  symbol: string
  total_return_pct: number
  max_drawdown_pct: number
  win_rate: number
  trades_count: number
  equity_curve: { timestamp: string; value: number; price: number }[]
}

const BacktestModal: React.FC<{ symbol: string; onClose: () => void }> = ({ symbol, onClose }) => {
  useTheme() // re-read chart colors on theme switch
  const ct = chartTheme()
  const [timeframe, _setTimeframe] = useState('1y')
  const { data, isLoading, error, refetch } = useQuery<BacktestResult>({
    queryKey: ['backtest', symbol, timeframe],
    queryFn: () =>
      fetch(ROUTES.AI_BACKTEST, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, timeframe }),
      }).then((r) => {
        if (!r.ok) throw new Error('Backtest failed')
        return r.json()
      }),
    enabled: !!symbol,
  })

  return (
    <div className="fixed inset-0 bg-black/90 backdrop-blur-md z-[100] flex items-center justify-center p-4 sm:p-8">
      <div className="bg-brand-surface border border-brand-divider rounded-2xl w-full max-w-5xl max-h-[95vh] flex flex-col shadow-2xl animate-in fade-in zoom-in duration-300">
        <div className="p-4 sm:p-8 border-b border-brand-divider flex items-center justify-between bg-brand-surface rounded-t-2xl">
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            <div className="p-2 sm:p-3 bg-brand-primary/10 rounded-xl shrink-0">
              <TrendingUp size={20} className="text-brand-primary sm:hidden" />
              <TrendingUp size={24} className="text-brand-primary hidden sm:block" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg sm:text-2xl font-bold tracking-tight text-brand-light truncate">
                Strategy Performance: {symbol}
              </h2>
              <p className="text-sm text-brand-light/50 font-medium">
                1-Year Historical Backtest Report
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="h-10 w-10 sm:h-12 sm:w-12 hover:bg-brand-base rounded-full shrink-0"
          >
            <XCircle size={24} className="text-brand-light/40" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-8 scrollbar-hide">
          {isLoading ? (
            <div className="py-32 flex flex-col items-center justify-center gap-6">
              <Loader size={48} className="animate-spin text-brand-primary opacity-50" />
              <div className="text-center">
                <p className="text-lg font-bold text-brand-light">Crunching data...</p>
                <p className="text-sm text-brand-light/50">Simulating Multi-Factor AI strategy</p>
              </div>
            </div>
          ) : error ? (
            <div className="py-20 text-center bg-brand-danger/5 rounded-2xl border border-brand-danger/20">
              <AlertTriangle size={48} className="mx-auto text-brand-danger mb-4 opacity-50" />
              <p className="text-brand-danger font-bold text-lg">Backtest Unavailable</p>
              <p className="text-sm text-brand-light/70 mt-1">{(error as Error).message}</p>
              <Button onClick={() => refetch()} className="mt-6 h-10 px-8">
                Try Again
              </Button>
            </div>
          ) : (
            data && (
              <div className="space-y-10">
                <CardGrid cols={4} className="gap-6 grid-cols-2 md:grid-cols-4">
                  {[
                    {
                      label: 'Total Return',
                      val: `${data.total_return_pct >= 0 ? '+' : ''}${data.total_return_pct.toFixed(2)}%`,
                      color:
                        data.total_return_pct >= 0 ? 'text-brand-success' : 'text-brand-danger',
                    },
                    {
                      label: 'Max Drawdown',
                      val: `-${data.max_drawdown_pct.toFixed(2)}%`,
                      color: 'text-brand-warning',
                    },
                    {
                      label: 'Signal Win Rate',
                      val: `${data.win_rate.toFixed(1)}%`,
                      color: 'text-brand-light',
                    },
                    { label: 'Execution Count', val: data.trades_count, color: 'text-brand-light' },
                  ].map((s) => (
                    <div
                      key={s.label}
                      className="bg-brand-base/40 p-5 rounded-2xl border border-brand-divider/50 shadow-inner"
                    >
                      <p className="text-[10px] font-bold text-brand-light/40 uppercase tracking-widest mb-2">
                        {s.label}
                      </p>
                      <p className={`text-3xl font-mono font-bold tracking-tighter ${s.color}`}>
                        {s.val}
                      </p>
                    </div>
                  ))}
                </CardGrid>

                <div className="bg-brand-base/20 p-4 sm:p-8 rounded-3xl border border-brand-divider">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6 sm:mb-10">
                    <h3 className="text-xs font-bold text-brand-light/40 uppercase tracking-widest flex items-center gap-2">
                      <RefreshCw size={14} className="text-brand-primary" />
                      Portfolio Growth Simulation ($10k Starting)
                    </h3>
                    <InfoRow className=" text-[10px] font-bold text-brand-light/30">
                      <div className="w-2 h-2 rounded-full bg-brand-success" />
                      HISTORICAL PRICE DATA
                    </InfoRow>
                  </div>
                  <div className="h-[250px] sm:h-[450px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={data.equity_curve}>
                        <defs>
                          <linearGradient id="colorBacktest" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={ct.success} stopOpacity={0.15} />
                            <stop offset="95%" stopColor={ct.success} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} vertical={false} />
                        <XAxis dataKey="timestamp" hide />
                        <YAxis
                          domain={['auto', 'auto']}
                          orientation="right"
                          tick={{ fontSize: 11, fill: ct.axis, fontWeight: 600 }}
                          axisLine={false}
                          tickLine={false}
                          tickFormatter={(v) => `$${v.toLocaleString()}`}
                        />
                        <ReTooltip
                          contentStyle={{
                            backgroundColor: ct.surface,
                            border: `1px solid ${ct.grid}`,
                            borderRadius: '12px',
                            padding: '12px',
                            boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
                          }}
                          itemStyle={{ color: ct.success, fontSize: '13px', fontWeight: 'bold' }}
                          labelStyle={{ display: 'none' }}
                          formatter={(v: number) => [`$${v.toLocaleString()}`, 'Portfolio Value']}
                        />
                        <Area
                          type="monotone"
                          dataKey="value"
                          stroke={ct.success}
                          strokeWidth={3}
                          fillOpacity={1}
                          fill="url(#colorBacktest)"
                          animationDuration={1500}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            )
          )}
        </div>
        <div className="p-6 border-t border-brand-divider bg-brand-base/30 rounded-b-2xl flex justify-end">
          <Button
            onClick={onClose}
            className="h-11 px-10 font-bold uppercase tracking-widest shadow-glow-primary"
          >
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}

interface Settings {
  trading_mode: 'MANUAL' | 'AUTO'
  auto_execute_threshold: number
  signal_min_confidence: number
  watchlist?: string[]
}

interface ApproveResult {
  state: string
  symbol: string
  quantity: number
  ibkr_order_id: number | null
}

const ConfidenceBar: React.FC<{ confidence: number; action: TradeSignal['action'] }> = ({
  confidence,
  action,
}) => {
  const color =
    action === 'BUY' ? 'bg-brand-success' : action === 'SELL' ? 'bg-brand-danger' : 'bg-brand-muted'

  return (
    <InfoRow className=" min-w-[120px]">
      <div className="flex-1 bg-brand-divider rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all ${color}`}
          style={{ width: `${confidence}%` }}
        />
      </div>
      <span className="text-xs font-mono font-bold w-8 text-right">{confidence}%</span>
    </InfoRow>
  )
}

const ActionBadge: React.FC<{ action: TradeSignal['action'] }> = ({ action }) => {
  if (action === 'BUY')
    return (
      <span className="flex items-center gap-1 text-brand-success font-bold text-sm">
        <TrendingUp size={14} /> BUY
      </span>
    )
  if (action === 'SELL')
    return (
      <span className="flex items-center gap-1 text-brand-danger font-bold text-sm">
        <TrendingDown size={14} /> SELL
      </span>
    )
  return (
    <span className="flex items-center gap-1 text-brand-light/70 text-sm">
      <Minus size={14} /> HOLD
    </span>
  )
}

const VIX_MAXES: Record<string, { f: number; t: number; s: number }> = {
  CALM:     { f: 25, t: 45, s: 30 },
  ELEVATED: { f: 35, t: 35, s: 30 },
  CRISIS:   { f: 45, t: 25, s: 30 },
}

const VIX_COLORS: Record<string, string> = {
  CALM: 'text-brand-success bg-brand-success/10 border-brand-success/20',
  ELEVATED: 'text-brand-warning bg-brand-warning/10 border-brand-warning/20',
  CRISIS: 'text-brand-danger bg-brand-danger/10 border-brand-danger/20',
}

const MultiFactorBreakdown: React.FC<{ signal: TradeSignal }> = ({ signal }) => {
  const { f_score = 0, t_score = 0, s_score = 0, vix_tier } = signal
  const maxes = (vix_tier && VIX_MAXES[vix_tier]) ?? { f: 30, t: 40, s: 30 }

  const Factor = ({
    label,
    val,
    max,
    color,
  }: {
    label: string
    val: number
    max: number
    color: string
  }) => (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between text-[8px] font-bold uppercase tracking-widest text-brand-light/70">
        <span>{label}</span>
        <span>
          {val}/{max}
        </span>
      </div>
      <div className="h-1 bg-brand-divider rounded-full overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${(val / max) * 100}%` }} />
      </div>
    </div>
  )

  return (
    <div className="grid grid-cols-3 gap-2 min-w-[150px]">
      <Factor label="Fund." val={f_score} max={maxes.f} color="bg-brand-primary" />
      <Factor label="Tech." val={t_score} max={maxes.t} color="bg-brand-success" />
      <Factor label="Sent." val={s_score} max={maxes.s} color="bg-brand-accent" />
    </div>
  )
}

const REC_LABEL: Record<string, string> = {
  strong_buy: 'Strong Buy',
  buy: 'Buy',
  hold: 'Hold',
  sell: 'Sell',
  strong_sell: 'Strong Sell',
  none: '—',
}

const ExpertConsensus: React.FC<{ symbol: string; aiAction: TradeSignal['action'] }> = ({
  symbol,
  aiAction,
}) => {
  const { data, isFetching } = useQuery<AnalystConsensus>({
    queryKey: ['analyst', symbol],
    queryFn: () =>
      fetch(`${API_BASE}/api/ai/analyst/${symbol}`).then((r) => {
        if (!r.ok) throw new Error('no data')
        return r.json()
      }),
    staleTime: 30 * 60_000,
    retry: false,
  })

  if (isFetching) return <Loader size={11} className="animate-spin text-brand-light/70" />
  if (!data) return <span className="text-xs text-brand-light/70">—</span>

  const total = data.buy_count + data.hold_count + data.sell_count
  const buyPct = total ? Math.round((data.buy_count / total) * 100) : 0
  const holdPct = total ? Math.round((data.hold_count / total) * 100) : 0
  const sellPct = total ? Math.round((data.sell_count / total) * 100) : 0

  const recKey = data.recommendation?.toLowerCase() ?? 'none'
  const labelColor = recKey.includes('buy')
    ? 'text-brand-success'
    : recKey.includes('sell')
      ? 'text-brand-danger'
      : 'text-brand-light/70'

  // Divergence: AI says BUY but analysts lean Sell, or vice versa
  const analystsBullish = recKey.includes('buy')
  const analystsBearish = recKey.includes('sell')
  const diverges =
    (aiAction === 'BUY' && analystsBearish) || (aiAction === 'SELL' && analystsBullish)

  return (
    <div className="flex flex-col gap-1 min-w-[140px]">
      <InfoRow className=" flex-wrap">
        <span className={`text-xs font-semibold flex items-center gap-1 ${labelColor}`}>
          <Users size={11} />
          {REC_LABEL[recKey] ?? recKey}
          {data.num_analysts > 0 && (
            <span className="text-brand-light/70 font-normal">({data.num_analysts})</span>
          )}
        </span>
        {diverges && (
          <Tooltip
            text={`AI says ${aiAction} but Wall Street analysts ${analystsBearish ? 'lean Sell' : 'lean Buy'}. These disagree — do your own research before acting.`}
            width="w-60"
          >
            <span className="flex items-center gap-0.5 text-xs text-brand-warning font-medium cursor-help">
              <AlertTriangle size={11} /> Diverges
            </span>
          </Tooltip>
        )}
      </InfoRow>
      {total > 0 && (
        <Tooltip
          text={`${data.buy_count} analysts say Buy · ${data.hold_count} say Hold · ${data.sell_count} say Sell`}
          width="w-56"
        >
          <div className="flex gap-0.5 h-1.5 rounded overflow-hidden w-full cursor-help">
            {buyPct > 0 && <div className="bg-brand-success" style={{ width: `${buyPct}%` }} />}
            {holdPct > 0 && <div className="bg-brand-warning" style={{ width: `${holdPct}%` }} />}
            {sellPct > 0 && <div className="bg-brand-danger" style={{ width: `${sellPct}%` }} />}
          </div>
        </Tooltip>
      )}
      {data.target_mean != null && (
        <Tooltip
          text={`Analysts' average price target: $${data.target_mean.toFixed(0)}. Range: $${data.target_low?.toFixed(0) ?? '?'} – $${data.target_high?.toFixed(0) ?? '?'}. This is where pros think the price could go.`}
          width="w-64"
        >
          <span className="text-xs text-brand-light/70 font-mono cursor-help whitespace-nowrap">
            target ${data.target_mean.toFixed(0)}
            {data.target_low != null &&
              data.target_high != null &&
              ` (${data.target_low.toFixed(0)}–${data.target_high.toFixed(0)})`}
          </span>
        </Tooltip>
      )}
    </div>
  )
}

interface SimulationResponse {
  cash_available_before: number
  cash_available_after: number
  portfolio_purity_before: number
  portfolio_purity_after: number
  sector_concentration_before: number
  sector_concentration_after: number
  warnings: string[]
}

const SimulateModal: React.FC<{
  signal: TradeSignal
  onClose: () => void
}> = ({ signal, onClose }) => {
  const { data, isLoading, error } = useQuery<SimulationResponse>({
    queryKey: ['simulate', signal.symbol, signal.action],
    queryFn: () =>
      fetch(ROUTES.PORTFOLIO_SIMULATE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: signal.symbol,
          quantity: 0,
          price: 0,
          side: signal.action,
        }),
      }).then(async (r) => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      }),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-brand-base/80 backdrop-blur-sm">
      <div className="w-full max-w-md card p-0 border border-brand-divider/50 shadow-2xl relative z-10 overflow-hidden flex flex-col">
        <div className="p-5 border-b border-brand-divider/50 flex items-center justify-between bg-brand-surface/50">
          <h2 className="text-base font-bold flex items-center gap-2 text-brand-light">
            <Zap size={16} className="text-brand-primary" />
            Blast Radius: {signal.action} {signal.symbol}
          </h2>
          <button onClick={onClose} className="p-1 hover:text-brand-danger text-brand-light/50 transition-colors">
            <XCircle size={18} />
          </button>
        </div>

        <div className="p-6 flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex flex-col items-center gap-4 py-8">
              <Loader className="animate-spin text-brand-primary" size={24} />
              <p className="text-sm text-brand-light/70">Simulating portfolio impact...</p>
            </div>
          ) : error ? (
            <div className="p-4 bg-brand-danger/10 border border-brand-danger/30 rounded-lg text-brand-danger text-sm">
              Failed to simulate trade: {(error as Error).message}
            </div>
          ) : data ? (
            <Stack className="space-y-2">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <span className="text-[10px] uppercase font-bold text-brand-light/50 tracking-wider">Available Cash</span>
                  <div className="flex flex-col gap-0.5">
                    <span className="line-through text-brand-light/50 font-mono text-sm">${data.cash_available_before.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    <span className={`font-mono font-bold ${data.cash_available_after < 0 ? 'text-brand-danger' : 'text-brand-light'}`}>${data.cash_available_after.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  </div>
                </div>
                <div className="space-y-1">
                  <span className="text-[10px] uppercase font-bold text-brand-light/50 tracking-wider">Portfolio Purity</span>
                  <div className="flex flex-col gap-0.5">
                    <span className="line-through text-brand-light/50 font-mono text-sm">{(data.portfolio_purity_before * 100).toFixed(1)}%</span>
                    <span className={`font-mono font-bold ${data.portfolio_purity_after > 0.05 ? 'text-brand-danger' : 'text-brand-success'}`}>
                      {(data.portfolio_purity_after * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                <div className="space-y-1 col-span-2">
                  <span className="text-[10px] uppercase font-bold text-brand-light/50 tracking-wider">Sector Concentration</span>
                  <div className="flex flex-col gap-0.5">
                    <span className="line-through text-brand-light/50 font-mono text-sm">{(data.sector_concentration_before * 100).toFixed(1)}%</span>
                    <span className="font-mono font-bold text-brand-light">{(data.sector_concentration_after * 100).toFixed(1)}%</span>
                  </div>
                </div>
              </div>

              {data.warnings && data.warnings.length > 0 && (
                <div className="p-3 bg-brand-warning/10 border border-brand-warning/30 rounded-lg space-y-2">
                  <h4 className="text-xs font-bold text-brand-warning uppercase tracking-wider flex items-center gap-1.5">
                    <AlertTriangle size={14} /> Warnings
                  </h4>
                  <ul className="text-xs text-brand-warning/90 space-y-1 list-disc pl-4">
                    {data.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Stack>
          ) : null}
        </div>
      </div>
    </div>
  )
}

const SignalRow: React.FC<{
  signal: TradeSignal
  settings: Settings
  onBacktest: (symbol: string) => void
  onSimulate: (signal: TradeSignal) => void
  forceApprove?: boolean
  onAddToWatchlist?: (symbol: string) => void
  tickerUpdates?: Record<string, any>
}> = ({ signal, settings, onBacktest, onSimulate, forceApprove, onAddToWatchlist, tickerUpdates = {} }) => {
  const queryClient = useQueryClient()
  const { selectedAccountId } = useAccount()
  const [result, setResult] = useState<ApproveResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const willAuto =
    !forceApprove &&
    (settings.trading_mode === 'AUTO' ||
      (settings.auto_execute_threshold > 0 && signal.confidence >= settings.auto_execute_threshold))

  const approve = useMutation({
    mutationFn: () =>
      fetch(ROUTES.AI_APPROVE, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Api-Key': API_KEY,
        },
        body: JSON.stringify({ symbol: signal.symbol, side: signal.action, account_id: selectedAccountId }),
      }).then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`)
        return r.json() as Promise<ApproveResult>
      }),
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['trades'] })
      toast.success(`Signal for ${signal.symbol} approved`)
    },
    onError: (e: Error) => {
      setError(e.message)
      toast.error(e.message || `Failed to approve ${signal.symbol}`)
    },
  })

  const actionable = signal.action !== 'HOLD'

  const signalTime = new Date(signal.timestamp).getTime()
  const isStale = Date.now() - signalTime > 5 * 60 * 1000 // 5 minutes
  const tick = tickerUpdates[signal.symbol]
  const livePrice = tick?.last && !isNaN(tick.last) ? tick.last : null

  return (
    <>
      {/* Mobile card */}
      <tr className="md:hidden">
        <td colSpan={5} className="p-0 border-b border-brand-divider/40 last:border-0">
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <InfoRow className="">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-brand-light text-xl tracking-tight">
                      {signal.symbol}
                    </span>
                    {livePrice != null && (
                      <span className="text-[10px] font-mono text-brand-primary flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-brand-primary animate-pulse" />
                        ${livePrice.toFixed(2)}
                      </span>
                    )}
                    {isStale && (
                      <Badge
                        variant="outline"
                        className="bg-brand-warning/10 text-brand-warning border-brand-warning/30 text-[9px] px-1.5 h-4 uppercase tracking-tighter"
                      >
                        Stale Data
                      </Badge>
                    )}
                  </div>
                  {signal.vix_tier && (
                    <span className={`text-[8px] px-1 py-0.5 rounded border font-bold uppercase tracking-widest ${VIX_COLORS[signal.vix_tier]}`}>
                      {signal.vix_tier}
                    </span>
                  )}
                </InfoRow>
                <InfoRow className="">
                  <button
                    onClick={() => onBacktest(signal.symbol)}
                    className="text-[9px] px-1.5 py-0.5 rounded border border-brand-divider font-bold uppercase tracking-wider text-brand-light/70 hover:bg-brand-primary/10 hover:text-brand-primary hover:border-brand-primary/30 transition-all"
                  >
                    Test
                  </button>
                  {forceApprove && onAddToWatchlist && (
                    <button
                      onClick={() => onAddToWatchlist(signal.symbol)}
                      className="text-[9px] px-1.5 py-0.5 rounded border border-brand-success/30 font-bold uppercase tracking-wider text-brand-success/70 hover:bg-brand-success/10 hover:text-brand-success hover:border-brand-success/50 transition-all"
                      title="Add to Watchlist"
                    >
                      + Watch
                    </button>
                  )}
                </InfoRow>
                <div className="mt-0.5">
                  <ActionBadge action={signal.action} />
                </div>
              </div>
              <div className="text-right flex flex-col items-end gap-1.5">
                <ExpertConsensus symbol={signal.symbol} aiAction={signal.action} />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-[10px] font-bold text-brand-light/70 uppercase tracking-wider">
                <span>AI Confidence</span>
                <span>{signal.confidence}%</span>
              </div>
              <ConfidenceBar confidence={signal.confidence} action={signal.action} />
            </div>

            <div className="bg-brand-elevated/50 p-3 rounded-lg border border-brand-divider/30">
              <div className="mb-3">
                <p className="text-[10px] font-bold text-brand-light/70 uppercase tracking-widest mb-1">
                  Scoring Breakdown
                </p>
                <MultiFactorBreakdown signal={signal} />
              </div>
              <p className="text-[11px] leading-relaxed text-brand-light/70 italic line-clamp-3">
                "{signal.reasoning}"
              </p>
            </div>

            <div className="pt-1 flex items-center justify-end">
              {result ? (
                result.state === 'IBKR_ERROR' ? (
                  <Tooltip text={`IBKR rejected the order. Order ID: ${result.ibkr_order_id ?? 'N/A'}. Check broker logs for details.`} width="w-72">
                    <Badge variant="destructive" className="gap-1.5 py-1 px-3 cursor-help">
                      <XCircle size={12} /> IBKR Error #{result.ibkr_order_id ?? '—'}
                    </Badge>
                  </Tooltip>
                ) : (
                  <Badge variant="success" className="gap-1.5 py-1 px-3">
                    <CheckCircle2 size={12} /> {result.state} #{result.ibkr_order_id ?? '—'}
                  </Badge>
                )
              ) : error ? (
                <Tooltip text={error} width="w-72">
                  <Badge variant="destructive" className="gap-1.5 py-1 px-3 cursor-help">
                    <XCircle size={12} /> Submission Failed
                  </Badge>
                </Tooltip>
              ) : actionable && !willAuto ? (
                <div className="w-full flex flex-col gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onSimulate(signal)}
                    className="w-full h-9 font-bold flex items-center justify-center border-brand-primary/30 text-brand-primary hover:bg-brand-primary/10 transition-colors"
                  >
                    SIMULATE
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => approve.mutate()}
                    disabled={approve.isPending}
                    className="w-full h-9 font-bold flex items-center justify-center gap-2 shadow-glow-primary"
                  >
                    {approve.isPending ? (
                      <>
                        <Loader size={14} className="animate-spin" /> EXECUTING...
                      </>
                    ) : (
                      <>
                        <CheckCircle2 size={14} /> APPROVE {signal.action}
                      </>
                    )}
                  </Button>
                </div>
              ) : willAuto ? (
                <Tooltip
                  text="Meets auto-execute threshold. This trade is handled by the system."
                  position="bottom"
                >
                  <InfoRow className=" text-[10px] font-bold text-brand-success uppercase tracking-widest bg-brand-success/10 px-3 py-1.5 rounded-full border border-brand-success/20 cursor-help">
                    <Zap size={12} fill="currentColor" /> Auto-executing
                  </InfoRow>
                </Tooltip>
              ) : (
                <Tooltip text="AI score is neutral. No action recommended." position="bottom">
                  <span className="text-[10px] font-bold text-brand-light/70 uppercase tracking-widest cursor-help">
                    AI: Hold
                  </span>
                </Tooltip>
              )}
            </div>
          </div>
        </td>
      </tr>

      {/* Desktop row */}
      <tr className="hidden md:table-row table-row">
        <td className="table-cell">
          <InfoRow className="">
            <div className="flex flex-col gap-0.5">
              <InfoRow className="">
                <span className="font-bold text-brand-light">{signal.symbol}</span>
                {livePrice != null && (
                  <span className="text-[10px] font-mono text-brand-primary flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-brand-primary animate-pulse" />
                    ${livePrice.toFixed(2)}
                  </span>
                )}
                {isStale && (
                  <Badge
                    variant="outline"
                    className="bg-brand-warning/10 text-brand-warning border-brand-warning/30 text-[9px] px-1.5 h-4 uppercase tracking-tighter"
                  >
                    Stale Data
                  </Badge>
                )}
                {signal.vix_tier && (
                  <span className={`text-[8px] px-1 py-0.5 rounded border font-bold uppercase tracking-widest ${VIX_COLORS[signal.vix_tier]}`}>
                    {signal.vix_tier}
                  </span>
                )}
              </InfoRow>
              <InfoRow className="">
                <button
                  onClick={() => onBacktest(signal.symbol)}
                  className="text-[9px] px-1.5 py-0.5 rounded border border-brand-divider font-bold uppercase tracking-wider text-brand-light/70 hover:bg-brand-primary/10 hover:text-brand-primary hover:border-brand-primary/30 transition-all"
                  title="Run Backtest"
                >
                  Test
                </button>
                {forceApprove && onAddToWatchlist && (
                  <button
                    onClick={() => onAddToWatchlist(signal.symbol)}
                    className="text-[9px] px-1.5 py-0.5 rounded border border-brand-success/30 font-bold uppercase tracking-wider text-brand-success/70 hover:bg-brand-success/10 hover:text-brand-success hover:border-brand-success/50 transition-all"
                    title="Add to Watchlist"
                  >
                    + Watch
                  </button>
                )}
              </InfoRow>
            </div>
          </InfoRow>
        </td>
        <td className="table-cell">
          <Tooltip text={signal.reasoning || '—'} width="w-72">
            <span className="cursor-help">
              <ActionBadge action={signal.action} />
            </span>
          </Tooltip>
        </td>
        <td className="table-cell">
          <ConfidenceBar confidence={signal.confidence} action={signal.action} />
        </td>
        <td className="table-cell">
          <MultiFactorBreakdown signal={signal} />
        </td>
        <td className="table-cell">
          <ExpertConsensus symbol={signal.symbol} aiAction={signal.action} />
        </td>
        <td className="table-cell">
          <InfoRow className="">
            {result ? (
              result.state === 'IBKR_ERROR' ? (
                <Tooltip text={`IBKR rejected the order. Order ID: ${result.ibkr_order_id ?? 'N/A'}. Check broker logs for details.`} width="w-72">
                  <span className="flex items-center gap-1 text-xs text-brand-danger font-medium cursor-help">
                    <XCircle size={14} /> IBKR Error #{result.ibkr_order_id ?? '—'}
                  </span>
                </Tooltip>
              ) : (
                <span className="flex items-center gap-1 text-xs text-brand-success font-medium">
                  <CheckCircle2 size={14} /> {result.state} #{result.ibkr_order_id ?? '—'}
                </span>
              )
            ) : error ? (
              <Tooltip text={error} width="w-72">
                <span className="flex items-center gap-1 text-xs text-brand-danger cursor-help">
                  <XCircle size={14} /> Failed
                </span>
              </Tooltip>
            ) : actionable && !willAuto ? (
              <ActionRow>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onSimulate(signal)}
                  className="text-xs flex items-center gap-1 whitespace-nowrap border-brand-primary/30 text-brand-primary hover:bg-brand-primary/10 transition-colors"
                >
                  Simulate
                </Button>
                <Button
                  size="sm"
                  onClick={() => approve.mutate()}
                  disabled={approve.isPending}
                  className="text-xs flex items-center gap-1 whitespace-nowrap"
                >
                  {approve.isPending ? (
                    <>
                      <Loader size={12} className="animate-spin" /> Executing...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 size={12} /> Approve {signal.action}
                    </>
                  )}
                </Button>
              </ActionRow>
            ) : willAuto ? (
              <Tooltip
                text="Confidence score meets your 'Auto' threshold. This trade will be managed by the AI loop automatically."
                width="w-60"
              >
                <span className="text-xs text-brand-success italic cursor-help flex items-center gap-1">
                  <Zap size={11} /> Will auto-execute
                </span>
              </Tooltip>
            ) : (
              <Tooltip
                text="The AI currently suggests holding this position. No trade is recommended at this score level."
                width="w-60"
              >
                <span className="text-xs text-brand-light/70 italic cursor-help">AI: Hold</span>
              </Tooltip>
            )}
          </InfoRow>
        </td>
      </tr>
    </>
  )
}

const DEFAULT_SETTINGS: Settings = {
  trading_mode: 'MANUAL',
  auto_execute_threshold: 0,
  signal_min_confidence: 30,
}

const SignalsPage = () => {
  const { tickerUpdates } = useTrading()
  const [activeTab, setActiveTab] = useState<'WATCHLIST' | 'DISCOVERY'>('WATCHLIST')
  const [backtestSymbol, setBacktestSymbol] = useState<string | null>(null)
  const [simulateSignal, setSimulateSignal] = useState<TradeSignal | null>(null)
  const queryClient = useQueryClient()

  const {
    data: signals = [],
    isFetching,
    refetch,
  } = useQuery<TradeSignal[]>({
    queryKey: ['ai-signals'],
    queryFn: () => fetch(`${API_BASE}/api/ai/signals`).then((r) => r.json()),
    staleTime: 60_000,
    enabled: activeTab === 'WATCHLIST',
  })

  // Discovery is served from the backend cache (fast). The slow S&P scan only
  // runs when the user explicitly clicks "Scan Market" (scanMarket below).
  const { data: discovery } = useQuery<DiscoveryResponse>({
    queryKey: ['ai-discover'],
    queryFn: () => fetch(ROUTES.AI_DISCOVER).then((r) => r.json()),
    staleTime: Infinity,
    enabled: activeTab === 'DISCOVERY',
  })
  const discoveries = discovery?.signals ?? []
  const scannedAt = discovery?.scanned_at ?? null

  const scanMarket = useMutation({
    mutationFn: () =>
      fetch(`${ROUTES.AI_DISCOVER}?refresh=true`).then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`)
        return r.json() as Promise<DiscoveryResponse>
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['ai-discover'], data)
      toast.success(`Scan complete — ${data.signals.length} Halal matches`)
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Market scan failed')
    },
  })
  const isScanning = scanMarket.isPending

  const { data: settings = DEFAULT_SETTINGS } = useQuery<Settings>({
    queryKey: ['settings'],
    queryFn: () => fetch(ROUTES.SETTINGS).then((r) => r.json()),
    staleTime: 30_000,
  })

  const addToWatchlist = useMutation({
    mutationFn: async (symbol: string) => {
      const current = queryClient.getQueryData<Settings>(['settings']) ?? settings
      const existing: string[] = current.watchlist ?? []
      if (existing.includes(symbol)) return
      const r = await fetch(ROUTES.SETTINGS, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ watchlist: [...existing, symbol] }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return { symbol, data: await r.json() }
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      if (res) {
        toast.success(`${res.symbol} added to watchlist`)
      }
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Failed to add symbol to watchlist')
    },
  })

  const retrain = useMutation({
    mutationFn: () =>
      fetch(`${API_BASE}/api/ai/retrain`, { method: 'POST', headers: { 'X-API-Key': API_KEY } })
        .then(async (r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`)
          return r.json()
        }),
    onSuccess: () => {
      toast.success('AI retraining initiated')
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Failed to initiate AI retraining')
    },
  })

  const filtered = signals.filter((s) => s.confidence >= settings.signal_min_confidence)
  const actionable = filtered.filter((s) => s.action !== 'HOLD')
  const holds = filtered.filter((s) => s.action === 'HOLD')
  const sorted = [...actionable.sort((a, b) => b.confidence - a.confidence), ...holds]
  const _ignoredCount = signals.length - filtered.length

  const displaySignals = activeTab === 'WATCHLIST' ? sorted : discoveries

  return (
    <Page>
      <PageHeader className="mb-6">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-4 flex-wrap">
            <h1 className="heading-1 mb-0">
              <BrainCircuit className="text-brand-primary" size={28} />
              AI Strategy Agent
            </h1>
            <div className="flex bg-brand-base p-1 rounded-lg border border-brand-divider">
              <button
                type="button"
                onClick={() => setActiveTab('WATCHLIST')}
                className={`px-3 py-1 text-[10px] font-bold uppercase rounded-md transition-all ${activeTab === 'WATCHLIST' ? 'bg-brand-primary text-white shadow-sm' : 'text-brand-light/70 hover:text-brand-light'}`}
              >
                Watchlist
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('DISCOVERY')}
                className={`px-3 py-1 text-[10px] font-bold uppercase rounded-md transition-all ${activeTab === 'DISCOVERY' ? 'bg-brand-primary text-white shadow-sm' : 'text-brand-light/70 hover:text-brand-light'}`}
              >
                Discovery
              </button>
            </div>
          </div>
          <p className="text-brand-light/70 text-sm">
            {activeTab === 'WATCHLIST'
              ? 'Review AI recommendations for your saved watchlist.'
              : (
                <>
                  Global scan for Halal "Strong Buy" opportunities in the S&P 500.{' '}
                  <span className="text-brand-light/50">
                    Last scan: {formatAgo(scannedAt)}.
                  </span>
                </>
              )}
          </p>
        </div>
        <div className="flex gap-2 self-start flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={() => retrain.mutate()}
            disabled={retrain.isPending}
            title={retrain.data ? `Last: ${retrain.data.snapshot_count?.toLocaleString()} snapshots · ${retrain.data.model}` : 'Retrain RF + PPO model'}
            className="border-brand-divider hover:border-brand-primary/50 hover:bg-brand-primary/5 transition-all gap-2"
          >
            <Cpu size={14} className={retrain.isPending ? 'animate-pulse' : ''} />
            {retrain.isPending ? 'Training…' : 'Retrain'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => (activeTab === 'WATCHLIST' ? refetch() : scanMarket.mutate())}
            disabled={activeTab === 'WATCHLIST' ? isFetching : isScanning}
            className="border-brand-divider hover:border-brand-primary/50 hover:bg-brand-primary/5 transition-all gap-2"
          >
            <RefreshCw
              size={14}
              className={(activeTab === 'WATCHLIST' ? isFetching : isScanning) ? 'animate-spin' : ''}
            />
            {activeTab === 'WATCHLIST' ? 'Refresh' : isScanning ? 'Scanning…' : 'Scan Market'}
          </Button>
        </div>
      </PageHeader>

      {(activeTab === 'WATCHLIST' ? isFetching : isScanning) &&
        (activeTab === 'WATCHLIST' ? signals : discoveries).length === 0 && (
          <div className="flex flex-col items-center gap-4 text-brand-light/70 py-20 justify-center">
            <Loader size={24} className="animate-spin text-brand-primary" />
            <span className="text-sm font-medium tracking-wide">
              {activeTab === 'WATCHLIST'
                ? 'Analyzing market sentiment...'
                : 'Deep scanning S&P 500 for Halal opportunities...'}
            </span>
          </div>
        )}

      {!(activeTab === 'WATCHLIST' ? isFetching : isScanning) && displaySignals.length === 0 && (
        <PageSection className="card text-center py-16 px-6 bg-brand-surface/50 border-dashed">
          <BrainCircuit className="mx-auto text-brand-light/70 mb-4 opacity-20" size={48} />
          <p className="text-brand-light font-medium">No signals available</p>
          <p className="text-brand-light/70 text-sm mt-1">
            {activeTab === 'WATCHLIST'
              ? 'Check your watchlist in Settings or refresh.'
              : 'Run a deep scan to discover new Halal opportunities.'}
          </p>
        </PageSection>
      )}

      {displaySignals.length > 0 && (
        <PageSection className="table-container mb-12">
          <div className="card-header justify-between py-3">
            <h2 className="heading-2 mb-0 flex items-center gap-2">
              <TrendingUp className="text-brand-success" size={16} />
              {activeTab === 'WATCHLIST'
                ? `${displaySignals.length} Actionable Signals`
                : `${displaySignals.length} Halal "Strong Buy" Matches`}
            </h2>
          </div>
          <table className="w-full text-left">
            <thead className="table-header hidden md:table-header-group">
              <tr>
                <th className="table-cell">Symbol</th>
                <th className="table-cell">
                  <TextTip text="AI recommendation based on technicals, fundamentals, and market sentiment. BUY = High potential, SELL = High risk, HOLD = Neutral." width="w-64">
                    Signal
                  </TextTip>
                </th>
                <th className="table-cell">
                  <TextTip text="Confidence score (0-100%). Higher means AI is more certain. Trades above your 'Auto' threshold in Settings execute automatically." width="w-64">
                    Confidence
                  </TextTip>
                </th>
                <th className="table-cell">
                  <TextTip text="Breakdown of factors: Fundamentals (30pts), Technicals (40pts), and Sentiment (30pts)." width="w-64">
                    AI Scorecard
                  </TextTip>
                </th>
                <th className="table-cell">
                  <TextTip text="Consensus from Wall Street analysts. If 'Diverges' appears, AI and human analysts disagree." width="w-60">
                    Experts
                  </TextTip>
                </th>
                <th className="table-cell min-w-[200px]">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-divider/40">
              {displaySignals.map((s) => (
                <SignalRow
                  key={s.symbol}
                  signal={s}
                  settings={settings}
                  onBacktest={setBacktestSymbol}
                  onSimulate={setSimulateSignal}
                  forceApprove={activeTab === 'DISCOVERY'}
                  onAddToWatchlist={(sym) => addToWatchlist.mutate(sym)}
                  tickerUpdates={tickerUpdates}
                />
              ))}
            </tbody>
          </table>
        </PageSection>
      )}

      {backtestSymbol && (
        <BacktestModal symbol={backtestSymbol} onClose={() => setBacktestSymbol(null)} />
      )}
      {simulateSignal && (
        <SimulateModal signal={simulateSignal} onClose={() => setSimulateSignal(null)} />
      )}
    </Page>
  )
}

import { ErrorBoundary } from '../../components/ErrorBoundary'

export default function SignalsPageWithBoundary() {
  return (
    <ErrorBoundary title="AI Signals unavailable">
      <SignalsPage />
    </ErrorBoundary>
  )
}
