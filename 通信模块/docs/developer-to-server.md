# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R1 allocator envelope + P8.3-I0 checkpoint inventory

~~~text
task_id: p8_dual_track_k1a_r1_allocator_and_p8_3_i0_inventory_2026_0717
execution_mode: authorized_checkpoint_inventory_geometry_only_lifecycle_and_bounded_pinned_envelope
server_sync_review_authorized: true
temporary_audit_workspace_authorized: true
result_directory_creation_authorized: true
p8_3_i0_checkpoint_inventory_authorized: true
checkpoint_full_sha256_authorized: true
keep_alive_stop_and_restore_authorized: true
geometry_probe_npu_execution_authorized: true
geometry_probe_vllm_start_authorized: true
geometry_probe_lifecycle_count_exact: 1
formal_model_lifecycle_count_exact: 0
model_request_count_exact: 0
pinned_allocator_probe_authorized: true
pinned_allocator_wave_count_max: 4
pinned_allocator_world_size_exact: 8
npu_execution_authorized: true
vllm_formal_workload_authorized: false
model_requests_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
runtime_or_dependency_mutation_authorized: false
result_transfer_authorized: false
next_task_authorized: false
standing_npu_and_vllm_consumption_authorization: true
~~~

本任务替换已消费的 K1A 32 GiB/rank 六请求 handoff，不得重跑旧任务。开发机已接受
`red_p8_2_k1a_simple_cpu_offload_no_success`，但边界只是：冻结 32 GiB/rank 配置在服务就绪前以
`aclrtMallocHostWithCfg / 207001` 失败，0/6 请求。`/proc/meminfo` 的 1.49 TiB available 不是
pinned allocator 可用量证据；当前也没有证明唯一 pool/per-allocation/concurrency/fragmentation
根因，更没有证明 `SimpleCPUOffloadConnector` 全局不支持。

本任务有两个彼此独立的 section：

1. `P8.3-I0`：只读 checkpoint index/header 和 full shard SHA-256，不占 NPU，生成 expert inventory
   与 TP4 planning budget。它不证明 TP4 runtime ownership、materialized bytes、hotness 或 offload。
2. `P8.2-K1A-R1`：一次 geometry-only 八卡初始化在任何 pinned CPU mirror allocation 前记录 exact
   per-tensor/total bytes per KV block，然后清理 vLLM；再用八个并发、可清理进程执行最多
   `32/64/96/128` CPU-block shaped pinned allocation waves。128 blocks 对应冻结 16K（`16384`）restore/
   128-token block 的最低 retention 需求。

即使 128-block wave 八 rank 全过，本任务也只能给
`candidate_ready_p8_2_k1a_r1_allocator_capacity`，绝对不得启动正式六请求 K1A lifecycle。
必须把 geometry/envelope 小结果交回开发机独立复核，再由新 handoff 冻结唯一候选容量。
K2、P8.3-I1、P8.4、P8.5、P9 均禁止自动进入。

保留 lineage：DeepSeek R2 hybrid-KV 修复下 P6.3B-R4-R1 保持
`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`；P6.3C 保持
`blocked_p6_3c_not_strict_single_variable`；P8.1 parent 保持 `yellow_p8_1_matrix_trace_invalid`，
P8.1-R1 保持 `green_p8_1_r1_official_mtp_observe_only_matrix`；P8.2-K0 保持
`green_p8_2_k0_order_balanced_prefix_cache_baseline`；legacy K1
`OffloadingConnector + NPUOffloadingSpec` 保持 `blocked_p8_2_k1_frozen_stack_import_incompatible`；
K1A 32 GiB/rank 保持 `red_p8_2_k1a_simple_cpu_offload_no_success`。本任务的任何结果不撤销它们。

## 1. 同步与冻结仓库门（零 NPU）

从服务器自己的干净 `main` 普通快进。不得 reset/stash/rebase/checkout 覆盖、运行
`sync.sh`、在服务器 commit/push，或删除既有未跟踪运行产物。

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
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r1_allocator_feasibility_audit.yaml": "c424c5019630472e08315c35fa7337ea7a9ce0845c6a5f343c17af49d15e25e2",
    "benchmarks/deepseek_v4_flash/p8_3_i0_checkpoint_inventory_contract.yaml": "1d5fd96e90dd6449b61b4cb754795b8b8138ba600833d56e29bfb06b6ff1c56e",
    "tools/inference_contracts/p8_2_k1a_r1_allocator.py": "166c61b207950aa1c283eac6111619e5b619a0775ce267e74325c4a7d6563ef0",
    "tools/inference_contracts/p8_2_k1a_r1_geometry_observer.py": "24fb72d1ed74b3ebbbdd19e19486e6b9de9d03fc0994a12b242056235a515854",
    "tools/inference_contracts/probe_deepseek_p8_2_k1a_r1_pinned_allocator.py": "8ae11b8183c829367ef6ac900fa92eb5c8d9db399c72dc1952dc477ecc29f13c",
    "tools/inference_contracts/inventory_deepseek_p8_3_i0_checkpoint.py": "50d9120d8740ff23e20e9354c2ea7c54d3372090ccd78a30202ad842982d6b00",
    "tests/inference_contracts/test_deepseek_p8_2_k1a_r1_allocator_envelope.py": "87450ee40e7492a97e48ff9b636f306cfc5aff8e03d7354f245ba72023a7c203",
    "tests/inference_contracts/test_deepseek_p8_3_i0_checkpoint_inventory.py": "eeebb2574fab432479a2f46f21827f80bc4c7c89ee05de1018ebb13094213994",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh": "e65c8a11d060579563998667877e67915722b1ab09176ab46ea40514da498670",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "d9e7f795f63c82e4fc3a39b7fe83f644de4d4260917d63fad9af71da6e1d57a9",
    "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch": "5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6",
}
for relative, wanted in expected.items():
    got = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
    if got != wanted:
        raise SystemExit(f"frozen repo hash mismatch: {relative} {got} != {wanted}")
print("frozen_repo_hash_gate=pass")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r1_allocator_envelope.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_simple_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1_kv_cache_cpu_offload_feasibility.py -q
python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_r1_allocator.py \
  tools/inference_contracts/p8_2_k1a_r1_geometry_observer.py \
  tools/inference_contracts/probe_deepseek_p8_2_k1a_r1_pinned_allocator.py \
  tools/inference_contracts/inventory_deepseek_p8_3_i0_checkpoint.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节任一 hash、K1/K1A-R1 合同、compile 或 tracked-clean 失败，给
`blocked_p8_dual_track_repository_contract_gate`，两个 section 都停止；不得占 NPU。

P8.3-I0 的 Parquet test 需 `pyarrow + safetensors + numpy + PyYAML`。在本节先只做 compile；
第 2 节会从现有解释器中选一个已安装依赖的运行。不得 pip/conda install。

## 2. P8.3-I0 checkpoint-first inventory（零 NPU，keep-alive 保持不动）

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
RESULT_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r1_allocator_and_p8_3_i0_inventory_2026_0717_run01
I0_RESULT=${RESULT_ROOT}/p8_3_i0_checkpoint_inventory
RUNTIME_PYTHON=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
cd "${REPO_ROOT}"

test ! -e "${RESULT_ROOT}"
mkdir -p "${RESULT_ROOT}"
test -f "${MODEL_PATH}/model.safetensors.index.json"

I0_PYTHON=
for candidate in "${RUNTIME_PYTHON}" python3; do
  if test -x "$(command -v "${candidate}" 2>/dev/null || true)" && \
     "${candidate}" -c 'import numpy, pyarrow, safetensors, yaml' >/dev/null 2>&1; then
    I0_PYTHON=${candidate}
    break
  fi
done

if test -z "${I0_PYTHON}"; then
  printf '%s\n' blocked_p8_3_i0_existing_dependency_gate > "${RESULT_ROOT}/p8_3_i0_grade.txt"
  printf '%s\n' 'No existing interpreter imports numpy, pyarrow, safetensors and yaml; no install authorized.' \
    > "${RESULT_ROOT}/p8_3_i0_first_failure.txt"
else
  set +e
  "${I0_PYTHON}" -m pytest \
    tests/inference_contracts/test_deepseek_p8_3_i0_checkpoint_inventory.py -q \
    > "${RESULT_ROOT}/p8_3_i0_contract_test.txt" 2>&1
  i0_contract_exit=$?
  set -e
  printf '%s\n' "${i0_contract_exit}" > "${RESULT_ROOT}/p8_3_i0_contract_exit_code.txt"
  if test "${i0_contract_exit}" -ne 0; then
    printf '%s\n' blocked_p8_3_i0_local_contract_gate > "${RESULT_ROOT}/p8_3_i0_grade.txt"
  else
    set +e
    "${I0_PYTHON}" tools/inference_contracts/inventory_deepseek_p8_3_i0_checkpoint.py \
      --model-dir "${MODEL_PATH}" \
      --output-dir "${I0_RESULT}" \
      --tp-size 4 \
      --shard-hash-mode full
    i0_exit=$?
    set -e
    printf '%s\n' "${i0_exit}" > "${RESULT_ROOT}/p8_3_i0_exit_code.txt"
  fi
  if test "${i0_contract_exit}" -eq 0 && test "${i0_exit}" -eq 0; then
    "${I0_PYTHON}" - "${I0_RESULT}" <<'PY'
from pathlib import Path
import json
import sys
import pyarrow.parquet as pq
import yaml

root = Path(sys.argv[1])
summary = json.loads((root / "inventory_summary.json").read_text())
manifest = json.loads((root / "inventory_manifest.json").read_text())
budget = yaml.safe_load((root / "tp4_rank_weight_budget.yaml").read_text())
table = pq.read_table(root / "expert_weight_inventory.parquet")
assert summary["indexed_tensor_count"] == summary["header_tensor_count"] == table.num_rows
assert summary["missing_index_tensor_count"] == 0
assert summary["duplicate_header_tensor_count"] == 0
assert summary["unindexed_header_tensor_count"] == 0
assert summary["wrong_shard_tensor_count"] == 0
assert summary["materialized_bytes_complete"] is False
assert summary["formal_tp4_runtime_claim_allowed"] is False
assert budget["ownership_status"] == "planning_candidate_not_runtime_validated"
assert budget["formal_tp4_runtime_claim_allowed"] is False
assert set(manifest["files"]) == {
    "expert_weight_inventory.parquet",
    "tp4_rank_weight_budget.yaml",
    "inventory_summary.json",
}
assert all(row["materialized_bytes"] is None for row in table.to_pylist())
print("p8_3_i0_inventory_acceptance=pass")
PY
    printf '%s\n' candidate_green_p8_3_i0_checkpoint_inventory \
      > "${RESULT_ROOT}/p8_3_i0_grade.txt"
  elif test "${i0_contract_exit}" -eq 0; then
    printf '%s\n' red_p8_3_i0_checkpoint_inventory_invalid > "${RESULT_ROOT}/p8_3_i0_grade.txt"
  fi
fi
~~~

I0 失败不得安装依赖、修 checkpoint、删 tensor 或改 owner 规则。它与 K1A-R1 技术独立：
I0 blocked/red 仍可继续第 3–4 节，但必须保留独立 grade。

## 3–4. K1A-R1 geometry-only lifecycle 与八 rank pinned allocator envelope

下面可以占用 NPU，但只允许一次 geometry-only 初始化。该 lifecycle 必须在
`SimpleCPUOffloadNPUWorker.register_kv_caches` 内、任何 `torch.zeros(... pin_memory=True)` 之前
写完 8 rank geometry 并抛出专用 sentinel。这是预期主动终止，不是 workload red。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r1_allocator_and_p8_3_i0_inventory_2026_0717_run01
GEOMETRY_RESULT=${RESULT_ROOT}/p8_2_k1a_r1_geometry_probe
GEOMETRY_DIR=${GEOMETRY_RESULT}/runtime/geometry
RUNTIME_PYTHON=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
cd "${REPO_ROOT}"

test -x "${RUNTIME_PYTHON}"
test -f "${KEEP_ALIVE_SCRIPT}"
test ! -e "${GEOMETRY_RESULT}"
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(ps -eo pid,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' || true)"
npu-smi info > "${RESULT_ROOT}/npu_before_geometry.txt"

mapfile -t marker_pgids < <(
  ps -eo pgid=,cmd= | awk '$0 ~ /#[0-7]#/ {gsub(/ /,"",$1); print $1}' | sort -u
)
test "${#marker_pgids[@]}" -ge 1
self_pgid=$(ps -o pgid= -p $$ | tr -d ' ')
for pgid in "${marker_pgids[@]}"; do
  test -n "${pgid}"
  test "${pgid}" != "${self_pgid}"
  kill -TERM -- "-${pgid}"
done
for _ in $(seq 1 60); do
  marker_count=$(ps -eo cmd= | grep -Ec '#[0-7]#' || true)
  test "${marker_count}" -eq 0 && break
  sleep 1
done
test "$(ps -eo cmd= | grep -Ec '#[0-7]#' || true)" -eq 0
sleep 3
npu-smi info > "${RESULT_ROOT}/npu_after_keep_alive_stop.txt"
grep -F 'No running processes found' "${RESULT_ROOT}/npu_after_keep_alive_stop.txt" >/dev/null

restore_keep_alive() {
  set +e
  pkill -TERM -f '[v]llm serve' 2>/dev/null || true
  for _ in $(seq 1 60); do
    test -z "$(ss -ltnp | grep ':7000' || true)" && break
    sleep 1
  done
  if test "$(ps -eo cmd= | grep -Ec '#[0-7]#' || true)" -eq 0; then
    bash "${KEEP_ALIVE_SCRIPT}" 0 1 2 3 4 5 6 7 \
      > "${RESULT_ROOT}/keep_alive_restore.log" 2>&1
  fi
  sleep 5
  ps -eo pid,ppid,pgid,stat,cmd | grep -E '#[0-7]#' \
    > "${RESULT_ROOT}/keep_alive_after.txt" || true
  npu-smi info > "${RESULT_ROOT}/npu_final.txt" 2>&1 || true
}
trap restore_keep_alive EXIT

set +e
P8_2_K1A_R1_GEOMETRY_ONLY=1 \
P8_2_K1A_R1_GEOMETRY_DIR="${GEOMETRY_DIR}" \
OBSERVER="${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_r1_geometry_observer.py" \
bash tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh \
  "${GEOMETRY_RESULT}"
geometry_exit=$?
set -e
printf '%s\n' "${geometry_exit}" > "${RESULT_ROOT}/geometry_probe_exit_code.txt"

test "${geometry_exit}" -eq 2
test "$(cat "${GEOMETRY_RESULT}/cleanup_status.txt")" = clean
test "$(find "${GEOMETRY_DIR}" -maxdepth 1 -name 'geometry.rank.*.json' | wc -l)" -eq 8
test "$(wc -l < "${GEOMETRY_RESULT}/request_summary.tsv")" -eq 1
grep -F 'P8_2_K1A_R1_GEOMETRY_PROBE_COMPLETE' \
  "${GEOMETRY_RESULT}/runtime/vllm_server.log" >/dev/null

"${RUNTIME_PYTHON}" - "${GEOMETRY_RESULT}" "${REPO_ROOT}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

result, repo = map(Path, sys.argv[1:])
observer = repo / "tools/inference_contracts/p8_2_k1a_r1_geometry_observer.py"
value = {
    "execution_scope": "geometry_only_before_pinned_allocation",
    "observer_override_path": str(observer.relative_to(repo)),
    "observer_override_sha256": hashlib.sha256(observer.read_bytes()).hexdigest(),
    "parent_mode_runner_reused": True,
    "parent_environment_and_hashes_not_formal_result_evidence": True,
    "model_requests_sent": 0,
}
(result / "geometry_probe_provenance.json").write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

"${RUNTIME_PYTHON}" tools/inference_contracts/p8_2_k1a_r1_allocator.py \
  summarize-geometry \
  --geometry-dir "${GEOMETRY_DIR}" \
  --output "${RESULT_ROOT}/k1a_r1_geometry_summary.json"

ENVELOPE_DIR=${RESULT_ROOT}/p8_2_k1a_r1_pinned_allocator_envelope
test -f "${RESULT_ROOT}/k1a_r1_geometry_summary.json"
test ! -e "${ENVELOPE_DIR}"
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(ps -eo pid,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' || true)"

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

set +e
"${RUNTIME_PYTHON}" \
  tools/inference_contracts/probe_deepseek_p8_2_k1a_r1_pinned_allocator.py \
  envelope \
  --geometry-summary "${RESULT_ROOT}/k1a_r1_geometry_summary.json" \
  --output-dir "${ENVELOPE_DIR}" \
  --wave-timeout-seconds 180
envelope_exit=$?
set -e
printf '%s\n' "${envelope_exit}" > "${RESULT_ROOT}/pinned_allocator_envelope_exit_code.txt"
test "${envelope_exit}" -eq 0 -o "${envelope_exit}" -eq 2
test -f "${ENVELOPE_DIR}/pinned_allocator_envelope.json"
test -z "$(ps -eo pid,cmd | grep -F '[p]robe_deepseek_p8_2_k1a_r1_pinned_allocator.py worker' || true)"
test -z "$(ss -ltnp | grep ':7000' || true)"

"${RUNTIME_PYTHON}" - "${RESULT_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
geometry = json.loads((root / "k1a_r1_geometry_summary.json").read_text())
envelope = json.loads(
    (root / "p8_2_k1a_r1_pinned_allocator_envelope/pinned_allocator_envelope.json").read_text()
)
assert geometry["geometry_gate_ok"] is True
assert geometry["required_cpu_blocks"] == 128
assert envelope["formal_lifecycle_allowed"] is False
assert envelope["formal_lifecycle_requires_new_handoff"] is True
assert envelope["grade"] in {
    "candidate_ready_p8_2_k1a_r1_allocator_capacity",
    "blocked_p8_2_k1a_r1_pinned_capacity_below_restore_requirement",
}
if envelope["acl_pinned_host_allocator_gate_ok"]:
    assert envelope["candidate_cpu_bytes_per_rank"] == geometry["required_capacity_bytes_per_rank"]
else:
    assert envelope["candidate_cpu_bytes_per_rank"] is None
print(envelope["grade"])
PY
~~~

若 geometry 不是专用 sentinel、8 rank 不齐、出现任何请求或 cleanup 不干净，`set -e`
会在 allocator 前停止，trap 只恢复 keep-alive，分级为 `red_p8_2_k1a_r1_geometry_probe_invalid`。
本节 allocator 按 32→64→96→128 blocks 递增，同 wave 8 rank 并发 hold/release；任一 wave 首错即停，
不 retry、不超过 128 blocks。pass 只证明 shaped pinned allocation capacity candidate，不证明 connector
registration、D2H store、H2D restore、Prefix hit、MTP、延迟或优化收益。不得启动正式六请求 K1A lifecycle。

## 5. 收尾、独立分级与报告

geometry/envelope 结束后让 trap 恢复 keep-alive，然后必须确认：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r1_allocator_and_p8_3_i0_inventory_2026_0717_run01
cd "${REPO_ROOT}"

test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(ps -eo pid,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' || true)"
test "$(ps -eo cmd= | grep -Ec '#[0-7]#' || true)" -eq 16
for card in 0 1 2 3 4 5 6 7; do
  grep -F "#${card}#" "${RESULT_ROOT}/keep_alive_after.txt" >/dev/null
done
test -z "$(git status --porcelain --untracked-files=no)"

python3 - "${RESULT_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
def text_or(path: Path, fallback: str) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else fallback
def json_or(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

i0_grade = text_or(root / "p8_3_i0_grade.txt", "not_completed_p8_3_i0")
geometry = json_or(root / "k1a_r1_geometry_summary.json")
envelope = json_or(
    root / "p8_2_k1a_r1_pinned_allocator_envelope/pinned_allocator_envelope.json"
)
k1a_grade = (
    envelope["grade"] if envelope is not None
    else "red_p8_2_k1a_r1_geometry_probe_invalid"
)
value = {
    "task_id": "p8_dual_track_k1a_r1_allocator_and_p8_3_i0_inventory_2026_0717",
    "task_completion": "complete_with_independent_section_grades",
    "p8_3_i0_grade": i0_grade,
    "p8_2_k1a_r1_grade": k1a_grade,
    "geometry_summary": geometry,
    "allocator_envelope": envelope,
    "formal_model_lifecycle_count": 0,
    "model_request_count": 0,
    "formal_k1a_authorized": False,
    "k2_authorized": False,
    "p8_3_i1_authorized": False,
    "result_transfer_authorized": False,
    "claim_boundary": (
        "checkpoint_inventory_and_tp4_planning_budget_plus_exact_kv_geometry_"
        "and_eight_rank_pinned_allocator_capacity_only"
    ),
}
(root / "grading_summary.json").write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(root / "result_summary.md").write_text(
    "# P8 dual-track bounded result\n\n"
    f"- task_id: `{value['task_id']}`\n"
    f"- P8.3-I0: `{i0_grade}`\n"
    f"- P8.2-K1A-R1: `{k1a_grade}`\n"
    "- formal model lifecycle / request: `0 / 0`\n"
    "- boundary: checkpoint planning inventory and allocator capacity only; "
    "no runtime offload, TP4, performance or optimization claim.\n",
    encoding="utf-8",
)
PY

git status --short --branch --untracked-files=no
npu-smi info
~~~

服务器报告必须分开给出：

- 同步前/后 HEAD、`origin/main`、ahead/behind、tracked clean；
- P8.3-I0 interpreter/dependency gate、index/shard/tensor 数、full-hash 结果、missing/duplicate/
  wrong-shard/unclassified bytes、Parquet rows、TP4 四 rank checkpoint-logical budget、
  `materialized_bytes_complete:false`、独立 grade；
- geometry lifecycle 是否恰好 1、请求是否恰好 0、sentinel、8 rank coverage、
  `total_bytes_per_block`、`required_capacity_bytes_per_rank`、cleanup；
- 每个 allocator wave 的 blocks、bytes/rank、success ranks、首错 error type/message、cleanup，
  以及最终 K1A-R1 grade；
- keep-alive 前/停止后/恢复后状态，端口、vLLM 残留和 tracked clean；
- 明确 `formal_model_lifecycle_count=0 / model_request_count=0 / no K2 or P8.3-I1`。

原始 checkpoint inventory Parquet、full shard hashes 细表、vLLM log、NPU log 和进程级 allocator status
留服务器。结果不自动外发。如需外发，先报告精确 `RESULT_ROOT`、完整候选清单、
逐文件 bytes/SHA-256/sensitivity、可用 `email / upload-api / server-local` 与一个推荐理由，
然后等用户对该完整范围重新选择。本 handoff 不是结果外发授权。
