import { Input as InputPrimitive } from '@base-ui/react/input'
import * as React from 'react'

import { cn } from '@/lib/utils'

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'> & { mono?: boolean }>(
  ({ className, type, mono, ...props }, ref) => {
  return (
    <InputPrimitive
      ref={ref}
      type={type}
      data-slot="input"
      className={cn('aegov-form-control', mono && 'font-mono', className)}
      {...props}
    />
  )
  },
)
Input.displayName = 'Input'

export { Input }
