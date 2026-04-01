# Demo Video Script

## Video: Mobile Automation Pipeline — Full Run Demo

**Target length**: 4-5 minutes  
**Target audience**: COO, technical interviewers  
**Format**: Screen recording with narration

---

## Setup (before recording)

1. Start Appium: `appium --address 127.0.0.1 --port 4723`
2. Start API server: `python api_server.py`
3. Start dashboard: `cd dashboard && npm run dev`
4. Connect Android device or start emulator
5. Have browser open at `http://localhost:3000`
6. Pre-close any running apps on the device

---

## Script

### [00:00–00:15] Hook

**[Screen: Empty Android home screen, project code visible in editor]**

> "This is a complete mobile automation pipeline built in Python and Next.js.
> It logs into Google, installs Mobile Legends from the Play Store, registers
> an account in the game, and makes a Google Pay purchase — all automatically,
> in under 3 minutes."

---

### [00:15–00:45] Architecture overview

**[Screen: docs/ARCHITECTURE.md or hand-drawn diagram]**

> "The architecture has four layers:
>
> At the bottom, we connect to a device farm — BrowserStack, AWS Device Farm,
> or a local Android device via ADB. Swap providers with one environment variable.
>
> Above that, the execution layer: Appium drives the UI. But the real innovation
> is the multi-layer locator engine — a 7-layer cascade that automatically falls
> back from DOM lookups to OpenCV template matching to Tesseract OCR. So when
> the app updates and a button's resource-ID changes, the pipeline self-heals.
>
> The orchestrator enforces a 3-minute time budget: each step has a hard timeout,
> and we track which steps are eating into the budget in real time.
>
> On top, a Next.js dashboard with Clerk auth shows live status via WebSocket."

---

### [00:45–01:00] Start a run via dashboard

**[Screen: Navigate to http://localhost:3000/dashboard]**

> "Let's run the full pipeline. I'll click 'New Run'..."

**[Click "New Run" button]**

> "Select 'Local ADB Device' — this is my Pixel 7 plugged in via USB.
> Set the Google test account credentials.
> Test payment mode is on — no real money changes hands.
> Hit Start."

**[Click Start Run]**

---

### [01:00–01:15] Live status appears

**[Screen: Dashboard shows live status bar, run appears in list]**

> "The run starts immediately. We can see the time budget ticking down —
> 180 seconds total. The WebSocket connection gives us real-time updates
> without polling."

---

### [01:15–02:30] Watch the device

**[Screen: Split view — Android device screen + dashboard]**

**[01:15] Google Login phase starts**

> "First step: Google Login. The fast path checks if the account is already
> on the device — in this case it is, so we skip the full login flow and
> save 20 seconds."

**[01:30] Play Store phase starts**

> "Now Play Store install. The locator cascade opens the store, finds the
> search bar — using resource-id first — types the query, and identifies
> the correct MLBB result. Watch the download start."

**[01:55] MLBB Registration phase starts**

> "MLBB is installed. Now we launch it. These loading screens are the
> unpredictable part — MLBB can take 15-45 seconds to load on first run.
> The budget manager dynamically allocates remaining time to each subsequent
> step. We tap 'Google' for registration, select the pre-configured account,
> and accept the service agreement."

**[02:20] Google Pay phase starts**

> "In the lobby. Navigate to Shop, select the smallest diamond pack — 22
> diamonds — and tap Buy. Google Play Billing appears."

---

### [02:30–03:00] Purchase confirmation

**[Screen: Google Play Billing dialog with test payment]**

> "The billing dialog shows 'Test payment of US$0.99'. Because this account
> is a licensed tester for the app, no real charge happens. We confirm."

**[Screen: MLBB shows diamonds added]**

> "Purchase confirmed. Back in MLBB, the diamond balance updated.
> Full pipeline complete in..."

**[Screen: Dashboard shows 'completed' badge with timing]**

> "...163 seconds. Under the 3-minute budget."

---

### [03:00–03:45] Dashboard tour

**[Screen: Run detail page]**

> "Back in the dashboard, the run detail page shows the full step timeline.
> Each step has a status, duration, and which locator layer succeeded.
>
> Here you can see the locator analytics: 78% of lookups resolved via
> resource-id, 12% via text, 8% via CV template, 2% via OCR.
>
> If the CV layer starts being used more often, that's an early warning
> that the app's DOM structure is changing and locators need updating."

**[Screen: Scroll to artifacts section]**

> "Screenshots are captured on every step failure automatically. Videos
> are saved from the Appium recording. Everything is downloadable."

---

### [03:45–04:30] Code walkthrough (optional)

**[Screen: locator_engine.py]**

> "The locator engine is the core engineering. Each `find_element()` call
> accepts a list of strategies in priority order. The cascade tries each one
> in sequence with a per-strategy timeout. Every attempt is recorded for
> analytics.
>
> This means a locator like this..."

```python
element = locator.find_element([
    LocatorStrategy.by_id("com.android.vending:id/install"),
    LocatorStrategy.by_text("Install"),
    LocatorStrategy.by_template("templates/play_store_install_btn.png"),
    LocatorStrategy.by_ocr("Install"),
])
```

> "...automatically degrades through 4 strategies before giving up.
> The scenario author doesn't write any fallback logic — the engine handles it."

---

### [04:30–04:50] Closing

**[Screen: Project structure in editor]**

> "The full project: Python orchestrator, 4 scenario modules, 3 provider
> adapters, FastAPI server, and a Next.js dashboard. Everything deployable
> on Replit with the included config.
>
> Production extensions would add: parallel device runs, A/B scenario
> comparison, Slack alerting for failures, and a locator health score
> that auto-flags degrading strategies before they break in CI."

---

## Production Notes

- Record at 1920×1080 minimum
- Use OBS with two scenes: device view and code editor
- Mute device audio (MLBB has loud music)
- Pre-warm Appium server to avoid 30s startup delay in recording
- If recording takes >3min due to MLBB loading, consider editing the loading screen section
- Add lower-thirds: "[Layer 1: resource-id]", "[CV fallback active]", etc.
