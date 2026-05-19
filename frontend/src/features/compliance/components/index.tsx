import { ChevronDown, ChevronRight, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import type React from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

export interface SourceDetail {
  source: string
  verdict: string
  note: string | null
}

export interface ComplianceResult {
  symbol: string
  is_compliant: boolean
  verdict: string // COMPLIANT | NON_COMPLIANT | DOUBTFUL | UNKNOWN
  reason: string | null
  debt_to_mkt_cap: number
  cash_to_mkt_cap: number
  impure_revenue_pct: number
  sector: string
  country: string | null
  company_name: string | null
  data_source: string | null
  data_as_of?: string | null
  data_stale?: boolean
  sources_detail: SourceDetail[]
  last_checked: string | null
  exchange?: string | null
}

export interface SearchSuggestion {
  symbol: string
  company_name: string
  exchange: string
  type: string
}

export const pct = (v: number) => `${(v * 100).toFixed(2)}%`

export const SOURCE_COLORS: Record<string, string> = {
  Zoya: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20',
  Musaffa: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
  YahooFinance: 'bg-brand-primary/10 text-brand-primary border-brand-primary/20',
  FMP: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  AlphaVantage: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/20',
}

export const verdictColor = (v: string) =>
  v === 'COMPLIANT'
    ? 'text-brand-success'
    : v === 'DOUBTFUL'
      ? 'text-brand-warning'
      : v === 'UNKNOWN'
        ? 'text-brand-light/70'
        : 'text-brand-danger'

export { RatioBar } from './RatioBar'

export const VerdictBadge: React.FC<{
  result: ComplianceResult
  expanded: boolean
  onClick: () => void
}> = ({ result, expanded, onClick }) => {
  const { verdict } = result

  const variant =
    verdict === 'COMPLIANT'
      ? 'success'
      : verdict === 'DOUBTFUL'
        ? 'warning'
        : verdict === 'UNKNOWN'
          ? 'outline'
          : 'destructive'

  const Icon =
    verdict === 'COMPLIANT' ? ShieldCheck : verdict === 'UNKNOWN' ? ShieldQuestion : ShieldAlert

  const label =
    verdict === 'COMPLIANT'
      ? 'HALAL'
      : verdict === 'DOUBTFUL'
        ? 'DOUBTFUL'
        : verdict === 'UNKNOWN'
          ? 'UNKNOWN'
          : 'HARAM'

  return (
    <Button
      variant="ghost"
      size="xs"
      onClick={onClick}
      className="h-6 gap-1 px-1 hover:bg-brand-elevated border-transparent"
      title="Click to see full calculation"
    >
      <Badge variant={variant} className="gap-1 px-1.5 h-5">
        <Icon size={11} />
        <span className="font-bold tracking-tight">{label}</span>
      </Badge>
      {expanded ? (
        <ChevronDown size={11} className="text-brand-light/70" />
      ) : (
        <ChevronRight size={11} className="text-brand-light/70" />
      )}
    </Button>
  )
}
