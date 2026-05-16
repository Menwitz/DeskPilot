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


def test_product_contract_preserves_local_first_authorized_use_boundary() -> None:
    documentation = " ".join(
        "\n".join(
            [
                Path("docs/project-definition.md").read_text(encoding="utf-8"),
                Path("docs/safety.md").read_text(encoding="utf-8"),
                Path("docs/personal-routine-assistant-roadmap.md").read_text(
                    encoding="utf-8",
                ),
            ]
        ).split()
    )

    for phrase in (
        "Screenshots, OCR output, traces, and reports stay local by default",
        "no cloud AI dependency",
        "authorized to automate",
        "human-paced visible automation without stealth or evasion",
        "stealth automation",
        "CAPTCHA bypass",
        "bot-detection evasion",
        "hidden automation",
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


def test_troubleshooting_documents_local_environment_failures() -> None:
    documentation = Path("docs/troubleshooting.md").read_text(encoding="utf-8")

    for phrase in (
        "Missing Windows Permissions Or UIA Access",
        "Desktop Session Is Locked",
        "OCR Is Unavailable Or Disabled",
        "Video Capture Fails",
        "Local Model Is Unavailable",
        "Tesseract",
        "video-capture.log",
        "proof-video.mp4",
        "--video-policy disabled",
        "desktop-agent local-model status",
        "local_model.enabled",
        "Windows desktop input",
    ):
        assert phrase in documentation


def test_signed_routine_pack_investigation_keeps_safety_boundary() -> None:
    documentation = Path("docs/signed-routine-pack-investigation.md").read_text(
        encoding="utf-8",
    )

    for phrase in (
        "later-release investigation",
        "routine-pack.sig",
        "pack-digest.json",
        "trusted keyring",
        "No automatic execution based only on a valid signature",
        "No signature bypass",
    ):
        assert phrase in documentation


def test_local_report_server_design_stays_read_only_and_optional() -> None:
    documentation = Path("docs/local-report-server-design.md").read_text(
        encoding="utf-8",
    )

    for phrase in (
        "fully functional without a report server",
        "No execution authority",
        "Read-only by default",
        "loopback only",
        "Redaction-aware",
        "Keep any future team/reporting sync separate",
    ):
        assert phrase in documentation


def test_linux_x11_plan_remains_after_windows_beta() -> None:
    documentation = Path("docs/linux-x11-adapter-plan.md").read_text(
        encoding="utf-8",
    )

    for phrase in (
        "post-Windows-beta plan",
        "Windows proof pack is complete",
        "X11ScreenObserver",
        "X11Actuator",
        "Never run from a headless session",
        "Preserve allowed-window checks",
    ):
        assert phrase in documentation


def test_wayland_support_remains_research_until_io_constraints_close() -> None:
    documentation = Path("docs/wayland-support-research.md").read_text(
        encoding="utf-8",
    )

    for phrase in (
        "research track, not a beta release target",
        "screenshot, focus, and input constraints",
        "Do not bypass compositor security",
        "XDG Desktop Portal",
        "Focus, cursor, and target readback",
        "No production support before the research constraints above are closed",
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
        "mixed-fixture",
        "native-fixture",
        "recovery-fixture",
        "windows-smoke-checklist",
        "video",
        "trace",
        "screenshots",
        "action-log.jsonl",
        "proof-video.mp4",
        "video-capture.log",
        "candidate rankings",
        "reviewer signoff",
        "proof-suite-promotion.json",
        "proof-promotion-verification.json",
        "proof-archive-verification.json",
        "artifact digests",
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


def test_local_ai_docs_preserve_advisory_only_boundary() -> None:
    documentation = "\n".join(
        [
            Path("docs/local-ai.md").read_text(encoding="utf-8"),
            Path("docs/configuration.md").read_text(encoding="utf-8"),
            Path("docs/goal-planning.md").read_text(encoding="utf-8"),
        ]
    )

    for phrase in (
        "disabled by default",
        "advisory selection and review workflows",
        "cannot execute raw desktop actions",
        "bypass approvals",
        "bypass safety gates",
        "deterministic result remains in force",
        "provider, model name, prompt class",
        "FakeLocalModelProvider",
    ):
        assert phrase in documentation
