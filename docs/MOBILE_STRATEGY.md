# Mobile Strategy

## Decision: Mobile-First Web → Expo Native (later)

### Phase 1 — Now
Make current Vite/React web app mobile-first responsive.
- Bottom tab nav on mobile, top nav on `md+`
- Replace `<table>` with card stacks on small screens
- `grid-cols-2 md:grid-cols-4` for PortfolioHealth widgets
- `text-xl md:text-3xl` headings
- 44px min touch targets on buttons

### Phase 2 — When push notifications needed
Add Expo app. Restructure to:

```
ibkr-trader/
  backend/             ← untouched (FastAPI + ib_insync)
  apps/
    web/               ← renamed from frontend/
    mobile/            ← new Expo app
  packages/
    shared/            ← moved from apps/web/src/shared/
      types/
      routes.ts
  package.json         ← bun workspaces
```

`bun workspaces` (not pnpm):
```json
{
  "workspaces": ["apps/*", "packages/*"]
}
```

### What gets shared
- `useTrading` hook (TanStack Query, works in Expo)
- `types/trade.ts` (TypeScript, platform-agnostic)
- API fetch functions + ROUTES constants

### What splits by platform
- `Layout.tsx` → React Navigation bottom tabs on RN
- `CommandPalette.tsx` → web only, skip on RN
- Theme toggle → `useColorScheme` hook instead of `document.classList`

### Styling
NativeWind v4 — same Tailwind class names work on both web and RN. No style duplication.

### React Native migration blockers (resolve when adding Expo)
| Blocker | Fix |
|---------|-----|
| `<table>` | Card list / FlatList |
| `backdrop-blur-md` | Solid bg fallback |
| `window.addEventListener` | Guard with `Platform.OS === 'web'` |
| `document.documentElement` | Extract into ThemeProvider |
| Google Fonts `@import` | expo-font + useFonts |
| `min-h-screen` | flex: 1 |
| `fixed` modal overlay | RN Modal component |

---

## Network: IB Gateway Problem

IB Gateway runs on local Mac. FastAPI connects via `localhost:4001`. Phone can't reach Mac by default.

### Recommendation: Tailscale
- Install on Mac + phone
- Creates private VPN mesh — phone hits `mac.tailnet:8000` from anywhere (WiFi or cellular)
- Free for personal use, 10 min setup
- No port forwarding, no cloud infra needed

### Alternatives
| Option | When |
|--------|------|
| Same WiFi (`192.168.x.x`) | Dev only, home only |
| Tailscale | Personal use, recommended |
| VPS + IBC headless | Production / multi-user |
| Split backend (local agent + cloud relay) | Over-engineered, skip |

IBC = [IB Controller](https://github.com/IbcAlpha/IBC) — runs IB Gateway headless on a VPS if ever needed.

---

## Why not T3 Stack
T3/tRPC requires Node.js backend. This project uses FastAPI (Python) for `ib_insync` and compliance ML. Can't replace. Borrow the monorepo structure, skip tRPC.
