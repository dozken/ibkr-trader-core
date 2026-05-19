import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import React from 'react'
import { describe, expect, it } from 'vitest'
import Settings from './Settings'

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    React.createElement(QueryClientProvider, { client: qc }, React.createElement(Settings)),
  )
}

describe('Settings Component', () => {
  it('renders all four sections', () => {
    renderSettings()
    expect(screen.getByText('Allocation')).toBeInTheDocument()
    expect(screen.getByText('Shariah Compliance')).toBeInTheDocument()
    expect(screen.getByText('AI & Execution')).toBeInTheDocument()
    expect(screen.getByText('Alerts & Safety')).toBeInTheDocument()
  })

  it('renders key allocation fields', () => {
    renderSettings()
    expect(screen.getByLabelText(/Minimum Trade Size/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Max Position Size/i)).toBeInTheDocument()
  })
})
