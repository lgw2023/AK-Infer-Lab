# Developer to Server

## 当前唯一服务器动作：P8.2-K1A SimpleCPUOffload 八卡 store→pressure→restore 机制闭环

~~~text
task_id: p8_2_k1a_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0717
execution_mode: authorized_simple_cpu_offload_single_lifecycle_six_request_mechanism
server_sync_review_authorized: true
installed_source_and_import_probe_authorized: true
temporary_audit_workspace_authorized: true
npu_execution_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
keep_alive_stop_and_restore_authorized: true
task_local_observer_authorized: true
task_local_compatibility_patch_authorized: false
result_directory_creation_authorized: true
result_transfer_authorized: false
next_task_authorized: false
lifecycle_count_exact: 1
request_count_exact: 6
request_retry_count_exact: 0
profiler_authorized: false
hbm_sampler_authorized: false
runtime_or_dependency_upgrade_authorized: false
no_k2_k3_k4_p8_3_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

本任务不重跑 P6、P8.1-R1 或 P8.2-K0，也不修复已 blocked 的
`OffloadingConnector + NPUOffloadingSpec` 路径。开发机已接受原 K1 只读复核结论
`blocked_p8_2_k1_frozen_stack_import_incompatible`：该路径的 legacy import 和 single-group
假设与已接受的 `CompressAttentionManager + SlidingWindowManager` hybrid 双 group 冲突，继续保留，
不得偷渡成 task-local compatibility patch。

K1A 是同一冻结栈内的独立候选路径：

```text
SimpleCPUOffloadConnector
  -> AscendSimpleCPUOffloadConnector
  -> SimpleCPUOffloadNPUWorker
  -> NPUDmaCopyBackend
  -> torch.ops._C_ascend.swap_blocks_batch
```

精确 Git object 审计已证明该路径在
vLLM=`0decac0d96c42b49572498019f0a0e3600f50398` /
vLLM-Ascend=`5f6faa0cb8830f667266f3b8121cd1383606f2a1`
中存在 Ascend override、`SupportsHMA`、`request_finished_all_groups`、
`FullAttentionSpec + SlidingWindowSpec + MambaSpec` 与 NPU D2H/H2D backend；但这些只是
`conditional_p8_2_k1a_simple_cpu_offload_source_candidate`，不是 DeepSeek TP8+EP+MTP 的
runtime green。服务器必须先完成零 NPU source/import/registration/host-memory 门，然后才可以
停 keep-alive 并执行一次有界 lifecycle。

保留且不撤销的 lineage：DeepSeek R2 hybrid-KV repair；P6.3B-R4-R1=
`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`；P6.3C=
`blocked_p6_3c_not_strict_single_variable`；P8.1 parent=
`yellow_p8_1_matrix_trace_invalid`；P8.1-R1=
`green_p8_1_r1_official_mtp_observe_only_matrix`；P8.2-K0 green；
P8.2-K1 frozen path blocked。K1A 任何 blocked/red/yellow 都不撤销这些结论。
P8.1-R1 对 parent 缺完整 R2 repair 的诊断仍是 `cause_proven_as_unique: false`，K1A 不扩大该因果结论。

本轮 32K restore/repeat 组的冻结 hybrid prefix 期望命中为 `16384` tokens；它只用于逐请求
结构门，不把 Prefix Cache 命中等同于 H2D restore。H2D 必须由 scheduler load 与八个 worker
copy-submit/copy-complete trace 独立证明。

## 1. 同步、tracked-clean 与仓库合同门（零 NPU）

从服务器自己的干净 `main` 普通快进同步。不得 reset、stash、rebase、用 checkout 覆盖、
运行 `sync.sh`、在服务器 commit/push，或删除既有未跟踪运行产物。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

git status --short --branch --untracked-files=no
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"

python3 - <<'PY'
from pathlib import Path
import hashlib

expected = {
    "benchmarks/deepseek_v4_flash/p8_2_k1a_simple_cpu_offload_feasibility_audit.yaml": "51fe967ff093678fdf7f4f208b09288c4ea020062b954d04c32a5925dfa7ba16",
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_simple_cpu_offload_store_restore.yaml": "4a77f74e1cb841eea865f879a637dbd447ef5d86639f7217c5776f5f62d22979",
    "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py": "0a97dfce48678be8d7f3ea1a53f859e5a71e9df155f2a53606ff238c377a41bd",
    "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "b31d212378c8aaed87c872c67a29b8d2ea039fbd7e97e5f7e6c54b29ef99a680",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "1059bd55b33463f57dec1d7779104801050df4ec96ad60c33cfb42ee4ec808fc",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "d9e7f795f63c82e4fc3a39b7fe83f644de4d4260917d63fad9af71da6e1d57a9",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh": "e65c8a11d060579563998667877e67915722b1ab09176ab46ea40514da498670",
    "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch": "5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6",
    "tests/inference_contracts/test_deepseek_p8_2_k1a_simple_cpu_offload_feasibility.py": "ad775079c9998635eae502346c439d4e4a2024370fbc45bdccad080291398a56",
}
for relative, wanted in expected.items():
    got = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
    if got != wanted:
        raise SystemExit(f"frozen repo hash mismatch: {relative} {got} != {wanted}")
print("frozen_repo_hash_gate=pass")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_simple_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1_kv_cache_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k0_order_balanced_prefix_baseline.py -q
python3 -m py_compile \
  tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
P8_2_K1A_AUDIT_ONLY=1 bash \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh /tmp/not-created \
  | grep -F 'request_count=6'
P8_2_K1A_MODE_AUDIT_ONLY=1 bash \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh /tmp/not-created \
  | grep -F 'observer_mode=observe_only_no_decision_or_copy_mutation'
test ! -e /tmp/not-created
test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节任一失败，给 `blocked_p8_2_k1a_source_or_contract_gate`，立即停止；不得停 keep-alive、
不得启动 vLLM/NPU、不得创建项目结果目录。

## 2. 冻结安装态 source/import/registration 复核（零 NPU）

本节只允许在 `/tmp/opencode/p8_2_k1a_preflight_2026_0717` 写 bounded JSON。使用服务器
editable vLLM checkout 和安装态 vLLM-Ascend；不得换版本、pip install、修源码、加 shim，
或把 `NPUOffloadingSpec` 的旧 K1 修复混入 K1A。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TMP_AUDIT=/tmp/opencode/p8_2_k1a_preflight_2026_0717
RUNTIME_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
RUNTIME_PYTHON="${RUNTIME_PREFIX}/bin/python"
VLLM_ROOT=/data/node0_disk1/vllm-0.22.1
VLLM_ASCEND_ROOT="${RUNTIME_PREFIX}/lib/python3.11/site-packages"
AUDITOR="${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py"

test ! -e "${TMP_AUDIT}"
mkdir -p "${TMP_AUDIT}"
test -x "${RUNTIME_PYTHON}"
test "$(git -C "${VLLM_ROOT}" rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398
test -z "$(git -C "${VLLM_ROOT}" status --porcelain --untracked-files=no)"

python3 "${AUDITOR}" installed-source-audit \
  --vllm-root "${VLLM_ROOT}" \
  --vllm-ascend-root "${VLLM_ASCEND_ROOT}" \
  --output "${TMP_AUDIT}/installed_source_audit.json"
python3 "${AUDITOR}" runtime-import-probe \
  --runtime-python "${RUNTIME_PYTHON}" \
  --output "${TMP_AUDIT}/runtime_import_probe.json"

python3 - "${TMP_AUDIT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
source = json.loads((root / "installed_source_audit.json").read_text())
runtime = json.loads((root / "runtime_import_probe.json").read_text())
assert source["audit_grade"] == "conditional_p8_2_k1a_simple_cpu_offload_source_candidate"
assert source["source_hash_gate"] is True
assert len(source["source_inventory"]) == 9
assert source["ascend_connector_override_present"] is True
assert source["supports_hma_present"] is True
assert source["hybrid_multi_group_source_support_present"] is True
assert source["npu_d2h_h2d_backend_present"] is True

assert runtime["subprocess_exit"] == 0
probe = runtime["probe"]
assert probe is not None and "probe_error" not in probe
assert probe["kv_transfer_config"] == {
    "kv_connector": "SimpleCPUOffloadConnector",
    "kv_role": "kv_both",
    "kv_connector_extra_config": {
        "cpu_bytes_to_use": 274877906944,
        "cpu_bytes_to_use_per_rank": 34359738368,
        "lazy_offload": False,
    },
}
assert probe["registry_module"] == (
    "vllm_ascend.distributed.kv_transfer.kv_pool."
    "simple_cpu_offload.simple_cpu_offload_connector"
)
assert probe["registry_class"] == "AscendSimpleCPUOffloadConnector"
assert probe["connector_import"] == "success"
assert probe["worker_import"] == "success"
assert probe["copy_backend_import"] == "success"
assert probe["ascend_connector_inherits_upstream"] is True
assert probe["npu_started"] is False
assert probe["vllm_server_started"] is False
assert probe["model_request_sent"] is False
print("installed_source_import_registration_gate=pass")
PY
~~~

若 exact installed hash、registry override、class import/inheritance 或 `KVTransferConfig` 任一漂移，给
`blocked_p8_2_k1a_runtime_source_or_registration_drift`并停止；不得修环境、retry 或占用 NPU。

## 3. 零扰动资源门与 host-memory 预算

先只读记录 keep-alive PID/PGID、NPU 0–7、端口 7000、vLLM 进程、model path 和
`/proc/meminfo`。`MemAvailable` 必须不小于 `412316860416` bytes（配置 256 GiB CPU tier +
128 GiB margin），且 swap used 必须为 0。这一节仍不得停 keep-alive。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TMP_AUDIT=/tmp/opencode/p8_2_k1a_preflight_2026_0717
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp

ps -eo pid,ppid,pgid,stat,cmd | grep -E 'npu_keep_alive|#0#|#1#|#2#|#3#|#4#|#5#|#6#|#7#' \
  > "${TMP_AUDIT}/keep_alive_before.txt" || true
npu-smi info > "${TMP_AUDIT}/npu_before.txt"
ss -ltnp | grep ':7000' > "${TMP_AUDIT}/port_7000_before.txt" || true
ps -eo pid,ppid,pgid,stat,cmd | grep -E '[v]llm|[V]LLM' > "${TMP_AUDIT}/vllm_before.txt" || true
cat /proc/meminfo > "${TMP_AUDIT}/meminfo_before.txt"
test ! -s "${TMP_AUDIT}/port_7000_before.txt"
test ! -s "${TMP_AUDIT}/vllm_before.txt"
test -d "${MODEL_PATH}"
test "$(find "${MODEL_PATH}" -maxdepth 1 -type f | wc -l)" -gt 0

python3 - "${TMP_AUDIT}/meminfo_before.txt" <<'PY'
from pathlib import Path
import sys

values = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    key, raw = line.split(":", 1)
    values[key] = int(raw.strip().split()[0]) * 1024
assert values["MemAvailable"] >= 412316860416, values["MemAvailable"]
assert values["SwapTotal"] == values["SwapFree"]
print(f"mem_available_bytes={values['MemAvailable']}")
print("host_memory_gate=pass")
PY

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
~~~

本节任一失败，给 `blocked_p8_2_k1a_source_or_resource_gate`并停止。不得为过门降低
CPU tier、减少 context、改 graph/MTP/Prefix/Chunked Prefill/R2 repair，或启用 swap。

## 4. 唯一 NPU lifecycle：安全退 keep-alive、六请求、清理并恢复

只有前三节全 green 才执行。下面是一个整体命令块：先从 marker 反查 keep-alive PGID，
仅对这些 PGID 发 `SIGTERM`；不得触碰无关进程。一旦开始退 keep-alive，不论 runner
成功或失败，trap 都必须用用户指定的官方脚本恢复 0–7 卡。
官方恢复命令的精确形状为 `bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7`。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TMP_AUDIT=/tmp/opencode/p8_2_k1a_preflight_2026_0717
RESULT_DIR="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0717_run01"
RUNNER="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh"
KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
KEEP_ALIVE_STOPPED=0
RESTORE_EXIT=not_run
MARKER_COUNT_BEFORE=0

restore_keep_alive() {
  if test "${KEEP_ALIVE_STOPPED}" -eq 1; then
    if bash "${KEEP_ALIVE_SCRIPT}" 0 1 2 3 4 5 6 7 \
      > "${TMP_AUDIT}/keep_alive_restore_stdout.txt" \
      2> "${TMP_AUDIT}/keep_alive_restore_stderr.txt"; then
      RESTORE_EXIT=0
    else
      RESTORE_EXIT=$?
    fi
    printf '%s\n' "${RESTORE_EXIT}" > "${TMP_AUDIT}/keep_alive_restore_exit_code.txt"
    sleep 5
    return "${RESTORE_EXIT}"
  fi
}
trap restore_keep_alive EXIT

test ! -e "${RESULT_DIR}"
test -f "${KEEP_ALIVE_SCRIPT}"

ps -eo pid=,ppid=,pgid=,stat=,args= \
  | awk '$0 ~ /#[0-7]#/' \
  > "${TMP_AUDIT}/keep_alive_markers_before.txt"
MARKER_COUNT_BEFORE=$(wc -l < "${TMP_AUDIT}/keep_alive_markers_before.txt" | tr -d ' ')
test "${MARKER_COUNT_BEFORE}" -ge 8
python3 - "${TMP_AUDIT}/keep_alive_markers_before.txt" <<'PY'
from pathlib import Path
import sys

rows = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
assert all(any(f"#{device}#" in row for row in rows) for device in range(8))
PY

mapfile -t KEEP_ALIVE_PGIDS < <(
  awk '{print $3}' "${TMP_AUDIT}/keep_alive_markers_before.txt" | sort -n -u
)
test "${#KEEP_ALIVE_PGIDS[@]}" -ge 1
CURRENT_PGID=$(ps -o pgid= -p $$ | tr -d ' ')
printf '%s\n' "${KEEP_ALIVE_PGIDS[@]}" > "${TMP_AUDIT}/keep_alive_pgids.txt"
for pgid in "${KEEP_ALIVE_PGIDS[@]}"; do
  test "${pgid}" != "${CURRENT_PGID}"
  test "${pgid}" -gt 1
  kill -TERM -- "-${pgid}"
done
KEEP_ALIVE_STOPPED=1

for _ in $(seq 1 30); do
  survivors=0
  while read -r pgid; do
    if ps -eo pgid= | awk -v wanted="${pgid}" '$1 == wanted {found=1} END {exit !found}'; then
      survivors=$((survivors + 1))
    fi
  done < "${TMP_AUDIT}/keep_alive_pgids.txt"
  test "${survivors}" -eq 0 && break
  sleep 2
done
test "${survivors}" -eq 0
npu-smi info > "${TMP_AUDIT}/npu_after_keep_alive_stop.txt"
ss -ltnp | grep ':7000' > "${TMP_AUDIT}/port_7000_after_keep_alive_stop.txt" || true
test ! -s "${TMP_AUDIT}/port_7000_after_keep_alive_stop.txt"

set +e
bash "${RUNNER}" "${RESULT_DIR}" \
  > "${TMP_AUDIT}/runner_stdout.txt" 2> "${TMP_AUDIT}/runner_stderr.txt"
RUNNER_EXIT=$?
set -e
printf '%s\n' "${RUNNER_EXIT}" > "${TMP_AUDIT}/runner_exit_code.txt"

if restore_keep_alive; then
  RESTORE_EXIT=0
else
  RESTORE_EXIT=$?
fi
KEEP_ALIVE_STOPPED=0
trap - EXIT
test "${RESTORE_EXIT}" -eq 0

MARKER_COUNT_AFTER=0
for _ in $(seq 1 30); do
  ps -eo pid=,ppid=,pgid=,stat=,args= \
    | awk '$0 ~ /#[0-7]#/' \
    > "${TMP_AUDIT}/keep_alive_after.txt"
  MARKER_COUNT_AFTER=$(wc -l < "${TMP_AUDIT}/keep_alive_after.txt" | tr -d ' ')
  test "${MARKER_COUNT_AFTER}" -eq "${MARKER_COUNT_BEFORE}" && break
  sleep 2
done
test "${MARKER_COUNT_AFTER}" -eq "${MARKER_COUNT_BEFORE}"
python3 - "${TMP_AUDIT}/keep_alive_after.txt" <<'PY'
from pathlib import Path
import sys

rows = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
assert all(any(f"#{device}#" in row for row in rows) for device in range(8))
PY
printf 'true\n' > "${TMP_AUDIT}/keep_alive_restored_exact.txt"
npu-smi info > "${TMP_AUDIT}/npu_after.txt"
ss -ltnp | grep ':7000' > "${TMP_AUDIT}/port_7000_after.txt" || true
ps -eo pid,ppid,pgid,stat,cmd | grep -E '[v]llm|[V]LLM' > "${TMP_AUDIT}/vllm_after.txt" || true
test ! -s "${TMP_AUDIT}/port_7000_after.txt"
test ! -s "${TMP_AUDIT}/vllm_after.txt"
test "$(cat "${TMP_AUDIT}/keep_alive_restored_exact.txt")" = true
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
printf 'runner_exit=%s\n' "${RUNNER_EXIT}"
~~~

runner 内部固定且只能执行：

```text
lifecycle_01
  1. warmup             4096+64
  2. prime             32768+64
  3. pressure         131072+64
  4. restore_follower  32768+64
  5. repeat_follower   32768+64
  6. isolated_control  32768+64
```

所有请求 `concurrency=1 / temperature=0 / ignore_eos=true / min_tokens=max_tokens=64 /
streaming=true`；body 在服务启动前冻结 token count/bytes/SHA-256。prime、restore follower、
repeat follower 共享同一 90% token prefix，其余请求与 primary 的 LCP `<128`。不保存或外发
generated text/token IDs。

runtime 固定 W8A8、TP8+EP、MTP `num_speculative_tokens=1`、`FULL_DECODE_ONLY`、
`max_model_len=135168`、`max_num_batched_tokens=4096`、`max_num_seqs=1`、block size=128、
Chunked Prefill on、Prefix Cache on、完整 R2 hybrid repair。唯一新机制配置是：

```json
{
  "kv_connector": "SimpleCPUOffloadConnector",
  "kv_role": "kv_both",
  "kv_connector_extra_config": {
    "cpu_bytes_to_use": 274877906944,
    "cpu_bytes_to_use_per_rank": 34359738368,
    "lazy_offload": false
  }
}
```

task-local observer 只记录 scheduler CPU hit/load/store event 和每 worker copy direction/block/bytes/event
completion 水位；不改 scheduler 返回值、block list、copy direction/bytes、stream 或同步语义。
不得 retry，不得发第 7 个请求，不得为了触发 restore 而增加 pressure、降低 context、
改 CPU tier、修 runtime 或执行 reset-prefix-cache。

## 5. 分级、首错与停止边界

- source/hash/import/registration/host-memory/port/model/NPU 资源门失败：
  `blocked_p8_2_k1a_source_or_resource_gate`。
- vLLM 启动后 6 个请求一个都未成功：`red_p8_2_k1a_simple_cpu_offload_no_success`。
- 只有部分请求/结构成功：`yellow_p8_2_k1a_simple_cpu_offload_partial`。
- 6/6 请求成功，8/8 worker D2H store 完整，但冻结 pressure 后无 8/8 H2D restore：
  `yellow_p8_2_k1a_store_only_no_restore`。这是有效负结果，不得 retry 或临时改序列。
- 6/6 请求成功但 request/repair/resolved config/trace/cleanup 任一证据不完整：
  `red_p8_2_k1a_transfer_evidence_incomplete`。
- 只有 6/6 首次成功、resolved connector 精确、R2/MTP/health/queue 完整、每个方向均
  8/8 worker 正 bytes 且 completion、restore follower 有 CPU hit/load schedule/load complete、cleanup clean、
  `keep_alive_restored_exact=true`
  时，才给 `candidate_green_p8_2_k1a_simple_cpu_offload_store_restore`。

服务器 candidate green 不是项目 green；必须由开发机独立复核小结果包后才能接受。
任何 timing 都只是这一 lifecycle 的 diagnostic，不得宣称 speedup、capacity gain、普遍 Ascend
offload 支持或 hardware bottleneck。不得进入 K2/K3/K4/P8.3/P9。

## 6. bounded 候选结果、灵敏度与禁止自动外发

raw vLLM log、metrics `.prom`、request bodies、逐 PID trace、model output/token IDs 留服务器。
仅下列候选可进入小结果清单，总量不得超过 `71680 bytes`：

```text
result_summary.md
environment_and_hashes.json
request_body_manifest.json
request_summary.tsv
transfer_trace_summary.json
connector_resolution_summary.json
mtp_queue_health_summary.json
host_memory_summary.json
repair_diagnostic_summary.json
grading_inputs.json
cleanup_status.txt
first_failure_excerpt.txt
```

运行后在服务器原位生成清单：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0717_run01"

python3 - "${RESULT_DIR}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
names = [
    "result_summary.md",
    "environment_and_hashes.json",
    "request_body_manifest.json",
    "request_summary.tsv",
    "transfer_trace_summary.json",
    "connector_resolution_summary.json",
    "mtp_queue_health_summary.json",
    "host_memory_summary.json",
    "repair_diagnostic_summary.json",
    "grading_inputs.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
]
inventory = []
for name in names:
    path = root / name
    if not path.is_file():
        continue
    payload = path.read_bytes()
    inventory.append({
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
    })
total = sum(item["bytes"] for item in inventory)
assert total <= 71680, total
print(json.dumps({
    "result_summary_path": str(root / "result_summary.md"),
    "candidate_file_count": len(inventory),
    "candidate_total_bytes": total,
    "candidates": inventory,
    "available_methods": ["email", "upload-api", "server-local"],
    "recommended_method": "server-local",
    "recommendation_reason": "developer should first review mechanism and grading metadata in place before choosing any transfer",
}, indent=2, sort_keys=True))
PY
~~~

完成回报必须包含：HEAD/origin/main/tracked-clean；section 1–3 门；runner exit 与 server
grade；6 个 slot 逐请求成功/token/MTP/Prefix 摘要；`d2h_store_complete`、`h2d_restore_complete`、
8-worker 覆盖、两方向 bytes；host memory 前后；cleanup、端口、vLLM residual、keep-alive 恢复；
RESULT_DIR 与完整候选清单。

`result_transfer_authorized:false`：不得自动外发，不 email、不 upload-api、不复制到其他服务。
先报告上述精确范围，等用户对该完整范围重新选择 `email / upload-api / server-local`
之一。完成后保持等待；不得自动进入任何下一任务。
