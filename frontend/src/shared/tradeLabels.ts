export const TRADE_STATE_LABELS: Record<string, string> = {
  HALAL_CERTIFIED: 'Approved',
  LIQUIDATING: 'Selling Off',
  REJECTED_COMPLIANCE: 'Blocked — Not Halal',
  REJECTED_FUNDS: 'Blocked — Insufficient Funds',
  IBKR_ERROR: 'Broker Error',
  FILLED: 'Executed',
  SETTLED: 'Complete',
  PENDING_COMPLIANCE: 'Checking Compliance…',
  PENDING: 'Pending',
  SUBMITTED: 'Sent to Broker',
  CANCELLED: 'Cancelled',
}

export function stateLabel(state: string): string {
  return TRADE_STATE_LABELS[state] ?? state.replace(/_/g, ' ')
}
