import { useState } from 'react'
import { AlertFeed } from '../components/AlertFeed'
import { EventLog } from '../components/EventLog'
import { EvidenceModal } from '../components/EvidenceModal'
import { useLive } from '../state/LiveContext'

export function AlertsPage() {
  const { seats, alerts, feedback, dismissAlert } = useLive()
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)
  const seatIds = Object.keys(seats)

  return (
    <div>
      <AlertFeed alerts={alerts} feedback={feedback} seatIds={seatIds} onDismiss={dismissAlert} onViewEvidence={setEvidenceUrl} />
      <EventLog onViewEvidence={setEvidenceUrl} />
      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
    </div>
  )
}
