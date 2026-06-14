import * as React from 'react'
import { cn } from '@/lib/utils'

// 1. The outermost wrapper for every page
export function Page({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn("page-container", className)} {...props} />
}

// 2. Standard page header (Title + Actions)
// Always uses mb-8, flex, and gap-4 for consistent spacing
export function PageHeader({ className, ...props }: React.ComponentProps<'header'>) {
  return (
    <header 
      className={cn("mb-8 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4", className)} 
      {...props} 
    />
  )
}

// 3. Standard vertical spacing between major sections (e.g., between cards/tables)
// Always uses mb-8 to keep vertical rhythm consistent
export function PageSection({ className, ...props }: React.ComponentProps<'section'>) {
  return <section className={cn("mb-8 last:mb-0", className)} {...props} />
}

// 4. Standard grid for summary cards
// Always uses gap-4. Automatically handles mobile (1 col) vs desktop (3 or 4 cols).
export function CardGrid({ cols = 3, className, ...props }: React.ComponentProps<'div'> & { cols?: 3 | 4 }) {
  return (
    <div 
      className={cn(
        "grid grid-cols-1 gap-4", 
        cols === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-4",
        className
      )} 
      {...props} 
    />
  )
}

// 5. Standard row for buttons/controls
// Always uses gap-3 for medium spacing between interactive elements
export function ActionRow({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn("flex items-center gap-3", className)} {...props} />
}

// 6. Standard row for icon + text or tight groupings
// Always uses gap-1.5 for tight associations
export function InfoRow({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn("flex items-center gap-1.5", className)} {...props} />
}

// ── Spacing/alignment scales (semantic props → tailwind, owned here) ────────
type Gap = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl'
const GAP: Record<Gap, string> = {
  none: 'gap-0', xs: 'gap-1', sm: 'gap-2', md: 'gap-4', lg: 'gap-6', xl: 'gap-8',
}
type Align = 'start' | 'center' | 'end' | 'baseline' | 'stretch'
const ALIGN: Record<Align, string> = {
  start: 'items-start', center: 'items-center', end: 'items-end',
  baseline: 'items-baseline', stretch: 'items-stretch',
}
type Justify = 'start' | 'center' | 'end' | 'between'
const JUSTIFY: Record<Justify, string> = {
  start: 'justify-start', center: 'justify-center', end: 'justify-end', between: 'justify-between',
}

// 7. Vertical stack — gap defaults to md (gap-4)
export function Stack({
  gap = 'md', align, className, ...props
}: React.ComponentProps<'div'> & { gap?: Gap; align?: Align }) {
  return <div className={cn('flex flex-col', GAP[gap], align && ALIGN[align], className)} {...props} />
}

// 8. Horizontal cluster — wraps, with gap/align/justify and optional self-start.
export function Cluster({
  gap = 'sm', align = 'center', justify, wrap = true, selfStart, className, ...props
}: React.ComponentProps<'div'> & {
  gap?: Gap; align?: Align; justify?: Justify; wrap?: boolean; selfStart?: boolean
}) {
  return (
    <div
      className={cn(
        'flex', wrap && 'flex-wrap', GAP[gap], ALIGN[align],
        justify && JUSTIFY[justify], selfStart && 'self-start', className,
      )}
      {...props}
    />
  )
}
