# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R2 八 rank rendezvous + P8.3-I0-R1 taxonomy

~~~text
task_id: p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717
execution_mode: authorized_existing_inventory_taxonomy_and_geometry_rendezvous_allocator_envelope
server_sync_review_authorized: true
result_directory_creation_authorized: true
p8_3_i0_r1_existing_inventory_taxonomy_authorized: true
p8_3_i0_r1_checkpoint_index_resolution_authorized: true
checkpoint_full_sha256_authorized: false
checkpoint_or_inventory_mutation_authorized: false
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

本任务替换且禁止重跑已消费的
`p8_dual_track_k1a_r1_allocator_and_p8_3_i0_inventory_2026_0717`。开发机已经独立接受：

- P8.3-I0 在 checkpoint inventory 边界为 `green_p8_3_i0_checkpoint_inventory`：70 shard、
  `103176/103176` indexed/header tensor、missing/duplicate/unindexed/wrong-shard 均为 0；但真实 index
  basename 是 `quant_model_weights.safetensors.index.json`，旧执行依赖临时 symlink，且仍有
  `1135` tensor / `12319364956 bytes` 未分类，所以 TP4 budget 继续 incomplete，不能进入 runtime claim。
- P8.2-K1A-R1 为 `red_p8_2_k1a_r1_geometry_probe_invalid`：只得到 rank 0/2 两份完整记录，allocator
  未执行。根因是旧 observer 每 rank 写盘后立即抛 sentinel，没有八 rank rendezvous；这不是 pinned
  allocator 容量失败，partial `430604288 bytes/rank` 也不是已接受容量候选。

本任务分两个独立 section：I0-R1 只读复用服务器已有 Parquet，不重跑 70 shard hash、不占 NPU；
K1A-R2 只允许一次 geometry-only 初始化，8 rank 以同一随机 probe run ID 原子写盘，只有全部记录可解析、
rank/world/parity 完整且 completion marker 已形成后才允许抛专用 sentinel。冻结 DeepSeek R2 hybrid-KV
的目标 restore geometry 仍为 `16384` token；geometry green 后才运行既有
`32→64→96→128` blocks 八 rank shaped pinned allocator waves。即使 128-block wave 通过，也只形成
`candidate_ready_p8_2_k1a_r2_allocator_capacity`，必须回开发机复核并另发 handoff 才能启动正式六请求。

保留 lineage：P6.3B-R4-R1=`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`、
P8.1-R1=`green_p8_1_r1_official_mtp_observe_only_matrix`、P8.2-K0 与 P8.3-I0 继续 green；
P6.3C=`blocked_p6_3c_not_strict_single_variable`；legacy `NPUOffloadingSpec` K1 继续
`blocked_p8_2_k1_frozen_stack_import_incompatible`；
`SimpleCPUOffloadConnector` K1A 32 GiB/rank 与 K1A-R1 各自保留 red。禁止自动进入 K2、P8.3-I1、
P8.4、P8.5、P9；禁止 profiler、checkpoint/runtime 修改和结果自动外发。

## 1. 同步与冻结仓库门（零 NPU）

从服务器自己的干净 `main` 普通快进。不得 reset/stash/rebase、运行 `sync.sh`、在服务器 commit/push，
或删除既有未跟踪运行产物。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717_run01
cd "${REPO_ROOT}"

git status --short --branch --untracked-files=no
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
test ! -e "${RESULT_ROOT}"

python3 - <<'PY'
from pathlib import Path
import hashlib

expected = {
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r2_geometry_rendezvous_audit.yaml": "7553ec2ee67422eacad6f6e4ca1f37da55b46a71706f74db07bc73dba5db9e82",
    "benchmarks/deepseek_v4_flash/p8_3_i0_r1_inventory_taxonomy_audit.yaml": "09cda890102a46d24b4b8866748937ba9f88f261f0012f0985e5af9deb12ea57",
    "benchmarks/deepseek_v4_flash/p8_3_i0_checkpoint_inventory_contract.yaml": "6af2a125cc88faafb38e350ea45ffe4906f64c8536b5b3ee01b63c84911f32b6",
    "tools/inference_contracts/p8_2_k1a_r2_geometry_observer.py": "6d9f3f08c05527107086d79259177044a670495648ff5066a7d7935d017a3ca9",
    "tools/inference_contracts/p8_2_k1a_r2_allocator.py": "135a95b70e8e73f791ff5a2ea2e79b2fde63e905d40e713b76fb4ee10691048d",
    "tools/inference_contracts/p8_2_k1a_r1_allocator.py": "c3f6f0ce3ab119f25245710f4d6b7ea05d9316e7b326a0209a6282408fe527c9",
    "tools/inference_contracts/probe_deepseek_p8_2_k1a_r1_pinned_allocator.py": "8ae11b8183c829367ef6ac900fa92eb5c8d9db399c72dc1952dc477ecc29f13c",
    "tools/inference_contracts/inventory_deepseek_p8_3_i0_checkpoint.py": "6d6535b9931fb0f7b17ab0bae67a59611d2b9174a532c2b80490f4d397ebd819",
    "tools/inference_contracts/analyze_deepseek_p8_3_i0_unclassified.py": "30ab89547dab3898d54fb91040d9827a1b2c504fc5d8b3cd8497dd25764f92ef",
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
  tests/inference_contracts/test_deepseek_p8_2_k1a_r2_geometry_rendezvous.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r1_allocator_envelope.py \
  tests/inference_contracts/test_deepseek_p8_3_i0_checkpoint_inventory.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_simple_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1_kv_cache_cpu_offload_feasibility.py -q
python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_r2_geometry_observer.py \
  tools/inference_contracts/p8_2_k1a_r2_allocator.py \
  tools/inference_contracts/p8_2_k1a_r1_allocator.py \
  tools/inference_contracts/probe_deepseek_p8_2_k1a_r1_pinned_allocator.py \
  tools/inference_contracts/inventory_deepseek_p8_3_i0_checkpoint.py \
  tools/inference_contracts/analyze_deepseek_p8_3_i0_unclassified.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
test -z "$(git status --porcelain --untracked-files=no)"
~~~

任一 hash、合同、compile、Bash 或 tracked-clean 失败，给
`blocked_p8_dual_track_r2_repository_contract_gate` 并停止；不得创建结果目录、停止 keep-alive 或占 NPU。
所有 Python 依赖必须来自既有环境，不得 pip/conda install。

## 2. P8.3-I0-R1：真实 index 与既有 Parquet taxonomy（零 NPU）

本节不重新读取 shard header、不重算 70 个 shard SHA-256、不复制或改写 parent inventory。先冻结 parent
四文件，再直接解析真实 checkpoint 目录的唯一 index；不得再建 symlink workspace。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
PARENT_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r1_allocator_and_p8_3_i0_inventory_2026_0717_run01
SOURCE_I0=${PARENT_ROOT}/p8_3_i0_checkpoint_inventory
RESULT_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717_run01
I0_R1=${RESULT_ROOT}/p8_3_i0_r1_taxonomy
RUNTIME_PYTHON=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
cd "${REPO_ROOT}"

test -x "${RUNTIME_PYTHON}"
"${RUNTIME_PYTHON}" -c 'import numpy, pyarrow, safetensors, yaml'
test ! -e "${RESULT_ROOT}"
test -f "${MODEL_PATH}/quant_model_weights.safetensors.index.json"
test ! -L "${MODEL_PATH}/quant_model_weights.safetensors.index.json"
test -f "${SOURCE_I0}/expert_weight_inventory.parquet"
test -f "${SOURCE_I0}/inventory_summary.json"
test -f "${SOURCE_I0}/tp4_rank_weight_budget.yaml"
test -f "${SOURCE_I0}/inventory_manifest.json"
test "$(stat -c '%s' "${SOURCE_I0}/expert_weight_inventory.parquet")" = 339497
test "$(sha256sum "${SOURCE_I0}/expert_weight_inventory.parquet" | awk '{print $1}')" = 3bba8656de0a2ccf5deccccf84e7010ad28f941a7d255a005b82d5d8d225b17c
test "$(stat -c '%s' "${SOURCE_I0}/inventory_summary.json")" = 17161
test "$(sha256sum "${SOURCE_I0}/inventory_summary.json" | awk '{print $1}')" = 90a77c91585278e28f89624d2f767e155939d9e5e7a78d1016a6b10aff93bc0d
test "$(stat -c '%s' "${SOURCE_I0}/tp4_rank_weight_budget.yaml")" = 1202
test "$(sha256sum "${SOURCE_I0}/tp4_rank_weight_budget.yaml" | awk '{print $1}')" = e6cb415880d5131e8913a7f6929cdd7f56cc7944c9b22ba0b24621c990d9e097
test "$(stat -c '%s' "${SOURCE_I0}/inventory_manifest.json")" = 589
test "$(sha256sum "${SOURCE_I0}/inventory_manifest.json" | awk '{print $1}')" = 347f5aa09712f437fafe76baa7d4689a7061623ee06b17f91575039e33502bd9
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(ps -eo pid,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' || true)"

mkdir -p "${I0_R1}"
ps -eo pid,ppid,pgid,stat,cmd | grep -E '#[0-7]#' > "${I0_R1}/keep_alive_before.txt"
npu-smi info > "${I0_R1}/npu_before.txt"

"${RUNTIME_PYTHON}" - "${MODEL_PATH}" "${I0_R1}/p8_3_i0_r1_index_resolution.json" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

from tools.inference_contracts.inventory_deepseek_p8_3_i0_checkpoint import resolve_safetensors_index

model, output = map(Path, sys.argv[1:])
explicit, explicit_mode = resolve_safetensors_index(
    model, Path("quant_model_weights.safetensors.index.json")
)
discovered, discovery_mode = resolve_safetensors_index(model)
assert explicit == discovered
assert explicit.name == "quant_model_weights.safetensors.index.json"
assert not explicit.is_symlink()
sha = hashlib.sha256(explicit.read_bytes()).hexdigest()
assert sha == "932abcc237e82bbb52fc044ae52dd7aa9d8af259cd40100ef978e479231164aa"
value = {
    "schema_version": "p8_3_i0_r1_index_resolution_v1",
    "index_basename": explicit.name,
    "index_bytes": explicit.stat().st_size,
    "index_sha256": sha,
    "explicit_resolution": explicit_mode,
    "discovery_resolution": discovery_mode,
    "explicit_and_discovered_same_file": True,
    "index_is_symlink": False,
    "temporary_workspace_used": False,
    "checkpoint_mutated": False,
}
output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

"${RUNTIME_PYTHON}" tools/inference_contracts/analyze_deepseek_p8_3_i0_unclassified.py \
  --inventory "${SOURCE_I0}/expert_weight_inventory.parquet" \
  --inventory-summary "${SOURCE_I0}/inventory_summary.json" \
  --output "${I0_R1}/p8_3_i0_r1_unclassified_taxonomy.json" \
  --max-groups 256 \
  --max-output-bytes 32768

"${RUNTIME_PYTHON}" - "${I0_R1}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
taxonomy = json.loads((root / "p8_3_i0_r1_unclassified_taxonomy.json").read_text())
assert taxonomy["unclassified_tensor_count"] == 1135
assert taxonomy["unclassified_checkpoint_bytes"] == 12319364956
assert taxonomy["accounted_tensor_count_exact"] is True
assert taxonomy["accounted_checkpoint_bytes_exact"] is True
assert taxonomy["formal_reclassification_allowed"] is False
assert taxonomy["formal_tp4_runtime_claim_allowed"] is False
grade = (
    "candidate_green_p8_3_i0_r1_unclassified_taxonomy"
    if taxonomy["taxonomy_complete"]
    else "yellow_p8_3_i0_r1_unclassified_taxonomy_truncated"
)
(root / "p8_3_i0_r1_grade.txt").write_text(grade + "\n", encoding="utf-8")
files = {}
for name in (
    "p8_3_i0_r1_index_resolution.json",
    "p8_3_i0_r1_unclassified_taxonomy.json",
    "p8_3_i0_r1_grade.txt",
):
    path = root / name
    files[name] = {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
    }
(root / "p8_3_i0_r1_section_manifest.json").write_text(
    json.dumps(
        {
            "schema_version": "p8_3_i0_r1_section_manifest_v1",
            "files": files,
            "source_parquet_copied": False,
            "full_shard_hash_rerun": False,
            "checkpoint_mutated": False,
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
PY

ps -eo pid,ppid,pgid,stat,cmd | grep -E '#[0-7]#' > "${I0_R1}/keep_alive_after.txt"
npu-smi info > "${I0_R1}/npu_after.txt"
cmp "${I0_R1}/keep_alive_before.txt" "${I0_R1}/keep_alive_after.txt"
test "$(sha256sum "${SOURCE_I0}/expert_weight_inventory.parquet" | awk '{print $1}')" = 3bba8656de0a2ccf5deccccf84e7010ad28f941a7d255a005b82d5d8d225b17c
test "$(sha256sum "${SOURCE_I0}/inventory_summary.json" | awk '{print $1}')" = 90a77c91585278e28f89624d2f767e155939d9e5e7a78d1016a6b10aff93bc0d
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(ps -eo pid,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' || true)"
test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节 `taxonomy_complete=false` 只给 bounded yellow，不得扩大发回文件、自动改 classification rule 或补算
TP4 budget。任何 parent hash/index 失败给对应 blocked grade；不得修 checkpoint、重跑 parent inventory、
停止 keep-alive 或进入 I1。本节 raw Parquet 继续留服务器，绝不进入候选小包。

## 3. P8.2-K1A-R2：一次 geometry rendezvous + allocator envelope

只允许一次 geometry-only 初始化。沿用 parent 的冻结 W8A8/TP8+EP/MTP/R2 repair/server argv，但 observer
必须换成 R2；它在 pinned CPU mirror allocation 前写 record，并以 bounded filesystem rendezvous 等待
同一 `P8_2_K1A_R2_PROBE_RUN_ID` 的 8 rank 完整记录。任何 rank/world/parity/timeout 问题都必须在
allocator 前停止。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717_run01
K1A_R2=${RESULT_ROOT}/p8_2_k1a_r2_geometry_and_allocator
GEOMETRY_RESULT=${K1A_R2}/geometry_probe
GEOMETRY_DIR=${GEOMETRY_RESULT}/runtime/geometry
ENVELOPE_DIR=${K1A_R2}/pinned_allocator_envelope
RUNTIME_PYTHON=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
cd "${REPO_ROOT}"

test -d "${RESULT_ROOT}"
test ! -e "${K1A_R2}"
test -x "${RUNTIME_PYTHON}"
test -f "${KEEP_ALIVE_SCRIPT}"
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(ps -eo pid,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' || true)"
mkdir -p "${K1A_R2}"
npu-smi info > "${K1A_R2}/npu_before_geometry.txt"
ps -eo pid,ppid,pgid,stat,cmd | grep -E '#[0-7]#' > "${K1A_R2}/keep_alive_before.txt"

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
npu-smi info > "${K1A_R2}/npu_after_keep_alive_stop.txt"
grep -F 'No running processes found' "${K1A_R2}/npu_after_keep_alive_stop.txt" >/dev/null

restore_keep_alive() {
  set +e
  pkill -TERM -f '[v]llm serve' 2>/dev/null || true
  for _ in $(seq 1 60); do
    test -z "$(ss -ltnp | grep ':7000' || true)" && break
    sleep 1
  done
  if test "$(ps -eo cmd= | grep -Ec '#[0-7]#' || true)" -eq 0; then
    bash "${KEEP_ALIVE_SCRIPT}" 0 1 2 3 4 5 6 7 \
      > "${K1A_R2}/keep_alive_restore.log" 2>&1
  fi
  sleep 5
  ps -eo pid,ppid,pgid,stat,cmd | grep -E '#[0-7]#' \
    > "${K1A_R2}/keep_alive_after.txt" || true
  npu-smi info > "${K1A_R2}/npu_final.txt" 2>&1 || true
}
trap restore_keep_alive EXIT

PROBE_RUN_ID=$("${RUNTIME_PYTHON}" -c 'import uuid; print(uuid.uuid4().hex)')
test -n "${PROBE_RUN_ID}"
printf '%s\n' "${PROBE_RUN_ID}" > "${K1A_R2}/probe_run_id.txt"

set +e
P8_2_K1A_R2_GEOMETRY_ONLY=1 \
P8_2_K1A_R2_GEOMETRY_DIR="${GEOMETRY_DIR}" \
P8_2_K1A_R2_PROBE_RUN_ID="${PROBE_RUN_ID}" \
P8_2_K1A_R2_RENDEZVOUS_TIMEOUT_SECONDS=180 \
OBSERVER="${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_r2_geometry_observer.py" \
bash tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh \
  "${GEOMETRY_RESULT}"
geometry_exit=$?
set -e
printf '%s\n' "${geometry_exit}" > "${K1A_R2}/geometry_probe_exit_code.txt"

test "${geometry_exit}" -eq 2
test "$(cat "${GEOMETRY_RESULT}/cleanup_status.txt")" = clean
test "$(wc -l < "${GEOMETRY_RESULT}/request_summary.tsv")" -eq 1
test "$(find "${GEOMETRY_DIR}" -maxdepth 1 -name 'geometry.rank.*.json' -size +0c | wc -l)" -eq 8
test -f "${GEOMETRY_DIR}/geometry.rendezvous.complete.json"
grep -F 'P8_2_K1A_R2_GEOMETRY_PROBE_COMPLETE' \
  "${GEOMETRY_RESULT}/runtime/vllm_server.log" >/dev/null

"${RUNTIME_PYTHON}" tools/inference_contracts/p8_2_k1a_r2_allocator.py \
  summarize-geometry \
  --geometry-dir "${GEOMETRY_DIR}" \
  --output "${K1A_R2}/k1a_r2_geometry_summary.json"

test ! -e "${ENVELOPE_DIR}"
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(ps -eo pid,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' || true)"
set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u

set +e
"${RUNTIME_PYTHON}" tools/inference_contracts/probe_deepseek_p8_2_k1a_r1_pinned_allocator.py \
  envelope \
  --geometry-summary "${K1A_R2}/k1a_r2_geometry_summary.json" \
  --output-dir "${ENVELOPE_DIR}" \
  --wave-timeout-seconds 180
envelope_exit=$?
set -e
printf '%s\n' "${envelope_exit}" > "${K1A_R2}/pinned_allocator_envelope_exit_code.txt"
test "${envelope_exit}" -eq 0 -o "${envelope_exit}" -eq 2
test -f "${ENVELOPE_DIR}/pinned_allocator_envelope.json"
test -z "$(ps -eo pid,cmd | grep -F '[p]robe_deepseek_p8_2_k1a_r1_pinned_allocator.py worker' || true)"
test -z "$(ss -ltnp | grep ':7000' || true)"

"${RUNTIME_PYTHON}" - "${K1A_R2}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
geometry = json.loads((root / "k1a_r2_geometry_summary.json").read_text())
envelope_path = root / "pinned_allocator_envelope/pinned_allocator_envelope.json"
envelope = json.loads(envelope_path.read_text())
assert geometry["stage"] == "P8.2-K1A-R2"
assert geometry["geometry_gate_ok"] is True
assert geometry["rendezvous_gate_ok"] is True
assert geometry["rank_coverage"] == list(range(8))
assert geometry["required_cpu_blocks"] == 128
assert envelope["formal_lifecycle_allowed"] is False
assert envelope["formal_lifecycle_requires_new_handoff"] is True
assert envelope["grade"] in {
    "candidate_ready_p8_2_k1a_r2_allocator_capacity",
    "blocked_p8_2_k1a_r2_pinned_capacity_below_restore_requirement",
}
(root / "p8_2_k1a_r2_grade.txt").write_text(envelope["grade"] + "\n", encoding="utf-8")

waves = []
for wave in envelope["waves"]:
    failed = next(
        (row for row in wave.get("rank_status", []) if row.get("success") is not True),
        None,
    )
    waves.append(
        {
            "cpu_blocks": wave["cpu_blocks"],
            "bytes_per_rank": wave["bytes_per_rank"],
            "rank_status_count": wave.get("rank_status_count", 0),
            "rank_success_count": wave.get("rank_success_count", 0),
            "cleanup_ok": wave.get("cleanup_ok"),
            "not_attempted_reason": wave.get("not_attempted_reason"),
            "first_failure_error_type": failed.get("error_type") if failed else None,
            "first_failure_error_message": str(failed.get("error_message", ""))[-512:] if failed else None,
        }
    )
bounded = {
    key: envelope[key]
    for key in (
        "schema_version",
        "acl_pinned_host_allocator_gate_ok",
        "required_cpu_blocks",
        "highest_eight_rank_clean_blocks",
        "candidate_cpu_bytes_per_rank",
        "candidate_cpu_bytes_total",
        "capacity_candidate_ready",
        "formal_lifecycle_allowed",
        "formal_lifecycle_requires_new_handoff",
        "grade",
    )
}
bounded["waves"] = waves
(root / "pinned_allocator_envelope_summary.json").write_text(
    json.dumps(bounded, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)

relative_files = (
    "probe_run_id.txt",
    "geometry_probe_exit_code.txt",
    "k1a_r2_geometry_summary.json",
    "pinned_allocator_envelope_summary.json",
    "p8_2_k1a_r2_grade.txt",
    "geometry_probe/runtime/geometry/geometry.rendezvous.complete.json",
    "geometry_probe/cleanup_status.txt",
)
files = {}
for relative in relative_files:
    path = root / relative
    files[relative] = {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
    }
(root / "p8_2_k1a_r2_section_manifest.json").write_text(
    json.dumps(
        {
            "schema_version": "p8_2_k1a_r2_section_manifest_v1",
            "files": files,
            "raw_rank_records_remain_server_local": True,
            "raw_allocator_status_remain_server_local": True,
            "formal_model_lifecycle_count": 0,
            "model_request_count": 0,
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
PY
~~~

若 geometry 不是专用 sentinel、8 rank/same-run/parity/marker 不完整、出现请求或 cleanup 不干净，给
`red_p8_2_k1a_r2_geometry_probe_invalid` 并在 allocator 前停止。allocator 只跑 32→64→96→128；任一
wave 首错即停、不 retry、不超过 128。不得启动正式六请求 K1A lifecycle。raw vLLM log、rank records、
NPU log 和逐 rank allocator status 全部留服务器。

## 4. 恢复、独立分级与 bounded candidate manifest

第 3 节 shell 退出时 trap 必须恢复 keep-alive。然后执行：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717_run01
I0_R1=${RESULT_ROOT}/p8_3_i0_r1_taxonomy
K1A_R2=${RESULT_ROOT}/p8_2_k1a_r2_geometry_and_allocator
cd "${REPO_ROOT}"

test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(ps -eo pid,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' || true)"
test "$(ps -eo cmd= | grep -Ec '#[0-7]#' || true)" -eq 16
for card in 0 1 2 3 4 5 6 7; do
  grep -F "#${card}#" "${K1A_R2}/keep_alive_after.txt" >/dev/null
done
test -z "$(git status --porcelain --untracked-files=no)"

python3 - "${RESULT_ROOT}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
i0 = root / "p8_3_i0_r1_taxonomy"
k1a = root / "p8_2_k1a_r2_geometry_and_allocator"
i0_grade = (i0 / "p8_3_i0_r1_grade.txt").read_text().strip()
k1a_grade = (k1a / "p8_2_k1a_r2_grade.txt").read_text().strip()
geometry = json.loads((k1a / "k1a_r2_geometry_summary.json").read_text())
envelope = json.loads((k1a / "pinned_allocator_envelope_summary.json").read_text())
taxonomy = json.loads((i0 / "p8_3_i0_r1_unclassified_taxonomy.json").read_text())

grading = {
    "schema_version": "p8_dual_track_k1a_r2_i0_r1_grading_v1",
    "task_id": "p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717",
    "task_completion": "complete_with_independent_section_grades",
    "p8_3_i0_parent_grade": "green_p8_3_i0_checkpoint_inventory",
    "p8_3_i0_r1_grade": i0_grade,
    "p8_2_k1a_r1_parent_grade": "red_p8_2_k1a_r1_geometry_probe_invalid",
    "p8_2_k1a_r2_grade": k1a_grade,
    "taxonomy_complete": taxonomy["taxonomy_complete"],
    "taxonomy_group_count": taxonomy["taxonomy_group_count"],
    "reported_taxonomy_group_count": taxonomy["reported_group_count"],
    "unclassified_tensor_count": taxonomy["unclassified_tensor_count"],
    "unclassified_checkpoint_bytes": taxonomy["unclassified_checkpoint_bytes"],
    "geometry_probe_run_id": geometry["probe_run_id"],
    "geometry_rank_coverage": geometry["rank_coverage"],
    "total_bytes_per_block": geometry["total_bytes_per_block"],
    "required_capacity_bytes_per_rank": geometry["required_capacity_bytes_per_rank"],
    "allocator_gate_ok": envelope["acl_pinned_host_allocator_gate_ok"],
    "formal_model_lifecycle_count": 0,
    "model_request_count": 0,
    "formal_k1a_authorized": False,
    "p8_3_i1_authorized": False,
    "k2_authorized": False,
    "result_transfer_authorized": False,
    "claim_boundary": "existing_inventory_taxonomy_plus_same_run_eight_rank_geometry_and_allocator_capacity_only",
}
(root / "grading_summary.json").write_text(
    json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(root / "result_summary.md").write_text(
    "# P8 dual-track R2/I0-R1 bounded result\n\n"
    f"- task_id: `{grading['task_id']}`\n"
    f"- P8.3-I0-R1: `{i0_grade}`\n"
    f"- P8.2-K1A-R2: `{k1a_grade}`\n"
    "- formal model lifecycle / request: `0 / 0`\n"
    "- boundary: existing inventory taxonomy and allocator feasibility only; no TP4 runtime, "
    "offload mechanism, performance or optimization claim.\n",
    encoding="utf-8",
)

candidate_paths = (
    root / "result_summary.md",
    root / "grading_summary.json",
    i0 / "p8_3_i0_r1_index_resolution.json",
    i0 / "p8_3_i0_r1_unclassified_taxonomy.json",
    i0 / "p8_3_i0_r1_grade.txt",
    i0 / "p8_3_i0_r1_section_manifest.json",
    k1a / "k1a_r2_geometry_summary.json",
    k1a / "pinned_allocator_envelope_summary.json",
    k1a / "p8_2_k1a_r2_grade.txt",
    k1a / "geometry_probe/runtime/geometry/geometry.rendezvous.complete.json",
    k1a / "geometry_probe/cleanup_status.txt",
    k1a / "p8_2_k1a_r2_section_manifest.json",
)
files = {}
for path in candidate_paths:
    relative = str(path.relative_to(root))
    files[relative] = {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
    }
total = sum(row["bytes"] for row in files.values())
assert total <= 71680, total
(root / "candidate_manifest.server_local.json").write_text(
    json.dumps(
        {
            "schema_version": "p8_dual_track_r2_candidate_manifest_v1",
            "result_root": str(root),
            "files": files,
            "candidate_file_count": len(files),
            "candidate_total_bytes": total,
            "max_total_bytes": 71680,
            "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
            "manifest_is_server_local_not_a_transfer_candidate": True,
            "result_transfer_authorized": False,
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
print(json.dumps({"i0_grade": i0_grade, "k1a_grade": k1a_grade, "candidate_total_bytes": total}))
PY

git status --short --branch --untracked-files=no
npu-smi info
~~~

服务器最终报告必须分 section 给出：同步前后 HEAD/origin/ahead-behind/tracked；I0 parent 四文件 hash、
真实 index basename/hash/无 symlink、taxonomy group/覆盖/遗漏/count/bytes/grade、source inventory 前后不变；
K1A probe run ID、8 rank coverage/parity/marker/sentinel、exact geometry、每 wave blocks/bytes/success/首错/
cleanup、最终 grade；keep-alive、端口、vLLM residual 与 formal lifecycle/request=`0/0`。

结果不自动外发。报告精确 `RESULT_ROOT` 与
`candidate_manifest.server_local.json` 中的完整候选清单、逐文件 bytes/SHA-256/sensitivity、总量、可用
`email / upload-api / server-local` 及一个推荐理由，等待用户对该完整范围重新选择。不得把 raw Parquet、
rank records、allocator status、vLLM/NPU log 或 request bodies 放进候选范围；本 handoff 不是外发授权。
