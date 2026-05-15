"""Website navigation playbook contracts and validation helpers."""

from __future__ import annotations


class SitePlaybookValidationError(ValueError):
    """Raised when a website navigation playbook is invalid."""
