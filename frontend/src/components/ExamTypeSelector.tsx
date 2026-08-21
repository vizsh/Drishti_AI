import { useEffect, useState } from 'react'
import { CheckCircle2 } from 'lucide-react'

type ExamType = 'mixed' | 'mcq' | 'written'

const OPTIONS: { value: ExamType; label: string; body: string }[] = [
  {
    value: 'mixed',
    label: 'Mixed / Default',
    body: 'Balanced weighting across gaze, hand movement, and object detection — no exam-type assumption.',
  },
  {
    value: 'mcq',
    label: 'MCQ',
    body: 'Marking answers is brief, periodic hand motion — sustained or repeated hand movement and neighbor-directed glances weight more heavily.',
  },
  {
    value: 'written',
    label: 'Written',
    body: 'Writing is near-constant hand motion, so that signal weights less on its own — weight shifts to sustained gaze/head-turn and paper/object detection.',
  },
]

// Part G Tier 1 (2026-08-21): a real, functioning weight-profile switch —
// applies immediately to every active worker's RiskEngine (no restart), so
// changing this mid-session takes effect on the very next frame.
export function ExamTypeSelector() {
  const [current, setCurrent] = useState<ExamType>('mixed')
  const [saving, setSaving] = useState<ExamType | null>(null)

  useEffect(() => {
    fetch('/api/session/exam-type')
      .then((r) => r.json())
      .then((d) => setCurrent(d.exam_type ?? 'mixed'))
      .catch(() => {})
  }, [])

  async function select(value: ExamType) {
    setSaving(value)
    try {
      await fetch('/api/session/exam-type', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exam_type: value }),
      })
      setCurrent(value)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="rounded-2xl border border-white/8 p-5 mb-5 max-w-lg bg-white/3">
      <h2 className="text-sm font-bold uppercase tracking-wide mb-1">Exam Type</h2>
      <p className="text-xs text-white/50 mb-4">
        Applies a different signal-weighting profile to risk scoring — same detected signals, weighted for what's
        actually expected in this exam format.
      </p>
      <div className="flex flex-col gap-2">
        {OPTIONS.map((opt) => {
          const active = current === opt.value
          return (
            <button
              key={opt.value}
              onClick={() => select(opt.value)}
              disabled={saving !== null}
              className={`text-left rounded-xl border px-4 py-3 transition-colors ${
                active ? 'border-watch/40 bg-watch/8' : 'border-white/10 hover:border-white/25'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                {active && <CheckCircle2 size={13} className="text-watch shrink-0" />}
                <span className="text-sm font-semibold">{opt.label}</span>
              </div>
              <p className="text-[11px] text-white/50 leading-relaxed">{opt.body}</p>
            </button>
          )
        })}
      </div>
    </div>
  )
}
