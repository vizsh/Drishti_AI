import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Fingerprint } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { FingerprintGauge } from '../components/FingerprintGauge'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'

interface Baseline {
  torso_yaw_mean: number
  torso_yaw_std: number
  motion_mean: number
  motion_std: number
}

interface TelemetryPoint {
  sim_time: number
  yaw_z: number | null
  motion_z: number | null
}

// Part 2.6: "Digital Twin" — a dedicated behavioural-profile view per
// student, distinct from SeatDetailPage's investigation-focused history
// table. The point is to make the system's core differentiator (scoring
// against THIS student's own settling-window baseline, never a flat
// threshold) something you can see at a glance: their usual range, and
// where they sit in it right now.
export function DigitalTwinPage() {
  const { seatId } = useParams<{ seatId: string }>()
  const { seats } = useLive()
  const { isSeatInScope } = useHallScope()
  const [baseline, setBaseline] = useState<Baseline | null>(null)
  const [calibrated, setCalibrated] = useState<boolean | null>(null)
  const [history, setHistory] = useState<TelemetryPoint[]>([])

  useEffect(() => {
    if (!seatId) return
    let cancelled = false
    async function poll() {
      try {
        const [b, e] = await Promise.all([
          fetch(`/api/seats/${seatId}/baseline`).then((r) => r.json()),
          fetch(`/api/events?seat_id=${seatId}&event_type=telemetry&limit=300`).then((r) => r.json()),
        ])
        if (cancelled) return
        setCalibrated(b.calibrated)
        setBaseline(b.baseline)
        setHistory(
          (e.events as TelemetryPoint[]).slice().reverse().map((ev) => ({ sim_time: ev.sim_time, yaw_z: ev.yaw_z, motion_z: ev.motion_z }))
        )
      } catch {
        /* keep last known */
      }
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [seatId])

  if (!seatId) return null

  if (!isSeatInScope(seatId)) {
    return (
      <div>
        <Link to="/overview" className="flex items-center gap-1.5 text-xs mono text-white/50 hover:text-white mb-4 w-fit">
          <ArrowLeft size={13} /> back to overview
        </Link>
        <div className="text-sm mono text-white/30 py-16 text-center">
          {seatId.toUpperCase()} is outside your assigned hall — access restricted.
        </div>
      </div>
    )
  }

  const seat = seats[seatId]

  return (
    <div>
      <Link to={`/seat/${seatId}`} className="flex items-center gap-1.5 text-xs mono text-white/50 hover:text-white mb-4 w-fit">
        <ArrowLeft size={13} /> back to investigation view
      </Link>
      <div className="flex items-center gap-3 mb-2">
        <Fingerprint size={20} className="text-white/50" />
        <h1 className="text-2xl font-bold">{seatId.replace('_', ' ').toUpperCase()} — behavioural profile</h1>
      </div>
      <p className="text-xs mono text-white/40 mb-6">
        every number below is scored against this student's OWN settling-window baseline — never a flat threshold shared across seats
      </p>

      {!calibrated ? (
        <div className="text-sm mono text-white/30 py-16 text-center">
          {calibrated === null ? 'loading…' : `${seatId.toUpperCase()} hasn't finished calibrating yet — a baseline needs a settling window of real data first.`}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            <FingerprintGauge
              label="Torso orientation"
              mean={baseline!.torso_yaw_mean}
              std={baseline!.torso_yaw_std}
              current={seat?.yawZ != null ? baseline!.torso_yaw_mean + seat.yawZ * Math.max(baseline!.torso_yaw_std, 1e-3) : null}
              zScore={seat?.yawZ ?? null}
            />
            <FingerprintGauge
              label="Movement level"
              mean={baseline!.motion_mean}
              std={baseline!.motion_std}
              current={seat?.motionZ != null ? baseline!.motion_mean + seat.motionZ * Math.max(baseline!.motion_std, 1e-3) : null}
              zScore={seat?.motionZ ?? null}
            />
          </div>

          <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Deviation from baseline — this session</h2>
          <div className="rounded-2xl border border-white/8 p-4 mb-6">
            {history.length === 0 ? (
              <div className="text-xs mono text-white/30 py-12 text-center">no telemetry recorded yet this session</div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={history}>
                  <CartesianGrid stroke="#ffffff0a" vertical={false} />
                  <XAxis dataKey="sim_time" tick={{ fontSize: 10, fill: '#8b8578' }} tickFormatter={(v) => `${v.toFixed(0)}s`} />
                  <YAxis tick={{ fontSize: 10, fill: '#8b8578' }} width={30} label={{ value: 'z-score', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#8b8578' }} />
                  <ReferenceLine y={0} stroke="#ffffff20" />
                  <ReferenceLine y={2} stroke="#ffb64840" strokeDasharray="3 3" />
                  <ReferenceLine y={-2} stroke="#ffb64840" strokeDasharray="3 3" />
                  <Tooltip contentStyle={{ background: '#0a0a0d', border: '1px solid #ffffff18', borderRadius: 10, fontSize: 11 }} labelFormatter={(v) => `t=${Number(v).toFixed(1)}s`} />
                  <Line type="monotone" dataKey="yaw_z" name="torso orientation" stroke="#ff5a36" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
                  <Line type="monotone" dataKey="motion_z" name="movement" stroke="#5ad1ff" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
          <p className="text-[10px] mono text-white/35">
            0 = exactly this student's own average · dashed lines mark ±2 standard deviations from their baseline, the threshold sustained-deviation scoring reacts to
          </p>
        </>
      )}
    </div>
  )
}
