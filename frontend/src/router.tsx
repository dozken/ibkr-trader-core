import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import BacktestPageRaw from './features/ai/BacktestPage'
import ScannerPageRaw from './features/ai/ScannerPage'
import SignalLogPageRaw from './features/ai/SignalLogPage'
import SignalQualityPageRaw from './features/ai/SignalQualityPage'
import SignalsPageRaw from './features/ai/SignalsPage'
import { AIModuleGate } from './features/ai/AIModuleGate'

const BacktestPage = () => <AIModuleGate pageTitle="Backtest"><BacktestPageRaw /></AIModuleGate>
const ScannerPage = () => <AIModuleGate pageTitle="Scanner"><ScannerPageRaw /></AIModuleGate>
const SignalLogPage = () => <AIModuleGate pageTitle="Signal Log"><SignalLogPageRaw /></AIModuleGate>
const SignalQualityPage = () => <AIModuleGate pageTitle="Signal Quality"><SignalQualityPageRaw /></AIModuleGate>
const SignalsPage = () => <AIModuleGate pageTitle="Signals"><SignalsPageRaw /></AIModuleGate>
import AuditPage from './features/compliance/AuditPage'
import ScreeningPage from './features/compliance/ScreeningPage'
import FAQPage from './features/faq/FAQPage'
import Dashboard from './features/portfolio/DashboardPage'
import AccountsPage from './features/settings/AccountsPage'
import Settings from './features/settings/Settings'
import ZakatPage from './features/zakat/ZakatPage'
import Layout from './Layout'
import { RouteErrorFallback } from './components/RouteErrorFallback'

const rootRoute = createRootRoute({ component: Layout, errorComponent: RouteErrorFallback })

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: Dashboard,
})
const screeningRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/screening',
  component: ScreeningPage,
})
const scannerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/scanner',
  component: ScannerPage,
  validateSearch: (search: Record<string, unknown>) => ({
    region: typeof search.region === 'string' ? search.region : undefined,
  }),
})
const signalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/signals',
  component: SignalsPage,
})
const auditRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/audit',
  component: AuditPage,
})
const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: Settings,
})
const zakatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/zakat',
  component: ZakatPage,
})
const backtestRoute = createRoute({ getParentRoute: () => rootRoute, path: '/backtest', component: BacktestPage })
const signalQualityRoute = createRoute({ getParentRoute: () => rootRoute, path: '/signal-quality', component: SignalQualityPage })
const signalLogRoute = createRoute({ getParentRoute: () => rootRoute, path: '/signal-log', component: SignalLogPage })
const faqRoute = createRoute({ getParentRoute: () => rootRoute, path: '/faq', component: FAQPage })
const accountsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/accounts',
  component: AccountsPage,
})

const routeTree = rootRoute.addChildren([
  dashboardRoute,
  screeningRoute,
  scannerRoute,
  signalsRoute,
  auditRoute,
  zakatRoute,
  settingsRoute,
  accountsRoute,
  backtestRoute,
  signalQualityRoute,
  signalLogRoute,
  faqRoute,
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
