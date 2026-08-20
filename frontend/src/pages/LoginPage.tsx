import { useState, type FormEvent } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Radar, Lock } from 'lucide-react'
import { useAuth, DEMO_ACCOUNTS } from '../state/AuthContext'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const result = login(email, password)
    if (!result.ok) {
      setError(result.error ?? 'Login failed')
      return
    }
    const from = (location.state as { from?: string })?.from ?? '/command-center'
    navigate(from, { replace: true })
  }

  function quickFill(acctEmail: string) {
    setEmail(acctEmail)
    setPassword('demo1234')
    setError(null)
  }

  return (
    <div className="noise-bg grid-texture min-h-screen flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm rounded-3xl border border-white/10 p-8"
        style={{ background: 'linear-gradient(180deg, #ffffff08, #ffffff02)' }}
      >
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #ff5a36, #ffb648)' }}>
            <Radar size={18} color="#060608" strokeWidth={2.4} />
          </div>
          <div>
            <h1 className="text-lg font-bold leading-none">KINESIS<span style={{ color: '#ff5a36' }}>.</span></h1>
            <p className="text-[10px] mono uppercase tracking-widest text-white/40 mt-0.5">exam behaviour monitor</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="text-[11px] mono uppercase tracking-wide text-white/40">
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1 w-full bg-transparent border border-white/15 rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-white/40"
              placeholder="you@kinesis.ai"
            />
          </label>
          <label className="text-[11px] mono uppercase tracking-wide text-white/40">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="mt-1 w-full bg-transparent border border-white/15 rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-white/40"
              placeholder="••••••••"
            />
          </label>
          {error && <p className="text-xs mono" style={{ color: '#ff5a36' }}>{error}</p>}
          <button
            type="submit"
            className="mt-2 flex items-center justify-center gap-2 text-sm font-bold px-4 py-2.5 rounded-lg"
            style={{ background: 'linear-gradient(135deg, #ff5a36, #ffb648)', color: '#060608' }}
          >
            <Lock size={14} /> Sign in
          </button>
        </form>

        <div className="mt-6 pt-6 border-t border-white/8">
          <p className="text-[10px] mono uppercase tracking-widest text-white/30 mb-2">demo accounts</p>
          <div className="flex flex-col gap-1.5">
            {DEMO_ACCOUNTS.map((acct) => (
              <button
                key={acct.email}
                onClick={() => quickFill(acct.email)}
                className="text-left text-[11px] mono px-3 py-2 rounded-lg border border-white/8 hover:border-white/25 text-white/50 hover:text-white/80"
              >
                {acct.name} — {acct.role === 'controller' ? 'Controller (all halls)' : `Invigilator (${acct.hall})`}
                <br />
                <span className="text-white/30">{acct.email}</span>
              </button>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
