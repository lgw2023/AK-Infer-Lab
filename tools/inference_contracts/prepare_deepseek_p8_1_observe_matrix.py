from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence


SLOTS = (
    ("short_isolated_a", "req_p8_short_isolated_a", 4096, "isolated_anchor", 0),
    (
        "medium_shared_prime",
        "req_p8_medium_shared_prime",
        65536,
        "shared_prefix_prime",
        0,
    ),
    (
        "medium_shared_follower",
        "req_p8_medium_shared_follower",
        65536,
        "shared_prefix_follower",
        49152,
    ),
    ("long_isolated_a", "req_p8_long_isolated_a", 131072, "isolated_anchor", 0),
    ("short_isolated_b", "req_p8_short_isolated_b", 4096, "isolated_repeat", 0),
    ("long_isolated_b", "req_p8_long_isolated_b", 131072, "isolated_repeat", 0),
)
SHARED_PREFIX_TOKENS = 58880


def _common_prefix_length(left: list[int], right: list[int]) -> int:
    for index, (left_token, right_token) in enumerate(zip(left, right)):
        if left_token != right_token:
            return index
    return min(len(left), len(right))


def _repeat_and_truncate(tokens: list[int], size: int, offset: int) -> list[int]:
    rotated = tokens[offset:] + tokens[:offset]
    repeats = math.ceil(size / len(rotated))
    return (rotated * repeats)[:size]


def _select_offsets(source_tokens: list[int], count: int) -> list[int]:
    prefixes: list[list[int]] = []
    offsets: list[int] = []
    for offset in range(len(source_tokens)):
        prefix = _repeat_and_truncate(source_tokens, 128, offset)
        if any(_common_prefix_length(prefix, prior) >= 128 for prior in prefixes):
            continue
        prefixes.append(prefix)
        offsets.append(offset)
        if len(offsets) == count:
            return offsets
    raise ValueError(f"source payload provides only {len(offsets)} distinct prefix rotations")


def prepare_matrix_bodies(
    source_payload: Path,
    output_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    source = json.loads(source_payload.read_text(encoding="utf-8"))
    source_tokens = source.get("prompt")
    if not isinstance(source_tokens, list) or len(source_tokens) != 4096:
        raise ValueError("source payload must contain exactly 4096 prompt token IDs")
    if not all(
        isinstance(token, int) and not isinstance(token, bool) for token in source_tokens
    ):
        raise ValueError("source prompt must contain integer token IDs")
    if not model_name:
        raise ValueError("model name must be non-empty")
    if output_dir.exists():
        raise ValueError(f"matrix output directory already exists: {output_dir}")

    body_dir = output_dir / "bodies"
    body_dir.mkdir(parents=True)
    offsets = _select_offsets(source_tokens, 5)
    base_offsets = {
        "short_isolated_a": offsets[0],
        "medium_shared_prime": offsets[1],
        "long_isolated_a": offsets[2],
        "short_isolated_b": offsets[3],
        "long_isolated_b": offsets[4],
    }
    prompts = {
        slot_id: _repeat_and_truncate(source_tokens, input_tokens, base_offsets[slot_id])
        for slot_id, _, input_tokens, _, _ in SLOTS
        if slot_id != "medium_shared_follower"
    }
    prime = prompts["medium_shared_prime"]
    prime_next_token = prime[SHARED_PREFIX_TOKENS]
    tail_offset = next(
        (
            offset
            for offset, token in enumerate(source_tokens)
            if token != prime_next_token
        ),
        None,
    )
    if tail_offset is None:
        raise ValueError("source payload cannot produce a divergent shared-prefix tail")
    follower_tail = _repeat_and_truncate(
        source_tokens,
        65536 - SHARED_PREFIX_TOKENS,
        tail_offset,
    )
    prompts["medium_shared_follower"] = (
        prime[:SHARED_PREFIX_TOKENS] + follower_tail
    )
    actual_shared_lcp = _common_prefix_length(
        prime,
        prompts["medium_shared_follower"],
    )
    if actual_shared_lcp != SHARED_PREFIX_TOKENS:
        raise ValueError(
            f"shared-prefix LCP is {actual_shared_lcp}, expected {SHARED_PREFIX_TOKENS}"
        )

    pairwise: list[dict[str, Any]] = []
    all_other_pairwise_valid = True
    slot_ids = [slot[0] for slot in SLOTS]
    for index, left_id in enumerate(slot_ids):
        for right_id in slot_ids[index + 1 :]:
            lcp = _common_prefix_length(prompts[left_id], prompts[right_id])
            shared_pair = {left_id, right_id} == {
                "medium_shared_prime",
                "medium_shared_follower",
            }
            valid = lcp == SHARED_PREFIX_TOKENS if shared_pair else lcp < 128
            pairwise.append(
                {
                    "left_slot": left_id,
                    "right_slot": right_id,
                    "token_lcp": lcp,
                    "expected_shared_pair": shared_pair,
                    "valid": valid,
                }
            )
            if not shared_pair and not valid:
                all_other_pairwise_valid = False
    if not all_other_pairwise_valid:
        raise ValueError("an isolated request body shares at least 128 prefix tokens")

    records: list[dict[str, Any]] = []
    for order, (slot_id, request_id, input_tokens, role, expected_hits) in enumerate(
        SLOTS, 1
    ):
        body = {
            "ignore_eos": True,
            "max_tokens": 64,
            "min_tokens": 64,
            "model": model_name,
            "prompt": prompts[slot_id],
            "return_token_ids": True,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": 0.0,
        }
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        relative_path = Path("bodies") / f"{slot_id}.json"
        (output_dir / relative_path).write_bytes(raw)
        records.append(
            {
                "order": order,
                "slot_id": slot_id,
                "request_id": request_id,
                "input_tokens": input_tokens,
                "output_tokens": 64,
                "role": role,
                "expected_prefix_hit_tokens": expected_hits,
                "body_relative_path": relative_path.as_posix(),
                "body_bytes": len(raw),
                "request_body_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )

    manifest = {
        "schema_version": 1,
        "source_prompt_tokens": len(source_tokens),
        "request_count": len(records),
        "all_request_body_sha256_unique": len(
            {record["request_body_sha256"] for record in records}
        )
        == len(records),
        "shared_prefix": {
            "prime_slot": "medium_shared_prime",
            "follower_slot": "medium_shared_follower",
            "token_lcp": SHARED_PREFIX_TOKENS,
            "expected_prefix_hit_tokens": 49152,
        },
        "all_other_pairwise_prefixes_less_than_tokens": 128,
        "all_other_pairwise_prefixes_valid": all_other_pairwise_valid,
        "pairwise_prefixes": pairwise,
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
        "request_bodies_remain_server_local": True,
        "records": records,
    }
    if not manifest["all_request_body_sha256_unique"]:
        raise ValueError("request body hashes are not unique")
    (output_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare the bounded P8.1 matrix")
    parser.add_argument("--source-payload", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-name", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = prepare_matrix_bodies(
        args.source_payload,
        args.output_dir,
        args.model_name,
    )
    print(
        json.dumps(
            {
                "output": args.output_dir.as_posix(),
                "request_count": manifest["request_count"],
                "shared_prefix_token_lcp": manifest["shared_prefix"]["token_lcp"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
