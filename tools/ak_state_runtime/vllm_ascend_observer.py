from __future__ import annotations

import json
import math
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class ObservationError(ValueError):
    """Raised when the bounded runtime observation cannot be collected safely."""


_PREFIX_METRIC_RE = re.compile(
    r"^(vllm:prefix_cache_(queries|hits)(?:_total)?)"
    r"(?:\{[^}]*\})?\s+([-+0-9.eE]+)(?:\s+\d+)?$"
)


@dataclass(frozen=True)
class StreamingResult:
    http_status: int
    request_start_ns: int
    first_token_ns: int
    request_end_ns: int
    prompt_tokens: int
    generated_token_count: int
    streamed_token_count: int
    finish_reason: str


def parse_prefix_metrics(text: str) -> dict[str, float]:
    totals = {"queries": 0.0, "hits": 0.0}
    counts = {"queries": 0, "hits": 0}
    for line in text.splitlines():
        match = _PREFIX_METRIC_RE.match(line.strip())
        if match is None:
            continue
        metric_kind = match.group(2)
        value = float(match.group(3))
        if not math.isfinite(value):
            raise ObservationError(f"non-finite prefix metric: {line}")
        totals[metric_kind] += value
        counts[metric_kind] += 1
    missing = sorted(name for name, count in counts.items() if count == 0)
    if missing:
        raise ObservationError(
            f"missing prefix cache metric samples: {', '.join(missing)}"
        )
    return totals


def collect_vllm_ascend_observations(
    *,
    endpoint: str,
    metrics_url: str,
    request_payload: Path,
    observations_output: Path,
    request_result_output: Path,
    metrics_output: Path,
    transfer_availability_output: Path,
    timeout_seconds: float,
    metrics_settle_seconds: float,
    expected_prompt_tokens: int = 4096,
    trace_id: str = "trace_p8_vllm_ascend_0001",
    request_id: str = "req_p8_0001",
    session_id: str = "session_p8_0001",
) -> dict[str, Any]:
    outputs = (
        observations_output,
        request_result_output,
        metrics_output,
        transfer_availability_output,
    )
    if any(path.exists() for path in outputs):
        raise ObservationError("observation outputs must not already exist")
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if expected_prompt_tokens <= 0:
            raise ObservationError("expected prompt tokens must be positive")
        if not trace_id or not request_id or not session_id:
            raise ObservationError("trace, request and session IDs must be non-empty")
        payload = _load_request_payload(request_payload, expected_prompt_tokens)
        before = _read_prefix_metrics(metrics_url, timeout_seconds)
        result = _stream_completion(endpoint, payload, timeout_seconds)
        after = _wait_for_prefix_metrics(
            metrics_url,
            before,
            timeout_seconds=timeout_seconds,
            settle_seconds=metrics_settle_seconds,
        )
        prefix_observed_ns = time.monotonic_ns()
        deltas = {
            name: after[name] - before[name] for name in ("queries", "hits")
        }
        if deltas["queries"] <= 0:
            raise ObservationError("prefix cache query counter did not increase")
        _validate_streaming_result(result, expected_prompt_tokens)
        observations = _build_observations(
            result,
            deltas,
            prefix_observed_ns,
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
        )
        _write_jsonl(observations_output, observations)
        _write_json(
            metrics_output,
            {
                "evidence_source": "vllm_prometheus_metrics_before_after_request",
                "metrics_url": metrics_url,
                "before": before,
                "after": after,
                "delta": deltas,
                "observed_ns": prefix_observed_ns,
                "time_base": "host_monotonic_ns",
                "claim_boundary": "token_counters_only_not_object_bytes_or_performance",
            },
        )
        _write_json(
            transfer_availability_output,
            {
                "status": "unavailable",
                "event_emitted": False,
                "reason": (
                    "no_native_bounded_transfer_event_source_in_this_tracer_bullet;"
                    "synthetic_transfer_forbidden"
                ),
            },
        )
        request_record = {
            "status": "success",
            "http_status": result.http_status,
            "prompt_tokens": result.prompt_tokens,
            "generated_token_count": result.generated_token_count,
            "streamed_token_count": result.streamed_token_count,
            "finish_reason": result.finish_reason,
            "trace_id": trace_id,
            "request_id": request_id,
            "session_id": session_id,
            "request_start_ns": result.request_start_ns,
            "first_token_ns": result.first_token_ns,
            "request_end_ns": result.request_end_ns,
            "time_base": "host_monotonic_ns",
            "generated_text_retained": False,
            "token_ids_retained": False,
            "claim_boundary": "p8_observe_only_smoke_not_performance",
        }
        _write_json(request_result_output, request_record)
        return request_record
    except Exception as exc:
        if not request_result_output.exists():
            _write_json(
                request_result_output,
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "generated_text_retained": False,
                    "token_ids_retained": False,
                },
            )
        raise


def _load_request_payload(path: Path, expected_prompt_tokens: int) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservationError(f"cannot read request payload: {path}") from exc
    if not isinstance(payload, dict):
        raise ObservationError("request payload must be a JSON object")
    prompt = payload.get("prompt")
    if (
        not isinstance(prompt, list)
        or len(prompt) != expected_prompt_tokens
        or any(not isinstance(token, int) or isinstance(token, bool) for token in prompt)
    ):
        raise ObservationError(
            "request payload prompt must contain exactly "
            f"{expected_prompt_tokens} token IDs"
        )
    expected = {
        "max_tokens": 64,
        "min_tokens": 64,
        "ignore_eos": True,
        "temperature": 0.0,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ObservationError(f"request payload {field} must equal {value!r}")
    if not isinstance(payload.get("model"), str) or not payload["model"]:
        raise ObservationError("request payload model must be a non-empty string")

    streaming_payload = dict(payload)
    streaming_payload["stream"] = True
    streaming_payload["stream_options"] = {"include_usage": True}
    streaming_payload["return_token_ids"] = True
    return streaming_payload


def _read_prefix_metrics(url: str, timeout_seconds: float) -> dict[str, float]:
    request = urllib.request.Request(url, headers={"Accept": "text/plain"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        if response.status != 200:
            raise ObservationError(f"metrics HTTP status is {response.status}")
        text = response.read().decode("utf-8")
    return parse_prefix_metrics(text)


def _wait_for_prefix_metrics(
    url: str,
    before: Mapping[str, float],
    *,
    timeout_seconds: float,
    settle_seconds: float,
) -> dict[str, float]:
    deadline = time.monotonic() + max(0.0, settle_seconds)
    while True:
        after = _read_prefix_metrics(url, timeout_seconds)
        if after["queries"] > before["queries"]:
            return after
        if time.monotonic() >= deadline:
            return after
        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))


def _stream_completion(
    endpoint: str,
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> StreamingResult:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    request_start_ns = time.monotonic_ns()
    first_token_ns = 0
    request_end_ns = 0
    streamed_token_count = 0
    usage_completion_tokens: int | None = None
    usage_prompt_tokens: int | None = None
    finish_reason = ""
    saw_done = False

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        http_status = response.status
        if http_status != 200:
            raise ObservationError(f"completion HTTP status is {http_status}")
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                saw_done = True
                request_end_ns = time.monotonic_ns()
                break
            if not data:
                continue
            chunk = json.loads(data)
            if not isinstance(chunk, dict):
                raise ObservationError("stream chunk must be a JSON object")
            if chunk.get("error"):
                raise ObservationError(f"stream returned error: {chunk['error']}")
            for choice in chunk.get("choices") or []:
                token_ids = choice.get("token_ids") or []
                if token_ids:
                    if any(
                        not isinstance(token, int) or isinstance(token, bool)
                        for token in token_ids
                    ):
                        raise ObservationError("stream returned invalid token IDs")
                    if first_token_ns == 0:
                        first_token_ns = time.monotonic_ns()
                    streamed_token_count += len(token_ids)
                if choice.get("finish_reason") is not None:
                    finish_reason = str(choice["finish_reason"])
            usage = chunk.get("usage")
            if isinstance(usage, dict):
                usage_completion_tokens = _required_integer(
                    usage, "completion_tokens"
                )
                usage_prompt_tokens = _required_integer(usage, "prompt_tokens")

    if not saw_done:
        request_end_ns = time.monotonic_ns()
        raise ObservationError("stream ended without [DONE]")
    if usage_completion_tokens is None or usage_prompt_tokens is None:
        raise ObservationError("stream did not return final usage")
    return StreamingResult(
        http_status=http_status,
        request_start_ns=request_start_ns,
        first_token_ns=first_token_ns,
        request_end_ns=request_end_ns,
        prompt_tokens=usage_prompt_tokens,
        generated_token_count=usage_completion_tokens,
        streamed_token_count=streamed_token_count,
        finish_reason=finish_reason,
    )


def _required_integer(record: Mapping[str, Any], field: str) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ObservationError(f"stream usage {field} must be an integer")
    return value


def _validate_streaming_result(
    result: StreamingResult,
    expected_prompt_tokens: int,
) -> None:
    if result.first_token_ns <= result.request_start_ns:
        raise ObservationError("first token timestamp is missing or invalid")
    if result.request_end_ns < result.first_token_ns:
        raise ObservationError("request end precedes first token")
    if result.prompt_tokens != expected_prompt_tokens:
        raise ObservationError(
            f"prompt token count is {result.prompt_tokens}, "
            f"expected {expected_prompt_tokens}"
        )
    if result.generated_token_count != 64:
        raise ObservationError(
            f"generated token count is {result.generated_token_count}, expected 64"
        )
    if result.streamed_token_count != 64:
        raise ObservationError(
            f"streamed token count is {result.streamed_token_count}, expected 64"
        )
    if result.finish_reason != "length":
        raise ObservationError(
            f"finish reason is {result.finish_reason!r}, expected 'length'"
        )


def _build_observations(
    result: StreamingResult,
    prefix_deltas: Mapping[str, float],
    prefix_observed_ns: int,
    *,
    trace_id: str,
    request_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    source_prefix = "" if request_id == "req_p8_0001" else f"{request_id}:"
    common = {
        "schema_version": "0.1.0",
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "rank_id": None,
    }
    observations = [
        {
            **common,
            "source_event_id": f"{source_prefix}request_start",
            "timestamp_ns": result.request_start_ns,
            "phase": "enqueue",
            "event_type": "request_stage",
            "action": "request_start",
            "object_id": None,
            "object_type": None,
            "source_tier": None,
            "target_tier": None,
            "bytes": None,
            "latency_ms": None,
            "evidence_source": "runtime_event",
            "reason": "host_monotonic_ns;bounded_streaming_client_event",
        },
        {
            **common,
            "source_event_id": f"{source_prefix}first_token",
            "timestamp_ns": result.first_token_ns,
            "phase": "decode",
            "event_type": "request_stage",
            "action": "first_token",
            "object_id": None,
            "object_type": None,
            "source_tier": None,
            "target_tier": None,
            "bytes": None,
            "latency_ms": (result.first_token_ns - result.request_start_ns) / 1e6,
            "evidence_source": "runtime_event",
            "reason": "host_monotonic_ns;first_nonempty_stream_token_ids",
        },
        {
            **common,
            "source_event_id": f"{source_prefix}request_end",
            "timestamp_ns": result.request_end_ns,
            "phase": "decode",
            "event_type": "request_stage",
            "action": "request_end",
            "object_id": None,
            "object_type": None,
            "source_tier": None,
            "target_tier": None,
            "bytes": None,
            "latency_ms": (result.request_end_ns - result.request_start_ns) / 1e6,
            "evidence_source": "runtime_event",
            "reason": "host_monotonic_ns;sse_done_received",
        },
        {
            **common,
            "source_event_id": f"{source_prefix}prefix_cache_counter_delta",
            "timestamp_ns": prefix_observed_ns,
            "phase": "prefill",
            "event_type": "state_lifecycle",
            "action": "prefix_cache_counter_delta",
            "object_id": f"prefix_proxy:{request_id}",
            "object_type": "prefix_block",
            "source_tier": None,
            "target_tier": None,
            "bytes": None,
            "latency_ms": None,
            "evidence_source": "server_stats",
            "reason": (
                "token_counter_proxy_only;"
                f"query_delta={prefix_deltas['queries']:g};"
                f"hit_delta={prefix_deltas['hits']:g};"
                "object_bytes_unavailable_in_server_stats"
            ),
        },
    ]
    return observations


def _write_json(path: Path, record: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
