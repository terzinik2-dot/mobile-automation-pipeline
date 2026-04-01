# Architecture — Mobile Automation Pipeline

## Overview

This pipeline automates a 4-stage Android workflow (Google Login → Play Store Install → MLBB Registration → Google Pay Purchase) in under 3 minutes, across cloud device farms or a local Android device.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Next.js Dashboard                          │
│              (Clerk Auth + Real-time WebSocket updates)             │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP / WebSocket
┌────────────────────────────▼────────────────────────────────────────┐
│                        FastAPI Server                               │
│             (SQLite persistence, background tasks)                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Python function call
┌────────────────────────────▼────────────────────────────────────────┐
│                    ScenarioOrchestrator                             │
│        (time budget, scenario sequencing, artifact collection)      │
└────┬──────────────────┬──────────────────────────────────┬──────────┘
     │                  │                                  │
     ▼                  ▼                                  ▼
┌─────────┐    ┌────────────────┐                ┌──────────────────┐
│Provider │    │ AppiumDriver   │                │  Scenarios       │
│Layer    │    │ (session mgmt) │                │  (4 stages)      │
│         │    └───────┬────────┘                └──────────────────┘
│BrowserS │            │                                ▲
│AWS Farm │    ┌───────▼────────┐                       │
│Local ADB│    │ MultiLayer     │─── uses ──────────────┘
└─────────┘    │ Locator Engine │
               └───────┬────────┘
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
         ┌────────┐ ┌───────┐ ┌────────┐
         │ DOM    │ │OpenCV │ │Tessera-│
         │Locator │ │Template│ │ct OCR  │
         └────────┘ └───────┘ └────────┘
```

---

## Layer-by-Layer Breakdown

### 1. Presentation Layer — Next.js Dashboard

- **Framework**: Next.js 14 (App Router)
- **Auth**: Clerk — drop-in auth with JWT session management
- **State**: SWR for server state, React hooks for UI state
- **Real-time**: WebSocket connection to FastAPI for live run status
- **Key pages**:
  - `/` — Landing page
  - `/dashboard` — Run list + "New Run" modal
  - `/dashboard/runs/[id]` — Step timeline, artifacts, locator analytics

### 2. API Layer — FastAPI

- **Bridge**: Translates Next.js HTTP calls into Python orchestrator calls
- **Background tasks**: `BackgroundTasks` for non-blocking run execution
- **Storage**: SQLite via async SQLAlchemy (`aiosqlite`)
- **WebSocket manager**: `ConnectionManager` tracks per-run subscribers
- **Run lifecycle**:
  1. POST `/api/v1/scenarios/run` → creates DB record, schedules background task
  2. Background task calls `ScenarioOrchestrator.run_async()`
  3. WS clients receive updates via `ws_manager.broadcast()`

### 3. Orchestration Layer

```
ScenarioOrchestrator
├── TimeBudgetManager       (180s total, per-step budgets)
├── DeviceProvider          (connects to device farm)
├── AppiumDriver            (Appium session lifecycle)
└── Scenario runner loop
    ├── GoogleLoginScenario       (30s budget)
    ├── PlayStoreInstallScenario  (40s budget)
    ├── MLBBRegistrationScenario  (40s budget)
    └── GooglePayPurchaseScenario (30s budget)
```

**Time budget design**:
- Total: 180s (3 minutes)
- Each step gets a hard timeout; overruns steal from the reserve
- `assert_step_alive()` is called inside polling loops
- `borrow_time()` allows dynamic reallocation if a step finishes early

### 4. Executor Layer

#### MultiLayerLocator (the crown jewel)

The 7-layer cascade:

```
1. resource-id          ← fastest, most stable. DB lookup.
2. text                 ← visible text. Breaks on i18n.
3. content-desc         ← accessibility description.
4. accessibility-id     ← Appium-specific. Good for ARIA.
5. XPath (semantic)     ← flexible but slow. ~200ms.
6. CV template match    ← OpenCV. Works without DOM.
7. OCR text detect      ← Tesseract. Last resort.
```

Each strategy is tried in order. The **first success wins** and subsequent strategies are skipped. Every attempt is logged with: layer, duration_ms, confidence, succeeded/failed. This telemetry powers the locator health analytics on the dashboard.

**Self-healing mechanics**:
- If a resource-id changes across app versions, text/OCR fallbacks kick in automatically
- Template images survive complete UI redesigns as long as the button appearance is similar
- The `wait_for_element()` method polls ALL strategies repeatedly until timeout

#### CVEngine

- `find_on_screen(template, screenshot)`: Multi-scale template matching (5 scale factors: 0.75→1.5x) handles resolution differences between devices
- `find_text_on_screen(text, screenshot)`: Tesseract with preprocessing pipeline (CLAHE → Gaussian blur → adaptive threshold)
- `screens_are_different(img1, img2)`: SSIM-based screen change detection for polling loops
- `preprocess()`: Image enhancement pipeline that significantly improves OCR accuracy on mobile screenshots

#### GestureEngine

Wraps Appium's W3C Actions API:
- `tap()` / `tap_at(x, y)` — DOM click or coordinate tap
- `swipe()` / `scroll_up()` / `scroll_down()` — scrolling
- `scroll_to_text()` — uses `UiScrollable` (on-device, fast) with manual loop fallback
- `type_text()` / `clear_and_type()` — with clipboard paste fallback

### 5. Provider Layer

```
DeviceProvider (abstract)
├── LocalDeviceProvider     ← starts Appium server, uses ADB
├── BrowserStackProvider    ← REST API calls to App Automate
└── AWSDeviceFarmProvider   ← boto3 for remote access sessions
```

All providers implement the same interface, so the orchestrator is provider-agnostic. Provider selection is a single env var (`DEVICE_PROVIDER`).

### 6. Scenario Layer

Each scenario is a subclass of `BaseScenario` and implements `run_steps()`.

`BaseScenario._execute_step()` provides:
- **Retry loop** (configurable, default 3 attempts)
- **Budget check** before each attempt
- **Screenshot capture** on failure/success
- **Step result recording** (timing, status, artifacts, locator attempts)

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Locator cascade | 7 layers DOM→CV→OCR | Self-healing without code changes |
| Time budget | Hard per-step + total | Guarantees sub-3-min completion |
| Provider abstraction | Strategy pattern | Swap providers with 1 env var |
| State storage | SQLite | Zero-setup, good enough for demo |
| Auth | Clerk | Drop-in, no user table needed |
| Real-time updates | WebSocket | Lower latency than polling |
| Background tasks | FastAPI BackgroundTasks | Simpler than Celery for this scope |

---

## Data Flow for a Run

```
User clicks "Start Run" in dashboard
    → POST /api/scenarios (Next.js API route)
    → POST /api/v1/scenarios/run (FastAPI)
    → Creates RunRecord in SQLite (status=PENDING)
    → Schedules run_pipeline_task (BackgroundTasks)
    → Returns { run_id, status: "pending", ws_url }

Dashboard opens WebSocket /ws/runs/{id}
    → Receives initial_state event

Background task starts:
    → Creates ScenarioOrchestrator
    → Calls orchestrator.run_async()
    → Updates DB status=RUNNING
    → Broadcasts status_change via WebSocket

ScenarioOrchestrator.run():
    → DeviceProvider.connect()
    → AppiumDriver.start_session()
    → For each scenario:
        → TimeBudget.start_step()
        → Scenario.run() → list[StepResult]
        → TimeBudget.end_step()
    → DeviceProvider.disconnect() (cleanup)
    → Returns RunResult

Background task on completion:
    → Updates DB with full RunResult JSON
    → Broadcasts run_complete via WebSocket

Dashboard receives run_complete:
    → SWR revalidates run detail
    → Renders timeline, artifacts, analytics
```

---

## Deployment

### Replit (default)

1. Import repo into Replit
2. Set env vars in Secrets
3. Run workflow "Start Full Stack"
4. Both FastAPI (port 8000) and Next.js (port 3000) start

### Self-hosted

```bash
# Python backend
pip install -r requirements.txt
python api_server.py

# Next.js dashboard
cd dashboard
npm install
npm run dev
```

### BrowserStack

Set `DEVICE_PROVIDER=browserstack` plus credentials. No local device needed.
