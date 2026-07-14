import json
import hashlib
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.inference_contracts.run_deepseek_p6_1_unprofiled_baseline import (
    build_run_plan,
    calculate_request_metrics,
    execute_artifacts,
    finalize_artifacts,
    grade_evidence,
    prepare_artifacts,
)


def test_run_plan_has_one_warmup_nine_pilot_and_fifteen_matrix_batches():
    plan = build_run_plan()

    assert len(plan) == 25
    assert sum(batch["phase"] == "warmup" for batch in plan) == 1
    assert sum(batch["phase"] == "pilot" for batch in plan) == 9
    assert sum(batch["phase"] == "matrix" for batch in plan) == 15
    assert sum(len(batch["requests"]) for batch in plan) == 91
    assert sum(
        len(batch["requests"]) for batch in plan if batch["phase"] != "warmup"
    ) == 90
    assert {
        (batch["context_tokens"], batch["output_tokens"], batch["concurrency"])
        for batch in plan
        if batch["phase"] != "warmup"
    } == {
        (context, output, concurrency)
        for context in (4096, 65536, 131072)
        for output in (64, 256)
        for concurrency in (1, 4, 8)
    }
    assert all(
        len(batch["requests"]) == batch["concurrency"] for batch in plan
    )


def test_prepare_artifacts_freezes_unique_cold_prefix_token_id_bodies(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")

    manifest = prepare_artifacts(source_path, tmp_path / "run", "deepseek-test")

    records = manifest["records"]
    assert len(records) == 91
    assert len({record["request_body_sha256"] for record in records}) == 91
    assert all(record["common_prefix_upper_bound_tokens"] < 128 for record in records)
    assert all(record["context_tokens"] in {4096, 65536, 131072} for record in records)
    assert all(record["output_tokens"] in {64, 256} for record in records)
    assert manifest["pairwise_common_prefix_tokens_less_than"] == 128
    assert manifest["generated_text_retained"] is False
    assert manifest["token_ids_retained"] is False
    persisted = json.loads(
        (tmp_path / "run" / "request_body_manifest.json").read_text(encoding="utf-8")
    )
    assert persisted == manifest
    assert "prompt" not in persisted["records"][0]
    first_body = json.loads(
        (tmp_path / "run" / "bodies" / f"{records[0]['request_id']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(first_body["prompt"]) == records[0]["context_tokens"]
    assert first_body["min_tokens"] == first_body["max_tokens"]
    assert first_body["return_token_ids"] is True


def test_request_metrics_use_exact_token_arrival_timestamps():
    metrics = calculate_request_metrics(
        request_start_ns=0,
        token_arrival_ns=[1_000_000_000, 2_000_000_000, 4_000_000_000],
        request_end_ns=5_000_000_000,
    )

    assert metrics == {
        "ttft_ms": 1000.0,
        "tpot_ms": 1500.0,
        "e2el_ms": 5000.0,
        "output_tokens_per_second": 0.6,
        "itl_count": 2,
        "itl_p50_ms": 1500.0,
        "itl_p95_ms": 1950.0,
        "itl_p99_ms": 1990.0,
    }


def test_grading_requires_all_measured_requests_batches_and_clean_cleanup():
    plan = build_run_plan()
    requests = [
        {
            "phase": batch["phase"],
            "context_tokens": batch["context_tokens"],
            "output_tokens": batch["output_tokens"],
            "concurrency": batch["concurrency"],
            "status": "success",
        }
        for batch in plan
        for _ in batch["requests"]
    ]
    batches = [
        {
            "phase": batch["phase"],
            "status": "success",
            "counter_evidence_ok": True,
            "counter_continuity_ok": True,
            "accepted_token_delta": 1.0,
        }
        for batch in plan
    ]

    green = grade_evidence(requests, batches, cleanup_status="clean")
    assert green["server_grade"] == "candidate_green_mtp_unprofiled_baseline"
    assert green["all_18_cells_represented"] is True
    assert green["measured_request_count"] == 90
    assert green["measured_batch_count"] == 24
    assert green["performance_reference_baseline"] is False

    batches[-1]["counter_continuity_ok"] = False
    discontinuous = grade_evidence(requests, batches, cleanup_status="clean")
    assert discontinuous["server_grade"] == "red_mtp_unprofiled_evidence_incomplete"
    batches[-1]["counter_continuity_ok"] = True

    requests[-1]["status"] = "failed"
    partial = grade_evidence(requests, batches, cleanup_status="clean")
    assert partial["server_grade"] == "yellow_mtp_unprofiled_matrix_partial"
    assert partial["official_functional_reference_baseline_remains_true"] is True


def test_finalize_preserves_a_pre_request_protocol_gate_grade(tmp_path):
    (tmp_path / "server_grade.txt").write_text(
        "blocked_protocol_or_resource_gate\n", encoding="utf-8"
    )

    grading = finalize_artifacts(tmp_path, cleanup_status="clean", run_exit=2)

    assert grading["server_grade"] == "blocked_protocol_or_resource_gate"
    assert grading["cleanup_status"] == "clean"


def test_execute_artifacts_reads_streaming_token_ids_and_live_metrics(tmp_path):
    state = {"drafts": 0, "draft_tokens": 0, "accepted": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_GET(self):
            if self.path == "/health":
                body = b"ok"
            elif self.path == "/metrics":
                body = (
                    f"vllm:spec_decode_num_drafts_total {state['drafts']}\n"
                    f"vllm:spec_decode_num_draft_tokens_total {state['draft_tokens']}\n"
                    f"vllm:spec_decode_num_accepted_tokens_total {state['accepted']}\n"
                    "vllm:num_requests_running 0\n"
                    "vllm:num_requests_waiting 0\n"
                ).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            assert self.path == "/v1/completions"
            length = int(self.headers["Content-Length"])
            payload = json.loads(self.rfile.read(length))
            output = int(payload["max_tokens"])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for index in range(output):
                event = {
                    "choices": [
                        {
                            "token_ids": [100 + index],
                            "finish_reason": "length" if index == output - 1 else None,
                        }
                    ]
                }
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            usage = {
                "choices": [],
                "usage": {
                    "prompt_tokens": len(payload["prompt"]),
                    "completion_tokens": output,
                },
            }
            self.wfile.write(f"data: {json.dumps(usage)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            state["drafts"] += output
            state["draft_tokens"] += output
            state["accepted"] += output

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        artifact_dir = tmp_path / "run"
        (artifact_dir / "bodies").mkdir(parents=True)
        body = json.dumps(
            {
                "prompt": [1, 2, 3],
                "max_tokens": 3,
                "min_tokens": 3,
                "temperature": 0.0,
                "ignore_eos": True,
                "stream": True,
                "return_token_ids": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        body_path = artifact_dir / "bodies" / "q1.json"
        body_path.write_bytes(body)
        plan = [
            {
                "batch_id": "warmup_b01",
                "phase": "warmup",
                "context_tokens": 3,
                "output_tokens": 3,
                "concurrency": 1,
                "repeat_index": 1,
                "requests": [
                    {
                        "request_id": "q1",
                        "request_index": 1,
                        "body_relative_path": "bodies/q1.json",
                        "request_body_sha256": hashlib.sha256(body).hexdigest(),
                    }
                ],
            }
        ]
        (artifact_dir / "run_plan.json").write_text(json.dumps(plan), encoding="utf-8")

        assert execute_artifacts(
            artifact_dir,
            f"http://127.0.0.1:{server.server_port}",
            os.getpid(),
        ) == 2
        result = json.loads(
            (artifact_dir / "raw_request_results.jsonl").read_text().splitlines()[0]
        )
        batch = json.loads(
            (artifact_dir / "raw_batch_results.jsonl").read_text().splitlines()[0]
        )
        assert result["status"] == "success"
        assert result["streamed_token_count"] == 3
        assert result["max_token_chunk_width"] == 1
        assert len(result["token_arrival_ns"]) == 3
        assert result["generated_text_retained"] is False
        assert result["token_ids_retained"] is False
        assert batch["status"] == "success"
        assert batch["counter_evidence_ok"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
