"""PyInstaller entry point for the DeskPilot console executable."""

from __future__ import annotations

from desktop_agent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
