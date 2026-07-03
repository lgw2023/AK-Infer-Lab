from __future__ import annotations

from typing import Any


def build_p0_acceptance_fields(fields: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    accepted = []
    for field in fields:
        status = field["availability"]["status"]
        if not field["required_for_p0"] or status not in {"measurable", "partial"}:
            continue
        accepted.append(
            {
                "field": f"{field['profile']}.{field['name']}",
                "status": status,
                "source": field["availability"].get("evidence_artifact") or field["expected_artifact"],
                "acceptance_rule": field["acceptance_rule"],
                "caveat": field["availability"].get("partial_reason"),
            }
        )
    return {"p0_acceptance_fields": accepted}
