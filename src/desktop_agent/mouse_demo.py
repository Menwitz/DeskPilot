"""Interactive Windows mouse-control demo using the real actuation layer."""

from __future__ import annotations

import ctypes
import json
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from desktop_agent.actuation import (
    ActuationProfile,
    DesktopActuator,
    MovementPlan,
    ScrollCadencePlan,
    WindowsInputBackend,
)


class MouseDemoError(RuntimeError):
    """Raised when the local mouse demo cannot run safely."""


@dataclass(frozen=True)
class MouseDemoStep:
    """One visible mouse action recorded by the demo."""

    step_id: str
    action: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class MouseDemoReport:
    """Result returned by the mouse demo command."""

    status: str
    trace_dir: Path
    report_path: Path
    steps: tuple[MouseDemoStep, ...]


@dataclass(frozen=True)
class MouseDemoPoints:
    """Absolute screen coordinates used by the local Tk demo fixture."""

    click_target: tuple[int, int]
    drag_start: tuple[int, int]
    drag_end: tuple[int, int]
    scroll_target: tuple[int, int]
    finish_target: tuple[int, int]


def run_mouse_demo(
    *,
    trace_root: Path = Path("traces"),
    random_seed: int = 20260515,
    movement_smoothness: float = 0.85,
    auto_close_seconds: float = 3.0,
) -> MouseDemoReport:
    """Open a local window and drive visible mouse actions inside it."""

    if sys.platform != "win32":
        raise MouseDemoError("demo-mouse requires Windows desktop input")
    if not 0 <= movement_smoothness <= 1:
        raise MouseDemoError("movement_smoothness must be between 0 and 1")
    if auto_close_seconds < 0:
        raise MouseDemoError("auto_close_seconds must not be negative")

    _set_process_dpi_aware()
    tk = _load_tkinter()
    root, canvas, state = _build_demo_window(tk)
    # Avoid closing the target window mid-sequence while real input is in flight.
    root.protocol("WM_DELETE_WINDOW", lambda: None)
    profile = _demo_actuation_profile(random_seed, movement_smoothness)
    actuator = DesktopActuator(WindowsInputBackend(), profile)
    trace_dir = _prepare_trace_dir(trace_root)
    steps: list[MouseDemoStep] = []
    completed = threading.Event()
    failed: list[str] = []

    def start_worker() -> None:
        points = _demo_points(canvas)
        worker = threading.Thread(
            target=_run_mouse_sequence,
            args=(actuator, points, steps, root, state, completed, failed),
            daemon=True,
        )
        worker.start()

    def poll_completion() -> None:
        if completed.is_set():
            _write_report(trace_dir, steps, "failed" if failed else "passed", failed)
            _mark_done(canvas, state, "failed" if failed else "passed")
            if auto_close_seconds == 0:
                root.destroy()
            else:
                root.after(round(auto_close_seconds * 1000), root.destroy)
            return
        root.after(100, poll_completion)

    # Keep the demo in front while the worker sends real OS-level input.
    root.attributes("-topmost", True)
    root.after(500, start_worker)
    root.after(100, poll_completion)
    root.mainloop()

    status = "failed" if failed else "passed"
    report_path = trace_dir / "mouse-demo-report.json"
    return MouseDemoReport(
        status=status,
        trace_dir=trace_dir,
        report_path=report_path,
        steps=tuple(steps),
    )


def _demo_actuation_profile(
    random_seed: int,
    movement_smoothness: float,
) -> ActuationProfile:
    return ActuationProfile(
        movement_duration_seconds=(0.35, 0.90),
        timing_variation_seconds=(0.04, 0.12),
        keyboard_interval_seconds=(0.02, 0.07),
        scroll_interval_seconds=(0.08, 0.18),
        movement_steps=32,
        movement_smoothness=movement_smoothness,
        overshoot_probability=0.35,
        overshoot_pixels=(3.0, 8.0),
        settle_duration_seconds=(0.04, 0.12),
        random_seed=random_seed,
    )


def _run_mouse_sequence(
    actuator: DesktopActuator,
    points: MouseDemoPoints,
    steps: list[MouseDemoStep],
    root: Any,
    state: dict[str, Any],
    completed: threading.Event,
    failed: list[str],
) -> None:
    try:
        time.sleep(0.8)
        _record_movement(
            steps,
            "click-target",
            "click",
            actuator.click(points.click_target, target_size_pixels=(160, 70)),
            points.click_target,
        )
        _set_status(root, state, "Clicked target. Dragging token...")
        time.sleep(0.25)
        _record_movement(
            steps,
            "drag-token",
            "drag",
            actuator.drag(
                points.drag_start,
                points.drag_end,
                start_target_size_pixels=(72, 72),
                end_target_size_pixels=(170, 100),
            ),
            points.drag_end,
        )
        _set_status(root, state, "Drag complete. Scrolling...")
        time.sleep(0.25)
        scroll = actuator.scroll(
            points.scroll_target,
            -5,
            target_size_pixels=(220, 140),
        )
        steps.append(
            MouseDemoStep(
                "scroll-panel",
                "scroll",
                {
                    "point": list(points.scroll_target),
                    **_scroll_metadata(scroll),
                },
            )
        )
        _set_status(root, state, "Scroll complete. Finishing...")
        time.sleep(0.25)
        _record_movement(
            steps,
            "finish-click",
            "click",
            actuator.click(points.finish_target, target_size_pixels=(160, 70)),
            points.finish_target,
        )
    except Exception as exc:  # pragma: no cover - exercised manually on Windows.
        failed.append(str(exc))
    finally:
        completed.set()


def _record_movement(
    steps: list[MouseDemoStep],
    step_id: str,
    action: str,
    plan: MovementPlan,
    point: tuple[int, int],
) -> None:
    steps.append(
        MouseDemoStep(
            step_id,
            action,
            {
                "point": list(point),
                **_movement_metadata(plan),
            },
        )
    )


def _movement_metadata(plan: MovementPlan) -> dict[str, object]:
    metadata: dict[str, object] = {
        "movement_points": len(plan.points),
        "movement_duration_seconds": plan.duration_seconds,
        "movement_smoothness": plan.movement_smoothness,
        "pointer_path_model": plan.path_model,
        "overshoot_applied": plan.overshoot_applied,
        "overshoot_point": list(plan.overshoot_point) if plan.overshoot_point else None,
        "settle_duration_seconds": plan.settle_duration_seconds,
        "random_seed": plan.random_seed,
        "sample_records": [record.metadata() for record in plan.sample_records],
    }
    if plan.timing_estimate is not None:
        metadata.update(plan.timing_estimate.metadata())
    return metadata


def _scroll_metadata(plan: ScrollCadencePlan) -> dict[str, object]:
    return plan.metadata()


def _set_status(root: Any, state: dict[str, Any], text: str) -> None:
    root.after(0, lambda: state["status"].set(text))


def _mark_done(canvas: Any, state: dict[str, Any], status: str) -> None:
    color = "#2f8f46" if status == "passed" else "#b3261e"
    state["status"].set(f"Demo {status}. Report written under traces.")
    canvas.itemconfig(state["finish_shape"], fill=color)


def _build_demo_window(tk: Any) -> tuple[Any, Any, dict[str, Any]]:
    root = tk.Tk()
    root.title("DeskPilot Mouse Demo")
    root.geometry("900x560+120+120")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=16, pady=16)
    frame.pack(fill="both", expand=True)
    status = tk.StringVar(value="Starting visible mouse demo...")
    tk.Label(
        frame,
        textvariable=status,
        font=("Segoe UI", 12, "bold"),
        anchor="w",
    ).pack(fill="x")
    canvas = tk.Canvas(frame, width=860, height=470, bg="#f6f8fb", highlightthickness=0)
    canvas.pack(pady=(12, 0))

    click_shape = canvas.create_rectangle(
        60,
        70,
        220,
        140,
        fill="#d7e8ff",
        outline="#2f67b2",
        width=2,
    )
    canvas.create_text(140, 105, text="Click target", font=("Segoe UI", 13, "bold"))
    canvas.create_rectangle(
        330,
        165,
        550,
        315,
        fill="#fff6d7",
        outline="#a97900",
        width=2,
    )
    canvas.create_text(440, 205, text="Scroll zone", font=("Segoe UI", 13, "bold"))
    canvas.create_text(440, 245, text="Wheel input lands here", font=("Segoe UI", 10))
    canvas.create_oval(80, 310, 152, 382, fill="#f3c6d3", outline="#9a3150", width=2)
    canvas.create_text(116, 346, text="Drag", font=("Segoe UI", 11, "bold"))
    canvas.create_rectangle(
        620,
        290,
        790,
        390,
        fill="#dff4df",
        outline="#3d8742",
        width=2,
    )
    canvas.create_text(705, 340, text="Drop zone", font=("Segoe UI", 13, "bold"))
    finish_shape = canvas.create_rectangle(
        640,
        70,
        800,
        140,
        fill="#e7ddff",
        outline="#6542a6",
        width=2,
    )
    canvas.create_text(720, 105, text="Finish", font=("Segoe UI", 13, "bold"))
    canvas.create_line(230, 105, 630, 105, fill="#8a94a6", width=2, dash=(4, 4))
    canvas.create_line(155, 346, 615, 346, fill="#8a94a6", width=2, dash=(4, 4))

    state: dict[str, Any] = {
        "status": status,
        "click_shape": click_shape,
        "finish_shape": finish_shape,
    }
    canvas.bind(
        "<Button-1>",
        lambda _event: canvas.itemconfig(click_shape, fill="#9fd0ff"),
    )
    canvas.bind("<MouseWheel>", lambda _event: status.set("Wheel event received"))
    root.update_idletasks()
    return root, canvas, state


def _demo_points(canvas: Any) -> MouseDemoPoints:
    root_x = int(canvas.winfo_rootx())
    root_y = int(canvas.winfo_rooty())
    return MouseDemoPoints(
        click_target=(root_x + 140, root_y + 105),
        drag_start=(root_x + 116, root_y + 346),
        drag_end=(root_x + 705, root_y + 340),
        scroll_target=(root_x + 440, root_y + 245),
        finish_target=(root_x + 720, root_y + 105),
    )


def _write_report(
    trace_dir: Path,
    steps: list[MouseDemoStep],
    status: str,
    errors: list[str],
) -> Path:
    payload = {
        "status": status,
        "errors": list(errors),
        "steps": [
            {
                "step_id": step.step_id,
                "action": step.action,
                "metadata": step.metadata,
            }
            for step in steps
        ],
    }
    report_path = trace_dir / "mouse-demo-report.json"
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def _prepare_trace_dir(trace_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = trace_root / f"{timestamp}-mouse-demo"
    trace_dir.mkdir(parents=True, exist_ok=False)
    return trace_dir


def _set_process_dpi_aware() -> None:
    try:
        cast(Any, ctypes).windll.user32.SetProcessDPIAware()
    except Exception:
        # DPI awareness is best-effort; the demo can still run without it.
        return


def _load_tkinter() -> Any:
    try:
        import tkinter as tk
    except Exception as exc:  # pragma: no cover - depends on Windows install.
        raise MouseDemoError("tkinter is required for demo-mouse") from exc
    return tk
