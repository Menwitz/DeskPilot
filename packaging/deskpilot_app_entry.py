"""PyInstaller entry point for the optional DeskPilot native operator app."""

from __future__ import annotations

from desktop_agent.operator_app import main

if __name__ == "__main__":
    raise SystemExit(main())
