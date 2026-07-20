# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R3-R2-R2-R1-R1-R1 因果异常重分级与条件式唯一 lifecycle

~~~text
task_id: p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720
execution_mode: authorized_offline_causal_exception_refinalization_then_one_same_capacity_lifecycle
server_sync_review_authorized: true
parent_raw_evidence_read_authorized: true
offline_refinalization_authorized: true
causal_exception_grouping_authorized: true
frozen_source_template_audit_authorized: true
source_binding_and_runtime_identity_replay_authorized: true
npu_execution_authorized: true
keep_alive_stop_and_restore_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
formal_model_lifecycle_count_max: 1
model_request_count_max: 6
request_retry_count_exact: 0
seventh_request_authorized: false  # 禁止第七请求
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

## 0. 开发机判断、parent provenance 与不可变边界

上轮服务器任务已消费，不得原样重跑。必须保留：

~~~text
parent_task_id=p8_2_k1a_r3_r2_r2_r1_r1_deepseek_v4_flash_source_binding_provenance_replay_2026_0720
parent_server_grade=blocked_p8_2_k1a_r3_r2_r2_r1_r1_offline_provenance_gate
parent_formal_model_lifecycle_count=0
parent_model_request_count=0
parent_npu_started=false
parent_vllm_started=false
parent_source_semantics_gate=pass
parent_installed_source_hash_gate=pass
parent_runtime_method_resolution=pass
parent_runtime_identity_probe=pass
parent_runtime_log_gate=fail_unknown_runtime_exception
parent_cause_proven_as_unique=false
~~~

上轮已消费合同的检索标识只作历史 provenance，不是第二当前任务：

~~~text
parent_task_id: p8_2_k1a_r3_r2_r2_r1_r1_deepseek_v4_flash_source_binding_provenance_replay_2026_0720
parent_execution_mode: authorized_offline_source_binding_exception_provenance_gate_then_one_same_capacity_lifecycle
parent_contract_label=P8.2-K1A-R3-R2-R2-R1-R1 source binding
parent_runner=run_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_simple_cpu_offload.sh
parent_candidate_grade=candidate_green_p8_2_k1a_r3_r2_r2_r1_r1_simple_cpu_offload_store_restore
parent_source_schema=p8_2_k1a_source_semantics_audit_v3
parent_copy_definition_label=ascend_npu_mem_ops
parent_runtime_exception_file=runtime_exception_provenance.json
parent_runtime_log_gate_allowed=pass_known_retired_observer_defect
parent_unknown_runtime_exception_count=3
~~~

开发机已逐文件复核 parent 15-file 回包，共 `62093 bytes`；旧 flat classifier 记录 35 个
exception：32 个已知 retired observer `launch_copy` TypeError、1 个冻结 vLLM multiprocess worker
RuntimeError 包装和 2 个 EngineDeadError 传播包装。后三者的类型、消息哈希与 callsite
精确匹配冻结 `vLLM@0decac0d...` 的 `multiproc_executor.py/get_response` 与
`core_client.py/get_output_async` 确定性传播模板，且必须出现在已知根异常之后，不是新独立根因。本轮不得手工把
parent grade 改 green；必须从同一 raw log 生成 v2 机器证据并精确得到：

~~~text
runtime_log_gate=pass_known_retired_observer_defect_with_deterministic_wrappers
exception_count=35
root_known_observer_defect_count=32
derived_worker_runtime_wrapper_count=1
derived_engine_dead_wrapper_count=2
independent_unknown_exception_count=0
exception_record_count_exact=true
frozen_wrapper_source_templates.gate=pass
source_log_unchanged=true
~~~

任一值不符、新 independent unknown、source-template 不符或 raw log 变化，都必须零 NPU 停止。
服务器 AI 不得用自然语言推断覆盖机器门。

冻结 runtime、canonical argv、body、顺序、R2 hybrid-KV repair、observer 与 accepted capacity 不变：

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

W8A8、TP8+EP、MTP `num_speculative_tokens=1`、`FULL_DECODE_ONLY`、Prefix Cache on、Chunked Prefill on、
`max_model_len=135168`、`max_num_batched_tokens=4096`、`max_num_seqs=1`、block size 128 全部冻结。
不得容量搜索、功能 patch、第二 lifecycle、第七个请求或 retry；不得进入 K2、P8.3-I1、
P8.4、P8.5、P9。已关闭的 P6.3B-R4-R1、P8.1-R1、P8.2-K0、K1A-R2、P8.3-I0-R1
与全部 red/yellow/blocked lineage 均不撤销。

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
P8.2-K1A-R3-R2-R2=blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure
P8.2-K1A-R3-R2-R2-R1=blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate
P8.2-K1A-R3-R2-R2-R1-R1=blocked_p8_2_k1a_r3_r2_r2_r1_r1_offline_provenance_gate
P8.3-I0-R1=green_p8_3_i0_r1_unclassified_taxonomy
parent_server_grade=blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure
definition_label=ascend_npu_mem_ops
parent_runtime_cleanup_sha256=2e22da2ab13713309ac75219e525b8e06ed02f3f1963b8feef203fa25827f93d
parent_runtime_request_summary_sha256=9a18833a9945ed8ef98b95636603cf45f097974c15c069cd4ce96f68c36b0629
parent_runtime_result_summary_sha256=3696c8b348011669e91450fbfe2dd151eacd02208deb1168a5392bbd19532304
~~~

## 1. 同步、冻结仓库与合同门（零 NPU）

只允许从 tracked-clean `main` 普通 fast-forward。本节失败不得创建任务目录、停 keep-alive、
启动 vLLM 或发请求。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720
PARENT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance_2026_0720_run01
PARENT_RUNTIME_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
TASK_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_2026_0720_run01
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_r1_simple_cpu_offload.sh
FORENSICS=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_failure_forensics.py
AUDITOR=${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py
RUNTIME_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
RUNTIME_PYTHON=${RUNTIME_PREFIX}/bin/python
VLLM_BASE=/data/node0_disk1/vllm-0.22.1
VLLM_ROOT=${VLLM_BASE}/vllm
VLLM_ASCEND_SITE=${RUNTIME_PREFIX}/lib/python3.11/site-packages
VLLM_ASCEND_ROOT=${VLLM_ASCEND_SITE}/vllm_ascend
cd "${REPO_ROOT}"

git status --short --branch --untracked-files=no
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
test -d "${PARENT_ROOT}"
test -d "${PARENT_RUNTIME_DIR}"
test ! -e "${TASK_ROOT}"
test ! -e "${RESULT_DIR}"

python3 - <<'PY'
from pathlib import Path
import hashlib

expected = {
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay_audit.yaml": "da00f9866d36551542f8391137311f8154a7003c4a106ea3cee72e4c4c33309b",
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay.yaml": "8d10c3aaa47177e5f62997521be738fbd36f8d14e10b252994b78258002a1ce9",
    "tools/inference_contracts/p8_2_k1a_failure_forensics.py": "f9065b9014cd7e70bfdf055eccd689fb05261ecb34d4f07716c646d9332d25c9",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_r1_simple_cpu_offload.sh": "30f9ed55e007644730824fab6faf2d328416412bf0082119e9f1c4487266ff9d",
    "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py": "a23147ce2b43c6b8bf2650a126465c70ea6e24711f63627fec5239a4b1d2710e",
    "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "d16157f71ecc8ee5b0b5a09e1f43d9a837841f5c30fdc3c9d2a70e2bb307101c",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "a9093f865e5045644df8ffa386bc162443f7ab6ad3121e3fed3556f92f9ff0b1",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "06e7c6ba2976418797a92110c406e79b938e2314394d39e6ca82519ef8261462",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh": "28065c30588413e839cd0195709b645e416b06aa91db361808b6ac72aff6edf4",
    "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch": "5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6",
    "tools/inference_contracts/canonicalize_server_argv.py": "c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d",
}
for relative, wanted in expected.items():
    got = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
    assert got == wanted, (relative, got, wanted)
print(f"frozen_repo_hash_gate=pass files={len(expected)}")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_portable_argv.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r1_installed_source_gate.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_forensics.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_r1_observer_contract.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay.py -q
python3 -m py_compile "${FORENSICS}" "${AUDITOR}" \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
bash -n "${RUNNER}" tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
P8_2_K1A_AUDIT_ONLY=1 bash "${RUNNER}" /tmp/p8_2_k1a_r3_r2_r2_r1_r1_r1_audit \
  > /tmp/p8_2_k1a_r3_r2_r2_r1_r1_r1_audit.txt
grep -Fx "task_id=${TASK_ID}" /tmp/p8_2_k1a_r3_r2_r2_r1_r1_r1_audit.txt
grep -Fx 'execution_mode=authorized_offline_causal_exception_refinalization_then_one_same_capacity_lifecycle' \
  /tmp/p8_2_k1a_r3_r2_r2_r1_r1_r1_audit.txt
grep -Fx 'cpu_bytes_to_use=3444834304' /tmp/p8_2_k1a_r3_r2_r2_r1_r1_r1_audit.txt
grep -Fx 'cpu_bytes_to_use_per_rank=430604288' /tmp/p8_2_k1a_r3_r2_r2_r1_r1_r1_audit.txt
grep -Fx 'server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6' \
  /tmp/p8_2_k1a_r3_r2_r2_r1_r1_r1_audit.txt
test ! -e /tmp/p8_2_k1a_r3_r2_r2_r1_r1_r1_audit
test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节失败：`blocked_p8_2_k1a_r3_r2_r2_r1_r1_r1_repository_contract_gate`，立即停止。

## 2. Parent 15-file 包、raw log 与因果异常重放（零 NPU）

先 byte-for-byte 核验 parent 包；只在通过后创建新 `TASK_ROOT`。不得改 parent 目录或 raw log。

~~~bash
set -euo pipefail
cd "${REPO_ROOT}"

python3 - "${PARENT_ROOT}" <<'PY'
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
expected = {
    "conditional_lifecycle_status.txt": (32, "9c77b6b50a717eea8011080032625eb818078564932fb756e32c65bb06e498ad"),
    "copy_primitive_runtime_identity.json": (591, "be4ceb7934d63a2d72afc6e85c69b1f99c7e47b0ff48a37a3f7a11155cef24f3"),
    "failed_request_sanitized.json": (2005, "c86abd46f9d9d9aa610a866e13ecd184a9d9f4a92a2e761ce3e4b9d0d264415f"),
    "failure_diagnostic_summary.json": (2233, "0e23efb7a181bed00e95dba2a506b7242daac6e219c8f03d8d453c78e4bea6d7"),
    "formal_lifecycle_allowed.txt": (6, "2ed27c1421e6928dbe13dbfdb5c59e1045b30341fe7ebe05700006bc5ac572c0"),
    "formal_model_lifecycle_count.txt": (2, "9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa"),
    "installed_source_audit.corrected.json": (3489, "3e82c711c93621e8e0608be2d9784db872f0c12612c1cd141b339aafbdd02ae8"),
    "model_request_count.txt": (2, "9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa"),
    "offload_source_semantics.corrected.json": (4503, "305cb58febdf3428487f7b28c273a55ac58fcfd67e4b0f7aaf4b0ba5fdf767f1"),
    "parent_server_grade_provenance.txt": (53, "d4dfa80b4bc8a9ad5ec12a4dc187ce3d194dcffa516994b41cfe3ab21a1cd639"),
    "runtime_exception_provenance.json": (36130, "62448f4263f51eddf8bc35439a85fa03c157474e06bf3df016e987b02c197e48"),
    "runtime_method_resolution.json": (1733, "449cfe11f943072373e90c9a0fc8b993ef60f5087f777e38ec7171b01f970a55"),
    "source_evidence_provenance.json": (686, "001049069362bfd3d2376ffe3818c4c7c1fe2ff70d78ff48aec04eb117dc5db3"),
    "task_grade.txt": (56, "19b9b515cac5a71ca72dbaeef312a83c223ff0163d6eb0604cbd345fc20adb5d"),
    "task_result_summary.md": (10572, "77cb35ac54e38e4fa3f0def253421808938f7bb36042c1c37ff837c72220323c"),
}
for name, (size, wanted) in expected.items():
    path = root / name
    assert path.is_file(), path
    assert path.stat().st_size == size, (name, path.stat().st_size, size)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == wanted, name
assert sum(size for size, _ in expected.values()) == 62093
print("parent_bounded_evidence_gate=pass files=15 bytes=62093")
PY

test "$(git -C "${VLLM_BASE}" rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398
test -z "$(git -C "${VLLM_BASE}" status --porcelain --untracked-files=no)"
test -f "${PARENT_RUNTIME_DIR}/runtime/vllm_server.log"
mkdir -p "${TASK_ROOT}"

"${RUNTIME_PYTHON}" "${FORENSICS}" runtime-log-audit \
  --compact \
  --log "${PARENT_RUNTIME_DIR}/runtime/vllm_server.log" \
  --vllm-root "${VLLM_ROOT}" \
  --output "${TASK_ROOT}/causal_runtime_exception_provenance.json" \
  > "${TASK_ROOT}/causal_runtime_exception_audit.stdout.json"

python3 - "${TASK_ROOT}/causal_runtime_exception_provenance.json" <<'PY'
from pathlib import Path
import json
import sys

value = json.loads(Path(sys.argv[1]).read_text())
assert value["schema_version"] == "p8_2_k1a_runtime_exception_causal_provenance_v2"
assert value["runtime_log_gate"] == "pass_known_retired_observer_defect_with_deterministic_wrappers"
assert value["formal_lifecycle_runtime_log_condition"] is True
assert value["exception_count"] == 35
assert value["root_known_observer_defect_count"] == 32
assert value["derived_worker_runtime_wrapper_count"] == 1
assert value["derived_engine_dead_wrapper_count"] == 2
assert value["independent_unknown_exception_count"] == 0
assert value["unknown_runtime_exception_count"] == 0
assert value["exception_record_count_exact"] is True
assert value["exception_record_samples_included"] is False
assert "exceptions" not in value
assert sum(group["count"] for group in value["exception_groups"]) == 35
assert value["frozen_wrapper_source_templates"]["gate"] == "pass"
assert value["frozen_wrapper_source_templates"]["required_file_count"] == 3
assert value["frozen_wrapper_source_templates"]["matched_file_count"] == 3
assert value["frozen_wrapper_contract"]["worker_runtime_message_sha256"] == "42d6217fd6e2666b3bc6a403bfb201809cf500353095062c39eed6f113e5fd63"
assert value["frozen_wrapper_contract"]["engine_dead_message_sha256"] == "988c82d7efef7bf00a3704ebde56ac21a2909a32bdbd1e13368341b475859130"
assert value["source_log_unchanged"] is True
assert value["generated_content_retained"] is False
assert value["token_ids_retained"] is False
print("causal_runtime_exception_refinalization=pass")
PY
~~~

任一断言失败：`blocked_p8_2_k1a_r3_r2_r2_r1_r1_r1_offline_provenance_gate`，不得执行后续节。

## 3. 六文件 source binding、9-file installed source 与 runtime identity 重放（零 NPU）

~~~bash
set -euo pipefail
cd "${REPO_ROOT}"

"${RUNTIME_PYTHON}" "${AUDITOR}" installed-source-audit \
  --vllm-root "${VLLM_BASE}" \
  --vllm-ascend-root "${VLLM_ASCEND_SITE}" \
  --output "${TASK_ROOT}/installed_source_audit.corrected.json"
"${RUNTIME_PYTHON}" "${FORENSICS}" source-audit \
  --vllm-root "${VLLM_ROOT}" \
  --vllm-ascend-root "${VLLM_ASCEND_ROOT}" \
  --output "${TASK_ROOT}/offload_source_semantics.corrected.json"
"${RUNTIME_PYTHON}" "${AUDITOR}" runtime-import-probe \
  --runtime-python "${RUNTIME_PYTHON}" \
  --output "${TASK_ROOT}/runtime_method_resolution.json"

"${RUNTIME_PYTHON}" - "${TASK_ROOT}/copy_primitive_runtime_identity.json" <<'PY'
from pathlib import Path
import inspect
import json
import sys
from vllm_ascend.simple_kv_offload import copy_backend, npu_mem_ops

same = copy_backend.copy_blocks is npu_mem_ops.copy_blocks
value = {
    "schema_version": "p8_2_k1a_copy_primitive_runtime_identity_v1",
    "identity_expression": "copy_backend.copy_blocks is npu_mem_ops.copy_blocks",
    "identity_exact": same,
    "module": copy_backend.copy_blocks.__module__,
    "name": copy_backend.copy_blocks.__name__,
    "signature": str(inspect.signature(copy_backend.copy_blocks)),
    "npu_started": False,
    "vllm_server_started": False,
    "model_request_sent": False,
}
Path(sys.argv[1]).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
assert same
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
causal = json.loads((root / "causal_runtime_exception_provenance.json").read_text())
assert installed["source_hash_gate"] is True
assert len(installed["source_inventory"]) == 9
assert all(row["matched"] is True for row in installed["source_inventory"])
assert source["schema_version"] == "p8_2_k1a_source_semantics_audit_v3"
assert source["source_semantics_gate"] == "pass"
assert source["source_file_count"] == 6
assert source["copy_primitive_resolution"]["resolved"] is True
assert source["copy_primitive_resolution"]["binding_kind"] == "import_from"
assert source["inheritance_resolution"]["resolved"] is True
assert source["frozen_launch_signature"]["observer_signature_compatible"] is True
assert runtime["subprocess_exit"] == 0
assert runtime["probe"]["worker_import"] == "success"
assert runtime["probe"]["copy_backend_import"] == "success"
assert identity["identity_expression"] == "copy_backend.copy_blocks is npu_mem_ops.copy_blocks"
assert identity["identity_exact"] is True
assert causal["formal_lifecycle_runtime_log_condition"] is True
(root / "formal_lifecycle_allowed.txt").write_text("true\n")
print("formal_lifecycle_allowed=true")
PY

test -z "$(git status --porcelain --untracked-files=no)"
~~~

source/hash/import/binding/identity 任一失败：
`blocked_p8_2_k1a_r3_r2_r2_r1_r1_r1_source_binding_gate`，不得停 keep-alive。

## 4. 资源门与唯一 accepted-capacity lifecycle

只有机器生成的 true 才允许进入。如果 false，写 `conditional_lifecycle_status.txt` 后直接进入第 5 节。

~~~bash
set -euo pipefail

FORMAL_LIFECYCLE_ALLOWED=$(cat "${TASK_ROOT}/formal_lifecycle_allowed.txt")
if test "${FORMAL_LIFECYCLE_ALLOWED}" = true; then
  test ! -e "${RESULT_DIR}"
else
  printf '%s\n' skipped_npu_due_to_offline_gate > "${TASK_ROOT}/conditional_lifecycle_status.txt"
fi

if test "${FORMAL_LIFECYCLE_ALLOWED}" = true; then
  KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
  MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
  test -f "${KEEP_ALIVE_SCRIPT}"
  test -d "${MODEL_PATH}"
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
      if ! ps -eo args= | grep -E '#[0-7]#' | grep -v grep >/dev/null; then break; fi
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
  test -f "${RESULT_DIR}/candidate_manifest.server_local.json"
  test "$(cat "${RESULT_DIR}/cleanup_status.txt")" = clean
  python3 - "${RESULT_DIR}/grading_inputs.json" "${TASK_ROOT}/task_grade.txt" <<'PY'
from pathlib import Path
import json
import sys
grade = json.loads(Path(sys.argv[1]).read_text())["server_grade"]
Path(sys.argv[2]).write_text(grade + "\n")
print(f"server_grade={grade}")
PY
  test -z "$(ss -ltnp | grep ':7000' || true)"
  test -z "$(pgrep -af '[v]llm.*serve' || true)"
fi
~~~

六请求仍为 `4K warmup -> 32K prime -> 131K pressure -> 32K restore_follower -> 32K
repeat_follower -> 32K isolated_control`。任一请求首错即停，不得补发。若开始时 keep-alive 为 0，
仍必须在结束时恢复官方 16 marker/8 卡覆盖。

## 5. 联合分级、完整 manifest 与回报

不得再启动服务。若运行 lifecycle，必须逐项报告 6 slot 的 HTTP/token/SSE/MTP/health/queue；
D2H/H2D 各自 submit、enqueue、copy thread、`copy_blocks` enter/return、event visible、poll completion、
bytes 和 8-rank coverage；scheduler store/restore 与 cleanup/keep-alive restore。仅 submit/enqueue 不算完成。

最终 grade 只能是：

- `blocked_p8_2_k1a_r3_r2_r2_r1_r1_r1_repository_contract_gate`；
- `blocked_p8_2_k1a_r3_r2_r2_r1_r1_r1_parent_evidence_gate`；
- `blocked_p8_2_k1a_r3_r2_r2_r1_r1_r1_offline_provenance_gate`；
- `blocked_p8_2_k1a_r3_r2_r2_r1_r1_r1_source_binding_gate`；
- `blocked_p8_2_k1a_r3_r2_r2_r1_r1_r1_source_or_resource_gate`；
- `red_p8_2_k1a_r3_r2_r2_r1_r1_r1_no_success`；
- `yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_partial`；
- `yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore`；
- `red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete`；
- 6/6 请求与双向 8/8 全链、health/queue/MTP/cleanup 全过：
  `candidate_green_p8_2_k1a_r3_r2_r2_r1_r1_r1_simple_cpu_offload_store_restore`。

服务器 AI 写 `${TASK_ROOT}/task_result_summary.md`，分节覆盖同步/合同、parent 15-file、raw log
before/after、root/derived/independent 分组、冻结源模板、六文件 source binding、9-file installed
source、runtime identity、formal 条件、资源、六请求、双向 copy、cleanup 和 grade。必须明确：

~~~text
parent_server_grade_preserved=true
runtime_log_gate=pass_known_retired_observer_defect_with_deterministic_wrappers
root_known_observer_defect_count=32
derived_worker_runtime_wrapper_count=1
derived_engine_dead_wrapper_count=2
independent_unknown_exception_count=0
exception_record_count_exact=true
source_log_unchanged=true
cause_proven_as_unique=false
performance_reference_accepted=false
k2_authorized=false
p8_3_i1_authorized=false
next_task_authorized=false
~~~

生成 `${TASK_ROOT}/candidate_manifest.server_local.json`，只纳入开发机判断所需的 bounded operational
metadata：精简因果 provenance、source/runtime/identity、formal gate、task report，以及若实跑则纳入
runtime 小 summary。必须排除 raw log/metrics/trace/request body、overlay tree、generated content 和 token IDs。
manifest 对每个 payload 文件记录 absolute path、bytes、SHA-256、sensitivity；
`missing_candidate_files=[]`、`manifest_is_required_transfer_control_file=true`、
`manifest_not_self_hashed_by_design=true`。写完后检查 payload + manifest 总量和每文件均 `<=71680 bytes`。

在第 2–4 节已产生证据后，用以下白名单生成 manifest；不得改成目录递归收集：

~~~bash
python3 - "${TASK_ROOT}" "${RESULT_DIR}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

task_root = Path(sys.argv[1])
result_dir = Path(sys.argv[2])
sensitivity = "bounded_operational_metadata_no_content_or_token_ids"
required_task = (
    "causal_runtime_exception_provenance.json",
    "installed_source_audit.corrected.json",
    "offload_source_semantics.corrected.json",
    "runtime_method_resolution.json",
    "copy_primitive_runtime_identity.json",
    "formal_lifecycle_allowed.txt",
    "task_grade.txt",
    "task_result_summary.md",
)
optional_task = (
    "conditional_lifecycle_status.txt",
    "runner_exit_code.txt",
    "keep_alive_restored_exact.txt",
)
optional_runtime = (
    "result_summary.md",
    "environment_and_hashes.json",
    "grading_inputs.json",
    "transfer_trace_summary.json",
    "mtp_queue_health_summary.json",
    "host_memory_summary.json",
    "request_summary.tsv",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
    "connector_resolution_summary.json",
    "repair_diagnostic_summary.json",
)

missing = [name for name in required_task if not (task_root / name).is_file()]
assert not missing, missing
paths = [task_root / name for name in required_task]
paths.extend(task_root / name for name in optional_task if (task_root / name).is_file())
if result_dir.is_dir():
    paths.extend(result_dir / name for name in optional_runtime if (result_dir / name).is_file())
assert len(paths) == len(set(paths))

files = []
for path in paths:
    raw = path.read_bytes()
    assert len(raw) <= 71680, (path, len(raw))
    files.append({
        "absolute_path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sensitivity": sensitivity,
    })

manifest = {
    "schema_version": "p8_2_k1a_bounded_candidate_manifest_v1",
    "task_id": "p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720",
    "files": files,
    "payload_file_count": len(files),
    "payload_total_bytes": sum(item["bytes"] for item in files),
    "missing_candidate_files": [],
    "sensitivity": sensitivity,
    "generated_content_retained": False,
    "token_ids_retained": False,
    "raw_logs_metrics_traces_or_request_bodies_included": False,
    "manifest_is_required_transfer_control_file": True,
    "manifest_not_self_hashed_by_design": True,
    "result_transfer_authorized": True,
    "transfer_method_selected": False,
}
output = task_root / "candidate_manifest.server_local.json"
output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
manifest_raw = output.read_bytes()
candidate_total = manifest["payload_total_bytes"] + len(manifest_raw)
assert len(manifest_raw) <= 71680
assert candidate_total <= 71680, candidate_total
print(f"candidate_payload_files={len(files)}")
print(f"candidate_payload_bytes={manifest['payload_total_bytes']}")
print(f"candidate_manifest_bytes={len(manifest_raw)}")
print(f"candidate_manifest_sha256={hashlib.sha256(manifest_raw).hexdigest()}")
print(f"candidate_total_bytes={candidate_total}")
PY
~~~

完成后先回报 `task_result_summary.md` 精确路径、完整候选清单（必须含 manifest 本身）、逐文件
bytes/SHA-256/sensitivity、总量、可用 `email / upload-api / server-local` 与推荐理由。
`result_transfer_authorized:true` 只表示有界包具备传输资格；`transfer_method_selected:false` 表示未选渠道。
没有用户对完整清单的新选择时不得发送或上传，失败不重试、不自动换渠道。

最终复核 tracked clean、端口 7000 空闲、无 vLLM 残留；若进入过 lifecycle，必须证明 16 个
keep-alive marker 覆盖 8 卡且已恢复。完成后保持等待：不得进入 K2；不得进入 P8.3-I1；
不得进入 P8.4、P8.5 或 P9。
