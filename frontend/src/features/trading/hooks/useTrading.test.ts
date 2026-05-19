import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useTrading } from './useTrading'

function queryWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children)
}

const mockTrade = {
  id: 1,
  symbol: 'AAPL',
  state: 'HALAL_CERTIFIED',
  side: 'BUY',
  quantity: 10,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  order_type: 'MKT',
}

describe('useTrading hook', () => {
  let mockWebSocket: any

  beforeEach(() => {
    mockWebSocket = { send: vi.fn(), close: vi.fn(), onmessage: null, onopen: null, onclose: null }
    function MockWebSocket(this: any, url: string) {
      this.url = url
      this.send = mockWebSocket.send
      this.close = mockWebSocket.close
      this.onmessage = null
      this.onopen = null
      this.onclose = null
      mockWebSocket.instance = this
    }
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([mockTrade]) }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('connects to /ws/tickers websocket on mount', () => {
    renderHook(() => useTrading(), { wrapper: queryWrapper() })
    expect(mockWebSocket.instance.url).toContain('/ws/tickers')
  })

  it('loads trades from REST API on mount', async () => {
    const { result } = renderHook(() => useTrading(), { wrapper: queryWrapper() })
    await waitFor(() => expect(result.current.trades).toContainEqual(mockTrade))
  })

  it('updates audits and refetches trades when compliance_result received', async () => {
    const { result } = renderHook(() => useTrading(), { wrapper: queryWrapper() })

    const mockAudit = {
      symbol: 'AAPL',
      sector: 'Tech',
      is_compliant: true,
      debt_to_mkt_cap: 0.1,
      cash_to_mkt_cap: 0.05,
      impure_revenue_pct: 0.01,
    }

    act(() => {
      mockWebSocket.instance.onmessage({
        data: JSON.stringify({ type: 'compliance_result', payload: mockAudit }),
      })
    })

    await waitFor(() => expect(result.current.audits).toContainEqual(mockAudit))
  })
})
