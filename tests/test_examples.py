from pathlib import Path

from desktop_agent.actuation import DryRunActuator
from desktop_agent.approval_manifest import load_approval_manifest
from desktop_agent.config import (
    RuntimeConfig,
    StaticConfigLoader,
    resolve_runtime_config,
)
from desktop_agent.content_variables import load_content_variables
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    DryRunPerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy
from desktop_agent.screen import StaticScreenObserver
from desktop_agent.site_playbooks import SiteTaskCompiler, load_site_playbook
from desktop_agent.task_compiler import TaskCompiler
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    YamlTaskLoader,
)
from desktop_agent.tracing import MemoryTraceSink, RunReport

EXAMPLE_TASKS = (
    Path("examples/adversarial-task.yaml"),
    Path("examples/browser-task.yaml"),
    Path("examples/capability-showcase-task.yaml"),
    Path("examples/execution-profile-careful-task.yaml"),
    Path("examples/execution-profile-fast-task.yaml"),
    Path("examples/execution-profile-normal-task.yaml"),
    Path("examples/native-task.yaml"),
    Path("examples/mixed-task.yaml"),
)

EXECUTION_PROFILE_EXAMPLES = {
    "careful": Path("examples/execution-profile-careful-task.yaml"),
    "fast": Path("examples/execution-profile-fast-task.yaml"),
    "normal": Path("examples/execution-profile-normal-task.yaml"),
}


def test_example_fixture_files_exist() -> None:
    assert Path("examples/adversarial_fixture.html").exists()
    assert Path("examples/browser_fixture.html").exists()
    assert Path("examples/native_fixture.py").exists()


def test_adversarial_fixture_contains_required_states() -> None:
    fixture = Path("examples/adversarial_fixture.html").read_text(encoding="utf-8")

    assert "disabled" in fixture
    assert "setTimeout" in fixture
    assert "moving-target" in fixture
    assert fixture.count(">Continue<") == 2


def test_example_tasks_validate() -> None:
    loader = YamlTaskLoader()
    validator = BasicTaskValidator()
    compiler = TaskCompiler()
    config = RuntimeConfig(max_steps=50)

    for task_path in EXAMPLE_TASKS:
        task = loader.load(task_path)
        validator.validate(task, config)
        compiled = compiler.compile(task)
        assert task.allowed_windows
        assert task.steps
        assert len(compiled.desktop_io_steps) == len(task.steps)


def test_example_tasks_validate_and_dry_run() -> None:
    loader = YamlTaskLoader()
    validator = BasicTaskValidator()

    for task_path in EXAMPLE_TASKS:
        task = loader.load(task_path)
        config = resolve_runtime_config(
            RuntimeConfig(max_steps=100),
            task_overrides=task.config_overrides,
        )
        validator.validate(task, config)

        report = _dry_run_report(task, task_path, config)

        assert report.status == "passed", task_path
        assert report.steps, task_path
        assert all(step.status == "passed" for step in report.steps), task_path


def test_publish_example_manifests_match_content_fingerprints() -> None:
    examples = (
        (
            "linkedin",
            "publish-post",
            Path("examples/linkedin-content-variables.yaml"),
            Path("examples/linkedin-approval-manifest.yaml"),
        ),
        (
            "medium",
            "publish-story",
            Path("examples/medium-content-variables.yaml"),
            Path("examples/medium-approval-manifest.yaml"),
        ),
    )

    for site_id, flow_id, variables_path, manifest_path in examples:
        variables = load_content_variables(variables_path)
        playbook = load_site_playbook(Path(f"navigation_playbooks/{site_id}.yaml"))
        task = SiteTaskCompiler(variables).compile(playbook, flow_id)
        manifest = load_approval_manifest(manifest_path)

        assert manifest.site_id == site_id
        assert manifest.flow_id == flow_id
        assert manifest.content_fingerprint == task.metadata[
            "content_variables_fingerprint"
        ]


def test_execution_profile_examples_cover_personas_and_reporting_gates() -> None:
    loader = YamlTaskLoader()

    for persona, task_path in EXECUTION_PROFILE_EXAMPLES.items():
        task = loader.load(task_path)
        profile = task.config_overrides.execution_profile
        submission_steps = [
            step for step in task.steps if step.category == "submission"
        ]

        assert profile is not None
        assert profile.enabled is True
        assert profile.persona == persona
        assert task.config_overrides.confirmed_steps == ("click-submit",)
        assert submission_steps
        assert all(step.checkpoint is not None for step in submission_steps)
        assert all(step.verify is not None for step in submission_steps)


def test_capability_showcase_covers_full_dry_run_action_surface() -> None:
    loader = YamlTaskLoader()
    task = loader.load(Path("examples/capability-showcase-task.yaml"))
    actions = {step.action for step in task.steps}
    verification_types = {
        step.verify.type
        for step in task.steps
        if step.verify is not None
    }

    assert {
        "assert_visible",
        "branch_if_visible",
        "click_image",
        "click_text",
        "click_uia",
        "drag",
        "press_key",
        "scroll",
        "scroll_until",
        "type_text",
        "wait_for",
    } <= actions
    assert {"visible_text", "not_visible_text"} <= verification_types
    assert task.config_overrides.execution_profile is not None
    assert task.config_overrides.confirmed_steps == ("submit-showcase",)
    assert any(step.recovery for step in task.steps)
    assert any(step.checkpoint is not None for step in task.steps)
    assert any(step.safe_action_variants for step in task.steps)


def _dry_run_report(
    task: TaskDefinition,
    task_path: Path,
    config: RuntimeConfig,
) -> RunReport:
    return ExecutionEngine(
        config_loader=StaticConfigLoader(config),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(),
        perception_engine=CompositePerceptionEngine((DryRunPerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
    ).run(task_path)
