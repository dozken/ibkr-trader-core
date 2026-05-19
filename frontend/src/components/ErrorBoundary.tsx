import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from './ui/button'

interface Props {
  children: React.ReactNode
  title?: string
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <AlertTriangle size={36} className="text-brand-warning" />
        <div>
          <p className="font-bold text-brand-light">{this.props.title ?? 'Something went wrong'}</p>
          <p className="text-xs text-brand-light/50 mt-1 font-mono max-w-sm break-all">{error.message}</p>
        </div>
        <Button variant="outline" size="sm" onClick={this.reset} className="gap-2">
          <RefreshCw size={13} /> Retry
        </Button>
      </div>
    )
  }
}
