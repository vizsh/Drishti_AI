import { Cpu } from 'lucide-react'
import { useLive } from '../state/LiveContext'

// Model transparency card (2026-08-23): resurrects a good idea that had
// gone dead (LiveFeed.tsx, an orphaned component nothing imported
// anymore) into the current live surfaces. Reads the exact same
// detectorFinetuned/lightingEnhanced flags the backend already streams
// per-frame (backend/pipeline_worker.py) — the badge below flips
// automatically and honestly the moment a validated fine-tuned model is
// actually swapped in, it's not a static claim.
export function ModelStatusCard() {
  const { detectorFinetuned, lightingEnhanced } = useLive()

  return (
    <div className="rounded-2xl border border-white/8 p-5 mb-6 bg-white/3">
      <div className="flex items-center gap-2 mb-3">
        <Cpu size={14} className="text-white/50" />
        <h2 className="text-sm font-bold uppercase tracking-wide">Detection models in use</h2>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs mono">
        <Row
          label="Object detector"
          value={detectorFinetuned ? 'fine-tuned (validated)' : 'stock COCO YOLO11n (baseline)'}
          accent={detectorFinetuned}
        />
        <Row label="Pose / tracking" value="YOLO11-pose + BoT-SORT" />
        <Row label="Identity" value="seat-anchored via homography — never face-based" />
        <Row label="Lighting compensation" value={lightingEnhanced ? 'CLAHE active — low-light frame' : 'normal exposure'} accent={lightingEnhanced} />
      </div>
      {!detectorFinetuned && (
        <p className="text-[10px] text-white/30 mt-3 leading-relaxed">
          the object detector is running COCO-pretrained stock weights, filtered to contraband-relevant classes — real
          detection, not a placeholder, but not yet specialized for this domain. A fine-tuned replacement only ever
          gets swapped in after it beats this baseline on real ground-truth footage, not a training-loss number.
        </p>
      )}
    </div>
  )
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-white/6 px-3 py-2">
      <div className="text-[9px] uppercase tracking-widest text-white/35 mb-0.5">{label}</div>
      <div style={{ color: accent ? '#8dff9e' : undefined }} className={accent ? 'font-semibold' : 'text-white/75'}>{value}</div>
    </div>
  )
}
