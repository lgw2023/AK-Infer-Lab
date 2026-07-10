from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping


SCHEMA_NAME = "ak_target_tag_source_probe"
SCHEMA_VERSION = "0.1.0"
SOURCE_CLAIM_CEILING = "instrumented"
REAL_ADAPTER_GATE = "waiting_selected_workload_runtime_gate"
CAPABILITY_STATUSES = (
    "unsupported",
    "documented_unverified",
    "available_uninstrumented",
    "instrumented",
    "validated_for_selected_workload",
)
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class ProbeSpecError(ValueError):
    """Raised when a source capability probe specification is unsafe or invalid."""


@dataclass(frozen=True)
class EvidenceClause:
    evidence_id: str
    target_id: str
    path: str
    contains: str


@dataclass(frozen=True)
class TargetSpec:
    target_id: str
    repo_path: str
    tag: str
    expected_commit: str


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    runtime_scope: tuple[str, ...]
    source_evidence: tuple[EvidenceClause, ...]
    instrumentation_evidence: tuple[EvidenceClause, ...]
    documentation_evidence: tuple[EvidenceClause, ...]


@dataclass(frozen=True)
class SourceProbeSpec:
    probe_id: str
    probe_date: str
    claim_ceiling: str
    selected_workload_model_id: str
    selected_workload_validated: bool
    selected_workload_gate: str
    real_vllm_ascend_adapter_gate: str
    targets: tuple[TargetSpec, ...]
    capabilities: tuple[CapabilitySpec, ...]


@dataclass(frozen=True)
class EvidenceResult:
    evidence_id: str
    evidence_group: str
    target_id: str
    path: str
    contains: str
    matched: bool
    blob_oid: str | None
    matched_lines: tuple[int, ...]
    error: str | None


@dataclass(frozen=True)
class TargetResult:
    target_id: str
    repo_path: str
    tag: str
    expected_commit: str
    observed_commit: str
    ref_verified: bool


@dataclass(frozen=True)
class CapabilityResult:
    capability_id: str
    runtime_scope: tuple[str, ...]
    status: str
    source_evidence: tuple[EvidenceResult, ...]
    instrumentation_evidence: tuple[EvidenceResult, ...]
    documentation_evidence: tuple[EvidenceResult, ...]
    selected_workload_validated: bool
    runtime_gate: str


@dataclass(frozen=True)
class SourceProbeResult:
    probe_id: str
    probe_date: str
    claim_ceiling: str
    selected_workload_model_id: str
    selected_workload_validated: bool
    selected_workload_gate: str
    real_vllm_ascend_adapter_gate: str
    targets: tuple[TargetResult, ...]
    capabilities: tuple[CapabilityResult, ...]


def parse_probe_spec(record: Mapping[str, Any]) -> SourceProbeSpec:
    root = _mapping(record, "probe spec")
    if _string(root, "schema_name", "probe spec") != SCHEMA_NAME:
        raise ProbeSpecError(f"schema_name must be {SCHEMA_NAME!r}")
    if _string(root, "schema_version", "probe spec") != SCHEMA_VERSION:
        raise ProbeSpecError(f"schema_version must be {SCHEMA_VERSION!r}")

    claim_ceiling = _string(root, "claim_ceiling", "probe spec")
    if claim_ceiling != SOURCE_CLAIM_CEILING:
        raise ProbeSpecError(
            f"claim_ceiling must be {SOURCE_CLAIM_CEILING!r} for a source probe"
        )

    selected = _mapping(root.get("selected_workload"), "selected_workload")
    selected_validated = _boolean(selected, "validated", "selected_workload")
    if selected_validated:
        raise ProbeSpecError(
            "selected_workload.validated must be false for a source-only probe"
        )

    adapter_gate = _string(
        root,
        "real_vllm_ascend_adapter_gate",
        "probe spec",
    )
    if adapter_gate != REAL_ADAPTER_GATE:
        raise ProbeSpecError(
            "real_vllm_ascend_adapter_gate must remain "
            f"{REAL_ADAPTER_GATE!r}"
        )

    targets = _parse_targets(root.get("targets"))
    capabilities = _parse_capabilities(root.get("capabilities"), targets)
    return SourceProbeSpec(
        probe_id=_string(root, "probe_id", "probe spec"),
        probe_date=_string(root, "probe_date", "probe spec"),
        claim_ceiling=claim_ceiling,
        selected_workload_model_id=_string(
            selected,
            "model_id",
            "selected_workload",
        ),
        selected_workload_validated=selected_validated,
        selected_workload_gate=_string(
            selected,
            "gate",
            "selected_workload",
        ),
        real_vllm_ascend_adapter_gate=adapter_gate,
        targets=targets,
        capabilities=capabilities,
    )


def _parse_targets(value: Any) -> tuple[TargetSpec, ...]:
    rows = _list(value, "targets")
    if not rows:
        raise ProbeSpecError("targets must not be empty")

    targets: list[TargetSpec] = []
    seen: set[str] = set()
    for index, value in enumerate(rows):
        context = f"targets[{index}]"
        row = _mapping(value, context)
        target_id = _string(row, "target_id", context)
        if target_id in seen:
            raise ProbeSpecError(f"duplicate target_id: {target_id}")
        seen.add(target_id)

        repo_path = _relative_path(_string(row, "repo_path", context), context)
        tag = _string(row, "tag", context)
        if tag.startswith("-"):
            raise ProbeSpecError(f"{context}.tag must not begin with '-'")
        expected_commit = _string(row, "expected_commit", context)
        if not _COMMIT_PATTERN.fullmatch(expected_commit):
            raise ProbeSpecError(
                f"{context}.expected_commit must be a lowercase 40-hex commit"
            )
        targets.append(
            TargetSpec(
                target_id=target_id,
                repo_path=repo_path,
                tag=tag,
                expected_commit=expected_commit,
            )
        )
    return tuple(targets)


def _parse_capabilities(
    value: Any,
    targets: tuple[TargetSpec, ...],
) -> tuple[CapabilitySpec, ...]:
    rows = _list(value, "capabilities")
    if not rows:
        raise ProbeSpecError("capabilities must not be empty")

    target_ids = {target.target_id for target in targets}
    capability_ids: set[str] = set()
    evidence_ids: set[str] = set()
    capabilities: list[CapabilitySpec] = []
    for index, value in enumerate(rows):
        context = f"capabilities[{index}]"
        row = _mapping(value, context)
        capability_id = _string(row, "capability_id", context)
        if capability_id in capability_ids:
            raise ProbeSpecError(f"duplicate capability_id: {capability_id}")
        capability_ids.add(capability_id)

        runtime_scope = tuple(
            _nonempty_string(item, f"{context}.runtime_scope")
            for item in _list(row.get("runtime_scope"), f"{context}.runtime_scope")
        )
        if not runtime_scope:
            raise ProbeSpecError(f"{context}.runtime_scope must not be empty")

        groups = {
            name: _parse_evidence_group(
                row.get(name),
                f"{context}.{name}",
                target_ids,
                evidence_ids,
            )
            for name in (
                "source_evidence",
                "instrumentation_evidence",
                "documentation_evidence",
            )
        }
        if not groups["source_evidence"] and not groups["documentation_evidence"]:
            raise ProbeSpecError(
                f"{context} requires source_evidence or documentation_evidence"
            )
        if groups["instrumentation_evidence"] and not groups["source_evidence"]:
            raise ProbeSpecError(
                f"{context}.instrumentation_evidence requires source_evidence"
            )
        capabilities.append(
            CapabilitySpec(
                capability_id=capability_id,
                runtime_scope=runtime_scope,
                source_evidence=groups["source_evidence"],
                instrumentation_evidence=groups["instrumentation_evidence"],
                documentation_evidence=groups["documentation_evidence"],
            )
        )
    return tuple(capabilities)


def _parse_evidence_group(
    value: Any,
    context: str,
    target_ids: set[str],
    seen_ids: set[str],
) -> tuple[EvidenceClause, ...]:
    clauses: list[EvidenceClause] = []
    for index, value in enumerate(_list(value, context)):
        item_context = f"{context}[{index}]"
        row = _mapping(value, item_context)
        evidence_id = _string(row, "evidence_id", item_context)
        if evidence_id in seen_ids:
            raise ProbeSpecError(f"duplicate evidence_id: {evidence_id}")
        seen_ids.add(evidence_id)
        target_id = _string(row, "target_id", item_context)
        if target_id not in target_ids:
            raise ProbeSpecError(
                f"{item_context} references unknown target_id {target_id!r}"
            )
        clauses.append(
            EvidenceClause(
                evidence_id=evidence_id,
                target_id=target_id,
                path=_relative_path(_string(row, "path", item_context), item_context),
                contains=_string(row, "contains", item_context),
            )
        )
    return tuple(clauses)


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProbeSpecError(f"{context} must be a mapping")
    return value


def _list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProbeSpecError(f"{context} must be a list")
    return value


def _string(record: Mapping[str, Any], key: str, context: str) -> str:
    if key not in record:
        raise ProbeSpecError(f"{context}.{key} is required")
    return _nonempty_string(record[key], f"{context}.{key}")


def _nonempty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProbeSpecError(f"{context} must be a non-empty string")
    return value


def _boolean(record: Mapping[str, Any], key: str, context: str) -> bool:
    if key not in record or not isinstance(record[key], bool):
        raise ProbeSpecError(f"{context}.{key} must be a boolean")
    return record[key]


def _relative_path(value: str, context: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value in {"", "."}:
        raise ProbeSpecError(f"{context} path must be a non-root relative path")
    return path.as_posix()
