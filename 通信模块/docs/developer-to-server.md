# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R3-R2-R2 parent forensics + source semantics + conditional replay

~~~text
task_id: p8_2_k1a_r3_r2_r2_deepseek_v4_flash_forensic_replay_2026_0720
execution_mode: authorized_parent_forensics_source_semantics_and_conditional_same_capacity_single_lifecycle
server_sync_review_authorized: true
parent_offline_forensics_authorized: true
source_semantics_audit_authorized: true
installed_source_and_import_probe_authorized: true
npu_execution_authorized: true
keep_alive_stop_and_restore_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
formal_model_lifecycle_count_max: 1
model_request_count_max: 6
request_retry_count_exact: 0
result_directory_creation_authorized: true
runtime_overlay_authorized: true
observer_authorized: true
observer_mode: observe_only_rethrow_original_exceptions
runtime_behavior_patch_authorized: false
capacity_search_authorized: false
second_capacity_point_authorized: false
second_lifecycle_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
runtime_or_dependency_mutation_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
next_task_authorized: false
no_k2_k3_k4_p8_3_i1_p8_4_p8_5_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

## 0. 背景、直接判断和停止边界

parent `P8.2-K1A-R3-R2-R1` 已经通过 repository、R2 accepted-capacity、frozen installed
source/import、connector 和 resource gate，并在同一冻结配置上启动服务。实际请求是 `2 sent / 1
success / 6 planned`：`4096+64` warmup 成功，`32768+64` prime 失败后首错即停；8 worker
合计提交 `403691520` D2H bytes，但 completion=`0/8`，H2D 未启动，cleanup 与
keep-alive restore 均 clean。开发机只接受：

~~~text
parent_grade=yellow_p8_2_k1a_r3_r2_r1_partial
parent_claim_boundary=deepseek_tp8_ep_mtp_single_lifecycle_d2h_store_h2d_restore_mechanism_only
parent_offload_store_evidence_accepted=false
parent_offload_restore_evidence_accepted=false
parent_performance_reference_accepted=false
~~~

已下载的 12 文件足够给 yellow，但不足以判断 prime 的直接首错：
`first_failure_excerpt.txt` 只有 grade，`request_summary.tsv` 没有 HTTP、token/SSE、health-after、
queue-after、failed predicate 或 request-error 摘录。本任务因此必须先在原服务器结果树上做离线
forensics，再审计 frozen SimpleCPUOffload scheduler/worker/copy surface。

只有同时满足以下条件，才可停 keep-alive 并执行一个新 lifecycle：

- `source_evidence_unchanged=true`；
- `source_semantics_gate=pass`；
- parent failure class 只能是
  `transfer_completion_absent_without_direct_exception` 或 `insufficient_parent_evidence`；
- 不存在已证明的 source/config/resource/runtime 直接首错。

若分类为 `http_or_client_error`、`server_process_or_health_loss` 或
`offload_runtime_exception`，则给
`blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure`，在零 NPU 处停止并报告证据；不得用重跑
代替诊断。

如果进入 replay，仍固定 vLLM `0.22.1+empty@0decac0d...`、vLLM-Ascend
`0.22.1rc1@5f6faa0c...`、W8A8、TP8+EP、MTP speculative token=`1`、
`FULL_DECODE_ONLY`、Prefix Cache on、Chunked Prefill on、R2 hybrid-KV repair、
`max_model_len=135168`、`max_num_batched_tokens=4096`、`max_num_seqs=1`、block size=`128`、
canonical argv hash=`8301f4c4...1bde6`、原六个 body/顺序和唯一 accepted capacity：

~~~text
required_restore_tokens=16384
required_cpu_blocks=128
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
request_order=warmup,prime,pressure,restore_follower,repeat_follower,isolated_control
~~~

新 observer 只记录 `device_copy_launch_returned`、`device_copy_launch_failed` 和
`transfer_poll_failed`，对异常必须原样 re-raise；不得吞异常、retry、改 scheduler decision、改 copy
parameter 或修复 runtime 行为。

已关闭 lineage 保持不变：P6.3B-R4-R1=`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`，
P8.1-R1=`green_p8_1_r1_official_mtp_observe_only_matrix`，P8.2-K0 green，K1 legacy
`blocked_p8_2_k1_frozen_stack_import_incompatible`，K1A-R2=`ready_p8_2_k1a_r2_allocator_capacity`，
K1A-R3=`blocked_p8_2_k1a_r3_source_or_provenance_gate`，P8.3-I0-R1=
`green_p8_3_i0_r1_unclassified_taxonomy`，P6.3C=`blocked_p6_3c_not_strict_single_variable`。
本任务不得进入 K2，不得进入 P8.3-I1、P8.4、P8.5 或 P9。

## 1. 同步、冻结仓库与本地合同门（零 NPU）

只允许从干净 `main` fast-forward 同步。不得 reset、stash、server commit、发布操作或使用
server-local 同步脚本。本节失败不得创建 `FORENSICS_ROOT/RESULT_DIR`，不得停 keep-alive。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_2_k1a_r3_r2_r2_deepseek_v4_flash_forensic_replay_2026_0720
PARENT_RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
FORENSICS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_parent_forensics_2026_0720_run01
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_deepseek_v4_flash_forensic_replay_2026_0720_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_simple_cpu_offload.sh
FORENSICS=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_failure_forensics.py
RUNTIME_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
cd "${REPO_ROOT}"

git status --short --branch --untracked-files=no
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
test ! -e "${FORENSICS_ROOT}"
test ! -e "${RESULT_DIR}"

python3 - <<'PY'
from pathlib import Path
import hashlib

expected = {
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r2_r2_forensic_replay_audit.yaml": "bf88a5541d5c6425be78685e846da18958ec6c13a31b30e78224753d7b304129",
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r3_r2_r2_forensic_replay.yaml": "02b83dd1f94d710939f8d1c5c891ddf610b09ec5decba75ba378c0e1e1ec0768",
    "tools/inference_contracts/p8_2_k1a_failure_forensics.py": "78ab0e6e4f01b97f7502a1c1851252512c90bcb3dfcee8f7d2bc65e6d189302f",
    "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "55af5e5a40f94756bc115b3b146b55699d6d49c85a8a04f038ee2363b98c03a6",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "d687e93e69b13e6ee0852fa2da3bf6c25dc1eda74ccf9bc1b50e08b5cd3f88fa",
    "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py": "d1af39ef7622bee62b6b10f774ef012f306d0bc5b0318666bc6d41df786836e3",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_simple_cpu_offload.sh": "6ad128cd5d70b3a813ea2ecd7d7d2def8c46745984e46ac4a7ea21fc93d59005",
}
for relative, wanted in expected.items():
    got = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
    assert got == wanted, (relative, got, wanted)
print(f"frozen_repo_hash_gate=pass files={len(expected)}")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_forensics.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_forensic_replay.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_portable_argv.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r1_installed_source_gate.py -q
python3 -m py_compile \
  "${FORENSICS}" \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
bash -n "${RUNNER}" tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh

P8_2_K1A_AUDIT_ONLY=1 bash "${RUNNER}" /tmp/p8_2_k1a_r3_r2_r2_top_audit \
  > /tmp/p8_2_k1a_r3_r2_r2_top_audit.txt
grep -Fx "task_id=${TASK_ID}" /tmp/p8_2_k1a_r3_r2_r2_top_audit.txt
grep -Fx 'cpu_bytes_to_use=3444834304' /tmp/p8_2_k1a_r3_r2_r2_top_audit.txt
grep -Fx 'cpu_bytes_to_use_per_rank=430604288' /tmp/p8_2_k1a_r3_r2_r2_top_audit.txt
grep -Fx 'server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6' \
  /tmp/p8_2_k1a_r3_r2_r2_top_audit.txt
test ! -e /tmp/p8_2_k1a_r3_r2_r2_top_audit
test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节任一失败：`blocked_p8_2_k1a_r3_r2_r2_repository_contract_gate`，立即停止。

## 2. parent 原始证据不可变盘点与离线 forensics（零 NPU）

本节只读 parent 结果树，输出到新 `FORENSICS_ROOT`；不得在 parent 树内 refinalize、删除、改名或
补文件。先复核已下载的 12 个 bounded 文件哈希，再要求 raw request/log/trace/metrics 存在。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
PARENT_RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
FORENSICS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_parent_forensics_2026_0720_run01
FORENSICS=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_failure_forensics.py
cd "${REPO_ROOT}"

test -d "${PARENT_RESULT_DIR}"
test ! -e "${FORENSICS_ROOT}"
python3 - "${PARENT_RESULT_DIR}" <<'PY'
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
expected = {
    "cleanup_status.txt": (6, "2e22da2ab13713309ac75219e525b8e06ed02f3f1963b8feef203fa25827f93d"),
    "connector_resolution_summary.json": (1130, "beb0044755e48b13c27f9d00a5dce063cefca43c93396f8d23bbf46a6acab4e0"),
    "environment_and_hashes.json": (3310, "9af109a372343aaff6e7b9a8b59003706e21ab85aced0de0da79d0675748fd85"),
    "first_failure_excerpt.txt": (33, "9543720eababea9fbb0c64ff3df8cc381c8843841c11ab1d890a537b803c2183"),
    "grading_inputs.json": (1379, "5aa2a0ba0697ed0934c75ebefc798defd479430eb070e54fbe58a32ffa3289d9"),
    "host_memory_summary.json": (358, "9a6f7496cdc1d6c24d89889335d34721e61a19b1d770501398b542f4f5c6036f"),
    "mtp_queue_health_summary.json": (160, "2c6469c2c947510516394ff82f9964c6943112db22aae00b897405ac6307ec10"),
    "repair_diagnostic_summary.json": (611, "459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862"),
    "request_body_manifest.json": (3526, "bce2e272c2d6d3fc1c59a999ebd435f704562d3d8edcfa754f2d21c67c207b7d"),
    "request_summary.tsv": (408, "9a18833a9945ed8ef98b95636603cf45f097974c15c069cd4ce96f68c36b0629"),
    "result_summary.md": (6414, "3696c8b348011669e91450fbfe2dd151eacd02208deb1168a5392bbd19532304"),
    "transfer_trace_summary.json": (478, "934071445789c2079f90ecc080f9ecd8236c37e17606a164815b0820cb61255b"),
}
for name, (size, wanted) in expected.items():
    path = root / name
    assert path.is_file(), path
    assert path.stat().st_size == size, (path, path.stat().st_size, size)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == wanted, path
assert sum(size for size, _ in expected.values()) == 17813
print("parent_bounded_evidence_gate=pass files=12 bytes=17813")
PY

test -f "${PARENT_RESULT_DIR}/modes/prefix_cache_on/raw_request_results.jsonl"
test -f "${PARENT_RESULT_DIR}/runtime/vllm_server.log"
test "$(find "${PARENT_RESULT_DIR}/runtime/offload_trace" -type f -name 'trace.*.jsonl' | wc -l)" -ge 1
test -f "${PARENT_RESULT_DIR}/modes/prefix_cache_on/raw_metrics/lifecycle_01_prime_before.prom"
test -f "${PARENT_RESULT_DIR}/modes/prefix_cache_on/raw_metrics/lifecycle_01_prime_after.prom"

python3 "${FORENSICS}" extract \
  --source-result-dir "${PARENT_RESULT_DIR}" \
  --output-dir "${FORENSICS_ROOT}" \
  > "${FORENSICS_ROOT}.stdout.json"

python3 - "${FORENSICS_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
diagnostic = json.loads((root / "failure_diagnostic_summary.json").read_text())
provenance = json.loads((root / "source_evidence_provenance.json").read_text())
timeline = json.loads((root / "transfer_trace_timeline.json").read_text())
manifest = json.loads((root / "candidate_manifest.server_local.json").read_text())
assert provenance["source_evidence_unchanged"] is True
assert provenance["before"] == provenance["after"]
assert diagnostic["failed_request_id"] == "lifecycle_01_prime"
assert diagnostic["cause_proven_as_unique"] is False
assert diagnostic["failure_classification"] in {
    "http_or_client_error",
    "server_process_or_health_loss",
    "offload_runtime_exception",
    "transfer_completion_absent_without_direct_exception",
    "insufficient_parent_evidence",
}
assert timeline["event_count"] == 28
assert manifest["missing_candidate_files"] == []
assert manifest["candidate_total_bytes"] <= 71680
assert manifest["result_transfer_authorized"] is True
assert manifest["transfer_method_selected"] is False
print(json.dumps({
    "parent_failure_classification": diagnostic["failure_classification"],
    "formal_replay_allowed": diagnostic["formal_replay_allowed"],
    "source_evidence_unchanged": provenance["source_evidence_unchanged"],
    "trace_event_count": timeline["event_count"],
}, sort_keys=True))
PY
~~~

请把上述 JSON 精确回报。parent 结果树的 before/after aggregate 必须一致。本节任一硬门失败：
`blocked_p8_2_k1a_r3_r2_r2_parent_evidence_gate`，不得进入 NPU 部分。

## 3. frozen source semantics 与 import/registration 审计（零 NPU）

审计精确安装态与 frozen vLLM source，不使用其他 vLLM-Ascend checkout 作为身份，不修改
site-packages。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
FORENSICS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_parent_forensics_2026_0720_run01
FORENSICS=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_failure_forensics.py
AUDITOR=${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py
RUNTIME_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
VLLM_BASE=/data/node0_disk1/vllm-0.22.1
VLLM_ROOT=${VLLM_BASE}/vllm
VLLM_ASCEND_SITE=${RUNTIME_PREFIX}/lib/python3.11/site-packages
VLLM_ASCEND_ROOT=${VLLM_ASCEND_SITE}/vllm_ascend
RUNTIME_PYTHON=${RUNTIME_PREFIX}/bin/python
cd "${REPO_ROOT}"

test "$(git -C /data/node0_disk1/vllm-0.22.1 rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398
test -z "$(git -C /data/node0_disk1/vllm-0.22.1 status --porcelain --untracked-files=no)"
"${RUNTIME_PYTHON}" "${AUDITOR}" installed-source-audit \
  --vllm-root "${VLLM_BASE}" \
  --vllm-ascend-root "${VLLM_ASCEND_SITE}" \
  --output "${FORENSICS_ROOT}/installed_source_audit.json"
"${RUNTIME_PYTHON}" "${FORENSICS}" source-audit \
  --vllm-root "${VLLM_ROOT}" \
  --vllm-ascend-root "${VLLM_ASCEND_ROOT}" \
  --output "${FORENSICS_ROOT}/offload_source_semantics.json"

"${RUNTIME_PYTHON}" - "${FORENSICS_ROOT}/runtime_import_probe.json" <<'PY'
from pathlib import Path
import importlib.metadata
import json
import sys

from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory
from vllm_ascend.distributed.kv_transfer import register_connector
from vllm_ascend.simple_kv_offload.copy_backend import NPUDmaCopyBackend
from vllm_ascend.simple_kv_offload.worker import SimpleCPUOffloadNPUWorker

register_connector()
connector = KVConnectorFactory.get_connector_class_by_name("SimpleCPUOffloadConnector")
value = {
    "vllm_version": importlib.metadata.version("vllm"),
    "vllm_ascend_version": importlib.metadata.version("vllm-ascend"),
    "connector_class": connector.__name__,
    "copy_backend_class": NPUDmaCopyBackend.__name__,
    "worker_class": SimpleCPUOffloadNPUWorker.__name__,
    "import_registration_gate": "pass",
    "npu_started": False,
    "vllm_server_started": False,
    "model_request_sent": False,
}
assert value["vllm_version"] == "0.22.1+empty"
assert value["vllm_ascend_version"] == "0.22.1rc1"
assert value["connector_class"] == "AscendSimpleCPUOffloadConnector"
Path(sys.argv[1]).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY

python3 - "${FORENSICS_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
installed = json.loads((root / "installed_source_audit.json").read_text())
source = json.loads((root / "offload_source_semantics.json").read_text())
diagnostic = json.loads((root / "failure_diagnostic_summary.json").read_text())
assert installed["source_hash_gate"] is True
assert len(installed["source_inventory"]) == 9
assert all(row["matched"] is True for row in installed["source_inventory"])
assert installed["ascend_connector_override_present"] is True
assert installed["supports_hma_present"] is True
assert installed["hybrid_multi_group_source_support_present"] is True
assert installed["npu_d2h_h2d_backend_present"] is True
assert source["source_semantics_gate"] == "pass"
assert source["source_file_count"] == 4
assert source["required_symbols_present"] is True
allowed = {
    "transfer_completion_absent_without_direct_exception",
    "insufficient_parent_evidence",
}
formal_replay_allowed = (
    diagnostic["formal_replay_allowed"] is True
    and diagnostic["failure_classification"] in allowed
)
(root / "formal_replay_allowed.txt").write_text(
    ("true" if formal_replay_allowed else "false") + "\n"
)
print("installed_source_hash_gate=pass")
print(f"source_semantics_gate={source['source_semantics_gate']}")
print(f"formal_replay_allowed={str(formal_replay_allowed).lower()}")
PY

test -z "$(git status --porcelain --untracked-files=no)"
~~~

source/import 失败：`blocked_p8_2_k1a_r3_r2_r2_source_or_resource_gate`，不停 keep-alive。

## 4. 条件分支：已证直接首错即停，否则执行唯一 replay

先读取结论，不得由人工覆盖：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
FORENSICS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_parent_forensics_2026_0720_run01
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_deepseek_v4_flash_forensic_replay_2026_0720_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_simple_cpu_offload.sh
KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
FORMAL_REPLAY_ALLOWED=$(cat "${FORENSICS_ROOT}/formal_replay_allowed.txt")

if test "${FORMAL_REPLAY_ALLOWED}" = true; then
  test ! -e "${RESULT_DIR}"
else
  printf '%s\n' blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure \
    > "${FORENSICS_ROOT}/task_grade.txt"
  printf '%s\n' 0 > "${FORENSICS_ROOT}/formal_model_lifecycle_count.txt"
  printf '%s\n' 0 > "${FORENSICS_ROOT}/model_request_count.txt"
fi
~~~

若为 `false`，跳过本节余下全部 NPU 命令，直接进入第 5 节包装与报告。

若为 `true`，才执行下列唯一 lifecycle。只从 `#[0-7]#` marker 提取 keep-alive PGID，
不得触碰其他进程组。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
FORENSICS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_parent_forensics_2026_0720_run01
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_deepseek_v4_flash_forensic_replay_2026_0720_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_simple_cpu_offload.sh
KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
test "$(cat "${FORENSICS_ROOT}/formal_replay_allowed.txt")" = true
cd "${REPO_ROOT}"
KEEP_ALIVE_STOPPED=0

cleanup() {
  set +e
  if test "${KEEP_ALIVE_STOPPED}" -eq 1; then
    bash "${KEEP_ALIVE_SCRIPT}" 0 1 2 3 4 5 6 7 \
      > "${FORENSICS_ROOT}/keep_alive_restore_stdout.txt" \
      2> "${FORENSICS_ROOT}/keep_alive_restore_stderr.txt"
    restore_exit=$?
    printf '%s\n' "${restore_exit}" > "${FORENSICS_ROOT}/keep_alive_restore_exit_code.txt"
    sleep 10
    ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' \
      > "${FORENSICS_ROOT}/keep_alive_markers_after.txt"
    npu-smi info > "${FORENSICS_ROOT}/npu_after.txt" 2>&1
    test "${restore_exit}" -eq 0
    test "$(wc -l < "${FORENSICS_ROOT}/keep_alive_markers_after.txt" | tr -d ' ')" = 16
    for card in 0 1 2 3 4 5 6 7; do
      grep -F "#${card}#" "${FORENSICS_ROOT}/keep_alive_markers_after.txt" >/dev/null
    done
    printf '%s\n' true > "${FORENSICS_ROOT}/keep_alive_restored_exact.txt"
  fi
  test -z "$(ss -ltnp | grep ':7000' || true)"
  test -z "$(pgrep -af '[v]llm.*serve' || true)"
}
trap cleanup EXIT

test -f "${KEEP_ALIVE_SCRIPT}"
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(pgrep -af '[v]llm.*serve' || true)"
ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' \
  > "${FORENSICS_ROOT}/keep_alive_markers_pre_stop.txt"
test "$(wc -l < "${FORENSICS_ROOT}/keep_alive_markers_pre_stop.txt" | tr -d ' ')" = 16
CURRENT_PGID=$(ps -o pgid= -p $$ | tr -d ' ')
mapfile -t KEEP_ALIVE_PGIDS < <(awk '{print $3}' "${FORENSICS_ROOT}/keep_alive_markers_pre_stop.txt" | sort -u)
test "${#KEEP_ALIVE_PGIDS[@]}" -ge 1
KEEP_ALIVE_STOPPED=1
for pgid in "${KEEP_ALIVE_PGIDS[@]}"; do
  test -n "${pgid}"
  test "${pgid}" != "${CURRENT_PGID}"
  kill -TERM -- "-${pgid}"
done
for _ in $(seq 1 60); do
  if ! ps -eo args= | grep -E '#[0-7]#' | grep -v grep >/dev/null; then
    break
  fi
  sleep 1
done
test -z "$(ps -eo args= | grep -E '#[0-7]#' | grep -v grep || true)"
npu-smi info > "${FORENSICS_ROOT}/npu_after_keep_alive_stop.txt"
grep -F 'No running processes found' "${FORENSICS_ROOT}/npu_after_keep_alive_stop.txt" >/dev/null

set +e
bash "${RUNNER}" "${RESULT_DIR}" \
  > "${FORENSICS_ROOT}/runner_stdout.txt" \
  2> "${FORENSICS_ROOT}/runner_stderr.txt"
RUNNER_EXIT=$?
set -e
printf '%s\n' "${RUNNER_EXIT}" > "${FORENSICS_ROOT}/runner_exit_code.txt"

test -d "${RESULT_DIR}"
test -f "${RESULT_DIR}/grading_inputs.json"
test -f "${RESULT_DIR}/failure_diagnostic_summary.json"
test -f "${RESULT_DIR}/first_failure_excerpt.txt"
test -f "${RESULT_DIR}/candidate_manifest.server_local.json"
test "$(cat "${RESULT_DIR}/cleanup_status.txt")" = clean
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(pgrep -af '[v]llm.*serve' || true)"
~~~

请求仍严格是：

~~~text
4K warmup -> 32K prime -> 131K pressure -> 32K restore_follower -> 32K repeat_follower -> 32K isolated_control
~~~

任一请求失败立即停，不得 retry、补发、第七请求、second lifecycle、capacity search 或改
runtime/body/argv。即使 replay 成功，parent yellow 也不改写。

## 5. 离线分级、合并候选清单、恢复与报告

本节不得重跑服务或请求。如果 replay 没执行，报告零 lifecycle/零 request、keep-alive
未扰动；如果执行，必须等 trap 完成恢复后再分级。

服务器 AI 在 `FORENSICS_ROOT/task_result_summary.md` 中必须写明：

- Git 同步前后 HEAD/origin/ahead-behind/tracked；
- parent tree before/after file count、bytes、aggregate SHA-256 和 `source_evidence_unchanged`；
- failed prime 的 HTTP/token/SSE/failed predicates/error excerpt/health/queue/MTP；
- 28 个 parent trace event 的 D2H submit/return/fail/poll/complete 时序；
- bounded vLLM failure log 窗口与 failure classification，`cause_proven_as_unique` 必须保留 false；
- nine-file frozen installed-source hash、four-file source semantics symbol 与 import/registration 结果；
- `formal_replay_allowed` 与执行/停止理由；
- 若 replay：runner/mode/finalizer exit、六 slot、connector/capacity、R2/MTP/queue/health、
  D2H/H2D worker/bytes/completion、observer exception event、cleanup/keep-alive restore；
- final grade 与 claim boundary。

最终分级只能是：

- parent 结果树不完整/发生改变：`blocked_p8_2_k1a_r3_r2_r2_parent_evidence_gate`；
- parent 已证直接失败类，未进 NPU：`blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure`；
- source/import/resource gate 失败：`blocked_p8_2_k1a_r3_r2_r2_source_or_resource_gate`；
- replay 启动后 0 成功：`red_p8_2_k1a_r3_r2_r2_no_success`；
- 部分请求成功或未达六请求结构：`yellow_p8_2_k1a_r3_r2_r2_partial`；
- 6/6 与 D2H complete 过、H2D restore 不过：`yellow_p8_2_k1a_r3_r2_r2_store_only_no_restore`；
- 请求/传输/观测证据不完整：`red_p8_2_k1a_r3_r2_r2_evidence_incomplete`；
- 只有 6/6 首次成功、8/8 D2H submit+complete、8/8 H2D submit+complete、restore CPU hit/load
  schedule/load complete、accepted capacity/canonical argv/R2/MTP/health/queue/cleanup/keep-alive 全过：
  `candidate_green_p8_2_k1a_r3_r2_r2_simple_cpu_offload_store_restore`。

然后构建一份 `FORENSICS_ROOT/task_candidate_manifest.server_local.json`：候选范围包含 offline
forensics 的 6 文件、`installed_source_audit.json`、`offload_source_semantics.json`、`runtime_import_probe.json`、
`task_result_summary.md`；如果 replay 实际运行，再加入 `RESULT_DIR/candidate_manifest.server_local.json`
中已列出的所有 bounded runtime candidate。每项必须记录 absolute path、bytes、SHA-256、
sensitivity=`bounded_operational_metadata_no_content_or_token_ids`；累计不超过 `71680 bytes`，
不得加入 raw log/metrics/trace/request body/generated content/token IDs。

完成后必须先回报精确 `task_result_summary.md` 路径、完整候选清单、逐文件 bytes/
SHA-256/sensitivity、总量、可用 `email / upload-api / server-local` 和一个推荐理由。
`result_transfer_authorized:true` 只表示该有界包具备传输资格，`transfer_method_selected:false`
表示当前未选渠道；未获用户对完整范围的新选择前，不得 email、upload-api 或复制到其他位置。
失败不重试，不自动换渠道。

最终复核 tracked 干净、端口 7000 空闲、无 vLLM 残留；如执行过 replay，还要证明 16 个
keep-alive marker 覆盖 8 卡已恢复。完成后停止等待 `next_task_authorized:false`，不得进入
K2，不得进入 P8.3-I1/P8.4/P8.5/P9。
