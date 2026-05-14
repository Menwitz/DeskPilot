from pathlib import Path

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import BasicTaskValidator, YamlTaskLoader

EXAMPLE_TASKS = (
    Path("examples/adversarial-task.yaml"),
    Path("examples/browser-task.yaml"),
    Path("examples/native-task.yaml"),
    Path("examples/mixed-task.yaml"),
)


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
