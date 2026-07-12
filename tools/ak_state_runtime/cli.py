from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import yaml

from .adapters.p1_fixture import P1FixtureAdapter
from .adapters.vllm_ascend import VllmAscendAdapter
from .bundle import write_bundle
from .capabilities.models import parse_probe_spec
from .capabilities.report import write_source_probe_outputs
from .capabilities.source import probe_source_capabilities
from .replay import replay, validate_replay_result
from .validation import load_contracts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="P8 state-runtime offline tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser(
        "build-offline-bundle",
        help="normalize the legacy P1 fixture into a deterministic P8 bundle",
    )
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--model-id", required=True)
    build.add_argument(
        "--runtime-label",
        choices=load_contracts()["state_event"]["enums"]["runtime"],
        required=True,
    )
    probe = subparsers.add_parser(
        "probe-source-capabilities",
        help="inspect exact target-tag Git blobs and emit bounded capability evidence",
    )
    probe.add_argument("--spec", type=Path, required=True)
    probe.add_argument("--repo-root", type=Path, required=True)
    probe.add_argument("--matrix-output", type=Path, required=True)
    probe.add_argument("--report-output", type=Path, required=True)
    runtime_bundle = subparsers.add_parser(
        "build-vllm-ascend-observe-bundle",
        help="normalize bounded server observations into an observe-only P8 bundle",
    )
    runtime_bundle.add_argument("--source", type=Path, required=True)
    runtime_bundle.add_argument("--output", type=Path, required=True)
    runtime_bundle.add_argument("--baseline-contract", type=Path, required=True)
    runtime_bundle.add_argument("--model-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build-offline-bundle":
        adapted = P1FixtureAdapter(
            model_id=args.model_id,
            runtime_label=args.runtime_label,
        ).read(args.source)
        result = replay(adapted)
        errors = validate_replay_result(result)
        write_bundle(result, args.output, source_artifact=args.source)
        print(
            json.dumps(
                {
                    "output": args.output.as_posix(),
                    "placement_decision_count": len(result.placement_decisions),
                    "state_object_count": len(result.state_objects),
                    "trace_validation_errors": len(errors),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "probe-source-capabilities":
        record = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
        spec = parse_probe_spec(record)
        result = probe_source_capabilities(spec, args.repo_root)
        write_source_probe_outputs(
            result,
            args.matrix_output,
            args.report_output,
        )
        print(
            json.dumps(
                {
                    "capability_count": len(result.capabilities),
                    "claim_ceiling": result.claim_ceiling,
                    "matrix_output": args.matrix_output.as_posix(),
                    "report_output": args.report_output.as_posix(),
                    "selected_workload_validated": (
                        result.selected_workload_validated
                    ),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "build-vllm-ascend-observe-bundle":
        adapted = VllmAscendAdapter(
            baseline_contract=args.baseline_contract,
            model_id=args.model_id,
        ).read(args.source)
        result = replay(adapted)
        errors = validate_replay_result(result)
        write_bundle(
            result,
            args.output,
            source_artifact=args.source,
            claim_level="selected_workload_observe_only_candidate",
            provenance_mode="bounded_server_observation",
            server_validated=False,
            slice_id="p8_vllm_ascend_observe_only_tracer_bullet",
        )
        print(
            json.dumps(
                {
                    "output": args.output.as_posix(),
                    "placement_decision_count": len(result.placement_decisions),
                    "state_object_count": len(result.state_objects),
                    "trace_validation_errors": len(errors),
                },
                sort_keys=True,
            )
        )
        return 0

    raise AssertionError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
