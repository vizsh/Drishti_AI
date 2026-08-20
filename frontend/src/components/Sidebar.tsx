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
    <aside className="w-56 shrink-0 h-screen sticky top-0 border-r border-white/8 flex flex-col py-6 px-3">
      <div className="flex items-center gap-2.5 px-2 mb-8">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'linear-gradient(135deg, #ff5a36, #ffb648)' }}>
          <Radar size={16} color="#060608" strokeWidth={2.4} />
        </div>
        <span className="text-sm font-bold">KINESIS<span style={{ color: '#ff5a36' }}>.</span></span>
      </div>

      <nav className="flex flex-col gap-1 flex-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] transition-colors ${
                isActive ? 'bg-white/8 text-white' : 'text-white/45 hover:text-white/75 hover:bg-white/4'
              }`
            }
          >
            <item.icon size={16} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/8 pt-4 px-2">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0" style={{ background: '#ffffff12' }}>
            {user.initials}
          </div>
          <div className="min-w-0">
            <div className="text-[12px] font-semibold truncate">{user.name}</div>
            <div className="text-[10px] mono text-white/40 truncate">
              {user.role === 'controller' ? 'Controller · all halls' : `Invigilator · ${user.hall}`}
            </div>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-[12px] text-white/45 hover:text-white/80 hover:bg-white/4"
        >
          <LogOut size={14} /> Log out
        </button>
      </div>
    </aside>
  )
}
