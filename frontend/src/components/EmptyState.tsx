import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

// Part 5 (product-conviction pass, 2026-08-21): a designed empty state,
// not a blank screen or a bare line of text — every empty state names
// what's missing and what to do about it.
export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon: LucideIcon
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center text-center py-16 px-6">
      <div className="w-12 h-12 rounded-2xl flex items-center justify-center bg-white/6 mb-4">
        <Icon size={20} className="text-white/35" />
      </div>
      <h3 className="text-sm font-bold mb-1.5">{title}</h3>
      <p className="text-xs text-white/45 max-w-xs leading-relaxed mb-4">{body}</p>
      {action}
    </div>
  )
}
