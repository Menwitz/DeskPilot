import json
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.routine_pack_runner import (
    run_routine_pack_tests,
    write_routine_pack_proof_bundle,
)


def test_routine_pack_test_runner_validates_routines_and_tasks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "routine_packs"
    _write_pack(root / "sample", pack_id="sample")

    result = run_routine_pack_tests(root, "sample")

    assert result.status == "passed"
    assert result.routine_count == 1
    assert result.validated_routine_count == 1
    assert result.errors == ()


def test_routine_pack_proof_bundle_writes_report_and_checklist(
    tmp_path: Path,
) -> None:
    root = tmp_path / "routine_packs"
    bundle_dir = tmp_path / "proof"
    _write_pack(root / "sample", pack_id="sample")

    result = write_routine_pack_proof_bundle(root, "sample", bundle_dir)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    checklist = result.checklist_path.read_text(encoding="utf-8")

    assert result.test_result.status == "passed"
    assert result.proof_status == "ready_for_review"
    assert result.metadata()["proof_status"] == "ready_for_review"
    assert report["proof_status"] == "ready_for_review"
    assert report["test_result"]["validated_routine_count"] == 1
    assert "Routine Pack Proof" in checklist
    assert "Proof status: `ready_for_review`" in checklist
    assert "`final-report.json`" in checklist
    assert result.manifest_copy_path.exists()


def test_routine_pack_runner_cli_writes_report_and_proof_bundle(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    root = tmp_path / "routine_packs"
    report_path = tmp_path / "pack-report.json"
    proof_dir = tmp_path / "proof"
    _write_pack(root / "sample", pack_id="sample")

    assert (
        main(
            [
                "test-routine-pack",
                "sample",
                "--routine-pack-root",
                str(root),
                "--output",
                str(report_path),
            ],
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "status: passed" in output
    assert report_path.exists()

    assert (
        main(
            [
                "write-routine-pack-proof",
                "sample",
                "--routine-pack-root",
                str(root),
                "--output",
                str(proof_dir),
            ],
        )
        == 0
    )
    proof_output = capsys.readouterr().out
    assert "routine pack proof: sample" in proof_output
    assert (proof_dir / "pack-test-report.json").exists()


def _write_pack(root: Path, *, pack_id: str) -> None:
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Sample Pack\n", encoding="utf-8")
    task_path = root / "tasks" / "sample.yaml"
    task_path.parent.mkdir()
    task_path.write_text(
        "\n".join(
            [
                "name: Sample task",
                "allowed_windows:",
                "  - Sample Window",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-target",
                "    action: click_text",
                "    target: Target",
                "",
            ],
        ),
        encoding="utf-8",
    )
    (root / "sample.routine.yaml").write_text(
        "\n".join(
            [
                f"id: {pack_id}.routine",
                "name: Sample routine",
                "description: Sample routine for pack test runner.",
                "goal: Validate pack-level test runner.",
                "required_app: Sample Window",
                "tags:",
                "  - sample",
                "inputs:",
                "  - topic",
                "outputs:",
                "  - result",
                "safety_class: low",
                "schedule_policy: manual",
                "approval_policy: none",
                "expected_duration_seconds: 30",
                "reference:",
                "  type: task",
                "  path: tasks/sample.yaml",
                "",
            ],
        ),
        encoding="utf-8",
    )
    (root / "routine-pack.yaml").write_text(
        "\n".join(
            [
                'pack_schema_version: "1"',
                f"id: {pack_id}",
                "name: Sample Pack",
                "description: Sample pack for runner tests.",
                'version: "0.1.0"',
                "publisher: Local Operator",
                "trust_level: trusted_local",
                "routine_globs:",
                '  - "*.routine.yaml"',
                "docs:",
                "  - README.md",
                "fixtures: []",
                "tests: []",
                "safety:",
                "  max_safety_class: low",
                "  requires_review: true",
                "  external_mutation_allowed: false",
                "  approval_required: false",
                "proof:",
                "  windows_proof_required: false",
                "  expected_artifacts:",
                "    - final-report.json",
                "    - action-log.jsonl",
                "",
            ],
        ),
        encoding="utf-8",
    )
