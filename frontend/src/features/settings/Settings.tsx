import {
  AlertTriangle,
  Bell,
  Brain,
  CheckCircle2,
  DollarSign,
  Plus,
  Save,
  Settings as SettingsIcon,
  ShieldCheck,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Stack } from '@/components/ui/layout'
import { Field, Heading, Toggle } from '@/components/ui/primitives'
import { Text } from '@/components/ui/text'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Abbr } from '../../components/Tooltip'
import { ROUTES, withAccount } from '../../shared/routes'
import { useAccount } from '../trading/context/AccountContext'
import RegionSelector from './RegionSelector'

interface MLStatus {
  snapshot_count: number
  ppo_threshold: number
  ppo_ready: boolean
  model_type: string
}

interface SettingsData {
  min_trade_size: number
  max_commission_pct: number
  cash_reserve_pct: number
  max_position_size_pct: number
  max_sector_exposure_pct: number
  max_positions?: number
  target_weights: Record<string, number>
  settlement_strictness: 'CONSTRUCTIVE' | 'PHYSICAL_T2'
  purification_automation: 'MANUAL' | 'AUTO_CALC'
  ratio_buffer: number
  risk_profile: 'CONSERVATIVE' | 'BALANCED' | 'AGGRESSIVE'
  sector_exclusion: string[]
  rebalance_frequency: 'DAILY' | 'WEEKLY'
  critical_auto_sell: boolean
  alert_channels: string[]
  watchlist: string[]
  auto_execute_threshold: number
  signal_min_confidence: number
  stop_loss_pct: number | null
  take_profit_pct: number | null
  auto_compliance_check: boolean
  compliance_check_interval_hours: number
  use_atr_stops?: boolean
  enable_discovery_auto?: boolean
  discovery_interval_hours?: number
  use_global_universe?: boolean
  global_universe_cap_per_cycle?: number
  enabled_regions?: string[] | null
  enable_halal_drip?: boolean
  use_trailing_stop?: boolean
  use_kelly_sizing?: boolean
  time_exit_days?: number
  partial_profit_pct?: number
  partial_profit_fraction?: number
  require_pullback_entry?: boolean
  re_entry_cooldown_days?: number
  use_limit_orders?: boolean
  limit_order_slippage_pct?: number
  max_correlation?: number
  rerate_sell_threshold?: number
  max_vix_for_buys?: number
  trading_paused?: boolean
  position_size_pct?: number
}

const RISK_DEFAULTS: Record<string, { stop: number; take: number }> = {
  CONSERVATIVE: { stop: 3, take: 6 },
  BALANCED: { stop: 5, take: 10 },
  AGGRESSIVE: { stop: 8, take: 16 },
}

const DEFAULTS: SettingsData = {
  min_trade_size: 100,
  max_commission_pct: 0.5,
  cash_reserve_pct: 10,
  max_position_size_pct: 15,
  max_sector_exposure_pct: 25,
  max_positions: 15,
  target_weights: {},
  settlement_strictness: 'PHYSICAL_T2',
  purification_automation: 'MANUAL',
  ratio_buffer: 2,
  risk_profile: 'CONSERVATIVE',
  sector_exclusion: [
    'Gambling',
    'Alcohol',
    'Tobacco',
    'Defense',
    'Weapons',
    'Adult Content',
    'Pork',
    'Conventional Finance',
    'Insurance',
  ],
  rebalance_frequency: 'WEEKLY',
  critical_auto_sell: false,
  alert_channels: [],
  watchlist: [
    '7203.T',
    '6758.T',
    '6367.T',
    '0700.HK',
    '9988.HK',
    '005930.KS',
    'TCS.NS',
    'INFY.NS',
    'AAPL',
    'MSFT',
    'AMZN',
  ],
  auto_execute_threshold: 0,
  signal_min_confidence: 30,
  stop_loss_pct: null,
  take_profit_pct: null,
  auto_compliance_check: true,
  compliance_check_interval_hours: 24,
  use_atr_stops: true,
  enable_discovery_auto: false,
  discovery_interval_hours: 6,
  use_global_universe: false,
  global_universe_cap_per_cycle: 60,
  enable_halal_drip: false,
  use_trailing_stop: true,
  use_kelly_sizing: true,
  time_exit_days: 45,
  partial_profit_pct: 10,
  partial_profit_fraction: 0.5,
  require_pullback_entry: true,
  re_entry_cooldown_days: 14,
  use_limit_orders: false,
  limit_order_slippage_pct: 0.1,
  max_correlation: 0.85,
  rerate_sell_threshold: 35,
  max_vix_for_buys: 30,
  trading_paused: false,
  position_size_pct: 5,
}

const Settings = () => {
  const { selectedAccountId } = useAccount()
  const [settings, setSettings] = useState<SettingsData>(DEFAULTS)
  const [loading, setLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [showSuccess, setShowSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newSector, setNewSector] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  const { data: mlStatus } = useQuery<MLStatus>({
    queryKey: ['ml-status'],
    queryFn: () => fetch(ROUTES.AI_ML_STATUS).then((r) => r.json()),
    refetchInterval: 60_000,
  })

  useEffect(() => {
    setLoading(true)
    fetch(withAccount(ROUTES.SETTINGS, selectedAccountId))
      .then((r) => r.json())
      .then((data) => {
        setSettings(data)
        setLoading(false)
      })
      .catch(() => {
        setSettings(DEFAULTS)
        setLoading(false)
      })
  }, [selectedAccountId])

  const set = (key: keyof SettingsData, value: any) =>
    setSettings((prev) => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)
    try {
      const res = await fetch(withAccount(ROUTES.SETTINGS, selectedAccountId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setShowSuccess(true)
      setTimeout(() => setShowSuccess(false), 3000)
      toast.success('Settings saved')
    } catch (e: any) {
      setError(e.message)
      toast.error(e.message || 'Save failed')
    } finally {
      setIsSaving(false)
    }
  }

  const riskDefaults = RISK_DEFAULTS[settings.risk_profile]
  const effectiveStop = settings.stop_loss_pct ?? riskDefaults.stop
  const effectiveTake = settings.take_profit_pct ?? riskDefaults.take

  const addSector = () => {
    const s = newSector.trim()
    if (s && !settings.sector_exclusion.includes(s)) {
      set('sector_exclusion', [...settings.sector_exclusion, s])
    }
    setNewSector('')
  }

  return (
    <div className="page-container">
      <header className="mb-8 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <Stack gap="xs">
          <Heading icon={SettingsIcon}>System Settings</Heading>
          <Text tone="muted">Configure Shariah-compliant trading parameters</Text>
        </Stack>
        <div className="flex items-center gap-4">
          {error && <span className="text-brand-danger text-sm">{error}</span>}
          {showSuccess && (
            <span className="text-brand-success flex items-center gap-1 text-sm font-medium">
              <CheckCircle2 size={16} /> Saved
            </span>
          )}
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? (
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Save size={20} />
            )}
            {isSaving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 mb-6 sticky top-14 z-10 bg-brand-base/95 backdrop-blur-sm py-2 -mx-4 px-4 border-b border-brand-divider/30">
        {[
          { id: 'section-autopilot', label: 'Autopilot' },
          { id: 'section-risk', label: 'Risk Limits' },
          { id: 'section-order', label: 'Order Settings' },
          { id: 'section-compliance', label: 'Compliance' },
          { id: 'section-alerts', label: 'Alerts' },
          ...(showAdvanced ? [
            { id: 'section-ai', label: 'AI & Execution' },
            { id: 'section-model', label: 'AI Model' },
          ] : []),
        ].map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            className="text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full border border-brand-divider/60 text-brand-light/60 hover:text-brand-primary hover:border-brand-primary/50 transition-colors"
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setShowAdvanced(v => !v)}
          className={`ml-auto text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full border transition-colors ${
            showAdvanced
              ? 'bg-brand-primary/20 border-brand-primary/50 text-brand-primary'
              : 'border-brand-divider/60 text-brand-light/40 hover:text-brand-light/70'
          }`}
        >
          {showAdvanced ? 'Hide Advanced' : 'Show Advanced'}
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-pulse">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card h-48">
              <div className="h-3 bg-brand-light/10 rounded w-1/3 mb-4" />
              <div className="space-y-3">
                <div className="h-2 bg-brand-light/10 rounded w-full" />
                <div className="h-2 bg-brand-light/10 rounded w-2/3" />
                <div className="h-8 bg-brand-light/10 rounded w-full mt-4" />
              </div>
            </div>
          ))}
        </div>
      ) : (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* ── Portfolio Autopilot ────────────────────────────── */}
        <section id="section-autopilot" className="card">
          <div className="flex items-center gap-2 mb-6">
            <Brain className="text-brand-primary" size={24} />
            <h2 className="heading-2 mb-0">Portfolio Autopilot (Target Weights)</h2>
          </div>
          <div className="space-y-4">
            <p className="text-xs text-brand-light/60 leading-relaxed">
              Define your ideal portfolio allocation. The system will calculate rebalance trades to
              match these targets.
            </p>
            <div className="space-y-3">
              {Object.entries(settings.target_weights).map(([symbol, weight]) => (
                <div
                  key={symbol}
                  className="flex items-center gap-3 bg-brand-base p-2 rounded-lg border border-brand-divider"
                >
                  <span className="font-bold w-20 truncate">{symbol}</span>
                  <div className="flex-1 flex items-center gap-2">
                    <Input
                      type="number"
                      className="font-mono h-8 text-xs bg-transparent border-brand-divider focus:border-brand-primary"
                      value={weight}
                      onChange={(e) => {
                        const newWeights = {
                          ...settings.target_weights,
                          [symbol]: parseFloat(e.target.value) || 0,
                        }
                        set('target_weights', newWeights)
                      }}
                    />
                    <span className="text-[10px] font-bold text-brand-light/70 uppercase">%</span>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-brand-light/70 hover:text-brand-danger"
                    onClick={() => {
                      const newWeights = { ...settings.target_weights }
                      delete newWeights[symbol]
                      set('target_weights', newWeights)
                    }}
                  >
                    <X size={14} />
                  </Button>
                </div>
              ))}
              <div className="flex gap-2">
                <Input
                  placeholder="ADD SYMBOL (e.g. AAPL)"
                  className="font-mono h-9 text-xs uppercase bg-brand-base/50"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      const sym = e.currentTarget.value.toUpperCase().trim()
                      if (sym && !settings.target_weights[sym]) {
                        set('target_weights', { ...settings.target_weights, [sym]: 0 })
                        e.currentTarget.value = ''
                      }
                    }
                  }}
                />
              </div>
              <div className="flex justify-between items-center px-1 py-2 border-t border-brand-divider/40 mt-2">
                <span className="text-[10px] font-bold text-brand-light/90 uppercase tracking-widest">
                  Total Allocated
                </span>
                <span
                  className={`font-mono font-bold ${Math.abs(Object.values(settings.target_weights).reduce((s, w) => s + w, 0) - 100) < 0.1 ? 'text-brand-success' : 'text-brand-warning'}`}
                >
                  {Object.values(settings.target_weights)
                    .reduce((s, w) => s + w, 0)
                    .toFixed(1)}
                  %
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ── Advanced Risk Guards ───────────────────────────── */}
        <section id="section-risk" className="card border-l-4 border-l-brand-warning">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="text-brand-warning" size={24} />
            <h2 className="heading-2 mb-0">Risk Limits</h2>
          </div>
          <p className="text-xs text-brand-light/50 mb-6">How much the bot can invest in any one stock, sector, or at once. Lower = safer, less concentrated.</p>
          <div className="space-y-4">
            <Field label="Max Position Size (%)" htmlFor="max_position_size_pct" help="Single-stock cap as % of total portfolio.">
              <Input id="max_position_size_pct" type="number" min={1} max={100} mono value={settings.max_position_size_pct} onChange={(e) => set('max_position_size_pct', parseFloat(e.target.value))} />
            </Field>
            <Field label="Max Sector Exposure (%)" htmlFor="max_sector_exposure_pct" help="Maximum % allowed for any single industry (e.g. Technology).">
              <Input id="max_sector_exposure_pct" type="number" min={1} max={100} mono value={settings.max_sector_exposure_pct} onChange={(e) => set('max_sector_exposure_pct', parseFloat(e.target.value))} />
            </Field>
            <Field label="Max Concurrent Positions" htmlFor="max_positions" help="Bot stops buying when this many positions are open. Exits free slots.">
              <Input id="max_positions" type="number" min={1} max={50} mono value={settings.max_positions ?? 15} onChange={(e) => set('max_positions', parseInt(e.target.value, 10))} />
            </Field>
            <Field label="Minimum Cash Reserve (%)" htmlFor="cash_reserve_pct" help="Cash kept liquid for safety. Rebalancer will never use this.">
              <Input id="cash_reserve_pct" type="number" min={0} max={100} mono value={settings.cash_reserve_pct} onChange={(e) => set('cash_reserve_pct', parseFloat(e.target.value))} />
            </Field>
          </div>
        </section>

        {/* ── Allocation ─────────────────────────────────────── */}
        <section id="section-order" className="card">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="text-brand-primary" size={24} />
            <h2 className="heading-2 mb-0">Order Settings</h2>
          </div>
          <p className="text-xs text-brand-light/50 mb-6">Controls how big each trade is and how stop-losses protect your money.</p>
          <div className="space-y-4">
            <Field label="Minimum Order Size (USD)" htmlFor="min_trade_size" help="Prevents tiny, inefficient trades that waste commissions.">
              <Input id="min_trade_size" type="number" min={1} mono value={settings.min_trade_size} onChange={(e) => set('min_trade_size', parseFloat(e.target.value))} />
            </Field>
            <Field label="Target Position Size (% of portfolio)" htmlFor="position_size_pct" help="Each new position targets this % of portfolio. Hard-capped by Max Position Size above.">
              <Input id="position_size_pct" type="number" min={1} max={25} step={0.5} mono value={settings.position_size_pct ?? 5} onChange={(e) => set('position_size_pct', parseFloat(e.target.value))} />
            </Field>
            <Field label="Max Commission Impact (%)" htmlFor="max_commission_pct" help="Trade is blocked if fees > this % of value.">
              <Input id="max_commission_pct" type="number" min={0} step={0.1} mono value={settings.max_commission_pct} onChange={(e) => set('max_commission_pct', parseFloat(e.target.value))} />
            </Field>
          </div>
        </section>

        {/* ── Shariah Compliance ─────────────────────────────── */}
        <section id="section-compliance" className="card">
          <h2 className="heading-2 mb-6">
            <ShieldCheck className="text-brand-success" size={24} />
            Shariah Compliance
          </h2>
          <div className="space-y-4">
            <Field
              label="Settlement Strictness"
              htmlFor="settlement_strictness"
              help={<>Strict locks a position until <Abbr>IBKR</Abbr> confirms settlement (<Abbr>T+2</Abbr> days).</>}
            >
              <Select
                value={settings.settlement_strictness}
                onValueChange={(v) => set('settlement_strictness', v)}
              >
                <SelectTrigger id="settlement_strictness" className="w-full font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PHYSICAL_T2">Strict — wait T+2 (Qabd al-Haqiqi)</SelectItem>
                  <SelectItem value="CONSTRUCTIVE">Lenient — allow instant re-sale</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field
              label="Ratio Strictness Buffer (%)"
              htmlFor="ratio_buffer"
              help={<>Tightens <Abbr>AAOIFI</Abbr> thresholds by this amount. At 2%: debt limit becomes 31% instead of 33%.</>}
            >
              <Input id="ratio_buffer" type="number" min={0} max={10} step={0.5} mono value={settings.ratio_buffer} onChange={(e) => set('ratio_buffer', parseFloat(e.target.value))} />
            </Field>
            <Field label="Purification Automation" htmlFor="purification_automation">
              <Select
                value={settings.purification_automation}
                onValueChange={(v) => set('purification_automation', v)}
              >
                <SelectTrigger id="purification_automation" className="w-full font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MANUAL">Manual — you approve each donation</SelectItem>
                  <SelectItem value="AUTO_CALC">Auto-Calculate — log amount, no action</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <div>
              <label className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase">
                Excluded Sectors
              </label>
              <div className="flex flex-wrap gap-2 mb-2">
                {settings.sector_exclusion.map((s) => (
                  <span
                    key={s}
                    className="flex items-center gap-1.5 px-2.5 py-1 bg-brand-danger/10 border border-brand-danger/20 text-brand-danger text-[10px] font-bold uppercase tracking-wider rounded-full group"
                  >
                    {s}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      className="h-auto w-auto p-0.5 hover:bg-brand-danger/20 rounded-full"
                      onClick={() =>
                        set(
                          'sector_exclusion',
                          settings.sector_exclusion.filter((x) => x !== s),
                        )
                      }
                    >
                      <X size={10} strokeWidth={3} />
                    </Button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  type="text"
                  className="font-mono flex-1 text-sm h-9"
                  placeholder="Add sector…"
                  value={newSector}
                  onChange={(e) => setNewSector(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addSector()
                    }
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  className="h-9 w-9 border-brand-divider/60 hover:border-brand-primary/50"
                  onClick={addSector}
                >
                  <Plus size={16} />
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* ── AI & Execution ─────────────────────────────────── */}
        {showAdvanced && <section id="section-ai" className="card">
          <h2 className="heading-2 mb-2">
            <Brain className="text-brand-primary" size={24} />
            AI & Execution
          </h2>
          <p className="text-xs text-brand-light/50 mb-6">Advanced order routing and AI signal settings. Leave defaults unless you know what you're changing.</p>
          <div className="space-y-4">
            <div>
              <Label
                htmlFor="risk_profile"
                className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
              >
                Risk Profile
              </Label>
              <Select
                value={settings.risk_profile}
                onValueChange={(v) => set('risk_profile', v as any)}
              >
                <SelectTrigger id="risk_profile" className="w-full font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="CONSERVATIVE">Conservative</SelectItem>
                  <SelectItem value="BALANCED">Balanced</SelectItem>
                  <SelectItem value="AGGRESSIVE">Aggressive</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-brand-light/60 mt-1">
                Sets default stop-loss / take-profit for bracket orders:{' '}
                <span className="text-brand-danger font-mono">−{riskDefaults.stop}%</span> /{' '}
                <span className="text-brand-success font-mono">+{riskDefaults.take}%</span>
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="stop_loss_pct"
                  className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
                >
                  Stop-Loss Override (%)
                </label>
                <Input
                  id="stop_loss_pct"
                  type="number"
                  step="0.5"
                  min="0"
                  className="font-mono"
                  placeholder={`${riskDefaults.stop}% (profile default)`}
                  value={settings.stop_loss_pct ?? ''}
                  onChange={(e) =>
                    set('stop_loss_pct', e.target.value === '' ? null : parseFloat(e.target.value))
                  }
                />
                {settings.stop_loss_pct !== null && (
                  <p className="text-xs text-brand-warning mt-1">
                    Override active: {effectiveStop}%
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="take_profit_pct"
                  className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
                >
                  Take-Profit Override (%)
                </label>
                <Input
                  id="take_profit_pct"
                  type="number"
                  step="0.5"
                  min="0"
                  className="font-mono"
                  placeholder={`${riskDefaults.take}% (profile default)`}
                  value={settings.take_profit_pct ?? ''}
                  onChange={(e) =>
                    set(
                      'take_profit_pct',
                      e.target.value === '' ? null : parseFloat(e.target.value),
                    )
                  }
                />
                {settings.take_profit_pct !== null && (
                  <p className="text-xs text-brand-success mt-1">
                    Override active: {effectiveTake}%
                  </p>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Stale Thesis Exit (days)" htmlFor="time_exit_days" help="Sell if held longer than this with less than target gain.">
                <Input id="time_exit_days" type="number" min="14" max="365" mono value={settings.time_exit_days ?? 45} onChange={(e) => set('time_exit_days', Number(e.target.value))} />
              </Field>
              <Field label="Partial Profit Target %" htmlFor="partial_profit_pct" help="Sell half position at this unrealized gain.">
                <Input id="partial_profit_pct" type="number" min="2" max="50" mono value={settings.partial_profit_pct ?? 10} onChange={(e) => set('partial_profit_pct', Number(e.target.value))} />
              </Field>
              <Field label="Partial Sell Fraction" htmlFor="partial_profit_fraction" help="Fraction of position to sell at partial profit (0.5 = half).">
                <Input id="partial_profit_fraction" type="number" min="0.1" max="0.9" step="0.1" mono value={settings.partial_profit_fraction ?? 0.5} onChange={(e) => set('partial_profit_fraction', Number(e.target.value))} />
              </Field>
              <Field label="Re-Entry Cooldown (days)" htmlFor="re_entry_cooldown_days" help="Block re-buying a symbol for this many days after take-profit exit.">
                <Input id="re_entry_cooldown_days" type="number" min="0" max="90" mono value={settings.re_entry_cooldown_days ?? 14} onChange={(e) => set('re_entry_cooldown_days', Number(e.target.value))} />
              </Field>
              <Field label="Re-Rating Sell Threshold" htmlFor="rerate_sell_threshold" help="Sell held position if AI score drops below this during re-scoring.">
                <Input id="rerate_sell_threshold" type="number" min="10" max="60" mono value={settings.rerate_sell_threshold ?? 35} onChange={(e) => set('rerate_sell_threshold', Number(e.target.value))} />
              </Field>
              <Field label="Max VIX for New Buys" htmlFor="max_vix_for_buys" help="Pause discovery BUYs when VIX exceeds this level. Default 30 (crisis threshold).">
                <Input id="max_vix_for_buys" type="number" min="15" max="80" step="1" mono value={settings.max_vix_for_buys ?? 30} onChange={(e) => set('max_vix_for_buys', Number(e.target.value))} />
              </Field>
            </div>

            <Toggle
              id="use_atr_stops"
              label="ATR-Based Stops"
              description="Use ATR volatility to set dynamic stop-loss and take-profit levels instead of fixed percentages."
              checked={settings.use_atr_stops ?? true}
              onChange={(v) => set('use_atr_stops', v)}
            />

            <Toggle
              id="use_trailing_stop"
              label="Trailing Stop"
              description="Move stop loss up as price rises, locking in gains from the high-water mark."
              checked={settings.use_trailing_stop ?? true}
              onChange={(v) => set('use_trailing_stop', v)}
            />

            <Toggle
              id="use_kelly_sizing"
              label="Kelly Position Sizing"
              description="Scale position size by signal confidence (half-Kelly). High confidence = bigger position, low confidence = smaller."
              checked={settings.use_kelly_sizing ?? true}
              onChange={(v) => set('use_kelly_sizing', v)}
            />

            <Toggle
              id="require_pullback_entry"
              label="Pullback Entry Filter"
              description="Only buy when price has dipped 1–5% from recent high while trend is still up. Avoids buying at local peaks."
              checked={settings.require_pullback_entry ?? true}
              onChange={(v) => set('require_pullback_entry', v)}
            />

            <Toggle
              id="use_limit_orders"
              label="Use Limit Orders"
              description="Place limit orders instead of market orders to reduce slippage. Uses mid-price ± tolerance."
              checked={settings.use_limit_orders ?? false}
              onChange={(v) => set('use_limit_orders', v)}
            >
              {(settings.use_limit_orders ?? false) && (
                <Field label="Limit Tolerance %" htmlFor="limit_order_slippage_pct">
                  <Input id="limit_order_slippage_pct" type="number" min={0.05} max={1.0} step={0.05} mono className="w-24" value={settings.limit_order_slippage_pct ?? 0.1} onChange={(e) => set('limit_order_slippage_pct', Number(e.target.value))} />
                </Field>
              )}
            </Toggle>

            {/* Max Portfolio Correlation */}
            <div>
              <label
                htmlFor="max_correlation"
                className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
              >
                Max Portfolio Correlation
              </label>
              <Input
                id="max_correlation"
                type="number"
                min="0.5"
                max="1.0"
                step="0.05"
                className="font-mono"
                value={settings.max_correlation ?? 0.85}
                onChange={(e) => set('max_correlation', Number(e.target.value))}
              />
              <p className="text-xs text-brand-light/60 mt-1">
                Skip BUY if candidate correlates above this threshold with any existing position (0.7–1.0). Prevents hidden concentration.
              </p>
            </div>

            <Toggle
              id="enable_discovery_auto"
              label="Auto-Execute Discovery Scans"
              description="Periodically scan the market for halal opportunities and auto-execute signals that meet your threshold."
              checked={settings.enable_discovery_auto ?? false}
              onChange={(v) => set('enable_discovery_auto', v)}
            >
              {(settings.enable_discovery_auto ?? false) && (
                <Field label="Scan Interval (hours)" htmlFor="discovery_interval_hours">
                  <Input id="discovery_interval_hours" type="number" min={1} max={24} mono className="w-24" value={settings.discovery_interval_hours ?? 6} onChange={(e) => set('discovery_interval_hours', Number(e.target.value))} />
                </Field>
              )}
            </Toggle>

            <Toggle
              id="use_global_universe"
              tone="accent"
              label="🌍 Global Halal Universe"
              description="Fold ~356 halal-eligible stocks across 33 regions into every main-loop cycle (open markets only). Asia overnight, MENA Sun-Thu, EU mornings."
              checked={settings.use_global_universe ?? false}
              onChange={(v) => set('use_global_universe', v)}
            >
              {(settings.use_global_universe ?? false) && (
                <div className="mt-3 space-y-4">
                  <Field label="Max symbols per cycle" htmlFor="global_universe_cap_per_cycle" help="Higher = more coverage but slower cycles. 60 = ~2min/cycle.">
                    <Input id="global_universe_cap_per_cycle" type="number" min={10} max={200} mono className="w-24" value={settings.global_universe_cap_per_cycle ?? 60} onChange={(e) => set('global_universe_cap_per_cycle', Number(e.target.value))} />
                  </Field>
                  <RegionSelector value={settings.enabled_regions} onChange={(regs) => set('enabled_regions', regs)} />
                </div>
              )}
            </Toggle>

            <Toggle
              id="enable_halal_drip"
              label="Halal DRIP"
              description="Auto-reinvest purified dividends back into the same halal stock (minus impure revenue %)."
              checked={settings.enable_halal_drip ?? false}
              onChange={(v) => set('enable_halal_drip', v)}
            />

            <div>
              <Label
                htmlFor="rebalance_frequency"
                className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
              >
                Rebalance Frequency
              </Label>
              <Select
                value={settings.rebalance_frequency}
                onValueChange={(v) => set('rebalance_frequency', v)}
              >
                <SelectTrigger id="rebalance_frequency" className="w-full font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="DAILY">Daily</SelectItem>
                  <SelectItem value="WEEKLY">Weekly</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-brand-light/60 mt-1">
                How often the AI scans held positions for SELL signals.
              </p>
            </div>

            <div>
              <label
                htmlFor="watchlist"
                className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
              >
                Global Watchlist
              </label>
              <div className="flex flex-wrap gap-1.5 p-2 bg-brand-base border border-brand-divider rounded-lg min-h-[44px] focus-within:border-brand-primary/60">
                {settings.watchlist.map((sym) => (
                  <span key={sym} className="inline-flex items-center gap-1 px-2 py-0.5 bg-brand-primary/10 border border-brand-primary/20 text-brand-primary text-[11px] font-bold uppercase rounded-full">
                    {sym}
                    <button
                      type="button"
                      onClick={() => set('watchlist', settings.watchlist.filter((s) => s !== sym))}
                      className="hover:text-brand-danger transition-colors ml-0.5"
                      aria-label={`Remove ${sym}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
                <input
                  type="text"
                  placeholder="Add symbol…"
                  className="flex-1 min-w-[80px] bg-transparent text-[12px] font-mono text-brand-light placeholder-brand-light/30 outline-none uppercase"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ',') {
                      e.preventDefault()
                      const sym = e.currentTarget.value.trim().toUpperCase()
                      if (sym && !settings.watchlist.includes(sym)) {
                        set('watchlist', [...settings.watchlist, sym])
                      }
                      e.currentTarget.value = ''
                    }
                  }}
                />
              </div>
              <p className="text-xs text-brand-light/60 mt-1">
                Type a ticker and press Enter or comma to add. Click × to remove.
              </p>
            </div>

            {/* Signal routing */}
            <div className="space-y-4 p-4 rounded-lg border border-brand-divider bg-brand-base">
              <div>
                <div className="flex justify-between mb-1">
                  <label
                    htmlFor="signal_min_confidence"
                    className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
                  >
                    Minimum Signal Confidence
                  </label>
                  <span className="text-xs font-mono text-brand-light">
                    {settings.signal_min_confidence}%
                  </span>
                </div>
                <input
                  id="signal_min_confidence"
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={settings.signal_min_confidence}
                  onChange={(e) => set('signal_min_confidence', parseInt(e.target.value, 10))}
                  className="w-full accent-brand-primary h-1.5 bg-brand-divider/40 rounded-lg appearance-none cursor-pointer"
                />
                <p className="text-xs text-brand-light/60 mt-1">
                  Signals below this are silently ignored.
                </p>
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <label
                    htmlFor="auto_execute_threshold"
                    className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
                  >
                    Auto-Execute Threshold
                    {settings.auto_execute_threshold === 0 && (
                      <span className="ml-2 text-brand-light/70 font-normal text-xs">
                        (off — all go to manual)
                      </span>
                    )}
                  </label>
                  <span className="text-xs font-mono text-brand-light">
                    {settings.auto_execute_threshold === 0
                      ? 'OFF'
                      : `≥ ${settings.auto_execute_threshold}%`}
                  </span>
                </div>
                <input
                  id="auto_execute_threshold"
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={settings.auto_execute_threshold}
                  onChange={(e) => set('auto_execute_threshold', parseInt(e.target.value, 10))}
                  className="w-full accent-brand-danger h-1.5 bg-brand-divider/40 rounded-lg appearance-none cursor-pointer"
                />
                {settings.auto_execute_threshold > 0 && (
                  <div className="mt-2 flex items-start gap-2 p-2 bg-brand-warning/10 border border-brand-warning/30 rounded text-xs text-brand-warning">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                    <span>
                      Signals ≥ {settings.auto_execute_threshold}% confidence auto-execute without
                      approval.
                    </span>
                  </div>
                )}
              </div>

              {/* Routing preview bar */}
              <div>
                <p className="text-xs text-brand-light/60 mb-2">Signal routing:</p>
                {(() => {
                  const ignoredW = settings.signal_min_confidence
                  const manualW = settings.auto_execute_threshold > settings.signal_min_confidence
                    ? settings.auto_execute_threshold - settings.signal_min_confidence
                    : 100 - settings.signal_min_confidence
                  const autoW = settings.auto_execute_threshold > settings.signal_min_confidence
                    ? 100 - settings.auto_execute_threshold
                    : 0
                  const hasAuto = autoW > 0
                  return (
                    <>
                      <div className="flex rounded-lg overflow-hidden text-[11px] font-semibold h-7">
                        <div
                          style={{ width: `${ignoredW}%` }}
                          className="bg-brand-divider flex items-center justify-center text-brand-light/60 overflow-hidden whitespace-nowrap"
                          title={`0–${settings.signal_min_confidence}%: Ignored`}
                        >
                          {ignoredW >= 10 ? 'Ignored' : ''}
                        </div>
                        <div
                          style={{ width: `${manualW}%` }}
                          className="bg-brand-warning/30 flex items-center justify-center text-brand-warning overflow-hidden whitespace-nowrap"
                          title={`${settings.signal_min_confidence}–${settings.auto_execute_threshold}%: Manual`}
                        >
                          {manualW >= 10 ? 'Manual' : ''}
                        </div>
                        {hasAuto && (
                          <div
                            style={{ width: `${autoW}%` }}
                            className="bg-brand-success/30 flex items-center justify-center text-brand-success overflow-hidden whitespace-nowrap"
                            title={`${settings.auto_execute_threshold}–100%: Auto`}
                          >
                            {autoW >= 6 ? 'Auto' : ''}
                          </div>
                        )}
                      </div>
                      <div className="flex justify-between text-xs text-brand-light/60 mt-1">
                        <span>0%</span>
                        {settings.signal_min_confidence > 0 && settings.signal_min_confidence < 90 && (
                          <span>{settings.signal_min_confidence}%</span>
                        )}
                        {hasAuto && settings.auto_execute_threshold !== settings.signal_min_confidence && (
                          <span className="text-brand-success">{settings.auto_execute_threshold}%</span>
                        )}
                        <span>100%</span>
                      </div>
                      {hasAuto && autoW < 6 && (
                        <p className="text-[10px] text-brand-success mt-0.5">
                          ✦ Auto-execute: ≥ {settings.auto_execute_threshold}% confidence
                        </p>
                      )}
                    </>
                  )
                })()}
              </div>
            </div>
          </div>
        </section>}

        {/* ── Alerts & Safety ────────────────────────────────── */}
        <section id="section-alerts" className="card">
          <h2 className="heading-2 mb-6">
            <Bell className="text-brand-warning" size={24} />
            Alerts & Safety
          </h2>
          <div className="space-y-4">
            {/* Master Trading Kill Switch */}
            <div className="p-4 rounded-xl border-2 border-red-500/40 bg-red-950/20 shadow-glow-danger/5">
              <div className="flex items-center justify-between relative z-10">
                <div className="flex-1 pr-4">
                  <Label
                    htmlFor="trading_paused"
                    className="text-sm font-bold text-red-400 cursor-pointer"
                  >
                    ⏸ Master Trading Pause
                  </Label>
                  <p className="text-[11px] text-brand-light/70 mt-1 leading-relaxed opacity-90">
                    When ON, all new BUY/SELL signals are blocked. Stop-loss exits still run for safety.
                  </p>
                </div>
                <div className="relative shrink-0">
                  <input
                    id="trading_paused"
                    type="checkbox"
                    className="sr-only peer"
                    checked={settings.trading_paused ?? false}
                    onChange={(e) => set('trading_paused', e.target.checked)}
                  />
                  <div
                    onClick={() => set('trading_paused', !(settings.trading_paused ?? false))}
                    className="flex w-10 h-5.5 bg-brand-divider peer-checked:bg-red-500 rounded-full cursor-pointer transition-all duration-300 relative"
                  >
                    <div
                      className={`absolute top-0.5 left-0.5 bg-white rounded-full h-4.5 w-4.5 transition-transform duration-300 shadow-sm ${(settings.trading_paused ?? false) ? 'translate-x-4.5' : ''}`}
                    />
                  </div>
                </div>
              </div>
              {(settings.trading_paused ?? false) && (
                <div className="mt-3 flex items-center gap-2 p-2.5 bg-red-500/10 border border-red-500/30 rounded-lg text-[10px] font-bold text-red-400 uppercase tracking-wider">
                  <AlertTriangle size={12} className="shrink-0" />
                  <span>ALL TRADING PAUSED — only stop-loss exits active</span>
                </div>
              )}
            </div>
            <div className="p-4 rounded-xl border border-brand-danger/20 bg-brand-danger/5 shadow-glow-danger/2 overflow-hidden relative">
              <div className="flex items-center justify-between mb-2 relative z-10">
                <Label
                  htmlFor="critical_auto_sell"
                  className="text-sm font-bold text-brand-danger cursor-pointer"
                >
                  Kill-Switch: Auto-Liquidate Non-Compliant
                </Label>
                <div className="relative">
                  <input
                    id="critical_auto_sell"
                    type="checkbox"
                    className="sr-only peer"
                    checked={settings.critical_auto_sell}
                    onChange={(e) => set('critical_auto_sell', e.target.checked)}
                  />
                  <div
                    onClick={() => set('critical_auto_sell', !settings.critical_auto_sell)}
                    className="flex w-10 h-5.5 bg-brand-divider peer-checked:bg-brand-danger rounded-full cursor-pointer transition-all duration-300 relative"
                  >
                    <div
                      className={`absolute top-0.5 left-0.5 bg-white rounded-full h-4.5 w-4.5 transition-transform duration-300 shadow-sm ${settings.critical_auto_sell ? 'translate-x-4.5' : ''}`}
                    />
                  </div>
                </div>
              </div>
              <p className="text-[11px] text-brand-light/70 leading-relaxed relative z-10 opacity-90">
                When enabled, any position flagged as non-compliant during the daily audit is
                automatically sold at market price.
              </p>
              {settings.critical_auto_sell && (
                <div className="mt-3 flex items-start gap-2 p-2.5 bg-brand-danger/10 border border-brand-danger/20 rounded-lg text-[10px] font-bold text-brand-danger uppercase tracking-wider relative z-10 animate-in fade-in slide-in-from-top-1">
                  <AlertTriangle size={12} className="shrink-0" />
                  <span>Kill-switch active: Unsafe positions sold immediately.</span>
                </div>
              )}
            </div>

            <div className="p-4 rounded-xl border border-brand-primary/20 bg-brand-primary/5 overflow-hidden relative">
              <div className="flex items-center justify-between mb-2 relative z-10">
                <div className="flex-1 pr-4">
                  <Label
                    htmlFor="auto_compliance_check"
                    className="text-sm font-bold text-brand-light cursor-pointer"
                  >
                    Auto Compliance Monitor
                  </Label>
                  <p className="text-[11px] text-brand-light/70 mt-1 leading-relaxed opacity-90">
                    Periodically re-screens all open positions as financials change.
                  </p>
                </div>
                <div className="relative shrink-0">
                  <input
                    id="auto_compliance_check"
                    type="checkbox"
                    className="sr-only peer"
                    checked={settings.auto_compliance_check}
                    onChange={(e) => set('auto_compliance_check', e.target.checked)}
                  />
                  <div
                    onClick={() => set('auto_compliance_check', !settings.auto_compliance_check)}
                    className="flex w-10 h-5.5 bg-brand-divider peer-checked:bg-brand-primary rounded-full cursor-pointer transition-all duration-300 relative"
                  >
                    <div
                      className={`absolute top-0.5 left-0.5 bg-white rounded-full h-4.5 w-4.5 transition-transform duration-300 shadow-sm ${settings.auto_compliance_check ? 'translate-x-4.5' : ''}`}
                    />
                  </div>
                </div>
              </div>
              {settings.auto_compliance_check && (
                <div className="mt-4 pt-4 border-t border-brand-primary/10 relative z-10 animate-in fade-in slide-in-from-top-1">
                  <Label
                    htmlFor="compliance_check_interval"
                    className="block text-[10px] font-bold text-brand-light/90 mb-1.5 tracking-[0.15em] uppercase"
                  >
                    Check Interval
                  </Label>
                  <Select
                    value={settings.compliance_check_interval_hours.toString()}
                    onValueChange={(v) =>
                      set('compliance_check_interval_hours', parseInt(v || '0', 10))
                    }
                  >
                    <SelectTrigger
                      id="compliance_check_interval"
                      className="w-full font-mono bg-brand-base/40 border-brand-primary/20 h-9 text-xs"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">Every hour</SelectItem>
                      <SelectItem value="6">Every 6 hours</SelectItem>
                      <SelectItem value="12">Every 12 hours</SelectItem>
                      <SelectItem value="24">Daily (recommended)</SelectItem>
                      <SelectItem value="48">Every 2 days</SelectItem>
                      <SelectItem value="72">Every 3 days</SelectItem>
                      <SelectItem value="168">Weekly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            <div>
              <span className="text-xs font-bold text-brand-light/90 mb-3 block tracking-widest uppercase">
                Alert Channels
              </span>
              <div className="space-y-2">
                <label className="flex items-center justify-between p-3 rounded-lg border border-brand-divider bg-brand-base cursor-pointer hover:border-brand-primary/50 transition-colors">
                  <div>
                    <span className="text-sm font-medium text-brand-light">Telegram</span>
                    <p className="text-xs text-brand-light/60">
                      Requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    className="w-4 h-4 rounded-md border-brand-divider bg-brand-base text-brand-primary focus:ring-brand-primary/20 transition-all cursor-pointer"
                    checked={settings.alert_channels.includes('telegram')}
                    onChange={(e) =>
                      set(
                        'alert_channels',
                        e.target.checked
                          ? [...settings.alert_channels, 'telegram']
                          : settings.alert_channels.filter((c) => c !== 'telegram'),
                      )
                    }
                  />
                </label>
                <label className="flex items-center justify-between p-3 rounded-lg border border-brand-divider/40 bg-brand-surface/60 cursor-pointer hover:border-brand-primary/30 transition-colors">
                  <div>
                    <span className="text-sm font-medium text-brand-light">Email</span>
                    <p className="text-xs text-brand-light/60">Requires SMTP_HOST, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_TO env vars</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={settings.alert_channels?.includes('email') ?? false}
                    onChange={(e) =>
                      set(
                        'alert_channels',
                        e.target.checked
                          ? [...(settings.alert_channels ?? []), 'email']
                          : (settings.alert_channels ?? []).filter((c) => c !== 'email'),
                      )
                    }
                    className="w-4 h-4 rounded-md border-brand-divider bg-brand-base/20"
                  />
                </label>
                <label className="flex items-center justify-between p-3 rounded-lg border border-brand-divider/40 bg-brand-surface/60 cursor-pointer hover:border-brand-primary/30 transition-colors">
                  <div>
                    <span className="text-sm font-medium text-brand-light">Slack</span>
                    <p className="text-xs text-brand-light/60">Requires SLACK_WEBHOOK_URL env var</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={settings.alert_channels?.includes('slack') ?? false}
                    onChange={(e) =>
                      set(
                        'alert_channels',
                        e.target.checked
                          ? [...(settings.alert_channels ?? []), 'slack']
                          : (settings.alert_channels ?? []).filter((c) => c !== 'slack'),
                      )
                    }
                    className="w-4 h-4 rounded-md border-brand-divider bg-brand-base/20"
                  />
                </label>
              </div>
            </div>
          </div>
        </section>

        {/* AI Model Status */}
        {showAdvanced && <section id="section-model" className="space-y-4">
          <h2 className="heading-2 flex items-center gap-2">
            <Brain size={16} className="text-brand-primary" />
            AI Model
          </h2>
          <div className="card p-5 space-y-4">
            {mlStatus ? (
              <>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-brand-light/70">Active model</span>
                  <span className="font-mono font-semibold text-brand-primary">{mlStatus.model_type}</span>
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs text-brand-light/70">
                    <span>PPO readiness — training snapshots</span>
                    <span className="font-mono">
                      {mlStatus.snapshot_count.toLocaleString()} / {mlStatus.ppo_threshold.toLocaleString()}
                    </span>
                  </div>
                  <div className="h-2 bg-brand-divider rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${mlStatus.ppo_ready ? 'bg-brand-success' : 'bg-brand-primary'}`}
                      style={{ width: `${Math.min(100, (mlStatus.snapshot_count / mlStatus.ppo_threshold) * 100)}%` }}
                    />
                  </div>
                  {mlStatus.ppo_ready ? (
                    <p className="text-xs text-brand-success">PPO will be used on next Sunday retrain.</p>
                  ) : (
                    <p className="text-xs text-brand-light/50">
                      {(mlStatus.ppo_threshold - mlStatus.snapshot_count).toLocaleString()} more snapshots needed to unlock PPO.
                    </p>
                  )}
                </div>
              </>
            ) : (
              <p className="text-sm text-brand-light/50">Loading model status…</p>
            )}
          </div>
        </section>}
      </div>
      )}
    </div>
  )
}

export default Settings
