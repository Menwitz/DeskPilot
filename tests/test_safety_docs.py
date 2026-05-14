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
