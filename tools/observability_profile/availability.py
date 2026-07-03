from __future__ import annotations

from copy import deepcopy
from typing import Any

from tools.observability_profile.constants import AVAILABILITY_STATUSES


def _field_key(field: dict[str, Any]) -> str:
    return f"{field['profile']}.{field['name']}"


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
                availability["blocked_reason"] = probe.get(
                    "blocked_reason",
                    {"category": "unknown", "detail": "probe failed without blocked_reason"},
                )
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
