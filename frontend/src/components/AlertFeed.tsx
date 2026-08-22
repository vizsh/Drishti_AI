import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { PlayCircle, X, ChevronDown, UserPlus, Check, ShieldAlert, MinusCircle, ShieldCheck, Eye } from 'lucide-react'
import type { AlertItem } from '../types'
import { seatColor } from '../lib/colors'
import { Badge } from './Badge'
import { EmptyState } from './EmptyState'
import { shortAlertSummary } from '../lib/shortSummary'
import { useAuth } from '../state/AuthContext'

type Resolution = 'false_alarm' | 'confirmed' | 'no_action'

interface Props {
  alerts: AlertItem[]
  feedback: string[]
  seatIds: string[]
  onDismiss: (seatId: string, resolution?: Resolution, invigilator?: string) => Promise<void>
  onDispatch?: (seatId: string, invigilator: string) => Promise<void>
  onAcknowledge?: (seatId: string, invigilator: string) => Promise<void>
  onViewEvidence: (url: string) => void
  onAlertClick?: (alert: AlertItem) => void
  limit?: number
  showViewAllLink?: boolean
}

export function AlertFeed({ alerts, feedback, seatIds, onDismiss, onDispatch, onAcknowledge, onViewEvidence, onAlertClick, limit, showViewAllLink }: Props) {
  const [resolved, setResolved] = useState<Map<string, Resolution>>(new Map())
  const [dispatched, setDispatched] = useState<Map<string, string>>(new Map())
  const [acknowledged, setAcknowledged] = useState<Map<string, string>>(new Map())
  const visible = limit ? alerts.slice(0, limit) : alerts

  const handleResolve = async (item: AlertItem, resolution: Resolution, invigilator?: string) => {
    setResolved((prev) => new Map(prev).set(item.id, resolution))
    await onDismiss(item.seatId, resolution, invigilator)
  }

  const handleDispatch = async (item: AlertItem, invigilator: string) => {
    setDispatched((prev) => new Map(prev).set(item.id, invigilator))
    if (onDispatch) await onDispatch(item.seatId, invigilator)
  }

  const handleAcknowledge = async (item: AlertItem, invigilator: string) => {
    setAcknowledged((prev) => new Map(prev).set(item.id, invigilator))
    if (onAcknowledge) await onAcknowledge(item.seatId, invigilator)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold uppercase tracking-wide">Alert feed</h2>
        {showViewAllLink && (
          <Link to="/alerts" className="text-[11px] mono text-white/50 hover:text-white/80">
            view all →
          </Link>
        )}
      </div>
      <div className="rounded-2xl border border-white/8 p-3 flex flex-col gap-2 overflow-y-auto" style={{ height: limit ? 'auto' : 560, maxHeight: 560 }}>
        {feedback.map((msg, i) => (
          <div key={`fb-${i}`} className="text-[11px] mono px-3 py-2 rounded-lg bg-white/5 text-white/60">
            ↺ {msg}
          </div>
        ))}
        {visible.length === 0 && feedback.length === 0 && (
          <EmptyState
            icon={ShieldCheck}
            title="All calm — no alerts yet"
            body="Nothing has crossed a student's own baseline deviation threshold this session. This feed updates in real time as soon as something does."
          />
        )}
        <AnimatePresence initial={false}>
          {visible.map((item) => (
            <AlertCard
              key={item.id}
              item={item}
              seatIds={seatIds}
              resolution={resolved.get(item.id) ?? null}
              dispatchedTo={dispatched.get(item.id) ?? null}
              acknowledgedBy={acknowledged.get(item.id) ?? null}
              onResolve={handleResolve}
              onDispatch={handleDispatch}
              onAcknowledge={handleAcknowledge}
              onViewEvidence={onViewEvidence}
              onAlertClick={onAlertClick}
            />
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

function AlertCard({
  item,
  seatIds,
  resolution,
  dispatchedTo,
  acknowledgedBy,
  onResolve,
  onDispatch,
  onAcknowledge,
  onViewEvidence,
  onAlertClick,
}: {
  item: AlertItem
  seatIds: string[]
  resolution: Resolution | null
  dispatchedTo: string | null
  acknowledgedBy: string | null
  onResolve: (item: AlertItem, resolution: Resolution, invigilator?: string) => void
  onDispatch: (item: AlertItem, invigilator: string) => void
  onAcknowledge: (item: AlertItem, invigilator: string) => void
  onViewEvidence: (url: string) => void
  onAlertClick?: (alert: AlertItem) => void
}) {
  const { user } = useAuth()
  const [expanded, setExpanded] = useState(false)
  const isGesture = item.kind === 'gesture'
  const isCalibrationWarning = item.kind === 'calibration_warning'
  // Gesture/calibration-warning explanations are already short/human
  // (behaviour/gestures.py) — pass through. Risk-engine explanations get
  // the raw-internals stripped for the default line (Problem 1); full text
  // only shows when expanded.
  const shortLine = isGesture || isCalibrationWarning ? item.explanation : shortAlertSummary(item.explanation)
  const hasMoreDetail = shortLine !== item.explanation

  // Only the alert card's own accent varies by meaning — critical for a
  // real risk alert, watch for a calibration-issue signal (it's a "pay
  // attention" system message, not a student accusation), and a quiet
  // neutral treatment for a gesture note. Everything else in this card is
  // neutral chrome.
  const borderColor = isCalibrationWarning ? '#ffb64840' : item.kind === 'alert' ? '#ff5a3640' : '#ffffff1a'
  const bgColor = isCalibrationWarning ? '#ffb6480c' : item.kind === 'alert' ? '#ff5a360c' : 'transparent'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className={`rounded-xl p-3 border ${onAlertClick ? 'cursor-pointer hover:border-white/25 transition-colors' : ''}`}
      style={{ borderColor, background: bgColor }}
      onClick={onAlertClick ? () => onAlertClick(item) : undefined}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-bold" style={{ color: seatColor(item.seatId, seatIds) }}>
          {item.seatId.toUpperCase()}
        </span>
        {isCalibrationWarning ? (
          <Badge tone="watch">Calibration</Badge>
        ) : isGesture ? (
          <Badge tone="neutral">Gesture</Badge>
        ) : (
          <div className="flex items-center gap-1.5">
            {item.occurrence != null && item.occurrence > 1 && (
              <span className="text-[10px] mono text-white/40">#{item.occurrence} this session</span>
            )}
            <span className="text-[10px] mono text-white/40">{item.timestamp.toFixed(1)}s</span>
          </div>
        )}
      </div>
      {item.objectLabel && (
        <div className="mb-1 flex flex-wrap gap-1.5">
          <Badge tone="watch">{item.objectLabel} — unverified</Badge>
          {item.needsVerification && (
            <Badge tone="neutral">moderate confidence — please verify visually</Badge>
          )}
        </div>
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
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            {item.evidenceUrl && (
              <button
                onClick={() => onViewEvidence(item.evidenceUrl!)}
                className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/60 hover:border-white/30"
              >
                <PlayCircle size={11} /> view evidence
              </button>
            )}
            {!dispatchedTo && !resolution && (
              <button
                onClick={() => onDispatch(item, user?.name ?? 'unknown')}
                className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/50 hover:border-white/30"
              >
                <UserPlus size={11} /> dispatch invigilator
              </button>
            )}
            {/* Acknowledge: a lightweight "seen, noted" for a minor item —
                distinct from Dispatch, doesn't require a resolution pick,
                and the alert stays open in case it later needs one. */}
            {!acknowledgedBy && !resolution && (
              <button
                onClick={() => onAcknowledge(item, user?.name ?? 'unknown')}
                className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/50 hover:border-white/30"
              >
                <Eye size={11} /> acknowledge
              </button>
            )}
          </div>

          {dispatchedTo && !resolution && (
            <p className="text-[10px] mono text-white/40">↳ dispatched to {dispatchedTo}</p>
          )}
          {acknowledgedBy && !resolution && (
            <p className="flex items-center gap-1 text-[10px] mono text-white/40">
              <Eye size={11} /> acknowledged by {acknowledgedBy}
            </p>
          )}

          {!resolution && (
            <div className="flex flex-wrap gap-2">
              <span className="text-[10px] mono text-white/35 self-center">resolve:</span>
              <button
                onClick={() => onResolve(item, 'false_alarm', dispatchedTo ?? undefined)}
                className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/50 hover:border-white/30"
              >
                <X size={11} /> false alarm
              </button>
              <button
                onClick={() => onResolve(item, 'confirmed', dispatchedTo ?? undefined)}
                className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border"
                style={{ borderColor: '#ff5a3640', color: '#ff5a36' }}
              >
                <ShieldAlert size={11} /> confirmed issue
              </button>
              <button
                onClick={() => onResolve(item, 'no_action', dispatchedTo ?? undefined)}
                className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/50 hover:border-white/30"
              >
                <MinusCircle size={11} /> no action
              </button>
            </div>
          )}

          {resolution && (
            <p className="flex items-center gap-1 text-[10px] mono" style={{ color: resolution === 'confirmed' ? '#ff5a36' : '#8dff9e' }}>
              <Check size={11} />
              {resolution === 'false_alarm' && 'resolved — false alarm (baseline widened)'}
              {resolution === 'confirmed' && 'resolved — confirmed issue'}
              {resolution === 'no_action' && 'resolved — no action taken'}
            </p>
          )}
        </div>
      )}
    </motion.div>
  )
}
