import json
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.recorder import RecorderController


def test_recorder_controller_runs_control_state_machine(tmp_path: Path) -> None:
    state_path = tmp_path / "recording.json"
    output_path = tmp_path / "saved-recording.json"
    controller = RecorderController(state_path)

    started = controller.start(name="Morning inbox")
    paused = controller.pause()
    stopped = controller.stop()
    saved = controller.save(output_path)
    discarded = controller.discard()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert started.status == "recording"
    assert paused.status == "paused"
    assert stopped.status == "stopped"
    assert saved.status == "saved"
    assert discarded.session_id == started.session_id
    assert payload["format"] == "deskpilot_recorder_session_v1"
    assert payload["name"] == "Morning inbox"
    assert payload["status"] == "saved"
    assert payload["event_count"] == 0
    assert not state_path.exists()


def test_cli_record_exposes_start_pause_stop_save_discard_controls(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    state_path = tmp_path / "recorder-state.json"
    output_path = tmp_path / "recording.json"

    assert main(
        [
            "record",
            "start",
            "--state",
            str(state_path),
            "--name",
            "Browser fixture",
        ],
    ) == 0
    assert main(["record", "pause", "--state", str(state_path)]) == 0
    assert main(["record", "stop", "--state", str(state_path)]) == 0
    assert main(
        [
            "record",
            "save",
            "--state",
            str(state_path),
            "--output",
            str(output_path),
        ],
    ) == 0
    assert main(["record", "discard", "--state", str(state_path)]) == 0

    output = capsys.readouterr().out
    saved_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "recording started:" in output
    assert "recording paused:" in output
    assert "recording stopped:" in output
    assert "recording saved:" in output
    assert "recording discarded:" in output
    assert saved_payload["name"] == "Browser fixture"
    assert saved_payload["status"] == "saved"
    assert not state_path.exists()
