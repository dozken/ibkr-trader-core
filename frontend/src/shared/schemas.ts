import { z } from 'zod'

const num = z.number().catch(0)
const numNull = z.number().nullable().catch(null)
const str = z.string().catch('')
const strNull = z.string().nullable().catch(null)
const bool = z.boolean().catch(false)

export const PositionSchema = z.object({
  symbol: str,
  quantity: num,
  avg_cost: num,
  market_value: num,
  unrealized_pnl: num,
})

const PositionPnLSchema = z.object({
  symbol: str,
  unrealized_pnl: num,
  realized_pnl: num,
  quantity: num,
  avg_cost: num,
  market_value: num,
  purification_cost: num,
  halal_pnl: num,
  days_held: z.number().nullable().catch(null),
  stop_price: numNull,
  target_price: numNull,
  partial_price: numNull,
})

export const PnLSummarySchema = z.object({
  total_unrealized_pnl: num,
  total_realized_pnl: num,
  total_purification_cost: num.optional(),
  positions: z.array(PositionPnLSchema).catch([]),
})

export const PortfolioValueSchema = z.object({
  available_funds: num,
  connected: bool,
  account_type: z.enum(['PAPER', 'LIVE']).catch('PAPER'),
})

export const PortfolioSummarySchema = z.object({
  connected: bool,
  account_type: z.enum(['PAPER', 'LIVE']).catch('PAPER'),
  total_value: numNull,
  cost_basis: numNull,
  cash_available: numNull,
  unrealized_pnl: numNull,
  return_pct: numNull,
  purity: numNull,
  purification_due: numNull,
  compliance_pct: numNull,
  zakat_estimate: numNull,
  sector_count: numNull,
  max_impure_revenue_pct: numNull,
  halal_label: strNull,
  compliance_label: strNull,
  sector_label: strNull,
  purify_label: strNull,
})

export const HistorySnapshotSchema = z.object({
  timestamp: str,
  total_value: num,
  benchmark_value: num.optional(),
  benchmarks: z.record(z.string(), z.number()).optional(),
})

export async function validatedFetch<T>(url: string, schema: z.ZodType<T>): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`API ${res.status}: ${url}`)
  const json = await res.json()
  return schema.parse(json)
}

export async function validatedFetchArray<T>(url: string, itemSchema: z.ZodType<T>): Promise<T[]> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`API ${res.status}: ${url}`)
  const json = await res.json()
  return z.array(itemSchema).catch([]).parse(json)
}
