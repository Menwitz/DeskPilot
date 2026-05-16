"""Routine catalog schema contracts for personal assistant packs."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

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
    failed_evidence_count: int = 0
    quarantine_status: str = "active"
    quarantine_reason: str | None = None
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
            "routine_failed_evidence_count": self.failed_evidence_count,
            "routine_quarantine_status": quarantine,
            "routine_quarantine_reason": self.quarantine_reason,
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
        failed_evidence_count=_optional_non_negative_int(
            data.get("failed_evidence_count"),
            "failed_evidence_count",
        ),
        quarantine_status=(
            _optional_string(data, "quarantine_status") or "active"
        ),
        quarantine_reason=_optional_string(data, "quarantine_reason"),
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
    if routine.quarantine_status not in SUPPORTED_QUARANTINE_STATUSES:
        errors.append(f"unsupported quarantine_status: {routine.quarantine_status}")
    if routine.quarantine_status == "quarantined" and not routine.quarantine_reason:
        errors.append("quarantine_reason is required when routine is quarantined")
    errors.extend(_reference_errors(routine.reference))
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


def routine_quarantine_status(routine: RoutineDefinition) -> str:
    """Return active/quarantined from explicit state and failed evidence count."""
    if routine.quarantine_status == "quarantined":
        return "quarantined"
    if routine.failed_evidence_count >= ROUTINE_QUARANTINE_FAILURE_THRESHOLD:
        return "quarantined"
    return "active"


def render_routine_documentation_template() -> str:
    """Return the reusable checklist template for one routine review page."""
    return ROUTINE_DOCUMENTATION_TEMPLATE


def render_routine_catalog_index(catalog: RoutineCatalog) -> str:
    """Render a deterministic Markdown index and quality report for a catalog."""
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
        f"- Windows proof required: {_windows_proof_required_count(routines)}",
        f"- Quarantined routines: {_quarantined_count(routines)}",
        f"- Approval gaps: {_approval_gap_summary(routines)}",
        "",
        "## Routine Index",
        "",
        "| ID | Pack | Name | Surface | Safety | Approval | Schedule | "
        "Gates | Status | Reference |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for routine in routines:
        lines.append(_routine_index_row(catalog, routine))
    lines.extend(
        [
            "",
            "## Search Coverage",
            "",
            "The local catalog search indexes routine IDs, names, tags, required app,",
            "required site, descriptions, goals, inputs, and outputs. Use these",
            "query seeds when checking deep catalog search behavior:",
            "",
            *_search_seed_lines(catalog, routines),
            "",
            "## Monitoring Fields",
            "",
            "- Promotion gates: schema validation, dry-run, fixture test, trace",
            "  replay review, documentation, and Windows proof when applicable.",
            "- Report metadata: routine ID, name, tags, safety class, schedule",
            "  policy, approval policy, expected duration, reference kind, failed",
            "  evidence count, quarantine status, and promotion gates.",
            "- Quarantine rule: routines are quarantined when explicitly marked or",
            "  when failed evidence count reaches three.",
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


def _approval_gap_summary(routines: Iterable[RoutineDefinition]) -> str:
    gaps = sorted(
        routine.id
        for routine in routines
        if routine.safety_class in {"high", "sensitive"}
        and routine.approval_policy == "none"
    )
    return "none" if not gaps else ", ".join(gaps)


def _routine_index_row(catalog: RoutineCatalog, routine: RoutineDefinition) -> str:
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
        routine_quarantine_status(routine),
        _routine_reference_label(routine),
    )
    return "| " + " | ".join(_markdown_cell(cell) for cell in cells) + " |"


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


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


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


def _routine_search_fields(
    routine: RoutineDefinition,
) -> tuple[tuple[str, int, str], ...]:
    return (
        ("id", 4, routine.id),
        ("name", 4, routine.name),
        ("tags", 3, " ".join(routine.tags)),
        ("required_app", 2, routine.required_app or ""),
        ("required_site", 2, routine.required_site or ""),
        ("description", 1, routine.description),
        ("goal", 1, routine.goal),
        ("inputs", 1, " ".join(routine.inputs)),
        ("outputs", 1, " ".join(routine.outputs)),
    )


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


def _optional_non_negative_int(value: object, key: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoutineDefinitionError(f"{key} must be an integer")
    if value < 0:
        raise RoutineDefinitionError(f"{key} must not be negative")
    return value
