import { NavLink, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Header } from '../components/Header'
import { StatStrip } from '../components/StatStrip'
import { useLive } from '../state/LiveContext'

const TABS = [
  { to: '/overview', label: 'Overview' },
  { to: '/live', label: 'Live' },
  { to: '/alerts', label: 'Alerts' },
  { to: '/analytics', label: 'Analytics' },
]

export function AppLayout() {
  const { seats, connected, cameraOnline } = useLive()
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

        <nav className="flex items-center gap-1 mb-6 border-b border-white/8 pb-0">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                `px-4 py-2.5 text-[12px] mono uppercase tracking-wide border-b-2 transition-colors ${
                  isActive ? 'text-white' : 'text-white/40 hover:text-white/70'
                }`
              }
              style={({ isActive }) => ({ borderColor: isActive ? '#ff5a36' : 'transparent' })}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>

        <Outlet />

        <footer className="mt-10 pb-10 text-center text-[11px] mono text-white/25">
          identity is seat-anchored, not face-based · risk scored against each student's own calibrated baseline · illustrative seat calibration for demo
        </footer>
      </div>
    </div>
  )
}
