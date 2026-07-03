from __future__ import annotations

from typing import Any

from tools.observability_profile.availability import summarize_availability


def render_server_observability_profile(
    *,
    manifest: dict[str, Any],
    fields: list[dict[str, Any]],
    probes: list[dict[str, Any]],
    microbench_results: list[dict[str, Any]],
    join_key_readiness: dict[str, Any],
    p0_acceptance_fields: dict[str, Any],
) -> str:
    summary = summarize_availability(fields)
    lines = [
        "# Server Observability Profile",
        "",
        "## 1. Run Summary",
        "",
        f"- profile_run_id: `{manifest['profile_run_id']}`",
        f"- server_id: `{manifest['server_id']}`",
        f"- schema_version: `{manifest['schema_version']}`",
        f"- hardware_topology_hash: `{manifest['hardware_topology_hash']}`",
        f"- software_stack_hash: `{manifest['software_stack_hash']}`",
        f"- probe_script_version: `{manifest['probe_script_version']}`",
        "",
        "## 2. Server And Tool Readiness",
        "",
    ]
    for probe in probes:
        lines.append(
            f"- `{probe['tool']}`: available={probe['available']} "
            f"permission={probe['permission_status']} exit_code={probe['exit_code']}"
        )

    if microbench_results:
        lines.extend(["", "## 2.1 Microbench Results", ""])
        for result in microbench_results:
            blocked_reason = result.get("blocked_reason") or {}
            category = blocked_reason.get("category") or "none"
            lines.append(
                f"- `{result['bench_name']}`: status={result['status']} "
                f"artifact=`{result['artifact_path']}` blocked={category}"
            )

    lines.extend(["", "## 3. Profile-Level Observability", ""])
    for profile, counts in sorted(summary.items()):
        lines.append(
            f"- `{profile}`: measurable={counts['measurable']} "
            f"partial={counts['partial']} blocked={counts['blocked']} "
            f"unknown={counts['unknown']} not_applicable={counts['not_applicable']}"
        )

    lines.extend(["", "## 4. P0 Acceptance Fields", ""])
    for field in p0_acceptance_fields["p0_acceptance_fields"]:
        lines.append(f"- `{field['field']}`: {field['status']} from `{field['source']}`")

    lines.extend(["", "## 5. Join-Key And Time-Alignment Readiness", ""])
    for item in join_key_readiness["join_key_readiness"]:
        lines.append(
            f"- `{item['profile_pair']}`: {item['status']}; "
            f"time_alignment={item['time_alignment']['status']}"
        )

    lines.extend(["", "## 6. Gap Summary", ""])
    gaps: dict[str, int] = {}
    for field in fields:
        availability = field["availability"]
        if availability["status"] not in {"blocked", "unknown"}:
            continue
        category = availability.get("blocked_reason", {}).get("category") or "unknown"
        gaps[category] = gaps.get(category, 0) + 1
    for category, count in sorted(gaps.items()):
        lines.append(f"- `{category}`: {count}")

    lines.extend(["", "## 7. Recommended Next Actions", ""])
    lines.append(
        "- Use `field_availability.yaml` and `join_key_readiness.yaml` to choose the first P0 probe fixes."
    )
    lines.append(
        "- Do not treat SSD cold tier, runtime hooks, or MoE expert hooks as P0 performance optimization work."
    )
    lines.append("")
    return "\n".join(lines)
