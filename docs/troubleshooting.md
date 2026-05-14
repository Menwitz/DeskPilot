# Troubleshooting

## Desktop Session Is Locked

DeskPilot v1 requires an unlocked, logged-in desktop. Unlock the Windows
session, make the fixture window visible, and rerun the task.

## Active Window Is Rejected

Check the task `allowed_windows` list and the visible window title. The title
must match exactly in v1.

## OCR Or Image Matching Finds No Target

Increase fixture visibility, avoid overlapping windows, confirm DPI scaling,
and inspect the trace screenshots, OCR JSON, overlays, and candidate rankings.

## Packaged Executable Fails

Run `deskpilot.exe --help` first. If that works, run a `dry-run` with
`packaging/default-config.yaml`. For real desktop execution, confirm the
Windows optional dependencies are installed and the session is unlocked.
