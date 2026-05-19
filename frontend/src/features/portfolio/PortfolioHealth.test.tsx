import { render, screen } from '@testing-library/react'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { ComplianceSnapshot } from '../../shared/types/trade'
import PortfolioHealth from './components/PortfolioHealth'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) =>
    React.createElement('a', props, children),
}))

describe('PortfolioHealth Component', () => {
  const mockAudits: ComplianceSnapshot[] = [
    {
      symbol: 'AAPL',
      sector: 'Tech',
      is_compliant: true,
      debt_to_mkt_cap: 0.1,
      cash_to_mkt_cap: 0.05,
      impure_revenue_pct: 0.01,
    },
    {
      symbol: 'TSLA',
      sector: 'Auto',
      is_compliant: false,
      debt_to_mkt_cap: 0.35,
      cash_to_mkt_cap: 0.1,
      impure_revenue_pct: 0.02,
    },
  ]

  it('calculates compliance percentage correctly', () => {
    render(<PortfolioHealth audits={mockAudits} portfolioValue={100000} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('renders Zakat calculation based on portfolio value', () => {
    // 2.5% of 100,000 = 2,500
    render(<PortfolioHealth audits={mockAudits} portfolioValue={100000} />)
    expect(screen.getByText(/\$2,500\.00/i)).toBeInTheDocument()
  })

  it('shows diversification status', () => {
    render(<PortfolioHealth audits={mockAudits} portfolioValue={100000} />)
    expect(screen.getByText(/Diversification/i)).toBeInTheDocument()
  })
})
