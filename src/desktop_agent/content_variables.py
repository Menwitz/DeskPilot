"""YAML content variable loading and safe placeholder resolution."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

_VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


class ContentVariableError(ValueError):
    """Raised when content variables cannot be loaded or resolved safely."""


@dataclass(frozen=True)
class ResolvedTemplate:
    """Resolved text plus variable names used to produce it."""

    value: str | None
    variable_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContentVariables:
    """Redacted content payload used to compile site playbook steps."""

    values: dict[str, str]
    source_path: Path | None = None

    def resolve(self, value: str | None) -> ResolvedTemplate:
        if value is None:
            return ResolvedTemplate(None)

        variable_names = tuple(dict.fromkeys(_VARIABLE_PATTERN.findall(value)))
        if not variable_names:
            return ResolvedTemplate(value)

        missing = tuple(name for name in variable_names if name not in self.values)
        if missing:
            raise ContentVariableError(
                "missing content variable(s): " + ", ".join(missing),
            )

        resolved = _VARIABLE_PATTERN.sub(
            lambda match: self.values[match.group(1)],
            value,
        )
        return ResolvedTemplate(resolved, variable_names)

    def fingerprint(self, variable_names: tuple[str, ...]) -> str:
        """Return a stable fingerprint for the variables a task actually uses."""

        payload = {
            name: self.values[name]
            for name in sorted(set(variable_names))
            if name in self.values
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8",
        )
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_content_variables(path: Path | None) -> ContentVariables:
    """Load a YAML variable file or return an empty variable set."""

    if path is None:
        return ContentVariables({})
    if not path.exists():
        raise ContentVariableError(f"content variables file not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ContentVariableError("content variables file must contain a mapping")
    data = cast(dict[str, object], loaded)
    variables_value = data.get("variables", data)
    if not isinstance(variables_value, dict):
        raise ContentVariableError("variables must be a mapping")
    values = {
        str(key): _variable_value_to_string(value)
        for key, value in cast(dict[object, object], variables_value).items()
    }
    if any(not key.strip() for key in values):
        raise ContentVariableError("content variable names must not be blank")
    return ContentVariables(values=values, source_path=path)


def _variable_value_to_string(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, list) and all(
        isinstance(item, str | int | float | bool) for item in value
    ):
        return " ".join(_variable_value_to_string(item) for item in value)
    raise ContentVariableError(
        "content variable values must be strings, numbers, booleans, or lists of "
        "those values",
    )
