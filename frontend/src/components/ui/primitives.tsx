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

// Segmented toggle (e.g. tab switcher). Owns the pill/active styling.
export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T
  onChange: (v: T) => void
  options: ReadonlyArray<{ value: T; label: string }>
}) {
  return (
    <div className="flex bg-brand-base p-1 rounded-lg border border-brand-divider">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            'px-3 py-1 text-[10px] font-bold uppercase rounded-md transition-all',
            value === o.value
              ? 'bg-brand-primary text-white shadow-sm'
              : 'text-brand-light/70 hover:text-brand-light',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// Labelled toggle card: title + description on the left, a switch on the right.
export function Toggle({
  id,
  label,
  description,
  checked,
  onChange,
  tone = 'primary',
  children,
}: {
  id?: string
  label: ReactNode
  description?: ReactNode
  checked: boolean
  onChange: (v: boolean) => void
  tone?: 'primary' | 'accent'
  children?: ReactNode
}) {
  const card = tone === 'accent' ? 'border-brand-accent/30 bg-brand-accent/5' : 'border-brand-primary/20 bg-brand-primary/5'
  const on = tone === 'accent' ? 'bg-brand-accent' : 'bg-brand-primary'
  return (
    <div className={cn('p-4 rounded-xl border relative', card)}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1">
          <label htmlFor={id} className="block text-sm font-bold text-brand-light cursor-pointer">
            {label}
          </label>
          {description && (
            <p className="text-[11px] text-brand-light/70 mt-1 leading-relaxed">{description}</p>
          )}
        </div>
        <button
          type="button"
          role="switch"
          id={id}
          aria-checked={checked}
          onClick={() => onChange(!checked)}
          className={cn(
            'shrink-0 relative flex w-10 h-[22px] rounded-full cursor-pointer transition-colors duration-300',
            checked ? on : 'bg-brand-divider',
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 left-0.5 bg-white rounded-full h-[18px] w-[18px] shadow-sm transition-transform duration-300',
              checked && 'translate-x-[18px]',
            )}
          />
        </button>
      </div>
      {children}
    </div>
  )
}

// Form field: uppercase label + control + optional help text. Owns the
// label/help styling so feature forms pass only text + the control.
export function Field({
  label,
  htmlFor,
  help,
  children,
}: {
  label: string
  htmlFor?: string
  help?: ReactNode
  children: ReactNode
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="block text-xs font-bold text-brand-light/90 mb-1 tracking-widest uppercase"
      >
        {label}
      </label>
      {children}
      {help && <p className="text-xs text-brand-light/60 mt-1">{help}</p>}
    </div>
  )
}

// Inline banner/alert. Tone tints border+bg; pass href to make it a link
// (adds hover affordance + a `group` for trailing arrows).
type AlertTone = 'info' | 'success' | 'warning' | 'danger'
const ALERT_TONE: Record<AlertTone, string> = {
  info: 'border-brand-primary/40 bg-brand-primary/5',
  success: 'border-brand-success/30 bg-brand-success/5',
  warning: 'border-brand-warning/40 bg-brand-warning/5',
  danger: 'border-brand-danger/40 bg-brand-danger/5',
}
const ALERT_HOVER: Record<AlertTone, string> = {
  info: 'hover:bg-brand-primary/10 hover:border-brand-primary/60',
  success: 'hover:bg-brand-success/10 hover:border-brand-success/60',
  warning: 'hover:bg-brand-warning/10 hover:border-brand-warning/60',
  danger: 'hover:bg-brand-danger/10 hover:border-brand-danger/60',
}
export function Alert({
  tone = 'info',
  href,
  children,
}: {
  tone?: AlertTone
  href?: string
  children: ReactNode
}) {
  const cls = cn(
    'mb-4 flex items-center gap-3 rounded-lg border px-4 py-3 text-sm',
    ALERT_TONE[tone],
    href && cn('transition-colors group', ALERT_HOVER[tone]),
  )
  return href ? (
    <a href={href} className={cls}>
      {children}
    </a>
  ) : (
    <div className={cls}>{children}</div>
  )
}

// Small status tag (e.g. STALE DATA, CALM, BUY). Soft tinted by tone.
type PillTone = 'neutral' | 'primary' | 'success' | 'danger' | 'warning'
const PILL_TONE: Record<PillTone, string> = {
  neutral: 'bg-brand-light/5 border-brand-divider text-brand-light/70',
  primary: 'bg-brand-primary/10 border-brand-primary/25 text-brand-primary',
  success: 'bg-brand-success/10 border-brand-success/25 text-brand-success',
  danger: 'bg-brand-danger/10 border-brand-danger/25 text-brand-danger',
  warning: 'bg-brand-warning/10 border-brand-warning/25 text-brand-warning',
}
export function Pill({
  tone = 'neutral',
  title,
  children,
}: {
  tone?: PillTone
  title?: string
  children: ReactNode
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wide whitespace-nowrap',
        PILL_TONE[tone],
      )}
    >
      {children}
    </span>
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
