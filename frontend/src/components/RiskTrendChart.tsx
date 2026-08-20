import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import type { RiskPoint } from '../types'
import { seatColor } from '../lib/colors'

export function RiskTrendChart({ riskHistory }: { riskHistory: Record<string, RiskPoint[]> }) {
  const seatIds = Object.keys(riskHistory).sort()
  if (seatIds.length === 0) {
    return <div className="text-xs mono text-white/30 py-16 text-center">no telemetry yet</div>
  }

  // recharts wants one merged array keyed by t
  const merged: Record<number, Record<string, number>> = {}
  for (const seatId of seatIds) {
    for (const p of riskHistory[seatId]) {
      const bucket = Math.round(p.t * 2) / 2 // 0.5s buckets
      merged[bucket] = merged[bucket] ?? { t: bucket }
      merged[bucket][seatId] = p.risk
    }
  }
  const data = Object.values(merged).sort((a, b) => a.t - b.t)

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data}>
        <CartesianGrid stroke="#ffffff0a" vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 10, fill: '#8b8578' }} tickFormatter={(v) => `${v.toFixed(0)}s`} />
        <YAxis domain={[0, 1.2]} tick={{ fontSize: 10, fill: '#8b8578' }} width={30} />
        <Tooltip
          contentStyle={{ background: '#0a0a0d', border: '1px solid #ffffff18', borderRadius: 10, fontSize: 11 }}
          labelFormatter={(v) => `t=${Number(v).toFixed(1)}s`}
        />
        {seatIds.map((seatId) => (
          <Line
            key={seatId}
            type="monotone"
            dataKey={seatId}
            stroke={seatColor(seatId, seatIds)}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
