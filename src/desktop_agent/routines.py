"""Routine catalog schema contracts for personal assistant packs."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

import yaml

from desktop_agent.redaction import (
    RedactionPolicy,
    redaction_policy_from_mapping,
    validate_redaction_policy,
)

ROUTINE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SUPPORTED_ROUTINE_SAFETY_CLASSES: frozenset[str] = frozenset(
    {"low", "medium", "high", "sensitive"},
)
SUPPORTED_SCHEDULE_POLICIES: frozenset[str] = frozenset(
    {"manual", "on_demand", "scheduled"},
)
SUPPORTED_APPROVAL_POLICIES: frozenset[str] = frozenset(
    {"none", "confirm", "manifest_required", "manual_handoff"},
)
SUPPORTED_QUARANTINE_STATUSES: frozenset[str] = frozenset(
    {"active", "quarantined"},
)
ROUTINE_QUARANTINE_FAILURE_THRESHOLD = 3
RoutineReferenceKind = Literal["task", "playbook"]
TIME_OF_DAY_PATTERN = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
SUPPORTED_SCHEDULE_DAYS: frozenset[str] = frozenset(
    {"mon", "tue", "wed", "thu", "fri", "sat", "sun"},
)
ROUTINE_DOCUMENTATION_TEMPLATE = """# <Routine Name>

## Routine Contract

- [ ] Routine ID:
- [ ] Pack:
- [ ] Owner:
- [ ] Goal:
- [ ] Required app:
- [ ] Required site:
- [ ] Safety class:
- [ ] Schedule policy:
- [ ] Approval policy:

## Inputs And Outputs

- [ ] Inputs are named and bounded:
- [ ] Outputs are observable:
- [ ] Local files, browser pages, or native windows touched:

## Execution Surface

- [ ] YAML task or playbook reference:
- [ ] Allowed windows:
- [ ] Target selectors:
- [ ] Recovery rules:
- [ ] Stop conditions:

## Verification And Reports

- [ ] Dry-run report path:
- [ ] Fixture test path:
- [ ] Trace replay summary:
- [ ] Before screenshot:
- [ ] After screenshot:
- [ ] Windows proof path, when applicable:
- [ ] Approval manifest path, when applicable:
- [ ] Redaction review:

## Monitoring

- [ ] Promotion gates reviewed:
- [ ] Failed evidence count:
- [ ] Quarantine status:
- [ ] Follow-up owner and date:
"""


class RoutineDefinitionError(ValueError):
    """Raised when a routine definition fails schema validation."""


@dataclass(frozen=True)
class RoutineReference:
    """Reference to executable routine implementation content."""

    kind: RoutineReferenceKind
    task_path: Path | None = None
    playbook_site: str | None = None
    playbook_flow: str | None = None


@dataclass(frozen=True)
class RoutineTimeWindow:
    """Allowed local time window for scheduled routine eligibility."""

    start: str
    end: str
    days: tuple[str, ...] = ()
    timezone: str = "local"

    def metadata(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "days": list(self.days),
            "timezone": self.timezone,
        }


@dataclass(frozen=True)
class RoutineSchedule:
    """Scheduling constraints attached to a reviewed routine definition."""

    allowed_time_windows: tuple[RoutineTimeWindow, ...] = ()
    cooldown_seconds: float = 0.0
    max_runs_per_day: int | None = None
    max_runs_per_week: int | None = None
    max_external_mutations: int | None = None
    stop_conditions: tuple[str, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "allowed_time_windows": [
                window.metadata() for window in self.allowed_time_windows
            ],
            "cooldown_seconds": self.cooldown_seconds,
            "max_runs_per_day": self.max_runs_per_day,
            "max_runs_per_week": self.max_runs_per_week,
            "max_external_mutations": self.max_external_mutations,
            "stop_conditions": list(self.stop_conditions),
        }


@dataclass(frozen=True)
class RoutineDefinition:
    """Reviewed routine metadata stored in routine packs."""

    id: str
    name: str
    description: str
    goal: str
    required_app: str | None
    required_site: str | None
    tags: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    safety_class: str
    schedule_policy: str
    approval_policy: str
    expected_duration_seconds: float
    reference: RoutineReference
    schedule: RoutineSchedule = RoutineSchedule()
    failed_evidence_count: int = 0
    quarantine_failure_threshold: int = ROUTINE_QUARANTINE_FAILURE_THRESHOLD
    quarantine_status: str = "active"
    quarantine_reason: str | None = None
    redaction_policy: RedactionPolicy = field(default_factory=RedactionPolicy)
    source_path: Path | None = None

    def report_metadata(self) -> dict[str, object]:
        """Return JSON-safe routine fields for traces and catalog reports."""
        quarantine = routine_quarantine_status(self)
        return {
            "routine_id": self.id,
            "routine_name": self.name,
            "routine_tags": list(self.tags),
            "routine_safety_class": self.safety_class,
            "routine_schedule_policy": self.schedule_policy,
            "routine_approval_policy": self.approval_policy,
            "routine_expected_duration_seconds": self.expected_duration_seconds,
            "routine_reference_kind": self.reference.kind,
            "routine_schedule": self.schedule.metadata(),
            "routine_failed_evidence_count": self.failed_evidence_count,
            "routine_quarantine_failure_threshold": (
                self.quarantine_failure_threshold
            ),
            "routine_quarantine_status": quarantine,
            "routine_quarantine_reason": self.quarantine_reason,
            "routine_redaction_policy": self.redaction_policy.metadata(),
            "routine_promotion_gates": [
                gate.metadata() for gate in routine_promotion_gates(self)
            ],
        }


@dataclass(frozen=True)
class RoutineSearchResult:
    """Ranked catalog search hit for a routine query."""

    routine: RoutineDefinition
    score: int
    matched_fields: tuple[str, ...]


@dataclass(frozen=True)
class RoutinePromotionGate:
    """Promotion requirement used before a routine enters the main catalog."""

    id: str
    description: str
    required: bool = True

    def metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "description": self.description,
            "required": self.required,
        }


@dataclass(frozen=True)
class RoutineExecutionGate:
    """Safety decision for turning a routine ID into executable content."""

    routine_id: str
    allowed: bool
    reason: str
    routine: RoutineDefinition | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "allowed": self.allowed,
            "reason": self.reason,
            "routine_found": self.routine is not None,
        }


@dataclass(frozen=True)
class RoutineFailureCounters:
    """Historical run counters derived from local routine trace reports."""

    routine_id: str
    total_runs: int = 0
    passed_runs: int = 0
    failed_runs: int = 0
    aborted_runs: int = 0
    emergency_stopped_runs: int = 0

    @property
    def failure_count(self) -> int:
        return self.failed_runs + self.aborted_runs + self.emergency_stopped_runs

    def record_status(self, status: str) -> RoutineFailureCounters:
        if status == "passed":
            return self._replace(passed_runs=self.passed_runs + 1)
        if status == "failed":
            return self._replace(failed_runs=self.failed_runs + 1)
        if status == "aborted":
            return self._replace(aborted_runs=self.aborted_runs + 1)
        if status == "emergency_stopped":
            return self._replace(
                emergency_stopped_runs=self.emergency_stopped_runs + 1,
            )
        return self

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "routine_historical_total_runs": self.total_runs,
            "routine_historical_passed_runs": self.passed_runs,
            "routine_historical_failed_runs": self.failed_runs,
            "routine_historical_aborted_runs": self.aborted_runs,
            "routine_historical_emergency_stopped_runs": self.emergency_stopped_runs,
            "routine_historical_failure_count": self.failure_count,
        }

    def _replace(self, **changes: int) -> RoutineFailureCounters:
        values = {
            "total_runs": self.total_runs + 1,
            "passed_runs": self.passed_runs,
            "failed_runs": self.failed_runs,
            "aborted_runs": self.aborted_runs,
            "emergency_stopped_runs": self.emergency_stopped_runs,
            **changes,
        }
        return RoutineFailureCounters(routine_id=self.routine_id, **values)


@dataclass(frozen=True)
class RoutineCatalog:
    """Loaded routine catalog with ID lookup and local search."""

    root: Path
    routines: tuple[RoutineDefinition, ...]

    def by_id(self, routine_id: str) -> RoutineDefinition | None:
        for routine in self.routines:
            if routine.id == routine_id:
                return routine
        return None

    def search(self, query: str, *, limit: int = 20) -> tuple[RoutineSearchResult, ...]:
        return search_routine_catalog(self, query, limit=limit)


def load_routine_definition(path: Path) -> RoutineDefinition:
    """Load one routine YAML definition from a routine pack."""
    if not path.exists():
        raise RoutineDefinitionError(f"routine definition not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    data = _mapping(loaded, "routine definition must contain a mapping")
    routine = routine_definition_from_mapping(data, source_path=path)
    validate_routine_definition(routine)
    return routine


def load_routine_catalog(root: Path = Path("routine_packs")) -> RoutineCatalog:
    """Load every routine definition in a routine pack tree."""
    if not root.exists():
        raise RoutineDefinitionError(f"routine catalog directory not found: {root}")
    paths = sorted(
        {
            *root.rglob("*.routine.yaml"),
            *root.rglob("*.routine.yml"),
        },
    )
    catalog = RoutineCatalog(
        root=root,
        routines=tuple(load_routine_definition(path) for path in paths),
    )
    validate_routine_catalog(catalog)
    return catalog


def routine_failure_counters_from_trace_root(
    trace_root: Path,
) -> dict[str, RoutineFailureCounters]:
    """Build routine run counters from local final-report JSON artifacts."""
    if not trace_root.exists():
        return {}

    counters: dict[str, RoutineFailureCounters] = {}
    for report_path in sorted(trace_root.rglob("final-report.json")):
        report = _json_report(report_path)
        if report is None:
            continue
        routine_id = _routine_id_from_report(report)
        status = report.get("status")
        if routine_id is None or not isinstance(status, str):
            continue
        counter = counters.get(
            routine_id,
            RoutineFailureCounters(routine_id=routine_id),
        )
        counters[routine_id] = counter.record_status(status)
    return counters


def routine_definition_from_mapping(
    data: Mapping[str, object],
    *,
    source_path: Path | None = None,
) -> RoutineDefinition:
    """Parse a routine definition mapping into a typed schema object."""
    base_dir = source_path.parent if source_path is not None else Path(".")
    routine = RoutineDefinition(
        id=_required_string(data, "id"),
        name=_required_string(data, "name"),
        description=_required_string(data, "description"),
        goal=_required_string(data, "goal"),
        required_app=_optional_string(data, "required_app"),
        required_site=_optional_string(data, "required_site"),
        tags=_string_tuple(data.get("tags"), "tags"),
        inputs=_string_tuple(data.get("inputs"), "inputs"),
        outputs=_string_tuple(data.get("outputs"), "outputs"),
        safety_class=_required_string(data, "safety_class"),
        schedule_policy=_required_string(data, "schedule_policy"),
        approval_policy=_required_string(data, "approval_policy"),
        expected_duration_seconds=_positive_float(
            data.get("expected_duration_seconds"),
            "expected_duration_seconds",
        ),
        reference=_reference_from_value(data.get("reference"), base_dir),
        schedule=_schedule_from_value(data.get("schedule")),
        failed_evidence_count=_optional_non_negative_int(
            data.get("failed_evidence_count"),
            "failed_evidence_count",
        ),
        quarantine_failure_threshold=(
            _optional_positive_int(
                data.get("quarantine_failure_threshold"),
                "quarantine_failure_threshold",
            )
            or ROUTINE_QUARANTINE_FAILURE_THRESHOLD
        ),
        quarantine_status=(
            _optional_string(data, "quarantine_status") or "active"
        ),
        quarantine_reason=_optional_string(data, "quarantine_reason"),
        redaction_policy=_redaction_policy_from_value(
            data.get("redaction_policy"),
        ),
        source_path=source_path,
    )
    validate_routine_definition(routine)
    return routine


def validate_routine_catalog(catalog: RoutineCatalog) -> None:
    """Validate catalog-wide constraints after loading routine definitions."""
    errors: list[str] = []
    seen: set[str] = set()
    duplicate_ids: set[str] = set()
    for routine in catalog.routines:
        try:
            validate_routine_definition(routine)
        except RoutineDefinitionError as exc:
            source = f"{routine.source_path}: " if routine.source_path else ""
            errors.append(f"{source}{exc}")
        if routine.id in seen:
            duplicate_ids.add(routine.id)
        seen.add(routine.id)
    for routine_id in sorted(duplicate_ids):
        errors.append(f"duplicate routine id: {routine_id}")
    if errors:
        raise RoutineDefinitionError("; ".join(errors))


def validate_routine_definition(routine: RoutineDefinition) -> None:
    """Validate one routine definition before catalog indexing."""
    errors: list[str] = []
    if not ROUTINE_ID_PATTERN.fullmatch(routine.id):
        errors.append("id is required and must be slug-safe")
    for field_name in ("name", "description", "goal"):
        if not getattr(routine, field_name):
            errors.append(f"{field_name} is required")
    if routine.safety_class not in SUPPORTED_ROUTINE_SAFETY_CLASSES:
        errors.append(f"unsupported safety_class: {routine.safety_class}")
    if routine.schedule_policy not in SUPPORTED_SCHEDULE_POLICIES:
        errors.append(f"unsupported schedule_policy: {routine.schedule_policy}")
    if routine.approval_policy not in SUPPORTED_APPROVAL_POLICIES:
        errors.append(f"unsupported approval_policy: {routine.approval_policy}")
    if routine.expected_duration_seconds <= 0:
        errors.append("expected_duration_seconds must be greater than zero")
    if routine.failed_evidence_count < 0:
        errors.append("failed_evidence_count must not be negative")
    if routine.quarantine_failure_threshold <= 0:
        errors.append("quarantine_failure_threshold must be greater than zero")
    if routine.quarantine_status not in SUPPORTED_QUARANTINE_STATUSES:
        errors.append(f"unsupported quarantine_status: {routine.quarantine_status}")
    if routine.quarantine_status == "quarantined" and not routine.quarantine_reason:
        errors.append("quarantine_reason is required when routine is quarantined")
    errors.extend(_reference_errors(routine.reference))
    errors.extend(_schedule_errors(routine.schedule))
    errors.extend(
        validate_redaction_policy(
            routine.redaction_policy,
            prefix="routine.redaction_policy",
        ),
    )
    if errors:
        raise RoutineDefinitionError("; ".join(errors))


def search_routine_catalog(
    catalog: RoutineCatalog,
    query: str,
    *,
    limit: int = 20,
) -> tuple[RoutineSearchResult, ...]:
    """Search routine metadata with a deterministic local token index."""
    tokens = _query_tokens(query)
    if not tokens or limit <= 0:
        return ()

    results: list[RoutineSearchResult] = []
    for routine in catalog.routines:
        score = 0
        matched_fields: list[str] = []
        for field_name, field_score, field_text in _routine_search_fields(routine):
            field_tokens = set(_query_tokens(field_text))
            matches = tokens & field_tokens
            if not matches:
                continue
            score += field_score * len(matches)
            matched_fields.append(field_name)
        if score:
            results.append(
                RoutineSearchResult(
                    routine=routine,
                    score=score,
                    matched_fields=tuple(dict.fromkeys(matched_fields)),
                ),
            )
    return tuple(
        sorted(results, key=lambda result: (-result.score, result.routine.id))[:limit],
    )


def routine_promotion_gates(
    routine: RoutineDefinition,
) -> tuple[RoutinePromotionGate, ...]:
    """Return the required promotion gates for a routine definition."""
    gates = [
        RoutinePromotionGate(
            id="schema_validation",
            description="RoutineDefinition schema validates.",
        ),
        RoutinePromotionGate(
            id="dry_run",
            description="Compiled routine passes dry-run without desktop input.",
        ),
        RoutinePromotionGate(
            id="fixture_test",
            description="Routine has a browser, native, or synthetic fixture test.",
        ),
        RoutinePromotionGate(
            id="trace_replay_review",
            description="Trace replay summary is reviewed for expected behavior.",
        ),
        RoutinePromotionGate(
            id="documentation",
            description="Routine docs describe inputs, outputs, risk, and proof.",
        ),
    ]
    gates.append(
        RoutinePromotionGate(
            id="windows_proof",
            description="Owned Windows desktop proof is collected when applicable.",
            required=_windows_proof_applicable(routine),
        ),
    )
    return tuple(gates)


def routine_quarantine_status(
    routine: RoutineDefinition,
    failure_counters: RoutineFailureCounters | None = None,
) -> str:
    """Return active/quarantined from explicit state and failure thresholds."""
    if routine.quarantine_status == "quarantined":
        return "quarantined"
    historical_failures = (
        failure_counters.failure_count if failure_counters is not None else 0
    )
    effective_failures = max(routine.failed_evidence_count, historical_failures)
    if effective_failures >= routine.quarantine_failure_threshold:
        return "quarantined"
    return "active"


def routine_execution_gate(
    catalog: RoutineCatalog,
    routine_id: str,
    failure_counters: Mapping[str, RoutineFailureCounters] | None = None,
) -> RoutineExecutionGate:
    """Return whether a routine ID may enter the execution pipeline."""
    if not ROUTINE_ID_PATTERN.fullmatch(routine_id):
        return RoutineExecutionGate(
            routine_id=routine_id,
            allowed=False,
            reason="invalid_routine_id",
        )
    routine = catalog.by_id(routine_id)
    if routine is None:
        return RoutineExecutionGate(
            routine_id=routine_id,
            allowed=False,
            reason="unknown_routine_id",
        )
    try:
        validate_routine_definition(routine)
    except RoutineDefinitionError:
        return RoutineExecutionGate(
            routine_id=routine_id,
            allowed=False,
            reason="invalid_routine_definition",
            routine=routine,
        )
    routine_counter = (failure_counters or {}).get(routine.id)
    if routine_quarantine_status(routine, routine_counter) != "active":
        return RoutineExecutionGate(
            routine_id=routine_id,
            allowed=False,
            reason="routine_quarantined",
            routine=routine,
        )
    return RoutineExecutionGate(
        routine_id=routine_id,
        allowed=True,
        reason="validated_catalog_routine",
        routine=routine,
    )


def require_validated_routine_for_execution(
    catalog: RoutineCatalog,
    routine_id: str,
    failure_counters: Mapping[str, RoutineFailureCounters] | None = None,
) -> RoutineDefinition:
    """Return a routine only after the execution safety gate passes."""
    gate = routine_execution_gate(catalog, routine_id, failure_counters)
    if not gate.allowed or gate.routine is None:
        raise RoutineDefinitionError(
            f"routine execution blocked: {gate.reason} ({routine_id})",
        )
    return gate.routine


def render_routine_documentation_template() -> str:
    """Return the reusable checklist template for one routine review page."""
    return ROUTINE_DOCUMENTATION_TEMPLATE


def render_routine_catalog_index(
    catalog: RoutineCatalog,
    failure_counters: Mapping[str, RoutineFailureCounters] | None = None,
) -> str:
    """Render a deterministic Markdown index and quality report for a catalog."""
    counters = failure_counters or {}
    routines = tuple(sorted(catalog.routines, key=lambda routine: routine.id))
    lines = [
        "# DeskPilot Routine Catalog Index",
        "",
        "Generated from `routine_packs/` routine definitions. Regenerate this",
        "file with `desktop-agent generate-routine-docs` after routine metadata",
        "changes.",
        "",
        "## Catalog Summary",
        "",
        f"- Total routines: {len(routines)}",
        f"- Packs: {_format_counter(_pack_counts(catalog, routines))}",
        f"- Safety classes: {_format_counter(_field_counts(routines, 'safety_class'))}",
        "- Approval policies: "
        f"{_format_counter(_field_counts(routines, 'approval_policy'))}",
        "- Schedule policies: "
        f"{_format_counter(_field_counts(routines, 'schedule_policy'))}",
        f"- Schedule-constrained routines: {_schedule_constrained_count(routines)}",
        f"- Windows proof required: {_windows_proof_required_count(routines)}",
        "- Quarantined routines: "
        f"{_quarantined_count_with_history(routines, counters)}",
        f"- Historical failed runs: {_historical_failure_count(routines, counters)}",
        f"- Approval gaps: {_approval_gap_summary(routines)}",
        "",
        "## Routine Index",
        "",
        "| ID | Pack | Name | Surface | Safety | Approval | Schedule | "
        "Gates | Status | Historical Failures | Reference |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for routine in routines:
        lines.append(_routine_index_row(catalog, routine, counters))
    lines.extend(
        [
            "",
            "## Search Coverage",
            "",
            "The local catalog search indexes routine IDs, names, tags, required app,",
            "required site, descriptions, goals, inputs, outputs, and schedule",
            "constraints. Use these query seeds when checking deep catalog search",
            "behavior:",
            "",
            *_search_seed_lines(catalog, routines),
            "",
            "## Monitoring Fields",
            "",
            "- Promotion gates: schema validation, dry-run, fixture test, trace",
            "  replay review, documentation, and Windows proof when applicable.",
            "- Report metadata: routine ID, name, tags, safety class, schedule",
            "  policy, schedule constraints, approval policy, expected duration,",
            "  reference kind, failed evidence count, historical failure count,",
            "  quarantine status, and promotion gates.",
            "- Quarantine rule: routines are quarantined when explicitly marked or",
            "  when failed evidence or historical failures reach the configured",
            "  threshold.",
            "- Configurable threshold: routine definitions may set",
            "  quarantine_failure_threshold to override the default of three.",
            "",
        ],
    )
    return "\n".join(lines)


def _pack_counts(
    catalog: RoutineCatalog,
    routines: Iterable[RoutineDefinition],
) -> Counter[str]:
    return Counter(_routine_pack_name(catalog, routine) for routine in routines)


def _field_counts(
    routines: Iterable[RoutineDefinition],
    field_name: str,
) -> Counter[str]:
    return Counter(str(getattr(routine, field_name)) for routine in routines)


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(
        f"{name} {count}" for name, count in sorted(counter.items())
    )


def _windows_proof_required_count(routines: Iterable[RoutineDefinition]) -> int:
    return sum(
        any(
            gate.id == "windows_proof" and gate.required
            for gate in routine_promotion_gates(routine)
        )
        for routine in routines
    )


def _quarantined_count(routines: Iterable[RoutineDefinition]) -> int:
    return sum(
        1 for routine in routines if routine_quarantine_status(routine) == "quarantined"
    )


def _quarantined_count_with_history(
    routines: Iterable[RoutineDefinition],
    counters: Mapping[str, RoutineFailureCounters],
) -> int:
    return sum(
        1
        for routine in routines
        if routine_quarantine_status(
            routine,
            counters.get(routine.id),
        )
        == "quarantined"
    )


def _schedule_constrained_count(routines: Iterable[RoutineDefinition]) -> int:
    return sum(1 for routine in routines if routine.schedule != RoutineSchedule())


def _historical_failure_count(
    routines: Iterable[RoutineDefinition],
    counters: Mapping[str, RoutineFailureCounters],
) -> int:
    return sum(
        counters.get(routine.id, _empty_counter(routine.id)).failure_count
        for routine in routines
    )


def _approval_gap_summary(routines: Iterable[RoutineDefinition]) -> str:
    gaps = sorted(
        routine.id
        for routine in routines
        if routine.safety_class in {"high", "sensitive"}
        and routine.approval_policy == "none"
    )
    return "none" if not gaps else ", ".join(gaps)


def _routine_index_row(
    catalog: RoutineCatalog,
    routine: RoutineDefinition,
    counters: Mapping[str, RoutineFailureCounters],
) -> str:
    gates = ",".join(
        gate.id for gate in routine_promotion_gates(routine) if gate.required
    )
    surface = ", ".join(routine.tags) or "untagged"
    cells = (
        routine.id,
        _routine_pack_name(catalog, routine),
        routine.name,
        surface,
        routine.safety_class,
        routine.approval_policy,
        routine.schedule_policy,
        gates,
        routine_quarantine_status(routine, counters.get(routine.id)),
        str(counters.get(routine.id, _empty_counter(routine.id)).failure_count),
        _routine_reference_label(routine),
    )
    return "| " + " | ".join(_markdown_cell(cell) for cell in cells) + " |"


def _empty_counter(routine_id: str) -> RoutineFailureCounters:
    return RoutineFailureCounters(routine_id=routine_id)


def _search_seed_lines(
    catalog: RoutineCatalog,
    routines: Iterable[RoutineDefinition],
) -> list[str]:
    seed_values: list[str] = []
    by_pack = _pack_counts(catalog, routines)
    for pack in sorted(by_pack):
        seed_values.append(pack)
    tag_counter: Counter[str] = Counter()
    site_counter: Counter[str] = Counter()
    app_counter: Counter[str] = Counter()
    for routine in routines:
        tag_counter.update(routine.tags)
        if routine.required_site:
            site_counter.update((routine.required_site,))
        if routine.required_app:
            app_counter.update((routine.required_app,))
    for value in _top_counter_values(tag_counter):
        seed_values.append(value)
    for value in _top_counter_values(site_counter):
        seed_values.append(value)
    for value in _top_counter_values(app_counter):
        seed_values.append(value)
    seeds = list(dict.fromkeys(seed_values))
    return [f"- `{seed}`" for seed in seeds] or ["- `no routines indexed`"]


def _top_counter_values(counter: Counter[str], *, limit: int = 12) -> tuple[str, ...]:
    return tuple(
        value
        for value, _count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    )


def _routine_pack_name(catalog: RoutineCatalog, routine: RoutineDefinition) -> str:
    if routine.source_path is not None:
        try:
            parts = routine.source_path.relative_to(catalog.root).parts
        except ValueError:
            parts = ()
        if parts:
            return parts[0]
    return routine.id.split(".", maxsplit=1)[0]


def _routine_reference_label(routine: RoutineDefinition) -> str:
    reference = routine.reference
    if reference.kind == "task":
        return f"task:{reference.task_path}" if reference.task_path else "task:"
    return f"playbook:{reference.playbook_site}/{reference.playbook_flow}"


def _json_report(path: Path) -> dict[str, object] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _routine_id_from_report(report: Mapping[str, object]) -> str | None:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return None
    routine_id = metadata.get("routine_id")
    return routine_id if isinstance(routine_id, str) else None


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _schedule_from_value(value: object) -> RoutineSchedule:
    if value is None:
        return RoutineSchedule()
    data = _mapping(value, "schedule must be a mapping")
    schedule = RoutineSchedule(
        allowed_time_windows=_time_windows_from_value(
            data.get("allowed_time_windows"),
        ),
        cooldown_seconds=_optional_non_negative_float(
            data.get("cooldown_seconds"),
            "schedule.cooldown_seconds",
        ),
        max_runs_per_day=_optional_positive_int(
            data.get("max_runs_per_day"),
            "schedule.max_runs_per_day",
        ),
        max_runs_per_week=_optional_positive_int(
            data.get("max_runs_per_week"),
            "schedule.max_runs_per_week",
        ),
        max_external_mutations=_optional_non_negative_int_or_none(
            data.get("max_external_mutations"),
            "schedule.max_external_mutations",
        ),
        stop_conditions=_string_tuple(
            data.get("stop_conditions"),
            "schedule.stop_conditions",
        ),
    )
    errors = _schedule_errors(schedule)
    if errors:
        raise RoutineDefinitionError("; ".join(errors))
    return schedule


def _time_windows_from_value(value: object) -> tuple[RoutineTimeWindow, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise RoutineDefinitionError("schedule.allowed_time_windows must be a list")
    return tuple(_time_window_from_value(item) for item in value)


def _time_window_from_value(value: object) -> RoutineTimeWindow:
    data = _mapping(
        value,
        "schedule.allowed_time_windows entries must be mappings",
    )
    return RoutineTimeWindow(
        start=_required_string(data, "start"),
        end=_required_string(data, "end"),
        days=_string_tuple(data.get("days"), "days"),
        timezone=_optional_string(data, "timezone") or "local",
    )


def _schedule_errors(schedule: RoutineSchedule) -> list[str]:
    errors: list[str] = []
    for index, window in enumerate(schedule.allowed_time_windows, start=1):
        prefix = f"schedule.allowed_time_windows[{index}]"
        if not TIME_OF_DAY_PATTERN.fullmatch(window.start):
            errors.append(f"{prefix}.start must be HH:MM")
        if not TIME_OF_DAY_PATTERN.fullmatch(window.end):
            errors.append(f"{prefix}.end must be HH:MM")
        if window.start == window.end:
            errors.append(f"{prefix}.start must differ from end")
        unsupported_days = sorted(set(window.days) - SUPPORTED_SCHEDULE_DAYS)
        if unsupported_days:
            errors.append(
                f"{prefix}.days contains unsupported values: "
                f"{', '.join(unsupported_days)}",
            )
        if not window.timezone.strip():
            errors.append(f"{prefix}.timezone is required")
    if schedule.cooldown_seconds < 0:
        errors.append("schedule.cooldown_seconds must not be negative")
    for field_name in ("max_runs_per_day", "max_runs_per_week"):
        value = getattr(schedule, field_name)
        if value is not None and value <= 0:
            errors.append(f"schedule.{field_name} must be greater than zero")
    if (
        schedule.max_external_mutations is not None
        and schedule.max_external_mutations < 0
    ):
        errors.append("schedule.max_external_mutations must not be negative")
    if any(not condition.strip() for condition in schedule.stop_conditions):
        errors.append("schedule.stop_conditions entries must not be blank")
    return errors


def _reference_from_value(value: object, base_dir: Path) -> RoutineReference:
    data = _mapping(value, "reference must be a mapping")
    kind_value = _required_string(data, "type")
    if kind_value == "task":
        raw_path = _required_string(data, "path")
        task_path = Path(raw_path)
        if not task_path.is_absolute():
            task_path = base_dir / task_path
        return RoutineReference(kind="task", task_path=task_path)
    if kind_value == "playbook":
        return RoutineReference(
            kind="playbook",
            playbook_site=_required_string(data, "site"),
            playbook_flow=_required_string(data, "flow"),
        )
    raise RoutineDefinitionError("reference type must be task or playbook")


def _redaction_policy_from_value(value: object) -> RedactionPolicy:
    if value is None:
        return RedactionPolicy()
    data = _mapping(value, "redaction_policy must be a mapping")
    try:
        return redaction_policy_from_mapping(data)
    except ValueError as exc:
        raise RoutineDefinitionError(str(exc)) from exc


def _routine_search_fields(
    routine: RoutineDefinition,
) -> tuple[tuple[str, int, str], ...]:
    return (
        ("id", 4, routine.id),
        ("name", 4, routine.name),
        ("tags", 3, " ".join(routine.tags)),
        ("required_app", 2, routine.required_app or ""),
        ("required_site", 2, routine.required_site or ""),
        ("safety_class", 2, routine.safety_class),
        ("approval_policy", 2, routine.approval_policy),
        ("schedule_policy", 2, routine.schedule_policy),
        ("description", 1, routine.description),
        ("goal", 1, routine.goal),
        ("inputs", 1, " ".join(routine.inputs)),
        ("outputs", 1, " ".join(routine.outputs)),
        ("schedule", 1, _schedule_search_text(routine.schedule)),
    )


def _schedule_search_text(schedule: RoutineSchedule) -> str:
    windows = [
        " ".join((*window.days, window.start, window.end, window.timezone))
        for window in schedule.allowed_time_windows
    ]
    limits = [
        f"cooldown {schedule.cooldown_seconds:g}",
        f"max runs day {schedule.max_runs_per_day}"
        if schedule.max_runs_per_day is not None
        else "",
        f"max runs week {schedule.max_runs_per_week}"
        if schedule.max_runs_per_week is not None
        else "",
        f"max external mutations {schedule.max_external_mutations}"
        if schedule.max_external_mutations is not None
        else "",
    ]
    return " ".join((*windows, *limits, *schedule.stop_conditions))


def _query_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _windows_proof_applicable(routine: RoutineDefinition) -> bool:
    return bool(routine.required_app) or routine.safety_class in {"high", "sensitive"}


def _reference_errors(reference: RoutineReference) -> list[str]:
    if reference.kind == "task":
        if reference.task_path is not None:
            return []
        return ["task reference path is required"]
    if reference.kind == "playbook":
        errors: list[str] = []
        if not reference.playbook_site:
            errors.append("playbook reference site is required")
        if not reference.playbook_flow:
            errors.append("playbook reference flow is required")
        return errors
    return ["reference type must be task or playbook"]


def _mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RoutineDefinitionError(message)
    return cast(Mapping[str, object], value)


def _required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise RoutineDefinitionError(f"{key} is required")
    return value


def _optional_string(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RoutineDefinitionError(f"{key} must be a string")
    return value or None


def _string_tuple(value: object, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise RoutineDefinitionError(f"{key} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise RoutineDefinitionError(f"{key} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _positive_float(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RoutineDefinitionError(f"{key} must be numeric")
    result = float(value)
    if result <= 0:
        raise RoutineDefinitionError(f"{key} must be greater than zero")
    return result


def _optional_non_negative_float(value: object, key: str) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RoutineDefinitionError(f"{key} must be numeric")
    result = float(value)
    if result < 0:
        raise RoutineDefinitionError(f"{key} must not be negative")
    return result


def _optional_positive_int(value: object, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoutineDefinitionError(f"{key} must be an integer")
    if value <= 0:
        raise RoutineDefinitionError(f"{key} must be greater than zero")
    return value


def _optional_non_negative_int(value: object, key: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoutineDefinitionError(f"{key} must be an integer")
    if value < 0:
        raise RoutineDefinitionError(f"{key} must not be negative")
    return value


def _optional_non_negative_int_or_none(value: object, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoutineDefinitionError(f"{key} must be an integer")
    if value < 0:
        raise RoutineDefinitionError(f"{key} must not be negative")
    return value
