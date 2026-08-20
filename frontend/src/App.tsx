import { useEffect, useState } from 'react'
import { useLiveSocket } from './hooks/useLiveSocket'
import { Header } from './components/Header'
import { StatStrip } from './components/StatStrip'
import { CoveragePanel } from './components/CoveragePanel'
import { LiveFeed } from './components/LiveFeed'
import { SeatGrid } from './components/SeatGrid'
import { RiskTrendChart } from './components/RiskTrendChart'
import { AlertFeed } from './components/AlertFeed'
import { EvidenceModal } from './components/EvidenceModal'
import { SessionAnalytics } from './components/SessionAnalytics'
import { EventLog } from './components/EventLog'

export default function App() {
  const { seats, riskHistory, alerts, connected, cameraOnline, detectorFinetuned, lightingEnhanced, feedImage, feedback, dismissAlert } = useLiveSocket()
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)
  const [sessionAlerts, setSessionAlerts] = useState(0)
  const [avgRisk, setAvgRisk] = useState(0)

  useEffect(() => {
    async function poll() {
      try {
        const res = await fetch('/api/analytics')
        const data = await res.json()
        setSessionAlerts(data.total_alerts)
        setAvgRisk(data.avg_risk)
      } catch { /* keep last known */ }
    }
    poll()
    const id = setInterval(poll, 4000)
    return () => clearInterval(id)
  }, [])

  const seatIds = Object.keys(seats)
  const calibratedCount = seatIds.filter((id) => seats[id].calibrated).length

  return (
    <div className="noise-bg grid-texture min-h-screen">
      <div className="max-w-[1600px] mx-auto px-6">
        <Header connected={connected} cameraOnline={cameraOnline} />
        <StatStrip seatsMonitored={seatIds.length} calibrated={calibratedCount} alerts={sessionAlerts} avgRisk={avgRisk} />
        <CoveragePanel />

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
          <div className="lg:col-span-1">
            <LiveFeed feedImage={feedImage} detectorFinetuned={detectorFinetuned} lightingEnhanced={lightingEnhanced} />
          </div>
          <div className="lg:col-span-2">
            <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Seating grid</h2>
            <SeatGrid seats={seats} />
            <h2 className="text-sm font-bold uppercase tracking-wide mb-3 mt-6">
              Risk trend <span className="text-white/30 font-normal normal-case">— last 60s</span>
            </h2>
            <div className="rounded-2xl border border-white/8 p-4">
              <RiskTrendChart riskHistory={riskHistory} />
            </div>
          </div>
          <div className="lg:col-span-1">
            <AlertFeed alerts={alerts} feedback={feedback} seatIds={seatIds} onDismiss={dismissAlert} onViewEvidence={setEvidenceUrl} />
          </div>
        </div>

        <div className="mt-8">
          <SessionAnalytics />
        </div>

        <EventLog onViewEvidence={setEvidenceUrl} />

        <footer className="mt-10 pb-10 text-center text-[11px] mono text-white/25">
          identity is seat-anchored, not face-based · risk scored against each student's own calibrated baseline · illustrative seat calibration for demo
        </footer>
      </div>

      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
    </div>
  )
}
