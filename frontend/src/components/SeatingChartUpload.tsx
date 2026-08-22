import { useEffect, useState } from 'react'
import { ClipboardList, UploadCloud, CheckCircle2 } from 'lucide-react'

interface Assignment {
  seat_id: string
  occupant_label: string
}

// Seating chart upload (2026-08-23): a real institution roster — which
// seat should have which student — parsed from a simple CSV
// (seat_id,occupant_label per line). occupant_label is free-text
// record-keeping only (a roll number or name), never tied to a face
// embedding or used for detection; identity stays seat-anchored per this
// project's non-negotiable no-face-recognition rule. This is purely the
// upload half — the occupancy-mismatch comparison lives on Examination
// Hall (OccupancyCheckPanel), reading this same data against live seat
// state.
export function SeatingChartUpload() {
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetch('/api/seating-chart')
      .then((r) => r.json())
      .then((d) => setAssignments(d.assignments ?? []))
      .catch(() => {})
  }, [])

  function parseCsv(text: string): Assignment[] {
    return text
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .filter((line) => !/^seat.?id/i.test(line)) // skip an optional header row
      .map((line) => {
        const [seat_id, ...rest] = line.split(',')
        return { seat_id: seat_id?.trim(), occupant_label: rest.join(',').trim() }
      })
      .filter((a) => a.seat_id && a.occupant_label)
  }

  async function handleFile(file: File) {
    setError(null)
    setSaved(false)
    try {
      const text = await file.text()
      const parsed = parseCsv(text)
      if (parsed.length === 0) throw new Error('no valid rows found — expected "seat_id,occupant_label" per line')
      const res = await fetch('/api/seating-chart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assignments: parsed }),
      })
      if (!res.ok) throw new Error('upload failed')
      setAssignments(parsed)
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'upload failed')
    }
  }

  return (
    <div className="rounded-2xl border border-white/8 p-5 mb-6" style={{ background: 'linear-gradient(180deg, #ffffff06, #ffffff01)' }}>
      <div className="flex items-center gap-2 mb-1">
        <ClipboardList size={14} className="text-white/50" />
        <h2 className="text-sm font-bold uppercase tracking-wide">Seating chart</h2>
      </div>
      <p className="text-[11px] mono text-white/40 mb-3">
        upload which seat should have which student (CSV: <code className="text-white/60">seat_id,occupant_label</code> per
        line) — record-keeping only, never used for detection or identity
      </p>
      <label className="flex items-center gap-2 text-[11px] mono text-white/50 px-3 py-2 rounded-lg border border-white/12 hover:border-white/25 cursor-pointer w-fit mb-3">
        <UploadCloud size={13} />
        upload seating chart (.csv)
        <input
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void handleFile(file)
            e.target.value = ''
          }}
        />
      </label>
      {error && <p className="text-[11px] text-critical mb-2">{error}</p>}
      {saved && (
        <p className="text-[11px] mono text-calm mb-2 flex items-center gap-1">
          <CheckCircle2 size={12} /> saved — {assignments.length} seat assignment{assignments.length === 1 ? '' : 's'}, feeds
          the occupancy check on Examination Hall
        </p>
      )}
      {assignments.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {assignments.slice(0, 12).map((a) => (
            <span key={a.seat_id} className="text-[10px] mono px-2 py-1 rounded-md border border-white/10 text-white/50">
              {a.seat_id} &rarr; {a.occupant_label}
            </span>
          ))}
          {assignments.length > 12 && (
            <span className="text-[10px] mono px-2 py-1 text-white/30">+{assignments.length - 12} more</span>
          )}
        </div>
      )}
    </div>
  )
}
