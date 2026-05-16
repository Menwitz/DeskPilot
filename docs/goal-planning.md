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

## Routine Index Search

`search_routine_index_for_goal()` wraps the routine catalog search and returns
`GoalPlanCandidate` records with schedule eligibility metadata. Search covers
routine ID, name, required app, required site, tags, inputs, outputs, safety
class, approval policy, schedule policy, and schedule constraint text.

When a timestamp is supplied, scheduled routines with allowed time windows are
marked `inside_allowed_time_window` or `outside_allowed_time_window`. Callers
can set `require_schedule_eligible` to remove routines that are outside their
allowed window before routing or execution.

## Deterministic Router

`route_goal_to_routine()` applies deterministic rules over the routine index:

- exact required app/site filters when the goal supplies those constraints.
- tag and input compatibility bonuses.
- max safety-class filtering.
- schedule eligibility filtering.
- stable score ordering with routine ID as the tie-breaker.

The router returns a `GoalPlan`. Missing inputs or unsatisfied approvals keep the
plan `blocked`; a routine is only `ready` when selected, fully supplied, and
approved.

## Missing-Input Prompts

`missing_input_prompts()` turns blocked plan inputs into explicit operator
prompts. Routine variables use kind `routine_input`; required session
prerequisites such as "browser signed in" use kind `session_state`. Prompt
metadata is JSON-safe so the future CLI dry-run and operator UI can show the
same required inputs before execution.
