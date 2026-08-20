import { Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Header } from '../components/Header'
import { StatStrip } from '../components/StatStrip'
import { Sidebar } from '../components/Sidebar'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'

export function AppLayout() {
  const { seats, connected, cameraOnline } = useLive()
  const { isSeatInScope, scopedSeatIds } = useHallScope()
  const [sessionAlerts, setSessionAlerts] = useState(0)
  const [avgRisk, setAvgRisk] = useState(0)

  const seatIds = Object.keys(seats).filter(isSeatInScope)
  const scopeKey = [...scopedSeatIds].sort().join(',')

  useEffect(() => {
    async function poll() {
      try {
        const params = scopeKey ? `?seat_ids=${scopeKey}` : ''
        const res = await fetch(`/api/analytics${params}`)
        const data = await res.json()
        setSessionAlerts(data.total_alerts)
        setAvgRisk(data.avg_risk)
      } catch { /* keep last known */ }
    }
    poll()
    const id = setInterval(poll, 4000)
    return () => clearInterval(id)
  }, [scopeKey])

  const calibratedCount = seatIds.filter((id) => seats[id].calibrated).length

  return (
    <div className="noise-bg grid-texture min-h-screen flex">
      <Sidebar />
      <div className="flex-1 min-w-0 px-6">
        <div className="max-w-[1500px] mx-auto">
          <Header connected={connected} cameraOnline={cameraOnline} />
          <StatStrip seatsMonitored={seatIds.length} calibrated={calibratedCount} alerts={sessionAlerts} avgRisk={avgRisk} />
          <Outlet />
          <footer className="mt-10 pb-10 text-center text-[11px] mono text-white/25">
            identity is seat-anchored, not face-based · risk scored against each student's own calibrated baseline · illustrative seat calibration for demo
          </footer>
        </div>
      </div>
    </div>
  )
}
