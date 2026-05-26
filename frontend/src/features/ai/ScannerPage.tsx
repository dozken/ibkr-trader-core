import { useQuery } from '@tanstack/react-query'
import { Radar, ScanSearch, Search, ShieldCheck } from 'lucide-react'
import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Page, PageHeader, PageSection, InfoRow } from '@/components/ui/layout'
import { Input } from '@/components/ui/input'
import { TextTip } from '../../components/Tooltip'
import { ROUTES, API_KEY } from '../../shared/routes'

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

interface ScanResponse {
  status: 'done' | 'running'
  results: ScanResult[]
  total_fetched?: number
}

const fetchJson = (url: string) =>
  fetch(url, { headers: API_KEY ? { 'X-API-Key': API_KEY } : {} }).then((r) => r.json())

const ScannerPage = () => {
  const [query, setQuery] = useState('')
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)

  const { data: regions = [] } = useQuery<string[]>({
    queryKey: ['scan-regions'],
    queryFn: () => fetchJson(ROUTES.AI_SCAN_REGIONS),
    staleTime: 600_000,
  })

  const { data: universeData, isLoading: universeLoading } = useQuery<any>({
    queryKey: ['halal-universe'],
    queryFn: () => fetchJson(ROUTES.AI_HALAL_UNIVERSE),
    staleTime: 300_000,
  })

  const { data: scanData, isLoading: scanLoading, isFetching: scanFetching } = useQuery<ScanResponse>({
    queryKey: ['scan-region', selectedRegion],
    queryFn: () => fetchJson(ROUTES.AI_SCAN(selectedRegion!)),
    enabled: !!selectedRegion,
    refetchInterval: (query) => {
      const d = query.state.data as ScanResponse | undefined
      return d?.status === 'running' ? 2000 : false
    },
  })

  const universe: ScanResult[] = Array.isArray(universeData)
    ? universeData
    : Array.isArray(universeData?.sample)
      ? universeData.sample
      : []

  const scanResults: ScanResult[] = scanData?.results ?? []
  const activeResults = selectedRegion ? scanResults : universe
  const isScanning = scanLoading || scanFetching || scanData?.status === 'running'

  const displayResults = activeResults.filter(
    (r) =>
      !query ||
      r.symbol?.toLowerCase().includes(query.toLowerCase()) ||
      r.name?.toLowerCase().includes(query.toLowerCase()),
  )

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
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1 relative">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-light/70"
              size={18}
            />
            <Input
              placeholder="Filter results by symbol or name…"
              className="pl-10 h-12 text-base"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <select
            value={selectedRegion ?? ''}
            onChange={(e) => setSelectedRegion(e.target.value || null)}
            className="h-12 px-4 bg-brand-elevated border border-brand-divider rounded-lg text-sm text-brand-light focus:outline-none focus:border-brand-primary/60"
          >
            <option value="">All (Halal Universe)</option>
            {regions.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          {selectedRegion && (
            <Button
              className="h-12 px-8 shrink-0"
              disabled={isScanning}
              onClick={() => setSelectedRegion(selectedRegion)}
            >
              {isScanning ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Scanning…
                </>
              ) : (
                <>
                  <ScanSearch size={20} />
                  Run Scan
                </>
              )}
            </Button>
          )}
        </div>
      </PageSection>

      {selectedRegion && scanData?.status === 'done' && (
        <p className="text-xs text-brand-light/50 -mt-2 mb-2">
          {scanResults.length} results from {selectedRegion} scan · {scanResults.filter((r) => r.is_shariah).length} Shariah-compliant
        </p>
      )}

      {(universeLoading || (selectedRegion && isScanning && scanResults.length === 0)) ? (
        <div className="flex flex-col items-center justify-center py-20 opacity-50">
          <div className="w-12 h-12 border-4 border-brand-primary/20 border-t-brand-primary rounded-full animate-spin mb-4" />
          <p className="text-brand-light/70 font-medium">Scanning markets…</p>
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
                        <InfoRow className="text-brand-success text-xs font-bold uppercase">
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
                      {r.impure_revenue_pct != null
                        ? `${(r.impure_revenue_pct * 100).toFixed(2)}%`
                        : '—'}
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
                    {activeResults.length === 0
                      ? selectedRegion
                        ? 'No scan results yet. Select a region and run the scan.'
                        : 'No halal universe data available.'
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
