# Goal Planning

Goal planning is the layer that maps a user's natural-language goal to known,
validated routines. It does not execute raw model output or invent desktop
actions. Execution remains limited to routine IDs that already exist in the
catalog and compile through the normal task/playbook pipeline.

## GoalPlan Schema

`desktop_agent.goal_planning.GoalPlan` is the traceable planning record:

- `user_goal`: the original user request.
- `normalized_intent`: deterministic normalized intent text.
- `candidate_routines`: ranked routine candidates with matched fields, score,
  safety class, and approval policy.
- `selected_routine_id`: the chosen routine ID, which must reference one of the
  candidates.
- `missing_inputs`: required variables or session state that block execution.
- `approvals`: approval requirements and whether they are satisfied.
- `explanation`: operator-facing reason for the selection or block.
- `execution_status`: `draft`, `blocked`, `ready`, `running`, `completed`,
  `failed`, or `canceled`.

`execution_ready` is true only when the plan is `ready`, a selected candidate is
present, required inputs are complete, and all required approvals are satisfied.

## Boundary

The schema is intentionally deterministic and local. Optional model output may
later help rank or explain candidates, but it cannot bypass validation, select
unknown routine IDs, or execute raw actions directly.
