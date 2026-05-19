import { CheckCircle2, XCircle } from 'lucide-react'
import type React from 'react'

const pct = (v: number) => `${(v * 100).toFixed(2)}%`

interface RatioBarProps {
  label: string
  value: number
  limit: number
  pass: boolean
}

export const RatioBar: React.FC<RatioBarProps> = ({ label, value, limit, pass }) => (
  <div className="space-y-1.5">
    <div className="flex justify-between items-end">
      <span className="text-[10px] font-bold uppercase tracking-wider text-brand-light/70 flex items-center gap-1">
        {pass ? (
          <CheckCircle2 size={10} className="text-brand-success" />
        ) : (
          <XCircle size={10} className="text-brand-danger" />
        )}
        {label}
      </span>
      <span
        className={`text-xs font-mono font-bold ${pass ? 'text-brand-success' : 'text-brand-danger'}`}
      >
        {pct(value)}{' '}
        <span className="text-[10px] text-brand-light/70 font-normal">/ {pct(limit)}</span>
      </span>
    </div>
    <div className="h-1 rounded-full bg-brand-divider/30 relative">
      <div
        className={`h-full rounded-full transition-all duration-700 ease-out ${pass ? 'bg-brand-success shadow-[0_0_8px_rgba(34,197,94,0.3)]' : 'bg-brand-danger shadow-[0_0_8px_rgba(239,68,68,0.3)]'}`}
        style={{ width: `${Math.min((value / limit) * 100, 100)}%` }}
      />
      <div
        className="absolute top-1/2 -translate-y-1/2 w-0.5 h-3 bg-brand-warning/70 rounded-full"
        style={{ left: '100%' }}
        title={`AAOIFI limit: ${(limit * 100).toFixed(0)}%`}
      />
    </div>
  </div>
)
