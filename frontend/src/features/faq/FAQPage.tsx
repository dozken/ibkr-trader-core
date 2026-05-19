import { Page, PageHeader, PageSection, CardGrid, ActionRow, InfoRow, Stack } from '@/components/ui/layout'
import {
  Ban,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Coins,
  ExternalLink,
  FileText,
  Heart,
  type LucideIcon,
  Scale,
  Search,
  ShieldAlert,
  ShieldCheck,
  Zap,
} from 'lucide-react'
import type React from 'react'
import { useState } from 'react'
import { Abbr } from '../../components/Tooltip'

interface FAQItem {
  q: string
  a: React.ReactNode
}

interface Section {
  title: React.ReactNode
  titleKey: string
  Icon: LucideIcon
  color: string
  items: FAQItem[]
}

const Ref: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="text-[11px] font-mono text-brand-primary/80 bg-brand-primary/10 px-1.5 py-0.5 rounded border border-brand-primary/20 ml-1">
    {children}
  </span>
)

const DocLink: React.FC<{ href: string; children: React.ReactNode }> = ({ href, children }) => (
  <a
    href={href}
    target="_blank"
    rel="noopener noreferrer"
    className="inline-flex items-center gap-1 text-brand-primary hover:underline text-xs"
  >
    {children}
    <ExternalLink size={10} />
  </a>
)

const SECTIONS: Section[] = [
  {
    titleKey: 'basics',
    title: 'Basics of Shariah-Compliant Investing',
    Icon: BookOpen,
    color: 'text-brand-primary',
    items: [
      {
        q: 'Is investing in stocks allowed in Islam?',
        a: (
          <div className="space-y-2">
            <p>
              Yes — buying shares in a company is permissible. A share represents part-ownership of
              a real business and its assets. The <Abbr>OIC</Abbr> Fiqh Academy
              <Ref>OIC Res. 63/1/7 (1992)</Ref> and <Abbr>AAOIFI</Abbr>
              <Ref>
                <Abbr>SS</Abbr> No. 21
              </Ref>{' '}
              both confirm that equity ownership is halal in principle, provided the company's
              primary business is lawful.
            </p>
            <p>
              Think of it like being a silent partner in a business. You profit when the business
              profits and share losses too — this is called{' '}
              <Abbr term="musharakah">
                <em>musharakah</em>
              </Abbr>{' '}
              (partnership), which Islam explicitly encourages.
            </p>
          </div>
        ),
      },
      {
        q: 'What makes a stock haram?',
        a: (
          <div className="space-y-2">
            <p>Three categories make a stock impermissible:</p>
            <ol className="list-decimal ml-5 space-y-2 text-sm">
              <li>
                <strong>Prohibited primary business</strong> — the company's core activity is haram:
                alcohol, tobacco, gambling, adult content, conventional banking/insurance, pork
                products, weapons manufacturing.
                <Ref>
                  <Abbr>AAOIFI</Abbr> <Abbr>SS</Abbr> No. 21 §3
                </Ref>
              </li>
              <li>
                <strong>
                  Excessive debt (<Abbr term="riba">riba</Abbr>)
                </strong>{' '}
                — the company borrows so heavily that its interest-bearing debt exceeds 33% of
                market capitalisation. You'd be part-owner of a business built on interest.
                <Ref>
                  <Abbr>AAOIFI</Abbr> <Abbr>SS</Abbr> No. 21 §6
                </Ref>
              </li>
              <li>
                <strong>Excessive prohibited income</strong> — even otherwise halal businesses earn
                some impure income (bank interest on cash holdings, etc.). When this exceeds 5% of
                revenue it becomes a disqualifier.
                <Ref>
                  <Abbr>DJIM</Abbr> Methodology §4.2
                </Ref>
              </li>
            </ol>
          </div>
        ),
      },
      {
        q: 'What is riba and why is it forbidden?',
        a: (
          <div className="space-y-2">
            <p>
              <strong>
                <Abbr term="riba">Riba</Abbr>
              </strong>{' '}
              literally means "increase" or "excess." In finance it refers to any guaranteed, fixed
              return on money itself — i.e., interest. The Quran prohibits it directly in four
              places (2:275–279, 3:130, 4:161, 30:39).
            </p>
            <p>
              The core reason: money is a medium of exchange, not a productive asset. Charging
              guaranteed rent on money disconnects reward from real economic activity and transfers
              risk entirely onto the borrower. Islam requires that profit and loss be shared.
            </p>
            <p className="text-xs text-brand-light/70">
              This is why this app enforces: no margin trading, no shorting, no leveraged{' '}
              <Abbr>ETF</Abbr>s, and debt-ratio checks on every stock.
            </p>
          </div>
        ),
      },
    ],
  },
  {
    titleKey: 'ratios',
    title: (
      <>
        The <Abbr>AAOIFI</Abbr> Screening Ratios
      </>
    ),
    Icon: Scale,
    color: 'text-brand-warning',
    items: [
      {
        q: 'What is AAOIFI and why do we follow their standards?',
        a: (
          <div className="space-y-2">
            <p>
              <Abbr>AAOIFI</Abbr> (Accounting and Auditing Organisation for Islamic Financial
              Institutions) is the international standard-setter for Islamic finance, founded in
              Bahrain in 1990. Over 60 countries adopt their standards. Their Shariah Supervisory
              Board includes senior scholars from across the Muslim world.
            </p>
            <p>
              Their Shariah Standard No. 21 ("Financial Papers: Shares and Bonds") is the most
              widely adopted framework for equity screening. This app implements it faithfully.
            </p>
            <p>
              <DocLink href="https://aaoifi.com/shariaa-standards/?lang=en">
                AAOIFI Shariah Standards (official)
              </DocLink>
            </p>
          </div>
        ),
      },
      {
        q: 'Explain the three ratio tests in plain English',
        a: (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-brand-warning/30 bg-brand-warning/5 space-y-1">
              <p className="font-semibold text-brand-warning text-sm">
                ① Debt / Market Cap &lt; 33%
              </p>
              <p className="text-sm">
                If a company has taken on a lot of interest-bearing loans, owning its shares makes
                you a part-owner of that debt burden. <Abbr>AAOIFI</Abbr> limits this to one-third
                of the company's market value. A company worth $10B should have no more than $3.3B
                in interest-bearing debt.
              </p>
              <p className="text-xs text-brand-light/70">
                The "one-third" rule traces back to a hadith: "One-third is much" (Bukhari/Muslim,
                the will of Sa'd ibn Abi Waqqas) — used by scholars as a tolerance threshold.
              </p>
            </div>
            <div className="p-3 rounded-lg border border-brand-warning/30 bg-brand-warning/5 space-y-1">
              <p className="font-semibold text-brand-warning text-sm">
                ② Cash &amp; Receivables / Market Cap &lt; 33%
              </p>
              <p className="text-sm">
                If a company's assets are mostly cash or financial receivables, buying the stock is
                essentially buying money — which must be done at face value under Shariah (the rules
                of
                <em> sarf</em>). If cash dominates, you risk paying more than face value for it,
                which is forbidden. <Abbr>AAOIFI</Abbr> caps this at 33%.
              </p>
            </div>
            <div className="p-3 rounded-lg border border-brand-warning/30 bg-brand-warning/5 space-y-1">
              <p className="font-semibold text-brand-warning text-sm">
                ③ Impure Revenue / Total Revenue &lt; 5%
              </p>
              <p className="text-sm">
                Almost every large company earns a small amount of interest on its bank deposits or
                has minor non-compliant income streams. Below 5%, scholars consider this a
                negligible contamination — you still invest but must purify your proportional share
                of those gains. Above 5%, the contamination is too large to tolerate.
              </p>
              <p className="text-xs text-brand-light/70">
                The 5% threshold is from <Abbr>DJIM</Abbr> methodology and is accepted by most
                contemporary scholars including Mufti Taqi Usmani.
                <Ref>
                  <Abbr>DJIM</Abbr> §4.2
                </Ref>
              </p>
            </div>
          </div>
        ),
      },
      {
        q: 'Why market cap and not total assets?',
        a: (
          <p>
            Using market capitalisation (share price × shares outstanding) rather than total assets
            reflects the actual economic ownership stake. A company with $1B in book assets but
            trading at $10B has its balance sheet ratios diluted by investor confidence in future
            earnings. <Abbr>AAOIFI</Abbr> chose market cap because it better represents the real
            price you're paying for those liabilities. Some scholars (e.g. the Fiqh Council of North
            America) use total assets — this app follows the more widely adopted <Abbr>AAOIFI</Abbr>
            /<Abbr>DJIM</Abbr> market-cap approach.
            <Ref>
              <Abbr>AAOIFI</Abbr> <Abbr>SS</Abbr> No. 21 §6.1
            </Ref>
          </p>
        ),
      },
    ],
  },
  {
    titleKey: 'sectors',
    title: 'Prohibited Sectors',
    Icon: Ban,
    color: 'text-brand-danger',
    items: [
      {
        q: 'Which sectors are always excluded?',
        a: (
          <div className="space-y-2">
            <p>These sectors are categorically prohibited regardless of financial ratios:</p>
            <div className="grid grid-cols-2 gap-2 text-sm">
              {[
                ['Conventional Finance', 'Banks, insurance companies earning from interest'],
                ['Alcohol', 'Production, distribution, retail'],
                ['Tobacco', 'Manufacturing and distribution'],
                ['Gambling', 'Casinos, betting platforms, lotteries'],
                ['Adult Content', 'Pornography, escort services'],
                ['Pork', 'Production, processing, retail of pork products'],
                ['Defense / Weapons', 'Offensive weapons manufacturing'],
                ['Recreational Cannabis', 'Where primary use is recreational'],
              ].map(([sector, desc]) => (
                <div
                  key={sector}
                  className="p-2 rounded border border-brand-danger/20 bg-brand-danger/5"
                >
                  <p className="font-semibold text-brand-danger text-xs">{sector}</p>
                  <p className="text-brand-light/70 text-xs mt-0.5">{desc}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-brand-light/70">
              You can add custom sectors to exclude in Settings → Shariah Compliance → Excluded
              Sectors.
            </p>
          </div>
        ),
      },
      {
        q: 'What about conventional banks — can I invest in any financial company?',
        a: (
          <div className="space-y-2">
            <p>
              Conventional banks are excluded because their core business model is{' '}
              <Abbr term="riba">riba</Abbr> — they borrow money at low interest and lend at high
              interest. Owning shares makes you a direct beneficiary of that interest income.
            </p>
            <p>
              However, <strong>Islamic banks</strong> operating under Shariah-compliant structures (
              <Abbr term="murabaha">murabaha</Abbr>, <Abbr term="ijara">ijara</Abbr>,{' '}
              <Abbr term="sukuk">sukuk</Abbr>) are generally permissible. The screening ratios would
              still apply. Insurance companies are excluded due to{' '}
              <Abbr term="gharar">
                <em>gharar</em>
              </Abbr>{' '}
              (excessive uncertainty) and <Abbr term="riba">riba</Abbr> in their investment
              portfolios, unless they operate as <Abbr term="takaful">takaful</Abbr> (Islamic mutual
              insurance).
            </p>
          </div>
        ),
      },
    ],
  },
  {
    titleKey: 'purification',
    title: 'Purification (Tazkiyah)',
    Icon: Heart,
    color: 'text-brand-danger',
    items: [
      {
        q: 'What is purification (tazkiyah) and do I have to do it?',
        a: (
          <div className="space-y-2">
            <p>
              When you own a stock that earns a small amount of impure income (below the 5%
              threshold), you've indirectly benefited from a prohibited source.{' '}
              <Abbr term="tazkiyah">Purification</Abbr> means donating the equivalent amount to
              charity to "cleanse" your portfolio returns.
            </p>
            <p>
              The formula:{' '}
              <code className="bg-brand-base px-1 rounded text-xs">
                Donation = (Your gains × Impure Revenue %)
              </code>
            </p>
            <p>
              For example: you earned $1,000 profit from a stock where 2% of revenue is impure. You
              donate $20 to charity. The $20 is not counted as a good deed (sadaqah) — it's simply
              removing something that doesn't belong to you.
            </p>
            <p className="text-xs text-brand-light/70">
              This is the position of Mufti Taqi Usmani, Sheikh Nizam Yaquby, and the{' '}
              <Abbr>AAOIFI</Abbr> Shariah Board. It is <strong>obligatory</strong>, not optional,
              when holding stocks with any impure income.
              <Ref>Usmani, "Introduction to Islamic Finance" Ch. 5</Ref>
            </p>
          </div>
        ),
      },
      {
        q: 'What if a stock I own becomes non-compliant?',
        a: (
          <div className="space-y-2">
            <p>
              If a stock crosses a ratio threshold (usually after a quarterly earnings report), you
              must <strong>intend to sell</strong> and exit within a reasonable period.
            </p>
            <ul className="list-disc ml-5 space-y-1 text-sm">
              <li>
                <strong>Grace period:</strong> Most scholars allow up to 3 months to sell without
                sinning, provided you intend to sell and do not buy more.
                <Ref>
                  <Abbr>AAOIFI</Abbr> <Abbr>SS</Abbr> No. 21 §5(e)
                </Ref>
              </li>
              <li>
                <strong>Your principal is safe:</strong> You keep 100% of your original investment.
                Only the proportional gains earned during the non-compliant period need{' '}
                <Abbr term="tazkiyah">purification</Abbr>.
              </li>
              <li>
                <strong>In this app:</strong> Enable "Kill-Switch" in Settings → Alerts &amp; Safety
                to auto-liquidate immediately. Or leave it off, get alerted, and sell manually.
                Either way, the Purification Owed widget shows what to donate.
              </li>
            </ul>
          </div>
        ),
      },
    ],
  },
  {
    titleKey: 'zakat',
    title: 'Zakat on Investments',
    Icon: Coins,
    color: 'text-brand-warning',
    items: [
      {
        q: 'Do I pay Zakat on stocks?',
        a: (
          <div className="space-y-2">
            <p>
              Yes, if your total zakatable wealth exceeds the <Abbr term="nisab">nisab</Abbr>{' '}
              (minimum threshold, approx. 85g of gold or 595g of silver — check current prices) and
              has been held for one lunar year (<Abbr term="hawl">hawl</Abbr>).
            </p>
            <p>
              The Zakat rate is <strong>2.5%</strong> of zakatable assets.
              <Ref>Fiqh Council NA, Res. 2001</Ref>
            </p>
            <p>For stocks, scholars differ on the base:</p>
            <ol className="list-decimal ml-5 space-y-1 text-sm">
              <li>
                <strong>Market value method (recommended for passive investors):</strong> Pay 2.5%
                of total portfolio market value at your Zakat anniversary date. Simple and
                conservative.
              </li>
              <li>
                <strong>Zakatable assets method:</strong> Calculate the underlying zakatable assets
                (cash + receivables + inventory) per share and pay 2.5% of that. Requires the
                company's balance sheet data.
              </li>
            </ol>
            <p className="text-xs text-brand-light/70 mt-1">
              This app uses market value method for the Zakat estimate (conservative and widely
              accepted). The Zakat page lets you record payment and track what's due.
            </p>
          </div>
        ),
      },
      {
        q: 'What is nisab?',
        a: (
          <p>
            <Abbr term="nisab">Nisab</Abbr> is the minimum threshold of wealth below which Zakat is
            not due. It equals the value of 85g of gold or 595g of silver (use the lower of the two
            for precaution — this is the silver-<Abbr term="nisab">nisab</Abbr> position, which is
            more inclusive). At current prices (~2026), this is approximately $5,000–8,000 USD. If
            your total wealth including investments exceeds this and has been held for a lunar year
            (<Abbr term="hawl">hawl</Abbr>), Zakat is due on the full amount at 2.5%.
          </p>
        ),
      },
    ],
  },
  {
    titleKey: 'howworks',
    title: 'How This App Works',
    Icon: Zap,
    color: 'text-brand-success',
    items: [
      {
        q: 'What happens before every trade?',
        a: (
          <div className="space-y-3">
            <p>
              Every BUY order passes this pipeline before any order reaches <Abbr>IBKR</Abbr>:
            </p>
            <ol className="space-y-2 text-sm">
              <li className="flex gap-3">
                <span className="font-bold text-brand-primary w-28 shrink-0">1. AI Signal</span>
                <span className="text-brand-light/70">
                  News sentiment analysis (Alpha Vantage / yfinance). Score must pass minimum
                  confidence threshold.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="font-bold text-brand-primary w-28 shrink-0">2. Sector Check</span>
                <span className="text-brand-light/70">
                  Company sector matched against prohibited list. Any match → rejected immediately.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="font-bold text-brand-primary w-28 shrink-0">
                  3. <Abbr>AAOIFI</Abbr> Ratios
                </span>
                <span className="text-brand-light/70">
                  Debt/MktCap, Cash/MktCap, Impure Revenue checked live via Yahoo Finance (+
                  Zoya/Musaffa <Abbr>API</Abbr>s if configured). All three must pass.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="font-bold text-brand-primary w-28 shrink-0">4. Cash Guard</span>
                <span className="text-brand-light/70">
                  Total order cost must not exceed available <Abbr>IBKR</Abbr> balance. No margin,
                  no leverage, ever.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="font-bold text-brand-primary w-28 shrink-0">5. Market Hours</span>
                <span className="text-brand-light/70">
                  Exchange-aware check. Tokyo, Hong Kong, Gulf, US all have different hours. Closed
                  = skip, not queue.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="font-bold text-brand-primary w-28 shrink-0">6. Execute</span>
                <span className="text-brand-light/70">
                  Market order via <Abbr>IBKR</Abbr>. Fill price, commission, order ID logged to
                  append-only audit trail.
                </span>
              </li>
            </ol>
          </div>
        ),
      },
      {
        q: 'How does the automatic compliance monitoring work?',
        a: (
          <div className="space-y-2">
            <p>
              Company financials change every quarter. A stock that was halal in January may cross a
              debt threshold after March earnings. The auto-monitor runs on your configured interval
              (default: daily) and:
            </p>
            <ol className="list-decimal ml-5 space-y-1 text-sm">
              <li>
                Fetches all open <Abbr>IBKR</Abbr> positions
              </li>
              <li>
                Re-runs full <Abbr>AAOIFI</Abbr> screening on each symbol
              </li>
              <li>Saves results to the database (full audit trail)</li>
              <li>If non-compliant: alerts via Telegram (if configured)</li>
              <li>If Kill-Switch enabled: auto-sells the position at market price</li>
            </ol>
            <p className="text-xs text-brand-light/70">
              Configure in Settings → Alerts &amp; Safety → Auto Compliance Monitor.
            </p>
          </div>
        ),
      },
      {
        q: 'What does "T+2 settlement strictness" mean?',
        a: (
          <div className="space-y-2">
            <p>
              When you buy a stock, you don't legally own it until settlement — typically 2 business
              days later (<Abbr>T+2</Abbr>). Some scholars require{' '}
              <Abbr term="qabd">
                <em>qabd al-haqiqi</em>
              </Abbr>{' '}
              (actual possession) before you can re-sell, meaning you must wait for settlement
              before selling.
            </p>
            <p>
              In this app,{' '}
              <strong>
                PHYSICAL_<Abbr>T+2</Abbr> (strict)
              </strong>{' '}
              mode locks a position for <Abbr>T+2</Abbr> days after purchase.{' '}
              <strong>CONSTRUCTIVE</strong> mode allows immediate re-sale, treating the broker
              confirmation as constructive possession — a lenient position held by some contemporary
              scholars.
            </p>
            <p className="text-xs text-brand-light/70">
              The stricter <Abbr>T+2</Abbr> position is held by Mufti Taqi Usmani and{' '}
              <Abbr>AAOIFI</Abbr>. The constructive position is accepted by many institutions for
              publicly listed equity.
              <Ref>Usmani, "Introduction to Islamic Finance" §3.8</Ref>
            </p>
          </div>
        ),
      },
      {
        q: 'Can I trust Yahoo Finance / Zoya data for screening?',
        a: (
          <div className="space-y-2">
            <p>The app uses a layered approach:</p>
            <ul className="list-disc ml-5 space-y-1 text-sm">
              <li>
                <strong>
                  Zoya / Musaffa <Abbr>API</Abbr>s
                </strong>{' '}
                (if <Abbr>API</Abbr> keys are set in .env) — dedicated Islamic finance screening
                services with scholar-reviewed methodologies. Most reliable.
              </li>
              <li>
                <strong>Yahoo Finance</strong> — free, global coverage, balance sheet data. Good for
                ratio screening but impure revenue classification is approximate.
              </li>
              <li>
                <strong>Financial Modeling Prep / Alpha Vantage</strong> — additional data sources
                when Yahoo data is unavailable.
              </li>
            </ul>
            <p>
              When data is over 90 days old (stale quarterly filing), the app warns you. When no
              data is available, the stock is blocked — "cannot verify" defaults to non-compliant.
            </p>
            <p className="text-xs text-brand-light/70">
              For large positions, cross-check against a dedicated service like Zoya, Musaffa, or
              Islamicly. The app automates the process but does not replace personal due diligence
              for significant investments.
            </p>
          </div>
        ),
      },
      {
        q: 'Is shorting or margin trading blocked?',
        a: (
          <div className="space-y-2">
            <p>
              <strong>Yes, both are structurally blocked:</strong>
            </p>
            <ul className="list-disc ml-5 space-y-1 text-sm">
              <li>
                <strong>Shorting</strong> is haram because you're selling something you don't own (
                <em>bay' al-ma'dum</em>) — forbidden by direct hadith (Abu Dawud, Tirmidhi).
              </li>
              <li>
                <strong>Margin trading</strong> involves borrowing from a broker at interest (
                <Abbr term="riba">riba</Abbr>) to buy stocks. The app only allows orders within your
                available <Abbr>IBKR</Abbr> cash balance.
              </li>
            </ul>
            <p className="text-xs text-brand-light/70">
              The cash guard runs before every order submission. If total order cost exceeds
              available funds, the order is rejected.
            </p>
          </div>
        ),
      },
    ],
  },
  {
    titleKey: 'refs',
    title: 'Key References',
    Icon: FileText,
    color: 'text-brand-light/70',
    items: [
      {
        q: 'Where can I learn more?',
        a: (
          <div className="space-y-3 text-sm">
            <div>
              <p className="font-semibold text-brand-light mb-2">Scholarly Works</p>
              <ul className="space-y-1.5 text-brand-light/70">
                <li>
                  Mufti Taqi Usmani — <em>An Introduction to Islamic Finance</em> (Kluwer Law, 2002)
                  — foundational text on Islamic finance principles
                </li>
                <li>
                  Dr. Monzer Kahf — <em>Fiqh of Zakat</em> — comprehensive modern treatment of Zakat
                </li>
                <li>
                  <Abbr>AAOIFI</Abbr> — <em>Shariah Standards</em> (2017 edition) — the industry
                  standard reference
                </li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-brand-light mb-2">Key Standards &amp; Rulings</p>
              <ul className="space-y-1.5 text-brand-light/70">
                <li>
                  <Ref>
                    <Abbr>AAOIFI</Abbr> <Abbr>SS</Abbr> No. 21
                  </Ref>{' '}
                  — Financial Papers: Shares and Bonds (equity screening)
                </li>
                <li>
                  <Ref>
                    <Abbr>AAOIFI</Abbr> <Abbr>SS</Abbr> No. 17
                  </Ref>{' '}
                  — Investment <Abbr term="sukuk">Sukuk</Abbr>
                </li>
                <li>
                  <Ref>
                    <Abbr>OIC</Abbr> Fiqh Academy Res. 63/1/7
                  </Ref>{' '}
                  — Permissibility of equity ownership (1992)
                </li>
                <li>
                  <Ref>
                    <Abbr>DJIM</Abbr> Methodology
                  </Ref>{' '}
                  — Dow Jones Islamic Market Index, widely adopted screening ratios
                </li>
                <li>
                  <Ref>
                    <Abbr>MSCI</Abbr> Islamic Index
                  </Ref>{' '}
                  — Alternative methodology with 33.33% thresholds
                </li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-brand-light mb-2">Online Resources</p>
              <ul className="space-y-1.5">
                <li>
                  <DocLink href="https://aaoifi.com">
                    <Abbr>AAOIFI</Abbr> Official Website
                  </DocLink>
                </li>
                <li>
                  <DocLink href="https://zoya.finance">Zoya — Islamic stock screener</DocLink>
                </li>
                <li>
                  <DocLink href="https://musaffa.com">Musaffa — Stock halal checker</DocLink>
                </li>
                <li>
                  <DocLink href="https://islamicfinance.com">
                    IslamicFinance.com — Educational resources
                  </DocLink>
                </li>
              </ul>
            </div>
          </div>
        ),
      },
    ],
  },
]

const FAQSection: React.FC<{ section: Section }> = ({ section }) => {
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  const { title, Icon, color, items } = section

  return (
    <div className="card">
      <h2 className={`heading-2 mb-5 ${color}`}>
        <Icon size={20} />
        {title}
      </h2>
      <div className="space-y-2">
        {items.map((item, i) => {
          const isOpen = openIdx === i
          return (
            <div
              key={i}
              className={`rounded-lg border transition-colors ${
                isOpen ? 'border-brand-primary/40 bg-brand-base' : 'border-brand-divider'
              }`}
            >
              <button
                type="button"
                className="w-full flex items-start justify-between gap-3 p-4 text-left"
                onClick={() => setOpenIdx(isOpen ? null : i)}
              >
                <span className="text-sm font-semibold text-brand-light">{item.q}</span>
                {isOpen ? (
                  <ChevronDown size={16} className="text-brand-primary shrink-0 mt-0.5" />
                ) : (
                  <ChevronRight size={16} className="text-brand-light/70 shrink-0 mt-0.5" />
                )}
              </button>
              {isOpen && (
                <div className="px-4 pb-4 text-sm text-brand-light/70 leading-relaxed">
                  {item.a}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const FAQPage = () => {
  const [search, setSearch] = useState('')

  const visibleSections = search.trim()
    ? SECTIONS.map(s => ({ ...s, items: s.items.filter(i =>
        i.q.toLowerCase().includes(search.toLowerCase()) ||
        (typeof s.title === 'string' && s.title.toLowerCase().includes(search.toLowerCase()))
      )})).filter(s => s.items.length > 0)
    : SECTIONS

  return (
  <Page>
    <PageHeader>
        <div>
          <h1 className="heading-1">
                  <BookOpen className="text-brand-primary" />
                  Shariah Compliance Guide
                </h1>
                <p className="text-brand-light/70">
                  Plain-language explanations with references to <Abbr>AAOIFI</Abbr> standards and scholarly
                  sources. Hover underlined terms for definitions.
                </p>
        </div>
      </PageHeader>

    <div className="relative mb-6 max-w-lg">
      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-light/50" />
      <input
        type="text"
        placeholder="Search the guide…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full pl-9 pr-4 py-2.5 bg-brand-elevated border border-brand-divider rounded-lg text-sm text-brand-light placeholder-brand-light/40 focus:outline-none focus:border-brand-primary/60"
      />
    </div>

    {/* Quick-reference card */}
    <PageSection className="card border-brand-primary/30 bg-brand-primary/5">
      <h2 className="heading-2 mb-4">
        <ShieldCheck className="text-brand-success" size={20} />
        Quick Reference — <Abbr>AAOIFI</Abbr> Thresholds
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
        {[
          {
            label: 'Debt / Market Cap',
            limit: '< 33%',
            detail: 'Interest-bearing liabilities',
            ref: 'SS No. 21 §6.1',
          },
          {
            label: 'Cash / Market Cap',
            limit: '< 33%',
            detail: 'Cash + interest-bearing receivables',
            ref: 'SS No. 21 §6.2',
          },
          {
            label: 'Impure Revenue',
            limit: '< 5%',
            detail: '% of total revenue from haram sources',
            ref: 'DJIM §4.2',
          },
        ].map(({ label, limit, detail, ref }) => (
          <div key={label} className="p-3 rounded-lg border border-brand-divider bg-brand-base">
            <p className="font-bold text-brand-light">{limit}</p>
            <p className="text-brand-light/70 font-medium text-xs mt-0.5">{label}</p>
            <p className="text-brand-light/70 text-xs mt-1">{detail}</p>
            <p className="text-brand-primary/70 text-[10px] font-mono mt-1">{ref}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        {(
          [
            ['No interest-bearing debt', 'riba'],
            ['No margin or leverage', null],
            ['No short selling', null],
            ['Prohibited sectors always blocked', null],
          ] as [string, string | null][]
        ).map(([rule, abbr]) => (
          <div key={rule} className="flex items-center gap-1.5 text-brand-success">
            <ShieldCheck size={11} />
            <span>
              {rule}
              {abbr ? (
                <>
                  {' '}
                  (<Abbr term={abbr}>{abbr}</Abbr>)
                </>
              ) : (
                ''
              )}
            </span>
          </div>
        ))}
      </div>
    </PageSection>

    {/* Non-compliant warning card */}
    <PageSection className="card border-brand-warning/30 bg-brand-warning/5">
      <div className="flex items-start gap-3">
        <ShieldAlert size={20} className="text-brand-warning shrink-0 mt-0.5" />
        <div className="text-sm space-y-1">
          <p className="font-semibold text-brand-warning">If a position becomes non-compliant</p>
          <ol className="list-decimal ml-4 space-y-1 text-brand-light/70">
            <li>
              <strong className="text-brand-light">Intend to sell</strong> — intention matters in
              Islamic law. Do not buy more.
            </li>
            <li>
              <strong className="text-brand-light">Exit within ~90 days</strong> — the grace period
              per <Abbr>AAOIFI</Abbr> <Abbr>SS</Abbr> No. 21 §5(e). Selling sooner is better.
            </li>
            <li>
              <strong className="text-brand-light">Purify gains</strong> — donate (profit × impure
              revenue %) to charity. See the Purification Owed widget on the Dashboard.
            </li>
            <li>
              <strong className="text-brand-light">Keep your principal</strong> — you are not
              required to donate capital, only the proportional impure gains.
            </li>
          </ol>
        </div>
      </div>
    </PageSection>

    <div className="space-y-6">
      {search && visibleSections.length === 0 && (
        <p className="text-center text-brand-light/50 py-12 text-sm italic">No results for "{search}"</p>
      )}
      {visibleSections.map((section) => (
        <FAQSection key={section.titleKey} section={section} />
      ))}
    </div>
  </Page>
  )
}

export default FAQPage
