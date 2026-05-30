import { useQuery } from '@tanstack/react-query'
import { Globe } from 'lucide-react'
import { useState } from 'react'
import { Text, Eyebrow } from '@/components/ui/text'
import { ROUTES } from '../../../shared/routes'

interface UtcSession {
  open_utc_h: number
  close_utc_h: number
  local_open: string
  local_close: string
}

interface RegionMarket {
  region: string
  continent: string
  exchange: string
  ibkr_exchange: string
  currency: string
  timezone: string
  local_time: string
  is_open: boolean
  is_holiday: boolean
  sessions: string[]
  utc_sessions: UtcSession[]
  symbol_count: number
}

interface MarketsData {
  regions: RegionMarket[]
  open_count: number
  total_count: number
  total_symbols: number
  utc_now_h: number
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

const REGION_NAMES: Record<string, string> = {
  US: 'United States', CA: 'Canada', MX: 'Mexico', BR: 'Brazil',
  UK: 'United Kingdom', DE: 'Germany', FR: 'France', NL: 'Netherlands',
  CH: 'Switzerland', SE: 'Sweden', NO: 'Norway', IT: 'Italy', ES: 'Spain',
  SA: 'Saudi Arabia', AE: 'UAE', EG: 'Egypt', TR: 'Turkey', PK: 'Pakistan',
  JP: 'Japan', CN: 'China', HK: 'Hong Kong', KR: 'South Korea', TW: 'Taiwan',
  SG: 'Singapore', MY: 'Malaysia', ID: 'Indonesia', TH: 'Thailand', PH: 'Philippines',
  VN: 'Vietnam', IN: 'India', AU: 'Australia', NZ: 'New Zealand', ZA: 'South Africa',
}

const CONTINENT_ORDER = ['Americas', 'Europe', 'MENA', 'Africa', 'Asia', 'Oceania']

interface BarHover {
  region: RegionMarket
  x: number
  y: number
}

function Timeline({ regions, utcNow }: { regions: RegionMarket[]; utcNow: number }) {
  const [hover, setHover] = useState<BarHover | null>(null)

  const byContinent = regions.reduce<Record<string, RegionMarket[]>>((acc, r) => {
    (acc[r.continent] ??= []).push(r)
    return acc
  }, {})

  // Sort each continent by UTC open time
  for (const k of Object.keys(byContinent)) {
    byContinent[k].sort((a, b) => (a.utc_sessions[0]?.open_utc_h ?? 99) - (b.utc_sessions[0]?.open_utc_h ?? 99))
  }

  const nowPct = (utcNow / 24) * 100
  const nowH = String(Math.floor(utcNow)).padStart(2, '0')
  const nowM = String(Math.floor((utcNow % 1) * 60)).padStart(2, '0')

  return (
    <div className="px-6 py-5 border-b border-brand-divider/40 relative">
      <div className="flex items-center justify-between mb-3">
        <Eyebrow>24-hour Trading Rail (UTC)</Eyebrow>
        <Text variant="tiny" className="t-num">now {nowH}:{nowM} UTC</Text>
      </div>

      {/* Hour ruler */}
      <div className="relative h-4 mb-2 ml-14 select-none">
        <div className="absolute inset-x-0 top-1/2 h-px bg-brand-divider/40" />
        {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
          <div
            key={h}
            className="absolute -translate-x-1/2 top-0 text-[9px] font-mono text-brand-light/40"
            style={{ left: `${(h / 24) * 100}%` }}
          >
            {String(h).padStart(2, '0')}
          </div>
        ))}
      </div>

      {/* Rows grouped by continent */}
      <div className="relative">
        {/* NOW line spans entire stack — positioned over bar area only */}
        <div
          className="absolute top-0 bottom-0 w-px bg-brand-primary/70 z-10 shadow-[0_0_8px_rgba(45,212,191,0.5)] pointer-events-none"
          style={{ left: `calc(3.5rem + ${nowPct}% * (100% - 3.5rem) / 100%)` }}
        />

        {CONTINENT_ORDER.filter((c) => byContinent[c]?.length).map((continent) => (
          <div key={continent} className="mb-3 last:mb-0">
            <div className="text-[9px] uppercase tracking-[0.2em] font-bold text-brand-light/30 mb-1 ml-14">
              {continent}
            </div>
            <div className="space-y-1">
              {byContinent[continent].map((r) => (
                <div key={r.region} className="relative h-5 flex items-center">
                  {/* Label */}
                  <div className="w-14 flex items-center gap-1.5 shrink-0 z-20">
                    <span className="text-xs leading-none">{REGION_FLAGS[r.region] ?? '🌐'}</span>
                    <span className={`text-[10px] font-bold leading-none ${r.is_open ? 'text-brand-light' : 'text-brand-light/40'}`}>
                      {r.region}
                    </span>
                  </div>
                  {/* Bars */}
                  <div className="relative flex-1 h-full">
                    {r.utc_sessions.map((s, i) => {
                      const segments: Array<[number, number]> =
                        s.close_utc_h >= s.open_utc_h
                          ? [[s.open_utc_h, s.close_utc_h]]
                          : [[s.open_utc_h, 24], [0, s.close_utc_h]]
                      return segments.map(([o, c], j) => (
                        <div
                          key={`${i}-${j}`}
                          className={`absolute top-1/2 -translate-y-1/2 h-2 rounded-sm transition-all cursor-pointer ${
                            r.is_open
                              ? 'bg-brand-success/70 shadow-[0_0_8px_rgba(45,212,191,0.4)] hover:bg-brand-success hover:h-3'
                              : r.is_holiday
                                ? 'bg-amber-500/30 hover:bg-amber-500/60 hover:h-3'
                                : 'bg-brand-light/15 hover:bg-brand-light/40 hover:h-3'
                          }`}
                          style={{
                            left: `${(o / 24) * 100}%`,
                            width: `${((c - o) / 24) * 100}%`,
                          }}
                          onMouseEnter={(e) => {
                            const rect = e.currentTarget.getBoundingClientRect()
                            const panel = e.currentTarget.closest('.relative.px-6')?.getBoundingClientRect()
                            setHover({
                              region: r,
                              x: rect.left + rect.width / 2 - (panel?.left ?? 0),
                              y: rect.top - (panel?.top ?? 0) - 8,
                            })
                          }}
                          onMouseLeave={() => setHover(null)}
                        />
                      ))
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Custom hover tooltip */}
      {hover && (
        <div
          className="absolute z-30 pointer-events-none -translate-x-1/2 -translate-y-full px-3 py-2 rounded-lg bg-brand-surface border border-brand-divider shadow-2xl text-left whitespace-nowrap"
          style={{ left: hover.x, top: hover.y }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-base leading-none">{REGION_FLAGS[hover.region.region] ?? '🌐'}</span>
            <span className="text-xs font-bold text-brand-light">{REGION_NAMES[hover.region.region]}</span>
            <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
              hover.region.is_open
                ? 'bg-brand-success/20 text-brand-success'
                : hover.region.is_holiday
                  ? 'bg-amber-500/20 text-amber-400'
                  : 'bg-brand-light/10 text-brand-light/50'
            }`}>
              {hover.region.is_open ? 'OPEN' : hover.region.is_holiday ? 'HOLIDAY' : 'CLOSED'}
            </span>
          </div>
          <div className="text-[10px] text-brand-light/70 t-num space-y-0.5">
            <div>Local: {hover.region.sessions.join(', ')} ({hover.region.timezone})</div>
            {hover.region.utc_sessions.map((s, i) => (
              <div key={i}>
                UTC: {String(Math.floor(s.open_utc_h)).padStart(2, '0')}:{String(Math.floor((s.open_utc_h % 1) * 60)).padStart(2, '0')}–{String(Math.floor(s.close_utc_h)).padStart(2, '0')}:{String(Math.floor((s.close_utc_h % 1) * 60)).padStart(2, '0')}
              </div>
            ))}
            <div>Now: {hover.region.local_time} · {hover.region.symbol_count} halal symbols</div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function GlobalMarketsPanel() {
  const { data, isLoading } = useQuery<MarketsData>({
    queryKey: ['system-markets'],
    queryFn: () => fetch(ROUTES.SYSTEM_MARKETS).then((r) => r.json()),
    refetchInterval: 60_000,
  })

  if (isLoading || !data) return null

  return (
    <div className="card p-0 mb-6 overflow-hidden">
      <header className="px-6 py-4 border-b border-brand-divider/40 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Globe size={16} className="text-brand-primary" />
          <Text variant="h3">Global Markets</Text>
        </div>
        <div className="flex items-center gap-3">
          <Text variant="tiny" as="span">
            <span className="t-num font-bold text-brand-success">{data.open_count}</span>
            <span className="opacity-60"> / {data.total_count} open</span>
          </Text>
          <span className="text-brand-light/30">·</span>
          <Text variant="tiny" as="span">
            <span className="t-num font-bold text-brand-light">{data.total_symbols}</span>
            <span className="opacity-60"> halal symbols</span>
          </Text>
        </div>
      </header>

      <Timeline regions={data.regions} utcNow={data.utc_now_h} />
    </div>
  )
}
