from pathlib import Path

from desktop_agent.config import LocalModelConfig
from desktop_agent.local_models import (
    LocalModelStatus,
    OllamaLocalModelProvider,
    write_local_model_status_report,
)


def test_ollama_status_skips_probe_when_disabled_by_default() -> None:
    calls: list[str] = []

    def get_json(url: str, timeout_seconds: float) -> dict[str, object]:
        _ = timeout_seconds
        calls.append(url)
        return {"models": []}

    status = OllamaLocalModelProvider(
        LocalModelConfig(enabled=False),
        get_json=get_json,
    ).status()

    assert status.status == "disabled"
    assert status.available is False
    assert status.models == ()
    assert calls == []


def test_ollama_status_lists_models_from_local_tags_endpoint() -> None:
    calls: list[tuple[str, float]] = []

    def get_json(url: str, timeout_seconds: float) -> dict[str, object]:
        calls.append((url, timeout_seconds))
        return {
            "models": [
                {
                    "name": "llama3.2:latest",
                    "modified_at": "2026-05-16T00:00:00Z",
                    "size": 2_019_393_189,
                    "digest": "sha256:abc",
                },
            ],
        }

    status = OllamaLocalModelProvider(
        LocalModelConfig(enabled=True, request_timeout_seconds=2.5),
        get_json=get_json,
    ).status()

    assert status.status == "available"
    assert status.available is True
    assert status.metadata()["model_count"] == 1
    assert status.models[0].name == "llama3.2:latest"
    assert calls == [("http://127.0.0.1:11434/api/tags", 2.5)]


def test_ollama_list_models_can_probe_disabled_config_on_explicit_request() -> None:
    def get_json(url: str, timeout_seconds: float) -> dict[str, object]:
        _ = (url, timeout_seconds)
        return {"models": [{"model": "mistral:latest"}]}

    models = OllamaLocalModelProvider(
        LocalModelConfig(enabled=False),
        get_json=get_json,
    ).list_models()

    assert [model.name for model in models] == ["mistral:latest"]


def test_ollama_status_reports_unavailable_for_invalid_tags_payload() -> None:
    def get_json(url: str, timeout_seconds: float) -> dict[str, object]:
        _ = (url, timeout_seconds)
        return {"unexpected": []}

    status = OllamaLocalModelProvider(
        LocalModelConfig(enabled=True),
        get_json=get_json,
    ).status()

    assert status.status == "unavailable"
    assert status.available is False
    assert status.error is not None
    assert "models list" in status.error


def test_local_model_status_report_writes_monitoring_json(tmp_path: Path) -> None:
    output_path = tmp_path / "reports" / "local-model-status.json"

    written_path = write_local_model_status_report(
        LocalModelStatus(
            enabled=True,
            provider="ollama",
            endpoint="http://127.0.0.1:11434",
            status="available",
            available=True,
        ),
        output_path,
    )

    assert written_path == output_path
    assert '"provider": "ollama"' in output_path.read_text(encoding="utf-8")
    assert '"status": "available"' in output_path.read_text(encoding="utf-8")
