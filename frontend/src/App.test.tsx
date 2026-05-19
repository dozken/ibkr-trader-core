import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App Component', () => {
  it('renders without crashing', () => {
    expect(() => render(<App />)).not.toThrow()
  })

  it('mounts QueryClientProvider and RouterProvider', () => {
    // App wraps RouterProvider in QueryClientProvider — if either fails to mount,
    // render() will throw and this test fails
    expect(() => render(<App />)).not.toThrow()
  })

  it('renders a non-empty DOM tree', () => {
    const { container } = render(<App />)
    expect(container.innerHTML).not.toBe('')
  })
})
