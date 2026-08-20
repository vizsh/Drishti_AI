const SEAT_PALETTE = ['#ff5a36', '#ffb648', '#5ad1ff', '#8dff9e', '#ff6bd6', '#c4a3ff']

export function seatColor(seatId: string, allSeatIds: string[]): string {
  const sorted = [...new Set(allSeatIds)].sort()
  const idx = sorted.indexOf(seatId)
  return SEAT_PALETTE[Math.max(0, idx) % SEAT_PALETTE.length]
}

export function riskLevel(risk: number): 'calm' | 'elevated' | 'alert' {
  if (risk >= 0.5) return 'alert'
  if (risk >= 0.25) return 'elevated'
  return 'calm'
}

export const LEVEL_COLOR: Record<string, string> = {
  calm: '#8dff9e',
  elevated: '#ffb648',
  alert: '#ff5a36',
}
