import { motion } from 'framer-motion'
import { Circle } from 'lucide-react'

interface Props {
  feedImage: string | null
  detectorFinetuned: boolean
  lightingEnhanced: boolean
}

export function LiveFeed({ feedImage, detectorFinetuned, lightingEnhanced }: Props) {
  return (
    <div>
      <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Live feed</h2>
      <div className="rounded-2xl overflow-hidden border border-white/8 relative mb-3" style={{ aspectRatio: '16/10', background: '#000' }}>
        {feedImage ? (
          <motion.img
            key={feedImage.slice(-20)}
            src={feedImage}
            className="w-full h-full object-cover"
            initial={{ opacity: 0.7 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.15 }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-xs mono text-white/30">waiting for stream…</div>
        )}
        <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] mono bg-black/60">
          <Circle size={7} fill="#ff5a36" color="#ff5a36" className="animate-pulse" /> REC · seat-anchored, faces not tracked
        </div>
      </div>
      <div className="rounded-2xl border border-white/8 p-4 text-xs mono text-white/45 leading-relaxed space-y-1.5">
        <Row label="Object detector" value={detectorFinetuned ? 'fine-tuned v1 (unverified)' : 'stock COCO (baseline)'} />
        <Row label="Perception" value="YOLO11-pose + BoT-SORT" />
        <Row label="Identity" value="seat-anchored (homography)" />
        <Row label="Lighting" value={lightingEnhanced ? 'CLAHE active — low light' : 'normal'} accent={lightingEnhanced} />
      </div>
    </div>
  )
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-white/35">{label}</span>
      <span style={{ color: accent ? '#ffb648' : undefined }} className={accent ? '' : 'text-white/70'}>{value}</span>
    </div>
  )
}
