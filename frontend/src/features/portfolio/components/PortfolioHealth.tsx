import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Activity, Coins, Heart, PieChart } from 'lucide-react'
import type React from 'react'
import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Text, Eyebrow } from '@/components/ui/text'
import { ROUTES, API_KEY } from '../../../shared/routes'
import type { ComplianceSnapshot } from '../../../shared/types/trade'

interface PortfolioHealthProps {
  audits: ComplianceSnapshot[]
  portfolioValue: number
  complianceResults?: Record<string, { sector?: string; is_compliant?: boolean; impure_revenue_pct?: number }>
}

interface CardProps {
  icon: ReactNode
  iconTone: 'success' | 'accent' | 'primary' | 'danger'
  badge?: ReactNode
  label: string
  value: ReactNode
  valueTone?: 'default' | 'success' | 'accent' | 'danger'
  footer?: ReactNode
  href?: string
  progress?: number
}

const ICON_BG: Record<CardProps['iconTone'], string> = {
  success: 'bg-brand-success/10 border-brand-success/20',
  accent:  'bg-brand-accent/10 border-brand-accent/20',
  primary: 'bg-brand-primary/10 border-brand-primary/20',
  danger:  'bg-brand-danger/10 border-brand-danger/20',
}

const VALUE_TONE: Record<NonNullable<CardProps['valueTone']>, string> = {
  default: 'text-brand-light',
  success: 'text-brand-success',
  accent: 'text-brand-accent',
  danger: 'text-brand-danger',
}

function HealthCard({ icon, iconTone, badge, label, value, valueTone = 'default', footer, href, progress }: CardProps) {
  const body = (
    <>
      <div className="flex justify-between items-start mb-4 relative z-10">
        <div className={`p-2 rounded-lg border ${ICON_BG[iconTone]}`}>{icon}</div>
        {badge}
      </div>
      <Eyebrow as="h3" className="!tracking-wider relative z-10">{label}</Eyebrow>
      <p className={`text-2xl font-bold t-num mt-1 relative z-10 ${VALUE_TONE[valueTone]}`}>{value}</p>
      {footer && <div className="mt-1 relative z-10">{footer}</div>}
      {progress !== undefined && (
        <div
          className="absolute bottom-0 left-0 h-1 bg-brand-success/50 transition-all duration-1000"
          style={{ width: `${progress}%` }}
        />
      )}
    </>
  )
  const baseClass = 'card relative overflow-hidden'
  if (href) {
    return (
      <Link to={href} className={`${baseClass} group hover:border-brand-accent/40 transition-all cursor-pointer block`}>
        {body}
      </Link>
    )
  }
  return <div className={baseClass}>{body}</div>
}

const PortfolioHealth: React.FC<PortfolioHealthProps> = ({ audits, portfolioValue, complianceResults }) => {
  const dbItems = Object.values(complianceResults ?? {})
  const source = audits.length > 0 ? audits : dbItems.map((d) => ({
    is_compliant: d.is_compliant ?? false,
    sector: d.sector ?? 'Unknown',
    impure_revenue_pct: d.impure_revenue_pct ?? 0,
  }))
  const compliantCount = source.filter((a) => a.is_compliant).length
  const compliancePct = source.length > 0 ? (compliantCount / source.length) * 100 : null

  const { data: zakatData } = useQuery({
    queryKey: ['zakat-estimate', portfolioValue, API_KEY],
    queryFn: async () => {
      const res = await fetch(ROUTES.ZAKAT_CALCULATE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(API_KEY ? { 'X-API-Key': API_KEY } : {}) },
        body: JSON.stringify({ zakatable_assets_value: portfolioValue }),
      })
      if (!res.ok) return null
      return res.json() as Promise<{ zakat_due: number; below_nisab: boolean; nisab: number }>
    },
    enabled: portfolioValue > 0,
    staleTime: 5 * 60 * 1000,
  })

  const sectors = Array.from(new Set(source.map((a) => a.sector.split('/')[0].trim())))
  const maxImpurePct = source.length > 0 ? Math.max(...source.map((a) => a.impure_revenue_pct)) : 0

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
      <HealthCard
        icon={<Activity className={compliancePct === null ? 'text-brand-light/70' : 'text-brand-success'} size={20} />}
        iconTone="success"
        badge={compliancePct !== null && (
          <Badge variant={compliancePct === 100 ? 'success' : 'warning'} className="font-bold">
            {compliancePct === 100 ? 'PURE' : 'REVIEW'}
          </Badge>
        )}
        label="Compliance Health"
        value={compliancePct === null ? '—' : `${compliancePct.toFixed(0)}%`}
        progress={compliancePct ?? 0}
      />

      <HealthCard
        icon={<Coins className="text-brand-accent" size={20} />}
        iconTone="accent"
        badge={zakatData && !zakatData.below_nisab ? <Eyebrow>Est. 2.5%</Eyebrow> : undefined}
        label="Zakat Liability"
        value={
          !zakatData || zakatData.below_nisab
            ? '—'
            : <>
                ${zakatData.zakat_due.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                <span className="text-sm font-normal opacity-60 ml-1 t-num">
                  .{(zakatData.zakat_due % 1).toFixed(2).slice(2)}
                </span>
              </>
        }
        valueTone={zakatData && !zakatData.below_nisab ? 'accent' : 'default'}
        footer={
          <Text variant="tiny" className="flex items-center gap-1 group-hover:text-brand-accent transition-colors">
            View calculator <span className="group-hover:translate-x-0.5 transition-transform">→</span>
          </Text>
        }
        href="/zakat"
      />

      <HealthCard
        icon={<PieChart className="text-brand-primary" size={20} />}
        iconTone="primary"
        label="Diversification"
        value={
          <>
            {sectors.length}
            <span className="text-xs font-bold uppercase tracking-tight ml-1 text-brand-light/70">Sectors</span>
          </>
        }
      />

      <HealthCard
        icon={<Heart className="text-brand-danger" size={20} />}
        iconTone="danger"
        badge={maxImpurePct > 0 && <Badge variant="destructive" className="font-bold">ALERT</Badge>}
        label="Purification Owed"
        value={
          source.length === 0
            ? '—'
            : maxImpurePct > 0
              ? <>{(maxImpurePct * 100).toFixed(2)}%<span className="text-xs font-bold uppercase ml-1">Impure</span></>
              : '$0.00'
        }
        valueTone={source.length === 0 ? 'default' : maxImpurePct > 0 ? 'danger' : 'success'}
      />
    </div>
  )
}

export default PortfolioHealth
