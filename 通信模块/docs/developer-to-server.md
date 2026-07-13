# Developer to Server

## 当前唯一任务：P6.1L-R1 完整六 slot 加固重跑

~~~text
task_id: p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_rerun1_2026_0713
execution_codebase: main-readonly-with-task-local-overlay
ASCEND_RT_VISIBLE_DEVICES: 0,1,2,3,4,5,6,7
claim_boundary: mtp_4096_decode_length_stability_revalidation_only
PATCH_ATTEMPTS_MAX=1
SERVER_LIFECYCLES_MAX=1
PLANNED_SLOTS=6
ATTEMPTS_MAX=12
RETRIES_MAX=6
CONCURRENCY=1
~~~

P6.1R retry2
p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_retry2_2026_0713
已取得 green_mtp_minimal_request_success：单行 task-local overlay 修复原
positions_cpu_none_type_not_subscriptable，MTP server ready，唯一
/v1/completions 请求 HTTP 200、prompt=4096、generated/streamed=64、
finish_reason=length，cleanup=clean。随后原 P6.1L 的六个 NPU slot 测量也全部首次成功，
但其 retry2 前置审计因一个并非当前运行路径必出的精确 init 日志文案返回 exit=2，
服务器助手仍继续执行，最终 grading 又没有消费该非零退出码。原始审计与 grading 文件
必须保留，不得改写成 clean pass。

六个 NPU slot 的重跑成本可接受。本轮不得只做离线 corrected audit/grading，也不得
用离线重判代替硬件复验；必须启动一个全新 MTP lifecycle，完整重跑 512×3 → 1024×3。
无隐藏 warmup。每个 slot 最多一次同请求原样重试，因此最多六个计划 slot、十二次
attempt、六次 retry，始终单 lifecycle、concurrency=1。

新审计把结构化计数、hash、HTTP/token、overlay 和 cleanup 作为硬门；单一 logger 文案
只作提示性证据。新 lifecycle 在发送 slot 前必须确认三项 speculative counter 与
running/waiting gauge 均可读取；每个成功 attempt 都必须有正 draft/draft-token 增量，
不再允许 log-only yellow。raw log、raw metrics、NPU 快照和生成内容全部留在服务器。

本轮不是 128K context ladder，也不是完整 P6.1、profiler、P8.1 或性能比较。

## 1. 固定基线、路径和禁止项

~~~text
model: /data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
runtime: vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1
vLLM commit: 0decac0d96c42b49572498019f0a0e3600f50398
vLLM-Ascend commit: 5f6faa0cb8830f667266f3b8121cd1383606f2a1
parallelism: TP8 + EP
quantization: ascend
MTP: {"method":"mtp","num_speculative_tokens":1}
cudagraph: FULL_DECODE_ONLY
max_model_len: 135168
max_num_batched_tokens: 4096
max_num_seqs: 1
endpoint: POST /v1/completions
fixed request URL: "http://127.0.0.1:7000/v1/completions"
request groups: 4096+512 x3, then 4096+1024 x3
sampling: temperature=0, ignore_eos=true, min_tokens=max_tokens
~~~

source payload：

~~~text
path: 工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
bytes: 19487
sha256: 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
~~~

唯一 patch：

该单行 hunk 来自上游 <https://github.com/vllm-project/vllm-ascend/pull/11062> /
commit `1930088f960aba65eeaae82e9617d090283edc1f` 的字段映射证据；上游测试基线为
vLLM 0.23.0，本轮仍只使用已通过 retry2 的 0.22.1rc1 task-local backport，
不得完整 cherry-pick 或宣称上游验证了当前栈。

~~~text
path: benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
sha256: 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
base proposer sha256: 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
patched proposer sha256: 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
changed files/lines: 1/1
~~~

不得运行 `通信模块/server_local_git_sync.sh`。不得 restore/reset/stash，不得 commit 或 push，
不得自行选择 ours/theirs。主镜像 tracked 文件、服务器专属 worktree、
base conda environment、site-packages 和 checkpoint 全部只读；不得修改 base conda environment。
不得做第二个 patch，
不得使用 eager fallback，不得调参、升级、重启第二个 lifecycle、切到 no-MTP、
进入 128K context ladder、完整 P6.1、profiler、P8.1、offload 或 placement mutation。

## 2. 同步 main 与双工作区门

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
SERVER_LOCAL_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab-server-local
SERVER_LOCAL_BRANCH=server-local/runtime-adaptations
TASK_ID=p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_rerun1_2026_0713
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
OVERLAY_ROOT="${RESULT_DIR}/overlay_root"
PRIOR_TASK_ID=p6_1r_deepseek_v4_flash_w8a8_bounded_mtp_reference_repair_retry2_2026_0713
PRIOR_RESULT_DIR="${REPO_ROOT}/server_local/${PRIOR_TASK_ID}"
PRIOR_LADDER_TASK_ID=p6_1l_deepseek_v4_flash_w8a8_mtp_decode_length_ladder_2026_0713
PRIOR_LADDER_RESULT_DIR="${REPO_ROOT}/server_local/${PRIOR_LADDER_TASK_ID}"
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
PLANNED_SLOTS=6
ATTEMPTS_MAX=12
RETRIES_MAX=6
CONCURRENCY=1
PATCH_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
PAYLOAD_PATH="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json"

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"

test ! -e "${RESULT_DIR}"
test -d "${PRIOR_RESULT_DIR}"
test -d "${PRIOR_LADDER_RESULT_DIR}"
test "$(git -C "${SERVER_LOCAL_ROOT}" rev-parse --is-inside-work-tree)" = true
test "$(git -C "${SERVER_LOCAL_ROOT}" branch --show-current)" = "${SERVER_LOCAL_BRANCH}"
test -z "$(git -C "${SERVER_LOCAL_ROOT}" status --porcelain --untracked-files=no)"

mkdir -p "${RESULT_DIR}"
git -C "${REPO_ROOT}" rev-parse HEAD > "${RESULT_DIR}/git_head.txt"
git -C "${REPO_ROOT}" rev-parse origin/main > "${RESULT_DIR}/origin_main.txt"
git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main > "${RESULT_DIR}/ahead_behind.txt"
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_before.txt"
git -C "${SERVER_LOCAL_ROOT}" rev-parse HEAD > "${RESULT_DIR}/server_local_head_observed.txt"
git -C "${SERVER_LOCAL_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/server_local_tracked_status_observed.txt"
~~~

服务器专属 worktree 仍只读观察；不得从中 import、启动、checkout、merge、commit、
push 或修改。任一仓库门失败，标记 blocked_repo 并停止。

## 3. 历史 lineage audit v2：保留偏差，但移除单日志文案假硬门

先运行确定性 v2 审计，再由服务器 AI 助手阅读 retry2 与原 P6.1L 的原始目录。
原 `retry2_raw_audit.json`、exit=2 和 `hard_conflict=true` 是历史事实，必须保留；
v2 不修改、不覆盖也不重新发布旧结果。v2 只决定本次 fresh lifecycle 是否具备
可信 lineage：结构化 count/hash/request/overlay/cleanup 和原 P6.1L 六次正 counter
增量是硬门；logger wording 只作提示，不能单独制造或消除 hard conflict。

~~~bash
set -euo pipefail

for name in patch_attempt_count.txt server_lifecycle_count.txt request_count.txt \
  server_ready_exit_code.txt request_exit_code.txt cleanup_status.txt request_result.json \
  overlay_import.json vllm_server.log server_command.txt; do
  test -f "${PRIOR_RESULT_DIR}/${name}"
done
for name in retry2_raw_audit.json retry2_raw_audit_exit_code.txt attempt_results.jsonl \
  ladder_summary.json cleanup_status.txt server_command_sha256.txt \
  source_payload_sha256.txt; do
  test -f "${PRIOR_LADDER_RESULT_DIR}/${name}"
done

set +e
"${PYTHON_BIN}" - "${PRIOR_RESULT_DIR}" "${PRIOR_LADDER_RESULT_DIR}" \
  "${RESULT_DIR}/historical_lineage_audit_v2.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

retry2 = Path(sys.argv[1])
prior_ladder = Path(sys.argv[2])
output = Path(sys.argv[3])

def read_int(root: Path, name: str) -> int:
    return int((root / name).read_text(encoding="utf-8").strip())

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def first_sha(root: Path, name: str) -> str:
    return (root / name).read_text(encoding="utf-8").split()[0]

request = json.loads((retry2 / "request_result.json").read_text(encoding="utf-8"))
overlay = json.loads((retry2 / "overlay_import.json").read_text(encoding="utf-8"))
retry2_cleanup = (retry2 / "cleanup_status.txt").read_text(encoding="utf-8").strip()
log_path = retry2 / "vllm_server.log"
log_text = log_path.read_text(encoding="utf-8", errors="replace")
positions_failure = (
    "common_attn_metadata.positions_cpu[:num_input_tokens].long()" in log_text
    and "TypeError: 'NoneType' object is not subscriptable" in log_text
)
original_audit = json.loads(
    (prior_ladder / "retry2_raw_audit.json").read_text(encoding="utf-8")
)
original_audit_exit = read_int(prior_ladder, "retry2_raw_audit_exit_code.txt")
ladder = json.loads((prior_ladder / "ladder_summary.json").read_text(encoding="utf-8"))
attempts = [
    json.loads(line)
    for line in (prior_ladder / "attempt_results.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    if line.strip()
]
expected_outputs = {
    "output512_slot1": 512,
    "output512_slot2": 512,
    "output512_slot3": 512,
    "output1024_slot1": 1024,
    "output1024_slot2": 1024,
    "output1024_slot3": 1024,
}

def prior_attempt_complete(item: dict) -> bool:
    delta = item.get("metrics_delta") or {}
    expected = expected_outputs.get(item.get("slot_id"))
    return (
        item.get("attempt_index") == 1
        and item.get("status") == "success"
        and item.get("http_status") == 200
        and item.get("prompt_tokens") == 4096
        and item.get("generated_token_count") == expected
        and item.get("streamed_token_count") == expected
        and item.get("finish_reason") == "length"
        and item.get("saw_done") is True
        and item.get("health_before") == 200
        and item.get("health_after") == 200
        and delta.get("num_drafts", 0) > 0
        and delta.get("num_draft_tokens", 0) > 0
    )

hard_checks = {
    "original_protocol_deviation_preserved": (
        original_audit_exit == 2 and original_audit.get("hard_conflict") is True
    ),
    "retry2_patch_attempts_1": read_int(retry2, "patch_attempt_count.txt") == 1,
    "retry2_server_lifecycles_1": read_int(retry2, "server_lifecycle_count.txt") == 1,
    "retry2_requests_1": read_int(retry2, "request_count.txt") == 1,
    "retry2_server_ready": read_int(retry2, "server_ready_exit_code.txt") == 0,
    "retry2_request_exit_zero": read_int(retry2, "request_exit_code.txt") == 0,
    "http_200": request.get("http_status") == 200,
    "prompt_4096": request.get("prompt_tokens") == 4096,
    "generated_64": request.get("generated_token_count") == 64,
    "streamed_64": request.get("streamed_token_count") == 64,
    "finish_reason_length": request.get("finish_reason") == "length",
    "saw_done": request.get("saw_done") is True,
    "retry2_cleanup_clean": retry2_cleanup == "clean",
    "package_from_overlay": overlay.get("package_from_overlay") is True,
    "overlay_hash": overlay.get("overlay_proposer_sha256")
        == "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02",
    "base_hash": overlay.get("base_proposer_sha256")
        == "0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb",
    "positions_cpu_failure_absent": not positions_failure,
    "prior_ladder_six_first_attempts": (
        len(attempts) == 6
        and {item.get("slot_id") for item in attempts} == set(expected_outputs)
        and all(prior_attempt_complete(item) for item in attempts)
    ),
    "prior_ladder_summary_complete": (
        ladder.get("all_slots_success") is True
        and ladder.get("all_slots_first_attempt_success") is True
        and ladder.get("completed_slot_count") == 6
        and ladder.get("attempt_count") == 6
        and ladder.get("retry_count") == 0
    ),
    "prior_ladder_cleanup_clean": (
        (prior_ladder / "cleanup_status.txt").read_text(encoding="utf-8").strip()
        == "clean"
    ),
    "source_payload_hash_frozen": first_sha(
        prior_ladder, "source_payload_sha256.txt"
    ) == "48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1",
    "server_command_hash_frozen": first_sha(
        prior_ladder, "server_command_sha256.txt"
    ) == "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19",
}
result = {
    "audit_version": 2,
    "original_retry2_raw_audit_exit_code": 2,
    "original_retry2_hard_conflict": True,
    "original_artifacts_preserved_without_rewrite": True,
    "prior_result_regrading_allowed": False,
    "exact_init_log_line_is_hard_gate": False,
    "logger_wording_is_informational_only": True,
    "fresh_npu_rerun_required": True,
    "raw_evidence": {
        "retry2_log_path": str(log_path),
        "retry2_log_bytes": log_path.stat().st_size,
        "retry2_log_sha256": sha256(log_path),
        "prior_ladder_attempts_path": str(prior_ladder / "attempt_results.jsonl"),
        "raw_files_retained_server_local": True,
    },
    "hard_checks": hard_checks,
    "hard_conflict": not all(hard_checks.values()),
}
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if result["hard_conflict"]:
    raise SystemExit(2)
PY
historical_audit_exit=$?
set -e
printf '%s\n' "${historical_audit_exit}" > \
  "${RESULT_DIR}/historical_lineage_audit_v2_exit_code.txt"
test "${historical_audit_exit}" -eq 0
~~~

服务器 AI 助手还必须检查：

- v2 中每个 hard check 是否与原始结构化文件一致；
- 原 P6.1L 六个 attempt 的 metrics delta 是否确实来自同一 lifecycle 且连续；
- retry2 request 之前和期间是否存在被结构化摘要漏掉的 fatal worker/engine traceback；
- shutdown/TBE 背景异常是否只发生在清理阶段。

若发现真实硬冲突，必须把 `historical_lineage_audit_v2_exit_code.txt` 改为 2，写小型
`first_failure_excerpt.txt` 后停止；不得创建 overlay 或启动 server。不得因为精确
`Initializing spec decode proposer` 文案缺失而单独判冲突，也不得把原 exit=2 改写掉。

## 4. 创建并验证 task-local overlay

~~~bash
set -euo pipefail

BASE_PROPOSER="${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py"
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(sha256sum "${PATCH_PATH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/source_payload_sha256.txt"

mkdir -p "${OVERLAY_ROOT}"
cp -a "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
OVERLAY_PROPOSER="${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py"
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${PATCH_PATH}" > "${RESULT_DIR}/patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${PATCH_PATH}" > "${RESULT_DIR}/patch_apply.txt"
printf '%s\n' 1 > "${RESULT_DIR}/patch_attempt_count.txt"
test "$(<"${RESULT_DIR}/patch_attempt_count.txt")" = "${PATCH_ATTEMPTS_MAX}"
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

"${PYTHON_BIN}" - "${OVERLAY_ROOT}" "${BASE_PROPOSER}" "${RESULT_DIR}/overlay_import.json" <<'PY'
import hashlib
import importlib
import json
import sys
from pathlib import Path

overlay = Path(sys.argv[1]).resolve()
base_proposer = Path(sys.argv[2]).resolve()
output = Path(sys.argv[3])
package = importlib.import_module("vllm_ascend")
package_root = Path(package.__file__).resolve()
overlay_proposer = overlay / "vllm_ascend/spec_decode/llm_base_proposer.py"

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = {
    "package_root": str(package_root),
    "package_from_overlay": package_root.is_relative_to(overlay),
    "proposer_module_imported": False,
    "overlay_proposer_sha256": sha256(overlay_proposer),
    "base_proposer_sha256": sha256(base_proposer),
}
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
assert result["package_from_overlay"]
assert result["overlay_proposer_sha256"] == "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02"
assert result["base_proposer_sha256"] == "0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb"
PY
~~~

不得直接 import vllm_ascend.spec_decode.llm_base_proposer；retry1 已证明该路径会命中
既存 circular import。dry-run 或唯一 apply 失败即 blocked_patch_apply。

## 5. 八卡资源门

~~~bash
npu-smi info > "${RESULT_DIR}/npu_smi_before.txt" 2>&1 || true
npu-smi info -t usages > "${RESULT_DIR}/npu_usage_before.txt" 2>&1 || true
ss -ltnp > "${RESULT_DIR}/listening_ports_before.txt" 2>&1 || true

RESOURCE_GATE=not_confirmed
# 服务器 AI 助手人工确认 NPU 0-7 全部 Health=OK、空闲、无未知进程且端口 7000 未占用后，改为 pass。
printf '%s\n' "${RESOURCE_GATE}" > "${RESULT_DIR}/resource_gate.txt"
test "${RESOURCE_GATE}" = pass
~~~

任一卡不健康、忙碌、存在未知进程或端口冲突，标记 blocked_resource 并停止。
不得清理非本任务进程。

## 6. 启动唯一 MTP lifecycle

只允许以下 server command。不得添加 enforce-eager 或修改 capture size。

~~~bash
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
server_command_sha256="$(sha256sum "${RESULT_DIR}/server_command.txt" | awk '{print $1}')"
test "${server_command_sha256}" = 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19

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
test "${ready_exit}" -eq 0
~~~

server 未 ready 时禁止发送请求；清理后标记 blocked_server_not_ready。

## 7. live metrics 完整性与空闲门

该门不发送模型请求，因此不构成 warmup。三项 speculative counter 与两项 request
gauge 必须同时存在，health 必须为 200，running/waiting 必须为 0；否则在 slot 1
之前停止。不得用 runtime log 替代缺失的 Prometheus 指标。

~~~bash
set +e
"${PYTHON_BIN}" - "${RESULT_DIR}" "${server_pid}" "http://${HOST}:${PORT}" <<'PY'
import json
import os
import sys
import urllib.request
from pathlib import Path

result_dir = Path(sys.argv[1])
server_pid = int(sys.argv[2])
base_url = sys.argv[3].rstrip("/")
required = {
    "vllm:spec_decode_num_drafts_total",
    "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total",
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
}

def fetch(path: str) -> tuple[int | None, bytes]:
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as response:
            return response.status, response.read()
    except Exception:
        return None, b""

def parse(text: str) -> tuple[set[str], dict[str, float]]:
    found = set()
    values = {name: 0.0 for name in required}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        name = parts[0].split("{", 1)[0]
        if name not in required:
            continue
        try:
            values[name] += float(parts[1])
            found.add(name)
        except ValueError:
            pass
    return found, values

health_status, _ = fetch("/health")
metrics_status, metrics_body = fetch("/metrics")
(result_dir / "live_metrics_preflight.prom").write_bytes(metrics_body)
found, values = parse(metrics_body.decode("utf-8", errors="replace"))
try:
    os.kill(server_pid, 0)
    server_alive = True
except ProcessLookupError:
    server_alive = False
checks = {
    "server_alive": server_alive,
    "health_200": health_status == 200,
    "metrics_200": metrics_status == 200,
    "all_required_metric_names_present": found == required,
    "num_requests_running_zero": values["vllm:num_requests_running"] == 0,
    "num_requests_waiting_zero": values["vllm:num_requests_waiting"] == 0,
}
result = {
    "health_status": health_status,
    "metrics_status": metrics_status,
    "required_metric_names": sorted(required),
    "found_metric_names": sorted(found),
    "values": values,
    "checks": checks,
    "all_checks_pass": all(checks.values()),
    "raw_metrics_retained_server_local": True,
}
(result_dir / "live_metrics_preflight.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
raise SystemExit(0 if result["all_checks_pass"] else 2)
PY
metrics_preflight_exit=$?
set -e
printf '%s\n' "${metrics_preflight_exit}" > \
  "${RESULT_DIR}/live_metrics_preflight_exit_code.txt"
test "${metrics_preflight_exit}" -eq 0
~~~

## 8. 六个 slot、metrics 与每 slot 一次原样重试

该客户端不保存 generated text 或 token IDs。它只计数 token_ids，记录结构化 usage、
诊断时长、HTTPError 的有界 server-local body、每次 attempt 前后 /metrics 和
/health。原始 metrics 保存到 raw_metrics/，不得列入外发候选。

~~~bash
set -euo pipefail
mkdir -p "${RESULT_DIR}/raw_metrics" "${RESULT_DIR}/request_errors"

set +e
"${PYTHON_BIN}" - "${PAYLOAD_PATH}" "${RESULT_DIR}" "${server_pid}" "http://${HOST}:${PORT}" <<'PY'
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HTTP_ERROR_BODY_MAX_BYTES = 8192
SOCKET_INACTIVITY_TIMEOUT_SECONDS = 1800
payload_path = Path(sys.argv[1])
result_dir = Path(sys.argv[2])
server_pid = int(sys.argv[3])
base_url = sys.argv[4].rstrip("/")
raw_metrics_dir = result_dir / "raw_metrics"
error_dir = result_dir / "request_errors"
attempts_path = result_dir / "attempt_results.jsonl"

slots = [
    ("output512_slot1", 512),
    ("output512_slot2", 512),
    ("output512_slot3", 512),
    ("output1024_slot1", 1024),
    ("output1024_slot2", 1024),
    ("output1024_slot3", 1024),
]

source_payload = json.loads(payload_path.read_text(encoding="utf-8"))
if source_payload.get("temperature") != 0.0:
    raise SystemExit("source payload temperature mismatch")
if source_payload.get("ignore_eos") is not True:
    raise SystemExit("source payload ignore_eos mismatch")

def process_alive() -> bool:
    try:
        os.kill(server_pid, 0)
        return True
    except ProcessLookupError:
        return False

def get(path: str, timeout: int = 10) -> tuple[int | None, bytes]:
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=timeout) as response:
            return response.status, response.read()
    except Exception:
        return None, b""

def health() -> int | None:
    status, _ = get("/health", timeout=5)
    return status

def parse_metrics(text: str) -> dict:
    names = {
        "vllm:spec_decode_num_drafts_total": "num_drafts",
        "vllm:spec_decode_num_draft_tokens_total": "num_draft_tokens",
        "vllm:spec_decode_num_accepted_tokens_total": "num_accepted_tokens",
        "vllm:num_requests_running": "num_requests_running",
        "vllm:num_requests_waiting": "num_requests_waiting",
    }
    values = {value: 0.0 for value in names.values()}
    found = {value: False for value in names.values()}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        metric_name = parts[0].split("{", 1)[0]
        key = names.get(metric_name)
        if key is None:
            continue
        try:
            values[key] += float(parts[1])
            found[key] = True
        except ValueError:
            continue
    values["spec_metrics_available"] = (
        found["num_drafts"] and found["num_draft_tokens"]
        and found["num_accepted_tokens"]
    )
    values["request_gauges_available"] = (
        found["num_requests_running"] and found["num_requests_waiting"]
    )
    return values

def metrics(snapshot_name: str) -> dict:
    status, body = get("/metrics", timeout=10)
    raw_path = raw_metrics_dir / f"{snapshot_name}.prom"
    raw_path.write_bytes(body)
    parsed = parse_metrics(body.decode("utf-8", errors="replace")) if status == 200 else {
        "num_drafts": 0.0,
        "num_draft_tokens": 0.0,
        "num_accepted_tokens": 0.0,
        "num_requests_running": 0.0,
        "num_requests_waiting": 0.0,
        "spec_metrics_available": False,
        "request_gauges_available": False,
    }
    parsed["http_status"] = status
    parsed["raw_server_path"] = str(raw_path)
    return parsed

def metric_delta(before: dict, after: dict) -> dict | None:
    if not before["spec_metrics_available"] or not after["spec_metrics_available"]:
        return None
    return {
        "num_drafts": after["num_drafts"] - before["num_drafts"],
        "num_draft_tokens": after["num_draft_tokens"] - before["num_draft_tokens"],
        "num_accepted_tokens": (
            after["num_accepted_tokens"] - before["num_accepted_tokens"]
        ),
    }

def append_attempt(record: dict) -> None:
    with attempts_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

def run_attempt(slot_id: str, output_tokens: int, attempt_index: int) -> dict:
    payload = dict(source_payload)
    payload["min_tokens"] = output_tokens
    payload["max_tokens"] = output_tokens
    payload["stream"] = True
    payload["stream_options"] = {"include_usage": True}
    payload["return_token_ids"] = True
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request_body_sha256 = hashlib.sha256(body).hexdigest()
    prefix = f"{slot_id}_attempt{attempt_index}"
    health_before = health()
    metrics_before = metrics(f"{prefix}_before")
    request = urllib.request.Request(
        f"{base_url}/v1/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    streamed = 0
    usage = None
    finish_reason = None
    saw_done = False
    http_status = None
    error_type = None
    error_reason = None
    start_ns = time.monotonic_ns()
    try:
        response_context = urllib.request.urlopen(
            request, timeout=SOCKET_INACTIVITY_TIMEOUT_SECONDS
        )
        with response_context as response:
            http_status = response.status
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
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice["finish_reason"]
                    token_ids = choice.get("token_ids")
                    if token_ids is None:
                        token_ids = choice.get("delta", {}).get("token_ids")
                    if token_ids:
                        streamed += len(token_ids)
    except urllib.error.HTTPError as exc:
        http_status = exc.code
        error_type = "http_error"
        error_reason = str(exc.reason)
        body_error = exc.read(HTTP_ERROR_BODY_MAX_BYTES + 1)
        retained = body_error[:HTTP_ERROR_BODY_MAX_BYTES]
        (error_dir / f"{prefix}.json").write_text(
            json.dumps(
                {
                    "http_status": exc.code,
                    "reason": str(exc.reason),
                    "response_body": retained.decode("utf-8", errors="replace"),
                    "response_body_bytes_retained": len(retained),
                    "response_body_truncated": len(body_error) > HTTP_ERROR_BODY_MAX_BYTES,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        error_type = type(exc).__name__
        error_reason = str(exc)
    wall_ms = (time.monotonic_ns() - start_ns) // 1_000_000
    health_after = health()
    metrics_after = metrics(f"{prefix}_after")
    delta = metric_delta(metrics_before, metrics_after)
    if delta is None:
        mtp_activity_evidence = "required_prometheus_counter_delta_missing"
        mtp_activity_ok = False
    else:
        mtp_activity_evidence = "prometheus_counter_delta"
        mtp_activity_ok = (
            delta["num_drafts"] > 0 and delta["num_draft_tokens"] > 0
        )
    queue_evidence_ok = (
        metrics_before["request_gauges_available"]
        and metrics_after["request_gauges_available"]
        and metrics_before["num_requests_running"] == 0
        and metrics_before["num_requests_waiting"] == 0
        and metrics_after["num_requests_running"] == 0
        and metrics_after["num_requests_waiting"] == 0
    )
    generated = usage.get("completion_tokens") if usage else None
    prompt = usage.get("prompt_tokens") if usage else None
    functional_ok = (
        error_type is None
        and http_status == 200
        and prompt == 4096
        and generated == output_tokens
        and streamed == output_tokens
        and finish_reason == "length"
        and saw_done is True
        and health_before == 200
        and health_after == 200
    )
    record = {
        "slot_id": slot_id,
        "output_tokens": output_tokens,
        "attempt_index": attempt_index,
        "request_body_sha256": request_body_sha256,
        "status": (
            "success"
            if functional_ok and mtp_activity_ok and queue_evidence_ok
            else "failed"
        ),
        "http_status": http_status,
        "prompt_tokens": prompt,
        "generated_token_count": generated,
        "streamed_token_count": streamed,
        "finish_reason": finish_reason,
        "saw_done": saw_done,
        "health_before": health_before,
        "health_after": health_after,
        "request_wall_ms_diagnostic_only": wall_ms,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "metrics_delta": delta,
        "mtp_activity_evidence": mtp_activity_evidence,
        "queue_evidence_ok": queue_evidence_ok,
        "retry_recovery": (
            attempt_index == 2
            and functional_ok
            and mtp_activity_ok
            and queue_evidence_ok
        ),
        "error_type": error_type,
        "error_reason": error_reason,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }
    append_attempt(record)
    return record

attempt_count = 0
retry_count = 0
completed_slots = []
failed_slot = None
stop_reason = None
request_hash_by_slot = {}

for slot_id, output_tokens in slots:
    slot_success = False
    for attempt_index in (1, 2):
        attempt_count += 1
        record = run_attempt(slot_id, output_tokens, attempt_index)
        old_hash = request_hash_by_slot.setdefault(slot_id, record["request_body_sha256"])
        if old_hash != record["request_body_sha256"]:
            stop_reason = "retry_request_body_hash_changed"
            failed_slot = slot_id
            break
        if record["status"] == "success":
            completed_slots.append(slot_id)
            slot_success = True
            break
        if attempt_index == 1:
            fresh_health = health()
            idle_metrics = metrics(f"{slot_id}_retry_idle_gate")
            retry_allowed = (
                process_alive()
                and fresh_health == 200
                and idle_metrics["request_gauges_available"]
                and idle_metrics["num_requests_running"] == 0
                and idle_metrics["num_requests_waiting"] == 0
            )
            if retry_allowed:
                retry_count += 1
                continue
            stop_reason = "retry_idle_or_health_gate_failed"
            failed_slot = slot_id
            break
        stop_reason = "slot_failed_twice"
        failed_slot = slot_id
    if not slot_success:
        break

all_slots_success = completed_slots == [slot_id for slot_id, _ in slots]
attempt_records = [
    json.loads(line)
    for line in attempts_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
missing_spec_metrics = any(
    item["metrics_delta"] is None for item in attempt_records
)
all_successes_have_positive_draft_deltas = all(
    item["metrics_delta"] is not None
    and item["metrics_delta"]["num_drafts"] > 0
    and item["metrics_delta"]["num_draft_tokens"] > 0
    for item in attempt_records
    if item["status"] == "success"
)
summary = {
    "planned_slots": 6,
    "completed_slots": completed_slots,
    "completed_slot_count": len(completed_slots),
    "attempt_count": attempt_count,
    "attempts_max": 12,
    "retry_count": retry_count,
    "retries_max": 6,
    "all_slots_success": all_slots_success,
    "all_slots_first_attempt_success": all_slots_success and retry_count == 0,
    "missing_spec_metrics_on_success": missing_spec_metrics,
    "all_successes_have_positive_draft_deltas": (
        all_successes_have_positive_draft_deltas
    ),
    "failed_slot": failed_slot,
    "stop_reason": stop_reason,
    "generated_text_retained": False,
    "token_ids_retained": False,
}
(result_dir / "ladder_summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(result_dir / "attempt_count.txt").write_text(f"{attempt_count}\n", encoding="utf-8")
(result_dir / "retry_count.txt").write_text(f"{retry_count}\n", encoding="utf-8")
(result_dir / "completed_slot_count.txt").write_text(
    f"{len(completed_slots)}\n", encoding="utf-8"
)
raise SystemExit(0 if all_slots_success else 2)
PY
ladder_exit=$?
set -e
printf '%s\n' "${ladder_exit}" > "${RESULT_DIR}/ladder_exit_code.txt"
test "$(<"${RESULT_DIR}/attempt_count.txt")" -le "${ATTEMPTS_MAX}"
test "$(<"${RESULT_DIR}/retry_count.txt")" -le "${RETRIES_MAX}"
~~~

如果首个 attempt 失败，只有进程存活、health=200、running=0、waiting=0 且同
request-body SHA-256 时才能重试。重试成功填满原 slot 并继续；该任务最终最高为
yellow_mtp_decode_length_ladder_revalidated_with_retry。任何 attempt 的三项 speculative
metrics 缺失都属于证据不完整，不得由日志降级替代；重试再失败、server 不健康或
idle 无法证明时，立即停止剩余 slot。

## 9. 清理唯一 process group

~~~bash
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
~~~

只能清理本任务记录的 process group，不得 kill 其他 PID。

## 10. 新日志就地分析、分级和故障反馈

服务器 AI 助手必须读取新 vllm_server.log、attempt_results.jsonl、
ladder_summary.json、raw_metrics/ 和 request_errors/，但只生成 bounded
runtime_log_observations.json、grading_inputs.json、result_summary.md；不得修改代码或
patch。日志观察只用于解释，不替代 metrics，也不参与 green/yellow 判定。

~~~bash
"${PYTHON_BIN}" - "${RESULT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
log_path = root / "vllm_server.log"
lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
text = "\n".join(lines)
ladder = json.loads((root / "ladder_summary.json").read_text(encoding="utf-8"))
attempts = [
    json.loads(line)
    for line in (root / "attempt_results.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    if line.strip()
]
cleanup = (root / "cleanup_status.txt").read_text(encoding="utf-8").strip()
overlay = json.loads((root / "overlay_import.json").read_text(encoding="utf-8"))
metrics_preflight = json.loads(
    (root / "live_metrics_preflight.json").read_text(encoding="utf-8")
)

draft_lines = [
    line for line in lines
    if "[spec_decode/base] Draft model loaded successfully: method=mtp" in line
][:8]
runtime_metric_lines = [
    line for line in lines if "SpecDecoding metrics:" in line
][:24]
positions_failure = (
    "common_attn_metadata.positions_cpu[:num_input_tokens].long()" in text
    and "TypeError: 'NoneType' object is not subscriptable" in text
)
observations = {
    "mtp_draft_loaded_lines": draft_lines,
    "runtime_spec_decode_metric_lines": runtime_metric_lines,
    "original_positions_cpu_failure_absent": not positions_failure,
    "logger_wording_is_informational_only": True,
    "raw_log_retained_server_local": True,
}
(root / "runtime_log_observations.json").write_text(
    json.dumps(observations, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

all_success = ladder["all_slots_success"]
retries = ladder["retry_count"]
missing_metrics = ladder["missing_spec_metrics_on_success"]
complete_metrics = (
    len(attempts) > 0
    and all(item.get("metrics_delta") is not None for item in attempts)
)
positive_success_deltas = all(
    item["metrics_delta"]["num_drafts"] > 0
    and item["metrics_delta"]["num_draft_tokens"] > 0
    for item in attempts
    if item.get("status") == "success" and item.get("metrics_delta") is not None
)
queue_evidence_complete = all(
    item.get("queue_evidence_ok") is True
    for item in attempts
    if item.get("status") == "success"
)
exit_codes = {
    "historical_lineage_audit_v2_exit_code": int(
        (root / "historical_lineage_audit_v2_exit_code.txt").read_text(
            encoding="utf-8"
        ).strip()
    ),
    "live_metrics_preflight_exit_code": int(
        (root / "live_metrics_preflight_exit_code.txt").read_text(
            encoding="utf-8"
        ).strip()
    ),
    "server_ready_exit_code": int(
        (root / "server_ready_exit_code.txt").read_text(encoding="utf-8").strip()
    ),
    "ladder_exit_code": int(
        (root / "ladder_exit_code.txt").read_text(encoding="utf-8").strip()
    ),
}
protocol_checks = {
    "historical_audit_v2_zero": (
        exit_codes["historical_lineage_audit_v2_exit_code"] == 0
    ),
    "live_metrics_preflight_zero": (
        exit_codes["live_metrics_preflight_exit_code"] == 0
    ),
    "server_ready_zero": exit_codes["server_ready_exit_code"] == 0,
    "resource_gate_pass": (
        (root / "resource_gate.txt").read_text(encoding="utf-8").strip() == "pass"
    ),
    "patch_attempt_count_1": (
        int((root / "patch_attempt_count.txt").read_text(encoding="utf-8")) == 1
    ),
    "server_lifecycle_count_1": (
        int((root / "server_lifecycle_count.txt").read_text(encoding="utf-8")) == 1
    ),
    "overlay_package_root": overlay.get("package_from_overlay") is True,
    "overlay_hash": overlay.get("overlay_proposer_sha256")
        == "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02",
    "base_hash": overlay.get("base_proposer_sha256")
        == "0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb",
    "server_command_hash_frozen": (
        (root / "server_command_sha256.txt").read_text(
            encoding="utf-8"
        ).split()[0]
        == "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
    ),
    "source_payload_hash_frozen": (
        (root / "source_payload_sha256.txt").read_text(
            encoding="utf-8"
        ).split()[0]
        == "48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1"
    ),
    "metrics_preflight_checks_pass": metrics_preflight.get("all_checks_pass") is True,
}
measurement_checks = {
    "ladder_exit_zero": exit_codes["ladder_exit_code"] == 0,
    "all_six_slots_success": (
        all_success
        and ladder.get("planned_slots") == 6
        and ladder.get("completed_slot_count") == 6
    ),
    "attempt_budget_respected": ladder.get("attempt_count", 13) <= 12,
    "retry_budget_respected": retries <= 6,
    "complete_spec_metrics": complete_metrics and not missing_metrics,
    "positive_draft_deltas": positive_success_deltas,
    "queue_evidence_complete": queue_evidence_complete,
    "cleanup_clean": cleanup == "clean",
}
hard_gate_failures = [
    name
    for name, passed in {**protocol_checks, **measurement_checks}.items()
    if not passed
]
all_hard_gates_pass = not hard_gate_failures

if cleanup != "clean":
    grade = "red_cleanup_incomplete"
elif not all(protocol_checks.values()):
    grade = "blocked_protocol_or_resource_gate"
elif not measurement_checks["complete_spec_metrics"]:
    grade = "red_mtp_decode_length_metrics_incomplete"
elif not all_success or exit_codes["ladder_exit_code"] != 0:
    grade = "red_mtp_decode_length_ladder_revalidation_failed"
elif not all_hard_gates_pass:
    grade = "red_mtp_decode_length_ladder_revalidation_failed"
elif retries > 0:
    grade = "yellow_mtp_decode_length_ladder_revalidated_with_retry"
else:
    grade = "green_mtp_decode_length_ladder_revalidated"

grading = {
    **exit_codes,
    "protocol_checks": protocol_checks,
    "measurement_checks": measurement_checks,
    "hard_gate_failures": hard_gate_failures,
    "all_hard_gates_pass": all_hard_gates_pass,
    "planned_slots": 6,
    "completed_slots": ladder["completed_slot_count"],
    "attempt_count": ladder["attempt_count"],
    "retry_count": retries,
    "missing_spec_metrics_on_success": missing_metrics,
    "cleanup_status": cleanup,
    "grade": grade,
    "prior_4096_64_green_remains_valid": True,
    "official_baseline": False,
    "context_128k_validated": False,
    "full_p6_1_matrix_validated": False,
    "optimization_gain_validated": False,
    "next_task_authorized": False,
}
(root / "grading_inputs.json").write_text(
    json.dumps(grading, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(root / "grade.txt").write_text(grade + "\n", encoding="utf-8")
PY
~~~

分级：

- green_mtp_decode_length_ladder_revalidated：所有 protocol/measurement hard gate 通过，
  六个 slot 全部首次成功、每次成功有正 draft/draft-token 增量、cleanup clean。
- yellow_mtp_decode_length_ladder_revalidated_with_retry：所有 hard gate 通过且六个 slot
  最终成功，但至少使用一次合规重试。
- red_mtp_decode_length_metrics_incomplete：任一 attempt 的 required speculative metrics
  缺失；不得用日志替代。
- red_mtp_decode_length_ladder_revalidation_failed：slot、token、health、queue、counter、
  attempt/retry budget 或 ladder exit 任一测量门失败。
- blocked_protocol_or_resource_gate：历史 v2 审计、live metrics preflight、server ready、
  resource、overlay/hash、patch/lifecycle 任一前置门失败。
- red_cleanup_incomplete：六个 slot 即使完成，只要本任务 process group 或端口未清理干净，
  不得定为 green/yellow。

RED/blocked 时，服务器 AI 助手必须在 result_summary.md 中分析第一次与重试的错误、
对应日志窗口、metrics/gauge、server health、是否仍有 in-flight request、最可能根因
和外部开发者最小下一步；不允许自行 patch、调参或重启。

无论本轮结果如何，既有 mtp_4096_64_minimal_request_validated=true 仍有效；
official_baseline=false、context_128k_validated=false、
full_p6_1_matrix_validated=false、optimization_gain_validated=false、
next_task_authorized=false。

## 11. 小结果包与传输确认

候选外发文件只允许：

~~~text
result_summary.md
historical_lineage_audit_v2.json
live_metrics_preflight.json
overlay_import.json
ladder_summary.json
attempt_results.jsonl
runtime_log_observations.json
grading_inputs.json
first_failure_excerpt.txt       # 仅 RED/blocked，最多 120 行且最多 12KB
server_command_sha256.txt
source_payload_sha256.txt
cleanup_status.txt
~~~

候选集合必须排除 overlay、raw server log、raw_metrics/、request_errors/、NPU/端口快照、
server command 原文、patch 副本、checkpoint、request payload、generated text 和 token IDs。

result_summary.md 必须写明：task/Git/runtime/model/NPU；原 audit exit=2 偏差保留状态、
v2 lineage hard checks、live metrics preflight；overlay/base hash；唯一 lifecycle；
六个 slot 的每次 attempt、重试、request-body hash、token checks、health、counter delta；
完整 metrics 证据；cleanup、grade、claim boundary 和故障反馈。

生成 delivery_candidates.tsv 与 transfer_preflight.md，内容必须包含：

~~~text
summary_path: <绝对路径>
attachment_scope: <精确候选列表>
total_bytes: <精确值>
set_sha256: <候选 path/bytes/hash 清单 SHA-256>
sensitivity: internal_mtp_decode_length_attempt_metadata_bounded_selected_log_evidence_no_payload_generated_text_or_token_ids
available_methods: email, upload-api, server-local
recommended_method: upload-api
recommendation_reason: one_named_multi_file_session_preserves_the_exact_small_package_and_hashes
selected_method: none
transfer_status: waiting_for_user_choice
~~~

最终大小门：

~~~bash
candidates=()
for relative_path in result_summary.md historical_lineage_audit_v2.json \
  live_metrics_preflight.json overlay_import.json ladder_summary.json \
  attempt_results.jsonl runtime_log_observations.json grading_inputs.json \
  first_failure_excerpt.txt server_command_sha256.txt source_payload_sha256.txt cleanup_status.txt; do
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
~~~

当前未选择 `email`、`upload-api` 或 `server-local`。只报告 exact summary path、候选列表、
bytes、SHA-256、敏感性、available methods 和推荐方法，然后等待用户选择；不得发送
pending-confirmation 邮件，不得沿用历史选择，不得在失败后自动切换传输方法。

## 12. 完成边界

- 任一结果后停止，不得自动进入 128K context ladder、完整 P6.1、profiler 或 P8.1。
- 不提交或 push server artifact，不修改主镜像 tracked 文件、服务器专属 worktree、
  base conda environment 或 installed site-packages。
- task-local overlay 和 raw artifacts 只保留在 server_local/<task_id>/。
- green/yellow 只说明固定 4096 input 下的 MTP decode-length 稳定性，不是 benchmark、
  性能收益、官方 baseline 或 128K 验证。
