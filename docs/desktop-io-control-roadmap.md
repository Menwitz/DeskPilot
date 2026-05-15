# Desktop I/O Control Roadmap

## Positioning

DeskPilot should be framed as a low-level desktop input/output controller, not a
human mimic. Smooth pointer paths and keyboard cadence are compatibility tools
for normal desktop software, not the product promise.

Product promise:

> DeskPilot controls ordinary desktop software through the real OS cursor,
> keyboard, and visual feedback loop, without requiring app-specific APIs,
> browser automation hooks, or fixture windows.

Core loop:

```text
Observe -> Interpret -> Decide -> Actuate -> Verify
   ^                                      |
   |______________________________________|
```

## North Star

- [ ] DeskPilot can operate an owned, unlocked Windows desktop through real
      screen observation and low-level OS input.
- [ ] Every action is traceable from intent to physical input to observed
      result.
- [ ] The system can explain what it saw, what it decided, what it sent, and
      whether the desktop state changed as expected.
- [ ] Demos show real cursor and keyboard control against real apps, not fake
      cursors, test-only canvases, or browser automation APIs.

## Non-Goals

- [ ] Do not market this as "human behavior simulation."
- [ ] Do not optimize for stealth, CAPTCHA bypass, rate-limit evasion, or
      anti-bot circumvention.
- [ ] Do not depend on Playwright, browser DevTools, LinkedIn APIs, or app
      plugins for the proof demos.
- [ ] Do not use rendered fixture cursors as proof of control.
- [ ] Do not perform account-mutating actions in public demo flows.

## Phase 1: Prove Real Desktop Actuation

- [x] Add a real Windows input controller for the main OS cursor.
- [x] Use `SendInput` for mouse movement, mouse buttons, wheel, and keyboard.
- [x] Record intended pointer frames and actual `GetCursorPos` readbacks.
- [x] Add `desktop-agent demo-input`.
- [x] Keep `desktop-agent demo-mouse` as a compatibility alias.
- [x] Demonstrate global desktop movement, desktop drag-selection, Notepad
      launch, and typed text.
- [x] Write `traces/<timestamp>-input-demo/input-demo-report.json`.
- [ ] Manually verify in the Windows VM that the visible cursor moves globally.
- [ ] Manually verify in the Windows VM that Notepad receives typed text.
- [ ] Add the manual result to release notes or acceptance notes.

Acceptance:

- [ ] Real Windows cursor visibly moves across the desktop.
- [ ] Drag-selection rectangle appears on the desktop.
- [ ] Notepad opens as a real native app.
- [ ] Typed text appears in Notepad.
- [ ] Trace contains planned point, actual point, drift, timestamp, and action.

## Phase 2: Prove Real Browser I/O

- [x] Add `desktop-agent demo-linkedin`.
- [x] Launch Microsoft Edge as a real process.
- [x] Navigate through the address bar using low-level keyboard input.
- [x] Scroll the loaded page with low-level wheel input.
- [x] Use browser Find to highlight page text.
- [x] Write `traces/<timestamp>-linkedin-demo/linkedin-demo-report.json`.
- [ ] Manually verify in the Windows VM that Edge opens in a fresh window.
- [ ] Manually verify that LinkedIn loads from address-bar input.
- [ ] Manually verify that page scroll is visible.
- [ ] Manually verify that browser Find highlights `LinkedIn`.

Acceptance:

- [ ] No browser automation API is used.
- [ ] No credentials are entered.
- [ ] No account-mutating LinkedIn action is performed.
- [ ] Trace includes launch metadata, keyboard cadence, cursor readbacks, wheel
      events, and final status.

## Phase 3: Close The Observe-Actuate-Verify Loop

- [ ] Capture pre-action screenshots for each real action.
- [ ] Capture post-action screenshots for each real action.
- [ ] Attach active window title before and after each action.
- [ ] Attach cursor readback before and after each action.
- [ ] Add verification result per step: `passed`, `failed`, or `inconclusive`.
- [ ] Store verification evidence alongside input evidence in one trace report.
- [ ] Add a trace replay view that summarizes observation, action, and
      verification per step.

Acceptance:

- [ ] A failed click can show what was visible before the click.
- [ ] A failed type can show which window had focus.
- [ ] A failed scroll can show whether the viewport moved.
- [ ] A passed action includes concrete evidence of the resulting desktop state.

## Phase 4: Real Target Acquisition

- [ ] Use screenshot, OCR, UIA, and window metadata to identify visible targets.
- [ ] Convert detected target bounds into physical desktop coordinates.
- [ ] Move the real cursor to the selected target.
- [ ] Re-read cursor position after movement and measure drift.
- [ ] Click only after target confidence and allowed-window checks pass.
- [ ] Reobserve after click and verify expected state change.
- [ ] Record why competing candidates were rejected.

Acceptance:

- [ ] The system can explain why it clicked one visible target instead of
      another.
- [ ] Target coordinates are auditable from screenshot bounds to physical point.
- [ ] A missed target produces a diagnostic trace, not just `missed_target`.

## Phase 5: Desktop I/O Task Model

- [ ] Define a first-class action schema for low-level desktop I/O:
      `move`, `click`, `drag`, `wheel`, `type`, `hotkey`, `wait`, `observe`,
      `verify`.
- [ ] Make each action idempotence and reversibility explicit where possible.
- [ ] Add per-action safety metadata: app scope, data sensitivity, mutation risk,
      and approval requirement.
- [ ] Support explicit "manual handoff" points when confidence is low.
- [ ] Add emergency-stop checks between every low-level action.

Acceptance:

- [ ] A task author can tell which actions mutate state.
- [ ] The runner blocks risky actions without approval.
- [ ] The operator can stop the loop between steps.

## Phase 6: Demonstration Ladder

- [x] Native proof: Notepad text entry.
- [x] Browser proof: Edge plus LinkedIn navigation, scroll, and Find.
- [ ] Local web fixture proof: identify and submit a form through real I/O.
- [ ] Native app proof: interact with a Windows settings or calculator flow.
- [ ] Mixed proof: switch between Edge and Notepad with real Alt+Tab or taskbar
      selection.
- [ ] Recovery proof: handle a loading delay, stale observation, or missed
      target with reobserve and retry.
- [ ] Audit proof: replay a trace and explain every input/output transition.

## Phase 7: Product Hardening

- [ ] Add Windows smoke tests gated by `DESKPILOT_WINDOWS_SMOKE=1`.
- [ ] Add a manual VM acceptance checklist for each demo command.
- [ ] Add trace schema versioning.
- [ ] Add a trace redaction policy for screenshots and typed text.
- [ ] Add a config flag to disable text capture in traces.
- [ ] Add bounds checks for multi-monitor and scaled displays.
- [ ] Add foreground-window checks before typing.
- [ ] Add focus verification after launching apps.
- [ ] Add timeout diagnostics that include last screen, cursor, and active
      window state.

## Open Decisions

- [ ] Should real browser demos use a public logged-out page by default, or a
      local deterministic page first?
- [ ] Should traces store full screenshots by default, or require an explicit
      opt-in when screenshots may contain sensitive data?
- [ ] Should the controller expose absolute coordinates directly to task YAML,
      or only through target acquisition?
- [ ] Should browser Find be treated as a demo-only action or a reusable
      verification primitive?
- [ ] Should low-level input demos close the apps they open, or leave them open
      for inspection?

## Next Three Concrete PRs

- [ ] Add post-action screenshot capture and active-window metadata to
      `demo-input` and `demo-linkedin` traces.
- [ ] Add a Windows smoke checklist command that verifies Edge launch, Notepad
      typing, cursor readback, and trace file creation.
- [ ] Replace `missed_target`-only failures with a diagnostic bundle containing
      screenshot, OCR candidates, UIA candidates, chosen target, and cursor
      readback.
