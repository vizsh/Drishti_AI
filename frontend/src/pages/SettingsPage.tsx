import { Link } from 'react-router-dom'
import { Settings as SettingsIcon, ShieldCheck, ChevronRight, PlayCircle } from 'lucide-react'
import { useAuth, DEMO_ACCOUNTS } from '../state/AuthContext'

export function SettingsPage() {
  const { user } = useAuth()
  if (!user) return null

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <SettingsIcon size={16} className="text-white/40" />
        <h1 className="text-lg font-bold">Settings</h1>
      </div>

      <div className="rounded-2xl border border-white/8 p-5 mb-5 max-w-lg bg-white/3">
        <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Signed in as</h2>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold bg-white/10">
            {user.initials}
          </div>
          <div>
            <div className="text-sm font-semibold">{user.name}</div>
            <div className="text-[11px] mono text-white/40">{user.email}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-4 text-xs mono px-3 py-2 rounded-lg bg-calm/10 text-calm">
          <ShieldCheck size={13} />
          {user.role === 'controller' ? 'Controller — full access to every hall' : `Invigilator — scoped to ${user.hall} only`}
        </div>
      </div>

      <Link
        to="/demo"
        className="flex items-center justify-between rounded-2xl border border-white/8 p-5 mb-5 max-w-lg bg-white/3 hover:border-white/20 transition-colors"
      >
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wide mb-1">Guided Demo</h2>
          <p className="text-xs text-white/50">A scripted, end-to-end walkthrough of the whole product — under two minutes, no live camera needed</p>
        </div>
        <PlayCircle size={16} className="text-white/30 shrink-0" />
      </Link>

      <Link
        to="/trust"
        className="flex items-center justify-between rounded-2xl border border-white/8 p-5 mb-5 max-w-lg bg-white/3 hover:border-white/20 transition-colors"
      >
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wide mb-1">Trust &amp; Compliance</h2>
          <p className="text-xs text-white/50">What this system does with video and evidence data, in plain language</p>
        </div>
        <ChevronRight size={16} className="text-white/30 shrink-0" />
      </Link>

      <div className="rounded-2xl border border-white/8 p-5 max-w-lg bg-white/3">
        <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Demo accounts</h2>
        <p className="text-[11px] mono text-white/35 mb-3">
          Role-based hall scoping applies consistently everywhere — Command Center, Examination Hall, Alerts, and Evidence Vault all filter through the same scope.
        </p>
        <div className="flex flex-col gap-2">
          {DEMO_ACCOUNTS.map((acct) => (
            <div key={acct.email} className="flex items-center justify-between text-xs px-3 py-2 rounded-lg border border-white/6">
              <span>{acct.name}</span>
              <span className="mono text-white/40">{acct.role === 'controller' ? 'all halls' : acct.hall}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
