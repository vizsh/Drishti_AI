/**
 * Action Drawer — the guided escalation panel from the product redesign
 * proposal §3 Step 3. Slides in from the right when an alert is selected,
 * guiding the invigilator through:
 *   1. System Assessment (what happened)
 *   2. Visual Verification (evidence playback)
 *   3. Action Protocol (acknowledge / warn / escalate)
 *   4. Invigilator Notes (free-text incident notes)
 */
import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  X,
  ShieldAlert,
  PlayCircle,
  Eye,
  UserPlus,
  CheckCircle2,
  AlertTriangle,
  MinusCircle,
  Send,
  Gavel,
  ThumbsUp,
  ThumbsDown,
} from 'lucide-react'
import type { AlertItem } from '../types'
import { humanizeConfidence, formatAlertTime } from '../lib/humanize'
import { shortAlertSummary } from '../lib/shortSummary'
import { useAuth } from '../state/AuthContext'

type Resolution = 'false_alarm' | 'confirmed' | 'no_action'

interface Props {
  alert: AlertItem | null
  onClose: () => void
  onDismiss: (
    seatId: string,
    resolution: Resolution,
    invigilator?: string,
    signal?: { signalType: string; objectLabel?: string; confidence?: number }
  ) => Promise<void>
  onDispatch?: (seatId: string, invigilator: string) => Promise<void>
  onAcknowledge?: (seatId: string, invigilator: string) => Promise<void>
  onViewEvidence: (url: string) => void
}

export function ActionDrawer({ alert, onClose, onDismiss, onDispatch, onAcknowledge, onViewEvidence }: Props) {
  const { user } = useAuth()
  const [notes, setNotes] = useState('')
  const [resolved, setResolved] = useState<Resolution | null>(null)
  const [dispatched, setDispatched] = useState(false)
  const [acknowledged, setAcknowledged] = useState(false)
  const [step, setStep] = useState(1)

  // Reset state when a new alert is opened
  const [lastAlertId, setLastAlertId] = useState<string | null>(null)
  if (alert && alert.id !== lastAlertId) {
    setLastAlertId(alert.id)
    setNotes('')
    setResolved(null)
    setDispatched(false)
    setAcknowledged(false)
    setStep(1)
  }

  const handleResolve = async (resolution: Resolution) => {
    if (!alert) return
    setResolved(resolution)
    const signalType = alert.kind === 'gesture' ? 'gesture' : alert.kind === 'calibration_warning' ? 'calibration' : alert.objectLabel ? 'object' : 'behavioral'
    await onDismiss(alert.seatId, resolution, user?.name, {
      signalType,
      objectLabel: alert.objectLabel ?? undefined,
      confidence: alert.confidence,
    })
  }

  const handleDispatch = async () => {
    if (!alert || !onDispatch) return
    setDispatched(true)
    await onDispatch(alert.seatId, user?.name ?? 'unknown')
  }

  const handleAcknowledge = async () => {
    if (!alert || !onAcknowledge) return
    setAcknowledged(true)
    await onAcknowledge(alert.seatId, user?.name ?? 'unknown')
  }

  const conf = alert ? humanizeConfidence(alert.confidence ?? null) : null

  return (
    <AnimatePresence>
      {alert && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] bg-black/50 backdrop-blur-sm"
            onClick={onClose}
          />
          {/* Drawer */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 z-[90] w-full max-w-[480px] border-l border-white/10 overflow-y-auto"
            style={{ background: '#0c0c10' }}
          >
            {/* Header */}
            <div className="sticky top-0 z-10 px-6 py-4 border-b border-white/8 flex items-center justify-between"
              style={{ background: '#0c0c10ee', backdropFilter: 'blur(12px)' }}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: alert.kind === 'alert' ? '#ff5a3618' : '#ffffff10' }}
                >
                  <ShieldAlert size={18} color={alert.kind === 'alert' ? '#ff5a36' : '#8b8578'} />
                </div>
                <div>
                  <div className="text-sm font-bold">{alert.seatId.replace('_', ' ').toUpperCase()}</div>
                  <div className="text-[10px] mono text-white/40">{formatAlertTime(alert.timestamp)}</div>
                </div>
              </div>
              <button onClick={onClose} className="text-white/40 hover:text-white p-2 rounded-lg hover:bg-white/5">
                <X size={18} />
              </button>
            </div>

            <div className="px-6 py-5 flex flex-col gap-5">
              {/* Step 1: System Assessment */}
              <DrawerSection
                number={1}
                title="System Assessment"
                subtitle="What happened"
                active={step >= 1}
                onClick={() => setStep(1)}
              >
                <p className="text-sm text-white/80 leading-relaxed">
                  {shortAlertSummary(alert.explanation)}
                </p>
                {alert.explanation !== shortAlertSummary(alert.explanation) && (
                  <details className="mt-2">
                    <summary className="text-[10px] mono text-white/35 cursor-pointer hover:text-white/50">
                      Technical detail
                    </summary>
                    <p className="text-[11px] mono text-white/40 leading-relaxed mt-1.5 pl-3 border-l-2 border-white/8">
                      {alert.explanation}
                    </p>
                  </details>
                )}
                {alert.objectLabel && (
                  <div className="mt-2 flex items-center gap-2 px-3 py-2 rounded-lg bg-watch/10 border border-watch/20">
                    <AlertTriangle size={13} className="text-watch shrink-0" />
                    <span className="text-xs text-watch">{alert.objectLabel} detected — unverified</span>
                  </div>
                )}
                {((alert.prosecution?.length ?? 0) > 0 || (alert.defense?.length ?? 0) > 0) && (
                  <div className="mt-3 pt-3 border-t border-white/8">
                    <div className="flex items-center gap-1.5 mb-2 text-[10px] mono uppercase tracking-wide text-white/40">
                      <Gavel size={11} /> Evidence checklist — both sides, before this alert fired
                    </div>
                    {alert.prosecution && alert.prosecution.length > 0 && (
                      <div className="mb-2">
                        <div className="text-[10px] mono text-calm/80 mb-1">Corroborating (for)</div>
                        <div className="flex flex-col gap-1">
                          {alert.prosecution.map((f, i) => (
                            <div key={i} className="flex items-start gap-1.5 text-[11px] text-white/70">
                              <ThumbsUp size={11} className="text-calm shrink-0 mt-0.5" />
                              <div>
                                <div>{f.label}</div>
                                <div className="text-[10px] mono text-white/35">{f.detail}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {alert.defense && alert.defense.length > 0 && (
                      <div>
                        <div className="text-[10px] mono text-white/40 mb-1">Counter-evidence considered (not disqualifying here)</div>
                        <div className="flex flex-col gap-1">
                          {alert.defense.map((f, i) => (
                            <div key={i} className="flex items-start gap-1.5 text-[11px] text-white/60">
                              <ThumbsDown size={11} className="text-white/40 shrink-0 mt-0.5" />
                              <div>
                                <div>{f.label}</div>
                                <div className="text-[10px] mono text-white/35">{f.detail}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
                <div className="flex gap-3 mt-3">
                  {conf && (
                    <div className="text-[10px] mono px-2.5 py-1 rounded-full border border-white/10 text-white/50">
                      Visibility: {conf.label}
                    </div>
                  )}
                  {alert.riskScore != null && (
                    <div className="text-[10px] mono px-2.5 py-1 rounded-full border border-white/10 text-white/50">
                      Risk: {(alert.riskScore * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              </DrawerSection>

              {/* Step 2: Visual Verification */}
              {alert.evidenceUrl && (
                <DrawerSection
                  number={2}
                  title="Visual Verification"
                  subtitle="Review the evidence clip"
                  active={step >= 2}
                  onClick={() => setStep(2)}
                >
                  <button
                    onClick={() => onViewEvidence(alert.evidenceUrl!)}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-white/12 text-sm text-white/70 hover:border-white/25 hover:text-white transition-colors"
                  >
                    <PlayCircle size={18} />
                    Play evidence clip (face-blurred)
                  </button>
                  <p className="text-[10px] mono text-white/30 mt-2 text-center">
                    All faces are automatically blurred for privacy compliance
                  </p>
                </DrawerSection>
              )}

              {/* Step 3: Action Protocol */}
              <DrawerSection
                number={alert.evidenceUrl ? 3 : 2}
                title="Action Protocol"
                subtitle="Choose your response"
                active={step >= (alert.evidenceUrl ? 3 : 2)}
                onClick={() => setStep(alert.evidenceUrl ? 3 : 2)}
              >
                {resolved ? (
                  <div className="flex items-center gap-2 px-4 py-3 rounded-xl border"
                    style={{
                      borderColor: resolved === 'confirmed' ? '#ff5a3640' : '#8dff9e40',
                      background: resolved === 'confirmed' ? '#ff5a360a' : '#8dff9e0a',
                    }}
                  >
                    <CheckCircle2 size={16} color={resolved === 'confirmed' ? '#ff5a36' : '#8dff9e'} />
                    <span className="text-sm" style={{ color: resolved === 'confirmed' ? '#ff5a36' : '#8dff9e' }}>
                      {resolved === 'false_alarm' && 'Resolved — natural behavior (baseline widened)'}
                      {resolved === 'confirmed' && 'Resolved — confirmed issue'}
                      {resolved === 'no_action' && 'Resolved — no action taken'}
                    </span>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {!acknowledged && (
                      <ActionButton
                        icon={Eye}
                        label="Acknowledge & Mute"
                        sublabel="Natural behavior — no concern"
                        onClick={handleAcknowledge}
                        color="#8dff9e"
                      />
                    )}
                    {acknowledged && (
                      <div className="text-[11px] mono text-white/40 px-3 py-2 rounded-lg bg-white/5">
                        ✓ Acknowledged by {user?.name}
                      </div>
                    )}
                    {!dispatched && (
                      <ActionButton
                        icon={UserPlus}
                        label="Dispatch Invigilator"
                        sublabel="Send someone to verify in person"
                        onClick={handleDispatch}
                        color="#ffb648"
                      />
                    )}
                    {dispatched && (
                      <div className="text-[11px] mono text-white/40 px-3 py-2 rounded-lg bg-white/5">
                        ↳ Dispatched to {user?.name}
                      </div>
                    )}
                    <div className="h-px bg-white/8 my-1" />
                    <span className="text-[10px] mono text-white/30 uppercase tracking-wider">Resolve:</span>
                    <ActionButton
                      icon={X}
                      label="False Alarm"
                      sublabel="It was a natural stretch — widen baseline"
                      onClick={() => handleResolve('false_alarm')}
                    />
                    <ActionButton
                      icon={ShieldAlert}
                      label="Confirmed Issue"
                      sublabel="Flag for disciplinary review"
                      onClick={() => handleResolve('confirmed')}
                      color="#ff5a36"
                      variant="danger"
                    />
                    <ActionButton
                      icon={MinusCircle}
                      label="No Action Needed"
                      sublabel="Noted but not actionable"
                      onClick={() => handleResolve('no_action')}
                    />
                  </div>
                )}
              </DrawerSection>

              {/* Step 4: Invigilator Notes */}
              <DrawerSection
                number={alert.evidenceUrl ? 4 : 3}
                title="Invigilator Notes"
                subtitle="Record incident details"
                active={true}
                onClick={() => {}}
              >
                <div className="relative">
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Describe what you observed. E.g., 'Student was reaching for a calculator from the adjacent desk. Verbal warning given.'"
                    className="w-full h-28 px-4 py-3 rounded-xl border border-white/12 bg-white/[0.03] text-sm text-white/80 placeholder:text-white/25 resize-none focus:outline-none focus:border-white/25 transition-colors"
                  />
                  {notes.trim() && (
                    <button
                      className="absolute bottom-3 right-3 flex items-center gap-1.5 text-[11px] mono px-3 py-1.5 rounded-lg bg-white/10 text-white/60 hover:bg-white/15 hover:text-white transition-colors"
                    >
                      <Send size={11} /> Save note
                    </button>
                  )}
                </div>
                <p className="text-[10px] mono text-white/25 mt-1.5">
                  Notes are stored in the session audit log alongside the system assessment
                </p>
              </DrawerSection>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

function DrawerSection({
  number,
  title,
  subtitle,
  active,
  onClick,
  children,
}: {
  number: number
  title: string
  subtitle: string
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <div
      className={`rounded-2xl border p-4 transition-colors cursor-pointer ${
        active ? 'border-white/12 bg-white/[0.02]' : 'border-white/6 opacity-60'
      }`}
      onClick={onClick}
    >
      <div className="flex items-center gap-3 mb-3">
        <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold bg-white/10 text-white/50 shrink-0">
          {number}
        </div>
        <div>
          <div className="text-xs font-bold">{title}</div>
          <div className="text-[10px] mono text-white/35">{subtitle}</div>
        </div>
      </div>
      {active && <div className="pl-9">{children}</div>}
    </div>
  )
}

function ActionButton({
  icon: Icon,
  label,
  sublabel,
  onClick,
  color,
  variant,
}: {
  icon: typeof Eye
  label: string
  sublabel: string
  onClick: () => void
  color?: string
  variant?: 'danger'
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className="w-full flex items-start gap-3 px-4 py-3 rounded-xl border text-left transition-all hover:border-white/25 group"
      style={{
        borderColor: variant === 'danger' ? '#ff5a3630' : '#ffffff12',
        background: variant === 'danger' ? '#ff5a360a' : undefined,
      }}
    >
      <Icon size={16} color={color ?? '#ffffff80'} className="shrink-0 mt-0.5" />
      <div>
        <div className="text-sm font-medium" style={{ color: color ?? '#ffffffcc' }}>{label}</div>
        <div className="text-[10px] mono text-white/35 group-hover:text-white/45">{sublabel}</div>
      </div>
    </button>
  )
}
