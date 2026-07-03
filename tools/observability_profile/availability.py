from __future__ import annotations

from copy import deepcopy
from typing import Any

from tools.observability_profile.constants import AVAILABILITY_STATUSES


MANIFEST_FIELD_KEYS = {
    "server_observability_profile.os_name": "os_name",
    "server_observability_profile.kernel_version": "kernel_version",
    "server_observability_profile.cann_version": "cann_version",
    "server_observability_profile.driver_version": "driver_version",
    "server_observability_profile.firmware_version": "firmware_version",
    "server_observability_profile.torch_npu_version": "torch_npu_version",
    "server_observability_profile.mindie_version": "mindie_version",
    "server_observability_profile.vllm_ascend_version": "vllm_ascend_version",
    "server_observability_profile.container_privileged": "container_privileged",
    "server_observability_profile.visible_npu_count": "npu_count",
}

MICROBENCH_FIELD_KEYS = {
    "npu_copy_h2d": [
        "microbench_profile.h2d_latency_us",
        "microbench_profile.h2d_bandwidth_gbps",
    ],
    "npu_copy_d2h": [
        "microbench_profile.d2h_latency_us",
        "microbench_profile.d2h_bandwidth_gbps",
    ],
    "npu_copy_overlap": ["microbench_profile.copy_overlap_ratio"],
    "npu_matmul_shape": ["microbench_profile.npu_op_by_shape"],
    "cpu_kernel": ["microbench_profile.cpu_kernel_by_shape"],
    "dram_bandwidth": ["microbench_profile.ddr_bandwidth_gbps"],
    "ssd_fio": ["microbench_profile.ssd_iops"],
}


def _field_key(field: dict[str, Any]) -> str:
    return f"{field['profile']}.{field['name']}"


def _has_known_manifest_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return False
    lowered = text.lower()
    failure_markers = (
        "filenotfounderror",
        "modulenotfounderror",
        "importerror",
        "traceback",
        "not found",
        "timeoutexpired",
        "timed out",
        "timeout",
    )
    return not any(marker in lowered for marker in failure_markers)


def apply_manifest_evidence(
    fields: list[dict[str, Any]],
    manifest: dict[str, Any],
    *,
    checked_at: str,
) -> list[dict[str, Any]]:
    updated = deepcopy(fields)
    by_key = {_field_key(field): field for field in updated}

    for field_key, manifest_key in MANIFEST_FIELD_KEYS.items():
        field = by_key.get(field_key)
        if field is None:
            continue
        value = manifest.get(manifest_key)
        if not _has_known_manifest_value(value):
            continue
        availability = field["availability"]
        availability["status"] = "measurable"
        availability["confidence"] = "medium"
        availability["evidence_probe"] = "manifest"
        availability["evidence_artifact"] = "manifest.yaml"
        availability["blocked_reason"] = {"category": None, "detail": None}
        availability["partial_reason"] = None
        availability["last_checked_at"] = checked_at
    return updated


def apply_probe_evidence(
    fields: list[dict[str, Any]],
    probes: list[dict[str, Any]],
    *,
    checked_at: str,
) -> list[dict[str, Any]]:
    updated = deepcopy(fields)
    by_key = {_field_key(field): field for field in updated}

    for probe in probes:
        for mapped_field in probe.get("maps_to_fields", []):
            field = by_key.get(mapped_field)
            if field is None:
                continue
            availability = field["availability"]
            availability["evidence_probe"] = probe["tool"]
            availability["evidence_artifact"] = probe.get("artifact_path")
            availability["last_checked_at"] = checked_at
            if probe.get("available") and probe.get("permission_status") in {"ok", "limited"}:
                availability["status"] = "measurable" if probe["permission_status"] == "ok" else "partial"
                availability["confidence"] = "medium"
                availability["blocked_reason"] = {"category": None, "detail": None}
                availability["partial_reason"] = None if probe["permission_status"] == "ok" else "tool reports limited permission"
            else:
                availability["status"] = "blocked"
                availability["confidence"] = "medium"
                availability["blocked_reason"] = deepcopy(
                    probe.get(
                        "blocked_reason",
                        {"category": "unknown", "detail": "probe failed without blocked_reason"},
                    )
                )
                availability["partial_reason"] = None
    return updated


def apply_microbench_evidence(
    fields: list[dict[str, Any]],
    microbench_results: list[dict[str, Any]],
    *,
    checked_at: str,
) -> list[dict[str, Any]]:
    updated = deepcopy(fields)
    by_key = {_field_key(field): field for field in updated}

    for result in microbench_results:
        status = result.get("status", "unknown")
        if status not in {"measurable", "partial", "blocked"}:
            continue
        for field_key in MICROBENCH_FIELD_KEYS.get(result.get("bench_name"), []):
            field = by_key.get(field_key)
            if field is None:
                continue
            availability = field["availability"]
            availability["status"] = status
            availability["confidence"] = "medium"
            availability["evidence_probe"] = result.get("bench_name")
            availability["evidence_artifact"] = result.get("artifact_path")
            availability["last_checked_at"] = checked_at
            if status == "blocked":
                availability["blocked_reason"] = deepcopy(
                    result.get("blocked_reason", {"category": "unknown", "detail": "microbench failed"})
                )
                availability["partial_reason"] = None
            else:
                availability["blocked_reason"] = {"category": None, "detail": None}
                availability["partial_reason"] = None if status == "measurable" else "microbench produced setup evidence only"
    return updated


def summarize_availability(fields: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for field in fields:
        profile = field["profile"]
        status = field["availability"]["status"]
        if status not in AVAILABILITY_STATUSES:
            status = "unknown"
        summary.setdefault(profile, {state: 0 for state in AVAILABILITY_STATUSES})
        summary[profile][status] += 1
    return summary
