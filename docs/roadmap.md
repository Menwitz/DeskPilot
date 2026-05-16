# Roadmap

DeskPilot now has two roadmap layers:

- [`PLAN.md`](../PLAN.md) is the historical v1 implementation checklist for the
  Windows-first YAML/playbook automation foundation.
- [Personal Routine Assistant Roadmap](personal-routine-assistant-roadmap.md)
  is the active product roadmap for recorder, routine catalog, goal planning,
  native operator app, proof bundles, redaction, and ecosystem work.

The v1 checklist remains useful for understanding the implemented foundation.
New post-v1 product work should be planned and checked off in the personal
routine assistant roadmap.

## V1 Execution Order

1. Project definition.
2. Repository bootstrap.
3. Target architecture.
4. CLI.
5. Configuration.
6. YAML task DSL.
7. Screen layer.
8. Windows UI Automation layer.
9. OCR layer.
10. Computer vision layer.
11. Candidate fusion.
12. Actuation layer.
13. Planner and execution engine.
14. Safety system.
15. Tracing and reports.
16. Example workflows.
17. Packaging.
18. Testing.
19. V1 acceptance criteria.
20. Post-v1 backlog.

Each completed top-level task should be committed separately using the commit
message structure defined for this repository.

Post-v1 items that remain broad ideas are tracked in
[Post-v1 Backlog](post-v1-backlog.md). Items that are now part of the personal
routine assistant direction should be promoted into
[Personal Routine Assistant Roadmap](personal-routine-assistant-roadmap.md)
before implementation starts.

Windows-only packaging and real desktop acceptance checks are listed in
`PLAN.md` as pending external verification instead of active implementation
checkboxes, because they require an unlocked, logged-in Windows session.
