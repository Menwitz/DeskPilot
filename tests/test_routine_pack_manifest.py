from pathlib import Path

import pytest

from desktop_agent.routine_pack_manifest import (
    RoutinePackManifestError,
    load_routine_pack_manifest,
    load_routine_pack_manifests,
    routine_pack_manifest_from_mapping,
    routine_pack_trust_warnings,
)

EXPECTED_ROUTINE_PACKS = {
    "browser",
    "native",
    "social-content",
    "email-writing",
    "files",
    "research",
    "publishing",
}


def test_routine_pack_manifest_schema_loads_manifest_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sample" / "routine-pack.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        "\n".join(
            [
                'pack_schema_version: "1"',
                "id: sample-pack",
                "name: Sample Pack",
                "description: Sample local routines.",
                'version: "0.1.0"',
                "publisher: Local Operator",
                "trust_level: trusted_local",
                "routine_globs:",
                '  - "*.routine.yaml"',
                "docs:",
                "  - README.md",
                "fixtures:",
                "  - fixtures/sample.json",
                "tests:",
                "  - tests/test_sample_pack.py",
                "safety:",
                "  max_safety_class: medium",
                "  requires_review: true",
                "  external_mutation_allowed: false",
                "  approval_required: true",
                "proof:",
                "  windows_proof_required: true",
                "  expected_artifacts:",
                "    - final-report.json",
                "    - action-log.jsonl",
                "",
            ],
        ),
        encoding="utf-8",
    )

    manifest = load_routine_pack_manifest(manifest_path.parent)
    metadata = manifest.metadata()

    assert manifest.id == "sample-pack"
    assert manifest.trust_level == "trusted_local"
    assert manifest.safety.max_safety_class == "medium"
    assert manifest.proof.windows_proof_required is True
    assert metadata["pack_id"] == "sample-pack"


def test_builtin_routine_pack_manifests_validate() -> None:
    manifests = load_routine_pack_manifests(Path("routine_packs"))
    by_id = {manifest.id: manifest for manifest in manifests}

    assert set(by_id) >= EXPECTED_ROUTINE_PACKS
    for manifest in manifests:
        assert manifest.trust_level == "builtin"
        assert manifest.routine_globs
        assert manifest.docs == ("README.md",)
        assert manifest.proof.expected_artifacts
        if manifest.source_path is not None:
            pack_root = manifest.source_path.parent
            for doc_path in manifest.docs:
                assert (pack_root / doc_path).exists()
    assert by_id["social-content"].safety.max_safety_class == "high"
    assert by_id["social-content"].safety.external_mutation_allowed is True


def test_routine_pack_manifest_rejects_parent_traversal() -> None:
    with pytest.raises(RoutinePackManifestError, match="relative pack paths"):
        routine_pack_manifest_from_mapping(
            {
                "pack_schema_version": "1",
                "id": "bad-pack",
                "name": "Bad Pack",
                "description": "Unsafe path.",
                "version": "0.1.0",
                "publisher": "Local Operator",
                "trust_level": "trusted_local",
                "routine_globs": ["../*.routine.yaml"],
                "docs": ["README.md"],
                "fixtures": [],
                "tests": [],
                "safety": {
                    "max_safety_class": "low",
                    "requires_review": True,
                    "external_mutation_allowed": False,
                    "approval_required": False,
                },
                "proof": {
                    "windows_proof_required": False,
                    "expected_artifacts": ["final-report.json"],
                },
            },
        )


def test_routine_pack_manifest_warns_for_unverified_local_pack() -> None:
    manifest = routine_pack_manifest_from_mapping(
        {
            "pack_schema_version": "1",
            "id": "unverified-pack",
            "name": "Unverified Pack",
            "description": "Needs operator review.",
            "version": "0.1.0",
            "publisher": "Unknown",
            "trust_level": "unverified_local",
            "routine_globs": ["*.routine.yaml"],
            "docs": ["README.md"],
            "fixtures": [],
            "tests": [],
            "safety": {
                "max_safety_class": "medium",
                "requires_review": True,
                "external_mutation_allowed": False,
                "approval_required": True,
            },
            "proof": {
                "windows_proof_required": True,
                "expected_artifacts": ["final-report.json"],
            },
        },
    )
    warnings = routine_pack_trust_warnings(manifest)
    metadata = manifest.metadata()

    assert len(warnings) == 1
    assert "pack is unverified" in warnings[0].message
    assert metadata["trust_warnings"]


def test_routine_pack_manifest_rejects_duplicate_ids(tmp_path: Path) -> None:
    _write_minimal_manifest(tmp_path / "one", pack_id="duplicate")
    _write_minimal_manifest(tmp_path / "two", pack_id="duplicate")

    with pytest.raises(RoutinePackManifestError, match="duplicate routine pack id"):
        load_routine_pack_manifests(tmp_path)


def _write_minimal_manifest(pack_root: Path, *, pack_id: str) -> None:
    pack_root.mkdir(parents=True)
    (pack_root / "routine-pack.yaml").write_text(
        "\n".join(
            [
                'pack_schema_version: "1"',
                f"id: {pack_id}",
                "name: Duplicate Pack",
                "description: Duplicate local pack.",
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
                "",
            ],
        ),
        encoding="utf-8",
    )
