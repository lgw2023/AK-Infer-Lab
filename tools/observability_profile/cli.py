from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tools.observability_profile.availability import apply_manifest_evidence, apply_probe_evidence
from tools.observability_profile.catalog import build_field_catalog
from tools.observability_profile.join_keys import build_join_key_readiness
from tools.observability_profile.manifest import build_manifest
from tools.observability_profile.p0_acceptance import build_p0_acceptance_fields
from tools.observability_profile.probes import run_standard_probes
from tools.observability_profile.render import render_server_observability_profile


def _write_yaml(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_probe_result(path: Path, probe: dict[str, Any]) -> None:
    content = [
        f"# {probe['tool']}",
        "",
        "```yaml",
        yaml.safe_dump(probe, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
    ]
    path.write_text("\n".join(content), encoding="utf-8")


def _safe_path_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return safe or "run"


def run_observability_profile(
    *,
    output_base: Path,
    run_id: str,
    server_id: str,
    operator: str,
    probes: list[dict[str, Any]] | None = None,
) -> Path:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_dir = output_base / f"{run_date}_{_safe_path_component(run_id)}_observability_run"
    probe_dir = run_dir / "probe_results"
    probe_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        run_id=run_id,
        output_root=run_dir,
        server_id=server_id,
        operator=operator,
    )
    probe_results = [dict(probe) for probe in probes] if probes is not None else run_standard_probes()
    for probe in probe_results:
        probe_path = probe_dir / f"{probe['tool']}.md"
        probe["artifact_path"] = str(probe_path.relative_to(run_dir))
        _write_probe_result(probe_path, probe)

    checked_at = datetime.now(timezone.utc).isoformat()
    fields = apply_manifest_evidence(build_field_catalog(), manifest, checked_at=checked_at)
    fields = apply_probe_evidence(fields, probe_results, checked_at=checked_at)
    join_key_readiness = build_join_key_readiness()
    p0_acceptance_fields = build_p0_acceptance_fields(fields)

    _write_yaml(run_dir / "manifest.yaml", manifest)
    _write_yaml(run_dir / "field_availability.yaml", {"fields": fields})
    _write_yaml(run_dir / "join_key_readiness.yaml", join_key_readiness)
    _write_yaml(run_dir / "p0_acceptance_fields.yaml", p0_acceptance_fields)
    summary = render_server_observability_profile(
        manifest=manifest,
        fields=fields,
        probes=probe_results,
        join_key_readiness=join_key_readiness,
        p0_acceptance_fields=p0_acceptance_fields,
    )
    (run_dir / "server_observability_profile.md").write_text(summary, encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an AK observability profile run.")
    parser.add_argument(
        "--output-base",
        default="工作记录与进度笔记本/observability_profiles",
        help="Directory where the observability run directory will be created.",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--operator", default="codex")
    args = parser.parse_args()
    run_dir = run_observability_profile(
        output_base=Path(args.output_base),
        run_id=args.run_id,
        server_id=args.server_id,
        operator=args.operator,
    )
    print(run_dir)


if __name__ == "__main__":
    main()
