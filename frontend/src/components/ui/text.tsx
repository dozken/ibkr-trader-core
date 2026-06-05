import { forwardRef } from 'react'
import type { ElementType, HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Variant = 'hero' | 'h1' | 'h2' | 'h3' | 'stat' | 'body' | 'meta' | 'tiny' | 'eyebrow'

const VARIANT_CLASS: Record<Variant, string> = {
  hero: 't-hero',
  h1: 't-h1',
  h2: 't-h2',
  h3: 't-h3',
  stat: 't-stat',
  body: 't-body',
  meta: 't-meta',
  tiny: 't-tiny',
  eyebrow: 't-eyebrow',
}

const DEFAULT_TAG: Record<Variant, ElementType> = {
  hero: 'p',
  h1: 'h1',
  h2: 'h2',
  h3: 'h3',
  stat: 'p',
  body: 'p',
  meta: 'p',
  tiny: 'p',
  eyebrow: 'p',
}

type Tone = 'default' | 'muted' | 'subtle' | 'primary' | 'success' | 'danger' | 'warning'

const TONE_CLASS: Record<Tone, string> = {
  default: '',
  muted: 'text-brand-light/70',
  subtle: 'text-brand-light/50',
  primary: 'text-brand-primary',
  success: 'text-brand-success',
  danger: 'text-brand-danger',
  warning: 'text-brand-warning',
}

interface TextProps extends HTMLAttributes<HTMLElement> {
  variant?: Variant
  tone?: Tone
  as?: ElementType
  mono?: boolean
  children?: ReactNode
}

export const Text = forwardRef<HTMLElement, TextProps>(
  ({ variant = 'body', tone = 'default', as, mono, className, children, ...props }, ref) => {
    const Tag = (as ?? DEFAULT_TAG[variant]) as ElementType
    return (
      <Tag
        ref={ref as never}
        className={cn(VARIANT_CLASS[variant], TONE_CLASS[tone], mono && 't-num', className)}
        {...props}
      >
        {children}
      </Tag>
    )
  },
)
Text.displayName = 'Text'

export function Eyebrow(props: Omit<TextProps, 'variant'>) {
  return <Text variant="eyebrow" {...props} />
}
