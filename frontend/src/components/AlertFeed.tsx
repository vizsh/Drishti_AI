import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { PlayCircle, X, ChevronDown } from 'lucide-react'
import type { AlertItem } from '../types'
import { seatColor } from '../lib/colors'
import { shortAlertSummary } from '../lib/shortSummary'

interface Props {
  alerts: AlertItem[]
  feedback: string[]
  seatIds: string[]
  onDismiss: (seatId: string) => Promise<void>
  onViewEvidence: (url: string) => void
  limit?: number
  showViewAllLink?: boolean
}

export function AlertFeed({ alerts, feedback, seatIds, onDismiss, onViewEvidence, limit, showViewAllLink }: Props) {
  const [dismissing, setDismissing] = useState<Set<string>>(new Set())
  const visible = limit ? alerts.slice(0, limit) : alerts

  const handleDismiss = async (item: AlertItem) => {
    setDismissing((prev) => new Set(prev).add(item.id))
    await onDismiss(item.seatId)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold uppercase tracking-wide">Alert feed</h2>
        {showViewAllLink && (
          <Link to="/alerts" className="text-[11px] mono" style={{ color: '#5ad1ff' }}>
            view all →
          </Link>
        )}
      </div>
      <div className="rounded-2xl border border-white/8 p-3 flex flex-col gap-2 overflow-y-auto" style={{ height: limit ? 'auto' : 560, maxHeight: 560 }}>
        {feedback.map((msg, i) => (
          <div key={`fb-${i}`} className="text-[11px] mono px-3 py-2 rounded-lg" style={{ background: '#5ad1ff14', color: '#5ad1ff' }}>
            ↺ {msg}
          </div>
        ))}
        {visible.length === 0 && feedback.length === 0 && (
          <div className="text-xs mono text-white/30 text-center py-8">Waiting for events…</div>
        )}
        <AnimatePresence initial={false}>
          {visible.map((item) => (
            <AlertCard key={item.id} item={item} seatIds={seatIds} dismissing={dismissing.has(item.id)} onDismiss={handleDismiss} onViewEvidence={onViewEvidence} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

function AlertCard({
  item,
  seatIds,
  dismissing,
  onDismiss,
  onViewEvidence,
}: {
  item: AlertItem
  seatIds: string[]
  dismissing: boolean
  onDismiss: (item: AlertItem) => void
  onViewEvidence: (url: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const isGesture = item.kind === 'gesture'
  // Gesture explanations are already short/human (behaviour/gestures.py) —
  // pass through. Risk-engine explanations get the raw-internals stripped
  // for the default line (Problem 1); full text only shows when expanded.
  const shortLine = isGesture ? item.explanation : shortAlertSummary(item.explanation)
  const hasMoreDetail = shortLine !== item.explanation

  return (
    <motion.div
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
        {isGesture ? (
          <span className="text-[9px] mono px-1.5 py-0.5 rounded" style={{ background: '#c4a3ff22', color: '#c4a3ff' }}>GESTURE</span>
        ) : (
          <span className="text-[10px] mono text-white/40">{item.timestamp.toFixed(1)}s</span>
        )}
      </div>
      {item.objectLabel && (
        <span className="text-[9px] mono px-1.5 py-0.5 rounded mr-1" style={{ background: '#ffb64822', color: '#ffb648' }}>
          {item.objectLabel.toUpperCase()} ⚠ UNVERIFIED
        </span>
      )}
      <p className="text-xs text-white/75 leading-snug mb-1">{shortLine}</p>
      {hasMoreDetail && (
        <button onClick={() => setExpanded((e) => !e)} className="flex items-center gap-1 text-[10px] mono text-white/35 hover:text-white/60 mb-2">
          <ChevronDown size={11} className={expanded ? 'rotate-180' : ''} /> {expanded ? 'hide detail' : 'full detail'}
        </button>
      )}
      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <p className="text-[10px] mono text-white/50 leading-relaxed mb-2 pb-2 border-b border-white/5">
              {item.explanation}
              {item.riskScore != null && ` · risk ${item.riskScore.toFixed(2)}`}
              {item.confidence != null && ` · confidence ${(item.confidence * 100).toFixed(0)}%`}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
      {item.confidence != null && item.confidence < 0.4 && (
        <p className="text-[10px] mono text-white/40 mb-2">⚠ low detection confidence — treat as a prompt to look, not evidence</p>
      )}
      {item.kind === 'alert' && (
        <div className="flex gap-2">
          <button
            onClick={() => onDismiss(item)}
            disabled={dismissing}
            className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/50 hover:border-white/30"
          >
            <X size={11} /> {dismissing ? 'widened ✓' : 'dismiss — false positive'}
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
  )
}
