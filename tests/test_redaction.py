from desktop_agent.redaction import (
    RedactionPolicy,
    redaction_policy_from_mapping,
    validate_redaction_policy,
)


def test_redaction_policy_defaults_keep_full_local_evidence() -> None:
    policy = RedactionPolicy()

    assert policy.metadata() == {
        "evidence_mode": "full",
        "screenshots": "full",
        "ocr_text": "full",
        "typed_text": "full",
        "content_variables": "fingerprint_only",
        "video": "full",
        "reports": "full",
    }
    assert validate_redaction_policy(policy) == []


def test_redaction_policy_parses_partial_mapping_with_defaults() -> None:
    policy = redaction_policy_from_mapping(
        {
            "evidence_mode": "metadata_only",
            "ocr_text": "suppress",
        },
    )

    assert policy.evidence_mode == "metadata_only"
    assert policy.ocr_text == "suppress"
    assert policy.screenshots == "full"


def test_redaction_policy_validation_reports_field_specific_errors() -> None:
    errors = validate_redaction_policy(
        RedactionPolicy(
            evidence_mode="hidden",
            video="erase",
        ),
    )

    assert any("redaction_policy.evidence_mode" in error for error in errors)
    assert any("redaction_policy.video" in error for error in errors)
