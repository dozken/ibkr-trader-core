import {
  ArrowRight,
  Banknote,
  CheckCircle2,
  Clock,
  Loader,
  Newspaper,
  Scale,
  ScanSearch,
  Search,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  XCircle,
} from 'lucide-react'
import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@/components/ui/button'
import { Page, PageHeader, PageSection, CardGrid, ActionRow, InfoRow, Stack } from '@/components/ui/layout'
import { Input } from '@/components/ui/input'
import { Abbr, InfoTip, TextTip } from '../../components/Tooltip'
import { ROUTES } from '../../shared/routes'
import {
  pct,
  type ComplianceResult as ScreenResult,
  type SearchSuggestion,
  SOURCE_COLORS,
  type SourceDetail,
  verdictColor,
} from './components'

const SourceBadges: React.FC<{ sources: SourceDetail[] }> = ({ sources }) => (
  <div className="flex flex-wrap gap-1.5">
    {sources.map((s, i) => (
      <div
        key={i}
        title={s.note ?? ''}
        className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[10px] ${SOURCE_COLORS[s.source] ?? 'bg-brand-base text-brand-light/70 border-brand-divider'}`}
      >
        <span className="font-bold">{s.source}</span>
        <span className={`font-black ${verdictColor(s.verdict)}`}>{s.verdict}</span>
      </div>
    ))}
  </div>
)

const Check: React.FC<{ pass: boolean; label: string; value: string; limit: string }> = ({
  pass,
  label,
  value,
  limit,
}) => (
  <div
    className={`flex flex-col gap-2 p-3.5 rounded-xl border transition-all ${
      pass
        ? 'border-brand-success/20 bg-brand-success/5'
        : 'border-brand-danger/20 bg-brand-danger/5'
    }`}
  >
    <div className="flex items-center justify-between">
      <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-brand-light/70 opacity-80">
        {label}
      </span>
      {pass ? (
        <CheckCircle2 size={14} className="text-brand-success" />
      ) : (
        <XCircle size={14} className="text-brand-danger" />
      )}
    </div>
    <div className="flex items-baseline justify-between">
      <span
        className={`font-mono font-bold text-lg ${pass ? 'text-brand-success' : 'text-brand-danger'}`}
      >
        {value}
      </span>
      <span className="text-[10px] text-brand-light/70 font-medium opacity-60">limit {limit}</span>
    </div>
  </div>
)

const PIPELINE: { icon: React.ElementType; title: string; desc: React.ReactNode }[] = [
  {
    icon: Newspaper,
    title: 'Signal',
    desc: 'Alpha Vantage news sentiment (US) or yfinance headlines (watchlist). Score ≥ 0.35 → BUY candidate.',
  },
  {
    icon: ScanSearch,
    title: 'Sector',
    desc: 'Business activity checked against prohibited list: Conventional Finance, Alcohol, Tobacco, Gambling, Adult Content, Pork, Defense, Weapons.',
  },
  {
    icon: Scale,
    title: 'Ratios',
    desc: (
      <>
        <Abbr>AAOIFI</Abbr> financial screening: Debt/MktCap &lt; 33%, Cash/MktCap &lt; 33%, Impure
        Revenue &lt; 5%. Data from Yahoo Finance.
      </>
    ),
  },
  {
    icon: Banknote,
    title: 'Funds',
    desc: (
      <>
        Cash-only guard. Total cost (qty × price) must not exceed available <Abbr>IBKR</Abbr>{' '}
        balance. No margin, no leverage.
      </>
    ),
  },
  {
    icon: Clock,
    title: 'Market',
    desc: 'Exchange-aware hours check. Japan/China have lunch breaks. Gulf markets trade Sun–Thu. Order skipped if market closed.',
  },
  {
    icon: ShieldCheck,
    title: 'Execute',
    desc: (
      <>
        Market order submitted via <Abbr>IBKR</Abbr> with exchange-specific routing and currency.
        Order ID logged to audit trail.
      </>
    ),
  },
]

const ScreeningPage = () => {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [result, setResult] = useState<ScreenResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [dropdownRect, setDropdownRect] = useState<{
    top: number
    left: number
    width: number
  } | null>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = query.trim()
    if (q.length < 2) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(ROUTES.COMPLIANCE_SEARCH(q))
        if (res.ok) {
          const data: SearchSuggestion[] = await res.json()
          setSuggestions(data)
          if (data.length > 0 && inputRef.current) {
            const r = inputRef.current.getBoundingClientRect()
            setDropdownRect({
              top: r.bottom + window.scrollY + 4,
              left: r.left + window.scrollX,
              width: r.width,
            })
          }
          setShowSuggestions(data.length > 0)
        }
      } catch {
        /* ignore */
      }
    }, 300)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  const screen = async (sym?: string) => {
    const raw = sym ?? query.trim()
    const resolved = raw.toUpperCase()
    if (!resolved) return
    setShowSuggestions(false)
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(ROUTES.COMPLIANCE_SCREEN(resolved))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setResult(await res.json())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const pickSuggestion = (s: SearchSuggestion) => {
    setQuery(s.symbol)
    setSuggestions([])
    setShowSuggestions(false)
    screen(s.symbol)
  }

  const debtPass = result ? result.debt_to_mkt_cap < 0.33 : false
  const cashPass = result ? result.cash_to_mkt_cap < 0.33 : false
  const impurePass = result ? result.impure_revenue_pct < 0.05 : false

  return (
    <Page>
      <PageHeader>
        <div>
          <h1 className="heading-1">
                    <ScanSearch className="text-brand-primary" />
                    Shariah Screening Process
                  </h1>
                  <p className="text-brand-light/70">Every trade passes this pipeline before execution</p>
        </div>
      </PageHeader>

      {/* Pipeline */}
      <PageSection className="card p-5 sm:p-6">
        <h2 className="heading-2 mb-6 flex items-center gap-2">
          <Scale className="text-brand-primary" size={20} />
          Screening Pipeline
        </h2>

        {/* Mobile View: Vertical List */}
        <div className="md:hidden space-y-4 relative">
          <div className="absolute left-[19px] top-2 bottom-2 w-px bg-brand-divider/40" />
          {PIPELINE.map((step, _i) => (
            <div key={step.title} className="flex gap-4 relative z-10">
              <div className="w-10 h-10 rounded-full bg-brand-surface border border-brand-divider flex items-center justify-center shrink-0 shadow-sm">
                <step.icon size={18} className="text-brand-primary" />
              </div>
              <div className="flex-1 pt-0.5 pb-2 border-b border-brand-divider/20 last:border-0">
                <p className="text-[11px] font-bold text-brand-primary uppercase tracking-widest mb-1">
                  {step.title}
                </p>
                <div className="text-[12px] leading-relaxed text-brand-light">{step.desc}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Desktop View: Horizontal Steps */}
        <div className="hidden md:block overflow-x-auto -mx-2 px-2 pb-2">
          <div className="flex gap-2 items-start min-w-max">
            {PIPELINE.map((step, i) => (
              <React.Fragment key={step.title}>
                <div className="flex flex-col items-center text-center w-40">
                  <div className="w-12 h-12 rounded-xl bg-brand-primary/5 border border-brand-primary/20 flex items-center justify-center mb-3 shadow-glow-primary/5">
                    <step.icon size={20} className="text-brand-primary" />
                  </div>
                  <p className="text-xs font-bold text-brand-light mb-1.5 uppercase tracking-wide">
                    {step.title}
                  </p>
                  <div className="text-[11px] text-brand-light/70 leading-relaxed px-1">
                    {step.desc}
                  </div>
                </div>
                {i < PIPELINE.length - 1 && (
                  <div className="pt-5 px-1">
                    <ArrowRight size={16} className="text-brand-divider animate-pulse" />
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </PageSection>

      {/* Manual Screener */}
      <PageSection className="card p-5 sm:p-6">
        <h2 className="heading-2 mb-6">
          <Search size={20} className="text-brand-accent" />
          Manual Screen
        </h2>

        <div className="flex flex-col sm:flex-row gap-3 mb-8">
          <div className="flex-1" ref={wrapperRef}>
            <div className="relative">
              <Input
                ref={inputRef}
                type="text"
                className="w-full h-11 sm:h-10 font-mono text-sm border-brand-divider/60 focus:border-brand-primary transition-all shadow-sm"
                placeholder="AAPL, 7203.T, Samsung..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') screen()
                  if (e.key === 'Escape') setShowSuggestions(false)
                }}
                onFocus={() => {
                  if (suggestions.length > 0 && inputRef.current) {
                    const r = inputRef.current.getBoundingClientRect()
                    setDropdownRect({
                      top: r.bottom + window.scrollY + 4,
                      left: r.left + window.scrollX,
                      width: r.width,
                    })
                    setShowSuggestions(true)
                  }
                }}
                autoComplete="off"
              />
              {showSuggestions &&
                dropdownRect &&
                createPortal(
                  <ul
                    style={{
                      position: 'absolute',
                      top: dropdownRect.top,
                      left: dropdownRect.left,
                      width: dropdownRect.width,
                      zIndex: 9999,
                    }}
                    className="rounded-xl border border-brand-divider bg-brand-surface shadow-2xl overflow-hidden backdrop-blur-xl"
                  >
                    {suggestions.map((s) => (
                      <li
                        key={s.symbol}
                        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-brand-primary/10 group transition-colors border-b border-brand-divider/40 last:border-0"
                        onMouseDown={() => pickSuggestion(s)}
                      >
                        <div className="flex flex-col">
                          <span className="font-mono font-bold text-brand-light group-hover:text-brand-primary transition-colors">
                            {s.symbol}
                          </span>
                          <span className="text-[11px] text-brand-light/70 truncate max-w-[180px] sm:max-w-none">
                            {s.company_name}
                          </span>
                        </div>
                        <span className="text-[10px] font-bold text-brand-light/70 uppercase tracking-tighter opacity-60 ml-2">
                          {s.exchange} · {s.type}
                        </span>
                      </li>
                    ))}
                  </ul>,
                  document.body,
                )}
            </div>
            <p className="text-[10px] sm:text-xs text-brand-light/70 mt-2 leading-relaxed italic opacity-80">
              Suffixes: Tokyo <code className="text-brand-primary">.T</code> · HK{' '}
              <code className="text-brand-primary">.HK</code> · China-SH{' '}
              <code className="text-brand-primary">.SS</code> · China-SZ{' '}
              <code className="text-brand-primary">.SZ</code> · Korea{' '}
              <code className="text-brand-primary">.KS</code> · Taiwan{' '}
              <code className="text-brand-primary">.TW</code> · India-NSE{' '}
              <code className="text-brand-primary">.NS</code> · Singapore{' '}
              <code className="text-brand-primary">.SI</code> · Australia{' '}
              <code className="text-brand-primary">.AX</code> · Canada{' '}
              <code className="text-brand-primary">.TO</code> · Helsinki{' '}
              <code className="text-brand-primary">.HE</code> · Stockholm{' '}
              <code className="text-brand-primary">.ST</code> · Frankfurt{' '}
              <code className="text-brand-primary">.F</code> · Paris{' '}
              <code className="text-brand-primary">.PA</code> · Istanbul{' '}
              <code className="text-brand-primary">.IS</code> · Saudi{' '}
              <code className="text-brand-primary">.SR</code> · Israel{' '}
              <code className="text-brand-primary">.TA</code> · Brazil{' '}
              <code className="text-brand-primary">.SA</code> · S.Africa{' '}
              <code className="text-brand-primary">.JO</code>
              {' '}· Or prefix: <code className="text-brand-primary">HEL:NOKIA</code>{' '}
              <code className="text-brand-primary">SSE:600519</code>{' '}
              <code className="text-brand-primary">ASX:BHP</code>
            </p>
          </div>
          <Button
            onClick={() => screen()}
            disabled={loading || !query.trim()}
            className="h-11 sm:h-10 px-6 font-bold uppercase tracking-widest shadow-glow-primary active:scale-[0.98] transition-all"
          >
            {loading ? <Loader size={16} className="animate-spin" /> : <Search size={16} />}
            {loading ? 'Screening...' : 'Screen'}
          </Button>
        </div>

        {error && <p className="text-brand-danger text-sm mb-4">{error}</p>}

        {result && (
          <div className="space-y-6">
            {/* Header */}
            <div
              className={`flex flex-col sm:flex-row items-center justify-between gap-6 p-6 rounded-2xl border transition-all ${
                result.verdict === 'COMPLIANT'
                  ? 'border-brand-success/30 bg-brand-success/5 shadow-glow-success/5'
                  : result.verdict === 'UNKNOWN'
                    ? 'border-brand-divider bg-brand-elevated/40'
                    : result.verdict === 'DOUBTFUL'
                      ? 'border-brand-warning/30 bg-brand-warning/5 shadow-glow-warning/5'
                      : 'border-brand-danger/30 bg-brand-danger/5 shadow-glow-danger/5'
              }`}
            >
              <div className="flex flex-col items-center sm:items-start text-center sm:text-left space-y-3">
                <div className="flex flex-col sm:flex-row items-center sm:items-baseline gap-2">
                  <p className="text-3xl font-black text-brand-light font-mono tracking-tighter">
                    {result.symbol}
                  </p>
                  {result.company_name && (
                    <p className="text-sm font-bold text-brand-light/70 tracking-tight">
                      {result.company_name}
                    </p>
                  )}
                </div>
                <p className="text-xs font-bold text-brand-light/70 opacity-80 uppercase tracking-widest">
                  {result.sector} · <span className="font-mono">{result.exchange ?? '—'}</span>
                </p>
                {result.sources_detail?.length > 0 && (
                  <SourceBadges sources={result.sources_detail} />
                )}
              </div>

              <div className="flex flex-col items-center gap-2">
                {result.verdict === 'COMPLIANT' ? (
                  <div className="flex flex-col items-center animate-in zoom-in-95 duration-500">
                    <ShieldCheck
                      size={48}
                      className="text-brand-success mb-2 drop-shadow-glow-success"
                    />
                    <span className="text-xs font-black text-brand-success tracking-[0.2em] uppercase">
                      HALAL CERTIFIED
                    </span>
                  </div>
                ) : result.verdict === 'UNKNOWN' ? (
                  <div className="flex flex-col items-center">
                    <ShieldQuestion size={48} className="text-brand-light/70 mb-2 opacity-50" />
                    <span className="text-xs font-black text-brand-light/70 tracking-[0.2em] uppercase">
                      UNVERIFIABLE
                    </span>
                  </div>
                ) : result.verdict === 'DOUBTFUL' ? (
                  <div className="flex flex-col items-center">
                    <ShieldAlert size={48} className="text-brand-warning mb-2 animate-pulse" />
                    <span className="text-xs font-black text-brand-warning tracking-[0.2em] uppercase">
                      DOUBTFUL
                    </span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center">
                    <ShieldAlert size={48} className="text-brand-danger mb-2" />
                    <span className="text-xs font-black text-brand-danger tracking-[0.2em] uppercase">
                      NON-COMPLIANT
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Ratio checks */}
            <InfoRow className=" mb-1">
              <TextTip text="Financial ratios derived from AAOIFI Shariah Standards. A company must pass all three to be considered compliant.">
                <h3 className="text-xs font-bold uppercase tracking-widest text-brand-light/70">
                  Ratio Analysis
                </h3>
              </TextTip>
            </InfoRow>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Check
                pass={debtPass}
                label="Debt / Mkt Cap"
                value={pct(result.debt_to_mkt_cap)}
                limit="33%"
              />
              <Check
                pass={cashPass}
                label="Cash / Mkt Cap"
                value={pct(result.cash_to_mkt_cap)}
                limit="33%"
              />
              <Check
                pass={impurePass}
                label="Impure Revenue"
                value={pct(result.impure_revenue_pct)}
                limit="5%"
              />
            </div>

            {/* Sector */}
            <div
              className={`flex items-center gap-3 p-4 rounded-xl border text-[11px] font-bold uppercase tracking-widest transition-all ${
                result.reason?.includes('sector')
                  ? 'border-brand-danger/20 bg-brand-danger/5 text-brand-danger'
                  : 'border-brand-success/20 bg-brand-success/5 text-brand-success'
              }`}
            >
              {result.reason?.includes('sector') ? (
                <XCircle size={16} />
              ) : (
                <CheckCircle2 size={16} />
              )}
              <span>
                Sector: <strong className="opacity-100">{result.sector}</strong>
              </span>
            </div>

            {/* Fail reason */}
            {result.reason && (
              <div className="flex gap-3 p-4 bg-brand-danger/10 border border-brand-danger/20 rounded-xl text-xs text-brand-danger">
                <ShieldAlert size={16} className="shrink-0 mt-0.5" />
                <span className="font-medium leading-relaxed">{result.reason}</span>
              </div>
            )}
          </div>
        )}
      </PageSection>
    </Page>
  )
}

import { ErrorBoundary } from '../../components/ErrorBoundary'

export default function ScreeningPageWithBoundary() {
  return (
    <ErrorBoundary title="Screening unavailable">
      <ScreeningPage />
    </ErrorBoundary>
  )
}
