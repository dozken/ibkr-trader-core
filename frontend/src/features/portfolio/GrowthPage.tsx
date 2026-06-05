import { useQuery } from '@tanstack/react-query'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { Page, PageHeader, PageSection, Stack } from '@/components/ui/layout'
import { Heading } from '@/components/ui/primitives'
import { Text } from '@/components/ui/text'
import { ROUTES, withAccount } from '../../shared/routes'
import { useAccount } from '../trading/context/AccountContext'
import { ErrorBoundary } from '../../components/ErrorBoundary'
import { useTheme } from '../../lib/ThemeContext'
import { chartTheme } from '../../lib/chartTheme'

function projectGrowth(
  principal: number,
  monthlyAdd: number,
  annualRate: number,
  years: number,
): { month: number; year: number; value: number }[] {
  const monthlyRate = annualRate / 12
  const points: { month: number; year: number; value: number }[] = []
  let value = principal
  const totalMonths = years * 12
  for (let m = 0; m <= totalMonths; m++) {
    points.push({ month: m, year: +(m / 12).toFixed(1), value: Math.round(value) })
    value = value * (1 + monthlyRate) + monthlyAdd
  }
  return points
}

function formatCurrency(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 10_000) return `$${(v / 1_000).toFixed(1)}K`
  return `$${v.toLocaleString()}`
}

function GrowthCalculator() {
  const { selectedAccountId } = useAccount()
  const { themeId } = useTheme() // subscribe so chart colors re-read on theme switch
  const ct = chartTheme()
  void themeId

  const { data: summary } = useQuery<{
    total_value?: number
    cost_basis?: number
    unrealized_pnl?: number
    return_pct?: number
  }>({
    queryKey: ['portfolio-summary', selectedAccountId],
    queryFn: () => fetch(withAccount(ROUTES.PORTFOLIO_SUMMARY, selectedAccountId)).then((r) => r.json()),
    staleTime: 60_000,
  })

  const currentValue = summary?.total_value ?? 0
  const [monthlyAdd, setMonthlyAdd] = useState(0)
  const [years, setYears] = useState(10)
  const [customRate, setCustomRate] = useState(15)

  const scenarios = [
    { label: 'Conservative', rate: 0.08, color: ct.axis },
    { label: 'Moderate', rate: 0.15, color: ct.primary },
    { label: 'Optimistic', rate: 0.25, color: ct.success },
    { label: 'Custom', rate: customRate / 100, color: ct.accent },
  ]

  const projections = scenarios.map((s) => ({
    ...s,
    data: projectGrowth(currentValue, monthlyAdd, s.rate, years),
  }))

  const milestones = [1, 3, 5, 10, 20].filter((y) => y <= years)

  return (
    <Page>
      <PageHeader>
        <Stack gap="xs">
          <Heading icon={TrendingUp}>Growth Projection</Heading>
          <Text tone="muted">Compound growth scenarios for your portfolio</Text>
        </Stack>
      </PageHeader>

      {/* Controls */}
      <PageSection className="card p-5 sm:p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-brand-light/50 block mb-2">
              Current Portfolio
            </label>
            <div className="text-2xl font-black font-mono text-brand-light">
              {formatCurrency(currentValue)}
            </div>
          </div>
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-brand-light/50 block mb-2">
              Monthly Contribution
            </label>
            <input
              type="range"
              min={0}
              max={1000}
              step={25}
              value={monthlyAdd}
              onChange={(e) => setMonthlyAdd(Number(e.target.value))}
              className="w-full accent-brand-primary"
            />
            <div className="flex justify-between text-xs mt-1">
              <span className="text-brand-light/50">$0</span>
              <span className="font-bold font-mono text-brand-primary">${monthlyAdd}/mo</span>
              <span className="text-brand-light/50">$1,000</span>
            </div>
          </div>
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-brand-light/50 block mb-2">
              Time Horizon
            </label>
            <input
              type="range"
              min={1}
              max={30}
              step={1}
              value={years}
              onChange={(e) => setYears(Number(e.target.value))}
              className="w-full accent-brand-primary"
            />
            <div className="flex justify-between text-xs mt-1">
              <span className="text-brand-light/50">1Y</span>
              <span className="font-bold font-mono text-brand-primary">{years} years</span>
              <span className="text-brand-light/50">30Y</span>
            </div>
          </div>
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-brand-light/50 block mb-2">
              Custom Rate
            </label>
            <input
              type="range"
              min={1}
              max={40}
              step={1}
              value={customRate}
              onChange={(e) => setCustomRate(Number(e.target.value))}
              className="w-full accent-purple-400"
            />
            <div className="flex justify-between text-xs mt-1">
              <span className="text-brand-light/50">1%</span>
              <span className="font-bold font-mono text-purple-400">{customRate}%/yr</span>
              <span className="text-brand-light/50">40%</span>
            </div>
          </div>
        </div>
      </PageSection>

      {/* Chart */}
      <PageSection className="card p-5 sm:p-6">
        <h2 className="heading-2 mb-4">
          <TrendingUp size={18} className="text-brand-primary" />
          Projected Portfolio Value
        </h2>
        <div className="h-[350px] sm:h-[400px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
              <defs>
                {scenarios.map((s) => (
                  <linearGradient key={s.label} id={`grad-${s.label}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={s.color} stopOpacity={0.15} />
                    <stop offset="95%" stopColor={s.color} stopOpacity={0} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} opacity={0.3} />
              <XAxis
                dataKey="year"
                type="number"
                domain={[0, years]}
                tickFormatter={(v) => `${v}Y`}
                tick={{ fill: ct.axis, fontSize: 11 }}
                axisLine={{ stroke: ct.grid }}
              />
              <YAxis
                tickFormatter={formatCurrency}
                tick={{ fill: ct.axis, fontSize: 11 }}
                axisLine={{ stroke: ct.grid }}
                width={65}
              />
              <Tooltip
                contentStyle={{
                  background: ct.surface,
                  border: `1px solid ${ct.grid}`,
                  borderRadius: '8px',
                  fontSize: '12px',
                  color: ct.text,
                }}
                formatter={(value: number) => [formatCurrency(value), '']}
                labelFormatter={(v) => `Year ${v}`}
              />
              {projections.map((p) => (
                <Area
                  key={p.label}
                  data={p.data}
                  dataKey="value"
                  name={`${p.label} (${(p.rate * 100).toFixed(0)}%)`}
                  type="monotone"
                  stroke={p.color}
                  strokeWidth={2}
                  fill={`url(#grad-${p.label})`}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </PageSection>

      {/* Milestones Table */}
      <PageSection className="card p-5 sm:p-6">
        <h2 className="heading-2 mb-4">Milestones</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-brand-light/50 uppercase tracking-wider text-[10px] border-b border-brand-divider/40">
                <th className="pb-2 pr-4">Scenario</th>
                <th className="pb-2 pr-4">Rate</th>
                {milestones.map((y) => (
                  <th key={y} className="pb-2 pr-4 text-right">{y}Y</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {projections.map((p) => (
                <tr key={p.label} className="border-b border-brand-divider/20">
                  <td className="py-3 pr-4">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ background: p.color }} />
                      <span className="font-bold text-brand-light">{p.label}</span>
                    </div>
                  </td>
                  <td className="py-3 pr-4 font-mono" style={{ color: p.color }}>
                    {(p.rate * 100).toFixed(0)}%
                  </td>
                  {milestones.map((y) => {
                    const point = p.data.find((d) => d.month === y * 12)
                    const gain = point ? point.value - currentValue - monthlyAdd * y * 12 : 0
                    return (
                      <td key={y} className="py-3 pr-4 text-right">
                        <div className="font-mono font-bold text-brand-light">
                          {point ? formatCurrency(point.value) : '—'}
                        </div>
                        <div className="text-[10px] text-brand-success font-mono">
                          +{formatCurrency(Math.max(0, gain))}
                        </div>
                      </td>
                    )
                  })}
                </tr>
              ))}
              <tr className="border-t border-brand-divider/60">
                <td className="py-3 pr-4 text-brand-light/50" colSpan={2}>
                  Total contributed
                </td>
                {milestones.map((y) => (
                  <td key={y} className="py-3 pr-4 text-right text-brand-light/50 font-mono">
                    {formatCurrency(currentValue + monthlyAdd * y * 12)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-brand-light/40 mt-4">
          Projections assume reinvested returns and constant monthly contributions. Actual results vary. Past performance does not guarantee future returns. Shariah-compliant portfolios exclude interest income.
        </p>
      </PageSection>
    </Page>
  )
}

export default function GrowthPageWithBoundary() {
  return (
    <ErrorBoundary title="Growth projections unavailable">
      <GrowthCalculator />
    </ErrorBoundary>
  )
}
