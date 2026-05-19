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

// 7. Standard vertical stack
// Always uses gap-4 for vertical lists of items
export function Stack({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn("flex flex-col gap-4", className)} {...props} />
}
