import { Link } from 'react-router-dom'
import { ArrowLeft, ShieldCheck, EyeOff, ScrollText, Database, AlertCircle } from 'lucide-react'

// A real, reachable page (from Settings) stating plainly what already
// exists in the backend — not a marketing page. Every claim here traces to
// specific code: ingestion/video_source.py, backend/evidence.py,
// backend/db.py. Where something ISN'T implemented (retention policy),
// this says so rather than implying it.
export function TrustCompliancePage() {
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
        <ComplianceCard
          icon={Database}
          title="Data retention"
          body="This system currently keeps all session data — event logs and evidence clips — indefinitely; there is no automatic deletion after a fixed period. An institution deploying this system should set its own retention period (e.g., delete evidence after the exam's appeal window closes) as a matter of policy and operational configuration. That retention policy is not yet enforced by the software itself."
          warn
        />
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
  warn,
}: {
  icon: typeof ShieldCheck
  title: string
  body: string
  warn?: boolean
}) {
  return (
    <div className="rounded-2xl border border-white/8 p-5 bg-white/3">
      <div className="flex items-center gap-2.5 mb-2">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${warn ? 'bg-watch/15' : 'bg-calm/15'}`}>
          <Icon size={15} className={warn ? 'text-watch' : 'text-calm'} />
        </div>
        <h2 className="text-sm font-bold">{title}</h2>
      </div>
      <p className="text-xs text-white/60 leading-relaxed">{body}</p>
    </div>
  )
}
