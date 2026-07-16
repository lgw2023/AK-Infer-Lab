from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.inference_contracts.prepare_deepseek_p8_1_observe_matrix import (
    prepare_matrix_bodies,
)


FROZEN_BODY_SHA256 = {
    "short_isolated_a": "7d59f274cf53019b221e5d4add7628551bed5a910255e267f52719dac41f2b21",
    "medium_shared_prime": "1ff2523c2cb5172f5ce0ba9ce5bde2a66c9ed3d20e73cb8715fbd36841f39496",
    "medium_shared_follower": "46363c923be52449e803488bec3f7691a620cd31248ac3b62304407d35485169",
    "long_isolated_a": "e5d848816122c3d9f1dba0e7149294017471fc4ebfabfe6a69402666b92f2857",
    "short_isolated_b": "c36dc099ab384fb8da5bff881473af45a75f918bf59104db5828a8302d2aecd5",
    "long_isolated_b": "820a663bf3335849673f508fde484a0a84c17ebc16b513b2be4be1e6508eeb88",
}


def build_body_relationship_summary(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ValueError("request body manifest records must be a list")
    actual = {
        str(record.get("slot_id")): str(record.get("request_body_sha256"))
        for record in records
    }
    if actual != FROZEN_BODY_SHA256:
        raise ValueError(
            f"frozen request body hash mismatch: actual={actual!r}"
        )
    shared_prefix = manifest.get("shared_prefix")
    expected_shared_prefix = {
        "prime_slot": "medium_shared_prime",
        "follower_slot": "medium_shared_follower",
        "token_lcp": 58880,
        "expected_prefix_hit_tokens": 49152,
    }
    if shared_prefix != expected_shared_prefix:
        raise ValueError(
            f"shared-prefix relationship mismatch: {shared_prefix!r}"
        )
    if manifest.get("all_other_pairwise_prefixes_less_than_tokens") != 128:
        raise ValueError("isolated-prefix bound must remain 128 tokens")
    if manifest.get("all_other_pairwise_prefixes_valid") is not True:
        raise ValueError("isolated-prefix relationships are not valid")

    sanitized_records = [
        {
            "order": int(record["order"]),
            "slot_id": str(record["slot_id"]),
            "input_tokens": int(record["input_tokens"]),
            "body_bytes": int(record["body_bytes"]),
            "request_body_sha256": str(record["request_body_sha256"]),
        }
        for record in records
    ]
    return {
        "schema_version": 1,
        "request_count": len(sanitized_records),
        "frozen_body_hashes_exact": True,
        "records": sanitized_records,
        "shared_prefix": expected_shared_prefix,
        "all_other_pairwise_prefixes_less_than_tokens": 128,
        "all_other_pairwise_prefixes_valid": True,
        "request_bodies_remain_server_local": True,
        "generated_text_or_token_ids_present": False,
        "claim_boundary": "sanitized_body_hash_size_and_lcp_relationships_only",
    }


def prepare_r1_matrix_bodies(
    source_payload: Path,
    output_dir: Path,
    model_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = prepare_matrix_bodies(source_payload, output_dir, model_name)
    summary = build_body_relationship_summary(manifest)
    (output_dir / "body_relationship_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare the frozen-body P8.1-R1 observation matrix"
    )
    parser.add_argument("--source-payload", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-name", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest, summary = prepare_r1_matrix_bodies(
        args.source_payload,
        args.output_dir,
        args.model_name,
    )
    print(
        json.dumps(
            {
                "output": args.output_dir.as_posix(),
                "request_count": manifest["request_count"],
                "frozen_body_hashes_exact": summary["frozen_body_hashes_exact"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
