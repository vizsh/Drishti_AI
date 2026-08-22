import { useEffect, useState } from 'react'
import { CheckCircle2 } from 'lucide-react'

type Sensitivity = 'strict' | 'balanced' | 'sensitive'

const OPTIONS: { value: Sensitivity; label: string; body: string }[] = [
  {
    value: 'strict',
    label: 'Strict — sustained pattern only',
    body: 'Single glances and brief stretches are absorbed into baseline and never reach the inbox. Matches the thresholds this project verified against real ground-truth footage — the calmest, most defensible default.',
  },
  {
    value: 'balanced',
    label: 'Balanced',
    body: 'Moderate-confidence detections are flagged for review a bit more readily, and repeat notifications for the same seat come a little sooner.',
  },
  {
    value: 'sensitive',
    label: 'Sensitive — flag more, verify more',
    body: 'Lower confidence bar and shorter cooldowns — catches more borderline activity, at the cost of more items landing in "needs your review" that turn out to be nothing.',
  },
]

// Product audit (2026-08-22): a real, working control over the exact
// thresholds risk_engine/scorer.py's needs_verification tier and
// backend/pipeline_worker.py's notify-cooldowns already enforce --
// SENSITIVITY_PRESETS in pipeline_worker.py, not a cosmetic slider. Same
// live-apply-no-restart pattern as ExamTypeSelector.
export function SensitivitySelector() {
  const [current, setCurrent] = useState<Sensitivity>('strict')
  const [saving, setSaving] = useState<Sensitivity | null>(null)

  useEffect(() => {
    fetch('/api/session/sensitivity')
      .then((r) => r.json())
      .then((d) => setCurrent(d.level ?? 'strict'))
      .catch(() => {})
  }, [])

  async function select(value: Sensitivity) {
    setSaving(value)
    try {
      await fetch('/api/session/sensitivity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level: value }),
      })
      setCurrent(value)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="rounded-2xl border border-white/8 p-5 mb-5 max-w-lg bg-white/3">
      <h2 className="text-sm font-bold uppercase tracking-wide mb-1">Alert sensitivity</h2>
      <p className="text-xs text-white/50 mb-4">
        Controls the confidence bar for a real, working needs-review threshold and how soon a repeating pattern can
        interrupt an invigilator again — not a cosmetic setting.
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
