import type { ReactNode } from 'react'
import { STATUS_COLOR, type StatusLevel } from '../lib/colors'

// One shared "small status pill" component (Step 0 audit, 2026-08-21) —
// this molecule used to be hand-rolled per file with drifting padding/
// radius/size (px-1.5 py-0.5 rounded vs px-2 py-1 rounded-md, 9px vs 10px
// text). tone='status' uses the calm/watch/critical palette (the only
// saturated colors in the app); tone='neutral' is for non-status labels
// (SIMULATED, GESTURE, CALIBRATION) which read as informational, not urgent.
type Tone = StatusLevel | 'neutral'

const TONE_COLOR: Record<Tone, string> = {
  ...STATUS_COLOR,
  neutral: '#8b8578',
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  const color = TONE_COLOR[tone]
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] mono uppercase px-2 py-0.5 rounded-full font-semibold tracking-wide"
      style={{ background: `${color}22`, color }}
    >
      {children}
    </span>
  )
}
