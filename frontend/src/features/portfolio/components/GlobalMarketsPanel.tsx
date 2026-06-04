import { useQuery } from '@tanstack/react-query'
import { Globe } from 'lucide-react'
import { useState } from 'react'
import { Text } from '@/components/ui/text'
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

// Is region open during the [h, h+1) UTC hour bucket? Handles midnight wrap.
function openInHour(r: RegionMarket, h: number): boolean {
  return r.utc_sessions.some((s) => {
    const mid = h + 0.5
    return s.close_utc_h >= s.open_utc_h
      ? mid >= s.open_utc_h && mid < s.close_utc_h
      : mid >= s.open_utc_h || mid < s.close_utc_h
  })
}

function DensityStrip({ regions, utcNow }: { regions: RegionMarket[]; utcNow: number }) {
  const [hover, setHover] = useState<{ h: number; n: number } | null>(null)

  // Markets open per UTC hour → density.
  const perHour = Array.from({ length: 24 }, (_, h) => regions.filter((r) => openInHour(r, h)).length)
  const max = Math.max(1, ...perHour)
  const nowPct = (utcNow / 24) * 100
  const nowH = String(Math.floor(utcNow)).padStart(2, '0')
  const nowM = String(Math.floor((utcNow % 1) * 60)).padStart(2, '0')

  const openNow = regions.filter((r) => r.is_open)

  return (
    <div className="px-6 py-5">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <span className="t-eyebrow">How many markets are open, each hour</span>
          <Text variant="tiny" className="opacity-50 mt-0.5">Taller bar = more of the 32 markets trading at that UTC hour</Text>
        </div>
        <Text variant="tiny" className="t-num shrink-0">now {nowH}:{nowM} UTC</Text>
      </div>

      {/* Histogram — bar height = # markets open that hour */}
      <div className="relative pl-6">
        {/* y-axis: peak count + baseline 0 */}
        <span className="absolute left-0 top-0 t-num text-[9px] text-brand-light/40 leading-none">{max}</span>
        <span className="absolute left-0 bottom-0 t-num text-[9px] text-brand-light/40 leading-none">0</span>

        <div className="flex gap-0.5 h-12 items-end border-l border-b border-brand-divider/50">
          {perHour.map((n, h) => (
            <div
              key={h}
              className="flex-1 h-full flex items-end"
              onMouseEnter={() => setHover({ h, n })}
              onMouseLeave={() => setHover(null)}
            >
              <div
                className="w-full rounded-t-sm bg-brand-success/70 hover:bg-brand-success transition-all"
                style={{ height: n ? `${Math.max(8, (n / max) * 100)}%` : '0%' }}
              />
            </div>
          ))}
        </div>

        {/* NOW marker over the bar area */}
        <div
          className="absolute top-0 bottom-0 w-px bg-brand-primary z-10 pointer-events-none"
          style={{ left: `calc(1.5rem + ${nowPct}% * (100% - 1.5rem) / 100%)` }}
        >
          <span className="absolute -top-0.5 left-1 text-[8px] font-bold text-brand-primary whitespace-nowrap">now</span>
        </div>

        {/* Hover readout */}
        {hover && (
          <div className="absolute -top-5 right-0 t-num text-[10px] font-bold text-brand-light bg-brand-surface border border-brand-divider rounded px-1.5 py-0.5 pointer-events-none">
            {String(hover.h).padStart(2, '0')}:00 UTC · {hover.n} of {regions.length} open
          </div>
        )}

        {/* Hour ruler */}
        <div className="relative h-3 mt-1 select-none">
          {[0, 6, 12, 18, 24].map((h) => (
            <span
              key={h}
              className="absolute -translate-x-1/2 top-0 text-[9px] font-mono text-brand-light/40"
              style={{ left: `${(h / 24) * 100}%` }}
            >
              {String(h).padStart(2, '0')}
            </span>
          ))}
        </div>
      </div>

      {/* Open-now flag chips */}
      <div className="flex flex-wrap items-center gap-1.5 mt-4">
        <span className="t-eyebrow mr-0.5">Open now</span>
        {openNow.length === 0 ? (
          <Text variant="tiny" className="opacity-60">— none</Text>
        ) : (
          openNow.map((r) => (
            <span
              key={r.region}
              title={`${r.region} · ${r.local_time} · ${r.symbol_count} halal`}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-brand-success/10 border border-brand-success/25 text-[10px] font-bold text-brand-success"
            >
              <span className="leading-none">{REGION_FLAGS[r.region] ?? '🌐'}</span>
              {r.region}
            </span>
          ))
        )}
      </div>
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

      <DensityStrip regions={data.regions} utcNow={data.utc_now_h} />
    </div>
  )
}
