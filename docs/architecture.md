# Architecture

DeskPilot v1 is organized as a local execution engine with strict platform
boundaries. The planner and task DSL should remain platform-neutral, while
screen capture, UI Automation, and actuation are implemented behind adapters.

## Planned Runtime Modules

- `cli` parses user commands and runtime overrides.
- `config` loads defaults, config files, task overrides, and CLI overrides.
- `task_dsl` validates YAML task files.
- `screen` captures screenshots and normalizes coordinates.
- `perception` performs UIA, OCR, and image-template candidate discovery.
- `actuation` moves the mouse, sends keyboard input, and scrolls.
- `planner` executes validated task steps with retries and recovery.
- `safety` enforces window allowlists, limits, and emergency stop behavior.
- `tracing` writes local logs, screenshots, OCR text, candidates, and reports.
- `platforms/windows` contains Windows-specific adapters.
- `platforms/linux_placeholder` reserves the future Linux adapter boundary.

The initial architecture commit defines these modules as Python contracts plus
safe in-memory implementations for tests. Real adapters are added in later
roadmap phases without changing the planner contract.

## Execution Pipeline

1. Load default configuration.
2. Load project-level configuration.
3. Load task YAML and task-level overrides.
4. Apply CLI overrides.
5. Validate configuration and task schema.
6. Prepare a per-run trace directory.
7. Check safety preconditions.
8. Observe the screen and active window.
9. Search for candidates through UIA, OCR, and computer vision.
10. Rank and select the target candidate.
11. Verify the active window is still allowed.
12. Execute the action.
13. Verify the result when requested.
14. Retry, recover, or abort.
15. Write final machine-readable and human-readable reports.

The `ExecutionEngine` coordinates the pipeline through explicit interfaces for
configuration, task loading, task validation, screen observation, deep candidate
search, target selection, actuation, safety, verification, tracing, and final
reporting.

## Website Playbook Layer

Website playbooks live in `navigation_playbooks/` and compile into normal
`TaskDefinition` objects before execution. The layer adds reusable site domains,
allowed window-title patterns, landmarks, flows, blocked states, and site
metadata without bypassing the planner, deep-search perception pipeline, safety
checks, tracing, or reports.

The compiler preserves confirmation requirements, inserts blocked-state checks
before confirmation-gated site actions, and writes site ID, flow ID, domains,
version, sensitive step IDs, and blocked-state IDs into task metadata.
The CLI boundary exposes this layer through `list-sites`, `list-flows`,
`compile-site`, `dry-run-site`, and `run-site`; each command still hands a
validated task to the same execution, safety, tracing, and final-reporting
pipeline used by hand-authored task YAML.

Site run traces and reports must keep the selected playbook version, site ID,
flow ID, blocked-state outcomes, sensitive confirmation state, and approved step
metadata so monitoring and support review can diagnose public-site failures
without replaying live input.

## Observability

Every runtime phase should leave enough local trace data to diagnose a failed
run without rerunning the desktop action. Reports should include the final
status, abort reason, step timings, selected candidates, confidence values, and
paths to any saved screenshots or OCR artifacts. Step timeout budget events
record planned action and retry waits before desktop input, and timing events
include the bounded operator breakdown used for cognitive timing so reports can
explain mental pauses, system waits, keying, pointing, and homing without
changing the task's selected actions. Entropy budget events record task-level
and step-level randomness allocations before later sampling logic can consume
them. Bounded random decisions flow through a shared seeded sampler so timing
and actuation choices can be replayed deterministically when a seed is set.
Distribution choices are constrained to timing/retry sampling and explicitly
approved safe action variants.
