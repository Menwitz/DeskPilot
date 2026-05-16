from desktop_agent.redaction import (
    RedactionPolicy,
    content_variable_redaction_metadata,
    mask_content_variable_names,
    mask_ocr_text,
    mask_typed_text,
    redaction_policy_from_mapping,
    screenshot_blur_masks,
    should_capture_screenshot,
    should_save_ocr_text,
    typed_text_redaction_metadata,
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
        "sensitive_zones": [],
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


def test_redaction_policy_builds_screenshot_blur_masks() -> None:
    policy = redaction_policy_from_mapping(
        {
            "screenshots": "blur_sensitive_zones",
            "sensitive_zones": [
                {
                    "id": "account-balance",
                    "x": 10,
                    "y": 20,
                    "width": 200,
                    "height": 40,
                    "reason": "financial account balance",
                },
            ],
        },
    )

    masks = screenshot_blur_masks(policy)

    assert validate_redaction_policy(policy) == []
    assert len(masks) == 1
    assert masks[0].metadata()["zone_id"] == "account-balance"
    assert masks[0].metadata()["bounds"] == {
        "id": "account-balance",
        "x": 10,
        "y": 20,
        "width": 200,
        "height": 40,
        "reason": "financial account balance",
    }


def test_redaction_policy_validation_reports_field_specific_errors() -> None:
    errors = validate_redaction_policy(
        RedactionPolicy(
            evidence_mode="hidden",
            video="erase",
        ),
    )

    assert any("redaction_policy.evidence_mode" in error for error in errors)
    assert any("redaction_policy.video" in error for error in errors)


def test_redaction_policy_validation_rejects_invalid_sensitive_zones() -> None:
    policy = redaction_policy_from_mapping(
        {
            "sensitive_zones": [
                {"id": "duplicate", "x": 0, "y": 0, "width": 10, "height": 10},
                {"id": "duplicate", "x": -1, "y": 0, "width": 0, "height": 10},
            ],
        },
    )

    errors = validate_redaction_policy(policy)

    assert any("id must be unique" in error for error in errors)
    assert any("x and y must not be negative" in error for error in errors)
    assert any("width and height" in error for error in errors)


def test_typed_text_masking_preserves_length_without_changing_input() -> None:
    policy = RedactionPolicy(typed_text="mask")

    assert mask_typed_text("secret", policy) == "******"
    assert typed_text_redaction_metadata("secret", policy) == {
        "typed_text_redaction": "mask",
        "typed_text_suppressed": False,
        "typed_text_value": "******",
    }


def test_content_variable_name_masking_reports_counts() -> None:
    policy = RedactionPolicy(content_variables="mask_names")

    assert mask_content_variable_names(("post_text", "post_url"), policy) == (
        "variable_1",
        "variable_2",
    )
    assert content_variable_redaction_metadata(("post_text", "post_url"), policy) == {
        "content_variable_names": ["variable_1", "variable_2"],
        "content_variable_count": 2,
        "content_variable_name_redaction": "mask_names",
        "content_variables_redacted": True,
    }


def test_metadata_only_policy_disables_screenshot_and_ocr_artifacts() -> None:
    policy = RedactionPolicy(evidence_mode="metadata_only")

    assert should_capture_screenshot(policy, save_enabled=True) is False
    assert should_save_ocr_text(policy, save_enabled=True) is False


def test_ocr_text_masking_and_suppression() -> None:
    assert mask_ocr_text("Visible total", RedactionPolicy(ocr_text="mask")) == (
        "*************"
    )
    assert mask_ocr_text("Visible total", RedactionPolicy(ocr_text="suppress")) is None


def test_redaction_policy_matrix_covers_all_evidence_surfaces() -> None:
    policy = redaction_policy_from_mapping(
        {
            "screenshots": "metadata_only",
            "ocr_text": "suppress",
            "typed_text": "suppress",
            "content_variables": "suppress",
            "video": "disabled",
            "reports": "redacted",
        }
    )
    metadata = policy.metadata()

    assert validate_redaction_policy(policy) == []
    assert should_capture_screenshot(policy, save_enabled=True) is False
    assert should_save_ocr_text(policy, save_enabled=True) is False
    assert mask_ocr_text("Visible total", policy) is None
    assert typed_text_redaction_metadata("secret", policy) == {
        "typed_text_redaction": "suppress",
        "typed_text_suppressed": True,
        "typed_text_value": None,
    }
    assert content_variable_redaction_metadata(("post_text", "post_url"), policy) == {
        "content_variable_names": [],
        "content_variable_count": 2,
        "content_variable_name_redaction": "suppress",
        "content_variables_redacted": True,
    }
    assert metadata["video"] == "disabled"
    assert metadata["reports"] == "redacted"
