const TRADE_STATE_LABELS: Record<string, string> = {
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

const TRADE_STATE_TOOLTIPS: Record<string, string> = {
  HALAL_CERTIFIED: 'Passed Shariah screen. Order queued — not yet sent to IBKR.',
  LIQUIDATING: 'Held position turned non-compliant. Force-unwinding to restore halal portfolio.',
  REJECTED_COMPLIANCE: 'Failed AAOIFI screen (debt, cash, or non-compliant revenue exceeded 33%). No order sent.',
  REJECTED_FUNDS: 'Insufficient buying power. Cash-only — no margin allowed.',
  IBKR_ERROR: 'IBKR rejected the order or network failed during submission.',
  FILLED: 'Order filled at IBKR. Awaiting T+2 settlement.',
  SETTLED: 'Trade settled (T+2). Cash cleared in account.',
  SUBMITTED: 'Order sent to IBKR. Awaiting fill confirmation.',
  PENDING_COMPLIANCE: 'Running Shariah compliance checks.',
  PENDING: 'Queued for processing.',
  CANCELLED: 'Order cancelled before fill.',
}

export function stateLabel(state: string): string {
  return TRADE_STATE_LABELS[state] ?? state.replace(/_/g, ' ')
}

export function stateTooltip(state: string): string | null {
  return TRADE_STATE_TOOLTIPS[state] ?? null
}
