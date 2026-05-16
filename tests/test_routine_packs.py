import json
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.cli import main
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


def test_builtin_routines_are_listable_inspectable_and_compilable_from_cli(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    pack_root = Path("routine_packs")
    catalog = load_routine_catalog(pack_root)
    validator = BasicTaskValidator()
    config = RuntimeConfig()

    assert catalog.routines
    assert main(["list-routines", "--routine-pack-root", str(pack_root)]) == 0
    list_output = capsys.readouterr().out

    for routine in catalog.routines:
        assert f"{routine.id}\t" in list_output

        assert (
            main(
                [
                    "show-routine",
                    routine.id,
                    "--routine-pack-root",
                    str(pack_root),
                ],
            )
            == 0
        )
        show_output = capsys.readouterr().out
        assert f"id: {routine.id}" in show_output
        assert f"name: {routine.name}" in show_output
        assert "reference:" in show_output

        output_path = tmp_path / f"{routine.id.replace('.', '_')}.compiled.yaml"
        assert (
            main(
                [
                    "compile-routine",
                    routine.id,
                    "--routine-pack-root",
                    str(pack_root),
                    "--output",
                    str(output_path),
                ],
            )
            == 0
        )
        compile_output = capsys.readouterr().out
        assert f"compiled routine: {routine.id}" in compile_output

        task = YamlTaskLoader().load(output_path)
        validator.validate(task, config)
        assert task.metadata["routine_id"] == routine.id
        assert task.metadata["routine_source_path"] == str(routine.source_path)


def test_builtin_routines_have_cli_dry_run_coverage(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    pack_root = Path("routine_packs")
    catalog = load_routine_catalog(pack_root)
    config_path = tmp_path / "config.yaml"
    trace_root = tmp_path / "traces"
    config_path.write_text(f"trace_root: {trace_root}\n", encoding="utf-8")

    assert catalog.routines
    for routine in catalog.routines:
        compiled_path = tmp_path / f"{routine.id.replace('.', '_')}.compiled.yaml"
        assert (
            main(
                [
                    "compile-routine",
                    routine.id,
                    "--routine-pack-root",
                    str(pack_root),
                    "--output",
                    str(compiled_path),
                ],
            )
            == 0
        )
        capsys.readouterr()
        task = YamlTaskLoader().load(compiled_path)
        args = [
            "dry-run-routine",
            routine.id,
            "--routine-pack-root",
            str(pack_root),
            "--config",
            str(config_path),
            "--no-screenshots",
        ]
        for step in task.steps:
            args.extend(["--confirm-step", step.id])

        assert main(args) == 0
        output = capsys.readouterr().out
        assert f"task: {routine.name}" in output
        assert "status: passed" in output

    reports = sorted(trace_root.glob("*/final-report.json"))
    reported_routine_ids = {
        json.loads(report.read_text(encoding="utf-8"))["metadata"]["routine_id"]
        for report in reports
    }
    assert len(reports) == len(catalog.routines)
    assert reported_routine_ids == {routine.id for routine in catalog.routines}


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
