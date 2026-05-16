"""Local model health and inventory helpers for optional Ollama use."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from desktop_agent.config import LocalModelConfig

JsonObject = Mapping[str, object]
JsonGetter = Callable[[str, float], JsonObject]


@dataclass(frozen=True)
class LocalModelInfo:
    """One model advertised by the local Ollama tags endpoint."""

    name: str
    modified_at: str | None = None
    size: int | None = None
    digest: str | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "modified_at": self.modified_at,
            "size": self.size,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class LocalModelStatus:
    """Health snapshot for the configured local model provider."""

    enabled: bool
    provider: str
    endpoint: str
    status: str
    available: bool
    models: tuple[LocalModelInfo, ...] = ()
    error: str | None = None
    checked_path: str = "/api/tags"

    def metadata(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "status": self.status,
            "available": self.available,
            "model_count": len(self.models),
            "models": [model.metadata() for model in self.models],
            "error": self.error,
            "checked_path": self.checked_path,
        }


class OllamaLocalModelProvider:
    """Explicit health and model-listing adapter for local Ollama."""

    def __init__(
        self,
        config: LocalModelConfig,
        *,
        get_json: JsonGetter | None = None,
    ) -> None:
        self._config = config
        self._get_json = get_json or _default_get_json

    def status(self, *, probe_when_disabled: bool = False) -> LocalModelStatus:
        """Return disabled, available, or unavailable without executing actions."""
        if not self._config.enabled and not probe_when_disabled:
            return LocalModelStatus(
                enabled=False,
                provider=self._config.provider,
                endpoint=self._config.endpoint,
                status="disabled",
                available=False,
            )

        try:
            payload = self._get_json(
                _ollama_tags_url(self._config.endpoint),
                self._config.request_timeout_seconds,
            )
            models = _models_from_ollama_tags(payload)
        except (HTTPError, OSError, TimeoutError, URLError, ValueError) as exc:
            return LocalModelStatus(
                enabled=self._config.enabled,
                provider=self._config.provider,
                endpoint=self._config.endpoint,
                status="unavailable",
                available=False,
                error=str(exc),
            )

        return LocalModelStatus(
            enabled=self._config.enabled,
            provider=self._config.provider,
            endpoint=self._config.endpoint,
            status="available",
            available=True,
            models=models,
        )

    def list_models(self) -> tuple[LocalModelInfo, ...]:
        """Probe Ollama and return advertised models or raise on unavailability."""
        status = self.status(probe_when_disabled=True)
        if not status.available:
            raise LocalModelProviderError(status.error or "local model unavailable")
        return status.models


class LocalModelProviderError(RuntimeError):
    """Raised when an explicit local model inventory request cannot complete."""


def write_local_model_status_report(
    status: LocalModelStatus,
    output_path: Path,
) -> Path:
    """Write a local JSON report for model-health monitoring and trace review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(status.metadata(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _default_get_json(url: str, timeout_seconds: float) -> JsonObject:
    request = Request(url, headers={"Accept": "application/json"})
    response = urlopen(request, timeout=timeout_seconds)
    try:
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        response.close()
    if not isinstance(payload, dict):
        raise ValueError("Ollama response must be a JSON object")
    return cast(JsonObject, payload)


def _ollama_tags_url(endpoint: str) -> str:
    return urljoin(endpoint.rstrip("/") + "/", "api/tags")


def _models_from_ollama_tags(payload: JsonObject) -> tuple[LocalModelInfo, ...]:
    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        raise ValueError("Ollama /api/tags response must contain a models list")

    models: list[LocalModelInfo] = []
    for index, raw_model in enumerate(raw_models):
        if not isinstance(raw_model, Mapping):
            raise ValueError(f"Ollama model entry {index} must be an object")
        model = cast(Mapping[str, Any], raw_model)
        name = _string_field(model, "name") or _string_field(model, "model")
        if name is None:
            raise ValueError(f"Ollama model entry {index} is missing name")
        models.append(
            LocalModelInfo(
                name=name,
                modified_at=_string_field(model, "modified_at"),
                size=_optional_int_field(model, "size"),
                digest=_string_field(model, "digest"),
            ),
        )
    return tuple(models)


def _string_field(model: Mapping[str, Any], key: str) -> str | None:
    value = model.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _optional_int_field(model: Mapping[str, Any], key: str) -> int | None:
    value = model.get(key)
    if isinstance(value, int):
        return value
    return None
