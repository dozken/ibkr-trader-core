import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Trade } from '../../../shared/types/trade'
import TradeLog from './TradeLog'

describe('TradeLog Component', () => {
  const mockTrades: Trade[] = [
    {
      id: 1,
      symbol: 'AAPL',
      side: 'BUY',
      quantity: 10,
      state: 'HALAL_CERTIFIED',
      order_type: 'MKT',
      created_at: '2026-04-25T10:00:00Z',
      updated_at: '2026-04-25T10:00:00Z',
    },
    {
      id: 2,
      symbol: 'TSLA',
      side: 'SELL',
      quantity: 5,
      state: 'LIQUIDATING',
      order_type: 'MKT',
      created_at: '2026-04-25T10:05:00Z',
      updated_at: '2026-04-25T10:05:00Z',
    },
  ]

  it('renders trade information correctly', () => {
    render(<TradeLog trades={mockTrades} />)
    expect(screen.getAllByText('AAPL').length).toBeGreaterThan(0)
    expect(screen.getAllByText('TSLA').length).toBeGreaterThan(0)
  })

  it('visually distinguishes HALAL_CERTIFIED state', () => {
    render(<TradeLog trades={mockTrades} />)
    const halalBadges = screen.getAllByText('Approved')
    const hasClass = halalBadges.some(el => el.classList.contains('bg-brand-success/10'))
    expect(hasClass).toBe(true)
  })

  it('visually distinguishes LIQUIDATING state', () => {
    render(<TradeLog trades={mockTrades} />)
    const liquidatingBadges = screen.getAllByText('Selling Off')
    const hasClass = liquidatingBadges.some(el => el.classList.contains('bg-brand-danger/10'))
    expect(hasClass).toBe(true)
  })
})
