from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tools.observability_profile.availability import apply_manifest_evidence, apply_microbench_evidence, apply_probe_evidence
from tools.observability_profile.catalog import build_field_catalog
from tools.observability_profile.join_keys import build_join_key_readiness
from tools.observability_profile.manifest import build_manifest
from tools.observability_profile.microbench import run_microbench_suite
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
    include_microbench: bool = False,
    scratch_dir: Path | None = None,
    copy_sizes: str = "4K,16K,64K,1M,16M,256M,1G",
    fio_qdepth: str = "1,4,16,32",
    microbench_duration: int = 10,
    directory_layout: str = "collect",
) -> Path:
    if directory_layout == "legacy":
        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        run_dir = output_base / f"{run_date}_{_safe_path_component(run_id)}_observability_run"
    else:
        run_dir = output_base / _safe_path_component(run_id)
    if run_dir.exists():
        raise FileExistsError(f"observability run directory already exists: {run_dir}")
    probe_dir = run_dir / "probe_results"
    probe_dir.mkdir(parents=True, exist_ok=False)

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

    microbench_results: list[dict[str, Any]] = []
    if include_microbench:
        microbench_results = run_microbench_suite(
            run_dir=run_dir,
            scratch_dir=scratch_dir,
            copy_sizes=copy_sizes,
            fio_qdepth=fio_qdepth,
            duration_s=microbench_duration,
        )

    checked_at = datetime.now(timezone.utc).isoformat()
    fields = apply_manifest_evidence(build_field_catalog(), manifest, checked_at=checked_at)
    fields = apply_probe_evidence(fields, probe_results, checked_at=checked_at)
    if microbench_results:
        fields = apply_microbench_evidence(fields, microbench_results, checked_at=checked_at)
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
        microbench_results=microbench_results,
        join_key_readiness=join_key_readiness,
        p0_acceptance_fields=p0_acceptance_fields,
    )
    (run_dir / "server_observability_profile.md").write_text(summary, encoding="utf-8")
    return run_dir


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-base",
        default="工作记录与进度笔记本/observability_profiles",
        help="Directory where the observability run directory will be created.",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--operator", default="codex")


def _build_legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an AK observability profile run.")
    _add_common_arguments(parser)
    return parser


def _build_collect_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect an AK observability profile run.")
    _add_common_arguments(parser)
    parser.add_argument(
        "--include-microbench",
        action="store_true",
        help="Run short, controlled microbench probes and write microbench artifacts.",
    )
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        default=None,
        help="Writable scratch directory required for SSD/fio write-class microbench.",
    )
    parser.add_argument(
        "--copy-sizes",
        default="4K,16K,64K,1M,16M,256M,1G",
        help="Comma-separated copy sizes for NPU copy microbench.",
    )
    parser.add_argument(
        "--fio-qdepth",
        default="1,4,16,32",
        help="Comma-separated fio queue depths for SSD microbench.",
    )
    parser.add_argument(
        "--microbench-duration",
        type=int,
        default=10,
        help="Short per-benchmark duration in seconds.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args_list = sys.argv[1:] if argv is None else list(argv)
    if args_list and args_list[0] == "collect":
        parser = _build_collect_parser()
        args = parser.parse_args(args_list[1:])
        directory_layout = "collect"
    else:
        parser = _build_legacy_parser()
        args = parser.parse_args(args_list)
        args.include_microbench = False
        args.scratch_dir = None
        args.copy_sizes = "4K,16K,64K,1M,16M,256M,1G"
        args.fio_qdepth = "1,4,16,32"
        args.microbench_duration = 10
        directory_layout = "legacy"
    run_dir = run_observability_profile(
        output_base=Path(args.output_base),
        run_id=args.run_id,
        server_id=args.server_id,
        operator=args.operator,
        include_microbench=args.include_microbench,
        scratch_dir=args.scratch_dir,
        copy_sizes=args.copy_sizes,
        fio_qdepth=args.fio_qdepth,
        microbench_duration=args.microbench_duration,
        directory_layout=directory_layout,
    )
    print(run_dir)


if __name__ == "__main__":
    main()
