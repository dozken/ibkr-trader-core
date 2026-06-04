import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { queryClient } from './queryClient'
import { router } from './router'
import { AccountProvider } from './features/trading/context/AccountContext'
import { ThemeProvider } from './lib/ThemeContext'

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AccountProvider>
          <RouterProvider router={router} />
        </AccountProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
