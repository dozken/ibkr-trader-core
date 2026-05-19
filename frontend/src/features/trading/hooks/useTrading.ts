import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ROUTES, withAccount } from '../../../shared/routes'
import { useAccount } from '../context/AccountContext'

async function fetchSystemHealth() {
  const r = await fetch('/api/system/health')
  if (!r.ok) throw new Error('Failed to fetch system health')
  return r.json()
}

export function useTrading() {
  const { selectedAccountId } = useAccount()

  const { data: trades = [] } = useQuery({
    queryKey: ['trades', selectedAccountId],
    queryFn: () => fetch(withAccount(ROUTES.TRADES, selectedAccountId)).then((r) => {
      if (!r.ok) throw new Error('Failed to fetch trades')
      return r.json()
    }),
    refetchInterval: 30_000,
  })

  const { data: systemHealth } = useQuery({
    queryKey: ['systemHealth'],
    queryFn: fetchSystemHealth,
    refetchInterval: 10_000,
  })

  // Seed from REST so signals survived across restarts are visible immediately
  const { data: persistedPending = [] } = useQuery<any[]>({
    queryKey: ['pending-signals', selectedAccountId],
    queryFn: () => fetch(withAccount(ROUTES.TRADES_PENDING, selectedAccountId)).then((r) => {
      if (!r.ok) throw new Error(`pending-signals ${r.status}`)
      return r.json()
    }),
    refetchInterval: 30_000,
  })

  const { data: twapJobs = [] } = useQuery<any[]>({
    queryKey: ['twap-jobs'],
    queryFn: () => fetch(`${ROUTES.TRADES_TWAP}?status=RUNNING`).then((r) => {
      if (!r.ok) throw new Error(`twap-jobs ${r.status}`)
      return r.json()
    }),
    refetchInterval: 15_000,
  })

  const [audits, setAudits] = useState<any[]>([])
  const [tickerUpdates, setTickerUpdates] = useState<Record<string, any>>({})
  const [aiAnalysis, setAiAnalysis] = useState<any[]>([])
  const [wsPendingSignals, setWsPendingSignals] = useState<any[]>([])
  const [complianceViolations, setComplianceViolations] = useState<any[]>([])
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    const ws = new WebSocket(ROUTES.WS_TICKERS)
    ws.onopen = () => setIsConnected(true)
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        switch (msg.type) {
          case 'compliance_result':
            setAudits((prev) => {
              const filtered = prev.filter((a) => a.symbol !== msg.payload.symbol)
              return [msg.payload, ...filtered].slice(0, 50)
            })
            break
          case 'ticker_update':
            setTickerUpdates((prev) => ({
              ...prev,
              [msg.data.symbol]: msg.data,
            }))
            break
          case 'ai_analysis':
            setAiAnalysis((prev) => [msg.payload, ...prev].slice(0, 20))
            break
          case 'pending_signal':
            setWsPendingSignals((prev) => {
              const filtered = prev.filter((s) => s.symbol !== msg.payload.symbol)
              return [msg.payload, ...filtered]
            })
            break
          case 'compliance_violation':
            setComplianceViolations((prev) => {
              const filtered = prev.filter((v) => v.symbol !== msg.payload.symbol)
              return [msg.payload, ...filtered]
            })
            break
        }
      } catch (e) {
        console.warn('WS message parse error:', e)
      }
    }
    ws.onclose = () => setIsConnected(false)
    return () => ws.close()
  }, [])

  // Filter WS signals by selected account (null = show all)
  const filteredWsSignals = selectedAccountId == null
    ? wsPendingSignals
    : wsPendingSignals.filter((s) => s.account_id == null || s.account_id === selectedAccountId)

  // Merge REST-persisted signals with live WS signals; WS takes precedence per symbol
  const pendingSignals = [
    ...persistedPending.filter(
      (p) => !filteredWsSignals.some((w) => w.symbol === p.symbol)
    ),
    ...filteredWsSignals,
  ]

  return {
    trades,
    audits,
    tickerUpdates,
    aiAnalysis,
    pendingSignals,
    twapJobs,
    complianceViolations,
    isConnected,
    systemHealth,
  }
}
