import { Button as ButtonPrimitive } from '@base-ui/react/button'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2, type LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

// AEGOV (UAE Design System) button classes. `.aegov-btn` = primary (aegold).
// Variants/sizes map to AEGOV modifiers; danger/success/warning are local
// helpers that set AEGOV's --btn-* vars to aered/aegreen/camel (see index.css).
const buttonVariants = cva('aegov-btn', {
  variants: {
    variant: {
      default: '',
      outline: 'btn-outline',
      secondary: 'btn-secondary',
      ghost: 'btn-ghost',
      destructive: 'btn-danger',
      link: 'btn-link',
      success: 'btn-success',
      warning: 'btn-warning',
    },
    size: {
      default: '',
      xs: 'btn-xs',
      sm: 'btn-sm',
      lg: 'btn-lg',
      icon: 'btn-icon',
      'icon-xs': 'btn-icon btn-xs',
      'icon-sm': 'btn-icon btn-sm',
      'icon-lg': 'btn-icon btn-lg',
    },
  },
  defaultVariants: {
    variant: 'default',
    size: 'default',
  },
})

const ICON_SIZE: Record<string, number> = {
  xs: 13, sm: 14, default: 16, lg: 16,
  icon: 16, 'icon-xs': 13, 'icon-sm': 14, 'icon-lg': 16,
}

// `icon` renders a leading lucide icon (sized to the button); `loading` swaps
// it for a spinner and disables. Lets features avoid inline <Icon size className/>.
function Button({
  className,
  variant = 'default',
  size = 'default',
  icon: Icon,
  loading = false,
  disabled,
  children,
  ...props
}: ButtonPrimitive.Props &
  VariantProps<typeof buttonVariants> & {
    icon?: LucideIcon
    loading?: boolean
  }) {
  const sz = ICON_SIZE[size ?? 'default'] ?? 16
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 size={sz} className="animate-spin" /> : Icon ? <Icon size={sz} /> : null}
      {children}
    </ButtonPrimitive>
  )
}

export { Button }
