// Single source of truth for status color naming (Step 0 audit,
// 2026-08-21) — "calm/watch/critical" everywhere, replacing the
// "calm/elevated/alert" vocabulary that used to differ from
// CommandCenterPage's own naming for the identical concept. Hex values
// mirror frontend/src/index.css's @theme tokens exactly; components that
// can use Tailwind classes (bg-calm, text-critical/70) should prefer those
// — these exports exist for the places that can't (inline SVG/recharts
// stroke props, style={{}} where a literal is unavoidable).

export type StatusLevel = 'calm' | 'watch' | 'critical'

export const STATUS_COLOR: Record<StatusLevel, string> = {
  calm: '#8dff9e',
  watch: '#ffb648',
  critical: '#ff5a36',
}

export function riskLevel(risk: number): StatusLevel {
  if (risk >= 0.5) return 'critical'
  if (risk >= 0.25) return 'watch'
  return 'calm'
}

// Categorical (not status) palette — distinguishing seats in charts/
// legends. Never reused for anything status-like.
const SEAT_PALETTE = ['#5ad1ff', '#c4a3ff', '#ff6bd6', '#6be6c1', '#ffb648', '#8dff9e']

export function seatColor(seatId: string, allSeatIds: string[]): string {
  const sorted = [...new Set(allSeatIds)].sort()
  const idx = sorted.indexOf(seatId)
  return SEAT_PALETTE[Math.max(0, idx) % SEAT_PALETTE.length]
}

/** @deprecated use STATUS_COLOR — kept only until every caller migrates. */
export const LEVEL_COLOR = STATUS_COLOR
