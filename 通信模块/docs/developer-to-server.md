# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R3-R2-R2-R1 observer-contract 修正、离线重判与条件式唯一 lifecycle

~~~text
task_id: p8_2_k1a_r3_r2_r2_r1_deepseek_v4_flash_observer_contract_replay_2026_0720
execution_mode: authorized_offline_refinalization_inheritance_observer_contract_gate_then_one_same_capacity_lifecycle
server_sync_review_authorized: true
offline_refinalization_authorized: true
parent_raw_evidence_read_authorized: true
source_semantics_audit_authorized: true
installed_source_and_import_probe_authorized: true
observer_contract_correction_authorized: true
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

## 0. 背景、开发机判断和不可变边界

R3-R2-R2 服务器已按时任务合同在零 NPU 处停止，其已执行 grade 必须保留为：

~~~text
parent_server_grade=blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure
parent_formal_model_lifecycle_count=0
parent_model_request_count=0
parent_npu_started=false
parent_vllm_started=false
parent_cause_proven_as_unique=false
~~~

但开发机对冻结源与 10 文件回包独立复核后，确认上轮合同有两个误判和一个
observer 签名缺陷：

1. `SimpleCPUOffloadNPUWorker` 明确继承冻结 vLLM `SimpleCPUOffloadWorker`，
   `_poll_stream_events` 的实现来自基类。旧 source audit 只在 Ascend 子类的直接 AST body
   中查找该方法，因此 `source_semantics_false_negative=true`。
2. parent 只证明 `HTTP 200 / zero token / saw_done=true / health_after_200=false /
   server_alive=true / no direct exception`，且 `cause_proven_as_unique=false`。这应重判为
   `request_health_loss_without_direct_exception`，不是已证唯一 server-process 根因。
3. 旧 observe-only wrapper 的 `observed_launch` 向冻结
   `NPUDmaCopyBackend.launch_copy(self, src_blocks, dst_blocks, is_store, event_idx, events_list)`
   多传了不存在的 `wait_event`，即 `observer_wait_event_extra_parameter=true`。新代码已把
   observer 签名恢复为冻结六参数形状，不修改 runtime 功能、scheduler decision 或 copy
   parameter。

旧 `device_copy_submitted` 位于 `launch_copy` 调用前，而冻结 `launch_copy` 只把 item 放入
queue。因此 parent 的 16 个 submitted 事件只能证明 enqueue 尝试，不能证明后台
`_copy_loop -> copy_blocks -> Event append -> inherited _poll_stream_events` 进展。本任务必须先
离线重分级和关闭继承/签名门，只有没有发现直接异常才可运行一个同容量 lifecycle。

不变 runtime：W8A8、TP8+EP、MTP `num_speculative_tokens=1`、`FULL_DECODE_ONLY`、Prefix
Cache on、Chunked Prefill on、R2 hybrid-KV repair、`135168/4096/max_num_seqs=1`、block
size 128、canonical argv `8301f4c4...1bde6`、六个 body/顺序与唯一 accepted capacity：

~~~text
required_restore_tokens=16384
required_cpu_blocks=128
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
request_order=warmup,prime,pressure,restore_follower,repeat_follower,isolated_control
~~~

本轮不是容量搜索、性能对比或 runtime 行为修复。P6.3B-R4-R1、P8.1-R1、P8.2-K0、
K1A-R2 和 P8.3-I0-R1 的已接受结论均不撤销；不得进入 K2，不得进入 P8.3-I1，P8.4/P8.5/P9 也不授权。
The second lifecycle is forbidden；任何首错都不得 retry 或以新容量点重跑。
其中 K1A-R2=`ready_p8_2_k1a_r2_allocator_capacity`、K1A-R3=`blocked_p8_2_k1a_r3_source_or_provenance_gate`、
P8.3-I0-R1=`green_p8_3_i0_r1_unclassified_taxonomy`。

必须原样保留的关闭门为：

~~~text
P6.3B-R4-R1=green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
P6.3C=blocked_p6_3c_not_strict_single_variable
P8.1-R1=green_p8_1_r1_official_mtp_observe_only_matrix
P8.2-K1=blocked_p8_2_k1_frozen_stack_import_incompatible
P8.2-K1A-candidate-path=SimpleCPUOffloadConnector
~~~

## 1. 同步、冻结仓库和合同门（零 NPU）

只允许从 tracked-clean `main` 普通 fast-forward。不得覆盖服务器本地产物，不得停
keep-alive，本节失败不得创建任务结果目录。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_2_k1a_r3_r2_r2_r1_deepseek_v4_flash_observer_contract_replay_2026_0720
PARENT_RUNTIME_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01
PARENT_FORENSICS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_parent_forensics_2026_0720_run01
TASK_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r3_r2_r2_r1_observer_contract_2026_0720_run01
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_r1_deepseek_v4_flash_observer_contract_replay_2026_0720_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_r1_simple_cpu_offload.sh
FORENSICS=${REPO_ROOT}/tools/inference_contracts/p8_2_k1a_failure_forensics.py
AUDITOR=${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py
RUNTIME_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
cd "${REPO_ROOT}"

git status --short --branch --untracked-files=no
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
test -d "${PARENT_RUNTIME_DIR}"
test -d "${PARENT_FORENSICS_ROOT}"
test ! -e "${TASK_ROOT}"
test ! -e "${RESULT_DIR}"

python3 - <<'PY'
from pathlib import Path
import hashlib

expected = {
    "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r2_r2_r1_observer_contract_audit.yaml": "531bd937066811a06510aa5ae74ac07eb0c04b921002a3225195075cf4f4ccad",
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r3_r2_r2_r1_observer_contract_replay.yaml": "d72203e29bcbaa6cfe0706964c2038cda19d4125bd938f5c3edd31b72007a71d",
    "tools/inference_contracts/p8_2_k1a_failure_forensics.py": "3862af8c0fea5b28ad5f3eafba5fb04005c1ab8af5298255dd3e5763ab8fdf0e",
    "tools/inference_contracts/audit_deepseek_p8_2_k1a_simple_cpu_offload.py": "a23147ce2b43c6b8bf2650a126465c70ea6e24711f63627fec5239a4b1d2710e",
    "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "d16157f71ecc8ee5b0b5a09e1f43d9a837841f5c30fdc3c9d2a70e2bb307101c",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "a9093f865e5045644df8ffa386bc162443f7ab6ad3121e3fed3556f92f9ff0b1",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "06e7c6ba2976418797a92110c406e79b938e2314394d39e6ca82519ef8261462",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_simple_cpu_offload.sh": "28065c30588413e839cd0195709b645e416b06aa91db361808b6ac72aff6edf4",
    "tools/inference_contracts/run_deepseek_p8_2_k1a_r3_r2_r2_r1_simple_cpu_offload.sh": "8a31457678d933b58a89082f63cb98121529594c527ceab72f7c634057618ac1",
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
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_r1_observer_contract.py -q
python3 -m py_compile "${FORENSICS}" "${AUDITOR}" \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
bash -n "${RUNNER}" tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh

P8_2_K1A_AUDIT_ONLY=1 bash "${RUNNER}" /tmp/p8_2_k1a_r3_r2_r2_r1_audit \
  > /tmp/p8_2_k1a_r3_r2_r2_r1_audit.txt
grep -Fx "task_id=${TASK_ID}" /tmp/p8_2_k1a_r3_r2_r2_r1_audit.txt
grep -Fx 'execution_mode=authorized_offline_refinalization_inheritance_observer_contract_gate_then_one_same_capacity_lifecycle' /tmp/p8_2_k1a_r3_r2_r2_r1_audit.txt
grep -Fx 'cpu_bytes_to_use=3444834304' /tmp/p8_2_k1a_r3_r2_r2_r1_audit.txt
grep -Fx 'cpu_bytes_to_use_per_rank=430604288' /tmp/p8_2_k1a_r3_r2_r2_r1_audit.txt
grep -Fx 'server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6' \
  /tmp/p8_2_k1a_r3_r2_r2_r1_audit.txt
test ! -e /tmp/p8_2_k1a_r3_r2_r2_r1_audit
test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节任一失败：`blocked_p8_2_k1a_r3_r2_r2_r1_repository_contract_gate`，立即停止。

## 2. parent 证据复播、精确时窗和离线重分级（零 NPU）

先复核上轮 10 文件，再从 R3-R2-R1 原始结果树重新运行已修正 extractor。所有新文件
只写入 `TASK_ROOT`，不得改 parent 目录。

~~~bash
set -euo pipefail
cd "${REPO_ROOT}"

python3 - "${PARENT_FORENSICS_ROOT}" <<'PY'
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
expected = {
    "failed_request_sanitized.json": (1927, "952f499398dc3b5966fe5ea0f06b2e0fe8b7ff83e9bed1b79286393a6955bc43"),
    "failure_diagnostic_summary.json": (1623, "b72b63411818e061ae0a32a824de5ba3280ffa800364c8be568ffec8003dca17"),
    "result_summary.md": (357, "3ee9e889838ffebb33ed3bf7549ec66acd888487143d7ec8181ebe81eb9bee7e"),
    "source_evidence_provenance.json": (686, "001049069362bfd3d2376ffe3818c4c7c1fe2ff70d78ff48aec04eb117dc5db3"),
    "transfer_trace_timeline.json": (7944, "f264e0abd4c696572e3da585aec974392a22fe4c066500574cf9c73326dd2875"),
    "vllm_first_failure_excerpt.txt": (16412, "dd291ffd20092ae73ca11805b9428e390be4fca6927bbca565706b1d809b44d1"),
    "installed_source_audit.json": (3489, "3e82c711c93621e8e0608be2d9784db872f0c12612c1cd141b339aafbdd02ae8"),
    "offload_source_semantics.json": (2741, "b777d38b745efb526dff68b5954eff789e2897b11ce181cc7451c5b85730e9a6"),
    "runtime_import_probe.json": (348, "58ba4d08bac25b8bddaff40d068f1e2034bf2876ec3b9b649acd55b9c774de84"),
    "task_result_summary.md": (9441, "0393c3bd1d412a02fe79c6a94d797fcb06fbbee883f70202f9248f37e3d8ef77"),
}
for name, (size, wanted) in expected.items():
    path = root / name
    assert path.is_file(), path
    assert path.stat().st_size == size, (name, path.stat().st_size, size)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == wanted, name
assert sum(size for size, _ in expected.values()) == 44968
print("parent_r3_r2_r2_bounded_evidence_gate=pass files=10 bytes=44968")
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
print("parent_r3_r2_r1_direct_input_hash_gate=pass files=3")
PY

test ! -e "${TASK_ROOT}"
"${RUNTIME_PREFIX}/bin/python" "${FORENSICS}" extract \
  --source-result-dir "${PARENT_RUNTIME_DIR}" \
  --output-dir "${TASK_ROOT}" \
  > /tmp/p8_2_k1a_r3_r2_r2_r1_refinalize.json

python3 - "${TASK_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
diagnostic = json.loads((root / "failure_diagnostic_summary.json").read_text())
request = json.loads((root / "failed_request_sanitized.json").read_text())
provenance = json.loads((root / "source_evidence_provenance.json").read_text())
timeline = json.loads((root / "transfer_trace_timeline.json").read_text())
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
assert diagnostic["failure_classification"] == "request_health_loss_without_direct_exception"
assert diagnostic["formal_replay_allowed"] is True
assert isinstance(request["request_start_ns"], int) and request["request_start_ns"] > 0
assert isinstance(request["request_end_ns"], int)
assert request["request_end_ns"] >= request["request_start_ns"]
assert timeline["event_count"] == 28
assert sum(row.get("event") == "device_copy_submitted" for row in timeline["events"]) == 16
assert sum(row.get("event") == "copy_blocks_entered" for row in timeline["events"]) == 0
assert sum(row.get("event") == "transfer_poll_entered" for row in timeline["events"]) == 0
(root / "parent_server_grade_provenance.txt").write_text(
    "blocked_p8_2_k1a_r3_r2_r2_deterministic_parent_failure\n"
)
print("offline_refinalization_validation=pass")
PY
~~~

服务器 AI 再以 raw request 的 `request_start_ns/request_end_ns` 和 16 个 D2H trace
`timestamp_ns` 为边界，在 parent `runtime/vllm_server.log` 中只提取该时窗前 5 秒至后 10 秒的
bounded 文本，写入：

~~~text
${TASK_ROOT}/request_time_correlation.json
${TASK_ROOT}/request_time_log_excerpt.txt
~~~

`request_time_correlation.json` 必须记录 request/trace 开始结束 ns、日志选中行数、是否出现
`Traceback|Exception|Error|failed|acl|copy|offload|health`、是否含直接异常，且固定
`generated_content_retained=false / token_ids_retained=false`。禁止保存 request body、prompt、generated text、
token arrival 列表或 token IDs。无时窗字段、parent aggregate 变化或出现请求时直接 runtime
exception：`blocked_p8_2_k1a_r3_r2_r2_r1_parent_evidence_gate`，零 NPU 停止。

## 3. 五文件继承语义、精确签名和 runtime method resolution（零 NPU）

~~~bash
set -euo pipefail

VLLM_BASE=/data/node0_disk1/vllm-0.22.1
VLLM_ROOT=${VLLM_BASE}/vllm
VLLM_ASCEND_SITE=${RUNTIME_PREFIX}/lib/python3.11/site-packages
VLLM_ASCEND_ROOT=${VLLM_ASCEND_SITE}/vllm_ascend
RUNTIME_PYTHON=${RUNTIME_PREFIX}/bin/python
cd "${REPO_ROOT}"

test "$(git -C "${VLLM_BASE}" rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398
test -z "$(git -C "${VLLM_BASE}" status --porcelain --untracked-files=no)"
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

python3 - "${TASK_ROOT}" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
installed = json.loads((root / "installed_source_audit.corrected.json").read_text())
source = json.loads((root / "offload_source_semantics.corrected.json").read_text())
runtime = json.loads((root / "runtime_method_resolution.json").read_text())
probe = runtime["probe"]
assert installed["source_hash_gate"] is True
assert len(installed["source_inventory"]) == 9
assert all(row["matched"] is True for row in installed["source_inventory"])
assert source["schema_version"] == "p8_2_k1a_source_semantics_audit_v2"
assert source["source_semantics_gate"] == "pass"
assert source["source_file_count"] == 5
assert source["required_symbols_present"] is True
assert source["inheritance_resolution"] == {
    "base_class": "SimpleCPUOffloadWorker",
    "base_method": "SimpleCPUOffloadWorker._poll_stream_events",
    "derived_class": "SimpleCPUOffloadNPUWorker",
    "derived_class_inherits_base": True,
    "method_resolution": "inherited_from_frozen_vllm",
    "resolved": True,
}
assert source["frozen_launch_signature"] == {
    "parameters": ["self", "src_blocks", "dst_blocks", "is_store", "event_idx", "events_list"],
    "observer_extra_parameters": [],
    "observer_signature_compatible": True,
}
assert runtime["subprocess_exit"] == 0
assert probe["worker_import"] == "success"
assert probe["copy_backend_import"] == "success"
assert probe["poll_method_callable"] is True
assert probe["poll_method_owner"] == "vllm.v1.simple_kv_offload.worker.SimpleCPUOffloadWorker"
assert probe["poll_method_parameters"] == ["self", "is_store"]
assert probe["launch_copy_parameters"] == [
    "self", "src_blocks", "dst_blocks", "is_store", "event_idx", "events_list"
]
assert runtime["npu_started"] is False
assert runtime["vllm_server_started"] is False
assert runtime["model_request_sent"] is False
print("installed_source_hash_gate=pass")
print("inheritance_resolution=inherited_from_frozen_vllm")
print("observer_signature_compatible=true")
PY

python3 - "${TASK_ROOT}" <<'PY'
from pathlib import Path
import json
import re
import sys

root = Path(sys.argv[1])
diagnostic = json.loads((root / "failure_diagnostic_summary.json").read_text())
source = json.loads((root / "offload_source_semantics.corrected.json").read_text())
runtime = json.loads((root / "runtime_method_resolution.json").read_text())
correlation = json.loads((root / "request_time_correlation.json").read_text())
allowed = {
    "request_health_loss_without_direct_exception",
    "transfer_completion_absent_without_direct_exception",
    "insufficient_parent_evidence",
}
formal = all((
    diagnostic["formal_replay_allowed"] is True,
    diagnostic["failure_classification"] in allowed,
    diagnostic["cause_proven_as_unique"] is False,
    source["source_semantics_gate"] == "pass",
    source["inheritance_resolution"]["resolved"] is True,
    source["frozen_launch_signature"]["observer_signature_compatible"] is True,
    runtime["subprocess_exit"] == 0,
    correlation["direct_runtime_exception_present"] is False,
))
(root / "formal_lifecycle_allowed.txt").write_text(
    ("true" if formal else "false") + "\n"
)
print(f"formal_lifecycle_allowed={str(formal).lower()}")
PY

test -z "$(git status --porcelain --untracked-files=no)"
~~~

本节任一 source/hash/import/inheritance/signature/runtime-resolution 门失败：
`blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate`，不停 keep-alive。不得使用其他
vLLM-Ascend checkout，不得修改 site-packages 或增加功能 patch。

## 4. 条件分支、资源门与唯一 same-capacity lifecycle

只有机器生成的 `formal_lifecycle_allowed.txt=true` 才可进入 NPU 部分，不得人工覆盖：

~~~bash
set -euo pipefail

FORMAL_LIFECYCLE_ALLOWED=$(cat "${TASK_ROOT}/formal_lifecycle_allowed.txt")
if test "${FORMAL_LIFECYCLE_ALLOWED}" = true; then
  test ! -e "${RESULT_DIR}"
else
  printf '%s\n' blocked_p8_2_k1a_r3_r2_r2_r1_offline_gate \
    > "${TASK_ROOT}/task_grade.txt"
  printf '%s\n' 0 > "${TASK_ROOT}/formal_model_lifecycle_count.txt"
  printf '%s\n' 0 > "${TASK_ROOT}/model_request_count.txt"
fi
~~~

若值为 `false`，跳过本节余下全部命令。若为 `true`，先做资源门，再执行唯一 lifecycle：

~~~bash
set -euo pipefail

KEEP_ALIVE_SCRIPT=/data/node0_disk1/Public/npu_keep_alive.sh
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
test "$(cat "${TASK_ROOT}/formal_lifecycle_allowed.txt")" = true
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

KEEP_ALIVE_STOPPED=0
cleanup() {
  set +e
  if test "${KEEP_ALIVE_STOPPED}" -eq 1; then
    bash "${KEEP_ALIVE_SCRIPT}" 0 1 2 3 4 5 6 7 \
      > "${TASK_ROOT}/keep_alive_restore_stdout.txt" \
      2> "${TASK_ROOT}/keep_alive_restore_stderr.txt"
    restore_exit=$?
    printf '%s\n' "${restore_exit}" > "${TASK_ROOT}/keep_alive_restore_exit_code.txt"
    sleep 10
    ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' \
      > "${TASK_ROOT}/keep_alive_markers_after.txt"
    npu-smi info > "${TASK_ROOT}/npu_after.txt" 2>&1
    test "${restore_exit}" -eq 0
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

test -f "${KEEP_ALIVE_SCRIPT}"
ps -eo pid=,ppid=,pgid=,stat=,args= | awk '$0 ~ /#[0-7]#/' \
  > "${TASK_ROOT}/keep_alive_markers_pre_stop.txt"
test "$(wc -l < "${TASK_ROOT}/keep_alive_markers_pre_stop.txt" | tr -d ' ')" = 16
CURRENT_PGID=$(ps -o pgid= -p $$ | tr -d ' ')
mapfile -t KEEP_ALIVE_PGIDS < <(awk '{print $3}' "${TASK_ROOT}/keep_alive_markers_pre_stop.txt" | sort -u)
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

请求仍严格是 `4K warmup -> 32K prime -> 131K pressure -> 32K restore_follower -> 32K
repeat_follower -> 32K isolated_control`。任一请求失败立即停，不得 retry、补发、增加
第七请求、第二 lifecycle 或另一 capacity。

## 5. 异步 copy 机制分级、结果编目和回报

不得再启动服务。若 lifecycle 实际运行，读取 `transfer_trace_summary.json` 并精确回报：

- `copy_thread_started_worker_count` 以及 `copy_thread_failed_count`；
- D2H/H2D 的 `device_copy_submitted`、`device_copy_enqueued`、`copy_blocks_entered`、`copy_blocks_returned`、
  poll-event-visible、completed worker count 和 bytes；
- `copy_blocks_failed_count / transfer_poll_failed_count / async_copy_failure_event_count`；
- `d2h_async_copy_pipeline_exact / h2d_async_copy_pipeline_exact`；
- scheduler store complete、restore CPU hit/load scheduled/load complete；
- 六请求 HTTP/token/SSE/MTP/health/queue、cleanup 和 keep-alive restore。

新 candidate green 必须同时满足 6/6 首次成功、8/8 D2H 与 8/8 H2D 的 enqueue、
background `copy_blocks` enter+return、event 对 inherited poll 可见、poll completion，并且无 thread/
primitive/poll 异常。仅 `device_copy_submitted` 不允许计为 store 或 restore 完成。

最终 grade 只能是：

- 仓库门失败：`blocked_p8_2_k1a_r3_r2_r2_r1_repository_contract_gate`；
- parent 不可变性/时窗失败：`blocked_p8_2_k1a_r3_r2_r2_r1_parent_evidence_gate`；
- source/inheritance/signature/import 失败：`blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate`；
- 条件不允许进入 NPU：`blocked_p8_2_k1a_r3_r2_r2_r1_offline_gate`；
- lifecycle 启动后 0 成功：`red_p8_2_k1a_r3_r2_r2_r1_no_success`；
- 部分成功/未达六请求：`yellow_p8_2_k1a_r3_r2_r2_r1_partial`；
- D2H 全闭环但 H2D 不足：`yellow_p8_2_k1a_r3_r2_r2_r1_store_only_no_restore`；
- 请求/异步线程/复制/poll 证据不完整：`red_p8_2_k1a_r3_r2_r2_r1_evidence_incomplete`；
- 上述全过：`candidate_green_p8_2_k1a_r3_r2_r2_r1_simple_cpu_offload_store_restore`。

服务器 AI 在 `${TASK_ROOT}/task_result_summary.md` 中写完整分节报告：Git 同步、合同门、
parent byte/hash replay、before/after aggregate、精确请求时窗、旧 grade provenance、修正后分类、
五文件继承解析、runtime method owner/signature、条件分支、资源门、六 slot、异步 copy
pipeline、cleanup/restore、final grade 和 claim boundary。必须明确：

~~~text
parent_server_grade_preserved=true
source_semantics_false_negative=true
observer_wait_event_extra_parameter=true
cause_proven_as_unique=false
performance_reference_accepted=false
k2_authorized=false
p8_3_i1_authorized=false
next_task_authorized=false
~~~

最后生成 `${TASK_ROOT}/task_candidate_manifest.server_local.json`。只选入对开发机判断必要的
bounded operational metadata：offline diagnostic/provenance/correlation、corrected source/runtime resolution、
task report，以及若运行 lifecycle 则选入 runtime candidate manifest 中的小 summary。每项记录
absolute path、bytes、SHA-256、`sensitivity=bounded_operational_metadata_no_content_or_token_ids`；
manifest 必须包含 `missing_candidate_files`（没有缺失时为 `[]`）；单文件与总量均不得超过
`71680 bytes`。禁止 raw log/metrics/trace/request body、overlay
tree、generated content 和 token IDs 进入候选包。

完成后先在回报中列出精确 `task_result_summary.md` 路径、完整候选清单、逐文件
bytes/SHA-256/sensitivity、总量、可用 `email / upload-api / server-local` 与一个推荐理由。
`result_transfer_authorized:true` 表示有界包具备传输资格；`transfer_method_selected:false` 表示
当前没有选择渠道。未获用户对该完整清单的新选择前，不得发送、上传或复制；失败
不重试、不自动换渠道。

最终复核 tracked clean、端口 7000 空闲、无 vLLM 残留；若执行过 lifecycle，还要证明
16 个 keep-alive marker 覆盖 8 卡且已恢复。完成后保持等待，不得进入 K2、
P8.3-I1、P8.4、P8.5 或 P9。
