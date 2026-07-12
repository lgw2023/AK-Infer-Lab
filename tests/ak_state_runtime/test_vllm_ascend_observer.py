import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tools.ak_state_runtime.adapters.vllm_ascend import VllmAscendAdapter
from tools.ak_state_runtime.replay import replay, validate_replay_result
from tools.ak_state_runtime.vllm_ascend_observer import (
    ObservationError,
    collect_vllm_ascend_observations,
    parse_prefix_metrics,
)


BASELINE_CONTRACT = Path(
    "benchmarks/deepseek_v4_flash/p8/p8_baseline_contract.yaml"
)
MODEL_ID = "deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp"


class _ObservationHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    request_payload: dict[str, object] | None = None
    request_complete = False

    def do_GET(self) -> None:
        if self.path != "/metrics":
            self.send_error(404)
            return
        queries = 4096 if self.request_complete else 0
        body = (
            '# TYPE vllm:prefix_cache_queries counter\n'
            f'vllm:prefix_cache_queries_total{{engine="0"}} {queries}.0\n'
            '# TYPE vllm:prefix_cache_hits counter\n'
            'vllm:prefix_cache_hits_total{engine="0"} 0.0\n'
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/v1/completions":
            self.send_error(404)
            return
        length = int(self.headers["Content-Length"])
        type(self).request_payload = json.loads(self.rfile.read(length))
        chunks = [
            {
                "choices": [
                    {
                        "text": "x",
                        "token_ids": [1],
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "text": "y",
                        "token_ids": list(range(2, 65)),
                        "finish_reason": "length",
                    }
                ]
            },
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 4096,
                    "completion_tokens": 64,
                    "total_tokens": 4160,
                },
            },
        ]
        body = "".join(
            f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"
            for chunk in chunks
        ) + "data: [DONE]\n\n"
        encoded = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
        type(self).request_complete = True

    def log_message(self, format: str, *args) -> None:
        return


@pytest.fixture
def observation_server():
    _ObservationHandler.request_payload = None
    _ObservationHandler.request_complete = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ObservationHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _payload(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "model": "deepseek-v4-flash-w8a8-mtp",
                "prompt": list(range(4096)),
                "temperature": 0.0,
                "max_tokens": 64,
                "min_tokens": 64,
                "ignore_eos": True,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_parse_prefix_metrics_accepts_prometheus_counter_suffix_and_labels() -> None:
    metrics = parse_prefix_metrics(
        "\n".join(
            [
                'vllm:prefix_cache_queries_total{engine="0"} 4096',
                'vllm:prefix_cache_queries_total{engine="1"} 2048',
                'vllm:prefix_cache_hits_total{engine="0"} 1024',
                'vllm:prefix_cache_hits_total{engine="1"} 0',
            ]
        )
    )

    assert metrics == {"queries": 6144.0, "hits": 1024.0}


def test_collector_emits_bounded_events_for_the_real_observe_only_adapter(
    tmp_path: Path,
    observation_server: str,
) -> None:
    observations = tmp_path / "runtime_observations.jsonl"
    request_result = tmp_path / "request_result.json"
    metrics = tmp_path / "prefix_cache_metrics.json"
    transfer = tmp_path / "transfer_availability.json"

    result = collect_vllm_ascend_observations(
        endpoint=f"{observation_server}/v1/completions",
        metrics_url=f"{observation_server}/metrics",
        request_payload=_payload(tmp_path / "request_payload.json"),
        observations_output=observations,
        request_result_output=request_result,
        metrics_output=metrics,
        transfer_availability_output=transfer,
        timeout_seconds=2.0,
        metrics_settle_seconds=1.0,
    )

    assert result["status"] == "success"
    assert result["generated_token_count"] == 64
    assert result["streamed_token_count"] == 64
    assert result["generated_text_retained"] is False
    sent = _ObservationHandler.request_payload
    assert sent is not None
    assert sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}
    assert sent["return_token_ids"] is True

    source_records = [json.loads(line) for line in observations.read_text().splitlines()]
    assert [record["source_event_id"] for record in source_records] == [
        "request_start",
        "first_token",
        "request_end",
        "prefix_cache_counter_delta",
    ]
    assert all("payload" not in record for record in source_records)
    assert source_records[-1]["bytes"] is None
    assert source_records[-1]["timestamp_ns"] >= source_records[2]["timestamp_ns"]
    assert "query_delta=4096" in source_records[-1]["reason"]

    adapter = VllmAscendAdapter(
        baseline_contract=BASELINE_CONTRACT,
        model_id=MODEL_ID,
    )
    replay_result = replay(adapter.read(observations))
    assert validate_replay_result(replay_result) == ()
    assert len(replay_result.events) == 4
    assert len(replay_result.state_objects) == 1
    assert len(replay_result.placement_decisions) == 1
    assert replay_result.placement_decisions[0].executed is False
    assert replay_result.state_objects[0].payload_ref is None

    availability = json.loads(transfer.read_text())
    assert availability["status"] == "unavailable"
    assert availability["event_emitted"] is False


def test_collector_rejects_non_fixed_payload_and_writes_a_bounded_error(
    tmp_path: Path,
) -> None:
    payload = _payload(tmp_path / "request_payload.json")
    record = json.loads(payload.read_text())
    record["prompt"] = record["prompt"][:-1]
    payload.write_text(json.dumps(record), encoding="utf-8")
    request_result = tmp_path / "request_result.json"

    with pytest.raises(ObservationError, match="exactly 4096 token IDs"):
        collect_vllm_ascend_observations(
            endpoint="http://127.0.0.1:1/v1/completions",
            metrics_url="http://127.0.0.1:1/metrics",
            request_payload=payload,
            observations_output=tmp_path / "runtime_observations.jsonl",
            request_result_output=request_result,
            metrics_output=tmp_path / "prefix_cache_metrics.json",
            transfer_availability_output=tmp_path / "transfer_availability.json",
            timeout_seconds=0.1,
            metrics_settle_seconds=0.0,
        )

    error = json.loads(request_result.read_text())
    assert error["status"] == "error"
    assert error["generated_text_retained"] is False
    assert error["token_ids_retained"] is False
