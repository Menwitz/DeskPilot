# Screen Layer

The screen layer captures local screenshots through `mss` and normalizes all
candidate coordinates before actuation uses them.

## Capture Scope

v1 captures the full primary monitor by default. When multiple monitors are
detected and `primary_monitor_only` is enabled, the observation includes a clear
warning. Region capture is implemented as a reusable primitive for active-window
and template-search workflows.

Each Windows observation also attempts to attach local desktop context metadata:
the foreground process ID and process name, plus the focused Win32 control handle,
label, and class name when those APIs are available. The observer does not record
process command lines.

## Coordinate Spaces

Screenshot coordinates are pixel positions in captured images. Physical
coordinates are the positions used by mouse input APIs. DPI scaling can make
those spaces differ, so the screen layer exposes conversion helpers for points
and bounds.

## Desktop Availability

On Windows, the observer checks that a foreground window is available before
capturing. Capture failures are converted into `ScreenUnavailableError` so the
planner and CLI can abort cleanly with a useful report instead of crashing.
