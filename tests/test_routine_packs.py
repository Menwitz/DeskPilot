from pathlib import Path

from desktop_agent.config import RuntimeConfig
from desktop_agent.routines import load_routine_catalog
from desktop_agent.task_dsl import BasicTaskValidator, YamlTaskLoader

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


def test_browser_routine_pack_contains_seed_categories() -> None:
    catalog = load_routine_catalog(Path("routine_packs"))
    expected_ids = {
        "browser.navigation-open-page",
        "browser.form-fill-basic",
        "browser.search-web",
        "browser.read-page",
        "browser.extract-visible-text",
        "browser.writing-surface-draft",
        "browser.download-open",
        "browser.settings-open",
    }
    routines = {
        routine.id: routine
        for routine in catalog.routines
        if routine.id.startswith("browser.")
    }

    assert expected_ids <= set(routines)
    for routine_id in expected_ids:
        reference = routines[routine_id].reference
        assert reference.kind == "task"
        assert reference.task_path is not None
        task = YamlTaskLoader().load(reference.task_path)
        BasicTaskValidator().validate(task, RuntimeConfig())


def test_native_routine_pack_contains_seed_categories() -> None:
    catalog = load_routine_catalog(Path("routine_packs"))
    expected_ids = {
        "native.notepad-draft",
        "native.calculator-basic",
        "native.settings-open",
        "native.file-explorer-open",
        "native.clipboard-copy",
        "native.app-switch",
        "native.window-manage",
        "native.office-like-draft",
    }
    routines = {
        routine.id: routine
        for routine in catalog.routines
        if routine.id.startswith("native.")
    }

    assert expected_ids <= set(routines)
    for routine_id in expected_ids:
        reference = routines[routine_id].reference
        assert reference.kind == "task"
        assert reference.task_path is not None
        task = YamlTaskLoader().load(reference.task_path)
        BasicTaskValidator().validate(task, RuntimeConfig())


def test_social_content_routine_pack_contains_platform_surface_matrix() -> None:
    catalog = load_routine_catalog(Path("routine_packs"))
    platforms = (
        "linkedin",
        "medium",
        "x-twitter",
        "instagram",
        "facebook",
        "youtube",
        "tiktok",
    )
    surfaces = ("read", "draft", "approved-publish")
    expected_ids = {
        f"social-content.{platform}-{surface}"
        for platform in platforms
        for surface in surfaces
    }
    routines = {
        routine.id: routine
        for routine in catalog.routines
        if routine.id.startswith("social-content.")
    }

    assert expected_ids <= set(routines)
    for routine_id in expected_ids:
        routine = routines[routine_id]
        reference = routine.reference
        assert reference.kind == "task"
        assert reference.task_path is not None
        if routine_id.endswith("approved-publish"):
            assert routine.approval_policy == "manifest_required"
            assert routine.safety_class == "high"
        task = YamlTaskLoader().load(reference.task_path)
        BasicTaskValidator().validate(task, RuntimeConfig())
