from pathlib import Path

EXPECTED_ROUTINE_PACKS = (
    "browser",
    "native",
    "social-content",
    "email-writing",
    "files",
    "research",
    "publishing",
)


def test_expected_routine_pack_directories_are_documented() -> None:
    root = Path("routine_packs")

    assert (root / "README.md").exists()
    for pack in EXPECTED_ROUTINE_PACKS:
        assert (root / pack / "README.md").exists()
