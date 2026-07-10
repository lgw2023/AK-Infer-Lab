from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .adapters.p1_fixture import P1FixtureAdapter
from .bundle import write_bundle
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "build-offline-bundle":
        raise AssertionError(f"unsupported command: {args.command}")

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


if __name__ == "__main__":
    raise SystemExit(main())
