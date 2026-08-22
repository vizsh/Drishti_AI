import { useEffect, useState } from 'react'
import { Timer } from 'lucide-react'

// Exam-phase-aware sensitivity (2026-08-23): a real, working control over
// PipelineWorker.set_exam_duration — setting a duration widens each
// seat's baseline for the real submission-rush motion spike in the last
// 10 minutes, the same mechanism a false-alarm dismissal already uses.
// Same live-apply-no-restart pattern as SensitivitySelector/
// ExamTypeSelector. Optional by design: leaving it unset simply disables
// the phase check rather than guessing a duration.
export function ExamDurationInput() {
  const [minutes, setMinutes] = useState<string>('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetch('/api/session/exam-duration')
      .then((r) => r.json())
      .then((d) => setMinutes(d.minutes != null ? String(d.minutes) : ''))
      .catch(() => {})
  }, [])

  async function save() {
    setSaving(true)
    setSaved(false)
    try {
      const value = minutes.trim() === '' ? null : Number(minutes)
      await fetch('/api/session/exam-duration', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes: value }),
      })
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-2xl border border-white/8 p-5 mb-5 max-w-lg bg-white/3">
      <h2 className="text-sm font-bold uppercase tracking-wide mb-1">Exam duration</h2>
      <p className="text-xs text-white/50 mb-4">
        Optional. Setting this widens each seat's tolerance for the last 10 minutes of the exam — the real
        submission-rush motion spike (page-flipping, gathering belongings) is legitimately elevated, not suspicious,
        and this stops it from being scored as if it were.
      </p>
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 border border-white/12 rounded-lg px-3 py-2 flex-1">
          <Timer size={13} className="text-white/35" />
          <input
            type="number"
            min={1}
            placeholder="e.g. 120 (unset = disabled)"
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            className="bg-transparent outline-none text-sm w-full placeholder:text-white/25"
          />
          <span className="text-[11px] mono text-white/30 shrink-0">minutes</span>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="text-[11px] mono uppercase px-3 py-2.5 rounded-lg border border-white/15 hover:border-white/30 text-white/70 disabled:opacity-50 shrink-0"
        >
          {saving ? 'saving…' : 'save'}
        </button>
      </div>
      {saved && <p className="text-[10px] mono text-calm mt-2">saved — applied to every running camera, no restart needed</p>}
    </div>
  )
}
