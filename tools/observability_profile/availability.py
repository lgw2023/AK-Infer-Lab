from __future__ import annotations

from copy import deepcopy
from typing import Any

from tools.observability_profile.constants import AVAILABILITY_STATUSES


MANIFEST_FIELD_KEYS = {
    "server_observability_profile.os_name": "os_name",
    "server_observability_profile.kernel_version": "kernel_version",
    "server_observability_profile.cann_version": "cann_version",
    "server_observability_profile.driver_version": "driver_version",
    "server_observability_profile.torch_npu_version": "torch_npu_version",
    "server_observability_profile.mindie_version": "mindie_version",
    "server_observability_profile.vllm_ascend_version": "vllm_ascend_version",
    "server_observability_profile.container_privileged": "container_privileged",
    "server_observability_profile.visible_npu_count": "npu_count",
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
    failure_markers = ("filenotfounderror", "modulenotfounderror", "importerror", "traceback", "not found")
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
