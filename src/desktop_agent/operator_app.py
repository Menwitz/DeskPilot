"""Native operator app entry point for optional PySide6 packaging."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib.util import find_spec

from desktop_agent.operator_app_shell import (
    OperatorAppUnavailableError,
    launch_operator_app,
    render_operator_app_shell_text,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the native operator app entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.check:
        return _check_app_environment()
    if args.describe_shell:
        print(render_operator_app_shell_text(), end="")
        return 0
    return _launch_app(argv)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deskpilot-app")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the app entry point and optional PySide6 availability",
    )
    parser.add_argument(
        "--describe-shell",
        action="store_true",
        help="print the app shell pages without launching PySide6",
    )
    return parser


def _check_app_environment() -> int:
    pyside_status = "available" if find_spec("PySide6") is not None else "missing"
    print("deskpilot-app entry point: ok")
    print(f"PySide6: {pyside_status}")
    return 0


def _launch_app(argv: Sequence[str] | None) -> int:
    try:
        return launch_operator_app(argv)
    except OperatorAppUnavailableError as exc:
        print(str(exc))
        return 2
