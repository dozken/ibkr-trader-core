import { useQuery } from '@tanstack/react-query'
import { useLocation } from '@tanstack/react-router'
import { Radar, ScanSearch, Search, ShieldCheck } from 'lucide-react'
import React, { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Page, PageHeader, PageSection, CardGrid, ActionRow, InfoRow, Stack } from '@/components/ui/layout'
import { Input } from '@/components/ui/input'
import { InfoTip, TextTip } from '../../components/Tooltip'
import { ROUTES } from '../../shared/routes'

interface ScanResult {
  symbol: string
  name: string
  price?: number
  change_pct?: number
  is_shariah: boolean
  debt_ratio?: number
  debt_to_mkt_cap?: number
  cash_ratio?: number
  receivables_ratio?: number
  impure_revenue_pct: number
}

const ScannerPage = () => {
  const _location = useLocation()
  const [results, setResults] = useState<ScanResult[]>([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')

  const { data: universeData, isLoading: universeLoading } = useQuery<any>({
    queryKey: ['halal-universe'],
    queryFn: () => fetch(ROUTES.AI_HALAL_UNIVERSE).then((r) => r.json()),
    staleTime: 300_000,
  })

  const universe: ScanResult[] = Array.isArray(universeData)
    ? universeData
    : Array.isArray(universeData?.sample)
      ? universeData.sample
      : []

  const displayResults = universe.filter((r) =>
    !query || r.symbol?.toLowerCase().includes(query.toLowerCase()) || r.name?.toLowerCase().includes(query.toLowerCase())
  )

  useEffect(() => {
    // Initial fetch or based on search
  }, [])

  return (
    <Page>
      <PageHeader>
        <div>
          <h1 className="heading-1">
                    <Radar className="text-brand-primary" />
                    Market Scanner
                  </h1>
                  <p className="text-brand-light/70">
                    Scan global markets for Shariah-compliant opportunities
                  </p>
        </div>
      </PageHeader>

      <PageSection className="card">
        <div className="flex gap-4">
          <div className="flex-1 relative">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-light/70"
              size={18}
            />
            <Input
              placeholder="Search by region, sector or theme (e.g. US Tech, Japan AI)..."
              className="pl-10 h-12 text-base"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <Button className="h-12 px-8 shrink-0">
            <ScanSearch size={20} />
            Run Scan
          </Button>
        </div>
      </PageSection>

      {universeLoading ? (
        <div className="flex flex-col items-center justify-center py-20 opacity-50">
          <div className="w-12 h-12 border-4 border-brand-primary/20 border-t-brand-primary rounded-full animate-spin mb-4" />
          <p className="text-brand-light/70 font-medium">Scanning markets...</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="w-full text-left">
            <thead className="table-header">
              <tr>
                <th className="p-4">Asset</th>
                <th className="p-4">Price</th>
                <th className="p-4">Chg %</th>
                <th className="p-4">
                  <TextTip text="Shariah status based on business activity and financial ratios. PASS means the company meets AAOIFI standards.">
                    Compliance
                  </TextTip>
                </th>
                <th className="p-4">
                  <TextTip text="Total Interest-Bearing Debt / Market Cap. Must be less than 33% to pass.">
                    Debt Ratio
                  </TextTip>
                </th>
                <th className="p-4">
                  <TextTip text="Income from non-compliant sources. Must be less than 5% of total revenue.">
                    Impure Rev
                  </TextTip>
                </th>
              </tr>
            </thead>
            <tbody>
              {displayResults.map((r) => (
                <React.Fragment key={r.symbol}>
                  <tr className="table-row">
                    <td className="table-cell">
                      <div className="flex flex-col">
                        <span className="font-bold">{r.symbol}</span>
                        <span className="text-[10px] text-brand-light/70 uppercase tracking-tight">
                          {r.name}
                        </span>
                      </div>
                    </td>
                    <td className="table-cell font-mono">
                      {r.price != null ? `$${r.price.toFixed(2)}` : '—'}
                    </td>
                    <td
                      className={`table-cell font-mono ${r.change_pct == null ? 'text-brand-light/50' : r.change_pct >= 0 ? 'text-brand-success' : 'text-brand-danger'}`}
                    >
                      {r.change_pct != null
                        ? `${r.change_pct >= 0 ? '+' : ''}${r.change_pct.toFixed(2)}%`
                        : '—'}
                    </td>
                    <td className="table-cell">
                      {r.is_shariah ? (
                        <InfoRow className=" text-brand-success text-xs font-bold uppercase">
                          <ShieldCheck size={14} /> Pass
                        </InfoRow>
                      ) : (
                        <span className="text-brand-danger text-xs font-bold uppercase">Fail</span>
                      )}
                    </td>
                    <td className="table-cell font-mono text-xs text-brand-light/70">
                      {r.debt_to_mkt_cap != null
                        ? `${(r.debt_to_mkt_cap * 100).toFixed(2)}%`
                        : r.debt_ratio != null
                          ? `${(r.debt_ratio * 100).toFixed(2)}%`
                          : '—'}
                    </td>
                    <td className="table-cell font-mono text-xs text-brand-light/70">
                      {r.impure_revenue_pct != null ? `${(r.impure_revenue_pct * 100).toFixed(2)}%` : '—'}
                    </td>
                  </tr>
                </React.Fragment>
              ))}
              {displayResults.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="table-cell text-center py-20 text-brand-light/70 italic"
                  >
                    {universe.length === 0
                      ? 'Start a scan to see potential Shariah-compliant opportunities.'
                      : 'No results match your search.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  )
}

export default ScannerPage
