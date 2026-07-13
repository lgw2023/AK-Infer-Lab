# Developer to Server

## 当前唯一任务：P6.1R bounded MTP reference repair retry1

```text
task_id: p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_retry1_2026_0713
execution_codebase: main-readonly-with-task-local-overlay
ASCEND_RT_VISIBLE_DEVICES: 0,1,2,3,4,5,6,7
claim_boundary: mtp_minimal_functional_repair_only
PATCH_ATTEMPTS_MAX=1
SERVER_LIFECYCLES_MAX=1
REQUESTS_MAX=1
CONCURRENCY=1
```

P6.1 任务 `p6_1_deepseek_v4_flash_w8a8_no_mtp_minimal_unprofiled_control_2026_0713` 已完成：warmup 与 3/3 measured `4096+64+c1` 全部成功，最终等级为 `yellow_degraded_minimal_unprofiled_control_measured`。不得重跑 P6.0 或 P6.1 control。

首次 P6.1R 任务 `p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_2026_0713` 已在 overlay 前定级 `blocked_repo`：五项实质 root-cause 诊断与 source/patch/payload hash 均通过，但 handoff 的历史首错证据路径不存在。该次 patch、server lifecycle、request 实际次数为 `0/0/0`。服务器报告实际 excerpt 位于本 retry 固定的精确路径并匹配全部三项首错字符串。本轮只修正该路径并建立新 task/result lineage；原 patch、runtime、资源、请求和停止边界全部不变。

本轮只修复首轮 MTP graph capture 的第一个确定性错误：MTP proposer 的 dummy `AscendCommonAttentionMetadata` 没有填 `positions_cpu`，而同版本 DSA-CP builder 在 `dsa_cp.py:280` 无条件执行 `common_attn_metadata.positions_cpu[:num_input_tokens]`，因此八个 worker 同点报 `positions_cpu_none_type_not_subscriptable`。

官方上游 PR <https://github.com/vllm-project/vllm-ascend/pull/11062> / commit `1930088f960aba65eeaae82e9617d090283edc1f` 为 DSV4 MTP graph 补充了 proposer dummy-run 参数，其中包含本轮选择的 `positions_cpu` 字段；但上游声明测试基线是 vLLM `0.23.0`，不是当前 `0.22.1rc1`。因此本轮只允许把该单字段、单行 hunk 应用到 task-local overlay；不允许完整 cherry-pick、版本升级或宣称上游已验证当前 backport。

诊断门全部成立后，最多启动一个 MTP lifecycle，并且最多发送一个固定 `4096+64+c1` 请求。若原错误消失但出现新首错，立即标记 `yellow_mtp_graph_capture_advanced_new_first_failure` 并停止；不得做第二个 patch、不得使用 eager fallback、不得调参。即使请求成功，也只得到 `green_mtp_minimal_request_success`，仍不是 official MTP/128K reference baseline。

禁止 128K/context ladder、其他 P6.1 cell、profiler、P8.1、offload、placement mutation、checkpoint/payload 修改、runtime 升级、base environment/site-packages 修改。成功或失败后都停止，不得自动进入下一任务。

## 1. 固定基线与修正面

```text
model: /data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
runtime: vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1
vLLM commit: 0decac0d96c42b49572498019f0a0e3600f50398
vLLM-Ascend commit: 5f6faa0cb8830f667266f3b8121cd1383606f2a1
NPU: 0,1,2,3,4,5,6,7
parallelism: TP8 + EP
quantization: ascend
MTP: {"method":"mtp","num_speculative_tokens":1}
cudagraph: FULL_DECODE_ONLY
max_model_len: 135168
max_num_batched_tokens: 4096
max_num_seqs: 1
request: one 4096 input + fixed 64 output, concurrency=1, unprofiled
```

固定 payload：

```text
path: 工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
bytes: 19487
sha256: 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
```

唯一修正 artifact：

```text
path: benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
sha256: 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
base target sha256: 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
patched target sha256: 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
changed files: 1
changed lines: 1
```

## 2. 完整同步 main 与双工作区安全门

必须完整 fast-forward 同步远程 `main`，同步后重新读取本文件并确认 task ID。主镜像 tracked 文件继续只读；服务器专属 worktree 仍只读观察。task-local overlay 只能位于主镜像 Git 忽略的 `server_local/<task_id>/overlay_root/`。

- 主镜像 `/data/node0_disk1/liguowei/AK-Infer-Lab@main`：读取 handoff、patch 和固定 payload；tracked 文件不得修改。
- 服务器专属 worktree `/data/node0_disk1/liguowei/AK-Infer-Lab-server-local@server-local/runtime-adaptations`：只记录身份，不从中 import/启动，不 checkout、merge、commit、push 或改写。
- base conda environment：只读；不得修改 base conda environment、`site-packages`、dist-info、entry point 或源码。

不得 restore/reset/stash，不得 commit 或 push，不得自行选择 ours/theirs。不得运行 `通信模块/server_local_git_sync.sh`。

```bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
SERVER_LOCAL_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab-server-local
SERVER_LOCAL_BRANCH=server-local/runtime-adaptations
TASK_ID=p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_retry1_2026_0713
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
OVERLAY_ROOT="${RESULT_DIR}/overlay_root"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_PREFIX}/bin/python"
VLLM_BIN="${ENV_PREFIX}/bin/vllm"
BASE_PLUGIN_ROOT="${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
SERVED_MODEL_NAME=deepseek-v4-flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000
PATCH_ATTEMPTS_MAX=1
SERVER_LIFECYCLES_MAX=1
REQUESTS_MAX=1
CONCURRENCY=1
PATCH_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
PAYLOAD_PATH="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json"
PRIOR_FAILURE_EXCERPT="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_context_smoke_v0221rc1_2026_0712/reference_mtp_maxseq16/first_failure_excerpt.txt"

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"

test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"
test "$(git -C "${SERVER_LOCAL_ROOT}" rev-parse --is-inside-work-tree)" = true
test "$(git -C "${SERVER_LOCAL_ROOT}" branch --show-current)" = "${SERVER_LOCAL_BRANCH}"
git -C "${REPO_ROOT}" rev-parse HEAD > "${RESULT_DIR}/git_head.txt"
git -C "${REPO_ROOT}" rev-parse origin/main > "${RESULT_DIR}/origin_main.txt"
git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main > "${RESULT_DIR}/ahead_behind.txt"
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_before.txt"
git -C "${SERVER_LOCAL_ROOT}" rev-parse HEAD > "${RESULT_DIR}/server_local_head_observed.txt"
git -C "${SERVER_LOCAL_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/server_local_tracked_status_observed.txt"
```

任一门失败标记 `blocked_repo` 并停止，不得建立 overlay 或启动 server。

## 3. 只读首错与源码一致性诊断

诊断必须证明五件事：历史首错仍是 `dsa_cp.py:280` 的 `positions_cpu=None`；installed source 精确等于 `v0.22.1rc1`；proposer dummy metadata 缺失字段；DSA-CP builder 要求字段；model config 含非空 `compress_ratios`，从而 proposer 的 `self.use_compress` 为真。

```bash
set -euo pipefail

test -f "${PRIOR_FAILURE_EXCERPT}"
{
  grep -F -m 1 "dsa_cp.py\", line 280, in build" "${PRIOR_FAILURE_EXCERPT}"
  grep -F -m 1 "common_attn_metadata.positions_cpu[:num_input_tokens].long()" "${PRIOR_FAILURE_EXCERPT}"
  grep -F -m 1 "TypeError: 'NoneType' object is not subscriptable" "${PRIOR_FAILURE_EXCERPT}"
} > "${RESULT_DIR}/prior_failure_gate.txt"
sha256sum "${PRIOR_FAILURE_EXCERPT}" > "${RESULT_DIR}/prior_failure_excerpt_sha256.txt"

BASE_PROPOSER="${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py"
BASE_DSA_CP="${BASE_PLUGIN_ROOT}/attention/context_parallel/dsa_cp.py"
BASE_RUNNER="${BASE_PLUGIN_ROOT}/worker/model_runner_v1.py"
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(sha256sum "${BASE_DSA_CP}" | awk '{print $1}')" = 0906c953fd80a0f86875a947446fe6c72c0057f422a787b52b6adbf7b77fe77b
test "$(sha256sum "${BASE_RUNNER}" | awk '{print $1}')" = 27cbd078817cf746ed0dca27ace2e188e5a13612ee0fe1764da4e55bf3ecbdd5
test "$(sha256sum "${PATCH_PATH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/payload_sha256.txt"

"${PYTHON_BIN}" - "${BASE_PROPOSER}" "${BASE_DSA_CP}" "${BASE_RUNNER}" "${MODEL_PATH}/config.json" "${RESULT_DIR}/diagnostic.json" <<'PY'
import json
import sys
from pathlib import Path

proposer_path, dsa_path, runner_path, config_path, output_path = map(Path, sys.argv[1:])
proposer = proposer_path.read_text(encoding="utf-8")
dsa = dsa_path.read_text(encoding="utf-8")
runner = runner_path.read_text(encoding="utf-8")
config = json.loads(config_path.read_text(encoding="utf-8"))

selected_line = "positions_cpu=self.runner._dsa_positions_cpu_buf if self.use_compress else None,"
checks = {
    "proposer_positions_field_missing": selected_line not in proposer,
    "proposer_positions_device_field_present": "positions=self.runner.positions," in proposer,
    "dsa_builder_unconditional_cpu_slice_present": (
        "input_positions_cpu = common_attn_metadata.positions_cpu[:num_input_tokens].long()" in dsa
    ),
    "runner_cpu_buffer_present": "self._dsa_positions_cpu_buf = torch.zeros(" in runner,
    "model_compress_ratios_nonempty": bool(config.get("compress_ratios")),
}
result = {
    "task_id": "p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_retry1_2026_0713",
    "historical_failure": "positions_cpu_none_type_not_subscriptable",
    "upstream_commit": "1930088f960aba65eeaae82e9617d090283edc1f",
    "upstream_tested_vllm": "0.23.0",
    "checks": checks,
    "root_cause_unique": all(checks.values()),
    "selected_backport": selected_line,
    "full_upstream_backport": False,
}
output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if not result["root_cause_unique"]:
    raise SystemExit(2)
PY
```

若 `diagnostic.json.root_cause_unique` 不是 `true`，最终等级为 `blocked_root_cause_not_unique_or_source_mismatch`，直接生成摘要并停止。不得猜测、放宽 hash、改 patch 或启动 server。

## 4. 创建并验证 task-local overlay

base conda environment 和两个 Git worktree 全部保持不变。overlay 可占用较大 server-local 空间，但不得列入外发候选。

```bash
set -euo pipefail

mkdir -p "${OVERLAY_ROOT}"
cp -a "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
OVERLAY_PROPOSER="${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py"
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${PATCH_PATH}" > "${RESULT_DIR}/patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${PATCH_PATH}" > "${RESULT_DIR}/patch_apply.txt"
printf '%s\n' 1 > "${RESULT_DIR}/patch_attempt_count.txt"
test "$(<"${RESULT_DIR}/patch_attempt_count.txt")" = "${PATCH_ATTEMPTS_MAX}"
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
test "$(sha256sum "${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

"${PYTHON_BIN}" - "${OVERLAY_ROOT}" "${RESULT_DIR}/overlay_import.json" <<'PY'
import importlib
import json
import sys
from pathlib import Path

overlay = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2])
package = importlib.import_module("vllm_ascend")
proposer = importlib.import_module("vllm_ascend.spec_decode.llm_base_proposer")
package_root = Path(package.__file__).resolve()
proposer_file = Path(proposer.__file__).resolve()
result = {
    "package_root": str(package_root),
    "proposer_file": str(proposer_file),
    "package_from_overlay": package_root.is_relative_to(overlay),
    "proposer_from_overlay": proposer_file.is_relative_to(overlay),
}
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
assert result["package_from_overlay"]
assert result["proposer_from_overlay"]
PY
```

dry-run 或唯一实际 apply 失败时标记 `blocked_patch_apply` 并停止。不得做第二个 patch，不得改 base file，不得改用 full upstream commit。

## 5. 八卡资源门

```bash
npu-smi info > "${RESULT_DIR}/npu_smi_before.txt" 2>&1 || true
npu-smi info -t usages > "${RESULT_DIR}/npu_usage_before.txt" 2>&1 || true
ss -ltnp > "${RESULT_DIR}/listening_ports_before.txt" 2>&1 || true

RESOURCE_GATE=not_confirmed
# 只有人工确认 NPU 0-7 全部 Health=OK、无归属不明进程、空闲，且 127.0.0.1:7000 未占用后，才可改为 pass。
printf '%s\n' "${RESOURCE_GATE}" > "${RESULT_DIR}/resource_gate.txt"
test "${RESOURCE_GATE}" = pass
```

任一卡不健康、忙碌、有未知进程或端口冲突，标记 `blocked_resource` 并停止。不得清理或影响非本任务进程。

## 6. 唯一 MTP lifecycle 与唯一请求

只允许以下 command。与冻结 no-MTP cell 的唯一功能差异是 task-local overlay 和 `--speculative-config`；不得添加 `--enforce-eager`，不得改变 capture size、context、并发或 sampling。

```bash
set -euo pipefail

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

printf '%q ' "${cmd[@]}" > "${RESULT_DIR}/server_command.txt"
printf '\n' >> "${RESULT_DIR}/server_command.txt"
sha256sum "${RESULT_DIR}/server_command.txt" > "${RESULT_DIR}/server_command_sha256.txt"

setsid "${cmd[@]}" > "${RESULT_DIR}/vllm_server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" > "${RESULT_DIR}/server_pid.txt"
printf '%s\n' 1 > "${RESULT_DIR}/server_lifecycle_count.txt"
test "$(<"${RESULT_DIR}/server_lifecycle_count.txt")" = "${SERVER_LIFECYCLES_MAX}"

ready_exit=1
for _ in $(seq 1 180); do
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    break
  fi
  if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    ready_exit=0
    break
  fi
  sleep 10
done
printf '%s\n' "${ready_exit}" > "${RESULT_DIR}/server_ready_exit_code.txt"

request_exit=90
request_count=0
if [ "${ready_exit}" -eq 0 ]; then
  request_count=1
  set +e
  "${PYTHON_BIN}" - "${PAYLOAD_PATH}" "${RESULT_DIR}/request_result.json" <<'PY'
import json
import sys
import urllib.request
from pathlib import Path

payload_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
payload = json.loads(payload_path.read_text(encoding="utf-8"))
payload["stream"] = True
payload["stream_options"] = {"include_usage": True}
payload["return_token_ids"] = True

request = urllib.request.Request(
    "http://127.0.0.1:7000/v1/chat/completions",
    data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

streamed = 0
usage = None
finish_reason = None
saw_done = False
with urllib.request.urlopen(request, timeout=1800) as response:
    status = response.status
    for raw in response:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            saw_done = True
            break
        event = json.loads(data)
        if event.get("usage"):
            usage = event["usage"]
        for choice in event.get("choices", []):
            reason = choice.get("finish_reason")
            if reason is not None:
                finish_reason = reason
            token_ids = choice.get("token_ids")
            if token_ids is None:
                token_ids = choice.get("delta", {}).get("token_ids")
            if token_ids:
                streamed += len(token_ids)

result = {
    "status": "success",
    "http_status": status,
    "prompt_tokens": usage.get("prompt_tokens") if usage else None,
    "generated_token_count": usage.get("completion_tokens") if usage else None,
    "streamed_token_count": streamed,
    "finish_reason": finish_reason,
    "saw_done": saw_done,
    "generated_text_retained": False,
    "token_ids_retained": False,
}
checks = {
    "http_status": result["http_status"] == 200,
    "prompt_tokens": result["prompt_tokens"] == 4096,
    "generated_tokens": result["generated_token_count"] == 64,
    "streamed_tokens": result["streamed_token_count"] == 64,
    "finish_reason": result["finish_reason"] == "length",
    "saw_done": result["saw_done"] is True,
}
result["checks"] = checks
output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if not all(checks.values()):
    raise SystemExit(2)
PY
  request_exit=$?
  set -e
fi
printf '%s\n' "${request_exit}" > "${RESULT_DIR}/request_exit_code.txt"
printf '%s\n' "${request_count}" > "${RESULT_DIR}/request_count.txt"
test "${request_count}" -le "${REQUESTS_MAX}"
```

若 server 未 ready，禁止发送请求。若 request 失败，禁止补发。首个 post-patch failure 出现后执行 `stop_after_first_post_patch_failure`，不得做第二个 patch、第二个 lifecycle 或第二个 request。

## 7. 只清理本任务 process group

```bash
set +e
if kill -0 "${server_pid}" 2>/dev/null; then
  kill -TERM -- "-${server_pid}" 2>/dev/null || true
  for _ in $(seq 1 60); do
    kill -0 "${server_pid}" 2>/dev/null || break
    sleep 1
  done
fi
if kill -0 "${server_pid}" 2>/dev/null; then
  kill -KILL -- "-${server_pid}" 2>/dev/null || true
fi
wait "${server_pid}" 2>/dev/null || true
set -e

sleep 10
npu-smi info > "${RESULT_DIR}/npu_smi_after.txt" 2>&1 || true
npu-smi info -t usages > "${RESULT_DIR}/npu_usage_after.txt" 2>&1 || true
ss -ltnp > "${RESULT_DIR}/listening_ports_after.txt" 2>&1 || true
if ss -ltn | awk '{print $4}' | grep -Eq '(^|:)7000$'; then
  printf '%s\n' port_7000_still_listening > "${RESULT_DIR}/cleanup_status.txt"
else
  printf '%s\n' clean > "${RESULT_DIR}/cleanup_status.txt"
fi
```

只能清理本任务记录的 process group。不得 kill 其他 PID。

## 8. 首错提取、分级与结果摘要

从 `vllm_server.log` 只提取最多 200 行围绕首个 traceback 的小 excerpt，不外发 raw log。分级必须互斥：

```bash
"${PYTHON_BIN}" - "${RESULT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

result_dir = Path(sys.argv[1])
log_path = result_dir / "vllm_server.log"
lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines() if log_path.exists() else []
failure_markers = ("Traceback (most recent call last):", " ERROR ", "RuntimeError:", "TypeError:")
start = next((i for i, line in enumerate(lines) if any(marker in line for marker in failure_markers)), None)
excerpt_path = result_dir / "first_failure_excerpt.txt"
if start is not None:
    excerpt_path.write_text("\n".join(lines[start : start + 200]) + "\n", encoding="utf-8")
elif excerpt_path.exists():
    excerpt_path.unlink()

def read_int(name: str, default: int) -> int:
    path = result_dir / name
    return int(path.read_text(encoding="utf-8").strip()) if path.exists() else default

cleanup_path = result_dir / "cleanup_status.txt"
cleanup = cleanup_path.read_text(encoding="utf-8").strip() if cleanup_path.exists() else "missing"
ready_exit = read_int("server_ready_exit_code.txt", 99)
request_exit = read_int("request_exit_code.txt", 99)
log_text = "\n".join(lines)
same_failure = (
    "common_attn_metadata.positions_cpu[:num_input_tokens].long()" in log_text
    and "TypeError: 'NoneType' object is not subscriptable" in log_text
)
if ready_exit == 0 and request_exit == 0 and cleanup == "clean":
    grade = "green_mtp_minimal_request_success"
elif same_failure:
    grade = "red_same_positions_cpu_failure"
else:
    grade = "yellow_mtp_graph_capture_advanced_new_first_failure"

(result_dir / "grade.txt").write_text(grade + "\n", encoding="utf-8")
(result_dir / "grading_inputs.json").write_text(
    json.dumps(
        {
            "server_ready_exit_code": ready_exit,
            "request_exit_code": request_exit,
            "cleanup_status": cleanup,
            "same_positions_cpu_failure": same_failure,
            "grade": grade,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
```

- `green_mtp_minimal_request_success`：server ready、唯一请求 HTTP 200、prompt=4096、generated/streamed=64、`finish_reason=length`、cleanup=`clean`。
- `yellow_mtp_graph_capture_advanced_new_first_failure`：原 `positions_cpu` 错误消失，但 server 或 request 出现新的第一失败点；这是定位进展，不授权第二 patch。
- `red_same_positions_cpu_failure`：post-patch 仍出现相同 `positions_cpu_none_type_not_subscriptable`。
- `blocked_root_cause_not_unique_or_source_mismatch` / `blocked_patch_apply` / `blocked_repo` / `blocked_resource`：对应门失败。

`result_summary.md` 必须写明：task/Git/runtime/model/NPU、parent task 的 `blocked_repo` 与 `0/0/0` 计数、修正后的历史 excerpt 精确路径和 SHA-256、三行 `prior_failure_gate.txt`、历史首错、官方 upstream PR/commit 与 vLLM 0.23.0 测试边界、五项诊断门、base/patch/patched hash、overlay import root、patch/lifecycle/request 实际次数、server-ready/request/cleanup、post-patch 第一失败点和最终 grade。

即使 green，也必须写：

```text
official_baseline: false
mtp_4096_64_minimal_request_validated: true
context_128k_validated: false
full_p6_1_matrix_validated: false
optimization_gain_validated: false
next_task_authorized: false
```

候选外发文件只允许：

```text
result_summary.md
diagnostic.json
overlay_import.json
grading_inputs.json
request_result.json              # 仅成功启动并发送请求时
first_failure_excerpt.txt        # 仅失败/blocked 时
server_command_sha256.txt        # 仅启动 server 时
payload_sha256.txt
prior_failure_gate.txt
prior_failure_excerpt_sha256.txt
cleanup_status.txt               # 仅启动 server 时
```

候选集合必须排除 overlay、raw server log、NPU/Prometheus 快照、patch 副本、checkpoint 和 token IDs。单文件及完整集合均不超过 70KB。

生成 `delivery_candidates.tsv` 和 `transfer_preflight.md`，后者必须包含：

```text
summary_path: <绝对路径>
attachment_scope: <精确候选列表>
total_bytes: <精确值>
set_sha256: <候选 path/bytes/hash 清单 SHA-256>
sensitivity: internal_mtp_functional_repair_selected_error_lines_no_generated_text_or_token_ids
available_methods: email, upload-api, server-local
recommended_method: upload-api
recommendation_reason: one_named_multi_file_session_preserves_the_exact_small_package_and_hashes
selected_method: none
transfer_status: waiting_for_user_choice
```

最终大小门：

```bash
candidates=()
for relative_path in result_summary.md diagnostic.json overlay_import.json grading_inputs.json request_result.json first_failure_excerpt.txt server_command_sha256.txt payload_sha256.txt prior_failure_gate.txt prior_failure_excerpt_sha256.txt cleanup_status.txt; do
  if [ -f "${RESULT_DIR}/${relative_path}" ]; then
    candidates+=("${relative_path}")
  fi
done

total_bytes=0
for relative_path in "${candidates[@]}"; do
  file_bytes="$(stat -c '%s' "${RESULT_DIR}/${relative_path}")"
  test "${file_bytes}" -le 71680
  total_bytes=$((total_bytes + file_bytes))
done
test "${total_bytes}" -le 71680
```

当前未选择 `email`、`upload-api` 或 `server-local`。只报告 exact summary path、候选列表、bytes、SHA-256、敏感性、available methods 和推荐方法，然后等待用户选择；不得发送 pending-confirmation 邮件，不得沿用历史选择。

## 9. 完成边界

- 成功或失败后立即停止，不得自动进入 128K、完整 P6.1、profiler、P8.1 或任何第二修复轮次。
- 不提交或 push server artifact，不修改主镜像 tracked 文件、server-local worktree、base conda environment 或 installed site-packages。
- task-local overlay 和 raw artifacts 只保留在 `server_local/<task_id>/`。
- green 只关闭 MTP `4096+64` 最小功能门；official reference baseline 仍要求未来单独授权的 context ladder 到 `131072+64`。
- yellow/red/blocked 只返回第一失败点和受限证据；不得自行继续。
