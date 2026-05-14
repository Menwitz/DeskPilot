# Windows UI Automation

The Windows UIA layer uses `pywinauto` behind a dynamic adapter so the core
package can still be developed and tested on non-Windows hosts. Install the
Windows extra on a Windows machine:

```bash
uv sync --extra dev --extra windows
```

## Adapter Responsibilities

- Detect active window title, process ID, and process name when available.
- Extract visible UIA elements from the active window.
- Normalize element name, control type, bounds, enabled state, and visible state.
- Convert usable UIA elements into shared `ElementCandidate` objects.
- Return no candidates when UIA is unavailable instead of crashing the planner.
- Write UIA tree snapshots as JSON for inspection and reports.

UIA candidates receive a high default confidence and the shared selector prefers
them over OCR or image candidates when confidence values are close.
