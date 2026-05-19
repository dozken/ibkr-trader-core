import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ComplianceSnapshot } from '../../shared/types/trade'
import ShariahAuditFeed from './ShariahAuditFeed'

describe('ShariahAuditFeed Component', () => {
  const mockAudits: ComplianceSnapshot[] = [
    {
      symbol: 'AAPL',
      sector: 'Technology',
      is_compliant: true,
      debt_to_mkt_cap: 0.124,
      cash_to_mkt_cap: 0.081,
      impure_revenue_pct: 0.012,
    },
    {
      symbol: 'TSLA',
      sector: 'Automotive',
      is_compliant: false,
      debt_to_mkt_cap: 0.35,
      cash_to_mkt_cap: 0.15,
      impure_revenue_pct: 0.02,
      reason: 'Debt exceeds 33% limit',
    },
  ]

  it('renders audit information correctly', () => {
    render(<ShariahAuditFeed audits={mockAudits} />)
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('TSLA')).toBeInTheDocument()
  })

  it('shows real-time math (ratios)', () => {
    render(<ShariahAuditFeed audits={mockAudits} />)
    expect(screen.getByText('12.40%')).toBeInTheDocument() // AAPL Debt
    expect(screen.getByText('35.00%')).toBeInTheDocument() // TSLA Debt
  })

  it('highlights compliance breaches', () => {
    render(<ShariahAuditFeed audits={mockAudits} />)
    const tslaRow = screen.getByText('TSLA').closest('tr')
    expect(tslaRow).toHaveClass('text-brand-danger')
    expect(screen.getByText(/Debt exceeds 33% limit/i)).toBeInTheDocument()
  })
})
