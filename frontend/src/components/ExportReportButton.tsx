import { useState } from 'react'
import { FileDown, Loader2 } from 'lucide-react'
import { useHallScope } from '../state/useHallScope'

// Phase 6: downloads a real PDF built from live session data at click time
// (backend/report.py) - not a static file. Browsers block a script-driven
// download unless it originates from a real user gesture, so this fetches
// the bytes on click and hands the browser a genuine object-URL download,
// rather than trying to auto-trigger anything.
export function ExportReportButton() {
  const [loading, setLoading] = useState(false)
  const { scopedSeatIds } = useHallScope()

  async function handleExport() {
    setLoading(true)
    try {
      const scopeKey = [...scopedSeatIds].sort().join(',')
      const params = scopeKey ? `?seat_ids=${scopeKey}` : ''
      const res = await fetch(`/api/report${params}`)
      if (!res.ok) throw new Error('export failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'kinesis_session_report.pdf'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      /* button stays enabled to retry */
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={loading}
      className="flex items-center gap-2 text-xs mono px-4 py-2.5 rounded-xl border shrink-0 self-start"
      style={{ borderColor: '#ffb64840', color: '#ffb648', background: '#ffb64810' }}
    >
      {loading ? <Loader2 size={14} className="animate-spin" /> : <FileDown size={14} />}
      {loading ? 'generating…' : 'export session report'}
    </button>
  )
}
