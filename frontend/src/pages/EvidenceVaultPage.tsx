import { useEffect, useMemo, useState } from 'react'
import { FolderOpen, ShieldCheck, ShieldAlert, MinusCircle, Clock, Database } from 'lucide-react'
import { EvidenceModal } from '../components/EvidenceModal'
import { EmptyState } from '../components/EmptyState'
import { useHallScope } from '../state/useHallScope'
import { seatColor, STATUS_COLOR } from '../lib/colors'

interface ClipRow {
  id: number
  seat_id: string
  sim_time: number
  explanation: string | null
  evidence_url: string | null
  risk_score: number | null
  confidence: number | null
  object_label: string | null
  resolution: 'confirmed' | 'false_alarm' | 'no_action' | null
}

interface VaultSummary {
  total_clips: number
  reviewed_count: number
  confirmed_count: number
  false_alarm_count: number
  no_action_count: number
  avg_confidence: number | null
  training_labels_count: number
}

const RESOLUTION_META: Record<string, { label: string; color: string; icon: typeof ShieldCheck }> = {
  confirmed: { label: 'confirmed issue', color: STATUS_COLOR.critical, icon: ShieldAlert },
  false_alarm: { label: 'false alarm', color: STATUS_COLOR.calm, icon: ShieldCheck },
  no_action: { label: 'no action taken', color: '#8b8578', icon: MinusCircle },
}

// Evidence Vault redesign (2026-08-23): was one flat, unfiltered grid of
// every clip — no grouping, no resolution status, no sense of whether the
// system's calls were actually right. Grouped by camera/hall (confirmed
// choice) with each clip's REAL resolution status as a badge (matched
// server-side from the FeedbackLabel table, see backend/db.py's
// evidence_vault_data), plus a real-numbers summary panel — the same
// "prove it, don't just claim it" standard every other accuracy feature
// this session built already follows.
export function EvidenceVaultPage() {
  const { isSeatInScope, scopedSeatIds, cameras } = useHallScope()
  const [clips, setClips] = useState<ClipRow[]>([])
  const [summary, setSummary] = useState<VaultSummary | null>(null)
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)

  const scopeKey = [...scopedSeatIds].sort().join(',')

  useEffect(() => {
    const params = scopeKey ? `?seat_ids=${scopeKey}` : ''
    fetch(`/api/evidence-vault${params}`)
      .then((r) => r.json())
      .then((d) => {
        setClips(d.clips.filter((c: ClipRow) => c.evidence_url && isSeatInScope(c.seat_id)))
        setSummary(d.summary)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey])

  const seatIds = [...scopedSeatIds]

  // Group clips by camera (the confirmed grouping), falling back to an
  // "other seats" bucket for any seat not covered by a camera currently in
  // scope (e.g. after a config change) rather than silently dropping clips.
  const groups = useMemo(() => {
    const seatToCamera = new Map<string, { camera_id: string; hall: string }>()
    for (const cam of cameras) {
      for (const s of cam.seats) seatToCamera.set(s, { camera_id: cam.camera_id, hall: cam.hall })
    }
    const byCamera = new Map<string, { camera_id: string; hall: string; clips: ClipRow[] }>()
    for (const clip of clips) {
      const cam = seatToCamera.get(clip.seat_id) ?? { camera_id: 'other seats', hall: 'Unassigned' }
      const key = cam.camera_id
      if (!byCamera.has(key)) byCamera.set(key, { ...cam, clips: [] })
      byCamera.get(key)!.clips.push(clip)
    }
    return [...byCamera.values()].sort((a, b) => a.hall.localeCompare(b.hall) || a.camera_id.localeCompare(b.camera_id))
  }, [clips, cameras])

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <FolderOpen size={16} className="text-white/40" />
        <h1 className="text-lg font-bold">Evidence Vault</h1>
      </div>
      <p className="text-xs mono text-white/35 mb-6">
        face-blurred clips for every confirmed alert, grouped by camera · every view is logged for audit purposes
      </p>

      {summary && summary.total_clips > 0 && (
        <div className="rounded-2xl border border-white/8 p-4 mb-6 bg-white/3">
          <div className="flex items-center gap-2 mb-3">
            <Database size={13} className="text-white/40" />
            <h2 className="text-[11px] mono uppercase tracking-widest text-white/40">vault summary — real numbers, not simulated</h2>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <SummaryStat label="clips captured" value={summary.total_clips} />
            <SummaryStat
              label="reviewed"
              value={summary.total_clips ? `${Math.round((summary.reviewed_count / summary.total_clips) * 100)}%` : '—'}
              sublabel={`${summary.reviewed_count}/${summary.total_clips}`}
            />
            <SummaryStat
              label="confirmed / false alarm"
              value={`${summary.confirmed_count} / ${summary.false_alarm_count}`}
              color={summary.confirmed_count > 0 ? STATUS_COLOR.critical : undefined}
            />
            <SummaryStat
              label="avg confidence"
              value={summary.avg_confidence != null ? summary.avg_confidence.toFixed(2) : '—'}
            />
            <SummaryStat label="training labels collected" value={summary.training_labels_count} color={STATUS_COLOR.calm} />
          </div>
        </div>
      )}

      {clips.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="No evidence clips yet"
          body="A clip is generated automatically the first time an alert fires — faces blurred, before it's ever stored. Nothing has triggered one yet this session."
        />
      ) : (
        groups.map((group) => (
          <div key={group.camera_id} className="mb-8">
            <div className="flex items-center gap-2 mb-3">
              <h2 className="text-xs font-bold uppercase tracking-wide text-white/60">
                {group.hall} &middot; {group.camera_id}
              </h2>
              <span className="text-[10px] mono text-white/30">{group.clips.length} clip{group.clips.length === 1 ? '' : 's'}</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {group.clips.map((e) => {
                const meta = e.resolution ? RESOLUTION_META[e.resolution] : null
                const Icon = meta?.icon ?? Clock
                return (
                  <button
                    key={e.id}
                    onClick={() => setEvidenceUrl(e.evidence_url)}
                    className="rounded-2xl border border-white/8 p-4 text-left hover:border-white/25 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold" style={{ color: seatColor(e.seat_id, seatIds) }}>
                        {e.seat_id.toUpperCase()}
                      </span>
                      <span className="text-[10px] mono text-white/35">{e.sim_time.toFixed(1)}s</span>
                    </div>
                    <p className="text-[11px] text-white/60 leading-snug mb-2 line-clamp-3">{e.explanation}</p>
                    <div
                      className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md mb-2 w-fit"
                      style={{ background: `${meta?.color ?? '#ffffff'}18`, color: meta?.color ?? '#ffffff60' }}
                    >
                      <Icon size={10} /> {meta?.label ?? 'awaiting review'}
                    </div>
                    <div className="flex items-center justify-between text-[10px] mono text-white/30">
                      <span>risk {e.risk_score?.toFixed(2) ?? '—'}</span>
                      <span className="text-white/50">&#9654; view clip</span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        ))
      )}
      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
    </div>
  )
}

function SummaryStat({ label, value, sublabel, color }: { label: string; value: string | number; sublabel?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-white/6 px-3 py-2.5">
      <div className="text-lg font-bold" style={{ color }}>{value}</div>
      <div className="text-[9px] mono uppercase tracking-widest text-white/35 mt-0.5">{label}</div>
      {sublabel && <div className="text-[9px] mono text-white/25 mt-0.5">{sublabel}</div>}
    </div>
  )
}
