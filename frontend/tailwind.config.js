/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          base: 'rgb(var(--color-base) / <alpha-value>)',
          surface: 'rgb(var(--color-surface) / <alpha-value>)',
          elevated: 'rgb(var(--color-elevated) / <alpha-value>)',
          divider: 'rgb(var(--color-divider) / <alpha-value>)',
          muted: 'rgb(var(--color-muted) / <alpha-value>)',
          light: 'rgb(var(--color-light) / <alpha-value>)',
          primary: 'rgb(var(--color-primary) / <alpha-value>)',
          'primary-hover': 'rgb(var(--color-primary-hover) / <alpha-value>)',
          success: 'rgb(var(--color-success) / <alpha-value>)',
          danger: 'rgb(var(--color-danger) / <alpha-value>)',
          warning: 'rgb(var(--color-warning) / <alpha-value>)',
          accent: 'rgb(var(--color-accent) / <alpha-value>)',
          'accent-light': 'rgb(var(--color-accent-light) / <alpha-value>)',
        },
        /* shadcn semantic tokens — map to brand vars */
        background: 'rgb(var(--color-base) / <alpha-value>)',
        foreground: 'rgb(var(--color-light) / <alpha-value>)',
        border: 'rgb(var(--color-divider) / <alpha-value>)',
        input: 'rgb(var(--color-divider) / <alpha-value>)',
        ring: 'rgb(var(--color-accent) / <alpha-value>)',
        primary: {
          DEFAULT: 'rgb(var(--color-primary) / <alpha-value>)',
          foreground: 'rgb(255 255 255 / <alpha-value>)',
        },
        destructive: {
          DEFAULT: 'rgb(var(--color-danger) / <alpha-value>)',
          foreground: 'rgb(255 255 255 / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--color-elevated) / <alpha-value>)',
          foreground: 'rgb(var(--color-light) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'rgb(var(--color-elevated) / <alpha-value>)',
          foreground: 'rgb(var(--color-muted) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--color-accent) / <alpha-value>)',
          foreground: 'rgb(var(--color-light) / <alpha-value>)',
        },
        card: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          foreground: 'rgb(var(--color-light) / <alpha-value>)',
        },
        popover: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          foreground: 'rgb(var(--color-light) / <alpha-value>)',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        'glow-primary':
          '0 0 20px rgba(var(--color-primary),0.35), 0 0 40px rgba(var(--color-primary),0.12)',
        'glow-accent':
          '0 0 20px rgba(var(--color-accent),0.4),   0 0 40px rgba(var(--color-accent),0.15)',
        'glow-success': '0 0 20px rgba(var(--color-success),0.3)',
        'glow-danger': '0 0 20px rgba(var(--color-danger),0.4)',
        card: '0 8px 40px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.06)',
      },
    },
  },
  plugins: [],
}
