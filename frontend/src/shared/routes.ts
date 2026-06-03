export const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const WS_BASE = API_BASE
  ? API_BASE.replace(/^http/, 'ws')
  : `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}`
export const API_KEY = import.meta.env.VITE_IBKR_API_KEY || ''

export const ROUTES = {
  WS_TICKERS: `${WS_BASE}/ws/tickers`,
  COMPLIANCE_SCREEN: (symbol: string) => `${API_BASE}/api/compliance/screen/${encodeURIComponent(symbol)}`,
  COMPLIANCE_SEARCH: (q: string) => `${API_BASE}/api/compliance/search?q=${encodeURIComponent(q)}`,
  COMPLIANCE_SCREEN_MANUAL: `${API_BASE}/api/compliance/screen`,
  COMPLIANCE_SCREEN_POSITIONS: `${API_BASE}/api/compliance/screen-positions`,
  COMPLIANCE_POSITIONS: `${API_BASE}/api/compliance/positions`,
  COMPLIANCE_AUDIT: `${API_BASE}/api/compliance/audit`,
  TRADES: `${API_BASE}/api/trades`,
  TRADES_TWAP: `${API_BASE}/api/trades/twap`,
  TRADES_TWAP_CANCEL: (id: number) => `${API_BASE}/api/trades/twap/${id}/cancel`,
  TRADES_PENDING: `${API_BASE}/api/trades/pending`,
  TRADES_PENDING_RESOLVE: (id: number) => `${API_BASE}/api/trades/pending/${id}/resolve`,
  ZAKAT_CALCULATE: `${API_BASE}/api/zakat/calculate`,
  ZAKAT_HAWL: `${API_BASE}/api/zakat/hawl`,
  ZAKAT_HAWL_RESET: `${API_BASE}/api/zakat/hawl/reset`,
  ZAKAT_PURIFICATION: `${API_BASE}/api/zakat/purification`,
  ZAKAT_PURIFICATION_RECORD: `${API_BASE}/api/zakat/purification/record`,
  ZAKAT_PURIFICATION_HISTORY: `${API_BASE}/api/zakat/purification/history`,
  ZAKAT_PURIFICATION_LIABILITIES: `${API_BASE}/api/zakat/purification/liabilities`,
  PORTFOLIO_DIVIDENDS: `${API_BASE}/api/portfolio/dividends`,
  PORTFOLIO_VALUE: `${API_BASE}/api/portfolio/value`,
  PORTFOLIO_SUMMARY: `${API_BASE}/api/portfolio/summary`,
  PORTFOLIO_POSITIONS: `${API_BASE}/api/portfolio/positions`,
  PORTFOLIO_HISTORY: `${API_BASE}/api/portfolio/history`,
  PORTFOLIO_ALLOCATE: `${API_BASE}/api/portfolio/allocate`,
  PORTFOLIO_PNL: `${API_BASE}/api/portfolio/pnl`,
  PORTFOLIO_SIMULATE: `${API_BASE}/api/portfolio/simulate`,
  AI_SIGNALS: `${API_BASE}/api/ai/signals`,
  AI_BACKTEST: `${API_BASE}/api/ai/backtest`,
  AI_DISCOVER: `${API_BASE}/api/ai/discover`,
  AI_REBALANCE: `${API_BASE}/api/ai/rebalance`,
  AI_ML_STATUS: `${API_BASE}/api/ai/ml-status`,
  AI_DIVERSIFY: `${API_BASE}/api/ai/diversify`,
  AI_DIVERSIFY_SECTOR: `${API_BASE}/api/ai/diversify-sector`,
  AI_APPROVE: `${API_BASE}/api/trades/approve`,
  AI_HALAL_UNIVERSE: `${API_BASE}/api/ai/halal-universe`,
  AI_PORTFOLIO_BACKTEST: `${API_BASE}/api/ai/portfolio-backtest`,
  AI_SIGNAL_LOG: `${API_BASE}/api/ai/signal-log`,
  AI_SIGNAL_QUALITY: `${API_BASE}/api/ai/signal-quality`,
  AI_STRATEGY_AUDIT: `${API_BASE}/api/ai/strategy-audit`,
  AI_SCAN_REGIONS: `${API_BASE}/api/ai/scan/regions`,
  AI_SCAN: (region: string) => `${API_BASE}/api/ai/scan/${encodeURIComponent(region)}`,
  SETTINGS: `${API_BASE}/api/settings`,
  ACCOUNTS: `${API_BASE}/api/accounts`,
  SYSTEM_READINESS: `${API_BASE}/api/system/readiness`,
  SYSTEM_MARKETS: `${API_BASE}/api/system/markets`,
  SETTINGS_PAUSE: `${API_BASE}/api/settings/pause`,
  SETTINGS_RESUME: `${API_BASE}/api/settings/resume`,
  TRADES_EMERGENCY_LIQUIDATE: `${API_BASE}/api/trades/emergency-liquidate`,
  TRADES_BATCH_SELL: `${API_BASE}/api/trades/batch-sell`,
  COMPLIANCE_MANUAL_VERIFICATIONS: `${API_BASE}/api/compliance/manual-verifications`,
  COMPLIANCE_MANUAL_VERIFY: `${API_BASE}/api/compliance/manual-verify`,
  COMPLIANCE_MANUAL_UNVERIFY: (symbol: string) => `${API_BASE}/api/compliance/manual-verify/${encodeURIComponent(symbol)}`,
  GATEWAY_STATUS: `${API_BASE}/api/gateway/status`,
  GATEWAY_AUTH: `${API_BASE}/api/gateway/auth`,
  GATEWAY_STOP: (gw: string) => `${API_BASE}/api/gateway/${gw}/stop`,
  GATEWAY_START: (gw: string) => `${API_BASE}/api/gateway/${gw}/start`,
  GATEWAY_RESTART: (gw: string) => `${API_BASE}/api/gateway/${gw}/restart`,
  GATEWAY_RECONNECT: `${API_BASE}/api/gateway/reconnect`,
} as const

export function withAccount(url: string, accountId: number | null): string {
  if (accountId == null) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}account_id=${accountId}`
}
