import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { ROUTES } from '@/shared/routes'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface BacktestRequest {
  symbols?: string[]
  timeframe: string
  initial_capital: number
  max_positions: number
  stop_loss_pct: number
  take_profit_pct: number
  buy_threshold: number
}

interface TradeRecord {
  symbol: string
  side: string
  date: string
  price: number
  shares: number
  value: number
  reason: string
}

interface EquityPoint {
  date: string
  portfolio: number
  benchmark: number | null
  cash: number
  positions: number
}

interface BacktestResult {
  total_return_pct: number
  benchmark_return_pct: number
  max_drawdown_pct: number
  sharpe_ratio: number
  sortino_ratio: number
  win_rate: number
  trades_count: number
  symbols_tested: number
  start_date: string
  end_date: string
  equity_curve: EquityPoint[]
  trades: TradeRecord[]
  per_symbol_stats: { symbol: string; buys: number; sells: number; last_action: string; last_date: string }[]
}

const fmt = (n: number, dec = 2) => n.toFixed(dec)
const fmtCurrency = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)

function StatCard({ label, value, sub, positive }: { label: string; value: string; sub?: string; positive?: boolean }) {
  const color = positive === undefined ? '' : positive ? 'text-emerald-400' : 'text-red-400'
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
      {sub && <div className="text-xs text-zinc-500 mt-1">{sub}</div>}
    </div>
  )
}

export default function BacktestPage() {
  const [timeframe, setTimeframe] = useState('1y')
  const [capital, setCapital] = useState(100000)
  const [maxPos, setMaxPos] = useState(15)
  const [stopLoss, setStopLoss] = useState(8)
  const [takeProfit, setTakeProfit] = useState(15)
  const [threshold, setThreshold] = useState(65)
  const [tradeFilter, setTradeFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL')
  const [showAllTrades, setShowAllTrades] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  const mutation = useMutation<BacktestResult, Error, BacktestRequest>({
    mutationFn: async (req) => {
      const r = await fetch(ROUTES.AI_PORTFOLIO_BACKTEST, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || 'Backtest failed')
      }
      return r.json()
    },
    onSuccess: () => {
      toast.success('Backtest completed successfully')
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Backtest failed')
    },
  })

  const run = () =>
    mutation.mutate({
      timeframe,
      initial_capital: capital,
      max_positions: maxPos,
      stop_loss_pct: stopLoss,
      take_profit_pct: takeProfit,
      buy_threshold: threshold,
    })

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    if (mutation.isPending) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [mutation.isPending])

  const result = mutation.data

  const thinCurve = result
    ? result.equity_curve.filter((_, i) => i % Math.max(1, Math.floor(result.equity_curve.length / 300)) === 0)
    : []

  const filteredTrades = result
    ? (tradeFilter === 'ALL' ? result.trades : result.trades.filter((t) => t.side === tradeFilter))
    : []
  const visibleTrades = showAllTrades ? filteredTrades : filteredTrades.slice(0, 20)

  const outperforms = result ? result.total_return_pct > result.benchmark_return_pct : false
  const alpha = result ? result.total_return_pct - result.benchmark_return_pct : 0

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Portfolio Backtest</h1>
        <p className="text-zinc-400 text-sm mt-1">
          Simulates full bot strategy on historical data — stop-loss/take-profit, position sizing, max-positions cap.
          Benchmark: SPY buy-and-hold.
        </p>
      </div>

      {/* Config */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-4">
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm"
            >
              <option value="1y">1 Year</option>
              <option value="2y">2 Years</option>
              <option value="3y">3 Years</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Capital ($)</label>
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Max Positions</label>
            <input
              type="number"
              value={maxPos}
              onChange={(e) => setMaxPos(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Stop-Loss %</label>
            <input
              type="number"
              value={stopLoss}
              onChange={(e) => setStopLoss(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Take-Profit %</label>
            <input
              type="number"
              value={takeProfit}
              onChange={(e) => setTakeProfit(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Buy Threshold</label>
            <input
              type="number"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm font-mono"
            />
          </div>
        </div>
        <Button onClick={run} disabled={mutation.isPending} className="w-full md:w-auto">
          {mutation.isPending ? (
            <span className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Running… {elapsed}s
            </span>
          ) : 'Run Backtest'}
        </Button>
        {mutation.isPending && (
          <div className="mt-3 space-y-1">
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500/70 rounded-full transition-all duration-1000"
                style={{ width: `${Math.min(95, (elapsed / 90) * 100)}%` }}
              />
            </div>
            <p className="text-xs text-zinc-500">
              {elapsed < 10 ? 'Fetching historical data…' : elapsed < 40 ? 'Simulating trades…' : elapsed < 70 ? 'Computing metrics…' : 'Almost done…'}
            </p>
          </div>
        )}
        {mutation.isError && (
          <p className="text-red-400 text-sm mt-2">{mutation.error.message}</p>
        )}
      </div>

      {result && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
            <StatCard
              label="Return"
              value={`${fmt(result.total_return_pct)}%`}
              positive={result.total_return_pct > 0}
            />
            <StatCard
              label="vs SPY"
              value={`${alpha >= 0 ? '+' : ''}${fmt(alpha)}%`}
              sub={`SPY: ${fmt(result.benchmark_return_pct)}%`}
              positive={outperforms}
            />
            <StatCard
              label="Max Drawdown"
              value={`${fmt(result.max_drawdown_pct)}%`}
              positive={result.max_drawdown_pct < 15}
            />
            <StatCard
              label="Sharpe"
              value={fmt(result.sharpe_ratio, 3)}
              positive={result.sharpe_ratio > 1}
            />
            <StatCard
              label="Sortino"
              value={fmt(result.sortino_ratio, 3)}
              positive={result.sortino_ratio > 1}
            />
            <StatCard
              label="Win Rate"
              value={`${fmt(result.win_rate)}%`}
              positive={result.win_rate > 50}
            />
            <StatCard
              label="Trades"
              value={String(result.trades_count)}
              sub={`${result.symbols_tested} symbols`}
            />
            <StatCard
              label="Period"
              value={timeframe.toUpperCase()}
              sub={`${result.start_date} → ${result.end_date}`}
            />
          </div>

          {/* Equity Curve */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <h2 className="text-sm font-semibold text-zinc-300 mb-4">Equity Curve vs SPY</h2>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={thinCurve} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickFormatter={(d: string) => d.slice(0, 7)}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickFormatter={(v: number) => fmtCurrency(v)}
                  width={80}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null
                    return (
                      <div className="bg-zinc-800 border border-zinc-700 rounded p-3 text-xs space-y-1">
                        <div className="text-zinc-400">{label}</div>
                        {payload.map((p: any) => (
                          <div key={p.dataKey} style={{ color: p.color }}>
                            {p.name}: {fmtCurrency(p.value)}
                          </div>
                        ))}
                        {payload[0]?.payload && (
                          <div className="text-zinc-500">
                            Positions: {payload[0].payload.positions} | Cash: {fmtCurrency(payload[0].payload.cash)}
                          </div>
                        )}
                      </div>
                    )
                  }}
                />
                <Legend />
                <ReferenceLine y={capital} stroke="#52525b" strokeDasharray="4 4" label={{ value: 'Start', fill: '#71717a', fontSize: 10 }} />
                <Line
                  type="monotone"
                  dataKey="portfolio"
                  name="Bot Strategy"
                  stroke="#10b981"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  name="SPY"
                  stroke="#6366f1"
                  dot={false}
                  strokeWidth={1.5}
                  strokeDasharray="4 2"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Trade Log */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-zinc-300">Trade Log ({result.trades.length})</h2>
              <div className="flex gap-2">
                {(['ALL', 'BUY', 'SELL'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setTradeFilter(f)}
                    className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                      tradeFilter === f
                        ? 'bg-zinc-700 border-zinc-500 text-white'
                        : 'border-zinc-700 text-zinc-500 hover:border-zinc-500'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-2 pr-3">Date</th>
                    <th className="text-left py-2 pr-3">Symbol</th>
                    <th className="text-left py-2 pr-3">Side</th>
                    <th className="text-right py-2 pr-3">Price</th>
                    <th className="text-right py-2 pr-3">Value</th>
                    <th className="text-left py-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTrades.map((t, i) => (
                    <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                      <td className="py-1.5 pr-3 font-mono text-zinc-400">{t.date}</td>
                      <td className="py-1.5 pr-3 font-semibold">{t.symbol}</td>
                      <td className="py-1.5 pr-3">
                        <Badge
                          variant="outline"
                          className={t.side === 'BUY' ? 'text-emerald-400 border-emerald-800' : 'text-red-400 border-red-800'}
                        >
                          {t.side}
                        </Badge>
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">${t.price.toFixed(2)}</td>
                      <td className="py-1.5 pr-3 text-right font-mono">{fmtCurrency(t.value)}</td>
                      <td className="py-1.5 text-zinc-500">{t.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {filteredTrades.length > 20 && !showAllTrades && (
              <button
                onClick={() => setShowAllTrades(true)}
                className="mt-3 text-xs text-zinc-500 hover:text-zinc-300 underline"
              >
                Show all {filteredTrades.length} trades
              </button>
            )}
          </div>

          {/* Per-Symbol Activity */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <h2 className="text-sm font-semibold text-zinc-300 mb-3">Symbol Activity</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
              {result.per_symbol_stats.map((s) => (
                <div key={s.symbol} className="bg-zinc-800 rounded p-2">
                  <div className="font-semibold text-sm">{s.symbol}</div>
                  <div className="text-xs text-zinc-500 mt-0.5">
                    {s.buys}B / {s.sells}S
                  </div>
                  <div className="text-xs text-zinc-600 mt-0.5">{s.last_date}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Caveats */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-4 text-xs text-zinc-500 space-y-1">
            <p><span className="text-zinc-400 font-medium">Methodology:</span> t_score computed daily from OHLCV. f_score uses <em>current</em> fundamentals as a proxy (slight lookahead bias). s_score = neutral (15/30). No slippage or commissions modeled.</p>
            <p><span className="text-zinc-400 font-medium">Limitation:</span> Historical fundamentals not available — past BUY signals may differ from what live bot would have generated. Results are indicative, not exact.</p>
          </div>
        </>
      )}
    </div>
  )
}
