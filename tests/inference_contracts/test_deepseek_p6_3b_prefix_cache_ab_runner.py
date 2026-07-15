import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    build_run_plan,
    execute_mode,
    finalize_artifacts,
    grade_evidence,
    parse_metrics,
    prepare_artifacts,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_prefix_cache_plan_freezes_eight_prime_then_reuse_groups(tmp_path):
    plan = build_run_plan()

    assert len(plan) == 32
    assert sum(item["request_role"] == "prime" for item in plan) == 8
    assert sum(item["request_role"] == "measured" for item in plan) == 24
    assert {
        (item["context_tokens"], item["target_shared_prefix_ratio_pct"])
        for item in plan
    } == {
        (context, ratio)
        for context in (4096, 32768, 65536, 131072)
        for ratio in (50, 90)
    }
    for group_id in {item["group_id"] for item in plan}:
        rows = [item for item in plan if item["group_id"] == group_id]
        assert [item["request_role"] for item in rows] == [
            "prime",
            "measured",
            "measured",
            "measured",
        ]

    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    manifest = prepare_artifacts(source, tmp_path / "run", "deepseek-test")

    assert manifest["request_count"] == 32
    assert manifest["group_count"] == 8
    assert manifest["modes_reuse_identical_body_bytes"] is True
    assert manifest["generated_text_retained"] is False
    assert manifest["token_ids_retained"] is False
    assert all(
        row["actual_shared_prefix_tokens"] >= row["target_shared_prefix_tokens"]
        for row in manifest["records"]
        if row["request_role"] == "measured"
    )
    assert all(
        row["actual_shared_prefix_tokens"]
        < row["target_shared_prefix_tokens"] + 128
        for row in manifest["records"]
        if row["request_role"] == "measured"
    )


def test_prefix_cache_grading_requires_on_hits_off_inactivity_and_mtp_activity():
    metrics = parse_metrics(
        b"\n".join(
            [
                b'vllm:num_requests_running{engine="0"} 0',
                b'vllm:num_requests_waiting{engine="0"} 0',
                b'vllm:prefix_cache_queries_total{engine="0"} 4096',
                b'vllm:prefix_cache_hits_total{engine="0"} 2048',
                b'vllm:spec_decode_num_drafts_total{engine="0"} 64',
                b'vllm:spec_decode_num_draft_tokens_total{engine="0"} 64',
                b'vllm:spec_decode_num_accepted_tokens_total{engine="0"} 32',
            ]
        )
    )
    assert metrics["prefix_queries"] == 4096
    assert metrics["prefix_hits"] == 2048
    assert metrics["prefix_metrics_present"] is True
    assert metrics["spec_metrics_present"] is True
    assert metrics["queue_metrics_present"] is True

    rows = []
    for mode in ("prefix_cache_off", "prefix_cache_on"):
        for item in build_run_plan():
            measured = item["request_role"] == "measured"
            rows.append(
                {
                    **item,
                    "mode": mode,
                    "request_body_sha256": item["request_id"],
                    "status": "success",
                    "queue_metrics_ok": True,
                    "counter_continuity_ok": True,
                    "spec_activity_ok": True,
                    "prefix_evidence_ok": True,
                    "prefix_queries_delta": 100.0 if mode == "prefix_cache_on" else 0.0,
                    "prefix_hits_delta": (
                        50.0 if mode == "prefix_cache_on" and measured else 0.0
                    ),
                    "accepted_token_delta": 32.0,
                }
            )

    green = grade_evidence(
        rows,
        cleanup_by_mode={"prefix_cache_off": "clean", "prefix_cache_on": "clean"},
    )
    assert green["server_grade"] == "candidate_green_p6_3b_prefix_cache_matched_ab"
    assert green["prime_request_count"] == 16
    assert green["measured_request_count"] == 48
    assert green["all_eight_groups_matched"] is True
    assert green["body_pairing_ok"] is True
    assert green["prefix_cache_on_positive_hit_measured_count"] == 24
    assert green["prefix_cache_off_hit_delta_total"] == 0
    assert green["mtp_accepted_token_delta_by_mode"] == {
        "prefix_cache_off": 1024.0,
        "prefix_cache_on": 1024.0,
    }

    next(
        row
        for row in rows
        if row["mode"] == "prefix_cache_on" and row["request_role"] == "measured"
    )["prefix_hits_delta"] = 0.0
    incomplete = grade_evidence(
        rows,
        cleanup_by_mode={"prefix_cache_off": "clean", "prefix_cache_on": "clean"},
    )
    assert incomplete["server_grade"] == "red_p6_3b_prefix_cache_evidence_incomplete"


def test_execute_mode_observes_positive_prefix_hits_only_on_reuse_requests(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    artifact_dir = tmp_path / "run"
    prepare_artifacts(source, artifact_dir, "deepseek-test")
    state = {
        "request_count": 0,
        "queries": 0,
        "hits": 0,
        "drafts": 0,
        "draft_tokens": 0,
        "accepted": 0,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_GET(self):
            if self.path == "/health":
                body = b"ok"
            elif self.path == "/metrics":
                body = (
                    "\n".join(
                        [
                            "vllm:num_requests_running 0",
                            "vllm:num_requests_waiting 0",
                            f"vllm:prefix_cache_queries_total {state['queries']}",
                            f"vllm:prefix_cache_hits_total {state['hits']}",
                            f"vllm:spec_decode_num_drafts_total {state['drafts']}",
                            f"vllm:spec_decode_num_draft_tokens_total {state['draft_tokens']}",
                            f"vllm:spec_decode_num_accepted_tokens_total {state['accepted']}",
                        ]
                    )
                    + "\n"
                ).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers["Content-Length"])
            payload = json.loads(self.rfile.read(length))
            output = int(payload["max_tokens"])
            state["request_count"] += 1
            state["queries"] += len(payload["prompt"])
            if state["request_count"] % 4 != 1:
                state["hits"] += len(payload["prompt"]) // 2
            state["drafts"] += output
            state["draft_tokens"] += output
            state["accepted"] += output
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for index in range(output):
                event = {
                    "choices": [
                        {
                            "token_ids": [index],
                            "finish_reason": "length" if index + 1 == output else None,
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

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert execute_mode(
            artifact_dir,
            f"http://127.0.0.1:{server.server_port}",
            os.getpid(),
            "prefix_cache_on",
        ) == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    rows = [
        json.loads(line)
        for line in (artifact_dir / "modes/prefix_cache_on/raw_request_results.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(rows) == 32
    assert all(row["status"] == "success" for row in rows)
    assert all(
        row["prefix_hits_delta"] == 0
        for row in rows
        if row["request_role"] == "prime"
    )
    assert all(
        row["prefix_hits_delta"] > 0
        for row in rows
        if row["request_role"] == "measured"
    )


def test_finalize_writes_bounded_structured_candidate_without_content(tmp_path):
    artifact_dir = tmp_path / "run"
    plan = build_run_plan()
    for mode in ("prefix_cache_off", "prefix_cache_on"):
        mode_dir = artifact_dir / "modes" / mode
        mode_dir.mkdir(parents=True)
        rows = []
        for item in plan:
            measured = item["request_role"] == "measured"
            rows.append(
                {
                    **item,
                    "mode": mode,
                    "request_body_sha256": item["request_id"],
                    "status": "success",
                    "ttft_ms": 10.0 if mode == "prefix_cache_on" else 20.0,
                    "tpot_ms": 30.0,
                    "e2el_ms": 100.0 if mode == "prefix_cache_on" else 110.0,
                    "output_tokens_per_second": 2.0,
                    "queue_metrics_ok": True,
                    "counter_continuity_ok": True,
                    "spec_activity_ok": True,
                    "prefix_evidence_ok": True,
                    "prefix_queries_delta": 100.0 if mode == "prefix_cache_on" else 0.0,
                    "prefix_hits_delta": (
                        50.0 if mode == "prefix_cache_on" and measured else 0.0
                    ),
                    "accepted_token_delta": 32.0,
                }
            )
        (mode_dir / "raw_request_results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        (mode_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps({"records": [], "generated_text_retained": False, "token_ids_retained": False}),
        encoding="utf-8",
    )
    grading = finalize_artifacts(artifact_dir)

    assert grading["server_grade"] == "candidate_green_p6_3b_prefix_cache_matched_ab"
    assert grading["candidate_size_gate_pass"] is True
    assert (artifact_dir / "mode_group_summary.tsv").exists()
    assert (artifact_dir / "paired_request_summary.tsv").exists()
    assert (artifact_dir / "result_summary.md").exists()
    candidates = (artifact_dir / "delivery_candidates.tsv").read_text(encoding="utf-8")
    assert "generated_text" not in candidates
    assert "token_ids" not in candidates


def test_mode_runner_keeps_mtp_on_and_only_toggles_prefix_cache():
    runner = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3b_mode.sh"
    ).read_text(encoding="utf-8")

    assert "prefix_cache_off|prefix_cache_on" in runner
    assert 'if test "${MODE}" = prefix_cache_on; then' in runner
    assert "cmd+=(--enable-prefix-caching)" in runner
    assert runner.count("--enable-prefix-caching") == 1
    assert runner.count("--speculative-config") == 1
    assert 'EXPECTED_COMMAND_SHA256[prefix_cache_off]=89376c95' in runner
    assert 'EXPECTED_COMMAND_SHA256[prefix_cache_on]=370f8d25' in runner
    assert "run_deepseek_p6_3b_prefix_cache_ab.py" in runner
    assert "msprof" not in runner
    assert "hbm" not in runner.lower()
