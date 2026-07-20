# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R3-R2-R2-R1-R1 source binding、异常 provenance 与条件式唯一 lifecycle

~~~text
task_id: p8_2_k1a_r3_r2_r2_r1_r1_deepseek_v4_flash_source_binding_provenance_replay_2026_0720
execution_mode: authorized_offline_source_binding_exception_provenance_gate_then_one_same_capacity_lifecycle
server_sync_review_authorized: true
parent_raw_evidence_read_authorized: true
offline_refinalization_authorized: true
source_semantics_audit_authorized: true
installed_source_and_import_probe_authorized: true
runtime_exception_provenance_audit_authorized: true
observer_mode: observe_only_rethrow_original_exceptions
npu_execution_authorized: true
keep_alive_stop_and_restore_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
formal_model_lifecycle_count_max: 1
model_request_count_max: 6
request_retry_count_exact: 0
result_directory_creation_authorized: true
runtime_overlay_authorized: true
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

## 0. 开发机判断、父级结论与不可变边界

上轮服务器任务已经执行完毕，不得原样重跑。必须保留它的正式 provenance：

~~~text
parent_task_id=p8_2_k1a_r3_r2_r2_r1_deepseek_v4_flash_observer_contract_replay_2026_0720
parent_server_grade=blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate
parent_formal_model_lifecycle_count=0
parent_model_request_count=0
parent_npu_started=false
parent_vllm_started=false
parent_cause_proven_as_unique=false
~~~

开发机已复核 11 个回包文件，共 `21828 bytes`，其清单与 SHA-256 完整。但 parent 有两个尚未关闭的
合同问题，不能直接把 `formal_lifecycle_allowed` 人工改成 true：

1. 冻结 `copy_backend.py` 不是直接定义 `copy_blocks`，而是
   `from vllm_ascend.simple_kv_offload.npu_mem_ops import copy_blocks`。旧 AST 只承认直接
   `FunctionDef`，因此产生 source-semantics 假阴性。新 auditor 必须同时证明 backend 的精确
   `ImportFrom` binding、`npu_mem_ops.py` 的直接定义和 runtime object identity。
2. parent 报告同时写了 `direct_runtime_exception_present=false` 和“worker TypeError 被
   multiproc_executor 捕获”，但回包没有 `request_time_log_excerpt.txt`。新任务必须直接读取服务器保留的
   parent raw `vllm_server.log`，由仓库工具生成有界 `runtime_exception_provenance.json`。只有确实没有直接
   exception，或所有 exception 都精确匹配已退役 observer 多传 `wait_event` 导致的
   `launch_copy` TypeError，才允许进入 NPU；任何未知 exception 都零 NPU 停止。

冻结 runtime、canonical argv、body、顺序、R2 hybrid-KV repair、observer 和 accepted capacity 不变：

~~~text
vllm=0.22.1+empty@0decac0d96c42b49572498019f0a0e3600f50398
vllm_ascend=0.22.1rc1@5f6faa0cb8830f667266f3b8121cd1383606f2a1
server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
required_cpu_blocks=128
required_restore_tokens=16384
request_order=warmup,prime,pressure,restore_follower,repeat_follower,isolated_control
~~~

W8A8、TP8+EP、MTP `num_speculative_tokens=1`、`FULL_DECODE_ONLY`、Prefix Cache on、Chunked
Prefill on、`max_model_len=135168`、`max_num_batched_tokens=4096`、`max_num_seqs=1`、block size 128
全部冻结。不得容量搜索、功能 patch、第二 lifecycle、第七请求或 retry；不得进入 K2、P8.3-I1、
P8.4、P8.5、P9。P6.3B-R4-R1、P8.1-R1、P8.2-K0、K1A-R2、P8.3-I0-R1 的已接受结论不撤销，
K1A-R3-R2-R1 partial yellow、R3-R2-R2 blocked 与 parent blocked 均保留。不得进入 P8.3-I1。

必须原样保留的关闭门和前序 lineage：

~~~text
P6.3B-R4-R1=green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
P6.3C=blocked_p6_3c_not_strict_single_variable
P8.1-R1=green_p8_1_r1_official_mtp_observe_only_matrix
P8.2-K0=green_p8_2_k0_order_balanced_prefix_cache_baseline
P8.2-K1=blocked_p8_2_k1_frozen_stack_import_incompatible
P8.2-K1A-candidate-path=SimpleCPUOffloadConnector
P8.2-K1A-R2=ready_p8_2_k1a_r2_allocator_capacity
P8.2-K1A-R3=blocked_p8_2_k1a_r3_source_or_provenance_gate
P8.2-K1A-R3-R2-R1=yellow_p8_2_k1a_r3_r2_r1_partial
parent_server_grade=blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure
P8.2-K1A-R3-R2-R2-R1=blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate
P8.3-I0-R1=green_p8_3_i0_r1_unclassified_taxonomy
~~~

## 1. 同步、冻结仓库和本地合同门（零 NPU）

只允许从 tracked-clean `main` 普通 fast-forward。不得覆盖服务器本地产物；本节失败不得创建
`TASK_ROOT`/`RESULT_DIR`，不得停止 keep-alive。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_2_k1a_r3_r2_r2_r1_r1_deepseek_v4_flash_source_binding_provenance_replay_2026_0720
PARENT_RUNTIME_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
PARENT_OBSERVER_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_r1_observer_contract_2026_0720_run01
TASK_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance_2026_0720_run01
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_r1_r1_deepseek_v4_flash_source_binding_provenance_replay_2026_0720_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_simple_cpu_offload.sh
FORENSICS=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_failure_forensics.py
AUDITOR=${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py
RUNTIME_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
RUNTIME_PYTHON=${RUNTIME_PREFIX}/bin/python
cd "${REPO_ROOT}"

git status --short --branch --untracked-files=no
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
test -d "${PARENT_RUNTIME_DIR}"
test -d "${PARENT_OBSERVER_ROOT}"
test ! -e "${TASK_ROOT}"
test ! -e "${RESULT_DIR}"

python3 - <<'PY'
from pathlib import Path
import hashlib

expected = {
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance_audit.yaml": "0c7db4cb0673a7575db3c4a1eb2600adcaf0cb0272b7a861f63a0b625efb8f17",
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance_replay.yaml": "2db8d8c31d78c1c807f44aa92942fae42448c4b32db30c16cf80268cc4c39939",
    "tools/inference_contracts/p8_2_k1a_failure_forensics.py": "4bc1d4f99a4c95e28cc31e249a660d978d51a874f218bba8ad3cfdd495862830",
    "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py": "a23147ce2b43c6b8bf2650a126465c70ea6e24711f63627fec5239a4b1d2710e",
    "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "d16157f71ecc8ee5b0b5a09e1f43d9a837841f5c30fdc3c9d2a70e2bb307101c",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "a9093f865e5045644df8ffa386bc162443f7ab6ad3121e3fed3556f92f9ff0b1",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "06e7c6ba2976418797a92110c406e79b938e2314394d39e6ca82519ef8261462",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh": "28065c30588413e839cd0195709b645e416b06aa91db361808b6ac72aff6edf4",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_simple_cpu_offload.sh": "a31a15e6067183d0eb98b38f78da5a56874752457d6adb044cd84611c111b439",
    "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch": "5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6",
    "tools/inference_contracts/canonicalize_server_argv.py": "c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d",
}
for relative, wanted in expected.items():
    got = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
    assert got == wanted, (relative, got, wanted)
print(f"frozen_repo_hash_gate=pass files={len(expected)}")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_simple_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_portable_argv.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r1_installed_source_gate.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_forensics.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_r1_observer_contract.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance.py -q
python3 -m py_compile "${FORENSICS}" "${AUDITOR}" \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
bash -n "${RUNNER}" tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
python3 - <<'PY'
from pathlib import Path
import yaml
for path in Path('benchmarks/deepseek_v4_flash').rglob('*.yaml'):
    yaml.safe_load(path.read_text(encoding='utf-8'))
print('deepseek_yaml_parse=pass')
PY

P8_2_K1A_AUDIT_ONLY=1 bash "${RUNNER}" /tmp/p8_2_k1a_r3_r2_r2_r1_r1_audit \
  > /tmp/p8_2_k1a_r3_r2_r2_r1_r1_audit.txt
grep -Fx "task_id=${TASK_ID}" /tmp/p8_2_k1a_r3_r2_r2_r1_r1_audit.txt
grep -Fx 'execution_mode=authorized_offline_source_binding_exception_provenance_gate_then_one_same_capacity_lifecycle' \
  /tmp/p8_2_k1a_r3_r2_r2_r1_r1_audit.txt
grep -Fx 'cpu_bytes_to_use=3444834304' /tmp/p8_2_k1a_r3_r2_r2_r1_r1_audit.txt
grep -Fx 'cpu_bytes_to_use_per_rank=430604288' /tmp/p8_2_k1a_r3_r2_r2_r1_r1_audit.txt
grep -Fx 'server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6' \
  /tmp/p8_2_k1a_r3_r2_r2_r1_r1_audit.txt
test ! -e /tmp/p8_2_k1a_r3_r2_r2_r1_r1_audit
test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节任一失败：`blocked_p8_2_k1a_r3_r2_r2_r1_r1_repository_contract_gate`，立即停止。

## 2. Parent 11 文件、原始结果树与异常 provenance（零 NPU）

本节才允许创建 `TASK_ROOT`；不得改 parent 目录。先 byte-for-byte 核对 parent 回包：

~~~bash
set -euo pipefail
cd "${REPO_ROOT}"

python3 - "${PARENT_OBSERVER_ROOT}" <<'PY'
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
expected = {
    "failed_request_sanitized.json": (2005, "c86abd46f9d9aa610a866e13ecd184a9d9f4a92a2e761ce3e4b9d0d264415f"),
    "failure_diagnostic_summary.json": (2233, "0e23efb7a181bed00e95dba2a506b7242daac6e219c8f03d8d453c78e4bea6d7"),
    "formal_lifecycle_allowed.txt": (6, "2ed27c1421e6928dbe13dbfdb5c59e1045b30341fe7ebe05700006bc5ac572c0"),
    "installed_source_audit.corrected.json": (3489, "3e82c711c93621e8e0608be2d9784db872f0c12612c1cd141b339aafbdd02ae8"),
    "offload_source_semantics.corrected.json": (3777, "a7fac461834b2ed8c4f01643b48843430cc5c07e0d13a16f40f10c7ee1b0dbaf"),
    "parent_server_grade_provenance.txt": (55, "95366c7310141ebee08727651b65b546f4493c38b098d4ff4b2e2f621ab426ad"),
    "request_time_correlation.json": (793, "5ea9d5d26c7aacb249b22a05401a0159a5182593284852f330e3fabc4a9898fc"),
    "runtime_method_resolution.json": (1733, "8d5a41dc4597cece6882399571f0ae5f272ccc83538fb3d767fc6db2e630b5eb"),
    "source_evidence_provenance.json": (686, "001049069362bfd3d2376ffe3818c4c7c1fe2ff70d78ff48aec04eb117dc5db3"),
    "task_grade.txt": (53, "d4dfa80b4bc8a9ad5ec12a4dc187ce3d194dcffa516994b41cfe3ab21a1cd639"),
    "task_result_summary.md": (6998, "3d7a863326c828708e4407543aa145254f3dfe9653dc07f426d4d3cdc00fc717"),
}
for name, (size, wanted) in expected.items():
    path = root / name
    assert path.is_file(), path
    assert path.stat().st_size == size, (name, path.stat().st_size, size)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == wanted, name
assert sum(size for size, _ in expected.values()) == 21828
print("parent_r3_r2_r2_r1_bounded_evidence_gate=pass files=11 bytes=21828")
PY

python3 - "${PARENT_RUNTIME_DIR}" <<'PY'
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
expected = {
    "cleanup_status.txt": "2e22da2ab13713309ac75219e525b8e06ed02f3f1963b8feef203fa25827f93d",
    "request_summary.tsv": "9a18833a9945ed8ef98b95636603cf45f097974c15c069cd4ce96f68c36b0629",
    "result_summary.md": "3696c8b348011669e91450fbfe2dd151eacd02208deb1168a5392bbd19532304",
}
for name, wanted in expected.items():
    path = root / name
    assert path.is_file(), path
    assert hashlib.sha256(path.read_bytes()).hexdigest() == wanted, name
assert (root / "runtime/vllm_server.log").is_file()
print("parent_runtime_direct_input_gate=pass files=3 plus_raw_log=true")
PY

test ! -e "${TASK_ROOT}"
"${RUNTIME_PYTHON}" "${FORENSICS}" extract \
  --source-result-dir "${PARENT_RUNTIME_DIR}" \
  --output-dir "${TASK_ROOT}" \
  > /tmp/p8_2_k1a_r3_r2_r2_r1_r1_refinalize.json
printf '%s\n' blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate \
  > "${TASK_ROOT}/parent_server_grade_provenance.txt"

set +e
"${RUNTIME_PYTHON}" "${FORENSICS}" runtime-log-audit \
  --log "${PARENT_RUNTIME_DIR}/runtime/vllm_server.log" \
  --output "${TASK_ROOT}/runtime_exception_provenance.json" \
  > /tmp/p8_2_k1a_r3_r2_r2_r1_r1_runtime_log_audit.json
RUNTIME_LOG_AUDIT_EXIT=$?
set -e
test "${RUNTIME_LOG_AUDIT_EXIT}" -eq 0 || test "${RUNTIME_LOG_AUDIT_EXIT}" -eq 2

python3 - "${TASK_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
diagnostic = json.loads((root / "failure_diagnostic_summary.json").read_text())
provenance = json.loads((root / "source_evidence_provenance.json").read_text())
runtime_log = json.loads((root / "runtime_exception_provenance.json").read_text())
assert provenance["source_evidence_unchanged"] is True
assert provenance["before"] == provenance["after"]
assert provenance["before"] == {
    "aggregate_sha256": "08da2b01af6682df0be3336f1aa0ef7f446493ca2eafbc41b5f45e1f35cb4b29",
    "file_count": 1709,
    "symlink_count": 0,
    "total_bytes": 80419374,
}
assert diagnostic["failed_request_id"] == "lifecycle_01_prime"
assert diagnostic["http_status"] == 200
assert diagnostic["server_alive"] is True
assert diagnostic["health_after_200"] is False
assert diagnostic["cause_proven_as_unique"] is False
assert runtime_log["schema_version"] == "p8_2_k1a_runtime_exception_provenance_v1"
assert runtime_log["source_log_unchanged"] is True
assert runtime_log["unknown_runtime_exception_count"] >= 0
assert runtime_log["generated_content_retained"] is False
assert runtime_log["token_ids_retained"] is False
assert all(len(row["normalized_message_sha256"]) == 64 for row in runtime_log["exceptions"])
assert all("message" not in row for row in runtime_log["exceptions"])
print(f"runtime_log_gate={runtime_log['runtime_log_gate']}")
print(f"runtime_exception_count={runtime_log['exception_count']}")
print(f"unknown_runtime_exception_count={runtime_log['unknown_runtime_exception_count']}")
PY
~~~

`runtime_log_gate` 只能是 `pass_no_direct_runtime_exception`、
`pass_known_retired_observer_defect` 或 `fail_unknown_runtime_exception`。第三种必须零 NPU 停止；不得由
服务器 AI 凭自然语言把未知异常改写成旧 observer 缺陷。原 raw log 不进入候选包。

## 3. 六文件 source binding、安装态 hash 与 runtime identity（零 NPU）

~~~bash
set -euo pipefail

VLLM_BASE=/data/node0_disk1/vllm-0.22.1
VLLM_ROOT=${VLLM_BASE}/vllm
VLLM_ASCEND_SITE=${RUNTIME_PREFIX}/lib/python3.11/site-packages
VLLM_ASCEND_ROOT=${VLLM_ASCEND_SITE}/vllm_ascend
cd "${REPO_ROOT}"

test "$(git -C "${VLLM_BASE}" rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398
test -z "$(git -C "${VLLM_BASE}" status --porcelain --untracked-files=no)"
"${RUNTIME_PYTHON}" "${AUDITOR}" installed-source-audit \
  --vllm-root "${VLLM_BASE}" \
  --vllm-ascend-root "${VLLM_ASCEND_SITE}" \
  --output "${TASK_ROOT}/installed_source_audit.corrected.json"

set +e
"${RUNTIME_PYTHON}" "${FORENSICS}" source-audit \
  --vllm-root "${VLLM_ROOT}" \
  --vllm-ascend-root "${VLLM_ASCEND_ROOT}" \
  --output "${TASK_ROOT}/offload_source_semantics.corrected.json"
SOURCE_AUDIT_EXIT=$?
set -e
test "${SOURCE_AUDIT_EXIT}" -eq 0 || test "${SOURCE_AUDIT_EXIT}" -eq 2

"${RUNTIME_PYTHON}" "${AUDITOR}" runtime-import-probe \
  --runtime-python "${RUNTIME_PYTHON}" \
  --output "${TASK_ROOT}/runtime_method_resolution.json"

"${RUNTIME_PYTHON}" - "${TASK_ROOT}/copy_primitive_runtime_identity.json" <<'PY'
from pathlib import Path
import hashlib
import inspect
import json
import sys

from vllm_ascend.simple_kv_offload import copy_backend, npu_mem_ops

output = Path(sys.argv[1])
same = copy_backend.copy_blocks is npu_mem_ops.copy_blocks
value = {
    "schema_version": "p8_2_k1a_copy_primitive_runtime_identity_v1",
    "identity_expression": "copy_backend.copy_blocks is npu_mem_ops.copy_blocks",
    "identity_exact": same,
    "copy_backend_module": copy_backend.copy_blocks.__module__,
    "copy_backend_name": copy_backend.copy_blocks.__name__,
    "npu_mem_ops_module": npu_mem_ops.copy_blocks.__module__,
    "npu_mem_ops_name": npu_mem_ops.copy_blocks.__name__,
    "signature": str(inspect.signature(copy_backend.copy_blocks)),
    "npu_started": False,
    "vllm_server_started": False,
    "model_request_sent": False,
}
output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
assert same
print("copy_primitive_runtime_identity=pass")
PY

python3 - "${TASK_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
installed = json.loads((root / "installed_source_audit.corrected.json").read_text())
source = json.loads((root / "offload_source_semantics.corrected.json").read_text())
runtime = json.loads((root / "runtime_method_resolution.json").read_text())
identity = json.loads((root / "copy_primitive_runtime_identity.json").read_text())
assert installed["source_hash_gate"] is True
assert len(installed["source_inventory"]) == 9
assert all(row["matched"] is True for row in installed["source_inventory"])
assert source["schema_version"] == "p8_2_k1a_source_semantics_audit_v3"
assert source["source_semantics_gate"] == "pass"
assert source["source_file_count"] == 6
assert source["required_symbols_present"] is True
assert source["copy_primitive_resolution"] == {
    "binding_imported_name": "copy_blocks",
    "binding_kind": "import_from",
    "binding_local_name": "copy_blocks",
    "binding_module": "vllm_ascend.simple_kv_offload.npu_mem_ops",
    "definition_label": "ascend_npu_mem_ops",
    "definition_present": True,
    "resolved": True,
    "symbol": "copy_blocks",
}
assert source["inheritance_resolution"]["resolved"] is True
assert source["frozen_launch_signature"]["observer_signature_compatible"] is True
assert runtime["subprocess_exit"] == 0
assert runtime["probe"]["worker_import"] == "success"
assert runtime["probe"]["copy_backend_import"] == "success"
assert runtime["probe"]["poll_method_owner"] == "vllm.v1.simple_kv_offload.worker.SimpleCPUOffloadWorker"
assert identity["identity_expression"] == "copy_backend.copy_blocks is npu_mem_ops.copy_blocks"
assert identity["identity_exact"] is True
assert runtime["npu_started"] is False
assert runtime["vllm_server_started"] is False
assert runtime["model_request_sent"] is False
print("source_binding_definition_runtime_identity_gate=pass")
PY

python3 - "${TASK_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
diagnostic = json.loads((root / "failure_diagnostic_summary.json").read_text())
provenance = json.loads((root / "source_evidence_provenance.json").read_text())
runtime_log = json.loads((root / "runtime_exception_provenance.json").read_text())
source = json.loads((root / "offload_source_semantics.corrected.json").read_text())
runtime = json.loads((root / "runtime_method_resolution.json").read_text())
identity = json.loads((root / "copy_primitive_runtime_identity.json").read_text())
allowed_log_gates = {
    "pass_no_direct_runtime_exception",
    "pass_known_retired_observer_defect",
}
formal = all((
    provenance["source_evidence_unchanged"] is True,
    diagnostic["cause_proven_as_unique"] is False,
    runtime_log["runtime_log_gate"] in allowed_log_gates,
    runtime_log["formal_lifecycle_runtime_log_condition"] is True,
    runtime_log["unknown_runtime_exception_count"] == 0,
    source["source_semantics_gate"] == "pass",
    source["copy_primitive_resolution"]["resolved"] is True,
    source["inheritance_resolution"]["resolved"] is True,
    source["frozen_launch_signature"]["observer_signature_compatible"] is True,
    runtime["subprocess_exit"] == 0,
    identity["identity_exact"] is True,
))
(root / "formal_lifecycle_allowed.txt").write_text(
    ("true" if formal else "false") + "\n"
)
if not formal:
    (root / "task_grade.txt").write_text(
        "blocked_p8_2_k1a_r3_r2_r2_r1_r1_offline_provenance_gate\n"
    )
    (root / "formal_model_lifecycle_count.txt").write_text("0\n")
    (root / "model_request_count.txt").write_text("0\n")
print(f"formal_lifecycle_allowed={str(formal).lower()}")
PY

test -z "$(git status --porcelain --untracked-files=no)"
~~~

source/hash/import/binding/identity/runtime-log 任一门失败，必须保持 `formal_lifecycle_allowed=false`，
不停 keep-alive，不启动服务，不发请求。不得使用另一个 vLLM-Ascend checkout，不得修改安装态源或依赖。

## 4. 条件式资源门与唯一 accepted-capacity lifecycle

只有机器生成的 true 才执行本节余下内容：

~~~bash
set -euo pipefail

FORMAL_LIFECYCLE_ALLOWED=$(cat "${TASK_ROOT}/formal_lifecycle_allowed.txt")
if test "${FORMAL_LIFECYCLE_ALLOWED}" = true; then
  test ! -e "${RESULT_DIR}"
else
  printf '%s\n' skipped_npu_due_to_offline_gate \
    > "${TASK_ROOT}/conditional_lifecycle_status.txt"
fi
~~~

若为 false，跳到第 5 节。若为 true，只执行以下一次：

~~~bash
set -euo pipefail

KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
test "$(cat "${TASK_ROOT}/formal_lifecycle_allowed.txt")" = true
test -f "${KEEP_ALIVE_SCRIPT}"
test -d "${MODEL_PATH}"
test "$(find "${MODEL_PATH}" -maxdepth 1 -type f | wc -l | tr -d ' ')" -gt 0
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(pgrep -af '[v]llm.*serve' || true)"
python3 - <<'PY'
from pathlib import Path
mem = {}
for line in Path('/proc/meminfo').read_text().splitlines():
    key, raw = line.split(':', 1)
    mem[key] = int(raw.strip().split()[0]) * 1024
assert mem['MemAvailable'] >= 64 * 1024**3, mem['MemAvailable']
print(f"mem_available_bytes={mem['MemAvailable']}")
PY

ENTERED_LIFECYCLE=0
cleanup() {
  set +e
  if test "${ENTERED_LIFECYCLE}" -eq 1; then
    current_markers=$(ps -eo args= | grep -E '#[0-7]#' | grep -v grep | wc -l | tr -d ' ')
    if test "${current_markers}" != 16; then
      bash "${KEEP_ALIVE_SCRIPT}" 0 1 2 3 4 5 6 7 \
        > "${TASK_ROOT}/keep_alive_restore_stdout.txt" \
        2> "${TASK_ROOT}/keep_alive_restore_stderr.txt"
      printf '%s\n' "$?" > "${TASK_ROOT}/keep_alive_restore_exit_code.txt"
      sleep 10
    fi
    ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' \
      > "${TASK_ROOT}/keep_alive_markers_after.txt"
    npu-smi info > "${TASK_ROOT}/npu_after.txt" 2>&1
    test "$(wc -l < "${TASK_ROOT}/keep_alive_markers_after.txt" | tr -d ' ')" = 16
    for card in 0 1 2 3 4 5 6 7; do
      grep -F "#${card}#" "${TASK_ROOT}/keep_alive_markers_after.txt" >/dev/null
    done
    printf '%s\n' true > "${TASK_ROOT}/keep_alive_restored_exact.txt"
  fi
  test -z "$(ss -ltnp | grep ':7000' || true)"
  test -z "$(pgrep -af '[v]llm.*serve' || true)"
}
trap cleanup EXIT

ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' \
  > "${TASK_ROOT}/keep_alive_markers_pre_stop.txt"
MARKER_COUNT=$(wc -l < "${TASK_ROOT}/keep_alive_markers_pre_stop.txt" | tr -d ' ')
test "${MARKER_COUNT}" = 0 || test "${MARKER_COUNT}" = 16
ENTERED_LIFECYCLE=1
if test "${MARKER_COUNT}" = 16; then
  CURRENT_PGID=$(ps -o pgid= -p $$ | tr -d ' ')
  mapfile -t KEEP_ALIVE_PGIDS < <(awk '{print $3}' "${TASK_ROOT}/keep_alive_markers_pre_stop.txt" | sort -u)
  test "${#KEEP_ALIVE_PGIDS[@]}" -ge 1
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
fi
test -z "$(ps -eo args= | grep -E '#[0-7]#' | grep -v grep || true)"
npu-smi info > "${TASK_ROOT}/npu_after_keep_alive_stop.txt"
grep -F 'No running processes found' "${TASK_ROOT}/npu_after_keep_alive_stop.txt" >/dev/null

set +e
bash "${RUNNER}" "${RESULT_DIR}" \
  > "${TASK_ROOT}/runner_stdout.txt" \
  2> "${TASK_ROOT}/runner_stderr.txt"
RUNNER_EXIT=$?
set -e
printf '%s\n' "${RUNNER_EXIT}" > "${TASK_ROOT}/runner_exit_code.txt"

test -d "${RESULT_DIR}"
test -f "${RESULT_DIR}/grading_inputs.json"
test -f "${RESULT_DIR}/transfer_trace_summary.json"
test -f "${RESULT_DIR}/failure_diagnostic_summary.json"
test -f "${RESULT_DIR}/first_failure_excerpt.txt"
test -f "${RESULT_DIR}/candidate_manifest.server_local.json"
test "$(cat "${RESULT_DIR}/cleanup_status.txt")" = clean
test -z "$(ss -ltnp | grep ':7000' || true)"
test -z "$(pgrep -af '[v]llm.*serve' || true)"
~~~

六请求仍为 `4K warmup -> 32K prime -> 131K pressure -> 32K restore_follower -> 32K
repeat_follower -> 32K isolated_control`。任一请求首错即停，不得补发。若任务开始时 keep-alive 为 0，
这是 pre-existing server state；本任务仍须在 cleanup 后用官方脚本恢复 16 marker/8 卡覆盖。

## 5. 分级、failure-safe manifest 与回报

不得再启动服务。若运行 lifecycle，必须逐项报告 6 个 slot 的 HTTP/token/SSE/MTP/health/queue；D2H/H2D
各自的 submit、enqueue、copy thread、`copy_blocks` enter/return、event visible、poll completion、bytes 和
8-rank coverage；scheduler store complete、restore hit/load scheduled/load complete；cleanup、7000、vLLM
残留与 keep-alive restore。仅 submit/enqueue 不算 store 或 restore 完成。

最终 grade 只能是：

- 仓库门失败：`blocked_p8_2_k1a_r3_r2_r2_r1_r1_repository_contract_gate`；
- parent 文件/不可变性失败：`blocked_p8_2_k1a_r3_r2_r2_r1_r1_parent_evidence_gate`；
- source binding/definition/runtime identity 失败：`blocked_p8_2_k1a_r3_r2_r2_r1_r1_source_binding_gate`；
- 未知 runtime exception 或其他 offline provenance 失败：`blocked_p8_2_k1a_r3_r2_r2_r1_r1_offline_provenance_gate`；
- lifecycle 启动后 0 成功：`red_p8_2_k1a_r3_r2_r2_r1_r1_no_success`；
- 部分成功：`yellow_p8_2_k1a_r3_r2_r2_r1_r1_partial`；
- D2H 完整但 H2D 不足：`yellow_p8_2_k1a_r3_r2_r2_r1_r1_store_only_no_restore`；
- 请求或异步证据不完整：`red_p8_2_k1a_r3_r2_r2_r1_r1_evidence_incomplete`；
- 6/6 请求与双向 8/8 全链、health/queue/MTP/cleanup 全过：
  `candidate_green_p8_2_k1a_r3_r2_r2_r1_r1_simple_cpu_offload_store_restore`。

服务器 AI 写 `${TASK_ROOT}/task_result_summary.md`，分节覆盖同步/合同、parent 11-file replay、原始树
before/after、`runtime_exception_provenance.json`、六文件 source binding、安装态 9-file hash、runtime
identity、formal 条件、资源、六请求、双向 copy、cleanup 和 grade。必须明确：

~~~text
parent_server_grade_preserved=true
source_semantics_false_negative_repaired=true
parent_exception_provenance_was_incomplete=true
runtime_log_gate=<exact value>
unknown_runtime_exception_count=<integer>
copy_backend.copy_blocks is npu_mem_ops.copy_blocks=<true|false>
cause_proven_as_unique=false
performance_reference_accepted=false
k2_authorized=false
p8_3_i1_authorized=false
next_task_authorized=false
~~~

最后生成 `${TASK_ROOT}/candidate_manifest.server_local.json`。只纳入开发机判断所需的 bounded operational
metadata：offline diagnostic/provenance、runtime exception fingerprint、corrected source/runtime/identity、
formal gate、task report，以及若运行 lifecycle 则选取 runtime 小 summary。每项记录 absolute path、bytes、
SHA-256、`sensitivity=bounded_operational_metadata_no_content_or_token_ids`；`missing_candidate_files=[]`；
单文件与总量均不超过 `71680 bytes`。raw log/metrics/trace/request body、overlay tree、generated content、
token IDs 不得进入候选。

完成后先回报 `task_result_summary.md` 精确路径、完整候选清单、逐文件 bytes/SHA-256/sensitivity、总量、
可用 `email / upload-api / server-local` 与推荐理由。`result_transfer_authorized:true` 只表示该有界包具备
传输资格；`transfer_method_selected:false` 表示尚未选择渠道。没有用户对完整清单的新选择时不得发送或
上传，失败不重试、不自动换渠道。

最终复核 tracked clean、端口 7000 空闲、无 vLLM 残留；若进入过 lifecycle，必须证明 16 个
keep-alive marker 覆盖 8 卡且已恢复。完成后保持等待，不得进入 K2、P8.3-I1、P8.4、P8.5 或 P9。
