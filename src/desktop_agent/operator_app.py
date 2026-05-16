"""Native operator app import target for optional PySide6 packaging."""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Return a clear placeholder until the Phase 8 app shell is implemented."""
    _ = argv
    print(
        "DeskPilot native operator app packaging is available; "
        "the app shell is implemented in the next Phase 8 tasks.",
    )
    return 2
