import { Button as ButtonPrimitive } from '@base-ui/react/button'
import { cva, type VariantProps } from 'class-variance-authority'

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

function Button({
  className,
  variant = 'default',
  size = 'default',
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button }
