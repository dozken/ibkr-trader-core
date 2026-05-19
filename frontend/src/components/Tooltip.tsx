import { HelpCircle } from 'lucide-react'
import React, { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/utils'

interface TooltipProps {
  text: string
  children: React.ReactNode
  width?: string
  position?: 'top' | 'bottom'
}

export const Tooltip: React.FC<TooltipProps> = ({
  text,
  children,
  width = 'w-52',
  position = 'top',
}) => {
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState({ top: 0, left: 0, width: 0 })
  const triggerRef = useRef<HTMLSpanElement>(null)

  const updateCoords = React.useCallback(() => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      setCoords({
        top: rect.top + window.scrollY,
        left: rect.left + window.scrollX,
        width: rect.width,
      })
    }
  }, [])

  const handleMouseEnter = () => {
    updateCoords()
    setOpen(true)
  }

  React.useLayoutEffect(() => {
    if (open) {
      window.addEventListener('scroll', updateCoords)
      window.addEventListener('resize', updateCoords)
    }
    return () => {
      window.removeEventListener('scroll', updateCoords)
      window.removeEventListener('resize', updateCoords)
    }
  }, [open, updateCoords])

  return (
    <span
      ref={triggerRef}
      className="relative inline-flex items-center"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setOpen(false)}
    >
      {children}
      {open &&
        coords.top !== 0 &&
        createPortal(
          <div
            style={{
              position: 'absolute',
              top: position === 'top' ? coords.top : coords.top + 24,
              left: coords.left + coords.width / 2,
              transform: position === 'top' ? 'translate(-50%, -100%)' : 'translate(-50%, 0)',
              zIndex: 9999,
            }}
            className={cn(
              'pointer-events-none p-2 animate-in fade-in zoom-in-95 duration-100',
              position === 'top' ? 'mb-2' : 'mt-2',
            )}
          >
            <div
              className={cn(
                'px-2.5 py-2 text-xs leading-relaxed shadow-2xl',
                'text-brand-light bg-brand-surface border border-brand-divider rounded-lg',
                'whitespace-normal text-left',
                width,
              )}
            >
              {text}
            </div>
          </div>,
          document.body,
        )}
    </span>
  )
}

export const InfoTip: React.FC<{ text: string; position?: 'top' | 'bottom'; width?: string }> = ({
  text,
  position = 'top',
  width,
}) => (
  <Tooltip text={text} position={position} width={width}>
    <HelpCircle
      size={14}
      className="ml-1 text-brand-light/70 cursor-help opacity-50 hover:opacity-100 transition-opacity shrink-0"
    />
  </Tooltip>
)

export const TextTip: React.FC<{
  text: string
  children: React.ReactNode
  position?: 'top' | 'bottom'
  width?: string
}> = ({ text, children, position = 'top', width }) => (
  <Tooltip text={text} position={position} width={width}>
    <span className="border-b border-dotted border-brand-light/50 cursor-help pb-px">
      {children}
    </span>
  </Tooltip>
)

// ── Abbreviation dictionary ───────────────────────────────────────────────────

export const ABBR: Record<string, string> = {
  // Organisations & indices
  AAOIFI:
    'Accounting and Auditing Organisation for Islamic Financial Institutions — the international standard-setter for Islamic finance, founded in Bahrain (1990). Over 60 countries adopt its standards.',
  DJIM: 'Dow Jones Islamic Market Index — one of the most widely used Shariah equity screening methodologies. Its 33%/5% ratio thresholds are the industry default.',
  OIC: 'Organisation of Islamic Cooperation — intergovernmental body of 57 Muslim-majority states. Its Fiqh Academy issues rulings on Islamic jurisprudence.',
  MSCI: 'Morgan Stanley Capital International — publishes the MSCI Islamic Index, an alternative Shariah equity screening methodology using similar ratio thresholds.',

  // Brokerage / app
  IBKR: 'Interactive Brokers — the brokerage platform this app connects to for executing and managing trades.',
  TWS: "Trader Workstation — Interactive Brokers' desktop trading platform (default port 7497 for paper trading, 7496 for live).",
  API: 'Application Programming Interface — a protocol that lets two software systems communicate. Used here for IBKR order submission and market data.',

  // Financial mechanics
  'P&L':
    'Profit and Loss — the gain or loss on a position. Unrealized P&L = paper gain/loss on open positions. Realized P&L = locked-in gain/loss after closing.',
  PnL: 'Profit and Loss — gain or loss on a position. Unrealized = open, Realized = closed.',
  ETF: 'Exchange-Traded Fund — a basket of securities (stocks, bonds, etc.) that trades on an exchange like a single stock. Must be Shariah-certified to be halal.',
  'T+2':
    'Trade date + 2 business days — the standard settlement cycle for equities. Legal ownership transfers at settlement, not at execution.',
  RSI: 'Relative Strength Index — momentum oscillator (0–100). Above 70 = potentially overbought. Below 30 = potentially oversold. Used as a signal filter.',
  SMA: 'Simple Moving Average — average closing price over N days. Price above SMA = recent uptrend. Used alongside news sentiment for buy/sell signals.',
  SMA20:
    'Simple Moving Average (20 days) — average closing price over the last 20 trading days. A common short-term trend indicator.',
  EMA: 'Exponential Moving Average — like SMA but gives more weight to recent prices, reacting faster to price changes.',
  NAV: "Net Asset Value — total value of a fund's assets minus liabilities, divided by shares outstanding. The per-share value of a fund.",

  // Shariah compliance terms
  SS: "Shariah Standard — formal ruling issued by AAOIFI's Shariah Supervisory Board. E.g. SS No. 21 covers equity screening.",
  riba: 'Riba (ربا) — interest or usury. Categorically forbidden in Islam (Quran 2:275–279). Covers any guaranteed fixed return on money itself, regardless of amount.',
  gharar:
    'Gharar (غرر) — excessive uncertainty or ambiguity in a contract. Forbidden when it leads to dispute or injustice (e.g. conventional insurance, short selling).',
  musharakah:
    'Musharakah (مشاركة) — partnership contract where all parties share profit and loss proportionally. The basis for permissible equity ownership.',
  murabaha:
    'Murabaha (مرابحة) — cost-plus sale. Seller discloses exact cost and adds an agreed profit margin. Used in Islamic mortgages and vehicle finance.',
  ijara:
    'Ijara (إجارة) — Islamic lease. The bank buys and leases the asset to the customer; ownership stays with the bank. Permissible alternative to conventional loans.',
  sukuk:
    'Sukuk (صكوك) — Islamic bonds. Represent ownership in an underlying asset rather than a debt obligation. No interest payments — returns come from asset performance.',
  takaful:
    'Takaful (تكافل) — Islamic insurance based on mutual contribution and shared risk. Permissible alternative to conventional insurance (which contains gharar and riba).',
  hawl: 'Hawl (حول) — one complete lunar year (~354 days). Zakat is only due on wealth that has been held continuously for one hawl above the nisab threshold.',
  nisab:
    'Nisab (نصاب) — minimum wealth threshold below which Zakat is not due. Equals value of 85g gold or 595g silver (use the lower — silver nisab is more inclusive).',
  tazkiyah:
    'Tazkiyah / Purification (تزكية) — donating the proportional share of impure income earned from marginally non-compliant sources to charity. Obligatory, not optional.',
  qabd: 'Qabd (قبض) — possession. Shariah requires actual (haqiqi) or constructive (hukmi) possession before re-selling an asset — the basis for T+2 settlement strictness.',
  Qabd: 'Qabd (قبض) — possession. Shariah requires actual or constructive possession before re-selling an asset. See T+2 settlement strictness setting.',
}

/**
 * Renders an abbreviation with a dotted underline and tooltip on hover.
 * Looks up the term in ABBR dictionary. Falls back to plain <span> if not found.
 *
 * Usage: <Abbr>AAOIFI</Abbr>  or  <Abbr term="riba">riba</Abbr>
 */
export const Abbr: React.FC<{
  children: React.ReactNode
  term?: string
  position?: 'top' | 'bottom'
}> = ({ children, term, position = 'top' }) => {
  const key = term ?? (typeof children === 'string' ? children : '')
  const def = ABBR[key] ?? ABBR[key.toLowerCase()]
  if (!def) return <span>{children}</span>
  return (
    <Tooltip text={def} width="w-80" position={position}>
      <span className="border-b border-dotted border-current cursor-help pb-px">{children}</span>
    </Tooltip>
  )
}
