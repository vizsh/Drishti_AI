import { Info } from 'lucide-react'

// Product audit (2026-08-22): reference pattern (KEYFRAME mockup) — a
// persistent, quiet reminder of the system's actual explainability
// contract, visible on every screen rather than buried in the Trust &
// Compliance page. Reinforces exactly what risk_engine/adjudication.py
// already guarantees: an alert is a measured observation, not a verdict,
// and the checklist behind it is inspectable, never hidden reasoning.
export function DisclosureBanner() {
  return (
    <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl border border-white/8 bg-white/3 mb-5 text-[11px] text-white/50 leading-relaxed">
      <Info size={13} className="text-white/35 shrink-0" />
      <span>
        Alerts describe <b className="text-white/75 font-semibold">observed behaviour</b>, not conclusions — every
        flag carries the real evidence behind it and needs invigilator confirmation before it means anything.
      </span>
    </div>
  )
}
