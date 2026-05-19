/**
 * Gate that probes /api/ai/ml-status. If endpoint absent (404 / network error)
 * the wrapped page is replaced with a banner pointing to the open-core split.
 *
 * The public ibkr-trader-core build does not ship the AI module; private forks
 * mount it via the `STRATEGY_CLASS` env var.
 */
import { useQuery } from '@tanstack/react-query'
import { Brain, ExternalLink } from 'lucide-react'
import type React from 'react'

import { Page, PageSection } from '@/components/ui/layout'
import { API_BASE } from '../../shared/routes'

async function probeAI(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/ai/ml-status`)
    if (res.status === 404) return false
    return res.ok
  } catch {
    return false
  }
}

export function AIModuleGate({ children, pageTitle }: { children: React.ReactNode; pageTitle: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['ai-module-available'],
    queryFn: probeAI,
    staleTime: 60_000,
    retry: false,
  })

  if (isLoading) return null
  if (data === false) {
    return (
      <Page>
        <header className="mb-8 flex items-center gap-3">
          <Brain className="w-6 h-6 text-amber-200" />
          <h1 className="text-2xl font-semibold">{pageTitle}</h1>
        </header>
        <PageSection>
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-6 space-y-3">
            <h3 className="text-lg font-semibold text-amber-200">AI module not installed</h3>
            <p className="text-sm text-brand-light/80">
              This page needs the private AI scoring + RL module that lives outside the open-core framework.
              The public <code className="text-xs bg-brand-base/40 px-1.5 py-0.5 rounded">ibkr-trader-core</code> build
              ships with the bundled <strong>SMA crossover</strong> reference strategy instead.
            </p>
            <p className="text-sm text-brand-light/80">
              To plug in your own alpha, implement the{' '}
              <code className="text-xs bg-brand-base/40 px-1.5 py-0.5 rounded">Strategy</code> interface and set
              <code className="text-xs bg-brand-base/40 px-1.5 py-0.5 rounded ml-1">STRATEGY_CLASS</code> via env.
            </p>
            <a
              href="https://github.com/dozken/ibkr-trader-core#plug-in-your-own-strategy"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-amber-200 hover:text-amber-100"
            >
              Docs <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </PageSection>
      </Page>
    )
  }
  return <>{children}</>
}
