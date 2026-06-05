import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import {
  AlertTriangle,
  Briefcase,
  CheckCircle2,
  Download,
  Globe,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  TrendingUp,
  XCircle,
  Zap,
} from 'lucide-react'
import React, { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  Pie,
  PieChart as RePieChart,
  ResponsiveContainer,
  Sector,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Page, PageHeader, PageSection, CardGrid, ActionRow, InfoRow, Stack } from '@/components/ui/layout'
import { Text, Eyebrow } from '@/components/ui/text'
import { Abbr, InfoTip, TextTip, Tooltip as AppTooltip } from '../../components/Tooltip'
import { API_KEY, ROUTES, withAccount } from '../../shared/routes'
import {
  PortfolioValueSchema,
  PortfolioSummarySchema,
  PnLSummarySchema,
  PositionSchema,
  HistorySnapshotSchema,
  validatedFetch,
  validatedFetchArray,
} from '../../shared/schemas'
import { useAccount } from '../trading/context/AccountContext'
import { useTheme } from '../../lib/ThemeContext'
import { chartTheme } from '../../lib/chartTheme'
import {
  type ComplianceResult,
  RatioBar,
  SOURCE_COLORS,
  VerdictBadge,
  verdictColor,
} from '../compliance/components'
import GlobalMarketsPanel from './components/GlobalMarketsPanel'
import TradeLog from '../trading/components/TradeLog'
import { useTrading } from '../trading/hooks/useTrading'

interface Position {
  symbol: string
  quantity: number
  avg_cost: number
  market_value: number
  unrealized_pnl: number
}

interface PositionPnL {
  symbol: string
  unrealized_pnl: number
  realized_pnl: number
  quantity: number
  avg_cost: number
  market_value: number
  purification_cost: number
  halal_pnl: number
  days_held: number | null
  stop_price: number | null
  target_price: number | null
  partial_price: number | null
}

interface PnLSummary {
  total_unrealized_pnl: number
  total_realized_pnl: number
  total_purification_cost?: number
  positions: PositionPnL[]
}

interface HistorySnapshot {
  timestamp: string
  total_value: number
  benchmark_value?: number
  benchmarks?: Record<string, number>
}

interface PortfolioValue {
  available_funds: number
  connected: boolean
  account_type: 'PAPER' | 'LIVE'
}

// Map raw DB record to ComplianceResult
interface DbRecord {
  symbol: string
  shariah_status: string
  metrics: Record<string, any>
  timestamp: string
}

function fromDb(r: DbRecord): ComplianceResult {
  const m = r.metrics ?? {}
  return {
    symbol: r.symbol,
    is_compliant: r.shariah_status === 'COMPLIANT',
    verdict: r.shariah_status,
    reason: m.reason ?? null,
    debt_to_mkt_cap: m.debt_to_mkt_cap ?? 0,
    cash_to_mkt_cap: m.cash_to_mkt_cap ?? 0,
    impure_revenue_pct: m.impure_revenue_pct ?? 0,
    sector: m.sector ?? '—',
    country: m.country ?? null,
    company_name: m.company_name ?? null,
    data_source: m.data_source ?? null,
    data_as_of: m.data_as_of ?? null,
    data_stale: m.data_stale ?? false,
    sources_detail: m.sources_detail ?? [],
    last_checked: r.timestamp,
  }
}

const formatUSD = (v: number, compact = false) =>
  new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    notation: compact && Math.abs(v) >= 1000 ? 'compact' : 'standard',
    maximumFractionDigits: 2,
  }).format(v)

const _pct = (v: number) => `${(v * 100).toFixed(2)}%`

const formatPnL = (v: number) => {
  const formatted = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(v))
  return v >= 0 ? `+${formatted}` : `-${formatted}`
}

const pnlClass = (v: number) => (v >= 0 ? 'text-brand-success' : 'text-brand-danger')

const relativeTime = (iso: string | null) => {
  if (!iso) return null
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  const hours = Math.floor(diff / 3_600_000)
  const days = Math.floor(diff / 86_400_000)
  if (mins < 2) return 'just now'
  if (mins < 60) return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}

const ComplianceDetail: React.FC<{
  result: ComplianceResult
  colSpan: number
  onVerify?: (symbol: string) => void
}> = ({
  result,
  colSpan,
  onVerify,
}) => {
  const debtPass = result.debt_to_mkt_cap < 0.33
  const cashPass = result.cash_to_mkt_cap < 0.33
  const impurePass = result.impure_revenue_pct < 0.05

  return (
    <tr>
      <td colSpan={colSpan} className="px-4 pb-4 pt-0 bg-brand-base/50">
        <div className="border border-brand-divider rounded-lg p-4 space-y-4">
          {/* Header row */}
          <div className="flex flex-wrap items-center gap-4 text-xs text-brand-light/70">
            <span>
              Sector: <strong className="text-brand-light">{result.sector}</strong>
            </span>
            {result.company_name && (
              <span>
                Company: <strong className="text-brand-light">{result.company_name}</strong>
              </span>
            )}
            {result.data_source && (
              <span>
                Data: <strong className="text-brand-light">{result.data_source}</strong>
              </span>
            )}
            {result.data_as_of && (
              <span className={result.data_stale ? 'text-brand-warning' : ''}>
                {result.data_stale && <AlertTriangle size={11} className="inline mr-1" />}
                Filing: <strong>{result.data_as_of}</strong>
                {result.data_stale && ' (stale)'}
              </span>
            )}
            {result.last_checked && (
              <span>
                Last checked:{' '}
                <strong className="text-brand-light">{relativeTime(result.last_checked)}</strong>
              </span>
            )}
          </div>

          {/* AAOIFI ratio bars */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <RatioBar
              label="Debt / Market Cap"
              value={result.debt_to_mkt_cap}
              limit={0.33}
              pass={debtPass}
            />
            <RatioBar
              label="Cash / Market Cap"
              value={result.cash_to_mkt_cap}
              limit={0.33}
              pass={cashPass}
            />
            <RatioBar
              label="Impure Revenue"
              value={result.impure_revenue_pct}
              limit={0.05}
              pass={impurePass}
            />
          </div>

          {/* Thresholds note */}
          <p className="text-xs text-brand-light/70">
            AAOIFI thresholds: Debt &lt; 33% · Cash &lt; 33% · Impure Revenue &lt; 5% of market cap
          </p>

          {/* Source badges */}
          {result.sources_detail.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {result.sources_detail.map((s, i) => (
                <div
                  key={i}
                  title={s.note ?? ''}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded border text-xs ${SOURCE_COLORS[s.source] ?? 'bg-brand-base text-brand-light/70 border-brand-divider'}`}
                >
                  <span className="font-semibold">{s.source}</span>
                  <span className={`font-bold ${verdictColor(s.verdict)}`}>{s.verdict}</span>
                  {s.note && (
                    <span className="text-brand-light/70 hidden sm:inline">· {s.note}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Fail reason */}
          {result.reason && (
            <div className="flex gap-2 p-2 bg-brand-danger/10 border border-brand-danger/30 rounded text-xs text-brand-danger">
              <XCircle size={13} className="shrink-0 mt-0.5" />
              <span>{result.reason}</span>
            </div>
          )}

          {/* Manual verify button */}
          {result.verdict !== 'COMPLIANT' && onVerify && (
            <button
              onClick={() => onVerify(result.symbol)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-brand-primary/30 bg-brand-primary/5 hover:bg-brand-primary/10 text-xs font-bold text-brand-primary transition-colors"
            >
              <ShieldCheck size={14} />
              Mark as Halal (90 days)
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

const SystemHealth: React.FC<{ health: any }> = ({ health }) => {
  const [expandedLoop, setExpandedLoop] = useState<string | null>(null)
  if (!health) return null
  return (
    <CardGrid cols={4} className="mb-8">
      {Object.entries(health)
        .filter(([, data]) => data !== null && typeof data === 'object' && 'status' in data)
        .map(([name, data]: [string, any]) => {
          const isError = data.status === 'error'
          return (
            <div
              key={name}
              className={`card p-4 flex flex-col gap-2 min-h-[92px] ${isError ? 'cursor-pointer hover:border-brand-danger/40' : ''}`}
              onClick={() => isError ? setExpandedLoop(expandedLoop === name ? null : name) : undefined}
            >
              <div className="flex justify-between items-start gap-2">
                <Eyebrow as="h3" className="!tracking-wider truncate">{name.replace(/_/g, ' ')}</Eyebrow>
                <AppTooltip
                  text={
                    ['running', 'ok', 'waiting'].includes(data.status)
                      ? data.status === 'waiting'
                        ? 'Waiting for IBKR connection before starting.'
                        : 'Background task is alive and running normally.'
                      : 'Task encountered an error or stopped unexpectedly.'
                  }
                  position="bottom"
                  width="w-48"
                >
                  <Badge
                    variant={
                      data.status === 'running' || data.status === 'ok'
                        ? 'success'
                        : data.status === 'waiting'
                          ? 'warning'
                          : 'destructive'
                    }
                    className="h-4 text-[9px] px-1.5 cursor-help"
                  >
                    {(data.status ?? 'unknown').toUpperCase()}
                  </Badge>
                </AppTooltip>
              </div>
              <Text variant="tiny" as="div" className="flex items-center gap-1">
                <TextTip text="The last time this loop woke up and actually executed a task or trade.">
                  <span className="opacity-70">Last Run:</span>
                </TextTip>{' '}
                <span className="text-brand-light t-num">{relativeTime(data.last_run) || 'Never'}</span>
              </Text>
              {data.next_retry && (
                <Text variant="tiny" className="!text-brand-warning/80">
                  Retries {relativeTime(data.next_retry)}
                </Text>
              )}
              {isError && expandedLoop === name && data.last_error && (
                <div className="p-2 bg-brand-danger/10 border border-brand-danger/20 rounded text-[10px] font-mono text-brand-danger break-all">
                  {String(data.last_error)}
                </div>
              )}
              {isError && (
                <Text variant="tiny" className="!text-brand-danger/60">
                  Click to {expandedLoop === name ? 'hide' : 'show'} error
                </Text>
              )}
            </div>
          )
        })}
    </CardGrid>
  )
}

const AccountTypeBadge: React.FC<{ type: PortfolioValue['account_type'] }> = ({ type }) => {
  const isPaper = type === 'PAPER'
  return (
    <div
      className={`px-3 py-1 rounded-full border flex items-center gap-1.5 shadow-sm t-eyebrow !tracking-tighter whitespace-nowrap shrink-0 ${
        isPaper
          ? 'bg-brand-warning/10 border-brand-warning/30 !text-brand-warning'
          : 'bg-brand-success/10 border-brand-success/30 !text-brand-success'
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${isPaper ? 'bg-brand-warning animate-pulse' : 'bg-brand-success'}`}
      />
      {type} ACCOUNT
    </div>
  )
}

const ExposureDonutChart: React.FC<{
  data: any[]
  label: string
  icon: React.ReactNode
  colors: string[]
  warnThreshold?: number
  onAction?: () => void
  actionLabel?: string
  actionPending?: boolean
  actionPicks?: { symbol: string; country: string; score: number; current_share_pct: number }[]
}> = ({ data, label, icon, colors, warnThreshold, onAction, actionLabel, actionPending, actionPicks }) => {
  const topEntry = data[0]
  const concentrated = warnThreshold != null && topEntry && topEntry.value >= warnThreshold
  const ct = chartTheme()
  return (
  <div className={`card p-5 flex flex-col h-full ${concentrated ? 'border border-brand-warning/50' : ''}`}>
    <InfoRow className="mb-3">
      {icon}
      <h3 className="text-xs font-bold uppercase tracking-widest text-brand-light/70">{label}</h3>
    </InfoRow>
    <div className="h-[160px] w-full shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <RePieChart>
          <Pie
            data={data}
            innerRadius={52}
            outerRadius={72}
            paddingAngle={4}
            dataKey="value"
            activeShape={(props: any) => (
              <Sector
                cx={props.cx} cy={props.cy}
                innerRadius={props.innerRadius} outerRadius={props.outerRadius}
                startAngle={props.startAngle} endAngle={props.endAngle}
                fill={props.fill}
              />
            )}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Pie>
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const { name, value } = payload[0].payload
              return (
                <div style={{ background: ct.surface, border: `1px solid ${ct.grid}`, borderRadius: 6, padding: '5px 10px', fontSize: 11, color: ct.text }}>
                  {name}: <strong>{(value * 100).toFixed(1)}%</strong>
                </div>
              )
            }}
          />
        </RePieChart>
      </ResponsiveContainer>
    </div>
    <div className="mt-3 overflow-y-auto max-h-[140px] space-y-1.5 pr-1 scrollbar-thin">
      {data.map((entry, i) => (
        <div key={entry.name} className={`flex items-center justify-between text-[11px] ${entry.name === 'Unknown' ? 'opacity-40' : ''}`}>
          <div className="flex items-center gap-1.5 min-w-0">
            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: colors[i % colors.length] }} />
            <span className={`truncate ${entry.name === 'Unknown' ? 'italic text-brand-light/60' : 'text-brand-light/80'}`}>{entry.name === 'Unknown' ? 'Unknown (no data)' : entry.name}</span>
          </div>
          <span className="font-mono text-brand-light/60 ml-2 shrink-0">
            {(entry.value * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
    {concentrated && topEntry && (
      <div className="mt-2 space-y-2">
        <div className="flex items-center gap-1.5 rounded bg-brand-warning/10 px-2 py-1.5">
          <AlertTriangle size={10} className="text-brand-warning shrink-0" />
          <span className="text-[10px] text-brand-warning flex-1">
            {topEntry.name} {(topEntry.value * 100).toFixed(0)}% — bot boosting non-{topEntry.name} signals
          </span>
        </div>
        {onAction && (
          <Button
            size="xs"
            variant="outline"
            onClick={onAction}
            disabled={actionPending}
            className="w-full text-[10px] h-7 border-brand-primary/40 text-brand-primary hover:bg-brand-primary/10 gap-1.5"
          >
            {actionPending ? (
              <div className="w-3 h-3 border-2 border-brand-primary/30 border-t-brand-primary rounded-full animate-spin" />
            ) : (
              <Zap size={11} />
            )}
            {actionLabel ?? 'Find Diversification Picks'}
          </Button>
        )}
        {actionPicks && actionPicks.length > 0 && (
          <div className="rounded border border-brand-divider/40 divide-y divide-brand-divider/20">
            {actionPicks.map((p) => (
              <div key={p.symbol} className="flex items-center justify-between px-2 py-1.5 text-[11px]">
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-brand-light">{p.symbol}</span>
                  <span className="text-brand-light/50">{p.country}</span>
                </div>
                <span className="font-mono text-brand-success">{p.score}pt</span>
              </div>
            ))}
          </div>
        )}
        {actionPicks && actionPicks.length === 0 && (
          <p className="text-[10px] text-brand-light/50 text-center py-1">No diversification picks found in watchlist</p>
        )}
      </div>
    )}
  </div>
  )
}

const SECTOR_COLORS = ['#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444', '#06b6d4', '#f97316', '#ec4899', '#84cc16', '#14b8a6', '#8b5cf6', '#f43f5e', '#0ea5e9']
const COUNTRY_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#a855f7', '#ef4444', '#06b6d4', '#f97316', '#ec4899']

const SectorExposureChart: React.FC<{
  data: any[]
  onDiversify?: () => void
  diversifyPending?: boolean
  diversifyPicks?: { symbol: string; sector: string; score: number; current_share_pct: number }[] | null
}> = ({ data, onDiversify, diversifyPending, diversifyPicks }) => (
  <ExposureDonutChart
    data={data}
    label="Sector Exposure"
    icon={<Briefcase size={15} className="text-brand-primary" />}
    colors={SECTOR_COLORS}
    warnThreshold={0.65}
    onAction={onDiversify}
    actionLabel="Diversify Sectors"
    actionPending={diversifyPending}
    actionPicks={diversifyPicks ? diversifyPicks.map((p) => ({ symbol: p.symbol, country: p.sector, score: p.score, current_share_pct: p.current_share_pct })) : undefined}
  />
)

const CountryExposureChart: React.FC<{
  data: any[]
  onDiversify?: () => void
  diversifyPending?: boolean
  diversifyPicks?: { symbol: string; country: string; score: number; current_share_pct: number }[] | null
}> = ({ data, onDiversify, diversifyPending, diversifyPicks }) => (
  <ExposureDonutChart
    data={data}
    label="Country Exposure"
    icon={<Globe size={15} className="text-brand-primary" />}
    colors={COUNTRY_COLORS}
    warnThreshold={0.65}
    onAction={onDiversify}
    actionLabel="Diversify Now"
    actionPending={diversifyPending}
    actionPicks={diversifyPicks ?? undefined}
  />
)

const EquityCurveCard: React.FC<{ data: HistorySnapshot[] }> = ({ data }) => {
  const last30 = data.slice(-30)
  if (last30.length < 2) return null
  const ct = chartTheme()

  const fmt = (ts: string) =>
    new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

  return (
    <div className="card p-5 mb-8">
      <InfoRow className="mb-4">
        <TrendingUp size={16} className="text-brand-primary" />
        <h3 className="text-xs font-bold uppercase tracking-widest text-brand-light/70">
          Portfolio Value — Last 30 Days
        </h3>
      </InfoRow>
      <div className="h-[180px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={last30} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} vertical={false} />
            <XAxis
              dataKey="timestamp"
              tickFormatter={fmt}
              tick={{ fontSize: 10, fill: ct.axis }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={['auto', 'auto']}
              orientation="right"
              tick={{ fontSize: 10, fill: ct.axis }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              width={44}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: ct.surface,
                border: `1px solid ${ct.grid}`,
                borderRadius: '8px',
              }}
              labelFormatter={(label) => fmt(String(label))}
              labelStyle={{ color: ct.axis, fontSize: 11 }}
              itemStyle={{ fontSize: 11, fontWeight: 'bold', color: ct.primary }}
              formatter={(v: number) => [
                `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
                'Portfolio Value',
              ]}
            />
            <Line
              type="monotone"
              dataKey="total_value"
              stroke={ct.primary}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: ct.primary }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

const Sparkline: React.FC<{ data: number[]; positive: boolean; w?: number; h?: number }> = ({ data, positive, w = 120, h = 36 }) => {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 4) - 2}`)
  const color = positive ? '#22c55e' : '#ef4444'
  const fillPts = `${pts[0].split(',')[0]},${h} ${pts.join(' ')} ${pts[pts.length - 1].split(',')[0]},${h}`
  return (
    <svg width={w} height={h} className="overflow-visible">
      <defs>
        <linearGradient id={`sg-${positive}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={fillPts} fill={`url(#sg-${positive})`} />
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

type PortfolioSummary = {
  connected: boolean
  account_type: 'PAPER' | 'LIVE'
  total_value: number | null
  cost_basis: number | null
  cash_available: number | null
  unrealized_pnl: number | null
  return_pct: number | null
  purity: number | null
  purification_due: number | null
  compliance_pct: number | null
  zakat_estimate: number | null
  sector_count: number | null
  max_impure_revenue_pct: number | null
  halal_label: string | null
  compliance_label: string | null
  sector_label: string | null
  purify_label: string | null
}

const SimplePortfolioSummary: React.FC<{ summary: PortfolioSummary; historyValues?: number[] }> = ({ summary, historyValues }) => {
  const value = summary.total_value ?? 0
  const cashAvailable = summary.cash_available ?? 0
  const costBasis = summary.cost_basis ?? 0
  const unrealizedPnl = summary.unrealized_pnl ?? 0
  const returnPct = summary.return_pct ?? 0
  const purity = summary.purity ?? null
  const purificationDue = summary.purification_due ?? 0
  const compliancePct = summary.compliance_pct ?? null
  const zakatEstimate = summary.zakat_estimate ?? 0
  const sectorCount = summary.sector_count ?? null
  const maxImpure = summary.max_impure_revenue_pct ?? null

  const pnlPositive = unrealizedPnl >= 0
  const accentColor = pnlPositive ? 'rgba(34,197,94,0.07)' : 'rgba(239,68,68,0.07)'

  const isHealthy = purity !== null && purity >= 0.98
  const hasPurification = purificationDue > 0
  const halalSub = purity === null
    ? 'no data'
    : (hasPurification ? `purify ${formatUSD(purificationDue)}` : (summary.halal_label ?? 'all clear'))
  const complianceSub = summary.compliance_label ?? 'no data'
  const sectorSub = summary.sector_label ?? 'no data'
  const purifySub = summary.purify_label ?? 'no data'

  const Stat = ({
    label, value: val, sub, color, tip, href,
  }: { label: string; value: string; sub?: string; color?: string; tip: string; href?: string }) => {
    const inner = (
      <div
        title={tip}
        className="py-4 px-2 text-center flex flex-col gap-1 w-full h-full justify-between items-center min-h-[88px] cursor-help"
      >
        <p className="t-eyebrow">{label}</p>
        <p className={`t-stat ${color ?? 'text-brand-light'}`}>{val}</p>
        <p className="t-tiny opacity-60 min-h-[14px]">{sub ?? ' '}</p>
      </div>
    )
    return href
      ? <Link to={href} className="hover:bg-brand-primary/5 transition-colors duration-150 flex w-full">{inner}</Link>
      : <div className="hover:bg-brand-primary/5 transition-colors duration-150 flex w-full">{inner}</div>
  }

  return (
    <div className="card p-0 mb-6 overflow-hidden">
      <header
        className="px-6 pt-6 pb-5"
        style={{ backgroundImage: `linear-gradient(135deg, ${accentColor} 0%, transparent 55%)` }}
      >
        <p className="t-eyebrow !tracking-[0.25em] mb-3">Total Portfolio</p>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="t-hero leading-none">{formatUSD(value)}</span>
          {historyValues && historyValues.length >= 2 && (
            <Sparkline data={historyValues} positive={pnlPositive} w={80} h={28} />
          )}
          <TextTip text="Unrealized gain or loss on open positions vs. what you paid for them.">
            <span className={`inline-flex items-center gap-1.5 text-sm font-bold px-3 py-1.5 rounded-xl leading-none ${
              pnlPositive ? 'bg-brand-success/12 text-brand-success border border-brand-success/20' : 'bg-brand-danger/12 text-brand-danger border border-brand-danger/20'
            }`}>
              {pnlPositive ? '▲' : '▼'} {formatUSD(Math.abs(unrealizedPnl), true)}
              <span className="opacity-60 font-normal text-[11px] t-num">unrealized · {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(2)}% vs cost</span>
            </span>
          </TextTip>
        </div>
      </header>

      {/* Stats row — elevated tray, all 7 stats unified */}
      <div className="bg-brand-elevated/60 border-t border-brand-divider/50 grid grid-cols-7 divide-x divide-brand-divider/40 overflow-x-auto">
        <Stat label="Invested" value={formatUSD(costBasis, true)} sub={value > 0 ? `${((costBasis / value) * 100).toFixed(0)}% of portfolio` : '—'} tip="Total amount currently invested in open positions." />
        <Stat label="Cash" value={formatUSD(cashAvailable, true)} sub={value > 0 ? `${((cashAvailable / value) * 100).toFixed(0)}% available` : '—'} tip="Uninvested cash ready to deploy on the next signal." />
        <Stat label="Halal" value={purity === null ? '—' : `🌙 ${(purity * 100).toFixed(0)}%`} sub={halalSub} color={purity === null ? undefined : (isHealthy ? 'text-brand-success' : 'text-brand-warning')} tip="How much of your portfolio income comes from Halal sources." />
        <Stat label="Compliance" value={compliancePct !== null ? `${compliancePct.toFixed(0)}%` : '—'} sub={complianceSub} color={compliancePct === null ? undefined : (compliancePct >= 100 ? 'text-brand-success' : 'text-brand-warning')} tip="Percentage of holdings that pass Shariah screening." />
        <Stat label="Zakat" value={formatUSD(zakatEstimate, true)} sub={value > 0 ? 'est. annual' : 'no data'} color="text-brand-accent" tip="Estimated Zakat due — 2.5% of total portfolio value. Tap for details." href="/zakat" />
        <Stat label="Sectors" value={sectorCount === null || sectorCount === 0 ? '—' : String(sectorCount)} sub={sectorSub} tip="Number of distinct industry sectors in your portfolio." />
        <Stat label="Purify" value={maxImpure === null ? '—' : (maxImpure > 0 ? `${(maxImpure * 100).toFixed(1)}%` : '$0')} sub={purifySub} color={maxImpure === null ? undefined : (maxImpure > 0 ? 'text-brand-danger' : 'text-brand-success')} tip="Max impure revenue % across holdings. Donate this share of profits from affected positions." />
      </div>
    </div>
  )
}

const PortfolioHistoryChart: React.FC<{ data: any[]; showNet: boolean; currentValue: number }> = ({
  data,
  showNet,
  currentValue,
}) => {
  if (!data || data.length < 2) {
    return (
      <div className="card flex flex-col items-center justify-center text-brand-light/40 text-sm min-h-[260px]">
        <TrendingUp size={28} className="mb-3 opacity-30" />
        <p className="font-medium">No history yet</p>
        <p className="text-xs mt-1 opacity-60">Portfolio snapshots record every hour while connected.</p>
      </div>
    )
  }

  const ct = chartTheme()
  // Back-calculate actual dollar values from normalized base-100 data
  const key = showNet ? 'net_purified_value' : 'total_value'
  const lastNorm = data[data.length - 1][key] as number
  const scale = lastNorm > 0 ? currentValue / lastNorm : 1

  // Find FIRST snapshot that has benchmark data — use as anchor for $ projection.
  // Many early snapshots may have empty benchmarks dict (yfinance gap, weekends, etc.)
  const firstBenchRow = data.find((d) => d.benchmarks && Object.keys(d.benchmarks).length > 0)
  const benchAnchor = firstBenchRow ? (firstBenchRow[key] as number) * scale : (data[0][key] as number) * scale

  // For each series, locate the first non-null normalized value to rebase
  const seriesKeys = ['SPUS', 'SPY', 'VTI', 'BRK-B'] as const
  const firstBenchVal: Record<string, number | null> = {}
  for (const k of seriesKeys) {
    const found = data.find((d) => d.benchmarks?.[k] != null)
    firstBenchVal[k] = found ? (found.benchmarks![k] as number) : null
  }

  const chartData = data.map((d) => {
    const benchs = d.benchmarks ?? {}
    const projectBench = (k: typeof seriesKeys[number]) => {
      const v = benchs[k]
      const base = firstBenchVal[k]
      if (v == null || base == null || base === 0) return null
      // Bench value normalized so series starts at benchAnchor (portfolio dollar value when bench data begins)
      return (v / base) * benchAnchor
    }
    return {
      ...d,
      _dollars: (d[key] as number) * scale,
      _spus: projectBench('SPUS'),
      _spy: projectBench('SPY'),
      _vti: projectBench('VTI'),
      _brk: projectBench('BRK-B'),
    }
  })

  const firstVal = chartData[0]._dollars
  const lastVal = chartData[chartData.length - 1]._dollars
  const isUp = lastVal >= firstVal
  const color = isUp ? '#22c55e' : '#ef4444'

  const pctChange = firstVal > 0 ? ((lastVal - firstVal) / firstVal) * 100 : 0

  const benchSeries = [
    { key: '_spus', label: 'SPUS',  color: '#a78bfa' },
    { key: '_spy',  label: 'SPY',   color: '#60a5fa' },
    { key: '_vti',  label: 'VTI',   color: '#facc15' },
    { key: '_brk',  label: 'BRK-B', color: '#f472b6' },
  ] as const

  // Pct return per benchmark: use first non-null and last non-null in series
  const benchReturns = benchSeries.map((b) => {
    const firstNonNull = chartData.find((d) => d[b.key] != null)?.[b.key] as number | undefined
    const lastNonNull = [...chartData].reverse().find((d) => d[b.key] != null)?.[b.key] as number | undefined
    const pct = (firstNonNull && lastNonNull) ? ((lastNonNull - firstNonNull) / firstNonNull) * 100 : null
    return { ...b, pct, hasData: firstNonNull != null && lastNonNull != null }
  })

  return (
    <div className="card p-0 overflow-hidden">
      <header className="px-6 pt-5 pb-3 flex items-start justify-between gap-4">
        <div>
          <p className="t-eyebrow !tracking-[0.25em] mb-1.5">Portfolio History</p>
          <div className="flex items-center gap-2.5">
            <span className="text-xl font-bold t-num text-brand-light">{formatUSD(lastVal, true)}</span>
            <span className={`inline-flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-lg border ${isUp ? 'text-brand-success bg-brand-success/10 border-brand-success/20' : 'text-brand-danger bg-brand-danger/10 border-brand-danger/20'}`}>
              {isUp ? '▲' : '▼'} {Math.abs(pctChange).toFixed(2)}%
              <span className="font-normal opacity-50 text-[10px] t-num">this period</span>
            </span>
          </div>
        </div>
        <span className="t-tiny mt-1 shrink-0">
          {showNet ? 'After purification' : 'Gross value'}
        </span>
      </header>
      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.2} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} vertical={false} />
            <XAxis
              dataKey="timestamp"
              tick={{ fontSize: 9, fill: ct.axis }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => {
                const d = new Date(v)
                return isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
              }}
              interval="preserveStartEnd"
              minTickGap={50}
            />
            <YAxis
              domain={['auto', 'auto']}
              orientation="right"
              tick={{ fontSize: 9, fill: ct.axis }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => formatUSD(v, true)}
              width={60}
            />
            <Tooltip
              contentStyle={{ backgroundColor: ct.surface, border: `1px solid ${ct.grid}`, borderRadius: '10px', fontSize: '12px', color: ct.text }}
              labelFormatter={(v) => {
                const d = new Date(v)
                return isNaN(d.getTime()) ? v : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
              }}
              labelStyle={{ color: ct.axis, marginBottom: '4px' }}
              formatter={(v: number, name: string) => {
                const labelMap: Record<string, string> = {
                  _dollars: 'Portfolio',
                  _spus: 'SPUS (halal ETF)',
                  _spy: 'SPY (S&P 500)',
                  _vti: 'VTI (Vanguard total)',
                  _brk: 'BRK-B (Berkshire)',
                }
                return [v != null ? formatUSD(v) : '—', labelMap[name] ?? name]
              }}
            />
            <Area
              type="monotone"
              dataKey="_dollars"
              stroke={color}
              strokeWidth={2.5}
              fill="url(#chartGrad)"
              dot={false}
              activeDot={{ r: 4, fill: color, strokeWidth: 0 }}
            />
            {benchSeries.map((b) => (
              <Line
                key={b.key}
                type="monotone"
                dataKey={b.key}
                stroke={b.color}
                strokeWidth={2}
                strokeDasharray="5 4"
                strokeOpacity={0.85}
                dot={false}
                activeDot={{ r: 4, fill: b.color, strokeWidth: 0 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Benchmark legend */}
      <div className="px-6 pb-4 flex flex-wrap items-center gap-3 pt-1 border-t border-brand-divider/30 mt-1">
        <span className="text-[10px] uppercase tracking-widest text-brand-light/40 font-bold mr-1">vs</span>
        {benchReturns.filter((b) => b.hasData).map((b) => {
          const positive = (b.pct ?? 0) >= 0
          return (
            <span key={b.key} className="inline-flex items-center gap-1.5">
              <span className="inline-block w-3 h-[2px]" style={{ backgroundImage: `repeating-linear-gradient(to right, ${b.color} 0, ${b.color} 4px, transparent 4px, transparent 7px)` }} />
              <span className="text-[11px] font-semibold text-brand-light/80">{b.label}</span>
              {b.pct !== null && (
                <span className={`text-[10px] font-mono font-bold ${positive ? 'text-brand-success' : 'text-brand-danger'}`}>
                  {positive ? '+' : ''}{b.pct.toFixed(2)}%
                </span>
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}

const MultiFactorBreakdown: React.FC<{ f: number; t: number; s: number }> = ({ f, t, s }) => {
  // Balanced weights (33/33/33) for dashboard summary
  const Factor = ({ label, val, color }: { label: string; val: number; color: string }) => (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between text-[7px] font-bold uppercase tracking-widest text-brand-light/40">
        <span>{label}</span>
      </div>
      <div className="h-0.5 bg-brand-divider rounded-full overflow-hidden w-8">
        <div className={`h-full ${color}`} style={{ width: `${(val / 33) * 100}%` }} />
      </div>
    </div>
  )

  return (
    <div className="flex gap-1.5">
      <Factor label="Quality" val={f} color="bg-brand-primary" />
      <Factor label="Momentum" val={t} color="bg-brand-success" />
    </div>
  )
}

const TwapJobsPanel: React.FC<{ twapJobs: any[] }> = ({ twapJobs }) => {
  const qc = useQueryClient()

  const cancel = useMutation({
    mutationFn: (id: number) =>
      fetch(ROUTES.TRADES_TWAP_CANCEL(id), {
        method: 'POST',
        headers: { 'X-Api-Key': API_KEY },
      }).then((r) => {
        if (!r.ok) throw new Error(`Cancel failed: HTTP ${r.status}`)
        return r.json()
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['twap-jobs'] })
      toast.success('TWAP job cancelled successfully')
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Failed to cancel TWAP job')
    },
  })

  return (
    <div className="mt-6">
      <h3 className="text-sm font-semibold text-brand-light mb-2">
        TWAP In Progress ({twapJobs.length})
      </h3>
      <div className="overflow-x-auto rounded-lg border border-brand-divider/40">
        <table className="w-full text-xs text-brand-muted">
          <thead>
            <tr className="border-b border-brand-divider/40 text-left">
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Progress</th>
              <th className="px-3 py-2">Slice Qty</th>
              <th className="px-3 py-2">Interval</th>
              <th className="px-3 py-2">Exchange</th>
              <th className="px-3 py-2">Started</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {twapJobs.map((job: any) => (
              <tr key={job.id} className="border-b border-brand-divider/20 last:border-0">
                <td className="px-3 py-2 font-medium text-brand-light">{job.symbol}</td>
                <td className="px-3 py-2">
                  <span className="text-brand-light">{job.slices_submitted}</span>
                  <span className="text-brand-muted">/{job.n_slices}</span>
                  <div className="mt-1 h-1 w-24 bg-brand-divider/40 rounded-full">
                    <div
                      className="h-1 bg-green-500 rounded-full"
                      style={{ width: `${(job.slices_submitted / job.n_slices) * 100}%` }}
                    />
                  </div>
                </td>
                <td className="px-3 py-2">{job.slice_qty?.toFixed(4)}</td>
                <td className="px-3 py-2">{job.interval_secs}s</td>
                <td className="px-3 py-2">{job.exchange}</td>
                <td className="px-3 py-2">{new Date(job.created_at).toLocaleTimeString()}</td>
                <td className="px-3 py-2">
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => cancel.mutate(job.id)}
                    disabled={cancel.isPending}
                    title="Stop future slices. Already-submitted IBKR orders remain active."
                  >
                    {cancel.isPending ? '…' : 'Cancel'}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[10px] text-brand-muted/60">
        Cancel stops future slices only. Already-submitted IBKR orders stay active — cancel those via Open Orders if needed.
      </p>
    </div>
  )
}

const Dashboard = () => {
  const qc = useQueryClient()
  useTheme() // re-render chart subtree when the theme knob flips
  const { trades, audits, isConnected, systemHealth, tickerUpdates, twapJobs } = useTrading()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [complianceResults, setComplianceResults] = useState<Record<string, ComplianceResult>>({})
  const [checkingSymbols, setCheckingSymbols] = useState<Set<string>>(new Set())
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null)
  const [showNet, setShowNet] = useState(false)
  const [historyDays, setHistoryDays] = useState<7 | 30 | 90 | 'all'>(30)
  const [emergencyModalStep, setEmergencyModalStep] = useState<0 | 1 | 2>(0)
  const [emergencyPhrase, setEmergencyPhrase] = useState('')
  const [emergencyPin, setEmergencyPin] = useState('')
  const [emergencyRunning, setEmergencyRunning] = useState(false)
  const [emergencyResult, setEmergencyResult] = useState<{ liquidated: string[]; skipped: { symbol: string; error: string }[] } | null>(null)
  const [diversifyPicks, setDiversifyPicks] = useState<{ symbol: string; country: string; score: number; current_share_pct: number }[] | null>(null)
  const [sectorPicks, setSectorPicks] = useState<{ symbol: string; sector: string; score: number; current_share_pct: number }[] | null>(null)
  const [dismissedOnboarding, setDismissedOnboarding] = useState(() => localStorage.getItem('onboarding_dismissed') === '1')
  const { selectedAccountId } = useAccount()

  const handleManualVerify = async (symbol: string) => {
    try {
      const res = await fetch(ROUTES.COMPLIANCE_MANUAL_VERIFY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, source: 'Zoya App', note: `Verified via UI ${new Date().toISOString().slice(0, 10)}` }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      toast.success(`${symbol} marked as halal (90 days)`)
      // Re-screen to update DB record
      const screenRes = await fetch(ROUTES.COMPLIANCE_SCREEN(symbol))
      if (screenRes.ok) {
        const updated = await screenRes.json()
        setComplianceResults((prev) => ({ ...prev, [symbol]: { ...updated, last_checked: new Date().toISOString() } }))
      }
    } catch (e: any) {
      toast.error(`Failed: ${e.message}`)
    }
  }

  const { data: settingsData } = useQuery<{ trading_paused?: boolean; watchlist?: string[]; auto_compliance_check?: boolean }>({
    queryKey: ['settings-paused', selectedAccountId],
    queryFn: () => fetch(withAccount(ROUTES.SETTINGS, selectedAccountId)).then((r) => r.json()),
    refetchInterval: 30_000,
  })
  const tradingPaused = settingsData?.trading_paused ?? false

  const resumeMutation = useMutation({
    mutationFn: () =>
      fetch(withAccount(ROUTES.SETTINGS_RESUME, selectedAccountId), { method: 'POST' }).then((r) => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-paused'] })
      toast.success('Trading resumed')
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Failed to resume trading')
    },
  })

  const {
    data: portfolio = {
      available_funds: 0,
      connected: false,
      account_type: 'PAPER',
    } as PortfolioValue,
    isLoading: portfolioLoading,
  } = useQuery<PortfolioValue>({
    queryKey: ['portfolio-value', selectedAccountId],
    queryFn: () => validatedFetch(withAccount(ROUTES.PORTFOLIO_VALUE, selectedAccountId), PortfolioValueSchema),
    refetchInterval: 60_000,
  })

  const { data: positions = [] } = useQuery<Position[]>({
    queryKey: ['positions', selectedAccountId],
    queryFn: () => validatedFetchArray(withAccount(ROUTES.PORTFOLIO_POSITIONS, selectedAccountId), PositionSchema),
    refetchInterval: 60_000,
  })

  const { data: pnlSummary, isLoading: pnlLoading } = useQuery<PnLSummary>({
    queryKey: ['portfolio-pnl', selectedAccountId],
    queryFn: () => validatedFetch(withAccount(ROUTES.PORTFOLIO_PNL, selectedAccountId), PnLSummarySchema),
    refetchInterval: 60_000,
  })

  const { data: portfolioSummary } = useQuery<PortfolioSummary>({
    queryKey: ['portfolio-summary', selectedAccountId],
    queryFn: () => validatedFetch(withAccount(ROUTES.PORTFOLIO_SUMMARY, selectedAccountId), PortfolioSummarySchema),
    refetchInterval: 60_000,
  })

  const summaryFallback: PortfolioSummary = {
    connected: false,
    account_type: 'PAPER',
    total_value: null,
    cost_basis: null,
    cash_available: null,
    unrealized_pnl: null,
    return_pct: null,
    purity: null,
    purification_due: null,
    compliance_pct: null,
    zakat_estimate: null,
    sector_count: null,
    max_impure_revenue_pct: null,
    halal_label: null,
    compliance_label: null,
    sector_label: null,
    purify_label: null,
  }

  const { data: history = [] } = useQuery<HistorySnapshot[]>({
    queryKey: ['portfolio-history', selectedAccountId, historyDays],
    queryFn: () => {
      const url = historyDays === 'all'
        ? withAccount(ROUTES.PORTFOLIO_HISTORY, selectedAccountId)
        : withAccount(`${ROUTES.PORTFOLIO_HISTORY}?days=${historyDays}`, selectedAccountId)
      return validatedFetchArray(url, HistorySnapshotSchema)
    },
    refetchInterval: 300_000,
  })

  const { data: readiness } = useQuery<{
    ready: boolean
    port_type: string
    trade_count: number
    error_rate_pct: number | null
    gates: Record<string, boolean | string>
    blockers: string[]
    note: string | null
  }>({
    queryKey: ['system-readiness'],
    queryFn: () => fetch(ROUTES.SYSTEM_READINESS).then((r) => r.json()),
    refetchInterval: 60_000,
  })

  const { data: signals = [] } = useQuery<any[]>({
    queryKey: ['ai-signals'],
    queryFn: () => fetch(ROUTES.AI_SIGNALS).then((r) => r.json()),
    staleTime: 60_000,
  })

  // Build a realized P&L lookup keyed by symbol for the positions table
  const realizedBySymbol: Record<string, number> = {}
  const purifBySymbol: Record<string, number> = {}
  const halalPnlBySymbol: Record<string, number> = {}
  for (const p of pnlSummary?.positions ?? []) {
    realizedBySymbol[p.symbol] = p.realized_pnl
    purifBySymbol[p.symbol] = p.purification_cost
    halalPnlBySymbol[p.symbol] = p.halal_pnl
  }

  // Signal lookup for factor breakdown
  const signalMap: Record<string, any> = {}
  for (const s of signals) signalMap[s.symbol] = s

  // Calculate sector data for risk guard visualization
  const sectorDataMap: Record<string, number> = {}
  positions.forEach((p) => {
    const wsAudit = audits.find((a) => a.symbol === p.symbol)
    const dbResult = complianceResults[p.symbol]
    const rawSector = wsAudit?.sector || dbResult?.sector || 'Other'
    const sector = rawSector.split('/')[0].trim()
    sectorDataMap[sector] = (sectorDataMap[sector] || 0) + (p.market_value || 0)
  })
  const totalValForSector = Object.values(sectorDataMap).reduce((s, v) => s + v, 0)
  const sectorData = Object.entries(sectorDataMap)
    .map(([name, value]) => ({
      name,
      value: totalValForSector > 0 ? value / totalValForSector : 0,
    }))
    .sort((a, b) => b.value - a.value)

  const countryDataMap: Record<string, number> = {}
  positions.forEach((p) => {
    const dbResult = complianceResults[p.symbol]
    const wsAudit = audits.find((a) => a.symbol === p.symbol)
    const country = dbResult?.country || wsAudit?.country || 'Unknown'
    countryDataMap[country] = (countryDataMap[country] || 0) + (p.market_value || 0)
  })
  const totalValForCountry = Object.values(countryDataMap).reduce((s, v) => s + v, 0)
  const countryData = Object.entries(countryDataMap)
    .map(([name, value]) => ({
      name,
      value: totalValForCountry > 0 ? value / totalValForCountry : 0,
    }))
    .sort((a, b) => b.value - a.value)

  const rebalanceMutation = useMutation({
    mutationFn: () => fetch(ROUTES.PORTFOLIO_ALLOCATE, { method: 'POST' }).then((r) => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trades'] })
      toast.success('Rebalance triggered')
    },
    onError: () => {
      toast.error('Rebalance failed')
    },
  })

  const diversifyMutation = useMutation({
    mutationFn: () =>
      fetch(ROUTES.AI_DIVERSIFY, { method: 'POST', headers: { 'X-Api-Key': API_KEY } }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      }),
    onSuccess: (data) => {
      setDiversifyPicks(data)
      toast.success('AI diversification ideas generated')
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Failed to generate diversification ideas')
    },
  })

  const sectorDiversifyMutation = useMutation({
    mutationFn: () =>
      fetch(ROUTES.AI_DIVERSIFY_SECTOR, { method: 'POST', headers: { 'X-Api-Key': API_KEY } }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      }),
    onSuccess: (data) => {
      setSectorPicks(data)
      toast.success('AI sector diversification ideas generated')
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Failed to generate sector diversification ideas')
    },
  })

  const batchSellMutation = useMutation({
    mutationFn: (symbols: string[]) =>
      fetch(ROUTES.TRADES_BATCH_SELL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Api-Key': API_KEY },
        body: JSON.stringify({ symbols, account_id: selectedAccountId }),
      }).then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({}))
          throw new Error(err.detail ?? `HTTP ${r.status}`)
        }
        return r.json()
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['positions'] })
      qc.invalidateQueries({ queryKey: ['portfolio-pnl'] })
      setSelected(new Set())
      if (data.sold.length) toast.success(`Sold ${data.sold.join(', ')}`)
      if (data.skipped.length) toast.error(`Failed: ${data.skipped.map((s: any) => s.symbol).join(', ')}`)
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Batch sell failed')
    },
  })

  const exportCSV = () => {
    const rows = positions.map((p) => {
      const pnlEntry = pnlSummary?.positions.find((pp) => pp.symbol === p.symbol)
      return [
        p.symbol,
        p.quantity,
        p.avg_cost.toFixed(2),
        (p.market_value ?? 0).toFixed(2),
        (p.unrealized_pnl ?? 0).toFixed(2),
        (pnlEntry?.realized_pnl ?? 0).toFixed(2),
        (pnlEntry?.halal_pnl ?? 0).toFixed(2),
        complianceResults[p.symbol]?.verdict ?? '',
      ].join(',')
    })
    const csv = ['Symbol,Quantity,AvgCost,MarketValue,UnrealizedPnL,RealizedPnL,HalalPnL,Compliance', ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `positions_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Positions exported to CSV')
  }

  // Load stored compliance results from DB on mount
  useEffect(() => {
    fetch(ROUTES.COMPLIANCE_POSITIONS)
      .then((r) => (r.ok ? r.json() : []))
      .then((records: DbRecord[]) => {
        const map: Record<string, ComplianceResult> = {}
        for (const r of records) map[r.symbol] = fromDb(r)
        setComplianceResults(map)
      })
      .catch(() => {})
  }, [])

  const [flashSymbols, setFlashSymbols] = useState<Set<string>>(new Set())

  useEffect(() => {
    const updated = Object.keys(tickerUpdates)
    if (updated.length === 0) return
    setFlashSymbols(new Set(updated))
    const t = setTimeout(() => setFlashSymbols(new Set()), 1200)
    return () => clearTimeout(t)
  }, [tickerUpdates])

  const totalMarketValue = positions.reduce((s, p) => {
    const tick = tickerUpdates[p.symbol]
    const lp = tick?.last && !isNaN(tick.last) ? tick.last : null
    return s + (lp != null ? lp * p.quantity : (p.market_value ?? p.quantity * p.avg_cost))
  }, 0)
  const totalPnl = positions.reduce((s, p) => {
    const tick = tickerUpdates[p.symbol]
    const lp = tick?.last && !isNaN(tick.last) ? tick.last : null
    return s + (lp != null ? (lp - p.avg_cost) * p.quantity : (p.unrealized_pnl ?? 0))
  }, 0)
  const totalCostBasis = positions.reduce((s, p) => s + p.quantity * p.avg_cost, 0)
  const returnPct = totalCostBasis > 0 ? (totalPnl / totalCostBasis) * 100 : 0
  const portfolioValue = portfolio.available_funds

  const toggleSelect = (symbol: string) =>
    setSelected((prev) => {
      const n = new Set(prev)
      n.has(symbol) ? n.delete(symbol) : n.add(symbol)
      return n
    })

  const toggleSelectAll = () =>
    setSelected(
      selected.size === positions.length ? new Set() : new Set(positions.map((p) => p.symbol)),
    )

  const checkCompliance = async (symbols: string[]) => {
    if (!symbols.length) return
    setCheckingSymbols(new Set(symbols))
    try {
      const res = await fetch(ROUTES.COMPLIANCE_SCREEN_POSITIONS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const results = await res.json()
      const now = new Date().toISOString()
      setComplianceResults((prev) => {
        const next = { ...prev }
        for (const r of results) {
          next[r.symbol] = {
            ...r,
            sector: r.sector ?? '—',
            last_checked: now,
          }
        }
        return next
      })
    } catch (e) {
      console.error('Compliance check failed:', e)
    } finally {
      setCheckingSymbols(new Set())
    }
  }

  const allSelected = positions.length > 0 && selected.size === positions.length
  const isChecking = checkingSymbols.size > 0
  const colCount = 6

  return (
    <Page>
      <PageHeader>
        <div className="flex flex-col gap-1">
          <ActionRow>
            <h1 className="heading-1 mb-0">
              <ShieldCheck className="text-brand-success" />
              IBKR Shariah Trader
            </h1>
            <AccountTypeBadge type={portfolio.account_type} />
          </ActionRow>
          <p className="text-brand-light/70">Ironclad Portfolio Monitoring</p>
        </div>
        <div className="flex flex-wrap items-center gap-4 self-start">
          <Button
            variant="outline"
            size="sm"
            onClick={() => rebalanceMutation.mutate()}
            disabled={rebalanceMutation.isPending}
            className="text-xs h-9 border-brand-primary/50 text-brand-primary hover:bg-brand-primary/10"
          >
            {rebalanceMutation.isPending ? (
              <RefreshCw size={14} className="animate-spin mr-2" />
            ) : (
              <Zap size={14} className="mr-2" />
            )}
            Rebalance Now
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEmergencyModalStep(1)}
            className="text-xs h-9 border-red-500/50 text-red-400 hover:bg-red-500/10"
          >
            <AlertTriangle size={14} className="mr-2" />
            Emergency Exit
          </Button>
          <InfoRow className=" text-xs">
            <div
              className={`w-2 h-2 rounded-full ${isConnected ? 'bg-brand-success animate-pulse' : 'bg-brand-danger'}`}
            />
            <span className="text-brand-light/70 font-mono">
              {isConnected ? 'WS CONNECTED' : 'WS DISCONNECTED'}
            </span>
          </InfoRow>
        </div>
      </PageHeader>

      {/* ── Trading paused banner ── */}
      {tradingPaused && (
        <div className="mb-4 flex items-center justify-between gap-4 rounded-lg border-2 border-red-500/60 bg-red-950/30 px-4 py-3">
          <div className="flex items-center gap-3">
            <AlertTriangle size={18} className="text-red-400 shrink-0 animate-pulse" />
            <div>
              <p className="text-sm font-bold text-red-400 uppercase tracking-wider">Trading Paused</p>
              <p className="text-xs text-red-300/70">All new BUY/SELL signals blocked. Stop-loss exits still active.</p>
            </div>
          </div>
          <Button
            size="sm"
            onClick={() => resumeMutation.mutate()}
            disabled={resumeMutation.isPending}
            className="bg-red-500/20 border border-red-500/50 text-red-300 hover:bg-red-500/30 text-xs h-8 shrink-0"
          >
            {resumeMutation.isPending ? 'Resuming…' : 'Resume Trading'}
          </Button>
        </div>
      )}

      {/* ── Plain-language health summary ── */}
      {!portfolioLoading && !pnlLoading && !tradingPaused && (() => {
        // Only flag positions actually held — ignore stale screenings for symbols no longer in portfolio
        const heldSymbols = new Set(positions.map(p => p.symbol))
        const nonCompliant = Object.entries(complianceResults)
          .filter(([sym, r]) => heldSymbols.has(sym) && !r.is_compliant && r.verdict !== 'UNKNOWN')
        const unknown = Object.entries(complianceResults)
          .filter(([sym, r]) => heldSymbols.has(sym) && r.verdict === 'UNKNOWN')
        const unscreened = positions.filter(p => !complianceResults[p.symbol])
        const purificationDue = (pnlSummary?.total_purification_cost ?? 0) > 0
        const posCount = positions.length

        if (!portfolio.connected) return (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-brand-warning/40 bg-brand-warning/5 px-4 py-3 text-sm">
            <span className="text-xl">🔌</span>
            <span className="text-brand-warning font-medium">Not connected to broker.</span>
            <span className="text-brand-light/60">Start IBKR TWS or Gateway, then refresh.</span>
          </div>
        )
        if (nonCompliant.length > 0) return (
          <a
            href="#positions-table"
            className="mb-4 flex items-center gap-3 rounded-lg border border-brand-danger/40 bg-brand-danger/5 hover:bg-brand-danger/10 hover:border-brand-danger/60 px-4 py-3 text-sm transition-colors group"
          >
            <span className="text-xl">⚠️</span>
            <span className="text-brand-danger font-medium">{nonCompliant.length} position{nonCompliant.length > 1 ? 's' : ''} flagged as non-Halal.</span>
            <span className="text-brand-light/60 flex-1">Review the compliance column below and consider selling.</span>
            <span className="text-brand-danger/80 text-xs font-bold uppercase tracking-wider flex items-center gap-1 shrink-0">
              Jump to positions
              <span className="group-hover:translate-x-0.5 transition-transform">→</span>
            </span>
          </a>
        )
        if (unknown.length > 0 || unscreened.length > 0) return (
          <a
            href="#positions-table"
            className="mb-4 flex items-center gap-3 rounded-lg border border-brand-warning/40 bg-brand-warning/5 hover:bg-brand-warning/10 hover:border-brand-warning/60 px-4 py-3 text-sm transition-colors group"
          >
            <span className="text-xl">🔍</span>
            <span className="text-brand-warning font-medium">{unknown.length + unscreened.length} position{unknown.length + unscreened.length > 1 ? 's' : ''} not yet screened.</span>
            <span className="text-brand-light/60 flex-1">Compliance data pending — run screening or verify manually.</span>
            <span className="text-brand-warning/80 text-xs font-bold uppercase tracking-wider flex items-center gap-1 shrink-0">
              Jump to positions
              <span className="group-hover:translate-x-0.5 transition-transform">→</span>
            </span>
          </a>
        )
        if (purificationDue) return (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-brand-warning/40 bg-brand-warning/5 px-4 py-3 text-sm">
            <span className="text-xl">🌙</span>
            <span className="text-brand-warning font-medium">Purification payment due.</span>
            <span className="text-brand-light/60">A small portion of returns must be donated to charity. See Zakat page.</span>
          </div>
        )
        return (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-brand-success/30 bg-brand-success/5 px-4 py-3 text-sm">
            <span className="text-xl">✅</span>
            <span className="text-brand-success font-medium">All good.</span>
            <span className="text-brand-light/60">
              {posCount > 0
                ? `${posCount} Halal position${posCount > 1 ? 's' : ''} — bot is active and monitoring.`
                : 'Bot is active and scanning for opportunities.'}
            </span>
          </div>
        )
      })()}

      {/* Mobile emergency exit — sticky at bottom for quick access */}
      <div className="md:hidden fixed bottom-24 right-4 z-40">
        <button
          type="button"
          onClick={() => setEmergencyModalStep(1)}
          className="flex items-center gap-2 bg-red-950/90 border border-red-500/40 text-red-400 text-xs font-bold px-3 py-2 rounded-full shadow-lg backdrop-blur-sm"
        >
          <AlertTriangle size={12} />
          Exit All
        </button>
      </div>

      {/* ── Emergency liquidate modal ── */}
      {emergencyModalStep > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
          <div className="w-full max-w-md mx-4 rounded-2xl border-2 border-red-500/60 bg-zinc-950 p-6 shadow-2xl">
            <div className="flex items-center gap-3 mb-6">
              <AlertTriangle size={24} className="text-red-500 shrink-0" />
              <div>
                <h2 className="text-lg font-bold text-red-400">Emergency Liquidation</h2>
                <p className="text-xs text-zinc-400">This will sell ALL positions at market price immediately.</p>
              </div>
            </div>

            {emergencyResult ? (
              <div className="space-y-4">
                <div className="rounded-lg bg-zinc-900 border border-zinc-700 p-4">
                  <p className="text-sm font-bold text-zinc-100 mb-2">Liquidation complete</p>
                  <p className="text-xs text-green-400">Sold: {emergencyResult.liquidated.join(', ') || 'none'}</p>
                  {emergencyResult.skipped.length > 0 && (
                    <p className="text-xs text-red-400 mt-1">Failed: {emergencyResult.skipped.map(s => s.symbol).join(', ')}</p>
                  )}
                </div>
                <Button className="w-full bg-zinc-800 text-zinc-100" onClick={() => { setEmergencyModalStep(0); setEmergencyResult(null); setEmergencyPhrase(''); setEmergencyPin('') }}>
                  Close
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                {emergencyModalStep === 1 && (
                  <>
                    <div className="rounded-lg bg-red-950/30 border border-red-500/30 p-3 text-xs text-red-300 space-y-1">
                      <p className="font-bold">⚠ This cannot be undone.</p>
                      <p>Every open position will be sold at current market price. Commission applies to each trade.</p>
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-zinc-400 mb-2 uppercase tracking-wider">
                        Type <span className="text-red-400 font-mono">SELL ALL</span> to continue
                      </label>
                      <input
                        type="text"
                        className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-red-500"
                        value={emergencyPhrase}
                        onChange={(e) => setEmergencyPhrase(e.target.value)}
                        placeholder="SELL ALL"
                        autoComplete="off"
                      />
                    </div>
                    <div className="flex gap-3">
                      <Button className="flex-1 bg-zinc-800 text-zinc-400 hover:bg-zinc-700" onClick={() => { setEmergencyModalStep(0); setEmergencyPhrase('') }}>
                        Cancel
                      </Button>
                      <Button
                        className="flex-1 bg-red-600 hover:bg-red-500 text-white"
                        disabled={emergencyPhrase !== 'SELL ALL'}
                        onClick={() => setEmergencyModalStep(2)}
                      >
                        Continue →
                      </Button>
                    </div>
                  </>
                )}

                {emergencyModalStep === 2 && (
                  <>
                    <div className="rounded-lg bg-zinc-900 border border-zinc-700 p-3 text-xs text-zinc-400">
                      Step 2 of 2 — Enter your emergency PIN configured in <code className="text-zinc-200">EMERGENCY_PIN</code> env var.
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-zinc-400 mb-2 uppercase tracking-wider">Emergency PIN</label>
                      <input
                        type="password"
                        className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-red-500"
                        value={emergencyPin}
                        onChange={(e) => setEmergencyPin(e.target.value)}
                        placeholder="••••••••"
                        autoComplete="new-password"
                      />
                    </div>
                    <div className="flex gap-3">
                      <Button className="flex-1 bg-zinc-800 text-zinc-400 hover:bg-zinc-700" onClick={() => setEmergencyModalStep(1)}>
                        ← Back
                      </Button>
                      <Button
                        className="flex-1 bg-red-600 hover:bg-red-500 text-white font-bold"
                        disabled={emergencyPin.length < 1 || emergencyRunning}
                        onClick={async () => {
                          setEmergencyRunning(true)
                          try {
                            const res = await fetch(ROUTES.TRADES_EMERGENCY_LIQUIDATE, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json', 'X-Api-Key': API_KEY },
                              body: JSON.stringify({ emergency_pin: emergencyPin, account_id: selectedAccountId }),
                            })
                            if (!res.ok) {
                              const err = await res.json()
                              throw new Error(err.detail ?? `HTTP ${res.status}`)
                            }
                            const data = await res.json()
                            setEmergencyResult(data)
                            qc.invalidateQueries({ queryKey: ['positions'] })
                          } catch (e: any) {
                            alert(`Liquidation failed: ${e.message}`)
                          } finally {
                            setEmergencyRunning(false)
                            setEmergencyPin('')
                          }
                        }}
                      >
                        {emergencyRunning ? 'Selling…' : '🔴 SELL ALL NOW'}
                      </Button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Loading skeleton ── */}
      {(portfolioLoading || pnlLoading) && (
        <div className="animate-pulse space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="card p-5 h-28">
                <div className="h-2.5 bg-brand-light/10 rounded w-1/2 mb-3" />
                <div className="h-7 bg-brand-light/10 rounded w-3/4 mb-2" />
                <div className="h-2 bg-brand-light/10 rounded w-1/3" />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 card h-64" />
            <div className="card h-64" />
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="card h-24" />
            ))}
          </div>
        </div>
      )}

      {/* ── Hero KPI row (hidden while loading) ── */}
      {!portfolioLoading && !pnlLoading && <>

      {!dismissedOnboarding && trades.length === 0 && positions.length === 0 && (
        <div className="mb-6 rounded-xl border border-brand-primary/30 bg-brand-primary/5 p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <h3 className="text-sm font-bold text-brand-primary mb-3">Getting Started</h3>
              <div className="space-y-2">
                {[
                  { done: portfolio.connected, label: 'Connect to IBKR (TWS or Gateway running)' },
                  { done: (settingsData?.watchlist?.length ?? 0) > 0, label: 'Add symbols to watchlist in Settings' },
                  { done: portfolio.connected, label: 'Configure risk profile in Settings' },
                  { done: false, label: 'Set EMERGENCY_PIN in your .env file' },
                  { done: (settingsData?.auto_compliance_check ?? false), label: 'Enable Auto Compliance Monitor in Settings' },
                ].map((step, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <div className={`w-4 h-4 rounded-full flex items-center justify-center shrink-0 ${step.done ? 'bg-brand-success/20 text-brand-success' : 'bg-brand-divider/40 text-brand-light/30'}`}>
                      {step.done ? '✓' : (i + 1)}
                    </div>
                    <span className={step.done ? 'text-brand-light/50 line-through' : 'text-brand-light/80'}>{step.label}</span>
                  </div>
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={() => { localStorage.setItem('onboarding_dismissed', '1'); setDismissedOnboarding(true) }}
              className="text-brand-light/30 hover:text-brand-light/60 text-lg leading-none shrink-0"
              title="Dismiss"
            >×</button>
          </div>
        </div>
      )}

      <SimplePortfolioSummary
        summary={portfolioSummary ?? summaryFallback}
        historyValues={history.length >= 2 ? history.map((h) => h.total_value) : undefined}
      />

      {/* Growth Projection Mini Card */}
      {(portfolioSummary?.total_value ?? 0) > 0 && (() => {
        const v = portfolioSummary!.total_value!
        const proj = (rate: number, years: number) => Math.round(v * Math.pow(1 + rate, years))
        return (
          <Link to="/growth" className="card p-0 mb-6 overflow-hidden hover:border-brand-primary/30 transition-colors group block">
            <div className="px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-brand-primary/10 border border-brand-primary/20">
                  <TrendingUp size={16} className="text-brand-primary" />
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-brand-light/50">Growth Projection</p>
                  <p className="text-xs text-brand-light/60">Compound growth at different rates</p>
                </div>
              </div>
              <div className="flex gap-6 items-center">
                {([
                  { label: '1Y', years: 1 },
                  { label: '3Y', years: 3 },
                  { label: '5Y', years: 5 },
                  { label: '10Y', years: 10 },
                ] as const).map(({ label, years }) => (
                  <div key={label} className="text-center">
                    <p className="text-[10px] text-brand-light/40 font-bold">{label}</p>
                    <p className="text-sm font-bold font-mono text-brand-light">{formatUSD(proj(0.15, years), true)}</p>
                    <p className="text-[10px] font-mono text-brand-success">+{((Math.pow(1.15, years) - 1) * 100).toFixed(0)}%</p>
                  </div>
                ))}
                <span className="text-brand-primary/60 group-hover:text-brand-primary text-xs font-bold transition-colors">
                  Calculator →
                </span>
              </div>
            </div>
          </Link>
        )
      })()}

      <GlobalMarketsPanel />

      {/* ── Readiness strip ── */}
      {readiness && readiness.blockers.length > 0 && portfolio?.account_type !== 'LIVE' && (
        <div className="mb-4 rounded-lg border border-brand-warning/40 bg-brand-warning/10 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className="text-brand-warning mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-brand-warning uppercase tracking-wider mb-1">
                Pre-Live Blockers ({readiness.blockers.length})
              </p>
              <ul className="text-xs text-brand-light/80 space-y-0.5">
                {readiness.blockers.map((b, i) => (
                  <li key={i}>• {b}</li>
                ))}
              </ul>
              {readiness.note && (
                <p className="text-[10px] text-brand-light/50 mt-1">{readiness.note}</p>
              )}
            </div>
            <div className="text-[10px] text-brand-light/50 shrink-0">
              {readiness.trade_count} trades · {readiness.error_rate_pct ?? 0}% err
            </div>
          </div>
        </div>
      )}

      {/* Removed: redundant "all pass" green banner — "All good" strip above conveys same.
          Failure case (blockers > 0) still shown via the warning banner block. */}

      {/* ── Portfolio history chart — full width ── */}
      <div className="card mb-6 flex flex-col gap-2">
        <div className="flex justify-between items-center px-1">
          <div className="flex items-center gap-2">
            {([7, 30, 90, 'all'] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setHistoryDays(d)}
                className={`text-[10px] h-7 px-2.5 rounded font-bold uppercase tracking-wider transition-colors ${
                  historyDays === d
                    ? 'bg-brand-primary/20 border border-brand-primary/40 text-brand-primary'
                    : 'text-brand-light/40 hover:text-brand-light/70'
                }`}
              >
                {d === 'all' ? 'ALL' : `${d}D`}
              </button>
            ))}
          </div>
          <Button
            variant={showNet ? 'default' : 'outline'}
            size="xs"
            onClick={() => setShowNet(!showNet)}
            className={`text-[10px] h-7 px-3 font-bold uppercase tracking-widest ${showNet ? 'bg-brand-primary' : 'border-brand-divider text-brand-light/50'}`}
          >
            {showNet ? 'Showing Net (Purified)' : 'Show Net (Purified)'}
          </Button>
        </div>
        <PortfolioHistoryChart data={history} showNet={showNet} currentValue={totalMarketValue + portfolioValue} />
      </div>

      {/* ── Sector / Country breakdown — expanded by default ── */}
      <details className="group mb-6" open>
        <summary className="flex items-center gap-2 cursor-pointer text-xs font-bold text-brand-light/50 hover:text-brand-light/80 uppercase tracking-widest select-none list-none mb-2">
          <Globe size={13} />
          Portfolio Breakdown
          <span className="ml-auto group-open:rotate-180 transition-transform">▾</span>
        </summary>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SectorExposureChart
            data={sectorData}
            onDiversify={() => sectorDiversifyMutation.mutate()}
            diversifyPending={sectorDiversifyMutation.isPending}
            diversifyPicks={sectorPicks}
          />
          <CountryExposureChart
            data={countryData}
            onDiversify={() => diversifyMutation.mutate()}
            diversifyPending={diversifyMutation.isPending}
            diversifyPicks={diversifyPicks}
          />
        </div>
      </details>

      {/* ── System status — collapsed by default ── */}
      <details className="group mb-6">
        <summary className="flex items-center gap-2 cursor-pointer text-xs font-bold text-brand-light/50 hover:text-brand-light/80 uppercase tracking-widest select-none list-none mb-2">
          <Zap size={13} />
          System Status
          <span className="ml-auto group-open:rotate-180 transition-transform">▾</span>
        </summary>
        <SystemHealth health={systemHealth} />
      </details>

      <div id="positions-table" className="table-container mb-8 h-fit scroll-mt-24">
        <div className="card-header">
          <h2 className="heading-2">
            <Briefcase className="text-brand-primary" size={20} />
            Active Positions (<Abbr>IBKR</Abbr>)
          </h2>
          <ActionRow className=" flex-wrap">
            {positions.length > 0 && (
              <div className="flex items-center gap-4 text-xs font-mono">
                <span className="text-brand-light/70">
                  Total value:{' '}
                  <span className="text-brand-light font-bold">
                    {new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalMarketValue)}
                  </span>
                </span>
                <span
                  className={
                    totalPnl >= 0 ? 'text-brand-success font-bold' : 'text-brand-danger font-bold'
                  }
                >
                  {totalPnl >= 0 ? '+' : ''}
                  {totalPnl.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}{' '}
                  unrealized
                </span>
              </div>
            )}
            {selected.size > 0 && (
              <>
                <Button
                  size="sm"
                  onClick={() => checkCompliance(Array.from(selected))}
                  disabled={isChecking}
                  className="text-xs flex items-center gap-1.5"
                >
                  {isChecking ? (
                    <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <ScanSearch size={13} />
                  )}
                  Screen {selected.size}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => {
                    if (confirm(`Sell ${selected.size} position${selected.size !== 1 ? 's' : ''} at market price?`)) {
                      batchSellMutation.mutate(Array.from(selected))
                    }
                  }}
                  disabled={batchSellMutation.isPending}
                  className="text-xs flex items-center gap-1.5"
                >
                  {batchSellMutation.isPending
                    ? <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    : <XCircle size={13} />}
                  Sell {selected.size}
                </Button>
              </>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={exportCSV}
              disabled={positions.length === 0}
              className="text-xs flex items-center gap-1.5 border-brand-divider"
            >
              <Download size={13} />
              Export CSV
            </Button>
          </ActionRow>
        </div>
        {/* Mobile position cards */}
        <div className="md:hidden divide-y divide-brand-divider/40">
          {positions.length === 0 ? (
            <p className="p-6 text-center text-brand-light/70 italic text-sm">
              No open positions in IBKR account
            </p>
          ) : (
            positions.map((pos) => {
              const tick = tickerUpdates[pos.symbol]
              const livePrice = tick?.last && !isNaN(tick.last) ? tick.last : null
              const liveMarketValue = livePrice != null ? livePrice * pos.quantity : null
              const displayMarketValue = liveMarketValue ?? pos.market_value ?? pos.quantity * pos.avg_cost
              const livePnl = livePrice != null ? (livePrice - pos.avg_cost) * pos.quantity : null
              const pnl = livePnl ?? pos.unrealized_pnl ?? 0
              const pnlPct = pos.avg_cost > 0 ? (pnl / (pos.avg_cost * pos.quantity)) * 100 : 0
              const realizedPnl = realizedBySymbol[pos.symbol] ?? 0
              const purifCost = purifBySymbol[pos.symbol] ?? 0
              const halalPnl = halalPnlBySymbol[pos.symbol] ?? 0
              const compliance = complianceResults[pos.symbol]
              const checking = checkingSymbols.has(pos.symbol)
              return (
                <div key={pos.symbol} className={`p-4 space-y-2 ${flashSymbols.has(pos.symbol) ? 'animate-pulse bg-brand-primary/5' : ''}`}>
                  <div className="flex items-center justify-between">
                    <InfoRow className="">
                      <input
                        type="checkbox"
                        className="w-4 h-4 rounded-md border-brand-divider bg-brand-base text-brand-primary focus:ring-brand-primary/20 transition-all cursor-pointer"
                        checked={selected.has(pos.symbol)}
                        onChange={() => toggleSelect(pos.symbol)}
                      />
                      <span className="font-bold text-brand-light">{pos.symbol}</span>
                      {livePrice != null && (
                        <span className="text-[10px] font-mono text-brand-primary flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-brand-primary animate-pulse" />
                          ${livePrice.toFixed(2)}
                        </span>
                      )}
                      {signalMap[pos.symbol] && (
                        <MultiFactorBreakdown
                          f={signalMap[pos.symbol].f_score}
                          t={signalMap[pos.symbol].t_score}
                          s={signalMap[pos.symbol].s_score}
                        />
                      )}
                    </InfoRow>
                    {checking ? (
                      <div className="w-3 h-3 border-2 border-brand-primary/30 border-t-brand-primary rounded-full animate-spin" />
                    ) : compliance ? (
                      <VerdictBadge
                        result={compliance}
                        expanded={expandedSymbol === pos.symbol}
                        onClick={() =>
                          setExpandedSymbol(expandedSymbol === pos.symbol ? null : pos.symbol)
                        }
                      />
                    ) : (
                      <span className="text-brand-light/70 text-xs">—</span>
                    )}
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-mono text-brand-light/70">
                      $
                      {displayMarketValue.toLocaleString(undefined, {
                        maximumFractionDigits: 0,
                      })}
                    </span>
                    <span
                      className={`text-sm font-mono font-bold ${pnl >= 0 ? 'text-brand-success' : 'text-brand-danger'}`}
                    >
                      Unrealized: {pnl >= 0 ? '+' : ''}
                      {pnl.toFixed(2)}
                      <span className="text-xs ml-1 opacity-70">
                        ({pnlPct >= 0 ? '+' : ''}
                        {pnlPct.toFixed(1)}%)
                      </span>
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-brand-light/70 font-mono">Halal P&L (after Zakat)</span>
                    <span className={`text-xs font-mono font-bold ${halalPnl >= 0 ? 'text-brand-success' : 'text-brand-danger'}`}>
                      {halalPnl >= 0 ? '+' : ''}
                      {halalPnl.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-brand-light/70 font-mono">Purification / Realized</span>
                    <div className="flex items-center gap-2">
                      {purifCost > 0 ? (
                        <span className="text-xs font-mono font-bold text-brand-danger">
                          -${purifCost.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-xs font-mono text-brand-light/50">—</span>
                      )}
                      <span className="text-xs text-brand-light/40">/</span>
                      <span className={`text-xs font-mono font-bold ${pnlClass(realizedPnl)}`}>
                        {formatPnL(realizedPnl)}
                      </span>
                    </div>
                  </div>
                  <p className="text-xs text-brand-light/70 font-mono">
                    Qty {pos.quantity} · Avg ${pos.avg_cost.toFixed(2)}
                  </p>
                </div>
              )
            })
          )}
        </div>

        {/* Desktop table */}
        <table className="hidden md:table w-full text-left">
          <thead className="table-header hidden md:table-header-group">
            <tr>
              <th className="table-cell w-8">
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded-md border-brand-divider bg-brand-base text-brand-primary focus:ring-brand-primary/20 transition-all cursor-pointer"
                  checked={allSelected}
                  onChange={toggleSelectAll}
                  title="Select all"
                />
              </th>
              <th className="table-cell">Stock</th>
              <th className="table-cell">
                <TextTip text="Number of shares you currently own.">Shares</TextTip>
              </th>
              <th className="table-cell">
                <TextTip text="Current worth — live price × shares. What you'd get if you sold now.">Value</TextTip>
              </th>
              <th className="table-cell">
                <TextTip text="How much you're up or down compared to what you paid. Becomes real money when you sell.">Gain / Loss</TextTip>
              </th>
              <th className="table-cell">
                <TextTip text="Click to see full Shariah compliance details. Select + Screen to re-check live.">Halal?</TextTip>
              </th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 ? (
              <tr>
                <td
                  colSpan={colCount}
                  className="table-cell text-center text-brand-light/70 italic py-6"
                >
                  No open positions in IBKR account
                </td>
              </tr>
            ) : (
              positions.map((pos) => {
                const tick = tickerUpdates[pos.symbol]
                const livePrice = tick?.last && !isNaN(tick.last) ? tick.last : null
                const liveMarketValue = livePrice != null ? livePrice * pos.quantity : null
                const displayMarketValue2 = liveMarketValue ?? pos.market_value ?? pos.quantity * pos.avg_cost
                const livePnl2 = livePrice != null ? (livePrice - pos.avg_cost) * pos.quantity : null
                const pnl = livePnl2 ?? pos.unrealized_pnl ?? 0
                const pnlPct = pos.avg_cost > 0 ? (pnl / (pos.avg_cost * pos.quantity)) * 100 : 0
                const realizedPnl = realizedBySymbol[pos.symbol] ?? 0
                const purifCost = purifBySymbol[pos.symbol] ?? 0
                const halalPnl = halalPnlBySymbol[pos.symbol] ?? 0
                const compliance = complianceResults[pos.symbol]
                const checking = checkingSymbols.has(pos.symbol)
                const isExpanded = expandedSymbol === pos.symbol
                const isHaram =
                  compliance && !compliance.is_compliant && compliance.verdict !== 'UNKNOWN'
                return (
                  <React.Fragment key={pos.symbol}>
                    <tr className={`table-row hover:bg-zinc-900/40 transition-colors ${flashSymbols.has(pos.symbol) ? 'animate-pulse bg-brand-primary/5' : isHaram ? 'bg-brand-danger/5' : ''}`}>
                      <td className="table-cell">
                        <input
                          type="checkbox"
                          className="w-4 h-4 rounded-md border-brand-divider bg-brand-base text-brand-primary focus:ring-brand-primary/20 transition-all cursor-pointer"
                          checked={selected.has(pos.symbol)}
                          onChange={() => toggleSelect(pos.symbol)}
                        />
                      </td>
                      <td className="table-cell font-bold">
                        <div className="flex items-center gap-1.5">
                          {pos.symbol}
                          {livePrice != null && (
                            <span className="text-[10px] font-mono text-brand-primary">
                              ${livePrice.toFixed(2)}
                            </span>
                          )}
                        </div>
                        {pnlSummary?.positions.find(p => p.symbol === pos.symbol)?.days_held != null && (
                          <div className="text-[10px] text-brand-light/40 font-normal">
                            {pnlSummary!.positions.find(p => p.symbol === pos.symbol)!.days_held}d held
                          </div>
                        )}
                      </td>
                      <td className="table-cell text-sm">{pos.quantity}</td>
                      <td className="table-cell text-sm font-mono">
                        ${displayMarketValue2.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td className="table-cell text-sm font-mono">
                        <span className={pnl >= 0 ? 'text-brand-success' : 'text-brand-danger'}>
                          {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
                          <span className="text-xs ml-1 opacity-70">({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%)</span>
                        </span>
                      </td>
                      <td className="table-cell">
                        {checking ? (
                          <div className="w-3 h-3 border-2 border-brand-primary/30 border-t-brand-primary rounded-full animate-spin" />
                        ) : compliance ? (
                          <div className="space-y-0.5">
                            <VerdictBadge
                              result={compliance}
                              expanded={isExpanded}
                              onClick={() => setExpandedSymbol(isExpanded ? null : pos.symbol)}
                            />
                            {compliance.last_checked && (
                              <p className="text-[10px] text-brand-light/70">{relativeTime(compliance.last_checked)}</p>
                            )}
                          </div>
                        ) : (
                          <span className="text-brand-light/70 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                    {isExpanded && compliance && (
                      <ComplianceDetail result={compliance} colSpan={colCount} onVerify={handleManualVerify} />
                    )}
                  </React.Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <TradeLog trades={trades} />

      {twapJobs.length > 0 && (
        <TwapJobsPanel twapJobs={twapJobs} />
      )}
      </>}
    </Page>
  )
}

import { ErrorBoundary } from '../../components/ErrorBoundary'

export default function DashboardWithBoundary() {
  return (
    <ErrorBoundary title="Portfolio dashboard unavailable">
      <Dashboard />
    </ErrorBoundary>
  )
}
