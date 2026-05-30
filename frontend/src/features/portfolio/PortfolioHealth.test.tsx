import { render, screen } from '@testing-library/react'
import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ComplianceSnapshot } from '../../shared/types/trade'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PortfolioHealth from './components/PortfolioHealth'

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

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
    renderWithClient(<PortfolioHealth audits={mockAudits} portfolioValue={100000} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders Zakat calculation based on portfolio value', async () => {
    // 2.5% of 100,000 = 2,500 (component fetches the estimate from the API)
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ zakat_due: 2500, below_nisab: false, nisab: 5000 }),
    } as Response)
    renderWithClient(<PortfolioHealth audits={mockAudits} portfolioValue={100000} />)
    expect(
      await screen.findByText((_content, element) => element?.textContent === '$2,500.00')
    ).toBeInTheDocument()
  })

  it('shows diversification status', () => {
    renderWithClient(<PortfolioHealth audits={mockAudits} portfolioValue={100000} />)
    expect(screen.getByText(/Diversification/i)).toBeInTheDocument()
  })
})
