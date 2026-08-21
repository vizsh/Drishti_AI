import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, Save, CheckCircle2, Loader2 } from 'lucide-react'
import { CoveragePanel } from '../components/CoveragePanel'

interface SeatEntry {
  seatId: string
  x: string
  y: string
}

interface CameraForm {
  cameraId: string
  videoPath: string
  imageWidth: string
  imageHeight: string
  isSimulated: boolean
  imagePoints: [string, string][]
  planePoints: [string, string][]
  seats: SeatEntry[]
}

// Reasonable generic default — a quad covering most of a 640x480 frame,
// mapped to a flat rectangle. Good enough to get a new camera running;
// precise pixel-perfect calibration is still a bigger, separate tool
// (drag-to-set homography points on a live snapshot) not built this pass.
function blankCamera(n: number): CameraForm {
  return {
    cameraId: `camera_${n}`,
    videoPath: '',
    imageWidth: '640',
    imageHeight: '480',
    isSimulated: false,
    imagePoints: [
      ['200', '195'],
      ['560', '260'],
      ['560', '150'],
      ['245', '105'],
    ],
    planePoints: [
      ['0', '0'],
      ['400', '0'],
      ['400', '40'],
      ['0', '40'],
    ],
    seats: [{ seatId: '', x: '', y: '' }],
  }
}

// Part F (2026-08-21): multi-camera lab setup flow. Configures a hall's
// cameras (RTSP or file sources — reuses the existing ingestion layer
// unchanged, this is purely a config/UI flow on top of it), assigns each
// to the seats it covers, and — where two cameras' seat assignments
// overlap — that overlap is exactly what backend/deployment_config.py's
// worker_groups() already uses to form a real fusion primary/secondary
// pair. No separate "enable fusion" step: configuring overlapping seats
// IS the fusion wiring.
export function LabSetupPage() {
  const [hall, setHall] = useState('Hall A')
  const [cameras, setCameras] = useState<CameraForm[]>([blankCamera(1)])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [coverageKey, setCoverageKey] = useState(0)

  function addCamera() {
    setCameras((prev) => [...prev, blankCamera(prev.length + 1)])
  }

  function removeCamera(i: number) {
    setCameras((prev) => prev.filter((_, idx) => idx !== i))
  }

  function updateCamera(i: number, patch: Partial<CameraForm>) {
    setCameras((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)))
  }

  function addSeat(camIdx: number) {
    updateCamera(camIdx, { seats: [...cameras[camIdx].seats, { seatId: '', x: '', y: '' }] })
  }

  function updateSeat(camIdx: number, seatIdx: number, patch: Partial<SeatEntry>) {
    const seats = cameras[camIdx].seats.map((s, idx) => (idx === seatIdx ? { ...s, ...patch } : s))
    updateCamera(camIdx, { seats })
  }

  function removeSeat(camIdx: number, seatIdx: number) {
    updateCamera(camIdx, { seats: cameras[camIdx].seats.filter((_, idx) => idx !== seatIdx) })
  }

  // Overlap preview: which seat ids appear in more than one camera's
  // assignment right now — this is what will become a real fusion pair
  // once saved, shown before saving so the setup flow tells that story.
  const seatCameraCount: Record<string, number> = {}
  for (const cam of cameras) {
    for (const s of cam.seats) {
      if (!s.seatId) continue
      seatCameraCount[s.seatId] = (seatCameraCount[s.seatId] ?? 0) + 1
    }
  }
  const overlappingSeats = Object.entries(seatCameraCount).filter(([, c]) => c > 1).map(([id]) => id)

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const payload = {
        hall,
        cameras: cameras.map((c) => ({
          camera_id: c.cameraId,
          video_path: c.videoPath,
          image_width: parseInt(c.imageWidth, 10),
          image_height: parseInt(c.imageHeight, 10),
          is_simulated: c.isSimulated,
          image_points: c.imagePoints.map(([x, y]) => [Number(x), Number(y)]),
          plane_points: c.planePoints.map(([x, y]) => [Number(x), Number(y)]),
          seats: Object.fromEntries(c.seats.filter((s) => s.seatId).map((s) => [s.seatId, [Number(s.x), Number(s.y)]])),
        })),
      }
      const res = await fetch('/api/setup/cameras', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(`save failed (${res.status})`)
      setSaved(true)
      setCoverageKey((k) => k + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <Link to="/settings" className="flex items-center gap-1.5 text-xs mono text-white/50 hover:text-white mb-4 w-fit">
        <ArrowLeft size={13} /> back to settings
      </Link>
      <h1 className="text-lg font-bold mb-1">Multi-Camera Lab Setup</h1>
      <p className="text-xs text-white/50 mb-6">
        Configure this hall's cameras and which seats each one covers — restarts the live pipeline against the new
        config, no manual file editing or app restart needed.
      </p>

      <div className="rounded-2xl border border-white/8 p-5 mb-5 bg-white/3">
        <label className="text-[11px] mono uppercase tracking-wide text-white/40">
          Hall name
          <input
            value={hall}
            onChange={(e) => setHall(e.target.value)}
            className="mt-1 w-full bg-transparent border border-white/15 rounded-lg px-3 py-2 text-sm outline-none focus:border-white/40"
          />
        </label>
      </div>

      {cameras.map((cam, i) => (
        <div key={i} className="rounded-2xl border border-white/8 p-5 mb-4 bg-white/3">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold">Camera {i + 1}</h2>
            {cameras.length > 1 && (
              <button onClick={() => removeCamera(i)} className="text-white/30 hover:text-critical">
                <Trash2 size={14} />
              </button>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <Field label="camera ID" value={cam.cameraId} onChange={(v) => updateCamera(i, { cameraId: v })} />
            <Field
              label="RTSP URL or video path"
              value={cam.videoPath}
              onChange={(v) => updateCamera(i, { videoPath: v })}
              placeholder="rtsp://192.168.1.50:554/stream1"
            />
            <Field label="image width (px)" value={cam.imageWidth} onChange={(v) => updateCamera(i, { imageWidth: v })} />
            <Field label="image height (px)" value={cam.imageHeight} onChange={(v) => updateCamera(i, { imageHeight: v })} />
          </div>

          <label className="flex items-center gap-2 text-[11px] mono text-white/50 mb-4">
            <input type="checkbox" checked={cam.isSimulated} onChange={(e) => updateCamera(i, { isSimulated: e.target.checked })} />
            simulated source (no real camera hardware)
          </label>

          <details className="mb-4">
            <summary className="text-[11px] mono uppercase tracking-wide text-white/40 cursor-pointer">
              homography alignment points (advanced — defaults are usually fine to start)
            </summary>
            <p className="text-[10px] text-white/35 mt-2 mb-2">
              4 image-pixel corners and their matching real-world/desk-plane positions. Precise drag-to-set calibration
              on a live snapshot is a separate, larger tool — these numeric defaults get a camera working immediately.
            </p>
            <div className="grid grid-cols-2 gap-4">
              <PointGrid label="image points (px)" points={cam.imagePoints} onChange={(pts) => updateCamera(i, { imagePoints: pts })} />
              <PointGrid label="plane points" points={cam.planePoints} onChange={(pts) => updateCamera(i, { planePoints: pts })} />
            </div>
          </details>

          <div className="border-t border-white/8 pt-3">
            <div className="text-[11px] mono uppercase tracking-wide text-white/40 mb-2">seats covered</div>
            {cam.seats.map((s, si) => (
              <div key={si} className="flex items-center gap-2 mb-2">
                <input
                  value={s.seatId}
                  onChange={(e) => updateSeat(i, si, { seatId: e.target.value })}
                  placeholder="seat_5"
                  className="w-24 bg-transparent border border-white/12 rounded-md px-2 py-1.5 text-xs outline-none focus:border-white/40"
                />
                <input
                  value={s.x}
                  onChange={(e) => updateSeat(i, si, { x: e.target.value })}
                  placeholder="x (px)"
                  className="w-20 bg-transparent border border-white/12 rounded-md px-2 py-1.5 text-xs outline-none focus:border-white/40"
                />
                <input
                  value={s.y}
                  onChange={(e) => updateSeat(i, si, { y: e.target.value })}
                  placeholder="y (px)"
                  className="w-20 bg-transparent border border-white/12 rounded-md px-2 py-1.5 text-xs outline-none focus:border-white/40"
                />
                {seatCameraCount[s.seatId] > 1 && (
                  <span className="text-[10px] mono text-watch">covered by {seatCameraCount[s.seatId]} cameras — will fuse</span>
                )}
                {cam.seats.length > 1 && (
                  <button onClick={() => removeSeat(i, si)} className="text-white/25 hover:text-critical">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            ))}
            <button onClick={() => addSeat(i)} className="flex items-center gap-1 text-[10px] mono text-white/40 hover:text-white/70 mt-1">
              <Plus size={11} /> add seat
            </button>
          </div>
        </div>
      ))}

      <button
        onClick={addCamera}
        className="flex items-center gap-1.5 text-xs mono px-3 py-2 rounded-lg border border-white/15 text-white/60 hover:border-white/30 mb-6"
      >
        <Plus size={13} /> add another camera
      </button>

      {overlappingSeats.length > 0 && (
        <div className="rounded-xl border border-watch/30 bg-watch/8 px-4 py-3 mb-5 text-xs text-watch">
          {overlappingSeats.length} seat{overlappingSeats.length === 1 ? '' : 's'} ({overlappingSeats.join(', ')}) covered by
          more than one camera — these will fuse both cameras' readings once saved.
        </div>
      )}

      <div className="flex items-center gap-3 mb-8">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 text-sm font-bold px-4 py-2.5 rounded-lg bg-watch text-void disabled:opacity-50"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          {saving ? 'saving & restarting pipeline…' : 'save & restart pipeline'}
        </button>
        {saved && (
          <span className="flex items-center gap-1.5 text-xs text-calm">
            <CheckCircle2 size={14} /> saved — live pipeline restarted
          </span>
        )}
        {error && <span className="text-xs text-critical">{error}</span>}
      </div>

      {saved && (
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Coverage summary</h2>
          <CoveragePanel key={coverageKey} />
        </div>
      )}
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <label className="text-[11px] mono uppercase tracking-wide text-white/40">
      {label}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full bg-transparent border border-white/15 rounded-lg px-3 py-2 text-sm outline-none focus:border-white/40"
      />
    </label>
  )
}

function PointGrid({
  label,
  points,
  onChange,
}: {
  label: string
  points: [string, string][]
  onChange: (pts: [string, string][]) => void
}) {
  return (
    <div>
      <div className="text-[10px] mono text-white/35 mb-1">{label}</div>
      {points.map(([x, y], i) => (
        <div key={i} className="flex items-center gap-1.5 mb-1.5">
          <input
            value={x}
            onChange={(e) => {
              const next = [...points] as [string, string][]
              next[i] = [e.target.value, y]
              onChange(next)
            }}
            className="w-16 bg-transparent border border-white/12 rounded-md px-2 py-1 text-xs outline-none focus:border-white/40"
          />
          <input
            value={y}
            onChange={(e) => {
              const next = [...points] as [string, string][]
              next[i] = [x, e.target.value]
              onChange(next)
            }}
            className="w-16 bg-transparent border border-white/12 rounded-md px-2 py-1 text-xs outline-none focus:border-white/40"
          />
        </div>
      ))}
    </div>
  )
}
