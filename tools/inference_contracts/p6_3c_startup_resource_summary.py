from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


PATTERNS = {
    "available_kv_cache_gib": re.compile(
        r"available KV cache memory(?::\s*|\s*\()([0-9.]+)\s*GiB",
        re.IGNORECASE,
    ),
    "required_kv_cache_gib": re.compile(
        r"([0-9.]+)\s*GiB KV cache is needed"
    ),
    "estimated_max_model_len": re.compile(
        r"estimated maximum model length is\s*([0-9,]+)"
    ),
    "gpu_kv_cache_tokens": re.compile(
        r"GPU KV cache size:\s*([0-9,]+)\s*tokens"
    ),
    "model_weight_gb": re.compile(
        r"Loading model weights took\s*([0-9.]+)\s*GB"
    ),
    "maximum_concurrency": re.compile(
        r"Maximum concurrency for\s*[0-9,]+\s*tokens per request:\s*"
        r"([0-9.]+)x"
    ),
}
FAILURE_MARKERS = (
    "To serve at least one request with the model's max seq len",
    "KV cache is needed",
    "estimated maximum model length",
    "Engine core initialization failed",
)


def _last_number(text: str, pattern: re.Pattern[str], cast: type) -> Any | None:
    matches = pattern.findall(text)
    if not matches:
        return None
    value = matches[-1].replace(",", "")
    return cast(value)


def summarize_startup_log(
    text: str,
    *,
    expected_max_model_len: int,
    expected_max_num_batched_tokens: int,
    expected_max_num_seqs: int,
    server_ready_exit_code: int,
) -> dict[str, Any]:
    summary = {
        "expected_max_model_len": expected_max_model_len,
        "expected_max_num_batched_tokens": expected_max_num_batched_tokens,
        "expected_max_num_seqs": expected_max_num_seqs,
        "server_ready": server_ready_exit_code == 0,
        "server_ready_exit_code": server_ready_exit_code,
        "available_kv_cache_gib": _last_number(
            text, PATTERNS["available_kv_cache_gib"], float
        ),
        "required_kv_cache_gib": _last_number(
            text, PATTERNS["required_kv_cache_gib"], float
        ),
        "estimated_max_model_len": _last_number(
            text, PATTERNS["estimated_max_model_len"], int
        ),
        "gpu_kv_cache_tokens": _last_number(
            text, PATTERNS["gpu_kv_cache_tokens"], int
        ),
        "model_weight_gb_max_observed": None,
        "maximum_concurrency": _last_number(
            text, PATTERNS["maximum_concurrency"], float
        ),
        "startup_failure_class": "none",
    }
    weight_matches = [
        float(value) for value in PATTERNS["model_weight_gb"].findall(text)
    ]
    if weight_matches:
        summary["model_weight_gb_max_observed"] = max(weight_matches)
    if server_ready_exit_code != 0:
        if (
            summary["required_kv_cache_gib"] is not None
            and summary["available_kv_cache_gib"] is not None
            and summary["required_kv_cache_gib"]
            > summary["available_kv_cache_gib"]
        ):
            summary["startup_failure_class"] = "insufficient_kv_cache_capacity"
        else:
            summary["startup_failure_class"] = "server_not_ready_other"
    return summary


def bounded_failure_excerpt(text: str, max_bytes: int = 8192) -> bytes:
    lines = text.splitlines()
    selected = [
        line
        for line in lines
        if any(marker in line for marker in FAILURE_MARKERS)
    ]
    if not selected:
        selected = lines[-40:]
    payload = ("\n".join(selected) + "\n").encode("utf-8", errors="replace")
    if len(payload) <= max_bytes:
        return payload
    return payload[-max_bytes:]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--failure-excerpt", type=Path, required=True)
    parser.add_argument("--expected-max-model-len", type=int, required=True)
    parser.add_argument("--expected-max-num-batched-tokens", type=int, required=True)
    parser.add_argument("--expected-max-num-seqs", type=int, required=True)
    parser.add_argument("--server-ready-exit-code", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = args.log.read_text(encoding="utf-8", errors="replace")
    summary = summarize_startup_log(
        text,
        expected_max_model_len=args.expected_max_model_len,
        expected_max_num_batched_tokens=args.expected_max_num_batched_tokens,
        expected_max_num_seqs=args.expected_max_num_seqs,
        server_ready_exit_code=args.server_ready_exit_code,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if args.server_ready_exit_code == 0:
        args.failure_excerpt.write_text("none\n", encoding="utf-8")
    else:
        args.failure_excerpt.write_bytes(bounded_failure_excerpt(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
