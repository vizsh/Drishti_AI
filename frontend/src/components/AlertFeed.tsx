import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { PlayCircle, X } from 'lucide-react'
import type { AlertItem } from '../types'
import { seatColor } from '../lib/colors'

interface Props {
  alerts: AlertItem[]
  feedback: string[]
  seatIds: string[]
  onDismiss: (seatId: string) => Promise<void>
  onViewEvidence: (url: string) => void
}

export function AlertFeed({ alerts, feedback, seatIds, onDismiss, onViewEvidence }: Props) {
  const [dismissing, setDismissing] = useState<Set<string>>(new Set())

  const handleDismiss = async (item: AlertItem) => {
    setDismissing((prev) => new Set(prev).add(item.id))
    await onDismiss(item.seatId)
  }

  return (
    <div>
      <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Alert feed</h2>
      <div className="rounded-2xl border border-white/8 p-3 flex flex-col gap-2 overflow-y-auto" style={{ height: 560 }}>
        {feedback.map((msg, i) => (
          <div key={`fb-${i}`} className="text-[11px] mono px-3 py-2 rounded-lg" style={{ background: '#5ad1ff14', color: '#5ad1ff' }}>
            ↺ {msg}
          </div>
        ))}
        {alerts.length === 0 && feedback.length === 0 && (
          <div className="text-xs mono text-white/30 text-center py-8">Waiting for events…</div>
        )}
        <AnimatePresence initial={false}>
          {alerts.map((item) => (
            <motion.div
              key={item.id}
              layout
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="rounded-xl p-3 border"
              style={{
                borderColor: item.kind === 'alert' ? '#ff5a3640' : '#c4a3ff40',
                background: item.kind === 'alert' ? '#ff5a360c' : '#c4a3ff0c',
              }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold" style={{ color: seatColor(item.seatId, seatIds) }}>
                  {item.seatId.toUpperCase()}
                </span>
                {item.kind === 'gesture' ? (
                  <span className="text-[9px] mono px-1.5 py-0.5 rounded" style={{ background: '#c4a3ff22', color: '#c4a3ff' }}>GESTURE</span>
                ) : (
                  <span className="text-[10px] mono text-white/40">
                    {item.timestamp.toFixed(1)}s · risk {item.riskScore?.toFixed(2)}
                    {item.confidence != null ? ` · conf ${(item.confidence * 100).toFixed(0)}%` : ''}
                  </span>
                )}
              </div>
              {item.objectLabel && (
                <span className="text-[9px] mono px-1.5 py-0.5 rounded mr-1" style={{ background: '#ffb64822', color: '#ffb648' }}>
                  {item.objectLabel.toUpperCase()} ⚠ UNVERIFIED
                </span>
              )}
              <p className="text-xs text-white/75 leading-snug mb-2">{item.explanation}</p>
              {item.confidence != null && item.confidence < 0.4 && (
                <p className="text-[10px] mono text-white/40 mb-2">⚠ low detection confidence — treat as a prompt to look, not evidence</p>
              )}
              {item.kind === 'alert' && (
                <div className="flex gap-2">
                  <button
                    onClick={() => handleDismiss(item)}
                    disabled={dismissing.has(item.id)}
                    className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/50 hover:border-white/30"
                  >
                    <X size={11} /> {dismissing.has(item.id) ? 'widened ✓' : 'dismiss — false positive'}
                  </button>
                  {item.evidenceUrl && (
                    <button
                      onClick={() => onViewEvidence(item.evidenceUrl!)}
                      className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border"
                      style={{ borderColor: '#5ad1ff40', color: '#5ad1ff' }}
                    >
                      <PlayCircle size={11} /> view evidence
                    </button>
                  )}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
