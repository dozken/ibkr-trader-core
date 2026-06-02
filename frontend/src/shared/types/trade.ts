/**
 * Trade Types
 *
 * Following schemas/trade.py and STATE_MACHINE.md.
 * Citing: AGENT.md Engineering Standards.
 */

type TradeState =
  | 'IDLE'
  | 'AI_ANALYSIS'
  | 'SCREENING'
  | 'HALAL_CERTIFIED'
  | 'PRE_ORDER'
  | 'SUBMITTED'
  | 'FILLED'
  | 'RE_SCREENING'
  | 'LIQUIDATING'
  | 'PENDING_SETTLEMENT'
  | 'SETTLED'
  | 'REJECTED_COMPLIANCE'
  | 'REJECTED_FUNDS'
  | 'IBKR_ERROR'

export interface ComplianceSnapshot {
  symbol: string
  sector: string
  is_compliant: boolean
  debt_to_mkt_cap: number
  cash_to_mkt_cap: number
  impure_revenue_pct: number
  reason?: string
  country?: string | null
}

export interface Trade {
  id?: number
  symbol: string
  quantity: number
  side: 'BUY' | 'SELL'
  order_type: string
  state: TradeState
  compliance_snapshot?: ComplianceSnapshot
  created_at: string
  updated_at: string
  ibkr_order_id?: number
  fill_price?: number
  commission?: number
  error_message?: string | null
}
