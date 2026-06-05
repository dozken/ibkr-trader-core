import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type IconTone = 'primary' | 'success' | 'danger' | 'warning' | 'muted'
const ICON_TONE: Record<IconTone, string> = {
  primary: 'text-brand-primary',
  success: 'text-brand-success',
  danger: 'text-brand-danger',
  warning: 'text-brand-warning',
  muted: 'text-brand-light/60',
}

// Page/section heading with an optional leading icon. Owns the type + icon
// styling so features pass only level, icon, and text.
export function Heading({
  level = 1,
  icon: Icon,
  iconTone = 'primary',
  children,
  className,
}: {
  level?: 1 | 2 | 3
  icon?: LucideIcon
  iconTone?: IconTone
  children: ReactNode
  className?: string
}) {
  const Tag = (['h1', 'h2', 'h3'] as const)[level - 1]
  const size = level === 1 ? 28 : level === 2 ? 20 : 16
  return (
    <Tag className={cn(`t-h${level}`, 'flex items-center gap-2', className)}>
      {Icon && <Icon size={size} className={ICON_TONE[iconTone]} />}
      {children}
    </Tag>
  )
}

// Connection / liveness indicator: dot + uppercase mono label.
export function StatusDot({
  ok,
  pulse = true,
  children,
}: {
  ok: boolean
  pulse?: boolean
  children: ReactNode
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span
        className={cn(
          'w-2 h-2 rounded-full',
          ok ? 'bg-brand-success' : 'bg-brand-danger',
          ok && pulse && 'animate-pulse',
        )}
      />
      <span className="text-brand-light/70 font-mono uppercase">{children}</span>
    </span>
  )
}
