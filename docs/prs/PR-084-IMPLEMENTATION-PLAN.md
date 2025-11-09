# PR-084 Implementation Plan

## Status: IN PROGRESS (0% → Implementation Started)

## Objective
Stand up production-grade Next.js 14 (App Router) web platform for marketing, docs, and shared UI library.

## Discovery Findings

### Current State
- ❌ `/frontend/web/` exists but empty (only admin/, performance/ subdirs)
- ❌ No `/frontend/web/package.json`
- ❌ No Next.js config files
- ❌ No app router pages
- ✅ `/frontend/packages/ui/` **CREATED** (7 components done)
- ❌ No PWA manifest/icons
- ❌ No backend telemetry endpoints
- ❌ No tests

### Conclusion
**PR-084 is 10% complete** (UI library created, web app not started)

---

## Implementation Phases

### Phase 1: Shared UI Library ✅ COMPLETE
**Created 7 components:**
1. ✅ `Card.tsx` - Containers with elevation/variants
2. ✅ `Badge.tsx` - Status indicators (success/warning/error/info)
3. ✅ `Button.tsx` - Primary CTAs with loading states
4. ✅ `Modal.tsx` - Overlay dialogs with keyboard nav
5. ✅ `Tabs.tsx` - Tabbed navigation (default/pills/underline)
6. ✅ `LineChart.tsx` - Time-series visualization (Recharts wrapper)
7. ✅ `Donut.tsx` - Percentage charts for win rate/allocation
8. ✅ `package.json` - Dependencies (react, recharts, clsx)
9. ✅ `tsconfig.json` - TypeScript config
10. ✅ `index.ts` - Package exports

### Phase 2: Next.js Web App Structure (IN PROGRESS)
**Required Files:**
```
/frontend/web/
  package.json                    # Next.js 14, React 18, Tailwind, @telebot/ui
  next.config.js                  # App Router, PWA, env vars
  tsconfig.json                   # TypeScript strict mode
  tailwind.config.ts              # Dark mode, custom theme
  postcss.config.js               # Tailwind processing

  app/
    layout.tsx                    # Root layout (dark mode provider, fonts, meta)
    page.tsx                      # Landing page (hero, features, CTA)
    pricing/page.tsx              # Pricing tiers (Free/Pro/Premium)
    performance/page.tsx          # Public performance stats (links to PR-047)
    legal/
      terms/page.tsx              # Terms of Service
      privacy/page.tsx            # Privacy Policy
      risk/page.tsx               # Risk Disclaimer
      cookies/page.tsx            # Cookie Policy
    not-found.tsx                 # 404 page

  components/
    Header.tsx                    # Navigation bar
    Footer.tsx                    # Links, legal, social
    ThemeToggle.tsx               # Dark/light mode switch

  lib/
    telemetry.ts                  # Track page views, CWV to backend

  public/
    manifest.json                 # PWA manifest
    icons/
      icon-192.png                # PWA icon
      icon-512.png                # PWA icon
      favicon.ico                 # Browser favicon
```

### Phase 3: Backend Telemetry Endpoints
**Required Files:**
```
backend/app/web/
  __init__.py
  routes.py                       # POST /api/v1/web/pageview, POST /api/v1/web/cwv

backend/app/observability/metrics.py  # Add web_page_view_total, web_cwv_lcp_seconds
```

**Metrics:**
- `web_page_view_total{route}` - Counter for page views
- `web_cwv_lcp_seconds` - Histogram for Largest Contentful Paint

### Phase 4: Tests (90%+ Coverage Target)
**Test Files:**
```
frontend/packages/ui/__tests__/
  Card.test.tsx                   # Rendering, variants, interactions
  Badge.test.tsx                  # Variants, sizes
  Button.test.tsx                 # Click, loading, disabled states
  Modal.test.tsx                  # Open/close, keyboard nav, overlay click
  Tabs.test.tsx                   # Tab switching, disabled tabs
  LineChart.test.tsx              # Data rendering, axes, tooltips
  Donut.test.tsx                  # Data rendering, center text, legend

frontend/web/__tests__/
  pages/
    index.test.tsx                # Landing page renders
    pricing.test.tsx              # Pricing tiers display
    legal.test.tsx                # Legal pages render
    not-found.test.tsx            # 404 page
  components/
    Header.test.tsx               # Navigation links
    Footer.test.tsx               # Footer links
    ThemeToggle.test.tsx          # Dark mode toggle
  lib/
    telemetry.test.ts             # Page view tracking, CWV reporting

backend/tests/
  test_web_telemetry.py           # POST endpoints, metric increments
```

**Test Coverage Requirements:**
- UI Components: ≥90% (rendering, props, interactions)
- Web Pages: ≥70% (SSR, navigation, meta tags)
- Backend Endpoints: ≥90% (request validation, metric recording)

### Phase 5: Integration & Verification
**Checklist:**
- [ ] `pnpm install` in `/frontend/packages/ui` succeeds
- [ ] `pnpm install` in `/frontend/web` succeeds
- [ ] `pnpm dev` starts Next.js dev server
- [ ] All pages render without errors
- [ ] Dark mode toggle works
- [ ] Navigation links functional
- [ ] Telemetry sends to backend
- [ ] PWA manifest validates
- [ ] Lighthouse score >90 (performance, accessibility, SEO)
- [ ] All tests passing (frontend + backend)
- [ ] Coverage ≥90% (backend), ≥70% (frontend)

### Phase 6: Documentation
**Required Docs:**
```
docs/prs/
  PR-084-IMPLEMENTATION-PLAN.md      # This file
  PR-084-IMPLEMENTATION-COMPLETE.md  # Final verification
  PR-084-ACCEPTANCE-CRITERIA.md      # Test results
  PR-084-BUSINESS-IMPACT.md          # Marketing value
```

---

## Acceptance Criteria (from spec)

### ✅ Deliverables
1. ✅ `/frontend/packages/ui/` with 7 components (Card, Badge, Button, Modal, Tabs, LineChart, Donut)
2. ⏳ `/frontend/web/` with Next.js 14 App Router
3. ⏳ Pages: `/`, `/pricing`, `/legal/*`, `/performance`
4. ⏳ PWA manifest + icons
5. ⏳ Backend telemetry endpoints
6. ⏳ Comprehensive tests

### Security
- ✅ No secrets in client bundle
- ⏳ API base from env (`NEXT_PUBLIC_API_BASE`)
- ⏳ PWA config from PR-002 settings

### Telemetry
- ⏳ `web_page_view_total{route}` counter
- ⏳ `web_cwv_lcp_seconds` histogram

### Tests
- ⏳ Rendering snapshots
- ⏳ Navigation links work
- ⏳ 404 route handling
- ⏳ Telemetry integration

### Verification
- ⏳ `pnpm dev` runs successfully
- ⏳ Pages render correctly
- ⏳ Lighthouse score >90

---

## Dependencies

### External Packages
**UI Library:**
- react@^18.2.0
- react-dom@^18.2.0
- clsx@^2.1.0
- recharts@^2.10.3

**Web App:**
- next@^14.0.0
- react@^18.2.0
- tailwindcss@^3.4.0
- @telebot/ui (local package)

### Internal Dependencies
- PR-002: Config settings for PWA name/description
- PR-047: Performance page backend (future integration)

---

## Risk & Mitigation

### Risk 1: TypeScript Errors in UI Library
**Impact**: Build failures
**Mitigation**: Install dependencies before final build test

### Risk 2: Next.js 14 App Router Complexity
**Impact**: Routing/rendering issues
**Mitigation**: Follow Next.js 14 docs exactly, use server/client components correctly

### Risk 3: Telemetry Backend Integration
**Impact**: Metrics not recorded
**Mitigation**: Create backend endpoints first, test with curl before frontend integration

### Risk 4: PWA Manifest Validation
**Impact**: Failed PWA install
**Mitigation**: Use PWA manifest validator, test in Chrome DevTools

---

## Next Steps

1. ✅ Create `/frontend/packages/ui/` (COMPLETE)
2. ⏳ Create `/frontend/web/package.json` and config files
3. ⏳ Implement all app router pages
4. ⏳ Create backend telemetry endpoints
5. ⏳ Write comprehensive test suites
6. ⏳ Run all tests, verify coverage
7. ⏳ Create final documentation
8. ⏳ Git commit + push

**Current Phase**: 2 (Next.js Web App Structure)
**Est. Completion Time**: 2-3 hours remaining
