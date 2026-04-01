# Decision Log — Mobile Automation Pipeline

Each entry records a significant architectural or implementation decision, the options considered, and the reasoning for the chosen path.

---

## DEC-001: Multi-Layer Locator Cascade

**Date**: 2024-04  
**Status**: Implemented

### Context
Mobile UIs change constantly — MLBB updates weekly, Play Store redesigns quarterly. A locator that breaks on every update creates maintenance burden that kills ROI.

### Options Considered
1. **XPath only** — Simple but brittle. A single class rename breaks everything.
2. **Accessibility IDs only** — Stable but incomplete; many elements lack proper a11y labels.
3. **Image-based only (Appium Eyes, SikuliX)** — Accurate but slow (300-800ms per lookup) and breaks on resolution changes.
4. **Multi-layer cascade** — Try fast/stable first, fall back to slow/flexible.

### Decision
Implemented 7-layer cascade (resource-id → text → content-desc → accessibility → XPath → CV → OCR). Each layer adds ~100-500ms only when the previous layer fails. Typical runs use layers 1-2, so performance is not impacted. Locator analytics let us identify brittle elements quickly.

### Trade-offs
- **+** Self-healing without code changes in most cases
- **+** Analytics show which locators are degrading
- **-** More code complexity in `locator_engine.py`
- **-** CV/OCR layers require OpenCV + Tesseract installed

---

## DEC-002: Time Budget Architecture

**Date**: 2024-04  
**Status**: Implemented

### Context
The task requires completion in under 3 minutes. Without enforcement, a single slow step (MLBB loading, slow network) can blow the budget silently.

### Options Considered
1. **Single global timeout** — Simple but gives no per-step visibility or recovery.
2. **Per-step soft warnings** — Logs warnings but doesn't enforce hard stops.
3. **Per-step hard deadlines with total budget** — Each step gets a budget slice; `assert_step_alive()` is checked in polling loops.

### Decision
`TimeBudgetManager` with per-step budgets that sum to 180s. Steps check `assert_step_alive()` before each polling iteration. The `borrow_time()` API allows fast steps to donate budget to slow ones. Total expiry triggers `TimeoutError` that propagates up.

### Budget allocation
```
Device connect:    30s (provider SLA)
Google Login:      30s (fast path: already signed in = ~2s)
Play Store:        40s (download is the variable)
MLBB Registration: 40s (loading screens are unpredictable)
Google Pay:        30s (payment processing SLA)
Cleanup:           10s
────────────────
Total:            180s
```

---

## DEC-003: Device Farm Provider Strategy Pattern

**Date**: 2024-04  
**Status**: Implemented

### Context
COO-level decision: different teams may use different providers. The code should not be coupled to any single provider.

### Options Considered
1. **Hard-code BrowserStack** — Fastest to implement, zero flexibility.
2. **Config flag with if/else** — Works but pollutes orchestrator with provider-specific logic.
3. **Abstract base class + factory** — Clean separation, easy to add providers.

### Decision
`DeviceProvider` abstract base class with `connect()`, `disconnect()`, `get_appium_url()`, `get_video()`, `get_logs()`. Provider is selected by `DEVICE_PROVIDER` env var and dynamically imported in the orchestrator. Adding a new provider requires only one new file.

---

## DEC-004: Google Login Strategy

**Date**: 2024-04  
**Status**: Implemented

### Context
Google login is the most risky step. Google has anti-automation measures, CAPTCHA, 2FA, and frequently changes the login UI.

### Options Considered
1. **Pre-configured device** — Device already has Google account. App tests skip the login flow entirely.
2. **Settings > Add Account flow** — Full UI automation of the account addition flow.
3. **ADB am broadcast** — Use Android's AccountManager directly via shell. Most reliable but requires root or special permissions.
4. **Google Sign-In SDK** — App handles it; we just select account from picker.

### Decision
Fast-path first (check if account already on device), then full Settings > Add Account flow as fallback. The check uses Play Store accessibility as a signal rather than AccountManager (which requires root on most devices).

For MLBB specifically, we tap the "Google" login button which triggers Android's built-in account picker — no credentials typed, most stable approach.

### 2FA Handling
2FA prompt is detected and handled via notification shade inspection. If no notification is found, we wait 15s for user/admin to approve externally. This is intentional: fully automating 2FA approval would require Google admin privileges or test account setup.

---

## DEC-005: SQLite vs PostgreSQL for Run Storage

**Date**: 2024-04  
**Status**: Implemented (SQLite)

### Context
The API server needs to persist run records between restarts.

### Options Considered
1. **In-memory dict** — Zero setup. Lost on restart. Bad for demo.
2. **SQLite** — File-based, zero config, `aiosqlite` for async.
3. **PostgreSQL** — Production-grade but requires external service.
4. **Redis** — Good for queues, overkill for structured run records.

### Decision
SQLite with `aiosqlite`. Zero infrastructure, works on Replit, easy to inspect with `sqlite3` CLI. Run data is stored as JSON blobs in `result_json` column — no schema migrations needed for the demo. If this went to production, the migration to PostgreSQL is straightforward (just change `DATABASE_URL`).

---

## DEC-006: Next.js vs Pure HTML Dashboard

**Date**: 2024-04  
**Status**: Implemented (Next.js)

### Context
The dashboard needs Clerk auth, real-time updates, and a professional UI.

### Options Considered
1. **Pure HTML + vanilla JS** — Minimal dependencies. Hard to build polished UX.
2. **Vue + Vite** — Fast, but Clerk has better Next.js support.
3. **Next.js 14 (App Router)** — First-class Clerk support, server components, easy API routes.

### Decision
Next.js 14 with App Router. Clerk's `@clerk/nextjs` package is purpose-built for this. App Router server components keep the bundle lean. SWR handles the polling and WebSocket-triggered revalidation pattern cleanly.

---

## DEC-007: Appium 2.x vs 1.x

**Date**: 2024-04  
**Status**: Implemented (Appium 2.x)

### Context
Appium 2.x was released in late 2022. BrowserStack and AWS Device Farm support both.

### Options Considered
1. **Appium 1.x** — Wider existing tooling, some tutorials use it.
2. **Appium 2.x** — Plugin system, `@appium/uiautomator2-driver` as separate package, W3C Actions API fully supported.

### Decision
Appium 2.x. W3C Actions API (used by GestureEngine) is only properly supported in 2.x. The plugin architecture also allows adding image comparison and other plugins without changing core code.

---

## DEC-008: OpenCV Multi-Scale Template Matching

**Date**: 2024-04  
**Status**: Implemented

### Context
Device farms may not provide the exact same device as local testing. Pixel density, display scaling, and screenshot resolution differ.

### Options Considered
1. **Fixed-scale template matching** — Fast but breaks when screenshot resolution differs by >10%.
2. **Multi-scale matching (5 scales)** — Tries 0.75x, 0.85x, 1.0x, 1.15x, 1.25x, 1.5x. Returns best match.
3. **Feature-based matching (ORB/SIFT)** — Rotation and scale invariant, but overkill for UI element matching and slower.

### Decision
Multi-scale `cv2.TM_CCOEFF_NORMED` with 5 scale factors. Handles ±50% resolution difference gracefully. For UI elements (buttons, icons), normalized cross-correlation is reliable and ~20ms per scale, so total matching is ~100ms worst case — acceptable for a locator fallback.

---

## DEC-009: Google Pay Purchase Safety

**Date**: 2024-04  
**Status**: Implemented

### Context
Automating a real financial transaction requires multiple safeguards.

### Decision
1. `GOOGLE_PAY_TEST_MODE=true` is the default — uses Google Play test cards
2. `LIVE_PAYMENT` mode requires explicit `--live-payment` CLI flag
3. Pre-purchase assertion logs a CRITICAL warning if test mode is off
4. Licensed tester setup is documented in README

The pipeline targets the **smallest** available diamond pack to minimize any accidental charge.
