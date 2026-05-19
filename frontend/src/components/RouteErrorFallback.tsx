import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from './ui/button'

interface Props {
  error: Error
  reset: () => void
}

export function RouteErrorFallback({ error, reset }: Props) {
  const isNetworkError =
    error.message.includes('fetch') ||
    error.message.includes('NetworkError') ||
    error.message.includes('Failed to fetch')

  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4 text-center px-4">
      <AlertTriangle size={40} className="text-brand-warning" />
      <div className="space-y-1">
        <p className="font-bold text-brand-light text-lg">
          {isNetworkError ? 'Backend unreachable' : 'Something went wrong'}
        </p>
        <p className="text-sm text-brand-light/60 max-w-sm">
          {isNetworkError
            ? 'Cannot connect to the trading server. Make sure the backend is running on port 8000.'
            : error.message}
        </p>
      </div>
      <Button variant="outline" size="sm" onClick={reset} className="gap-2 mt-2">
        <RefreshCw size={13} /> Retry
      </Button>
    </div>
  )
}
