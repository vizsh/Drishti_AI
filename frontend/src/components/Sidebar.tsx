import { NavLink } from 'react-router-dom'
import { LayoutGrid, Grid3x3, Bell, FolderOpen, BarChart3, Settings, LogOut, Radar } from 'lucide-react'
import { useAuth } from '../state/AuthContext'

const NAV_ITEMS = [
  { to: '/command-center', label: 'Command Center', icon: LayoutGrid },
  { to: '/overview', label: 'Examination Hall', icon: Grid3x3 },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/evidence-vault', label: 'Evidence Vault', icon: FolderOpen },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const { user, logout } = useAuth()
  if (!user) return null

  return (
    // Icon-only below lg (Part 6 tablet check, 2026-08-21) — a fixed 224px
    // sidebar was eating ~30% of a 768px tablet viewport permanently. An
    // invigilator is mobile in the room on a tablet, not desk-bound at a
    // wide monitor, so this collapses to a narrow icon rail instead of
    // assuming desktop width.
    <aside className="w-16 lg:w-56 shrink-0 h-screen sticky top-0 border-r border-white/8 flex flex-col py-6 px-2 lg:px-3">
      <div className="flex items-center justify-center lg:justify-start gap-2.5 px-0 lg:px-2 mb-8">
        {/* Brand mark is deliberately neutral, not orange (Step 0 audit,
            2026-08-21) — the old orange/amber gradient shared a hue with
            the critical-alert color, so the eye got trained all session to
            see "orange" as house style, diluting it as an urgency signal. */}
        <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 bg-white/10">
          <Radar size={16} className="text-ink" strokeWidth={2.4} />
        </div>
        <span className="hidden lg:inline text-sm font-bold">KINESIS<span className="text-white/40">.</span></span>
      </div>

      <nav className="flex flex-col gap-1 flex-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={item.label}
            className={({ isActive }) =>
              `flex items-center justify-center lg:justify-start gap-2.5 px-0 lg:px-3 py-2.5 rounded-lg text-xs transition-colors ${
                isActive ? 'bg-white/8 text-white' : 'text-white/45 hover:text-white/75 hover:bg-white/4'
              }`
            }
          >
            <item.icon size={16} />
            <span className="hidden lg:inline">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/8 pt-4 px-0 lg:px-2">
        <div className="flex items-center justify-center lg:justify-start gap-2.5 mb-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 bg-white/10"
            title={`${user.name} — ${user.role === 'controller' ? 'Controller' : `Invigilator, ${user.hall}`}`}
          >
            {user.initials}
          </div>
          <div className="min-w-0 hidden lg:block">
            <div className="text-xs font-semibold truncate">{user.name}</div>
            <div className="text-[10px] mono text-white/40 truncate">
              {user.role === 'controller' ? 'Controller · all halls' : `Invigilator · ${user.hall}`}
            </div>
          </div>
        </div>
        <button
          onClick={logout}
          title="Log out"
          className="flex items-center justify-center lg:justify-start gap-2 w-full px-0 lg:px-3 py-2 rounded-lg text-xs text-white/45 hover:text-white/80 hover:bg-white/4"
        >
          <LogOut size={14} /> <span className="hidden lg:inline">Log out</span>
        </button>
      </div>
    </aside>
  )
}
