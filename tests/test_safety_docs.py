from pathlib import Path


def test_execution_profile_docs_preserve_unsupported_use_boundary() -> None:
    documentation = "\n".join(
        [
            Path("docs/safety.md").read_text(encoding="utf-8"),
            Path("docs/configuration.md").read_text(encoding="utf-8"),
        ]
    )

    for phrase in (
        "stealth automation",
        "CAPTCHA bypass",
        "bot-detection evasion",
        "credential abuse",
        "abusive third-party automation",
    ):
        assert phrase in documentation


def test_operator_guidance_documents_timing_budget_and_report_checks() -> None:
    documentation = Path("docs/configuration.md").read_text(encoding="utf-8")

    for phrase in (
        "Choosing Delay Bounds",
        "Choosing Entropy Budgets",
        "dry-run preview",
        "action-log.jsonl",
        "safety-audit.md",
        "benchmark-report.json",
        "variance-report.json",
    ):
        assert phrase in documentation


def test_troubleshooting_documents_stop_categories_and_report_fields() -> None:
    documentation = Path("docs/troubleshooting.md").read_text(encoding="utf-8")

    for phrase in (
        "Ambiguity Gate Stops",
        "Recovery Stops",
        "Safety Stops",
        "selection_ambiguity",
        "confidence_or_ambiguity_gate",
        "recover_candidates",
        "recovery_path_summary",
        "safety_stop",
        "input_blocked",
        "actuation_guard",
    ):
        assert phrase in documentation


def test_troubleshooting_documents_public_site_failure_modes() -> None:
    documentation = Path("docs/troubleshooting.md").read_text(encoding="utf-8")

    for phrase in (
        "Public Site Playbook Stops",
        "Logged-out session",
        "Consent dialog",
        "Site redesign",
        "CAPTCHA or suspicious-activity challenge",
        "Permission restriction",
        "Ambiguous selector",
        "desktop-agent replay <trace-dir>",
    ):
        assert phrase in documentation


def test_windows_proof_docs_cover_manual_evidence_review() -> None:
    documentation = "\n".join(
        [
            Path("docs/windows-proof-evidence-checklist.md").read_text(
                encoding="utf-8"
            ),
            Path("docs/actuation.md").read_text(encoding="utf-8"),
            Path("docs/acceptance.md").read_text(encoding="utf-8"),
        ]
    )

    for phrase in (
        "desktop-agent proof replay <trace-dir>",
        "proof-manifest.json",
        "demo-input",
        "demo-linkedin",
        "windows-smoke-checklist",
        "video",
        "trace",
        "screenshots",
        "action-log.jsonl",
        "candidate rankings",
        "reviewer signoff",
    ):
        assert phrase in documentation


def test_release_notes_distinguish_natural_execution_from_impersonation() -> None:
    documentation = Path("docs/release-notes.md").read_text(encoding="utf-8")

    for phrase in (
        "Natural execution",
        "deceptive human impersonation",
        "stealth automation",
        "CAPTCHA bypass",
        "bot-detection evasion",
        "safety audit",
        "benchmark-run",
    ):
        assert phrase in documentation


def test_documentation_set_covers_behavior_boundary_and_safe_configuration() -> None:
    documentation = "\n".join(
        [
            Path("docs/configuration.md").read_text(encoding="utf-8"),
            Path("docs/safety.md").read_text(encoding="utf-8"),
            Path("docs/examples.md").read_text(encoding="utf-8"),
            Path("docs/troubleshooting.md").read_text(encoding="utf-8"),
            Path("docs/release-notes.md").read_text(encoding="utf-8"),
        ]
    )

    for phrase in (
        "execution_profile",
        "Operator Guidance",
        "Explicitly Unsupported Uses",
        "Execution Profile Examples",
        "Ambiguity Gate Stops",
        "Natural execution",
        "Not Human Impersonation",
        "benchmark-report.json",
        "safety-audit.md",
    ):
        assert phrase in documentation
