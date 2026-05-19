import { AlertTriangle, CheckCircle2, ShieldAlert, Skull, XCircle } from 'lucide-react'
import type React from 'react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Trade } from '../../../shared/types/trade'

interface ControlsProps {
  pendingApprovals: Trade[]
  onKillSwitch: () => void
  onApprove: (trade: Trade) => void
  onReject: (trade: Trade) => void
}

const Controls: React.FC<ControlsProps> = ({
  pendingApprovals,
  onKillSwitch,
  onApprove,
  onReject,
}) => {
  const [showKillConfirm, setShowKillConfirm] = useState(false)

  return (
    <div className="flex gap-4 mb-8">
      <Button
        variant="destructive"
        onClick={() => setShowKillConfirm(true)}
        aria-label="Kill-Switch"
      >
        <Skull size={20} />
        EMERGENCY KILL-SWITCH
      </Button>

      {showKillConfirm && (
        <div className="modal-overlay">
          <div className="modal-content-danger">
            <div className="flex flex-col items-center text-center mb-8">
              <div className="w-16 h-16 bg-brand-danger/10 rounded-full flex items-center justify-center mb-4 border border-brand-danger/20">
                <Skull className="text-brand-danger" size={32} />
              </div>
              <h2 className="heading-1 justify-center mb-2">Confirm Emergency Liquidation</h2>
              <p className="text-brand-light/70">
                This will immediately trigger sell orders for ALL held positions. This action is
                irreversible and follows the "Safe Shutdown" protocol in SECURITY.md.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <Button
                variant="destructive"
                className="w-full py-3"
                onClick={() => {
                  onKillSwitch()
                  setShowKillConfirm(false)
                }}
              >
                Confirm Kill-Switch
              </Button>
              <Button
                variant="secondary"
                className="w-full py-3"
                onClick={() => setShowKillConfirm(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {pendingApprovals.length > 0 && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="bg-brand-primary/10 p-6 border-b border-brand-primary/20 flex items-center justify-between">
              <div className="flex items-center gap-3 text-brand-primary">
                <ShieldAlert size={24} />
                <h2 className="heading-2">Manual Approval Required</h2>
              </div>
              <span className="bg-brand-primary text-brand-light text-xs px-2 py-1 rounded-full font-bold">
                {pendingApprovals.length} PENDING
              </span>
            </div>

            <div className="p-6 max-h-[60vh] overflow-auto">
              <div className="space-y-4">
                {pendingApprovals.map((trade) => (
                  <div
                    key={trade.id || trade.created_at}
                    className="bg-brand-surface border border-brand-divider p-4 rounded-xl flex items-center justify-between"
                  >
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-lg font-bold text-brand-light">{trade.symbol}</span>
                        <Badge variant={trade.side === 'BUY' ? 'success' : 'danger'}>
                          {trade.side}
                        </Badge>
                      </div>
                      <div className="text-sm text-brand-light/70">
                        {trade.quantity} Shares • Market Order
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => onReject(trade)}
                        title="Reject Trade"
                        className="text-brand-light/70 hover:text-brand-danger hover:bg-brand-danger/10"
                      >
                        <XCircle size={24} />
                      </Button>
                      <Button
                        variant="success"
                        onClick={() => onApprove(trade)}
                        aria-label="Approve"
                      >
                        <CheckCircle2 size={20} />
                        Approve
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-6 bg-brand-surface/50 border-t border-brand-divider flex items-start gap-3">
              <AlertTriangle className="text-brand-warning shrink-0" size={18} />
              <p className="text-xs text-brand-light/70 leading-relaxed">
                Verification required per SECURITY.md Section 4. Approving these trades will execute
                them against the live IBKR Paper Trading gateway. Ensure AAOIFI ratios are within
                "Ironclad" limits before proceeding.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Controls
