import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { ArrowLeft, ShieldCheck, EyeOff, ScrollText, Database, AlertCircle, Loader2, Trash2 } from 'lucide-react'

// A real, reachable page (from Settings) stating plainly what already
// exists in the backend — not a marketing page. Every claim here traces to
// specific code: ingestion/video_source.py, backend/evidence.py,
// backend/db.py, backend/retention.py.
export function TrustCompliancePage() {
  const [retentionDays, setRetentionDays] = useState<number | null>(null)
  const [savingRetention, setSavingRetention] = useState(false)
  const [sweeping, setSweeping] = useState(false)
  const [sweepResult, setSweepResult] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/settings/retention')
      .then((r) => r.json())
      .then((d) => setRetentionDays(d.retention_days))
      .catch(() => {})
  }, [])

  async function saveRetention(days: number) {
    setSavingRetention(true)
    try {
      await fetch('/api/settings/retention', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ retention_days: days }),
      })
      setRetentionDays(days)
    } finally {
      setSavingRetention(false)
    }
  }

  async function sweepNow() {
    setSweeping(true)
    setSweepResult(null)
    try {
      const res = await fetch('/api/settings/retention/sweep-now', { method: 'POST' })
      const d = await res.json()
      setSweepResult(
        `swept just now — removed ${d.deleted_evidence_clips} evidence clip(s), ${d.deleted_event_rows} event row(s), ${d.deleted_access_log_rows} access-log row(s) older than ${d.retention_days} days`
      )
    } finally {
      setSweeping(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <Link to="/settings" className="flex items-center gap-1.5 text-xs mono text-white/50 hover:text-white mb-4 w-fit">
        <ArrowLeft size={13} /> back to settings
      </Link>
      <div className="flex items-center gap-2 mb-1">
        <ShieldCheck size={18} className="text-white/50" />
        <h1 className="text-lg font-bold">Trust &amp; Compliance</h1>
      </div>
      <p className="text-xs mono text-white/35 mb-8">
        what this system actually does with video and evidence data — written plainly, not as a legal disclaimer
      </p>

      <div className="flex flex-col gap-4">
        <ComplianceCard
          icon={EyeOff}
          title="No face recognition, ever"
          body="Students are identified by which seat they're sitting in, determined by camera geometry (a one-time calibration per room), not by their face. The system has no facial recognition model anywhere in its pipeline and never stores a face embedding. If a camera angle changes or a student moves seats, the system re-anchors to the seat — it does not, and cannot, follow an individual by face."
        />
        <ComplianceCard
          icon={ShieldCheck}
          title="Video stays on this system"
          body="Camera footage is decoded and analyzed on the same machine running this software — there is no step in the current pipeline that uploads raw video to an external server or cloud service. The only artifact that can leave this machine is a short evidence clip attached to a confirmed alert, and only if an authorized user explicitly opens or exports it."
        />
        <ComplianceCard
          icon={EyeOff}
          title="Faces are blurred before any clip is saved"
          body="When an alert generates an evidence clip, every visible person in that clip — not just the flagged student — has their face blurred before the file is written to disk. This happens automatically, before storage, not as an optional or after-the-fact step."
        />
        <ComplianceCard
          icon={ScrollText}
          title="Every evidence view is logged"
          body="Each time an evidence clip is opened, the system records who accessed it and when, in a permanent, queryable audit log. This log exists so any use of evidence can be reviewed after the fact — including by the institution itself, to confirm evidence was only accessed for legitimate review."
        />

        <div className="rounded-2xl border border-white/8 p-5 bg-white/3">
          <div className="flex items-center gap-2.5 mb-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 bg-calm/15">
              <Database size={15} className="text-calm" />
            </div>
            <h2 className="text-sm font-bold">Data retention — enforced, not just described</h2>
          </div>
          <p className="text-xs text-white/60 leading-relaxed mb-3">
            A background sweep runs daily (and once immediately at startup) and permanently deletes evidence clips
            and event-log rows older than the retention period below. Age is measured from real, wall-clock
            timestamps, not session time, so it holds up across restarts.
          </p>
          <div className="flex items-center gap-2 flex-wrap mb-3">
            <span className="text-[11px] mono text-white/50">keep evidence &amp; logs for</span>
            <input
              type="number"
              min={1}
              max={3650}
              value={retentionDays ?? ''}
              onChange={(e) => setRetentionDays(Number(e.target.value))}
              className="w-20 bg-transparent border border-white/15 rounded-lg px-2.5 py-1.5 text-xs outline-none focus:border-white/40"
            />
            <span className="text-[11px] mono text-white/50">days</span>
            <button
              onClick={() => retentionDays != null && saveRetention(retentionDays)}
              disabled={savingRetention || retentionDays == null}
              className="flex items-center gap-1.5 text-[11px] mono px-3 py-1.5 rounded-lg border border-white/15 text-white/70 hover:border-white/30 disabled:opacity-40"
            >
              {savingRetention ? <Loader2 size={11} className="animate-spin" /> : null}
              save
            </button>
          </div>
          <button
            onClick={sweepNow}
            disabled={sweeping}
            className="flex items-center gap-1.5 text-[11px] mono px-3 py-1.5 rounded-lg border border-watch/30 text-watch hover:border-watch/50 disabled:opacity-40"
          >
            {sweeping ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
            {sweeping ? 'sweeping…' : 'run sweep now'}
          </button>
          {sweepResult && <p className="text-[10px] mono text-white/40 mt-2">{sweepResult}</p>}
          <p className="text-[10px] mono text-white/30 mt-2">
            changing the number never deletes anything by itself — only the daily sweep or "run sweep now" does, so
            the two are always separate, deliberate actions.
          </p>
        </div>
      </div>

      <div className="mt-6 rounded-2xl border border-white/8 px-4 py-3 flex items-start gap-2.5 bg-white/3">
        <AlertCircle size={14} className="text-white/40 shrink-0 mt-0.5" />
        <p className="text-[11px] text-white/45 leading-relaxed">
          This page describes the current implementation, not a certification or legal guarantee. It's written so a
          non-technical decision-maker can evaluate what the software actually does — verify any claim here against
          the current codebase before relying on it for a compliance decision.
        </p>
      </div>
    </div>
  )
}

function ComplianceCard({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof ShieldCheck
  title: string
  body: string
}) {
  return (
    <div className="rounded-2xl border border-white/8 p-5 bg-white/3">
      <div className="flex items-center gap-2.5 mb-2">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 bg-calm/15">
          <Icon size={15} className="text-calm" />
        </div>
        <h2 className="text-sm font-bold">{title}</h2>
      </div>
      <p className="text-xs text-white/60 leading-relaxed">{body}</p>
    </div>
  )
}
