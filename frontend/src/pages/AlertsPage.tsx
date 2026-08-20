import { useState } from 'react'
import { AlertFeed } from '../components/AlertFeed'
import { EventLog } from '../components/EventLog'
import { EvidenceModal } from '../components/EvidenceModal'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'

export function AlertsPage() {
  const { seats, alerts, feedback, dismissAlert, dispatchInvigilator, acknowledgeAlert } = useLive()
  const { isSeatInScope } = useHallScope()
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)
  const seatIds = Object.keys(seats).filter(isSeatInScope)
  const scopedAlerts = alerts.filter((a) => isSeatInScope(a.seatId))

  return (
    <div>
      <AlertFeed alerts={scopedAlerts} feedback={feedback} seatIds={seatIds} onDismiss={dismissAlert} onDispatch={dispatchInvigilator} onAcknowledge={acknowledgeAlert} onViewEvidence={setEvidenceUrl} />
      <EventLog onViewEvidence={setEvidenceUrl} />
      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
    </div>
  )
}
