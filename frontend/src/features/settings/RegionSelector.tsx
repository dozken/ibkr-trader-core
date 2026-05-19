import { useQuery } from '@tanstack/react-query'
import { ROUTES } from '../../shared/routes'

interface RegionMarket {
  region: string
  is_open: boolean
  symbol_count: number
  ibkr_exchange: string
}

interface MarketsData {
  regions: RegionMarket[]
}

const REGION_FLAGS: Record<string, string> = {
  US: '🇺🇸', CA: '🇨🇦', MX: '🇲🇽', BR: '🇧🇷',
  UK: '🇬🇧', DE: '🇩🇪', FR: '🇫🇷', NL: '🇳🇱',
  CH: '🇨🇭', SE: '🇸🇪', NO: '🇳🇴', IT: '🇮🇹', ES: '🇪🇸',
  SA: '🇸🇦', AE: '🇦🇪', EG: '🇪🇬', TR: '🇹🇷', PK: '🇵🇰',
  JP: '🇯🇵', CN: '🇨🇳', HK: '🇭🇰', KR: '🇰🇷', TW: '🇹🇼',
  SG: '🇸🇬', MY: '🇲🇾', ID: '🇮🇩', TH: '🇹🇭', PH: '🇵🇭',
  VN: '🇻🇳', IN: '🇮🇳', AU: '🇦🇺', NZ: '🇳🇿', ZA: '🇿🇦',
}

interface Props {
  value: string[] | null | undefined
  onChange: (regions: string[] | null) => void
}

export default function RegionSelector({ value, onChange }: Props) {
  const { data, isLoading } = useQuery<MarketsData>({
    queryKey: ['system-markets'],
    queryFn: () => fetch(ROUTES.SYSTEM_MARKETS).then((r) => r.json()),
    staleTime: 120_000,
  })

  const allRegions = data?.regions ?? []
  const allRegionCodes = allRegions.map((r) => r.region)
  const allEnabled = value === null || value === undefined
  const selected = allEnabled ? new Set(allRegionCodes) : new Set(value ?? [])

  const toggle = (region: string) => {
    if (allEnabled) {
      const next = allRegionCodes.filter((r) => r !== region)
      onChange(next)
      return
    }
    const next = new Set(value ?? [])
    if (next.has(region)) next.delete(region)
    else next.add(region)
    // If all selected → use null (all)
    if (next.size === allRegionCodes.length) onChange(null)
    else onChange(Array.from(next))
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <Label />
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-[10px] uppercase tracking-wider text-brand-accent hover:text-brand-accent-light font-bold"
          >
            All
          </button>
          <span className="text-brand-light/30">·</span>
          <button
            type="button"
            onClick={() => onChange([])}
            className="text-[10px] uppercase tracking-wider text-brand-light/50 hover:text-brand-light font-bold"
          >
            None
          </button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-xs text-brand-light/40">Loading regions…</p>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-1.5">
          {allRegions.map((r) => {
            const on = selected.has(r.region)
            return (
              <button
                key={r.region}
                type="button"
                onClick={() => toggle(r.region)}
                className={`flex items-center gap-1.5 px-2 py-1.5 rounded-md border transition-all text-left ${
                  on
                    ? 'bg-brand-accent/15 border-brand-accent/40 text-brand-light'
                    : 'bg-brand-base/40 border-brand-divider text-brand-light/40 hover:border-brand-light/30'
                }`}
                title={`${r.region} · ${r.ibkr_exchange} · ${r.symbol_count} symbols`}
              >
                <span className="text-sm leading-none">{REGION_FLAGS[r.region] ?? '🌐'}</span>
                <span className="text-[10px] font-bold tracking-tight truncate">{r.region}</span>
                {r.is_open && (
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-brand-success animate-pulse shrink-0" />
                )}
              </button>
            )
          })}
        </div>
      )}
      <p className="text-[10px] text-brand-light/40 mt-2">
        {allEnabled
          ? `All ${allRegions.length} regions enabled.`
          : `${(value ?? []).length} of ${allRegions.length} regions selected.`}
        {' '}Green dot = market currently open.
      </p>
    </div>
  )
}

function Label() {
  return (
    <label className="block text-xs font-bold text-brand-light/70 uppercase tracking-wider">
      Enabled Regions
    </label>
  )
}
