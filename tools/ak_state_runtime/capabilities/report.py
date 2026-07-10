from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import (
    CAPABILITY_STATUSES,
    REAL_ADAPTER_GATE,
    SOURCE_CLAIM_CEILING,
    EvidenceResult,
    SourceProbeResult,
)


MATRIX_SCHEMA_NAME = "ak_runtime_capability_matrix"
MATRIX_SCHEMA_VERSION = "0.1.0"


class CapabilityReportError(ValueError):
    """Raised when deterministic source-probe artifacts cannot be published."""


def matrix_bytes(result: SourceProbeResult) -> bytes:
    _validate_result(result)
    status_counts = {
        status: sum(
            capability.status == status for capability in result.capabilities
        )
        for status in CAPABILITY_STATUSES
    }
    record = {
        "schema_name": MATRIX_SCHEMA_NAME,
        "schema_version": MATRIX_SCHEMA_VERSION,
        "probe_kind": "target_tag_source",
        "probe_id": result.probe_id,
        "probe_date": result.probe_date,
        "claim_ceiling": result.claim_ceiling,
        "selected_workload_model_id": result.selected_workload_model_id,
        "selected_workload_validated": result.selected_workload_validated,
        "selected_workload_gate": result.selected_workload_gate,
        "real_vllm_ascend_adapter_gate": (
            result.real_vllm_ascend_adapter_gate
        ),
        "target_count": len(result.targets),
        "capability_count": len(result.capabilities),
        "status_counts": status_counts,
        "targets": [
            {
                "target_id": target.target_id,
                "repo_path": target.repo_path,
                "tag": target.tag,
                "expected_commit": target.expected_commit,
                "observed_commit": target.observed_commit,
                "ref_verified": target.ref_verified,
            }
            for target in result.targets
        ],
        "capabilities": [
            {
                "capability_id": capability.capability_id,
                "runtime_scope": list(capability.runtime_scope),
                "status": capability.status,
                "selected_workload_validated": (
                    capability.selected_workload_validated
                ),
                "runtime_gate": capability.runtime_gate,
                "source_evidence": [
                    _evidence_record(item) for item in capability.source_evidence
                ],
                "instrumentation_evidence": [
                    _evidence_record(item)
                    for item in capability.instrumentation_evidence
                ],
                "documentation_evidence": [
                    _evidence_record(item)
                    for item in capability.documentation_evidence
                ],
            }
            for capability in result.capabilities
        ],
    }
    return yaml.safe_dump(
        record,
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")


def report_bytes(result: SourceProbeResult) -> bytes:
    _validate_result(result)
    lines = [
        "# P8.0 Target-tag Source Capability Probe Report",
        "",
        f"- Probe: `{result.probe_id}`",
        f"- Probe date: `{result.probe_date}`",
        f"- Claim ceiling: `{result.claim_ceiling}`",
        (
            "- Selected workload validated: "
            f"`{str(result.selected_workload_validated).lower()}`"
        ),
        f"- Selected-workload gate: `{result.selected_workload_gate}`",
        (
            "- Real VllmAscendAdapter gate: "
            f"`{result.real_vllm_ascend_adapter_gate}`"
        ),
        "",
        "## Pinned targets",
        "",
        "| Target | Tag | Expected commit | Observed commit | Verified |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        "| {target} | `{tag}` | `{expected}` | `{observed}` | `{verified}` |".format(
            target=_markdown(target.target_id),
            tag=_markdown(target.tag),
            expected=target.expected_commit,
            observed=target.observed_commit,
            verified=str(target.ref_verified).lower(),
        )
        for target in result.targets
    )
    lines.extend(
        [
            "",
            "## Capability matrix",
            "",
            "| Capability | Runtime scope | Source status | Runtime gate |",
            "| --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        "| {capability} | {scope} | `{status}` | `{gate}` |".format(
            capability=_markdown(capability.capability_id),
            scope=_markdown(", ".join(capability.runtime_scope)),
            status=capability.status,
            gate=_markdown(capability.runtime_gate),
        )
        for capability in result.capabilities
    )
    lines.extend(
        [
            "",
            "## Evidence details",
            "",
        ]
    )
    for capability in result.capabilities:
        lines.append(f"### `{capability.capability_id}`")
        lines.append("")
        evidence = (
            *capability.source_evidence,
            *capability.instrumentation_evidence,
            *capability.documentation_evidence,
        )
        for item in evidence:
            location = f"{item.target_id}:{item.path}"
            lines_text = ",".join(str(value) for value in item.matched_lines) or "none"
            result_text = "matched" if item.matched else item.error
            lines.append(
                "- `{group}` `{evidence}` at `{location}`; blob `{blob}`; "
                "lines `{lines}`; result `{result}`; contains `{contains}`.".format(
                    group=item.evidence_group,
                    evidence=_markdown(item.evidence_id),
                    location=_markdown(location),
                    blob=item.blob_oid or "none",
                    lines=lines_text,
                    result=result_text,
                    contains=_markdown(item.contains),
                )
            )
        lines.append("")
    lines.extend(
        [
            "## Boundary",
            "",
            "This report proves only that exact source/config/instrumentation "
            "symbols exist at the pinned Git objects. It does not import or run "
            "either runtime, does not validate the selected workload, and does "
            "not authorize a real VllmAscendAdapter.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def write_source_probe_outputs(
    result: SourceProbeResult,
    matrix_path: Path,
    report_path: Path,
) -> None:
    if matrix_path == report_path:
        raise CapabilityReportError("matrix and report outputs must be different")
    existing = [path for path in (matrix_path, report_path) if path.exists()]
    if existing:
        raise CapabilityReportError(
            "output already exists: " + ", ".join(path.as_posix() for path in existing)
        )

    matrix_payload = matrix_bytes(result)
    report_payload = report_bytes(result)
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with matrix_path.open("xb") as stream:
            stream.write(matrix_payload)
        with report_path.open("xb") as stream:
            stream.write(report_payload)
    except Exception:
        matrix_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        raise


def _evidence_record(item: EvidenceResult) -> dict[str, Any]:
    return {
        "evidence_id": item.evidence_id,
        "target_id": item.target_id,
        "path": item.path,
        "contains": item.contains,
        "matched": item.matched,
        "blob_oid": item.blob_oid,
        "matched_lines": list(item.matched_lines),
        "error": item.error,
    }


def _validate_result(result: SourceProbeResult) -> None:
    if (
        result.claim_ceiling != SOURCE_CLAIM_CEILING
        or result.selected_workload_validated
        or any(
            capability.selected_workload_validated
            or capability.status == "validated_for_selected_workload"
            for capability in result.capabilities
        )
    ):
        raise CapabilityReportError(
            "source probe result exceeds the instrumented claim ceiling"
        )
    if result.real_vllm_ascend_adapter_gate != REAL_ADAPTER_GATE:
        raise CapabilityReportError("real VllmAscendAdapter gate is not preserved")
    bypassed_gates = [
        capability.capability_id
        for capability in result.capabilities
        if capability.runtime_gate != result.selected_workload_gate
    ]
    if bypassed_gates:
        raise CapabilityReportError(
            "capability runtime gate differs from selected-workload gate: "
            + ", ".join(bypassed_gates)
        )
    invalid_statuses = [
        capability.status
        for capability in result.capabilities
        if capability.status not in CAPABILITY_STATUSES
    ]
    if invalid_statuses:
        raise CapabilityReportError(
            "unknown capability status: " + ", ".join(invalid_statuses)
        )
    invalid_targets = [
        target.target_id
        for target in result.targets
        if not target.ref_verified
        or target.expected_commit != target.observed_commit
    ]
    if invalid_targets:
        raise CapabilityReportError(
            "unverified target refs: " + ", ".join(invalid_targets)
        )


def _markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "'")
