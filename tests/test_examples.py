from pathlib import Path

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import BasicTaskValidator, YamlTaskLoader

EXAMPLE_TASKS = (
    Path("examples/adversarial-task.yaml"),
    Path("examples/browser-task.yaml"),
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
    config = RuntimeConfig(max_steps=50)

    for task_path in EXAMPLE_TASKS:
        task = loader.load(task_path)
        validator.validate(task, config)
        assert task.allowed_windows
        assert task.steps


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
