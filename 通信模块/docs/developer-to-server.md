# Developer to Server

## 当前唯一服务器动作：P6.1C 合同已准备，未授权执行

~~~text
task_id: p6_1c_deepseek_v4_flash_w8a8_mtp_official_context_ladder_2026_0714
execution_mode: prepared_not_dispatched
workload: benchmarks/deepseek_v4_flash/workloads/p6_1c_mtp_official_context_ladder.yaml
npu_execution_authorized: false
next_task_authorized: false
~~~

本文已准备 P6.1C 的完整服务器执行合同，但当前只作为外部开发机上的待发布输入。
当前不得执行本文任何 Bash/Python 命令；不得启动 vLLM，不得发送模型请求，也不得
占用 NPU 0-7。必须等待本合同发布完成且用户另行明确授权下发后，服务器才可同步并执行。

当前开发范围只包括 workload、handoff、合同测试和直接相关真值面。外部开发机不运行
NPU，开发完成后也不自动提交、推送、下发或传输结果。

## 1. 声明边界与固定合同

本任务只验证 `mtp_context_ladder_functional_capacity_and_stability_only`。HBM calibration
只用于选择不明显干扰推理、又能保留峰值观测精度的采样周期；它不是 official context
slot，也不是性能 benchmark。wall time 只作为 sampler interference guard，不得产生
TTFT、TPOT、吞吐、优化收益或硬件性能结论。HBM 是 whole-device occupancy，不是 KV
object bytes，也不是 HBM traffic。

固定运行时沿用已验收 P6.1R retry2 / P6.1L-R1：DeepSeek-V4-Flash W8A8、TP8+EP、
MTP、graph `FULL_DECODE_ONLY`、`max_num_seqs=1`、prefix cache、chunked prefill、
vLLM `0decac0d96c42b49572498019f0a0e3600f50398` 与 vLLM-Ascend
`5f6faa0cb8830f667266f3b8121cd1383606f2a1`。只允许已验收的 task-local overlay：

~~~text
patch sha256: 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
overlay proposer sha256: 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
base proposer sha256: 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
server command sha256: 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
source payload: 19487 bytes
source payload sha256: 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
SERVER_LIFECYCLES_MAX=2
CALIBRATION_CONTEXT_TOKENS=65536
CALIBRATION_OUTPUT_TOKENS=64
OFFICIAL_CONTEXTS=(4096 32768 65536 98304 131072)
CANDIDATE_INTERVALS=(0.5 1.0 2.0 5.0)
~~~

第一个 fresh lifecycle 只运行 `calibration_control`、
`calibration_high_resolution`、`calibration_selected_validation`；只有 calibration green
才清理并进入第二个 fresh official lifecycle。第二个 lifecycle 无 warmup，按上述五档
顺序各执行一次，失败时最多复用同一 body 一次。两个 lifecycle 都不得在内部重启、
换参数或增加第二 patch。

不得运行 `通信模块/server_local_git_sync.sh`，不得 reset、restore、stash、commit、push，
也不得修改主镜像 tracked 文件、server-local worktree、base environment、site-packages 或
checkpoint。不得关闭 MTP、降低 context、修改 max_num_seqs 或 eager fallback；不得调参、
升级版本、运行 profiler、进入完整 P6.1 性能、P8/offload，或自动修复失败。

## 2. 授权门、同步和任务目录

当前代码块中的授权值故意为 `false`，所以即使误复制也会在任何同步、NPU 查询或目录
创建前停止。只有用户另行明确授权执行、开发机把 workload 与本文中的授权值一并改为
true、发布到远程 `main` 后，服务器才可从本节开始逐节执行。

~~~bash
set -euo pipefail

NPU_EXECUTION_AUTHORIZED=false
test "${NPU_EXECUTION_AUTHORIZED}" = true

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_1c_deepseek_v4_flash_w8a8_mtp_official_context_ladder_2026_0714
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_PREFIX}/bin/python"
VLLM_BIN="${ENV_PREFIX}/bin/vllm"
BASE_PLUGIN_ROOT="${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
SERVED_MODEL_NAME=deepseek-v4-flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000
PATCH_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
PAYLOAD_PATH="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json"
WORKLOAD_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_1c_mtp_official_context_ladder.yaml"
SERVER_LIFECYCLES_MAX=2
CALIBRATION_CONTEXT_TOKENS=65536
CALIBRATION_OUTPUT_TOKENS=64
CANDIDATE_INTERVALS=(0.5 1.0 2.0 5.0)
OFFICIAL_CONTEXTS=(4096 32768 65536 98304 131072)
MAX_RETRIES_PER_CONTEXT=1
MAX_RETRIES_TOTAL=5
MAX_ATTEMPTS_TOTAL=10

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F "npu_execution_authorized: true" "${WORKLOAD_PATH}"
grep -F "npu_execution_authorized: true" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"

test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"/{bodies,calibration,official,helpers,raw_hbm,raw_metrics,request_errors}
git -C "${REPO_ROOT}" rev-parse HEAD > "${RESULT_DIR}/git_head.txt"
git -C "${REPO_ROOT}" rev-parse origin/main > "${RESULT_DIR}/origin_main.txt"
git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main > "${RESULT_DIR}/ahead_behind.txt"
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_before.txt"
~~~

同步只能使用 `fetch + merge --ff-only`。任何仓库门失败都写入小型首错并停止，不得用
`reset --hard` 达成表面一致。

## 3. 启动前 hash、资源和 canonical body 门

先核验 frozen inputs，再构造所有 request body。body 文件、原始 prompt token IDs 与
raw HBM/metrics 全部只留服务器；小结果只含 body 的 token 数、bytes 和 SHA-256。

~~~bash
set -euo pipefail

BASE_PROPOSER="${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py"
test "$(sha256sum "${PATCH_PATH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/source_payload_sha256.txt"

npu-smi info > "${RESULT_DIR}/npu_smi_before.txt" 2>&1 || true
npu-smi info -t usages > "${RESULT_DIR}/npu_usage_before.txt" 2>&1 || true
ss -ltnp > "${RESULT_DIR}/listening_ports_before.txt" 2>&1 || true
RESOURCE_GATE=not_confirmed
# 服务器助手确认 NPU 0-7 Health=OK、空闲、无未知进程且 7000 未占用后，只把此运行时变量设为 pass。
printf '%s\n' "${RESOURCE_GATE}" > "${RESULT_DIR}/resource_gate.txt"
test "${RESOURCE_GATE}" = pass

"${PYTHON_BIN}" - "${PAYLOAD_PATH}" "${RESULT_DIR}/bodies" "${SERVED_MODEL_NAME}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
body_dir = Path(sys.argv[2])
model = sys.argv[3]
source = json.loads(source_path.read_text(encoding="utf-8"))
prompt = source.get("prompt")
assert isinstance(prompt, list) and len(prompt) == 4096
assert all(isinstance(token, int) and not isinstance(token, bool) for token in prompt)

distinct_offsets = []
seen = set()
for offset, token in enumerate(prompt):
    if token not in seen:
        distinct_offsets.append(offset)
        seen.add(token)
    if len(distinct_offsets) == 3:
        break
assert len(distinct_offsets) == 3

def repeat_and_truncate(tokens, size, offset=0):
    rotated = tokens[offset:] + tokens[:offset]
    repeats = (size + len(rotated) - 1) // len(rotated)
    return (rotated * repeats)[:size]

def body_bytes(tokens):
    payload = {
        "ignore_eos": True,
        "max_tokens": 64,
        "min_tokens": 64,
        "model": model,
        "prompt": tokens,
        "return_token_ids": True,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0.0,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

records = []
roles = [
    "calibration_control",
    "calibration_high_resolution",
    "calibration_selected_validation",
]
calibration_prompts = []
for role, offset in zip(roles, distinct_offsets, strict=True):
    tokens = repeat_and_truncate(prompt, 65536, offset)
    calibration_prompts.append(tokens)
    raw = body_bytes(tokens)
    path = body_dir / f"{role}.json"
    path.write_bytes(raw)
    records.append({
        "role": role,
        "context_tokens": len(tokens),
        "body_bytes": len(raw),
        "request_body_sha256": hashlib.sha256(raw).hexdigest(),
        "server_path": str(path),
    })

assert all(len(tokens) == 65536 for tokens in calibration_prompts)
assert all(sorted(tokens) == sorted(calibration_prompts[0]) for tokens in calibration_prompts[1:])
for left in range(3):
    for right in range(left + 1, 3):
        assert calibration_prompts[left][0] != calibration_prompts[right][0]

for context in [4096, 32768, 65536, 98304, 131072]:
    tokens = repeat_and_truncate(prompt, context)
    raw = body_bytes(tokens)
    path = body_dir / f"official_{context}.json"
    path.write_bytes(raw)
    records.append({
        "role": "official_context",
        "context_tokens": context,
        "body_bytes": len(raw),
        "request_body_sha256": hashlib.sha256(raw).hexdigest(),
        "server_path": str(path),
    })

(body_dir / "request_body_manifest.json").write_text(
    json.dumps({
        "source_prompt_tokens": 4096,
        "calibration_pairwise_common_prefix_tokens": 0,
        "calibration_same_token_multiset": True,
        "records": records,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
~~~

启动 server 前，服务器助手必须复核 manifest 中三份 calibration body 均为 65536、三份
SHA-256 不同、pairwise common-prefix=`0`，以及五份 official body 的精确 token 数。
任一 hash/resource/body 门失败，分级为 `blocked_protocol_or_resource_gate`，不得创建 overlay
或启动 lifecycle。

## 4. 固定 HBM sampler 与 request runner

每个 HBM sweep 只能调用一次 `npu-smi info -t usages`，解析 NPU 0-7 的 `NPU ID`、
`HBM Capacity(MB)`、`HBM Usage Rate(%)`。记录 sweep start/end monotonic time、wall time、
八卡覆盖和 parser 状态。以下 helper 必须逐字保存到任务目录；不得把 command 替换成
持续刷新或 profiler。

~~~bash
set -euo pipefail

"${PYTHON_BIN}" - "${RESULT_DIR}/helpers/hbm_sampler.py" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(r'''import argparse
import json
import re
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--interval", type=float, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--raw-dir", type=Path, required=True)
parser.add_argument("--stop-file", type=Path, required=True)
args = parser.parse_args()
assert args.interval in {0.5, 1.0, 2.0, 5.0}
args.raw_dir.mkdir(parents=True, exist_ok=True)

def parse_usage(text):
    records = {}
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^NPU ID\s*[:|]\s*(\d+)\s*$", line)
        if match:
            current = int(match.group(1))
            records.setdefault(current, {"device_id": current})
            continue
        if current is None:
            continue
        match = re.match(r"^HBM Capacity\(MB\)\s*[:|]\s*([0-9.]+)\s*$", line)
        if match:
            records[current]["hbm_capacity_mb"] = float(match.group(1))
            continue
        match = re.match(r"^HBM Usage Rate\(%\)\s*[:|]\s*([0-9.]+)\s*$", line)
        if match:
            records[current]["hbm_usage_pct"] = float(match.group(1))
    devices = []
    for device_id in range(8):
        item = records.get(device_id, {"device_id": device_id})
        item["parser_ok"] = (
            "hbm_capacity_mb" in item and "hbm_usage_pct" in item
        )
        if item["parser_ok"]:
            item["hbm_used_mb"] = (
                item["hbm_capacity_mb"] * item["hbm_usage_pct"] / 100.0
            )
            item["hbm_free_mb"] = item["hbm_capacity_mb"] - item["hbm_used_mb"]
        devices.append(item)
    return devices

sequence = 0
with args.output.open("a", encoding="utf-8") as trace:
    while not args.stop_file.exists():
        sweep_start_ns = time.monotonic_ns()
        completed = subprocess.run(
            ["npu-smi", "info", "-t", "usages"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
        sweep_end_ns = time.monotonic_ns()
        raw_path = args.raw_dir / f"sweep_{sequence:06d}.txt"
        raw_path.write_text(completed.stdout, encoding="utf-8")
        devices = parse_usage(completed.stdout)
        record = {
            "sequence": sequence,
            "command": ["npu-smi", "info", "-t", "usages"],
            "return_code": completed.returncode,
            "sweep_start_monotonic_ns": sweep_start_ns,
            "sweep_end_monotonic_ns": sweep_end_ns,
            "sweep_wall_seconds": (sweep_end_ns - sweep_start_ns) / 1e9,
            "device_coverage": sum(item["parser_ok"] for item in devices),
            "parse_failure_count": sum(not item["parser_ok"] for item in devices),
            "devices": devices,
            "raw_server_path": str(raw_path),
        }
        trace.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        trace.flush()
        sequence += 1
        remaining = args.interval - (time.monotonic_ns() - sweep_start_ns) / 1e9
        if remaining > 0:
            time.sleep(remaining)
''', encoding="utf-8")
PY

"${PYTHON_BIN}" - "${RESULT_DIR}/helpers/request_once.py" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(r'''import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

METRIC_NAMES = {
    "vllm:spec_decode_num_drafts_total": "num_drafts",
    "vllm:spec_decode_num_draft_tokens_total": "num_draft_tokens",
    "vllm:spec_decode_num_accepted_tokens_total": "num_accepted_tokens",
    "vllm:num_requests_running": "num_requests_running",
    "vllm:num_requests_waiting": "num_requests_waiting",
}

parser = argparse.ArgumentParser()
parser.add_argument("--body", type=Path, required=True)
parser.add_argument("--result", type=Path, required=True)
parser.add_argument("--role", required=True)
parser.add_argument("--attempt", type=int, required=True)
parser.add_argument("--base-url", required=True)
parser.add_argument("--server-pid", type=int, required=True)
parser.add_argument("--raw-metrics-dir", type=Path, required=True)
parser.add_argument("--error-dir", type=Path, required=True)
args = parser.parse_args()
args.raw_metrics_dir.mkdir(parents=True, exist_ok=True)
args.error_dir.mkdir(parents=True, exist_ok=True)
body = args.body.read_bytes()
body_sha = hashlib.sha256(body).hexdigest()
payload = json.loads(body)
expected_prompt = len(payload["prompt"])
expected_output = payload["max_tokens"]
assert payload["min_tokens"] == expected_output == 64
assert payload["temperature"] == 0.0
assert payload["ignore_eos"] is True
assert payload["stream"] is True
assert payload["return_token_ids"] is True

def process_alive():
    try:
        os.kill(args.server_pid, 0)
        return True
    except ProcessLookupError:
        return False

def get(path, timeout=10):
    try:
        with urllib.request.urlopen(args.base_url.rstrip("/") + path, timeout=timeout) as response:
            return response.status, response.read()
    except Exception:
        return None, b""

def parse_metrics(raw):
    values = {value: 0.0 for value in METRIC_NAMES.values()}
    found = {value: False for value in METRIC_NAMES.values()}
    for raw_line in raw.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        name = parts[0].split("{", 1)[0]
        key = METRIC_NAMES.get(name)
        if key is None:
            continue
        try:
            values[key] += float(parts[1])
            found[key] = True
        except ValueError:
            pass
    values["all_required_metrics_present"] = all(found.values())
    return values

def metrics(label):
    status, raw = get("/metrics")
    path = args.raw_metrics_dir / f"{args.role}_attempt{args.attempt}_{label}.prom"
    path.write_bytes(raw)
    parsed = parse_metrics(raw) if status == 200 else {
        **{value: 0.0 for value in METRIC_NAMES.values()},
        "all_required_metrics_present": False,
    }
    parsed["http_status"] = status
    parsed["raw_server_path"] = str(path)
    return parsed

health_before, _ = get("/health", timeout=5)
before = metrics("before")
pre_request_checks = {
    "server_alive": process_alive(),
    "health_before_200": health_before == 200,
    "metrics_complete": before["all_required_metrics_present"],
    "queue_idle_before": (
        before["num_requests_running"] == 0
        and before["num_requests_waiting"] == 0
    ),
}
if not all(pre_request_checks.values()):
    record = {
        "slot_id": args.role,
        "context_tokens": expected_prompt,
        "output_tokens": expected_output,
        "attempt_index": args.attempt,
        "request_body_sha256": body_sha,
        "status": "failed_pre_request_gate",
        "http_status": None,
        "prompt_tokens": None,
        "generated_token_count": None,
        "streamed_token_count": 0,
        "finish_reason": None,
        "saw_done": False,
        "health_before": health_before,
        "health_after": health_before,
        "metrics_before": before,
        "metrics_after": before,
        "metrics_delta": {
            "num_drafts": 0.0,
            "num_draft_tokens": 0.0,
            "num_accepted_tokens": 0.0,
        },
        "mtp_activity_evidence": False,
        "queue_evidence_ok": pre_request_checks["queue_idle_before"],
        "request_start_monotonic_ns": None,
        "first_token_monotonic_ns": None,
        "request_end_monotonic_ns": None,
        "request_wall_ms_diagnostic_only": None,
        "bounded_error_server_path": None,
        "checks": pre_request_checks,
        "request_sent": False,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }
    args.result.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    raise SystemExit(2)
request = urllib.request.Request(
    args.base_url.rstrip("/") + "/v1/completions",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
http_status = None
streamed = 0
usage = None
finish_reason = None
saw_done = False
first_token_ns = None
error_path = None
request_start_ns = time.monotonic_ns()
try:
    with urllib.request.urlopen(request, timeout=7200) as response:
        http_status = response.status
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                saw_done = True
                continue
            item = json.loads(data)
            if item.get("usage") is not None:
                usage = item["usage"]
            choices = item.get("choices") or []
            for choice in choices:
                token_ids = choice.get("token_ids") or []
                if token_ids and first_token_ns is None:
                    first_token_ns = time.monotonic_ns()
                streamed += len(token_ids)
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]
except urllib.error.HTTPError as exc:
    http_status = exc.code
    error_path = args.error_dir / f"{args.role}_attempt{args.attempt}.body"
    error_path.write_bytes(exc.read(8192))
except Exception as exc:
    error_path = args.error_dir / f"{args.role}_attempt{args.attempt}.txt"
    error_path.write_text(type(exc).__name__ + ": " + str(exc)[:2048] + "\n", encoding="utf-8")
request_end_ns = time.monotonic_ns()
health_after, _ = get("/health", timeout=5)
after = metrics("after")
delta = {
    "num_drafts": after["num_drafts"] - before["num_drafts"],
    "num_draft_tokens": after["num_draft_tokens"] - before["num_draft_tokens"],
    "num_accepted_tokens": after["num_accepted_tokens"] - before["num_accepted_tokens"],
}
prompt_tokens = usage.get("prompt_tokens") if usage else None
generated = usage.get("completion_tokens") if usage else None
checks = {
    "server_alive": process_alive(),
    "health_before_200": health_before == 200,
    "health_after_200": health_after == 200,
    "http_200": http_status == 200,
    "prompt_tokens_exact": prompt_tokens == expected_prompt,
    "generated_tokens_exact": generated == expected_output,
    "streamed_tokens_exact": streamed == expected_output,
    "finish_reason_length": finish_reason == "length",
    "saw_done": saw_done,
    "metrics_complete": before["all_required_metrics_present"] and after["all_required_metrics_present"],
    "queue_idle_before": before["num_requests_running"] == 0 and before["num_requests_waiting"] == 0,
    "queue_idle_after": after["num_requests_running"] == 0 and after["num_requests_waiting"] == 0,
    "drafts_positive": delta["num_drafts"] > 0,
    "draft_tokens_positive": delta["num_draft_tokens"] > 0,
    "counters_non_decreasing": all(value >= 0 for value in delta.values()),
}
record = {
    "slot_id": args.role,
    "context_tokens": expected_prompt,
    "output_tokens": expected_output,
    "attempt_index": args.attempt,
    "request_body_sha256": body_sha,
    "status": "success" if all(checks.values()) else "failed",
    "http_status": http_status,
    "prompt_tokens": prompt_tokens,
    "generated_token_count": generated,
    "streamed_token_count": streamed,
    "finish_reason": finish_reason,
    "saw_done": saw_done,
    "health_before": health_before,
    "health_after": health_after,
    "metrics_before": before,
    "metrics_after": after,
    "metrics_delta": delta,
    "mtp_activity_evidence": delta["num_drafts"] > 0 and delta["num_draft_tokens"] > 0,
    "queue_evidence_ok": checks["queue_idle_before"] and checks["queue_idle_after"],
    "request_start_monotonic_ns": request_start_ns,
    "first_token_monotonic_ns": first_token_ns,
    "request_end_monotonic_ns": request_end_ns,
    "request_wall_ms_diagnostic_only": (request_end_ns - request_start_ns) / 1e6,
    "bounded_error_server_path": str(error_path) if error_path else None,
    "checks": checks,
    "generated_text_retained": False,
    "token_ids_retained": False,
}
args.result.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if record["status"] == "success" else 2)
''', encoding="utf-8")
PY
~~~

client 只累计 token-ID 数量，不把 token IDs 或 generated content 写入任何结果。HTTP 错误
body 最多截取 8192 bytes 且只留服务器。每个 request 前后都必须读取 `/health`、
`/metrics`，并核对 `vllm:spec_decode_num_drafts_total`、
`vllm:spec_decode_num_draft_tokens_total`、
`vllm:spec_decode_num_accepted_tokens_total`、`vllm:num_requests_running` 与
`vllm:num_requests_waiting`。

## 5. task-local overlay 与固定 server lifecycle 函数

每个 lifecycle 各建一个独立 overlay 目录并只 apply 一次同一 patch。base 文件在前后都要
维持原 hash。只允许下列 server command，命令序列化后的 hash 必须与 R1 一致。

~~~bash
set -euo pipefail

source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

prepare_overlay() {
  local lifecycle_name=$1
  local lifecycle_dir="${RESULT_DIR}/${lifecycle_name}"
  local overlay_root="${lifecycle_dir}/overlay_root"
  mkdir -p "${lifecycle_dir}"
  cp -a "${BASE_PLUGIN_ROOT}" "${overlay_root}/vllm_ascend"
  local proposer="${overlay_root}/vllm_ascend/spec_decode/llm_base_proposer.py"
  test "$(sha256sum "${proposer}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
  patch -p1 -d "${overlay_root}" --dry-run < "${PATCH_PATH}" > "${lifecycle_dir}/patch_dry_run.txt"
  patch -p1 -d "${overlay_root}" < "${PATCH_PATH}" > "${lifecycle_dir}/patch_apply.txt"
  printf '%s\n' 1 > "${lifecycle_dir}/patch_attempt_count.txt"
  test "$(sha256sum "${proposer}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
  test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
  export PYTHONPATH="${overlay_root}:${CANN_GENERATED_PYTHONPATH}"
  "${PYTHON_BIN}" - "${overlay_root}" "${BASE_PROPOSER}" "${lifecycle_dir}/overlay_import.json" <<'PY'
import hashlib
import importlib
import json
import sys
from pathlib import Path

overlay = Path(sys.argv[1]).resolve()
base = Path(sys.argv[2]).resolve()
output = Path(sys.argv[3])
package = importlib.import_module("vllm_ascend")
package_root = Path(package.__file__).resolve()
proposer = overlay / "vllm_ascend/spec_decode/llm_base_proposer.py"
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
result = {
    "package_root": str(package_root),
    "package_from_overlay": package_root.is_relative_to(overlay),
    "overlay_proposer_sha256": digest(proposer),
    "base_proposer_sha256": digest(base),
}
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
assert result["package_from_overlay"]
assert result["overlay_proposer_sha256"] == "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02"
assert result["base_proposer_sha256"] == "0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb"
PY
}

start_server() {
  local lifecycle_name=$1
  local lifecycle_dir="${RESULT_DIR}/${lifecycle_name}"
  cmd=(
    "${VLLM_BIN}" serve "${MODEL_PATH}"
    --safetensors-load-strategy prefetch
    --max-model-len 135168
    --max-num-batched-tokens 4096
    --served-model-name "${SERVED_MODEL_NAME}"
    --gpu-memory-utilization 0.92
    --max-num-seqs 1
    --data-parallel-size 1
    --tensor-parallel-size 8
    --enable-expert-parallel
    --quantization ascend
    --host "${HOST}"
    --port "${PORT}"
    --block-size 128
    --enable-chunked-prefill
    --enable-prefix-caching
    --tokenizer-mode deepseek_v4
    --tool-call-parser deepseek_v4
    --enable-auto-tool-choice
    --reasoning-parser deepseek_v4
    --async-scheduling
    --additional-config '{"enable_flashcomm1":true,"enable_dsa_cp":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":false}'
    --model-loader-extra-config '{"enable_multithread_load":true,"num_threads":16}'
    --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[2,4,6,8,10,12,14,16,18,20,22,24,32,36,40]}'
    --speculative-config '{"method":"mtp","num_speculative_tokens":1}'
  )
  printf '%q ' "${cmd[@]}" > "${lifecycle_dir}/server_command.txt"
  printf '\n' >> "${lifecycle_dir}/server_command.txt"
  sha256sum "${lifecycle_dir}/server_command.txt" > "${lifecycle_dir}/server_command_sha256.txt"
  test "$(awk '{print $1}' "${lifecycle_dir}/server_command_sha256.txt")" = 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
  setsid "${cmd[@]}" > "${lifecycle_dir}/vllm_server.log" 2>&1 &
  server_pid=$!
  export server_pid
  printf '%s\n' "${server_pid}" > "${lifecycle_dir}/server_pid.txt"
  ready_exit=1
  for _ in $(seq 1 180); do
    kill -0 "${server_pid}" 2>/dev/null || break
    if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
      ready_exit=0
      break
    fi
    sleep 10
  done
  printf '%s\n' "${ready_exit}" > "${lifecycle_dir}/server_ready_exit_code.txt"
  if test "${ready_exit}" -ne 0; then
    stop_server "${lifecycle_name}" || true
    return 2
  fi
  if ! curl -fsS "http://${HOST}:${PORT}/metrics" > "${lifecycle_dir}/live_metrics_preflight.prom" \
    || ! grep -F 'vllm:spec_decode_num_drafts_total' "${lifecycle_dir}/live_metrics_preflight.prom" \
    || ! grep -F 'vllm:spec_decode_num_draft_tokens_total' "${lifecycle_dir}/live_metrics_preflight.prom" \
    || ! grep -F 'vllm:spec_decode_num_accepted_tokens_total' "${lifecycle_dir}/live_metrics_preflight.prom" \
    || ! grep -F 'vllm:num_requests_running' "${lifecycle_dir}/live_metrics_preflight.prom" \
    || ! grep -F 'vllm:num_requests_waiting' "${lifecycle_dir}/live_metrics_preflight.prom"; then
    stop_server "${lifecycle_name}" || true
    return 2
  fi
}

stop_server() {
  local lifecycle_name=$1
  local lifecycle_dir="${RESULT_DIR}/${lifecycle_name}"
  kill -TERM -- "-${server_pid}" 2>/dev/null || true
  for _ in $(seq 1 60); do
    kill -0 "${server_pid}" 2>/dev/null || break
    sleep 2
  done
  if kill -0 "${server_pid}" 2>/dev/null; then
    kill -KILL -- "-${server_pid}" 2>/dev/null || true
  fi
  if kill -0 "${server_pid}" 2>/dev/null; then
    printf '%s\n' incomplete > "${lifecycle_dir}/cleanup_status.txt"
    return 2
  fi
  printf '%s\n' clean > "${lifecycle_dir}/cleanup_status.txt"
}
~~~

每次 ready 后还必须结构化解析 live metrics，确认 health=200、running=waiting=0、五个指标
完整；`grep` 只作存在性预检，不能替代 request runner 的结构化前后快照。server 启动但未
ready 时，若尚无成功请求则最终分级为 `red_mtp_context_ladder_no_success`，清理后停止。

## 6. calibration lifecycle：三份长请求与周期选择

先启动一个 fresh calibration lifecycle。`calibration_control` 不启动 sampler；
`calibration_high_resolution` 固定 0.5 秒；从其 raw trace 离线下采样 0.5/1/2/5 秒，选择
满足全部门的最大周期，再由 `calibration_selected_validation` 直接验证。三份 65536+64
请求不计入 `highest_stable_context`，也不得被写成 64K official 成功。

~~~bash
set -euo pipefail

if ! prepare_overlay calibration; then
  printf '%s\n' blocked_protocol_or_resource_gate > "${RESULT_DIR}/server_grade.txt"
  exit 2
fi
if ! start_server calibration; then
  printf '%s\n' red_mtp_context_ladder_no_success > "${RESULT_DIR}/server_grade.txt"
  exit 2
fi
printf '%s\n' 1 > "${RESULT_DIR}/server_lifecycle_count.txt"

run_request_without_sampler() {
  local role=$1
  set +e
  "${PYTHON_BIN}" "${RESULT_DIR}/helpers/request_once.py" \
    --body "${RESULT_DIR}/bodies/${role}.json" \
    --result "${RESULT_DIR}/calibration/${role}.json" \
    --role "${role}" --attempt 1 \
    --base-url "http://${HOST}:${PORT}" --server-pid "${server_pid}" \
    --raw-metrics-dir "${RESULT_DIR}/raw_metrics" \
    --error-dir "${RESULT_DIR}/request_errors"
  request_exit=$?
  set -e
  return "${request_exit}"
}

run_request_with_sampler() {
  local role=$1
  local interval=$2
  local trace="${RESULT_DIR}/raw_hbm/${role}.jsonl"
  local raw_dir="${RESULT_DIR}/raw_hbm/${role}"
  local stop_file="${RESULT_DIR}/raw_hbm/${role}.stop"
  rm -f "${stop_file}"
  "${PYTHON_BIN}" "${RESULT_DIR}/helpers/hbm_sampler.py" \
    --interval "${interval}" --output "${trace}" \
    --raw-dir "${raw_dir}" --stop-file "${stop_file}" &
  sampler_pid=$!
  set +e
  "${PYTHON_BIN}" "${RESULT_DIR}/helpers/request_once.py" \
    --body "${RESULT_DIR}/bodies/${role}.json" \
    --result "${RESULT_DIR}/calibration/${role}.json" \
    --role "${role}" --attempt 1 \
    --base-url "http://${HOST}:${PORT}" --server-pid "${server_pid}" \
    --raw-metrics-dir "${RESULT_DIR}/raw_metrics" \
    --error-dir "${RESULT_DIR}/request_errors"
  request_exit=$?
  set -e
  touch "${stop_file}"
  wait "${sampler_pid}"
  return "${request_exit}"
}

if ! run_request_without_sampler calibration_control; then
  printf '%s\n' blocked_sampling_calibration > "${RESULT_DIR}/server_grade.txt"
  stop_server calibration || true
  exit 2
fi
if ! run_request_with_sampler calibration_high_resolution 0.5; then
  printf '%s\n' blocked_sampling_calibration > "${RESULT_DIR}/server_grade.txt"
  stop_server calibration || true
  exit 2
fi
~~~

离线 selector 的 reference 是 0.5 秒 raw trace 在 request start 到 first token 的 prefill
窗口。每个 candidate 按固定时间 bucket 取第一个 sweep；不得重跑、插值或删掉 parser
失败点。门值固定如下：

~~~text
max_peak_delta_percentage_points=1.0
min_prefill_samples_per_device=20
max_p95_sweep_duty_cycle_ratio=0.05
max_selected_wall_time_increase_ratio=0.10
~~~

~~~bash
set -euo pipefail

set +e
"${PYTHON_BIN}" - \
  "${RESULT_DIR}/raw_hbm/calibration_high_resolution.jsonl" \
  "${RESULT_DIR}/calibration/calibration_high_resolution.json" \
  "${RESULT_DIR}/calibration/sampling_calibration.json" <<'PY'
import json
import math
import statistics
import sys
from pathlib import Path

trace_path = Path(sys.argv[1])
request_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])
sweeps = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line]
request = json.loads(request_path.read_text(encoding="utf-8"))
start_ns = request.get("request_start_monotonic_ns")
first_ns = request.get("first_token_monotonic_ns")
assert request.get("status") == "success"
assert isinstance(start_ns, int) and isinstance(first_ns, int) and first_ns > start_ns
assert sweeps

all_parse_ok = all(
    sweep.get("return_code") == 0
    and sweep.get("device_coverage") == 8
    and sweep.get("parse_failure_count") == 0
    for sweep in sweeps
)
prefill = [
    sweep for sweep in sweeps
    if start_ns <= sweep["sweep_start_monotonic_ns"] <= first_ns
]

def percentile(values, percentile_value):
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]

def downsample(interval):
    selected = []
    seen_buckets = set()
    for sweep in prefill:
        bucket = int((sweep["sweep_start_monotonic_ns"] - start_ns) // int(interval * 1e9))
        if bucket not in seen_buckets:
            seen_buckets.add(bucket)
            selected.append(sweep)
    return selected

reference = downsample(0.5)
reference_peaks = {
    str(device_id): max(
        next(item["hbm_usage_pct"] for item in sweep["devices"] if item["device_id"] == device_id)
        for sweep in reference
    )
    for device_id in range(8)
} if reference and all_parse_ok else {}
p95_wall = percentile([sweep["sweep_wall_seconds"] for sweep in sweeps], 0.95)
candidates = []
for interval in [0.5, 1.0, 2.0, 5.0]:
    selected = downsample(interval)
    peaks = {}
    if selected and all_parse_ok:
        peaks = {
            str(device_id): max(
                next(item["hbm_usage_pct"] for item in sweep["devices"] if item["device_id"] == device_id)
                for sweep in selected
            )
            for device_id in range(8)
        }
    deltas = {
        key: abs(peaks[key] - reference_peaks[key])
        for key in peaks.keys() & reference_peaks.keys()
    }
    sample_counts = {str(device_id): len(selected) for device_id in range(8)}
    gates = {
        "eight_device_coverage": all_parse_ok and len(peaks) == 8,
        "no_parse_failure": all_parse_ok,
        "peak_delta_within_one_percentage_point": (
            len(deltas) == 8 and max(deltas.values()) <= 1.0
        ),
        "at_least_twenty_prefill_samples_per_device": min(sample_counts.values()) >= 20,
        "p95_sweep_duty_cycle_at_most_five_percent": p95_wall / interval <= 0.05,
    }
    candidates.append({
        "interval_seconds": interval,
        "prefill_sample_count_by_device": sample_counts,
        "hbm_usage_pct_max_by_device": peaks,
        "peak_delta_percentage_points_by_device": deltas,
        "p95_sweep_wall_seconds": p95_wall,
        "p95_sweep_duty_cycle_ratio": p95_wall / interval,
        "gates": gates,
        "passes": all(gates.values()),
    })
passing = [item for item in candidates if item["passes"]]
result = {
    "reference_interval_seconds": 0.5,
    "reference_prefill_sample_count": len(reference),
    "reference_hbm_usage_pct_max_by_device": reference_peaks,
    "raw_sweep_count": len(sweeps),
    "raw_all_eight_devices_and_no_parse_failures": all_parse_ok,
    "sweep_wall_seconds_p50": statistics.median([item["sweep_wall_seconds"] for item in sweeps]),
    "sweep_wall_seconds_p95": p95_wall,
    "candidates": candidates,
    "selected_interval_seconds": max(item["interval_seconds"] for item in passing) if passing else None,
    "selection_policy": "largest_interval_passing_all_gates",
    "calibration_request_is_official_context_evidence": False,
}
output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if result["selected_interval_seconds"] is not None else 2)
PY
selector_exit=$?
set -e
if test "${selector_exit}" -ne 0; then
  printf '%s\n' blocked_sampling_calibration > "${RESULT_DIR}/server_grade.txt"
  stop_server calibration || true
  exit 2
fi

SELECTED_HBM_INTERVAL_SECONDS="$("${PYTHON_BIN}" -c 'import json,sys; print(json.load(open(sys.argv[1]))["selected_interval_seconds"])' "${RESULT_DIR}/calibration/sampling_calibration.json")"
case "${SELECTED_HBM_INTERVAL_SECONDS}" in
  0.5|1.0|2.0|5.0) ;;
  *) printf '%s\n' blocked_sampling_calibration > "${RESULT_DIR}/server_grade.txt"; stop_server calibration || true; exit 2 ;;
esac
printf '%s\n' "${SELECTED_HBM_INTERVAL_SECONDS}" > "${RESULT_DIR}/calibration/selected_hbm_interval_seconds.txt"

if ! run_request_with_sampler calibration_selected_validation "${SELECTED_HBM_INTERVAL_SECONDS}"; then
  printf '%s\n' blocked_sampling_calibration > "${RESULT_DIR}/server_grade.txt"
  stop_server calibration || true
  exit 2
fi

set +e
"${PYTHON_BIN}" - \
  "${RESULT_DIR}/calibration/calibration_control.json" \
  "${RESULT_DIR}/calibration/calibration_high_resolution.json" \
  "${RESULT_DIR}/calibration/calibration_selected_validation.json" \
  "${RESULT_DIR}/raw_hbm/calibration_selected_validation.jsonl" \
  "${RESULT_DIR}/calibration/selected_validation_guard.json" \
  "${RESULT_DIR}/calibration/sampling_calibration.json" <<'PY'
import json
import sys
from pathlib import Path

control = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
high_resolution = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
validation = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
sweeps = [
    json.loads(line)
    for line in Path(sys.argv[4]).read_text(encoding="utf-8").splitlines()
    if line
]
output = Path(sys.argv[5])
calibration_path = Path(sys.argv[6])
control_ms = control["request_wall_ms_diagnostic_only"]
validation_ms = validation["request_wall_ms_diagnostic_only"]
increase = max(0.0, validation_ms - control_ms) / control_ms
counter_names = ["num_drafts", "num_draft_tokens", "num_accepted_tokens"]
counter_continuity = all(
    high_resolution["metrics_before"][name] == control["metrics_after"][name]
    and validation["metrics_before"][name] == high_resolution["metrics_after"][name]
    for name in counter_names
)
all_selected_sweeps_valid = bool(sweeps) and all(
    sweep.get("return_code") == 0
    and sweep.get("device_coverage") == 8
    and sweep.get("parse_failure_count") == 0
    for sweep in sweeps
)
selected_samples = {}
for device_id in range(8):
    device_samples = [
        next(item for item in sweep["devices"] if item["device_id"] == device_id)
        for sweep in sweeps
    ] if all_selected_sweeps_valid else []
    selected_samples[str(device_id)] = {
        "sample_count": len(device_samples),
        "hbm_usage_pct_max": max(
            (item["hbm_usage_pct"] for item in device_samples), default=None
        ),
        "parser_ok": bool(device_samples) and all(item.get("parser_ok") for item in device_samples),
    }
checks = {
    "control_success": control.get("status") == "success",
    "high_resolution_success": high_resolution.get("status") == "success",
    "selected_validation_success": validation.get("status") == "success",
    "counter_continuity": counter_continuity,
    "selected_validation_hbm_eight_devices_and_no_parse_failures": all_selected_sweeps_valid,
    "wall_time_increase_ratio_at_most_ten_percent": increase <= 0.10,
}
result = {
    "control_wall_ms_diagnostic_only": control_ms,
    "selected_validation_wall_ms_diagnostic_only": validation_ms,
    "wall_time_increase_ratio": increase,
    "wall_time_is_performance_evidence": False,
    "selected_validation_hbm_by_device": selected_samples,
    "checks": checks,
    "all_checks_pass": all(checks.values()),
}
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
calibration["selected_validation"] = result
calibration_path.write_text(
    json.dumps(calibration, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
raise SystemExit(0 if result["all_checks_pass"] else 2)
PY
validation_guard_exit=$?
set -e
if test "${validation_guard_exit}" -ne 0; then
  printf '%s\n' blocked_sampling_calibration > "${RESULT_DIR}/server_grade.txt"
  stop_server calibration || true
  exit 2
fi

printf '%s\n' green > "${RESULT_DIR}/calibration/calibration_status.txt"
stop_server calibration
test "$(<"${RESULT_DIR}/calibration/cleanup_status.txt")" = clean
~~~

任一 calibration 请求失败、任一 sweep 八卡解析不全、没有 candidate 同时通过全部门，或
selected validation 相对 control 的 diagnostic wall-time 增幅超过 10%，必须写
`blocked_sampling_calibration`，清理后停止，不得启动 official lifecycle。raw trace、三份
body 和 token IDs 留服务器；calibration status 不产生 context 成功声明。

## 7. fresh official lifecycle、五档与一次原 body 重试

只有 calibration status=`green` 且 calibration cleanup=`clean` 才进入本节。此处必须重新
创建 overlay、启动新 server、重新取得 health/metrics/counter baseline。calibration cache、
counter 和采样 trace 不得进入 official 结果。`SELECTED_HBM_INTERVAL_SECONDS` 从校准文件
只读取一次；selected interval 在正式 lifecycle 内不得改变。

~~~bash
set -euo pipefail

test "$(<"${RESULT_DIR}/calibration/calibration_status.txt")" = green
test "$(<"${RESULT_DIR}/calibration/cleanup_status.txt")" = clean
SELECTED_HBM_INTERVAL_SECONDS="$(<"${RESULT_DIR}/calibration/selected_hbm_interval_seconds.txt")"
case "${SELECTED_HBM_INTERVAL_SECONDS}" in 0.5|1.0|2.0|5.0) ;; *) exit 2 ;; esac
FROZEN_SELECTED_HBM_INTERVAL_SECONDS="${SELECTED_HBM_INTERVAL_SECONDS}"

if ! prepare_overlay official; then
  printf '%s\n' blocked_protocol_or_resource_gate > "${RESULT_DIR}/server_grade.txt"
  exit 2
fi
if ! start_server official; then
  printf '%s\n' red_mtp_context_ladder_no_success > "${RESULT_DIR}/server_grade.txt"
  exit 2
fi
printf '%s\n' 2 > "${RESULT_DIR}/server_lifecycle_count.txt"
test "$(<"${RESULT_DIR}/server_lifecycle_count.txt")" = "${SERVER_LIFECYCLES_MAX}"

"${PYTHON_BIN}" - "${RESULT_DIR}/helpers/pre_attempt_gate.py" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(r'''import json
import os
import sys
import urllib.request
from pathlib import Path

base_url = sys.argv[1].rstrip("/")
server_pid = int(sys.argv[2])
output = Path(sys.argv[3])
required = {
    "vllm:spec_decode_num_drafts_total",
    "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total",
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
}

def fetch(path):
    try:
        with urllib.request.urlopen(base_url + path, timeout=10) as response:
            return response.status, response.read()
    except Exception:
        return None, b""

health_status, _ = fetch("/health")
metrics_status, raw = fetch("/metrics")
values = {name: 0.0 for name in required}
found = set()
for raw_line in raw.decode("utf-8", errors="replace").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split(None, 1)
    name = parts[0].split("{", 1)[0] if len(parts) == 2 else ""
    if name in required:
        try:
            values[name] += float(parts[1])
            found.add(name)
        except ValueError:
            pass
try:
    os.kill(server_pid, 0)
    alive = True
except ProcessLookupError:
    alive = False
checks = {
    "server_alive": alive,
    "health_200": health_status == 200,
    "metrics_200": metrics_status == 200,
    "all_required_metrics_present": found == required,
    "running_zero": values["vllm:num_requests_running"] == 0,
    "waiting_zero": values["vllm:num_requests_waiting"] == 0,
}
result = {"checks": checks, "values": values, "all_checks_pass": all(checks.values())}
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if result["all_checks_pass"] else 2)
''', encoding="utf-8")
PY

"${PYTHON_BIN}" - "${RESULT_DIR}/helpers/summarize_hbm.py" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(r'''import json
import sys
from pathlib import Path

trace_path = Path(sys.argv[1])
context = int(sys.argv[2])
attempt = int(sys.argv[3])
interval = float(sys.argv[4])
output = Path(sys.argv[5])
sweeps = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line]
records = []
for device_id in range(8):
    samples = []
    parser_ok = bool(sweeps)
    for sweep in sweeps:
        matches = [item for item in sweep.get("devices", []) if item.get("device_id") == device_id]
        parser_ok = parser_ok and sweep.get("return_code") == 0 and len(matches) == 1 and matches[0].get("parser_ok") is True
        if matches and matches[0].get("parser_ok") is True:
            samples.append(matches[0])
    capacities = {item["hbm_capacity_mb"] for item in samples}
    records.append({
        "context_tokens": context,
        "attempt_index": attempt,
        "selected_interval_seconds": interval,
        "device_id": device_id,
        "sample_count": len(samples),
        "hbm_capacity_mb": next(iter(capacities)) if len(capacities) == 1 else None,
        "hbm_used_max_mb": max((item["hbm_used_mb"] for item in samples), default=None),
        "hbm_free_min_mb": min((item["hbm_free_mb"] for item in samples), default=None),
        "hbm_usage_pct_max": max((item["hbm_usage_pct"] for item in samples), default=None),
        "parser_ok": parser_ok and len(samples) > 0 and len(capacities) == 1,
        "scope": "whole_device_hbm_occupancy_not_kv_object_bytes_or_traffic",
    })
result = {
    "context_tokens": context,
    "attempt_index": attempt,
    "selected_interval_seconds": interval,
    "devices": records,
    "all_eight_devices_valid": len(records) == 8 and all(item["parser_ok"] for item in records),
}
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if result["all_eight_devices_valid"] else 2)
''', encoding="utf-8")
PY

: > "${RESULT_DIR}/attempt_results.jsonl"
: > "${RESULT_DIR}/hbm_summary.jsonl"
retry_count=0
successful_contexts=()
evidence_incomplete=0

for context in "${OFFICIAL_CONTEXTS[@]}"; do
  context_succeeded=0
  body="${RESULT_DIR}/bodies/official_${context}.json"
  frozen_body_sha="$(sha256sum "${body}" | awk '{print $1}')"
  for attempt in 1 2; do
    if test "${attempt}" -eq 2; then
      test "${MAX_RETRIES_PER_CONTEXT}" -eq 1
      test "${retry_count}" -lt "${MAX_RETRIES_TOTAL}"
      retry_count=$((retry_count + 1))
      test "$(sha256sum "${body}" | awk '{print $1}')" = "${frozen_body_sha}"
    fi
    gate_path="${RESULT_DIR}/official/pre_attempt_${context}_${attempt}.json"
    set +e
    "${PYTHON_BIN}" "${RESULT_DIR}/helpers/pre_attempt_gate.py" \
      "http://${HOST}:${PORT}" "${server_pid}" "${gate_path}"
    gate_exit=$?
    set -e
    if test "${gate_exit}" -ne 0; then
      printf '%s\n' blocked_protocol_or_resource_gate > "${RESULT_DIR}/server_grade.txt"
      stop_server official || true
      exit 2
    fi

    role="official_${context}"
    trace="${RESULT_DIR}/raw_hbm/${role}_attempt${attempt}.jsonl"
    raw_dir="${RESULT_DIR}/raw_hbm/${role}_attempt${attempt}"
    stop_file="${RESULT_DIR}/raw_hbm/${role}_attempt${attempt}.stop"
    request_result="${RESULT_DIR}/official/${role}_attempt${attempt}.json"
    hbm_result="${RESULT_DIR}/official/${role}_attempt${attempt}_hbm.json"
    rm -f "${stop_file}"
    "${PYTHON_BIN}" "${RESULT_DIR}/helpers/hbm_sampler.py" \
      --interval "${FROZEN_SELECTED_HBM_INTERVAL_SECONDS}" \
      --output "${trace}" --raw-dir "${raw_dir}" --stop-file "${stop_file}" &
    sampler_pid=$!
    set +e
    "${PYTHON_BIN}" "${RESULT_DIR}/helpers/request_once.py" \
      --body "${body}" --result "${request_result}" \
      --role "${role}" --attempt "${attempt}" \
      --base-url "http://${HOST}:${PORT}" --server-pid "${server_pid}" \
      --raw-metrics-dir "${RESULT_DIR}/raw_metrics" \
      --error-dir "${RESULT_DIR}/request_errors"
    request_exit=$?
    set -e
    touch "${stop_file}"
    wait "${sampler_pid}"
    set +e
    "${PYTHON_BIN}" "${RESULT_DIR}/helpers/summarize_hbm.py" \
      "${trace}" "${context}" "${attempt}" \
      "${FROZEN_SELECTED_HBM_INTERVAL_SECONDS}" "${hbm_result}"
    hbm_exit=$?
    set -e
    "${PYTHON_BIN}" - "${request_result}" "${hbm_result}" \
      "${RESULT_DIR}/attempt_results.jsonl" "${RESULT_DIR}/hbm_summary.jsonl" \
      "${FROZEN_SELECTED_HBM_INTERVAL_SECONDS}" "${attempt}" <<'PY'
import json
import sys
from pathlib import Path

request_path = Path(sys.argv[1])
hbm_path = Path(sys.argv[2])
attempts_path = Path(sys.argv[3])
hbm_summary_path = Path(sys.argv[4])
interval = float(sys.argv[5])
attempt = int(sys.argv[6])
request = json.loads(request_path.read_text(encoding="utf-8"))
hbm = json.loads(hbm_path.read_text(encoding="utf-8"))
request["selected_hbm_interval_seconds"] = interval
request["hbm_summary_path"] = str(hbm_path)
request["retry_recovery"] = attempt == 2 and request.get("status") == "success"
with attempts_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n")
with hbm_summary_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(hbm, sort_keys=True, separators=(",", ":")) + "\n")
PY
    if test "${hbm_exit}" -ne 0; then
      evidence_incomplete=1
      break 2
    fi
    if test "${request_exit}" -eq 0; then
      successful_contexts+=("${context}")
      context_succeeded=1
      break
    fi
  done
  if test "${context_succeeded}" -ne 1; then
    break
  fi
done
~~~

不得在某档失败后降低长度冒充该档，也不得在 retry 前改变 body bytes、采样周期、server
参数或 patch。每档最多一次 retry，总 retry 上限 5、总 attempt 上限 10。仅在原进程存活、
health=200、running=waiting=0、metrics 完整且 body hash 不变时才允许 retry；第二次失败
立即停止，不执行更高档。

## 8. hard-gate grading 与 cleanup

grading 必须消费每个 attempt 的 request、metrics、HBM 摘要与固定 body manifest。每个成功
attempt 的 drafts、draft_tokens 必须正增量；accepted 单档可为 0，但五档累计必须大于 0；
counter 必须连续。`highest_stable_context` 只能来自 official 五档成功结果。

~~~bash
set -euo pipefail

set +e
"${PYTHON_BIN}" - "${RESULT_DIR}" "${FROZEN_SELECTED_HBM_INTERVAL_SECONDS}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
selected_interval = float(sys.argv[2])
contexts = [4096, 32768, 65536, 98304, 131072]
attempts = [json.loads(line) for line in (root / "attempt_results.jsonl").read_text(encoding="utf-8").splitlines() if line]
manifest = json.loads((root / "bodies/request_body_manifest.json").read_text(encoding="utf-8"))
official_hashes = {
    item["context_tokens"]: item["request_body_sha256"]
    for item in manifest["records"] if item["role"] == "official_context"
}
successes = {}
hashes_stable = True
all_attempt_evidence = True
counter_continuity = True
previous_after = None
accepted_total = 0.0
retry_count = 0
for item in attempts:
    context = item["context_tokens"]
    hashes_stable = hashes_stable and item["request_body_sha256"] == official_hashes.get(context)
    if item["attempt_index"] == 2:
        retry_count += 1
    before = item["metrics_before"]
    after = item["metrics_after"]
    if previous_after is not None:
        for key in ["num_drafts", "num_draft_tokens", "num_accepted_tokens"]:
            counter_continuity = counter_continuity and before[key] == previous_after[key]
    previous_after = after
    if item["status"] == "success":
        successes[context] = item
        accepted_total += item["metrics_delta"]["num_accepted_tokens"]
    hbm = json.loads(Path(item["hbm_summary_path"]).read_text(encoding="utf-8"))
    checks = item.get("checks", {})
    evidence_checks = [
        checks.get("server_alive") is True,
        checks.get("health_before_200") is True,
        checks.get("health_after_200") is True,
        checks.get("metrics_complete") is True,
        checks.get("queue_idle_before") is True,
        checks.get("queue_idle_after") is True,
        checks.get("counters_non_decreasing") is True,
    ]
    if item["status"] == "success":
        evidence_checks.append(all(checks.values()))
    all_attempt_evidence = all_attempt_evidence and (
        item["selected_hbm_interval_seconds"] == selected_interval
        and all(evidence_checks)
        and hbm.get("all_eight_devices_valid") is True
        and len(hbm.get("devices", [])) == 8
    )
successful_order = [context for context in contexts if context in successes]
all_five = successful_order == contexts
all_first_attempt = all_five and all(successes[context]["attempt_index"] == 1 for context in contexts)
if not attempts or 4096 not in successes:
    grade = "red_mtp_context_ladder_no_success"
elif not all_attempt_evidence or not hashes_stable or not counter_continuity:
    grade = "red_mtp_context_ladder_evidence_incomplete"
elif not all_five:
    grade = "yellow_mtp_context_ladder_partial"
elif retry_count:
    grade = "yellow_mtp_official_context_ladder_recovered_with_retry"
elif accepted_total <= 0:
    grade = "red_mtp_context_ladder_evidence_incomplete"
else:
    grade = "candidate_green_mtp_official_context_ladder"
result = {
    "server_grade": grade,
    "claim_boundary": "mtp_context_ladder_functional_capacity_and_stability_only",
    "selected_hbm_interval_seconds": selected_interval,
    "attempt_count": len(attempts),
    "retry_count": retry_count,
    "successful_contexts": successful_order,
    "highest_stable_context": max(successful_order) if successful_order else None,
    "all_five_contexts_successful": all_five,
    "all_five_first_attempt_successes": all_first_attempt,
    "accepted_token_delta_total": accepted_total,
    "request_body_hashes_stable": hashes_stable,
    "counter_continuity": counter_continuity,
    "all_attempt_evidence_complete": all_attempt_evidence,
    "official_reference_baseline": False,
    "developer_review_required_for_green": True,
    "calibration_counts_as_context_success": False,
    "prior_green_results_remain_valid": True,
}
(root / "official_ladder_summary.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(root / "server_grade.txt").write_text(grade + "\n", encoding="utf-8")
raise SystemExit(0 if grade == "candidate_green_mtp_official_context_ladder" else 1)
PY
grading_exit=$?
set -e

stop_server official || cleanup_exit=$?
cleanup_exit=${cleanup_exit:-0}
cp "${RESULT_DIR}/official/cleanup_status.txt" "${RESULT_DIR}/cleanup_status.txt"
if test "${cleanup_exit}" -ne 0 || test "$(<"${RESULT_DIR}/cleanup_status.txt")" != clean; then
  printf '%s\n' red_cleanup_incomplete > "${RESULT_DIR}/server_grade.txt"
  grading_exit=2
fi
~~~

分级优先级如下：

- calibration 任一门失败：`blocked_sampling_calibration`，不启动 official lifecycle；
- request 前 hash/resource/live-metrics 门失败：`blocked_protocol_or_resource_gate`；
- server 启动但未 ready，或 4096 两次失败且没有成功请求：`red_mtp_context_ladder_no_success`；
- 至少一档成功、后续档两次失败：`yellow_mtp_context_ladder_partial`，记录精确最高稳定档；
- 五档最终成功但发生 retry：`yellow_mtp_official_context_ladder_recovered_with_retry`；
- token、metrics、HBM、counter 或其他 hard evidence 不完整：
  `red_mtp_context_ladder_evidence_incomplete`；
- cleanup 不 clean：`red_cleanup_incomplete`；
- 只有五档全部首次成功且全部 hard gates 通过：
  `candidate_green_mtp_official_context_ladder`。

服务器不得直接写 `green_mtp_official_context_ladder`。只有开发机独立复核用户批准外发的
小结果包后，才可接受该 green 并把 official reference baseline 置为 true。任何新失败都
不撤销既有 4096+64、P6.1L-R1 green 或 no-MTP degraded evidence。

## 9. 小结果候选、敏感性与传输等待门

无论结果是 candidate green、yellow、red 或 blocked，都只准备有界结构化候选。raw server
log、raw metrics、raw HBM sweep、request bodies、错误 body 和 token IDs 全部留服务器。
`generated text 和 token IDs 不得进入结果包`。以下命令只建立候选清单，不执行传输。

~~~bash
set -euo pipefail

cp "${RESULT_DIR}/bodies/request_body_manifest.json" "${RESULT_DIR}/request_body_manifest.json"
if test -f "${RESULT_DIR}/calibration/sampling_calibration.json"; then
  cp "${RESULT_DIR}/calibration/sampling_calibration.json" "${RESULT_DIR}/sampling_calibration.json"
fi
if test -f "${RESULT_DIR}/official/overlay_import.json"; then
  cp "${RESULT_DIR}/official/overlay_import.json" "${RESULT_DIR}/overlay_import.json"
elif test -f "${RESULT_DIR}/calibration/overlay_import.json"; then
  cp "${RESULT_DIR}/calibration/overlay_import.json" "${RESULT_DIR}/overlay_import.json"
fi
if test -f "${RESULT_DIR}/official/server_command_sha256.txt"; then
  cp "${RESULT_DIR}/official/server_command_sha256.txt" "${RESULT_DIR}/server_command_sha256.txt"
elif test -f "${RESULT_DIR}/calibration/server_command_sha256.txt"; then
  cp "${RESULT_DIR}/calibration/server_command_sha256.txt" "${RESULT_DIR}/server_command_sha256.txt"
fi
if test -f "${RESULT_DIR}/official/cleanup_status.txt"; then
  cp "${RESULT_DIR}/official/cleanup_status.txt" "${RESULT_DIR}/cleanup_status.txt"
elif test -f "${RESULT_DIR}/calibration/cleanup_status.txt"; then
  cp "${RESULT_DIR}/calibration/cleanup_status.txt" "${RESULT_DIR}/cleanup_status.txt"
fi

"${PYTHON_BIN}" - "${RESULT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
summary_path = root / "official_ladder_summary.json"
if summary_path.exists():
    ladder = json.loads(summary_path.read_text(encoding="utf-8"))
else:
    ladder = {
        "server_grade": (root / "server_grade.txt").read_text(encoding="utf-8").strip(),
        "highest_stable_context": None,
        "official_reference_baseline": False,
    }
calibration_path = root / "sampling_calibration.json"
calibration = json.loads(calibration_path.read_text(encoding="utf-8")) if calibration_path.exists() else {}
hbm_records = [
    json.loads(line)
    for line in (root / "hbm_summary.jsonl").read_text(encoding="utf-8").splitlines()
    if line
] if (root / "hbm_summary.jsonl").exists() else []
(root / "hbm_summary.json").write_text(
    json.dumps({
        "scope": "whole_device_hbm_occupancy_not_kv_object_bytes_or_traffic",
        "attempt_summaries": hbm_records,
    }, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
grading_inputs = {
    "task_id": "p6_1c_deepseek_v4_flash_w8a8_mtp_official_context_ladder_2026_0714",
    "claim_boundary": "mtp_context_ladder_functional_capacity_and_stability_only",
    "calibration_status": (root / "calibration/calibration_status.txt").read_text(encoding="utf-8").strip()
        if (root / "calibration/calibration_status.txt").exists() else "not_green",
    "server_grade": ladder.get("server_grade"),
    "highest_stable_context": ladder.get("highest_stable_context"),
    "official_reference_baseline": False,
    "developer_review_required": True,
    "performance_claim_allowed": False,
    "profiler_or_p8_claim_allowed": False,
}
(root / "grading_inputs.json").write_text(
    json.dumps(grading_inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
selected = calibration.get("selected_interval_seconds")
lines = [
    "# P6.1C server result summary",
    "",
    f"- task_id: {grading_inputs['task_id']}",
    f"- server_grade: {grading_inputs['server_grade']}",
    f"- selected_hbm_interval_seconds: {selected}",
    f"- highest_stable_context: {grading_inputs['highest_stable_context']}",
    "- official_reference_baseline: false (developer review required)",
    "- claim_boundary: mtp_context_ladder_functional_capacity_and_stability_only",
    "- calibration_counts_as_context_success: false",
    "- performance/profiler/P8 claims: forbidden",
    f"- raw_result_root_server_local: {root}",
    "- generated_text_retained: false",
    "- token_ids_retained: false",
]
(root / "result_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

candidate_names=(
  result_summary.md
  sampling_calibration.json
  request_body_manifest.json
  official_ladder_summary.json
  attempt_results.jsonl
  hbm_summary.json
  grading_inputs.json
  overlay_import.json
  server_command_sha256.txt
  source_payload_sha256.txt
  cleanup_status.txt
  first_failure_excerpt.txt
)
: > "${RESULT_DIR}/delivery_candidates.tsv"
candidate_total_bytes=0
for name in "${candidate_names[@]}"; do
  path="${RESULT_DIR}/${name}"
  test -f "${path}" || continue
  bytes="$(stat -c '%s' "${path}")"
  sha256="$(sha256sum "${path}" | awk '{print $1}')"
  sensitivity=internal_operational_no_generated_content
  printf '%s\t%s\t%s\t%s\n' "${path}" "${bytes}" "${sha256}" "${sensitivity}" >> "${RESULT_DIR}/delivery_candidates.tsv"
  candidate_total_bytes=$((candidate_total_bytes + bytes))
done
printf '%s\n' "${candidate_total_bytes}" > "${RESULT_DIR}/delivery_candidates_total_bytes.txt"
test "${candidate_total_bytes}" -le 71680

scan_files=()
for name in "${candidate_names[@]}"; do
  test -f "${RESULT_DIR}/${name}" && scan_files+=("${RESULT_DIR}/${name}")
done
if rg -n -i '(authorization:|bearer |api[_-]?key|password|passwd|secret|token[=:])' "${scan_files[@]}"; then
  exit 2
fi
~~~

服务器助手随后只在当前会话中报告并等待用户选择：

- exact result summary path；
- `delivery_candidates.tsv` 中完整候选清单及逐文件 bytes、SHA-256、sensitivity；
- total bytes（必须不超过 71680）；
- 可用且互斥的 `email / upload-api / server-local`；
- 推荐方法及理由。对这个原子小包，默认推荐 `upload-api`，理由是命名 multi-file session
  能保持清单和逐文件 hash 的原子对应；这只是推荐，不是授权。

在用户对该完整范围给出新的单一选择前，不得发送 email、不得调用 upload-api，也不得以
status-only 消息先行外发。本文不包含任何 transfer command。过去选择不可继承；任何 401、
409、413、redirect/proxy、timeout、service 或 hash validation 失败后不得自动切换方法，必须
重新报告并等待新选择。服务器 raw artifacts 始终保留。

## 10. 本任务完成条件与报告格式

服务器最终就地报告必须逐项给出：repo HEAD/origin parity、两个 lifecycle 的 PID/ready/
cleanup、三份 calibration 请求、四个 candidate interval 的样本数/peak delta/sweep p50/p95/
duty-cycle、selected validation wall guard、五档逐 attempt token/health/queue/counter/HBM 摘要、
retry、highest stable context、server grade、首错和 raw server paths。不得把 calibration 写入
official 成功档位，也不得把 candidate green 写成开发机已接受的 green。

当前 `npu_execution_authorized:false`、`next_task_authorized:false` 不因本文合同完整而改变。
本轮开发机只验证合同语义与语法，不运行 NPU；后续发布、授权值变更、服务器同步执行和
任何结果外发都分别需要用户新的明确授权。
