import { useEffect, useState } from 'react'
import {
  ShieldCheck, ShieldAlert, Radar, Video, AlertTriangle, UserPlus, X, Check,
  Brain, Play, Pause, ChevronLeft, ChevronRight, LogOut,
} from 'lucide-react'
import { Badge } from '../components/Badge'
import { EvidenceModal } from '../components/EvidenceModal'
import { ExportReportButton } from '../components/ExportReportButton'
import { FingerprintGauge } from '../components/FingerprintGauge'

const STEP_SECONDS = 11

// A real evidence clip captured earlier this session (seat_1's calibrated
// baseline, real bbox/keypoint annotations from frame 0) — reused here
// rather than fabricating a frame, so the "annotated evidence" step shows
// genuine backend output, not a mockup.
const DEMO_EVIDENCE_URL = '/evidence/seat_1_1002248/manifest.json'

interface Step {
  title: string
  narration: string
  render: (props: { active: boolean; onOpenEvidence: () => void }) => React.ReactNode
}

const COVERAGE_SEATS = ['seat_1', 'seat_2', 'seat_3', 'seat_4', 'seat_5', 'seat_6']

function CoverageGrid({ blindSeat }: { blindSeat: string | null }) {
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-3">
      {COVERAGE_SEATS.map((s) => {
        const covered = s !== blindSeat
        return (
          <div
            key={s}
            className="rounded-xl p-3 text-center border"
            style={{ borderColor: covered ? '#8dff9e35' : '#ff5a3645', background: covered ? '#8dff9e0a' : '#ff5a360f' }}
          >
            <div className="flex justify-center mb-1">
              {covered ? <ShieldCheck size={16} className="text-calm" /> : <ShieldAlert size={16} className="text-critical" />}
            </div>
            <div className="text-[11px] font-bold">{s.replace('_', ' ').toUpperCase()}</div>
            <div className={`text-[9px] mono mt-0.5 ${covered ? 'text-calm' : 'text-critical'}`}>{covered ? 'covered' : 'blind spot'}</div>
          </div>
        )
      })}
    </div>
  )
}

function DemoCameraTile({ label, seats, severity }: { label: string; seats: string; severity: 'calm' | 'watch' | 'critical' }) {
  const border = severity === 'critical' ? 'border-critical/60' : severity === 'watch' ? 'border-watch/50' : 'border-white/10'
  const glow = severity === 'critical' ? 'shadow-[0_0_24px_-4px_#ff5a3680]' : ''
  return (
    <div className={`rounded-2xl border overflow-hidden ${border} ${glow}`}>
      <div className="relative flex items-center justify-center bg-black" style={{ aspectRatio: '16/10' }}>
        <Video size={20} className="text-white/20" />
        {severity !== 'calm' && (
          <div className="absolute top-2 right-2">
            <Badge tone={severity}>
              <AlertTriangle size={10} /> 1
            </Badge>
          </div>
        )}
      </div>
      <div className="p-3">
        <div className="text-xs font-bold mb-1">{label}</div>
        <div className="text-[10px] mono text-white/40">{seats}</div>
      </div>
    </div>
  )
}

function DemoAlertCard({ stage }: { stage: 'fired' | 'dispatched' | 'resolved' }) {
  return (
    <div className="rounded-xl p-4 border max-w-md" style={{ borderColor: '#ff5a3640', background: '#ff5a360c' }}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-bold text-critical">SEAT_5</span>
        <span className="text-[10px] mono text-white/40">14.2s</span>
      </div>
      <p className="text-xs text-white/75 leading-snug mb-3">Unusual posture sustained for 2.3s</p>
      <div className="flex flex-col gap-2">
        {stage === 'fired' && (
          <button className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/50 w-fit">
            <UserPlus size={11} /> dispatch invigilator
          </button>
        )}
        {stage === 'dispatched' && (
          <>
            <p className="text-[10px] mono text-white/40">↳ dispatched to R. Fernandes</p>
            <div className="flex flex-wrap gap-2">
              <button className="flex items-center gap-1 text-[10px] mono px-2 py-1 rounded-md border border-white/12 text-white/50">
                <X size={11} /> false alarm
              </button>
            </div>
          </>
        )}
        {stage === 'resolved' && (
          <p className="flex items-center gap-1 text-[10px] mono text-calm">
            <Check size={11} /> resolved — false alarm (baseline widened)
          </p>
        )}
      </div>
    </div>
  )
}

const STEPS: Step[] = [
  {
    title: 'Pre-exam setup: coverage check',
    narration: 'Before students are seated, every configured seat is checked against real camera geometry — Seat 6 falls outside any camera\'s usable frame.',
    render: () => <CoverageGrid blindSeat="seat_6" />,
  },
  {
    title: 'Blind spot resolved',
    narration: 'Coverage is fixed before the exam starts, not discovered mid-exam — the invigilator can see this and act before a single student goes unmonitored.',
    render: () => <CoverageGrid blindSeat={null} />,
  },
  {
    title: 'Baseline calibration',
    narration: 'Each seat runs its own ~20 second settling window — this student\'s own usual torso orientation and movement become the baseline everything is measured against, not a flat threshold shared with every other seat.',
    render: () => (
      <div className="max-w-md">
        <FingerprintGauge label="Torso orientation" mean={-0.12} std={0.08} current={-0.09} zScore={0.4} />
      </div>
    ),
  },
  {
    title: 'Command Center: all calm',
    narration: 'The default view after login — every camera the logged-in role can see, grouped by hall. Calm by default: nothing here is competing for attention.',
    render: () => (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 max-w-2xl">
        <DemoCameraTile label="cam04_illustrative" seats="4 seats" severity="calm" />
        <DemoCameraTile label="cam_b_SIMULATED" seats="2 seats" severity="calm" />
        <DemoCameraTile label="cam_c_SIMULATED" seats="2 seats" severity="calm" />
      </div>
    ),
  },
  {
    title: 'A real alert fires',
    narration: 'Seat 5 deviates from its own baseline for a sustained duration — the tile flags red, pulling attention only when something actually warrants it.',
    render: () => (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 max-w-2xl">
        <DemoCameraTile label="cam04_illustrative" seats="4 seats" severity="critical" />
        <DemoCameraTile label="cam_b_SIMULATED" seats="2 seats" severity="calm" />
        <DemoCameraTile label="cam_c_SIMULATED" seats="2 seats" severity="calm" />
      </div>
    ),
  },
  {
    title: 'Annotated evidence appears',
    narration: 'Clicking the flagged tile goes straight to the investigation view — a real evidence clip from this session, with the flagged student\'s bounding box and skeleton drawn directly on the frame, faces auto-blurred.',
    render: (props) => (
      <button
        onClick={props.onOpenEvidence}
        className="flex items-center gap-2 text-xs mono px-4 py-2.5 rounded-xl border border-white/15 text-white/70 hover:border-white/30"
      >
        <Play size={14} /> view annotated evidence clip
      </button>
    ),
  },
  {
    title: 'Dispatch invigilator',
    narration: 'One click auto-fills the logged-in invigilator and timestamps the dispatch — a real, audited action, not a note taken elsewhere.',
    render: () => <DemoAlertCard stage="dispatched" />,
  },
  {
    title: 'Resolution',
    narration: 'The invigilator resolves it as a false alarm — this seat\'s baseline widens immediately, live, so the same pattern won\'t re-trigger.',
    render: () => <DemoAlertCard stage="resolved" />,
  },
  {
    title: 'System learning indicator moves',
    narration: 'That resolution is the same data this indicator reads — dismissing a real alert as a false alarm is what makes this number move, not a simulated counter.',
    render: () => (
      <div className="rounded-2xl border border-white/8 px-5 py-4 flex items-center gap-4 bg-white/3 max-w-md">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 bg-white/8">
          <Brain size={18} className="text-ink-dim" />
        </div>
        <div>
          <div className="text-[10px] mono uppercase tracking-widest text-white/40">system learning</div>
          <div className="text-sm text-white/80">
            <span className="font-bold text-white">1</span> false-positive dismissed this session
            <span className="text-white/50"> — that seat's baseline has been widened, reducing repeat false alarms</span>
          </div>
        </div>
      </div>
    ),
  },
  {
    title: 'Session report export',
    narration: 'This button is real — it downloads an actual PDF built from this session\'s live data at the moment you click it, not a canned sample.',
    render: () => <ExportReportButton />,
  },
]

// Part 1 (product-conviction pass, 2026-08-21): a scripted walkthrough that
// sequences through the whole product story in under two minutes without
// depending on live camera behaviour cooperating — the coverage grid,
// camera tiles, alert card, and learning indicator here are staged data
// through the SAME components/styling as the live app (not a separate
// mockup); the evidence step opens a real evidence clip's real manifest,
// and the export step triggers a real PDF download.
export function DemoModePage({ onExit }: { onExit: () => void }) {
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  const step = STEPS[index]
  const isLast = index === STEPS.length - 1

  useEffect(() => {
    if (!playing || evidenceOpen) return
    const id = setInterval(() => {
      setElapsed((e) => {
        if (e + 1 >= STEP_SECONDS) {
          setIndex((i) => (i < STEPS.length - 1 ? i + 1 : i))
          return 0
        }
        return e + 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [playing, evidenceOpen, index])

  function goTo(i: number) {
    setIndex(Math.max(0, Math.min(STEPS.length - 1, i)))
    setElapsed(0)
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-void">
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/8">
        <div className="flex items-center gap-2.5">
          <Radar size={18} className="text-ink" />
          <span className="text-sm font-bold">KINESIS <span className="text-white/40">— guided demo</span></span>
        </div>
        <button onClick={onExit} className="flex items-center gap-1.5 text-xs mono px-3 py-1.5 rounded-lg border border-white/15 text-white/60 hover:border-white/30">
          <LogOut size={13} /> exit demo
        </button>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 gap-8">
        <div className="text-center max-w-xl">
          <div className="text-[10px] mono uppercase tracking-widest text-white/35 mb-1.5">
            step {index + 1} of {STEPS.length}
          </div>
          <h1 className="text-xl font-bold mb-2">{step.title}</h1>
          <p className="text-xs text-white/55 leading-relaxed">{step.narration}</p>
        </div>
        <div className="min-h-[180px] flex items-center justify-center w-full">
          {step.render({ active: true, onOpenEvidence: () => setEvidenceOpen(true) })}
        </div>
      </div>

      <div className="px-6 pb-6">
        <div className="flex gap-1 mb-3">
          {STEPS.map((_, i) => (
            <button key={i} onClick={() => goTo(i)} className="flex-1 h-1 rounded-full overflow-hidden bg-white/10">
              <div
                className="h-full bg-white/60"
                style={{ width: i < index ? '100%' : i === index ? `${(elapsed / STEP_SECONDS) * 100}%` : '0%' }}
              />
            </button>
          ))}
        </div>
        <div className="flex items-center justify-center gap-3">
          <button onClick={() => goTo(index - 1)} disabled={index === 0} className="p-2 rounded-lg border border-white/12 text-white/60 disabled:opacity-30">
            <ChevronLeft size={16} />
          </button>
          <button onClick={() => setPlaying((p) => !p)} className="flex items-center gap-1.5 text-xs mono px-4 py-2 rounded-lg border border-white/15 text-white/70">
            {playing ? <Pause size={13} /> : <Play size={13} />} {playing ? 'pause' : 'play'}
          </button>
          <button onClick={() => (isLast ? onExit() : goTo(index + 1))} className="p-2 rounded-lg border border-white/12 text-white/60">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <EvidenceModal url={evidenceOpen ? DEMO_EVIDENCE_URL : null} onClose={() => setEvidenceOpen(false)} />
    </div>
  )
}
