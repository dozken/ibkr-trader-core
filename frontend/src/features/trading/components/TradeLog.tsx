import { AlertTriangle, Ban, CheckCircle2, ClipboardList, Clock } from 'lucide-react'
import type React from 'react'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { stateLabel } from '../../../shared/tradeLabels'
import type { Trade } from '../../../shared/types/trade'

interface TradeLogProps {
  trades: Trade[]
}

/**
 * TradeLog Component
 *
 * Displays a real-time log of trades with their Shariah status and execution state.
 * Following Track A rules and AGENT.md engineering standards.
 *
 * Citing:
 * - AGENT.md: Ironclad Engineering & Fail-Closed logic.
 * - STATE_MACHINE.md: Visually distinguishes HALAL_CERTIFIED and LIQUIDATING.
 */
const TradeLog: React.FC<TradeLogProps> = ({ trades }) => {
  const [filterState, setFilterState] = useState('ALL')

  const getStatusStyle = (state: Trade['state']) => {
    switch (state) {
      case 'HALAL_CERTIFIED':
        return 'bg-brand-success/10 text-brand-success border-brand-success/20'
      case 'LIQUIDATING':
        return 'bg-brand-danger/10 text-brand-danger border-brand-danger/20'
      case 'REJECTED_COMPLIANCE':
      case 'REJECTED_FUNDS':
      case 'IBKR_ERROR':
        return 'bg-brand-warning/10 text-brand-warning border-brand-warning/20'
      case 'FILLED':
      case 'SETTLED':
        return 'bg-brand-primary/10 text-brand-primary border-brand-primary/20'
      default:
        return 'bg-brand-muted/10 text-brand-light/70 border-brand-muted/20'
    }
  }

  const getStatusIcon = (state: Trade['state']) => {
    switch (state) {
      case 'HALAL_CERTIFIED':
        return <CheckCircle2 size={14} />
      case 'LIQUIDATING':
        return <AlertTriangle size={14} />
      case 'REJECTED_COMPLIANCE':
      case 'IBKR_ERROR':
        return <Ban size={14} />
      case 'FILLED':
      case 'SETTLED':
        return <CheckCircle2 size={14} />
      default:
        return <Clock size={14} />
    }
  }

  const filtered = filterState === 'ALL' ? trades : trades.filter(t => t.state === filterState)

  return (
    <div className="table-container">
      <div className="card-header">
        <h2 className="heading-2">
          <ClipboardList className="text-brand-primary" />
          Real-Time Trade Log
        </h2>
      </div>

      <div className="flex flex-wrap gap-1.5 px-4 pb-3 border-b border-brand-divider/40">
        {(['ALL', 'FILLED', 'SETTLED', 'HALAL_CERTIFIED', 'LIQUIDATING', 'REJECTED_COMPLIANCE', 'REJECTED_FUNDS', 'IBKR_ERROR'] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setFilterState(s)}
            className={`px-2.5 py-0.5 text-[10px] font-bold uppercase rounded-full border transition-colors ${
              filterState === s
                ? 'bg-brand-primary/20 border-brand-primary/50 text-brand-primary'
                : 'border-brand-divider/40 text-brand-light/50 hover:text-brand-light/80'
            }`}
          >
            {s === 'ALL' ? `All (${trades.length})` : stateLabel(s)}
          </button>
        ))}
      </div>

      {/* Mobile cards */}
      <div className="md:hidden divide-y divide-brand-divider/40">
        {filtered.length === 0 ? (
          <p className="p-6 text-center text-brand-light/70 italic text-sm">
            No active trades detected.
          </p>
        ) : (
          filtered.map((trade) => (
            <div key={trade.id || trade.created_at} className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-brand-light">{trade.symbol}</span>
                <span
                  className={cn(
                    'text-xs font-bold px-2 py-0.5 rounded',
                    trade.side === 'BUY' ? 'text-brand-success' : 'text-brand-danger',
                  )}
                >
                  {trade.side}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span
                  className={cn(
                    'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border',
                    getStatusStyle(trade.state),
                  )}
                >
                  {getStatusIcon(trade.state)}
                  {stateLabel(trade.state)}
                </span>
                <span className="text-xs text-brand-light/70 font-mono">
                  {new Date(trade.created_at).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-xs text-brand-light/70 font-mono">
                Qty: {trade.quantity} · {trade.ibkr_order_id || '—'}
              </p>
            </div>
          ))
        )}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-left">
          <thead className="table-header">
            <tr>
              <th className="table-cell font-medium">Time</th>
              <th className="table-cell font-medium">Symbol</th>
              <th className="table-cell font-medium">Side</th>
              <th className="table-cell font-medium">Quantity</th>
              <th className="table-cell font-medium">State</th>
              <th className="table-cell font-medium">IBKR ID</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="table-cell text-center text-brand-light/70 italic">
                  No active trades detected in state machine.
                </td>
              </tr>
            ) : (
              filtered.map((trade) => (
                <tr key={trade.id || trade.created_at} className="table-row">
                  <td className="table-cell text-xs text-brand-light/70">
                    {new Date(trade.created_at).toLocaleTimeString()}
                  </td>
                  <td className="table-cell font-bold text-brand-light">{trade.symbol}</td>
                  <td className="table-cell">
                    <span
                      className={cn(
                        'text-xs font-bold px-2 py-0.5 rounded',
                        trade.side === 'BUY' ? 'text-brand-success' : 'text-brand-danger',
                      )}
                    >
                      {trade.side}
                    </span>
                  </td>
                  <td className="table-cell text-sm text-brand-light">{trade.quantity}</td>
                  <td className="table-cell">
                    <span
                      className={cn(
                        'flex items-center gap-1.5 w-fit px-2.5 py-1 rounded-full text-xs font-medium border',
                        getStatusStyle(trade.state),
                      )}
                    >
                      {getStatusIcon(trade.state)}
                      {trade.state}
                    </span>
                  </td>
                  <td className="table-cell text-xs font-mono text-brand-light/70">
                    {trade.ibkr_order_id || '---'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default TradeLog
