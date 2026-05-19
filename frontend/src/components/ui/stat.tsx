import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Text } from './text'

type Tone = 'default' | 'success' | 'danger' | 'warning' | 'accent' | 'primary'

const TONE_CLASS: Record<Tone, string> = {
  default: 'text-brand-light',
  success: 'text-brand-success',
  danger: 'text-brand-danger',
  warning: 'text-brand-warning',
  accent: 'text-brand-accent',
  primary: 'text-brand-primary',
}

interface StatProps {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: Tone
  align?: 'left' | 'center' | 'right'
  className?: string
}

export function Stat({ label, value, sub, tone = 'default', align = 'left', className }: StatProps) {
  const alignClass = align === 'center' ? 'text-center items-center' : align === 'right' ? 'text-right items-end' : 'text-left items-start'
  return (
    <div className={cn('flex flex-col gap-0.5', alignClass, className)}>
      <Text variant="eyebrow">{label}</Text>
      <p className={cn('t-stat', TONE_CLASS[tone])}>{value}</p>
      {sub && <Text variant="tiny" className="opacity-80">{sub}</Text>}
    </div>
  )
}

interface MetricCardProps extends StatProps {
  icon?: ReactNode
  href?: string
  onClick?: () => void
}

export function MetricCard({ icon, href, onClick, className, ...stat }: MetricCardProps) {
  const interactive = href || onClick
  const content = (
    <div className={cn(
      'card p-4 flex flex-col gap-1.5 transition-colors',
      interactive && 'cursor-pointer hover:border-brand-primary/40',
      className,
    )}>
      {icon && <div className="text-brand-primary/70 mb-1">{icon}</div>}
      <Stat {...stat} />
    </div>
  )
  if (href) {
    return <a href={href}>{content}</a>
  }
  if (onClick) {
    return <button type="button" onClick={onClick} className="text-left w-full">{content}</button>
  }
  return content
}

interface KVProps {
  label: ReactNode
  value: ReactNode
  tone?: Tone
  mono?: boolean
}

export function KV({ label, value, tone = 'default', mono = true }: KVProps) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <Text variant="meta">{label}</Text>
      <p className={cn('text-sm font-semibold', mono && 't-num', TONE_CLASS[tone])}>{value}</p>
    </div>
  )
}
