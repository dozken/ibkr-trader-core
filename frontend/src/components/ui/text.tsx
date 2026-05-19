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

interface TextProps extends HTMLAttributes<HTMLElement> {
  variant?: Variant
  as?: ElementType
  mono?: boolean
  children?: ReactNode
}

export const Text = forwardRef<HTMLElement, TextProps>(
  ({ variant = 'body', as, mono, className, children, ...props }, ref) => {
    const Tag = (as ?? DEFAULT_TAG[variant]) as ElementType
    return (
      <Tag
        ref={ref as never}
        className={cn(VARIANT_CLASS[variant], mono && 't-num', className)}
        {...props}
      >
        {children}
      </Tag>
    )
  },
)
Text.displayName = 'Text'

export function Heading({ level = 1, ...rest }: { level?: 1 | 2 | 3 } & Omit<TextProps, 'variant'>) {
  const v: Variant = level === 1 ? 'h1' : level === 2 ? 'h2' : 'h3'
  return <Text variant={v} {...rest} />
}

export function Eyebrow(props: Omit<TextProps, 'variant'>) {
  return <Text variant="eyebrow" {...props} />
}
