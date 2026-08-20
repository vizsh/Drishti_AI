import { useState } from 'react'
import { CoveragePanel } from '../components/CoveragePanel'
import { SeatGrid } from '../components/SeatGrid'
import { AlertFeed } from '../components/AlertFeed'
import { EvidenceModal } from '../components/EvidenceModal'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'

export function OverviewPage() {
  const { seats, alerts, feedback, dismissAlert } = useLive()
  const { isSeatInScope } = useHallScope()
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)

  const scopedSeats = Object.fromEntries(Object.entries(seats).filter(([id]) => isSeatInScope(id)))
  const seatIds = Object.keys(scopedSeats)
  const scopedAlerts = alerts.filter((a) => isSeatInScope(a.seatId))

  return (
    <div>
      <CoveragePanel />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Seating grid</h2>
          <SeatGrid seats={scopedSeats} />
        </div>
        <div className="lg:col-span-1">
          <AlertFeed
            alerts={scopedAlerts}
            feedback={feedback}
            seatIds={seatIds}
            onDismiss={dismissAlert}
            onViewEvidence={setEvidenceUrl}
            limit={8}
            showViewAllLink
          />
        </div>
      </div>
      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
    </div>
  )
}
