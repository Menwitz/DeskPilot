# Recovery Fixture Proof

`desktop-agent proof recovery-fixture` is a Windows-only proof command for a
delayed disabled-control recovery workflow. It opens a generated local browser
fixture in Microsoft Edge, clicks a disabled target before it is ready, waits for
the fixture to enable the control, retries the same target with real cursor
input, then uses browser Find to verify the result text.

The command does not use Playwright, DevTools, DOM automation, browser APIs, or
a synthetic cursor. The recovery path is pre-authored and visible in the trace
metadata as a wait-then-retry policy.

## Run

From the repository root on an owned, unlocked Windows desktop:

```powershell
uv run desktop-agent proof recovery-fixture --countdown-seconds 5
```

Useful options:

```powershell
uv run desktop-agent proof recovery-fixture `
  --trace-root traces `
  --random-seed 20260515 `
  --movement-smoothness 0.85 `
  --countdown-seconds 5 `
  --page-load-seconds 0.5 `
  --ready-delay-seconds 1.5 `
  --recovery-wait-seconds 2.0 `
  --result-text "Recovery fixture clicked"
```

## Expected Behavior

- Edge opens the generated recovery fixture.
- The target button starts disabled.
- DeskPilot clicks the disabled target as the recovery probe.
- DeskPilot waits for the ready delay.
- The target button becomes enabled.
- DeskPilot retries the same target and the page writes the result text.
- Edge Find searches for the configured result text.
- A report and proof manifest are written under
  `traces/<timestamp>-recovery-fixture/`.

## Expected Artifacts

- `recovery-fixture.html`
- `recovery-fixture-report.json`
- `proof-manifest.json`
- `action-log.jsonl`
- `screenshots/*.png`

Review the bundle with:

```powershell
uv run desktop-agent proof replay traces/<timestamp>-recovery-fixture
```

Use [Windows Proof Evidence Checklist](windows-proof-evidence-checklist.md) to
record the video, trace, manifest, screenshots, replay output, and reviewer
decision.

## Acceptance

- [ ] The command exits with `status: passed`.
- [ ] Video shows the target initially disabled.
- [ ] Video shows the first probe click before the target is ready.
- [ ] Video shows the wait interval and target becoming ready.
- [ ] Video shows the retry click succeeding.
- [ ] Video shows Edge Find searching the result text.
- [ ] `recovery-fixture-report.json` includes recovery reason, policy, action,
      retry index, and post-action evidence.
- [ ] `action-log.jsonl` includes the same recovery metadata for the probe,
      wait, and retry steps.
- [ ] `proof-manifest.json` links command, environment metadata, report, action
      log, screenshots, and trace directory.
- [ ] Reviewer confirms no browser API, DOM automation, or synthetic cursor was
      used.
