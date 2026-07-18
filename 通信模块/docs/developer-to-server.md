# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R3-R1 repaired provenance + same accepted-capacity lifecycle

~~~text
task_id: p8_2_k1a_r3_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0718
execution_mode: authorized_repaired_provenance_single_lifecycle_six_request_mechanism
server_sync_review_authorized: true
installed_source_and_import_probe_authorized: true
accepted_r2_provenance_review_authorized: true
temporary_audit_workspace_authorized: true
npu_execution_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
keep_alive_stop_and_restore_authorized: true
task_local_observer_authorized: true
task_local_compatibility_patch_authorized: false
result_directory_creation_authorized: true
formal_model_lifecycle_count_exact: 1
model_request_count_exact: 6
request_retry_count_exact: 0
capacity_search_authorized: false
second_capacity_point_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
runtime_or_dependency_upgrade_authorized: false
runtime_or_dependency_mutation_authorized: false
result_transfer_authorized: false
next_task_authorized: false
no_k2_k3_k4_p8_3_i1_p8_4_p8_5_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

本任务替换且禁止重跑已经消费的
`p8_2_k1a_r3_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0718`。该 parent R3 已在三份 R2
evidence hash 通过后，因为 handoff 错把 geometry summary 当成 rendezvous marker 读取而以
`KeyError: world_size` 停止；keep-alive 未动，NPU/vLLM/request/result-dir 均为零。该结果只接受为
`blocked_p8_2_k1a_r3_source_or_provenance_gate`，不是容量或 runtime red。

开发机此前已对服务器 raw evidence、
既有 12-file candidate package 和 upload-api provenance replay 独立完成交叉验收：

- P8.2-K1A-R2 正式收口为 `ready_p8_2_k1a_r2_allocator_capacity`。8 rank same-run geometry、
  `32/64/96/128` blocks shaped allocator waves 和离线重放全部通过；接受的唯一容量是
  `16384 restore tokens = 128 blocks × 3364096 bytes/block = 430604288 bytes/rank`，TP8 总量为
  `3444834304 bytes`。
- P8.3-I0-R1 正式收口为 `green_p8_3_i0_r1_unclassified_taxonomy`。该结果与本任务技术独立，
  本 handoff 不授权 P8.3-I1、TP4 runtime、reclassification 或新 checkpoint 扫描。
- K1A 旧 `32 GiB/rank` 点继续保留 `red_p8_2_k1a_simple_cpu_offload_no_success`；K1A-R1 继续保留
  `red_p8_2_k1a_r1_geometry_probe_invalid`。R2 ready 只解锁本次精确容量的一个 formal lifecycle，
  不撤销旧 red，也不是 store/restore runtime green。

本轮只回答：冻结 DeepSeek W8A8、TP8+EP、official MTP、完整 R2 hybrid-KV repair 和
`SimpleCPUOffloadConnector` 在已验收 128-block CPU tier 上，能否在一个固定六请求 lifecycle 内形成
8/8 worker D2H store 与 8/8 worker H2D restore 机制闭环。任何 timing 仅为 unprofiled diagnostic，
不是性能 reference、优化收益、普遍容量收益或硬件瓶颈归因。

保留 lineage：`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`、
`green_p8_1_r1_official_mtp_observe_only_matrix`、
`green_p8_2_k0_order_balanced_prefix_cache_baseline` 与
`green_p8_3_i0_r1_unclassified_taxonomy`；P6.3C 保留
`blocked_p6_3c_not_strict_single_variable`，legacy K1 保留
`blocked_p8_2_k1_frozen_stack_import_incompatible`。K1A-R3/R3-R1 blocked/red/yellow 不撤销这些结果。
不得进入 K2、K3、K4、P8.3-I1、P8.4、P8.5 或 P9。

## 1. 同步、tracked-clean 与冻结仓库合同门（零 NPU）

从服务器自己的干净 `main` 普通快进同步。不得 reset、stash、rebase、checkout 覆盖、运行
`sync.sh`、在服务器 commit/push，或删除既有未跟踪运行产物。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0718_run01
cd "${REPO_ROOT}"

git status --short --branch --untracked-files=no
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
test ! -e "${RESULT_DIR}"

python3 - <<'PY'
from pathlib import Path
import hashlib

expected = {
    "benchmarks/deepseek_v4_flash/p8_2_k1a_simple_cpu_offload_feasibility_audit.yaml": "51fe967ff093678fdf7f4f208b09288c4ea020062b954d04c32a5925dfa7ba16",
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r2_geometry_rendezvous_audit.yaml": "7553ec2ee67422eacad6f6e4ca1f37da55b46a71706f74db07bc73dba5db9e82",
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_formal_lifecycle_audit.yaml": "dc9588d8d71c2742e5831bf6facdd82348b5e6d3ab4f5dd466c1d771d7ffe9dc",
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r1_provenance_gate_audit.yaml": "3e7f49b82d0d01abd70db895714de0b19fb7603bce94fe1ab22fa2e590ddf967",
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r3_simple_cpu_offload_store_restore.yaml": "aa87b3b9cf08b1404ac034a132f5dd2db7abc1cb7472d4abc02b4cb01aa5e116",
    "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py": "d1af39ef7622bee62b6b10f774ef012f306d0bc5b0318666bc6d41df786836e3",
    "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "b31d212378c8aaed87c872c67a29b8d2ea039fbd7e97e5f7e6c54b29ef99a680",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "1eabe65e103abae117e48a65c7dcedb0451f79d78b404eb2bc6643fdcce24120",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "76891fba6c4426a2344f93a9ecab216143bb6da0a03318b265b1e580681eec6c",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh": "e0c27c984403a727dcfb92cf5266372298721a2550d5e66a68cd552b145067eb",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh": "b41564b8ef8524df825ac03822a705c842f5ddac56d4cb6fed186fb8291e3252",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r1_simple_cpu_offload.sh": "09d9697de12dff6635fa36f0ec787a5774b26cde3aa9b8a56e8e2a330edfa1f9",
    "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch": "5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6",
    "tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py": "fd913f4c47a019d935e0b6b6ba8f2b5702742e3f1581703246aec9f86512a389",
    "tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r1_provenance_gate.py": "6e19af7cfbd86cf77b43e2fbaa4e0488ef34a137584ef0c8ecbba86b2aff8e85",
}
for relative, wanted in expected.items():
    got = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
    if got != wanted:
        raise SystemExit(f"frozen repo hash mismatch: {relative} {got} != {wanted}")
print("frozen_repo_hash_gate=pass")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r1_provenance_gate.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_simple_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r2_geometry_rendezvous.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r1_allocator_envelope.py \
  tests/inference_contracts/test_deepseek_p8_2_k1_kv_cache_cpu_offload_feasibility.py -q
python3 -m py_compile \
  tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r1_simple_cpu_offload.sh

P8_2_K1A_AUDIT_ONLY=1 bash \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r1_simple_cpu_offload.sh /tmp/p8_k1a_r3_r1_not_created \
  > /tmp/p8_k1a_r3_r1_contract_audit.txt
grep -Fx 'task_id=p8_2_k1a_r3_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0718' /tmp/p8_k1a_r3_r1_contract_audit.txt
grep -Fx 'cpu_bytes_to_use=3444834304' /tmp/p8_k1a_r3_r1_contract_audit.txt
grep -Fx 'cpu_bytes_to_use_per_rank=430604288' /tmp/p8_k1a_r3_r1_contract_audit.txt
grep -Fx 'server_command_sha256=418d2796ec2dd15ab7504c264a6635a50d064cb7b6425f809cbfba550d2f5bb0' /tmp/p8_k1a_r3_r1_contract_audit.txt

P8_2_K1A_MODE_AUDIT_ONLY=1 bash \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r1_simple_cpu_offload.sh /tmp/p8_k1a_r3_r1_not_created \
  > /tmp/p8_k1a_r3_r1_mode_audit.txt
grep -Fx 'cpu_bytes_to_use=3444834304' /tmp/p8_k1a_r3_r1_mode_audit.txt
grep -Fx 'cpu_bytes_to_use_per_rank=430604288' /tmp/p8_k1a_r3_r1_mode_audit.txt
grep -Fx 'observer_mode=observe_only_no_decision_or_copy_mutation' /tmp/p8_k1a_r3_r1_mode_audit.txt
test ! -e /tmp/p8_k1a_r3_r1_not_created
test -z "$(git status --porcelain --untracked-files=no)"
~~~

任一 hash、合同、compile、Bash、audit-only、tracked-clean 或 result-dir uniqueness 门失败，给
`blocked_p8_2_k1a_r3_r1_repository_contract_gate` 并停止。不得停 keep-alive、创建项目结果目录或占 NPU。

## 2. R2 accepted-capacity provenance 与冻结安装态 source/import 复核（零 NPU）

只读复核既有 R2 raw evidence 和 accepted summaries；不得重跑 geometry lifecycle 或 allocator waves。
临时输出只能写新的 `/tmp/opencode/p8_2_k1a_r3_r1_preflight_2026_0718_<unique>`。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
R2_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717_run01
K1A_R2=${R2_ROOT}/p8_2_k1a_r2_geometry_and_allocator
RENDEZVOUS=${K1A_R2}/geometry_probe/runtime/geometry/geometry.rendezvous.complete.json
TMP_AUDIT=$(mktemp -d /tmp/opencode/p8_2_k1a_r3_r1_preflight_2026_0718_XXXXXX)
TMP_AUDIT_POINTER=/tmp/opencode/p8_2_k1a_r3_r1_preflight_current_2026_0718.path
RUNTIME_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
RUNTIME_PYTHON=${RUNTIME_PREFIX}/bin/python
VLLM_ROOT=/data/node0_disk1/vllm-0.22.1
VLLM_ASCEND_ROOT=${RUNTIME_PREFIX}/lib/python3.11/site-packages
AUDITOR=${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py

test ! -e "${TMP_AUDIT_POINTER}"
printf '%s\n' "${TMP_AUDIT}" > "${TMP_AUDIT_POINTER}"
test -d "${R2_ROOT}"
test "$(sha256sum "${K1A_R2}/k1a_r2_geometry_summary.json" | awk '{print $1}')" = 8430730a583371ebdcc1cb35ff80903376a007cb3f2645ce6a55114bdb9ea6d1
test "$(sha256sum "${RENDEZVOUS}" | awk '{print $1}')" = fa258790475303b88a41d4e3f2db684a41a79026b22d434ba9827f0275280796
test "$(sha256sum "${K1A_R2}/pinned_allocator_envelope_summary.json" | awk '{print $1}')" = 99f997a66cb14aeaf1941d34c525729c70dcda0569d45c465a0f1c7f55dfc6b2
test "$(sha256sum "${R2_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = 5a65d66911ac8f073c1dd939b06d78de2a6f51dd2d5ecd66f60f5ee212cc01e9

python3 "${AUDITOR}" accepted-capacity-provenance \
  --geometry-summary "${K1A_R2}/k1a_r2_geometry_summary.json" \
  --rendezvous-marker "${RENDEZVOUS}" \
  --allocator-summary "${K1A_R2}/pinned_allocator_envelope_summary.json" \
  --output "${TMP_AUDIT}/accepted_r2_capacity_provenance.json"
grep -F '"accepted_r2_capacity_provenance_gate": "pass"' \
  "${TMP_AUDIT}/accepted_r2_capacity_provenance.json"

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

任何 R2 accepted summary、安装态 source、registry/import 或 frozen Git 状态漂移，给
`blocked_p8_2_k1a_r3_r1_source_or_provenance_gate` 并停止；不得修环境、换版本、加 shim 或占 NPU。

## 3. 零扰动资源门

keep-alive 保持运行，只读记录 marker/PID/PGID、NPU 0–7、端口 7000、vLLM 残留、model path、
`/proc/meminfo`。`MemAvailable >= 412316860416` 且 swap used=0；不得为过门改容量或启用 swap。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
TMP_AUDIT_POINTER=/tmp/opencode/p8_2_k1a_r3_r1_preflight_current_2026_0718.path
test -f "${TMP_AUDIT_POINTER}"
TMP_AUDIT=$(cat "${TMP_AUDIT_POINTER}")
test -n "${TMP_AUDIT}"
test -d "${TMP_AUDIT}"

ps -eo pid,ppid,pgid,stat,cmd | grep -E '#[0-7]#' > "${TMP_AUDIT}/keep_alive_before.txt"
npu-smi info > "${TMP_AUDIT}/npu_before.txt"
ss -ltnp | grep ':7000' > "${TMP_AUDIT}/port_7000_before.txt" || true
ps -eo pid,ppid,pgid,stat,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' > "${TMP_AUDIT}/vllm_before.txt" || true
cat /proc/meminfo > "${TMP_AUDIT}/meminfo_before.txt"
test ! -s "${TMP_AUDIT}/port_7000_before.txt"
test ! -s "${TMP_AUDIT}/vllm_before.txt"
test -d "${MODEL_PATH}"
test "$(find "${MODEL_PATH}" -maxdepth 1 -type f | wc -l)" -gt 0

python3 - "${TMP_AUDIT}/keep_alive_before.txt" "${TMP_AUDIT}/meminfo_before.txt" <<'PY'
from pathlib import Path
import sys

markers = Path(sys.argv[1]).read_text().splitlines()
assert len(markers) >= 8
assert all(any(f"#{device}#" in row for row in markers) for device in range(8))
values = {}
for line in Path(sys.argv[2]).read_text().splitlines():
    key, raw = line.split(":", 1)
    values[key] = int(raw.strip().split()[0]) * 1024
assert values["MemAvailable"] >= 412316860416
assert values["SwapTotal"] == values["SwapFree"]
print(f"mem_available_bytes={values['MemAvailable']}")
print("resource_gate=pass")
PY

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
~~~

本节失败给 `blocked_p8_2_k1a_r3_r1_source_or_resource_gate` 并停止。不得清理未知进程或启动 vLLM。

## 4. 唯一 NPU lifecycle：安全退 keep-alive、六请求、清理与恢复

只有前三节全部 green 才执行。仅从真实 `#[0-7]#` marker 反查 keep-alive PGID，并排除当前 shell PGID；
不得触碰无关进程。无论 runner 成败，trap 都必须使用官方脚本恢复 0–7 卡。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0718_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r1_simple_cpu_offload.sh
KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
TMP_AUDIT_POINTER=/tmp/opencode/p8_2_k1a_r3_r1_preflight_current_2026_0718.path
test -f "${TMP_AUDIT_POINTER}"
TMP_AUDIT=$(cat "${TMP_AUDIT_POINTER}")
test -d "${TMP_AUDIT}"
KEEP_ALIVE_STOPPED=0
MARKER_COUNT_BEFORE=0

restore_keep_alive() {
  local restore_exit=0
  if test "${KEEP_ALIVE_STOPPED}" -eq 1; then
    bash "${KEEP_ALIVE_SCRIPT}" 0 1 2 3 4 5 6 7 \
      > "${TMP_AUDIT}/keep_alive_restore_stdout.txt" \
      2> "${TMP_AUDIT}/keep_alive_restore_stderr.txt" || restore_exit=$?
    printf '%s\n' "${restore_exit}" > "${TMP_AUDIT}/keep_alive_restore_exit_code.txt"
    sleep 5
  fi
  return "${restore_exit}"
}
trap restore_keep_alive EXIT

test ! -e "${RESULT_DIR}"
test -f "${RUNNER}"
test -f "${KEEP_ALIVE_SCRIPT}"
ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' > "${TMP_AUDIT}/keep_alive_markers_before.txt"
MARKER_COUNT_BEFORE=$(wc -l < "${TMP_AUDIT}/keep_alive_markers_before.txt" | tr -d ' ')
test "${MARKER_COUNT_BEFORE}" -ge 8
mapfile -t KEEP_ALIVE_PGIDS < <(awk '{print $3}' "${TMP_AUDIT}/keep_alive_markers_before.txt" | sort -n -u)
test "${#KEEP_ALIVE_PGIDS[@]}" -ge 1
CURRENT_PGID=$(ps -o pgid= -p $$ | tr -d ' ')
printf '%s\n' "${KEEP_ALIVE_PGIDS[@]}" > "${TMP_AUDIT}/keep_alive_pgids.txt"
for pgid in "${KEEP_ALIVE_PGIDS[@]}"; do
  test "${pgid}" != "${CURRENT_PGID}"
  test "${pgid}" -gt 1
  kill -TERM -- "-${pgid}"
done
KEEP_ALIVE_STOPPED=1

for _ in $(seq 1 60); do
  survivor_count=0
  while read -r pgid; do
    if ps -eo pgid= | awk -v wanted="${pgid}" '$1 == wanted {found=1} END {exit !found}'; then
      survivor_count=$((survivor_count + 1))
    fi
  done < "${TMP_AUDIT}/keep_alive_pgids.txt"
  test "${survivor_count}" -eq 0 && break
  sleep 1
done
test "${survivor_count}" -eq 0
npu-smi info > "${TMP_AUDIT}/npu_after_keep_alive_stop.txt"
grep -F 'No running processes found' "${TMP_AUDIT}/npu_after_keep_alive_stop.txt" >/dev/null
test -z "$(ss -ltnp | grep ':7000' || true)"

set +e
bash "${RUNNER}" "${RESULT_DIR}" > "${TMP_AUDIT}/runner_stdout.txt" 2> "${TMP_AUDIT}/runner_stderr.txt"
RUNNER_EXIT=$?
set -e
printf '%s\n' "${RUNNER_EXIT}" > "${TMP_AUDIT}/runner_exit_code.txt"

restore_keep_alive
KEEP_ALIVE_STOPPED=0
trap - EXIT
test "$(cat "${TMP_AUDIT}/keep_alive_restore_exit_code.txt")" = 0

for _ in $(seq 1 60); do
  ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' > "${TMP_AUDIT}/keep_alive_after.txt"
  MARKER_COUNT_AFTER=$(wc -l < "${TMP_AUDIT}/keep_alive_after.txt" | tr -d ' ')
  test "${MARKER_COUNT_AFTER}" -eq "${MARKER_COUNT_BEFORE}" && break
  sleep 1
done
test "${MARKER_COUNT_AFTER}" -eq "${MARKER_COUNT_BEFORE}"
python3 - "${TMP_AUDIT}/keep_alive_after.txt" <<'PY'
from pathlib import Path
import sys

rows = Path(sys.argv[1]).read_text().splitlines()
assert all(any(f"#{device}#" in row for row in rows) for device in range(8))
PY
printf 'true\n' > "${TMP_AUDIT}/keep_alive_restored_exact.txt"
npu-smi info > "${TMP_AUDIT}/npu_after.txt"
ss -ltnp | grep ':7000' > "${TMP_AUDIT}/port_7000_after.txt" || true
ps -eo pid,ppid,pgid,stat,cmd | grep -E '[v]llm serve|[V]LLM::EngineCore' > "${TMP_AUDIT}/vllm_after.txt" || true
test ! -s "${TMP_AUDIT}/port_7000_after.txt"
test ! -s "${TMP_AUDIT}/vllm_after.txt"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
printf 'runner_exit=%s\n' "${RUNNER_EXIT}"
~~~

runner 只能执行一个 fresh lifecycle：

~~~text
1. warmup              4096+64
2. prime              32768+64
3. pressure          131072+64
4. restore_follower   32768+64
5. repeat_follower    32768+64
6. isolated_control   32768+64
~~~

所有请求固定 `concurrency=1 / temperature=0 / ignore_eos=true / min_tokens=max_tokens=64 /
streaming=true`，零 retry、不得第 7 请求。body 在 server start 前冻结 token count/bytes/SHA-256，
不保存或外发 generated text/token IDs。

server argv 固定 W8A8、TP8+EP、MTP `num_speculative_tokens=1`、`FULL_DECODE_ONLY`、
`max_model_len=135168`、`max_num_batched_tokens=4096`、`max_num_seqs=1`、block size=128、
Chunked Prefill on、Prefix Cache on、完整 R2 repair。容量配置必须逐字为：

~~~json
{
  "kv_connector": "SimpleCPUOffloadConnector",
  "kv_role": "kv_both",
  "kv_connector_extra_config": {
    "cpu_bytes_to_use": 3444834304,
    "cpu_bytes_to_use_per_rank": 430604288,
    "lazy_offload": false
  }
}
~~~

不得改成相邻容量、32 GiB/rank、自动 fallback、第二次 lifecycle 或 allocator probe。task-local observer
只记录 scheduler CPU hit/load/store 和每 worker copy submit/completion，不改 scheduler 决策、block list、
copy 参数、stream 或同步语义。

## 5. 原位分级、候选清单与停止边界

runner 结束后只读解析结果，不重跑。先验证 exact task/config/request/trace/repair/cleanup：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0718_run01
TMP_AUDIT_POINTER=/tmp/opencode/p8_2_k1a_r3_r1_preflight_current_2026_0718.path
test -f "${TMP_AUDIT_POINTER}"
TMP_AUDIT=$(cat "${TMP_AUDIT_POINTER}")
test -d "${RESULT_DIR}"
test -d "${TMP_AUDIT}"

python3 - "${RESULT_DIR}" "${TMP_AUDIT}" <<'PY'
from pathlib import Path
import csv
import hashlib
import json
import sys

root, audit = map(Path, sys.argv[1:])
grading = json.loads((root / "grading_inputs.json").read_text())
connector = json.loads((root / "connector_resolution_summary.json").read_text())
trace = json.loads((root / "transfer_trace_summary.json").read_text())
host = json.loads((root / "host_memory_summary.json").read_text())
environment = json.loads((root / "environment_and_hashes.json").read_text())
rows = list(csv.DictReader((root / "request_summary.tsv").open(), delimiter="\t"))

assert grading["task_id"] == "p8_2_k1a_r3_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0718"
assert grading["cpu_bytes_to_use"] == 3444834304
assert grading["cpu_bytes_to_use_per_rank"] == 430604288
assert grading["accepted_capacity_exact"] is True
assert connector["resolved_cpu_capacity_exact"] is True
assert connector["cpu_bytes_to_use"] == 3444834304
assert connector["cpu_bytes_to_use_per_rank"] == 430604288
assert host["configured_cpu_tier_bytes_total"] == 3444834304
assert host["configured_cpu_tier_bytes_per_rank"] == 430604288
assert environment["server_command_sha256"] == "418d2796ec2dd15ab7504c264a6635a50d064cb7b6425f809cbfba550d2f5bb0"
assert len(rows) == 6
assert [row["k1a_role"] for row in rows] == [
    "warmup", "prime", "pressure", "restore_follower", "repeat_follower", "isolated_control"
]
assert grading["request_count"] == 6
assert grading["cleanup"] == "clean"
assert (audit / "keep_alive_restored_exact.txt").read_text().strip() == "true"

candidate_names = (
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
)
files = {}
for name in candidate_names:
    path = root / name
    if path.is_file():
        files[name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sensitivity": "bounded_operational_metadata_no_content_or_token_ids",
        }
total = sum(row["bytes"] for row in files.values())
assert total <= 71680, total
manifest = {
    "schema_version": "p8_2_k1a_r3_r1_candidate_manifest_v1",
    "result_root": str(root),
    "files": files,
    "candidate_file_count": len(files),
    "candidate_total_bytes": total,
    "max_total_bytes": 71680,
    "result_transfer_authorized": False,
}
(root / "candidate_manifest.server_local.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n"
)
print(json.dumps({
    "server_grade": grading["server_grade"],
    "successful_request_count": grading["successful_request_count"],
    "d2h_worker_count": trace["d2h_worker_count"],
    "h2d_worker_count": trace["h2d_worker_count"],
    "candidate_total_bytes": total,
}, sort_keys=True))
PY
~~~

分级严格为：

- repository/source/provenance/resource 门失败：`blocked_p8_2_k1a_r3_r1_source_or_resource_gate`；
- server 启动后 0/6 成功：`red_p8_2_k1a_r3_r1_no_success`；
- 请求结构不完整或只有部分成功：`yellow_p8_2_k1a_r3_r1_partial`；
- 6/6 成功且 8/8 D2H store 完整，但没有 8/8 H2D restore：
  `yellow_p8_2_k1a_r3_r1_store_only_no_restore`；这是有效负结果，不得 retry；
- request/connector/capacity/R2 repair/MTP/health/queue/cleanup 任一证据不完整：
  `red_p8_2_k1a_r3_r1_transfer_evidence_incomplete`；
- 只有 6/6 首次成功、accepted capacity exact、8/8 worker D2H submit+complete、8/8 worker H2D
  submit+complete、restore scheduler CPU hit/load schedule/load complete、R2/MTP/queue/health/cleanup/keep-alive
  全过，才给 `candidate_green_p8_2_k1a_r3_r1_simple_cpu_offload_store_restore`。

candidate green 也只证明该冻结 lifecycle 的双向机制，不是 performance reference、加速收益、通用支持、
K2 解锁或硬件归因。服务器只能给 candidate；必须由开发机独立复核小结果包后决定正式等级。

## 6. 最终报告与传输边界

最终报告必须给出：同步前后 HEAD/origin/ahead-behind/tracked；R2 accepted provenance；安装态 source/import；
资源门；keep-alive stop/restore；runner/mode/finalize exit；6 个 slot 的 HTTP/token/SSE/MTP/prefix 摘要；
resolved connector/capacity；D2H/H2D worker/bytes/completion；repair/health/queue；cleanup；最终 grade。

同时报告 `RESULT_DIR` 与 `candidate_manifest.server_local.json` 的完整文件清单、逐文件 bytes/SHA-256/
sensitivity、总量，以及可用 `email / upload-api / server-local` 和一个推荐理由。当前
`result_transfer_authorized:false`：不得发送邮件、调用 upload-api、复制到 Inbox 或自动切换渠道。
raw logs、metrics、trace、request bodies、generated content/token IDs 全部留服务器。

完成后停止等待：`next_task_authorized:false`。不得自动重跑、改变容量、进入 K2/P8.3-I1/P8.4/P8.5/P9。
