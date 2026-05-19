import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Trade } from '../../../shared/types/trade'
import Controls from './Controls'

describe('Controls Component', () => {
  const mockTrades: Trade[] = [
    {
      id: 1,
      symbol: 'AAPL',
      side: 'BUY',
      quantity: 10,
      state: 'HALAL_CERTIFIED',
      order_type: 'MKT',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ]

  it('renders Kill-Switch button', () => {
    render(
      <Controls
        pendingApprovals={[]}
        onKillSwitch={vi.fn()}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /Kill-Switch/i })).toBeInTheDocument()
  })

  it('calls onKillSwitch when confirmed', () => {
    const onKillSwitch = vi.fn()
    render(
      <Controls
        pendingApprovals={[]}
        onKillSwitch={onKillSwitch}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Kill-Switch/i }))

    // Should show confirmation
    expect(screen.getByText(/Confirm Emergency Liquidation/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Confirm Kill-Switch/i }))
    expect(onKillSwitch).toHaveBeenCalled()
  })

  it('renders Manual Approval modal when trades are pending', () => {
    render(
      <Controls
        pendingApprovals={mockTrades}
        onKillSwitch={vi.fn()}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    )
    expect(screen.getByText(/Manual Approval Required/i)).toBeInTheDocument()
    expect(screen.getByText('AAPL')).toBeInTheDocument()
  })

  it('calls onApprove when approve button is clicked', () => {
    const onApprove = vi.fn()
    render(
      <Controls
        pendingApprovals={mockTrades}
        onKillSwitch={vi.fn()}
        onApprove={onApprove}
        onReject={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Approve/i }))
    expect(onApprove).toHaveBeenCalledWith(mockTrades[0])
  })
})
