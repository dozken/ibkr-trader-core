import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import Settings from './Settings'

// Mock context/hooks to prevent dependency errors
vi.mock('../trading/context/AccountContext', () => ({
  useAccount: () => ({
    selectedAccountId: 1,
  }),
}))

const MOCK_SETTINGS = {
  min_trade_size: 100,
  max_commission_pct: 0.5,
  cash_reserve_pct: 10,
  max_position_size_pct: 15,
  max_sector_exposure_pct: 25,
  max_positions: 15,
  target_weights: { AAPL: 10 },
  settlement_strictness: 'PHYSICAL_T2',
  purification_automation: 'MANUAL',
  ratio_buffer: 2,
  risk_profile: 'CONSERVATIVE',
  sector_exclusion: [],
  rebalance_frequency: 'WEEKLY',
  critical_auto_sell: false,
  alert_channels: [],
  watchlist: ['AAPL'],
  auto_execute_threshold: 0,
  signal_min_confidence: 30,
  stop_loss_pct: null,
  take_profit_pct: null,
  auto_compliance_check: true,
  compliance_check_interval_hours: 24,
  use_atr_stops: true,
  enable_discovery_auto: false,
  discovery_interval_hours: 6,
  use_global_universe: false,
  global_universe_cap_per_cycle: 60,
  enable_halal_drip: false,
  use_trailing_stop: true,
  use_kelly_sizing: true,
  time_exit_days: 45,
  partial_profit_pct: 10,
  partial_profit_fraction: 0.5,
  require_pullback_entry: true,
  re_entry_cooldown_days: 14,
  use_limit_orders: false,
  limit_order_slippage_pct: 0.1,
  max_correlation: 0.85,
  rerate_sell_threshold: 35,
  max_vix_for_buys: 30,
  trading_paused: false,
  position_size_pct: 5,
}

function renderSettings() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
    },
  })
  return render(
    React.createElement(QueryClientProvider, { client: qc }, React.createElement(Settings)),
  )
}

describe('Settings Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    
    // Mock the global fetch function
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/settings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(MOCK_SETTINGS),
        })
      }
      if (url.includes('/api/ai/ml-status')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              snapshot_count: 100,
              ppo_threshold: 500,
              model_type: 'DQN',
              ppo_ready: false,
              is_training: false,
              last_trained: '2026-05-20T10:00:00Z',
            }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    })
  })

  it('renders all four sections', async () => {
    renderSettings()
    
    // Wait for the initial loading skeleton to resolve
    expect(await screen.findByText(/Order Settings/i)).toBeInTheDocument()
    
    // Click Show Advanced to show the advanced sections
    const showAdvancedBtn = screen.getByText(/Show Advanced/i)
    fireEvent.click(showAdvancedBtn)
    
    // Verify sections are visible
    expect(await screen.findByText(/Shariah Compliance/i)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Execution/i })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Alerts/i })).toBeInTheDocument()
  })

  it('renders key allocation fields', async () => {
    renderSettings()
    
    expect(await screen.findByLabelText(/Minimum Order Size/i)).toBeInTheDocument()
    expect(await screen.findByLabelText(/Max Position Size/i)).toBeInTheDocument()
  })
})
