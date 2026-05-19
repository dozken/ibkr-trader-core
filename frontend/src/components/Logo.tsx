import { cn } from '@/lib/utils'

interface LogoProps {
  className?: string
  size?: number
}

export function Logo({ className, size = 32 }: LogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn('shrink-0', className)}
      role="img"
      aria-labelledby="logo-title"
    >
      <title id="logo-title">IBKR Shariah Trader Logo</title>
      <defs>
        <clipPath id="star-clip">
          <path d="M16 2L20.5 6.5H25.5V11.5L30 16L25.5 20.5V25.5H20.5L16 30L11.5 25.5H6.5V20.5L2 16L6.5 11.5V6.5H11.5L16 2Z" />
        </clipPath>
      </defs>

      <g clipPath="url(#star-clip)">
        {/* Perfectly Symmetric Alternating Mosaic */}
        <path d="M16 16L16 0L27.3 4.7Z" fill="#064e3b" />
        <path d="M16 16L27.3 4.7L32 16Z" fill="#0f766e" />
        <path d="M16 16L32 16L27.3 27.3Z" fill="#064e3b" />
        <path d="M16 16L27.3 27.3L16 32Z" fill="#0f766e" />
        <path d="M16 16L16 32L4.7 27.3Z" fill="#064e3b" />
        <path d="M16 16L4.7 27.3L0 16Z" fill="#0f766e" />
        <path d="M16 16L0 16L4.7 4.7Z" fill="#064e3b" />
        <path d="M16 16L4.7 4.7L16 0Z" fill="#0f766e" />
      </g>

      {/* Symmetric Gold Border */}
      <path
        d="M16 2L20.5 6.5H25.5V11.5L30 16L25.5 20.5V25.5H20.5L16 30L11.5 25.5H6.5V20.5L2 16L6.5 11.5V6.5H11.5L16 2Z"
        fill="none"
        stroke="#fbbf24"
        strokeWidth="1.2"
      />

      {/* Point-Symmetric Balanced Trend Line */}
      {/* Coordinates: (8,22) to (12,18) is mirrored by (20,14) to (24,10) across center (16,16) */}
      <path
        d="M8 22L12 18L20 14L24 10"
        stroke="#fbbf24"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="24" cy="10" r="2" fill="white" />
    </svg>
  )
}
