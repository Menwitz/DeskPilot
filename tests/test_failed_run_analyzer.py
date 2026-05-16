import json
from pathlib import Path

from desktop_agent.failed_run_analyzer import (
    analyze_failed_run_report,
    analyze_failed_run_trace,
    write_failed_run_analysis,
)


def test_failed_run_analyzer_proposes_review_only_selector_yaml() -> None:
    analysis = analyze_failed_run_report(
        {
            "task_name": "Browser search",
            "status": "failed",
            "metadata": {"routine_id": "browser.search"},
            "steps": [
                {
                    "step_id": "click-submit",
                    "status": "failed",
                    "metadata": {
                        "failure_category": "selection_ambiguity",
                        "diagnostic_bundle": {
                            "candidate_count": 2,
                            "candidates_by_source": {"uia": 2},
                        },
                    },
                },
            ],
        },
    )

    proposal = analysis.proposals[0]
    assert analysis.routine_id == "browser.search"
    assert proposal.step_id == "click-submit"
    assert proposal.proposal_type == "selector_or_region_review"
    assert proposal.review_required is True
    assert proposal.applies_automatically is False
    assert "region:" in proposal.yaml_snippet


def test_failed_run_analyzer_writes_json_and_markdown(tmp_path: Path) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "final-report.json").write_text(
        json.dumps(
            {
                "task_name": "Browser search",
                "status": "failed",
                "metadata": {"routine_id": "browser.search"},
                "steps": [
                    {
                        "step_id": "verify-results",
                        "status": "failed",
                        "metadata": {"failure_category": "verification_failure"},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    analysis = analyze_failed_run_trace(trace_dir)
    write_failed_run_analysis(trace_dir, analysis)

    payload = json.loads((trace_dir / "failed-run-analysis.json").read_text())
    markdown = (trace_dir / "failed-run-analysis.md").read_text(encoding="utf-8")
    assert payload["proposal_count"] == 1
    assert payload["diagnostic_ready"] is False
    assert payload["desktop_input_rerun_required"] is False
    assert payload["proposals"][0]["applies_automatically"] is False
    assert "checkpoint:" in payload["proposals"][0]["yaml_snippet"]
    assert "Desktop input rerun required" in markdown
    assert "Review required" in markdown


def test_failed_run_analyzer_indexes_local_artifacts_without_rerun(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "final-report.json").write_text(
        json.dumps(
            {
                "task_name": "Browser search",
                "status": "failed",
                "steps": [
                    {
                        "step_id": "click-submit",
                        "status": "failed",
                        "metadata": {"failure_category": "safety_stop"},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    (trace_dir / "action-log.jsonl").write_text("", encoding="utf-8")
    (trace_dir / "task.json").write_text("{}", encoding="utf-8")
    (trace_dir / "screenshots").mkdir()

    analysis = analyze_failed_run_trace(trace_dir)
    write_failed_run_analysis(trace_dir, analysis)

    payload = json.loads((trace_dir / "failed-run-analysis.json").read_text())
    markdown = (trace_dir / "failed-run-analysis.md").read_text(encoding="utf-8")
    artifacts = {artifact["name"]: artifact for artifact in payload["artifacts"]}
    assert payload["diagnostic_ready"] is True
    assert payload["desktop_input_rerun_required"] is False
    assert artifacts["final_report"]["present"] is True
    assert artifacts["action_log"]["present"] is True
    assert artifacts["task_snapshot"]["present"] is True
    assert artifacts["screenshots"]["present"] is True
    assert "Desktop input rerun required: `false`" in markdown
