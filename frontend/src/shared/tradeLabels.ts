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

const TRADE_STATE_TOOLTIPS: Record<string, string> = {
  HALAL_CERTIFIED: 'Passed Shariah screening — ready to execute',
  LIQUIDATING: 'Position is being sold off due to compliance change',
  REJECTED_COMPLIANCE: 'Failed AAOIFI screening — trade blocked',
  REJECTED_FUNDS: 'Not enough cash available to place this order',
  IBKR_ERROR: 'Interactive Brokers returned an error',
  FILLED: 'Order has been filled by the broker',
  SETTLED: 'Trade fully settled and recorded',
  PENDING_COMPLIANCE: 'Waiting for Shariah compliance check',
  PENDING: 'Trade is queued and waiting for execution',
  SUBMITTED: 'Order submitted to Interactive Brokers',
  CANCELLED: 'Order was cancelled',
}

export function stateTooltip(state: string): string | null {
  return TRADE_STATE_TOOLTIPS[state] ?? null
}
