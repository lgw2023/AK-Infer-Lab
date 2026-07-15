# Developer to Server

## 当前唯一服务器动作：立即执行 P6.3B-R1 hybrid-KV 修复验证

~~~text
task_id: p6_3b_r1_deepseek_v4_flash_w8a8_mtp_prefix_cache_hybrid_kv_repair_2026_0715
execution_mode: authorized_for_execution
workload: benchmarks/deepseek_v4_flash/workloads/p6_3b_r1_hybrid_kv_repair.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
code_sync_and_task_local_runtime_patch_authorized: true
claim_boundary: hybrid_kv_mtp_prefix_cache_compatibility_repair_and_positive_hit_only
~~~

用户已明确授权本任务同步远程 `main`、使用 NPU 0-7、启动 vLLM，并在 server-local
task overlay 中加载已发布的 frozen-version compatibility patch。同步和资源/hash/source
门通过后立即执行，不再等待额外 NPU/vLLM 授权。

若资源门前唯一占卡者是服务器已知的 `npu_trigger_alive` 占卡监控 placeholder 及其 worker/forkserver
子进程，允许为本任务停止该 placeholder、记录 PID/命令和释放结果，并在本任务 cleanup 后恢复；
不得终止其他用户、模型服务或来源不明的 NPU 进程。若存在真实冲突，停止并报告。

同步只允许：

~~~bash
git fetch origin main
git merge --ff-only origin/main
~~~

不得使用 `pull-remote` alias、`server_local_git_sync.sh`、reset、restore、stash、服务器 commit
或 push。不得修改 base environment 或 site-packages；所有 compatibility 逻辑只存在于本任务
`server_local/<task_id>/.../overlay_root` 和进程内。任务结束后不得自动进入完整 P6.3B matched A/B、P6.3C、P7 或 P8。

## 1. 问题、修复边界与成功条件

原 P6.3B 已保留为 `yellow_p6_3b_prefix_cache_matched_ab_partial`：64/64 HTTP/token/MTP
正常，但 Prefix-on 24/24 measured follower 的 query 正增、hit 全为 0。R1 不重写这份负证据，
只验证 frozen vLLM/vLLM-Ascend 的 hybrid-KV + MTP compatibility repair 是否恢复真实 local APC hit。

task-local repair 同时包含：

1. frozen vLLM 写入侧：补齐 vLLM PR #44082 的 manager `use_eagle`、SWA reachable mask
   与 alignment boundary 后一个 lookahead block 的 cache target 语义；
2. frozen vLLM-Ascend coordinator：补齐 PR #11107 的同一 attention group/same-spec sibling
   `use_eagle` 传播；
3. 显式执行 `unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL`，本轮不混入 PR #11383 的 retention
   分支，不继承 shell 中未记录的 retention 值。

installed source 必须逐字节匹配：

~~~text
vllm/v1/core/single_type_kv_cache_manager.py
  53714 bytes / d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1
vllm/v1/core/kv_cache_coordinator.py
  25255 bytes / a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89
vllm_ascend/patch/platform/patch_kv_cache_coordinator.py
  23103 bytes / dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20
runtime patch
  6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
Ascend overlay patch
  cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
patched Ascend coordinator
  a1ed9c82e308608cd20965a49baa29a3e95d723248fff699fd83dfb3caf10250
existing MTP proposer patch
  75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
~~~

任一 source/hash/patch dry-run/self-test 失败都必须在启动 vLLM 前停止并分级
`blocked_p6_3b_r1_source_or_resource_gate`，不得就地改 patch、改 site-packages 或升级版本。

NPU 只运行一个 fresh lifecycle，无 warmup、无 retry。请求固定为
`32768 / 65536 / 131072 × 90% shared prefix`，每组 1 prime + 3 measured follower，
即 `3 prime + 9 measured = 12`。输出固定 64，MTP、graph、chunked prefill、Prefix Cache、
`max_num_seqs=1` 均保持开启。9/9 measured follower 都必须出现 `prefix_hits_delta > 0`；同时要求
query、MTP drafts/accepted、health/queue/counter continuity、runtime hybrid diagnostic 和 cleanup 全通过。
本轮不运行 profiler 或 HBM sampler。

candidate green 只表示 repair 恢复了该有界 workload 的真实 hit，不是 Prefix Cache matched
性能收益，也不接受 cross-run timing 对比。完整 matched A/B 需后续独立 workload/handoff。

## 2. 同步、资源门和执行

从一个 shell 执行以下合同；不要预先创建结果目录：

~~~bash
set -euo pipefail

NPU_EXECUTION_AUTHORIZED=true
NEXT_TASK_AUTHORIZED=true
test "${NPU_EXECUTION_AUTHORIZED}" = true
test "${NEXT_TASK_AUTHORIZED}" = true

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_3b_r1_deepseek_v4_flash_w8a8_mtp_prefix_cache_hybrid_kv_repair_2026_0715
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
PYTHON_BIN="${ENV_PREFIX}/bin/python"
WORKLOAD_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_3b_r1_hybrid_kv_repair.yaml"
RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_r1_hybrid_kv_repair.py"
MODE_RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_r1_mode.sh"
PAYLOAD_PATH="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json"

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F "npu_execution_authorized: true" "${WORKLOAD_PATH}"
grep -F "next_task_authorized: true" "${WORKLOAD_PATH}"
test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"/{modes,runtime}

test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/source_payload_sha256.txt"

npu-smi info > "${RESULT_DIR}/npu_smi_before.txt" 2>&1
"${PYTHON_BIN}" - "${RESULT_DIR}/npu_smi_before.txt" "${RESULT_DIR}/resource_gate.json" <<'PY'
import json
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
health = {
    int(match.group(1)): match.group(2)
    for match in re.finditer(
        r"^\|\s*([0-7])\s+910B1\s+\|\s*(OK)\s+\|", text, re.MULTILINE
    )
}
idle = {int(value) for value in re.findall(r"No running processes found in NPU ([0-7])", text)}
result = {
    "health": health,
    "idle_devices": sorted(idle),
    "all_eight_healthy": health == {index: "OK" for index in range(8)},
    "all_eight_idle": idle == set(range(8)),
}
result["pass"] = result["all_eight_healthy"] and result["all_eight_idle"]
Path(sys.argv[2]).write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
raise SystemExit(0 if result["pass"] else 2)
PY
if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
  printf '%s\n' blocked_port_7000 > "${RESULT_DIR}/first_failure_excerpt.txt"
  exit 2
fi

"${PYTHON_BIN}" "${RUNNER_PATH}" prepare \
  --source-payload "${PAYLOAD_PATH}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name deepseek-v4-flash-w8a8-mtp

printf '%s\n' 1 > "${RESULT_DIR}/server_lifecycle_count.txt"
set +e
bash "${MODE_RUNNER_PATH}" "${RESULT_DIR}"
mode_exit=$?
set -e
printf '%s\n' "${mode_exit}" > "${RESULT_DIR}/mode_exit_code.txt"

set +e
"${PYTHON_BIN}" "${RUNNER_PATH}" finalize --artifact-dir "${RESULT_DIR}"
finalize_exit=$?
set -e
printf '%s\n' "${finalize_exit}" > "${RESULT_DIR}/finalize_exit_code.txt"

git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_after.txt"
test ! -s "${RESULT_DIR}/tracked_status_after.txt"
npu-smi info > "${RESULT_DIR}/npu_smi_after.txt" 2>&1 || true
if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
  printf '%s\n' incomplete > "${RESULT_DIR}/cleanup_status.txt"
fi

"${PYTHON_BIN}" - "${RESULT_DIR}" "${REPO_ROOT}" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

result_dir = Path(sys.argv[1])
repo = Path(sys.argv[2])
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
files = {
    "workload": repo / "benchmarks/deepseek_v4_flash/workloads/p6_3b_r1_hybrid_kv_repair.yaml",
    "runtime_patch": repo / "tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py",
    "ascend_patch": repo / "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch",
    "runner": repo / "tools/inference_contracts/run_deepseek_p6_3b_r1_hybrid_kv_repair.py",
    "mode_runner": repo / "tools/inference_contracts/run_deepseek_p6_3b_r1_mode.sh",
}
evidence = {
    "head": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
    "origin_main": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "origin/main"], text=True).strip(),
    "tracked_clean": not (result_dir / "tracked_status_after.txt").read_text().strip(),
    "files": {name: {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)} for name, path in files.items()},
}
(result_dir / "environment_and_hashes.json").write_text(
    json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

exit "${finalize_exit}"
~~~

`run_deepseek_p6_3b_r1_mode.sh` 内部会设置
`P6_3B_R1_ENABLE_HYBRID_KV_PATCH=1`，先做 source hash、patch dry-run/apply 和无 NPU
self-test，再启动唯一 vLLM lifecycle。禁止直接绕过该 runner 手写一套 server command。

## 3. 分级、停止和允许的 server-local 适配

- source/hash/resource/patch/self-test 在 server 启动前失败：
  `blocked_p6_3b_r1_source_or_resource_gate`；停止，不自行修补。
- server 启动但没有成功请求：`red_p6_3b_r1_hybrid_kv_repair_no_success`。
- 12 行齐全但 9 measured hit 仍全部为 0：`red_p6_3b_r1_hybrid_kv_zero_hit_persists`。
- 至少一个 measured positive hit，但 9/9、请求结构或证据不全：
  `yellow_p6_3b_r1_hybrid_kv_repair_partial`。
- 请求/hit 完整但 runtime diagnostic、MTP、health/queue/counter 不全：
  `red_p6_3b_r1_hybrid_kv_evidence_incomplete`。
- 3/3 prime、9/9 measured 全部首次成功且每个 measured hit 正增，source/patch/hybrid
  diagnostic、MTP、health/queue/counter、cleanup 全过：
  `candidate_green_p6_3b_r1_hybrid_kv_repair`。

允许直接处理 server-local mkdir/path、shell quoting、`set -u` source 兼容、真实输出 parser、
等价 runner error reporting，以及前述已知 NPU placeholder 的停/恢复；必须逐项报告。不得修改 tracked
文件、base environment/site-packages、runtime/model、patch 内容、request body/group/order/repeat、server
参数、retention、指标定义。禁止 retry、restart、第二 patch、版本升级、eager fallback、关闭 MTP/chunked
prefill/graph、降 context 或自动扩展完整 matched A/B。

失败不撤销 P6.1C-R1、P6.1、P6.2、P6.3A green，也不撤销原 P6.3B yellow 负证据。

## 4. 回报与传输门

raw server log、metrics、hybrid diagnostic JSONL、request bodies、prompt/token IDs 和 token arrival
留服务器。完成后先在当前会话报告：

1. HEAD/origin、tracked 状态、资源/source/hash/patch/self-test 门；
2. lifecycle PID/ready/exit/cleanup，任何 server-local 适配；
3. 三组逐组 prime/measured、query/hit/observed ratio、MTP accepted；
4. diagnostic 中实际 KV group/spec/manager、LCM/effective block、eagle group、manager flag、
   lookahead cache target 与 retention unset 证据；
5. server grade、claim boundary、raw result root；
6. 精确 `result_summary.md` 路径和以下完整候选清单的逐文件 bytes/SHA-256/sensitivity/总 bytes：
   `result_summary.md`、`environment_and_hashes.json`、`request_body_manifest.json`、
   `group_summary.tsv`、`grading_inputs.json`、`hybrid_kv_diagnostic_summary.json`、
   `cleanup_status.txt`、`first_failure_excerpt.txt`；
7. `email / upload-api / server-local` 三种可用方法及一个推荐方法和理由。

候选总和必须不超过 71680 bytes，不得包含 generated text 或 token IDs。不得发送 email，
不得调用 upload-api，不得自动选择 server-local；等待用户对该完整范围重新选择唯一传输方法，
过去选择不继承，失败后不得自动切换方法。
