// Part 2.6: a "this student's own baseline" gauge — the visual center of
// the Digital Twin view. Shows the settling-window mean ± std band as a
// horizontal zone, and the current live value's position within it, so the
// personal-baseline concept (this system's core differentiator) is
// something you can *see*, not just a number in a table.
export function FingerprintGauge({
  label,
  mean,
  std,
  current,
  zScore,
  unit,
}: {
  label: string
  mean: number
  std: number
  current: number | null
  zScore: number | null
  unit?: string
}) {
  const span = Math.max(std * 3.5, 0.5)
  const lo = mean - span
  const hi = mean + span
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100))

  const band1Lo = pct(mean - std)
  const band1Hi = pct(mean + std)
  const band2Lo = pct(mean - 2 * std)
  const band2Hi = pct(mean + 2 * std)
  const meanPct = pct(mean)
  const currentPct = current != null ? pct(current) : null

  const severity = zScore == null ? 'unknown' : Math.abs(zScore) >= 3 ? 'alert' : Math.abs(zScore) >= 2 ? 'watch' : 'calm'
  const markerColor = severity === 'alert' ? '#ff5a36' : severity === 'watch' ? '#ffb648' : '#8dff9e'

  return (
    <div className="rounded-2xl border border-white/8 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-bold uppercase tracking-wide text-white/70">{label}</span>
        {current != null && (
          <span className="text-xs mono" style={{ color: markerColor }}>
            {current.toFixed(2)}
            {unit ?? ''}
          </span>
        )}
      </div>
      <div className="relative h-8">
        <div className="absolute inset-y-0 rounded-full" style={{ left: `${band2Lo}%`, right: `${100 - band2Hi}%`, background: '#ffffff08' }} />
        <div className="absolute inset-y-0 rounded-full" style={{ left: `${band1Lo}%`, right: `${100 - band1Hi}%`, background: '#8dff9e1a' }} />
        <div className="absolute top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-white/30" style={{ left: `${meanPct}%` }} />
        {currentPct != null && (
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-black"
            style={{ left: `calc(${currentPct}% - 6px)`, background: markerColor, boxShadow: `0 0 8px ${markerColor}80` }}
          />
        )}
      </div>
      <div className="flex justify-between text-[9px] mono text-white/30 mt-1.5">
        <span>usual range (±2σ)</span>
        <span>this student's own baseline</span>
      </div>
    </div>
  )
}
