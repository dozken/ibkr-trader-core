import { Binary, Info, ShieldAlert, ShieldCheck } from 'lucide-react'
import React from 'react'
import { cn } from '@/lib/utils'
import type { ComplianceSnapshot } from '../../shared/types/trade'

interface ShariahAuditFeedProps {
  audits: ComplianceSnapshot[]
}

/**
 * ShariahAuditFeed Component
 *
 * Displays a live feed of Shariah audits with real-time financial ratios.
 * Following Track A rules and AGENT.md engineering standards.
 *
 * Citing:
 * - AGENT.md: Ironclad Engineering & Strict TDD.
 * - COMPLIANCE.md: Financial Ratio Screening (AAOIFI Standard).
 */
const ShariahAuditFeed: React.FC<ShariahAuditFeedProps> = ({ audits }) => {
  const formatPct = (val: number) => `${(val * 100).toFixed(2)}%`

  return (
    <div className="table-container">
      <div className="card-header bg-brand-surface/50">
        <h2 className="heading-2">
          <Binary className="text-brand-success" />
          Live Shariah Audit Feed
        </h2>
        <div className="text-xs text-brand-light/70 font-mono flex gap-4">
          <span>DEBT &lt; 33%</span>
          <span>CASH &lt; 33%</span>
          <span>IMPURE &lt; 5%</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="table-header">
            <tr>
              <th className="table-cell font-medium">Symbol</th>
              <th className="table-cell font-medium">Debt / Mkt Cap</th>
              <th className="table-cell font-medium">Cash / Mkt Cap</th>
              <th className="table-cell font-medium">Impure Revenue</th>
              <th className="table-cell font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {audits.length === 0 ? (
              <tr>
                <td colSpan={5} className="table-cell text-center text-brand-light/70 italic">
                  Waiting for live compliance data stream...
                </td>
              </tr>
            ) : (
              audits.map((audit) => (
                <React.Fragment key={audit.symbol}>
                  <tr
                    className={cn(
                      'table-row',
                      !audit.is_compliant && 'bg-brand-danger/5 text-brand-danger',
                    )}
                  >
                    <td className="table-cell font-bold">{audit.symbol}</td>
                    <td
                      className={cn(
                        'table-cell text-sm font-mono',
                        audit.debt_to_mkt_cap >= 0.33
                          ? 'text-brand-danger font-bold'
                          : 'text-brand-light',
                      )}
                    >
                      {formatPct(audit.debt_to_mkt_cap)}
                    </td>
                    <td
                      className={cn(
                        'table-cell text-sm font-mono',
                        audit.cash_to_mkt_cap >= 0.33
                          ? 'text-brand-danger font-bold'
                          : 'text-brand-light',
                      )}
                    >
                      {formatPct(audit.cash_to_mkt_cap)}
                    </td>
                    <td
                      className={cn(
                        'table-cell text-sm font-mono',
                        audit.impure_revenue_pct >= 0.05
                          ? 'text-brand-danger font-bold'
                          : 'text-brand-light',
                      )}
                    >
                      {formatPct(audit.impure_revenue_pct)}
                    </td>
                    <td className="table-cell">
                      {audit.is_compliant ? (
                        <span className="flex items-center gap-1 text-xs text-brand-success font-medium">
                          <ShieldCheck size={14} /> COMPLIANT
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-brand-danger font-medium">
                          <ShieldAlert size={14} /> NON-COMPLIANT
                        </span>
                      )}
                    </td>
                  </tr>
                  {!audit.is_compliant && audit.reason && (
                    <tr className="bg-brand-danger/5 border-b border-brand-divider/50">
                      <td colSpan={5} className="px-4 pb-4 pt-0">
                        <div className="flex items-start gap-2 text-xs text-brand-danger bg-brand-danger/10 p-2 rounded border border-brand-danger/20">
                          <Info size={14} className="mt-0.5 shrink-0" />
                          <span>{audit.reason}</span>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default ShariahAuditFeed
