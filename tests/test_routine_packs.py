import json
from collections import Counter
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.action_safety import action_safety_profile
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


def test_builtin_routine_catalog_has_broad_reusable_surface_coverage() -> None:
    pack_root = Path("routine_packs")
    catalog = load_routine_catalog(pack_root)
    pack_counts: Counter[str] = Counter()

    for routine in catalog.routines:
        assert routine.source_path is not None
        pack_name = routine.source_path.relative_to(pack_root).parts[0]
        pack_counts[pack_name] += 1
        assert routine.reference.kind in {"task", "playbook"}
        if routine.reference.kind == "task":
            assert routine.reference.task_path is not None
            assert routine.reference.task_path.exists()

    assert len(catalog.routines) >= 30
    assert pack_counts["browser"] >= 65
    assert pack_counts["native"] >= 65
    assert pack_counts["social-content"] >= 84


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
    report_metadata_by_routine_id: dict[str, dict[str, object]] = {}
    for report in reports:
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["status"] == "passed"
        metadata = payload["metadata"]
        assert isinstance(metadata, dict)
        routine_id = metadata["routine_id"]
        assert isinstance(routine_id, str)
        report_metadata_by_routine_id[routine_id] = metadata

    assert len(reports) == len(catalog.routines)
    assert set(report_metadata_by_routine_id) == {
        routine.id for routine in catalog.routines
    }
    for routine in catalog.routines:
        metadata = report_metadata_by_routine_id[routine.id]
        assert routine.tags
        assert routine.inputs
        assert routine.outputs
        assert metadata["routine_inputs"] == list(routine.inputs)
        assert metadata["routine_outputs"] == list(routine.outputs)
        assert metadata["routine_safety_class"] == routine.safety_class
        gates = metadata["routine_promotion_gates"]
        assert isinstance(gates, list)
        assert "trace_replay_review" in {
            gate["id"] for gate in gates if isinstance(gate, dict)
        }


def test_high_risk_builtin_routines_require_approval_and_checkpoints(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    pack_root = Path("routine_packs")
    catalog = load_routine_catalog(pack_root)
    high_risk_routines = [
        routine
        for routine in catalog.routines
        if routine.safety_class in {"high", "sensitive"}
    ]

    assert high_risk_routines
    for routine in high_risk_routines:
        output_path = tmp_path / f"{routine.id.replace('.', '_')}.compiled.yaml"
        assert routine.approval_policy in {
            "confirm",
            "manifest_required",
            "manual_handoff",
        }
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
        capsys.readouterr()

        task = YamlTaskLoader().load(output_path)
        approval_steps = [
            step
            for step in task.steps
            if action_safety_profile(
                step,
                allowed_windows=task.allowed_windows,
            ).approval_required
        ]
        assert approval_steps
        for step in approval_steps:
            assert step.requires_confirmation is True
            assert step.checkpoint is not None


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
        "browser.open-new-tab",
        "browser.close-current-tab",
        "browser.restore-closed-tab",
        "browser.find-on-page",
        "browser.copy-page-link",
        "browser.bookmark-page",
        "browser.print-page-dialog",
        "browser.save-page-dialog",
        "browser.zoom-reset",
        "browser.history-open",
        "browser.extensions-open",
        "browser.private-window-open",
        "browser.reload-page",
        "browser.navigate-back",
        "browser.navigate-forward",
        "browser.home-open",
        "browser.new-window-open",
        "browser.tab-search",
        "browser.downloads-search",
        "browser.site-info-open",
        "browser.reader-view-toggle",
        "browser.translate-dialog-open",
        "browser.privacy-settings-open",
        "browser.cookies-settings-open",
        "browser.autofill-settings-open",
        "browser.search-settings-review",
        "browser.clear-browsing-data-dialog-review",
        "browser.page-source-open",
        "browser.help-open",
        "browser.about-page-open",
        "browser.favorites-open",
        "browser.bookmarks-manager-open",
        "browser.side-panel-open",
        "browser.collections-open",
        "browser.reading-list-open",
        "browser.browser-task-manager-open",
        "browser.fullscreen-enter",
        "browser.fullscreen-exit",
        "browser.accessibility-settings-open",
        "browser.language-settings-open",
        "browser.profile-settings-open",
        "browser.system-settings-open",
        "browser.security-settings-open",
        "browser.site-permissions-settings-open",
        "browser.notifications-settings-open",
        "browser.popups-settings-open",
        "browser.downloads-settings-open",
        "browser.appearance-settings-open",
        "browser.default-browser-settings-open",
        "browser.performance-settings-open",
        "browser.startup-settings-open",
        "browser.new-tab-settings-open",
        "browser.printing-settings-open",
        "browser.accessibility-captions-settings-open",
        "browser.search-shortcuts-review",
        "browser.extension-shortcuts-open",
        "browser.developer-tools-review",
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
        "native.notepad-find",
        "native.notepad-save-dialog-review",
        "native.file-explorer-search",
        "native.file-explorer-new-folder-review",
        "native.settings-search",
        "native.calculator-scientific-mode",
        "native.calculator-copy-result",
        "native.task-manager-open",
        "native.run-dialog-open",
        "native.snipping-tool-open",
        "native.clipboard-history-open",
        "native.window-snap-left",
        "native.window-snap-right",
        "native.window-minimize",
        "native.window-restore",
        "native.desktop-show",
        "native.desktop-restore",
        "native.virtual-desktop-new",
        "native.virtual-desktop-switch-left",
        "native.virtual-desktop-switch-right",
        "native.action-center-open",
        "native.notification-center-open",
        "native.start-menu-search",
        "native.emoji-panel-open",
        "native.quick-link-menu-open",
        "native.system-about-open",
        "native.display-settings-open",
        "native.file-explorer-address-focus",
        "native.file-explorer-refresh",
        "native.file-explorer-properties-dialog-review",
        "native.file-explorer-rename-review",
        "native.file-explorer-preview-pane-toggle",
        "native.file-explorer-details-pane-toggle",
        "native.taskbar-search-open",
        "native.taskbar-search-query-review",
        "native.system-tray-focus",
        "native.settings-bluetooth-open",
        "native.settings-network-open",
        "native.settings-apps-open",
        "native.settings-privacy-open",
        "native.settings-windows-update-open",
        "native.settings-storage-open",
        "native.notepad-replace-dialog-review",
        "native.notepad-go-to-dialog-review",
        "native.notepad-print-dialog-review",
        "native.notepad-zoom-in",
        "native.notepad-zoom-out",
        "native.notepad-zoom-reset",
        "native.notepad-select-all-review",
        "native.calculator-programmer-mode",
        "native.calculator-date-calculation-mode",
        "native.calculator-history-open",
        "native.calculator-memory-open",
        "native.character-map-open",
        "native.system-information-open",
        "native.resource-monitor-open",
        "native.on-screen-keyboard-open",
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
    surfaces = (
        "read",
        "profile-review",
        "notifications-review",
        "messages-review",
        "search-review",
        "saved-review",
        "comments-review",
        "analytics-review",
        "mentions-review",
        "audience-review",
        "draft",
        "approved-publish",
    )
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
