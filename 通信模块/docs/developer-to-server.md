# Developer to Server

## 当前唯一服务器动作：P8.2-K1 冻结栈源码、导入与配置只读复核

~~~text
task_id: p8_2_k1_frozen_stack_import_compatibility_review_2026_0717
execution_mode: authorized_read_only_source_import_config_review_no_npu
server_sync_review_authorized: true
source_import_config_review_authorized: true
temporary_audit_workspace_authorized: true
npu_execution_authorized: false
vllm_server_start_authorized: false
model_requests_authorized: false
keep_alive_mutation_authorized: false
task_local_compatibility_patch_authorized: false
result_directory_creation_authorized: false
result_transfer_authorized: false
next_task_authorized: false
lifecycle_count_exact: 0
request_count_exact: 0
profiler_authorized: false
offload_runtime_execution_authorized: false
no_k2_k3_k4_p8_3_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

本任务是 K1 可行性门的服务器只读复核，不是 KV Cache CPU Offload workload。开发机已接受
P8.2-K0-R1 为 `green_p8_2_k0_order_balanced_prefix_cache_baseline`：原 29-file raw evidence 未变，
20/20 请求与 15 项逐请求 predicate 均完整，6 个 on measured follower 的 Prefix Cache hit 均为
`49152`，off hit total=`0`；但 `performance_reference_accepted: false`、
`offload_evidence_accepted: false` 继续有效。

开发机从冻结 Git object 审计到：vLLM-Ascend 的 `NPUOffloadingSpec` 仍导入
`vllm.v1.kv_offload.abstract`、`mediums` 与 `spec`，而冻结 vLLM 对应路径不存在，API 已位于
`vllm.v1.kv_offload.base`；同一 Ascend spec 还两次断言只有一个 GPU block-size group，而已接受的
DeepSeek R2 hybrid-KV 证据包含 `CompressAttentionManager` 与 `SlidingWindowManager`。因此当前结论为
`blocked_p8_2_k1_frozen_stack_import_incompatible`。服务器只确认冻结安装态与既有 K0 证据是否吻合；
不得把 probe 当作 offload runtime 证据，不得创建 workload，不得开发或应用兼容补丁。

保留且不撤销的 lineage：P6.3B-R4-R1=
`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`；P6.3C=
`blocked_p6_3c_not_strict_single_variable`；P8.1 parent=`yellow_p8_1_matrix_trace_invalid`；P8.1-R1=
`green_p8_1_r1_official_mtp_observe_only_matrix` 且 `cause_proven_as_unique: false`；P8.2-K0 green。
K1 blocked 不撤销上述结论。

## 1. 同步门与冻结仓库合同

服务器从自己的干净 `main` 镜像普通快进同步。不得 reset、stash、rebase、用 checkout 覆盖、运行
`sync.sh`、在服务器 commit 或 push。服务器既有未跟踪运行产物保留，只要求 tracked 状态干净。

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
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k0_order_balanced_prefix_cache_baseline.yaml": "9a0de8859e1b3772b83155048d3cda9d9b472669509095ac157ae463964ef818",
    "benchmarks/deepseek_v4_flash/p8_2_k1_kv_cache_cpu_offload_feasibility_audit.yaml": "0649c0f2fd32251cbfadf2a8bee36a21c6b42cd3c89fb3e1e1c4919302a61f70",
    "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml": "7e432ed6c0984dbcd0bd8a54e6b0d2050194117ce6390c590673c2f4f4aa1804",
    "tools/inference_contracts/audit_deepseek_p8_2_k1_kv_cache_cpu_offload.py": "e2fc8706ce6e5b360d9bcd0784c28914beb6b0d532736fdd26d2c4d9db221f65",
    "tests/inference_contracts/test_deepseek_p8_2_k1_kv_cache_cpu_offload_feasibility.py": "f6245b29af6b6fe486fa80c2844c8c4e66f4fdb2bd7701722612cc8ec14b00b6",
}
for relative, wanted in expected.items():
    path = Path(relative)
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != wanted:
        raise SystemExit(f"frozen repo hash mismatch: {relative} {got} != {wanted}")
print("frozen_repo_hash_gate=pass")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1_kv_cache_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k0_order_balanced_prefix_baseline.py -q
python3 -m py_compile \
  tools/inference_contracts/audit_deepseek_p8_2_k1_kv_cache_cpu_offload.py
test -z "$(git status --porcelain --untracked-files=no)"
~~~

若同步、tracked-clean、五个冻结 hash、定向合同或 compile 任一失败，给
`blocked_p8_2_k1_source_or_contract_gate` 并停止；不得继续 probe、不得修改 runtime、不得创建项目结果目录。

## 2. 零资源扰动门与临时审计空间

本节只读记录 keep-alive marker/PID/PGID、NPU 状态、端口 7000 与 vLLM 进程。任务前后必须保持既有
keep-alive PID/PGID/进程形态不变。不得停止或重启 keep-alive，不得向任何既有进程发信号，不得清卡，
不得启动 vLLM，不得绑定端口，不得发送模型请求。standing 资源许可不改变本任务的零资源授权。

仅允许在 `/tmp/opencode/p8_2_k1_frozen_stack_import_compatibility_review_2026_0717` 写入小型审计 JSON；
仓库内不得创建结果目录，临时目录必须在本轮开始时不存在。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TMP_AUDIT=/tmp/opencode/p8_2_k1_frozen_stack_import_compatibility_review_2026_0717

test ! -e "${TMP_AUDIT}"
mkdir -p "${TMP_AUDIT}"
ps -eo pid,ppid,pgid,stat,cmd | grep -E 'npu_keep_alive|#0#|#1#|#2#|#3#|#4#|#5#|#6#|#7#' > "${TMP_AUDIT}/keep_alive_before.txt" || true
npu-smi info > "${TMP_AUDIT}/npu_before.txt"
ss -ltnp | grep ':7000' > "${TMP_AUDIT}/port_7000_before.txt" || true
ps -eo pid,ppid,pgid,stat,cmd | grep -E '[v]llm|[V]LLM' > "${TMP_AUDIT}/vllm_before.txt" || true
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
~~~

只允许记录状态，不得处置任何发现的进程或端口。若 tracked 不干净，给
`blocked_p8_2_k1_source_or_resource_gate` 并停止。

## 3. 冻结安装态 source-audit 与 runtime-import-probe

固定冻结版本：

~~~text
vllm_version: 0.22.1+empty
vllm_commit: 0decac0d96c42b49572498019f0a0e3600f50398
vllm_ascend_version: 0.22.1rc1
vllm_ascend_commit: 5f6faa0cb8830f667266f3b8121cd1383606f2a1
~~~

使用服务器真实 editable vLLM source checkout 与安装态 vLLM-Ascend package。不得更换版本、安装包、
编辑源码、复制 overlay、设置 Python path 指向另一版本，或把缺失模块临时补入环境。probe 只做文件
hash、module resolution、`KVTransferConfig` 对象构造和隔离 import；不会构建 engine 或 connector，
也不会访问 NPU。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TMP_AUDIT=/tmp/opencode/p8_2_k1_frozen_stack_import_compatibility_review_2026_0717
AUDITOR="${REPO_ROOT}/tools/inference_contracts/audit_deepseek_p8_2_k1_kv_cache_cpu_offload.py"
RUNTIME_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
RUNTIME_PYTHON="${RUNTIME_PREFIX}/bin/python"
VLLM_ROOT=/data/node0_disk1/vllm-0.22.1
VLLM_ASCEND_ROOT="${RUNTIME_PREFIX}/lib/python3.11/site-packages"

test -x "${RUNTIME_PYTHON}"
test -d "${VLLM_ROOT}/vllm"
test -d "${VLLM_ASCEND_ROOT}/vllm_ascend"
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

assert source["audit_grade"] == "blocked_p8_2_k1_frozen_stack_import_incompatible"
assert source["source_hash_gate"] is True
assert source["missing_legacy_modules"] == [
    "vllm/v1/kv_offload/abstract.py",
    "vllm/v1/kv_offload/mediums.py",
    "vllm/v1/kv_offload/spec.py",
]
assert source["npu_spec_single_group_assertion_count"] == 2
assert source["formal_k1_workload_allowed"] is False

probe = runtime["probe"]
assert runtime["subprocess_exit"] == 0
assert probe is not None
for name in (
    "vllm.v1.kv_offload.abstract",
    "vllm.v1.kv_offload.mediums",
    "vllm.v1.kv_offload.spec",
):
    assert probe["module_resolution"][name] is None
assert probe["kv_transfer_config"] == {
    "kv_connector": "OffloadingConnector",
    "kv_role": "kv_both",
    "kv_connector_extra_config": {
        "num_cpu_blocks": 1000,
        "block_size": 128,
        "spec_name": "NPUOffloadingSpec",
        "spec_module_path": "vllm_ascend.kv_offload.npu",
    },
}
assert probe["npu_spec_import"] == "failed"
error = probe["npu_spec_import_error"]
assert error["error_type"] == "ModuleNotFoundError"
assert "vllm.v1.kv_offload.abstract" in error["error"]
assert probe["npu_started"] is False
assert probe["vllm_server_started"] is False
assert probe["model_request_sent"] is False
print("frozen_stack_import_compatibility_review=blocked_as_expected")
PY
~~~

若安装态文件 hash、缺失模块集合、两处单 group assertion、配置字段或 import failure 与冻结审计不同，
给 `blocked_p8_2_k1_runtime_source_drift`；仍不得修环境、retry、启动 runtime 或创建 workload。

## 4. 既有 K0-R1 hybrid 证据交叉检查与 K1 不存在性门

只读检查既有 K0-R1 派生目录；不得修改原 K0 或派生目录。确认它仍是 accepted K0 基线，且其 repair
diagnostic 明确记录 `CompressAttentionManager` 与 `SlidingWindowManager`。这一步只证明选定 DeepSeek
路径是 hybrid multi-group，不证明 offload 已运行。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
K0_R1_RESULT="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k0_r1_offline_refinalization_2026_0717_run01"
TMP_AUDIT=/tmp/opencode/p8_2_k1_frozen_stack_import_compatibility_review_2026_0717

test -d "${K0_R1_RESULT}"
python3 - "${K0_R1_RESULT}" "${TMP_AUDIT}/k0_hybrid_crosscheck.json" <<'PY'
from pathlib import Path
import json
import sys

result_dir = Path(sys.argv[1])
output = Path(sys.argv[2])
grading = json.loads((result_dir / "grading_inputs.json").read_text())
repair = json.loads((result_dir / "repair_diagnostic_summary.json").read_text())

assert grading["server_grade"] == "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
assert grading["successful_request_count"] == 20
assert grading["request_evidence_exact"] is True
assert grading["source_evidence_file_count"] == 29
assert grading["source_evidence_unchanged"] is True
rendered = json.dumps(repair, sort_keys=True)
assert "CompressAttentionManager" in rendered
assert "SlidingWindowManager" in rendered
summary = {
    "k0_grade": grading["server_grade"],
    "successful_request_count": grading["successful_request_count"],
    "source_evidence_unchanged": grading["source_evidence_unchanged"],
    "manager_types": ["CompressAttentionManager", "SlidingWindowManager"],
    "offload_evidence_accepted": False,
}
output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
PY

test -z "$(find "${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads" -maxdepth 1 -name 'p8_2_k1*.yaml' -print -quit)"
test -z "$(find "${REPO_ROOT}/tools/inference_contracts" -maxdepth 1 -name 'run_deepseek_p8_2_k1*' -print -quit)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
~~~

若 K0 派生证据缺失或漂移，给 `blocked_p8_2_k1_k0_reference_evidence_drift`。不得重跑 K0，不得因
交叉检查失败而启动新请求。

## 5. 结束资源不变性、分级与回报

再次只读记录 keep-alive/NPU/端口/vLLM 状态，并逐字节比较任务前后的 keep-alive 进程快照；不得停止或
重启 keep-alive。仓库 tracked 状态必须仍干净，仓库内不得产生 K1 结果目录或其他新文件。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TMP_AUDIT=/tmp/opencode/p8_2_k1_frozen_stack_import_compatibility_review_2026_0717

ps -eo pid,ppid,pgid,stat,cmd | grep -E 'npu_keep_alive|#0#|#1#|#2#|#3#|#4#|#5#|#6#|#7#' > "${TMP_AUDIT}/keep_alive_after.txt" || true
npu-smi info > "${TMP_AUDIT}/npu_after.txt"
ss -ltnp | grep ':7000' > "${TMP_AUDIT}/port_7000_after.txt" || true
ps -eo pid,ppid,pgid,stat,cmd | grep -E '[v]llm|[V]LLM' > "${TMP_AUDIT}/vllm_after.txt" || true
cmp "${TMP_AUDIT}/keep_alive_before.txt" "${TMP_AUDIT}/keep_alive_after.txt"
cmp "${TMP_AUDIT}/port_7000_before.txt" "${TMP_AUDIT}/port_7000_after.txt"
cmp "${TMP_AUDIT}/vllm_before.txt" "${TMP_AUDIT}/vllm_after.txt"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"

python3 - "${TMP_AUDIT}" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
rows = []
for path in sorted(root.iterdir()):
    if path.is_file():
        rows.append({
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sensitivity": "bounded_operational_metadata_no_model_content_or_token_ids",
        })
summary = {
    "task_id": "p8_2_k1_frozen_stack_import_compatibility_review_2026_0717",
    "server_grade": "candidate_blocked_p8_2_k1_frozen_stack_import_incompatible",
    "files": rows,
    "total_bytes": sum(row["bytes"] for row in rows),
    "npu_started": False,
    "vllm_started": False,
    "model_request_sent": False,
    "workload_created": False,
    "next_task_authorized": False,
}
(root / "review_summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(summary, indent=2, sort_keys=True))
PY
~~~

分级：

- 同步、仓库 hash、合同或 compile 失败：`blocked_p8_2_k1_source_or_contract_gate`；
- 安装态源码或 runtime probe 与冻结审计不同：`blocked_p8_2_k1_runtime_source_drift`；
- K0 交叉证据缺失或漂移：`blocked_p8_2_k1_k0_reference_evidence_drift`；
- 全部只读门匹配：服务器只能给
  `candidate_blocked_p8_2_k1_frozen_stack_import_incompatible`，等待开发机独立复核。

回报必须包括：同步前后 HEAD/origin/main/tracked 状态、五个仓库 hash、pytest/compile、冻结 source hash
gate、三个 missing module resolution、`NPUOffloadingSpec` import error type/message、精确
`KVTransferConfig` 字段、两处 single-group assertion、K0-R1 grade/20 requests/source unchanged/两类 hybrid
manager、K1 workload/runner 不存在、任务前后 keep-alive/NPU/端口/vLLM 只读快照，以及 `/tmp` 小文件逐项
path/bytes/SHA-256/sensitivity 与总 bytes。

`/tmp` 输出仅是待复核的 operational metadata；`result_transfer_authorized:false`。不要 email、不要调用
upload-api、不要复制到仓库结果树。raw package、request bodies、generated content/token IDs 均不得读取或
外发。本任务没有可接受的 K1 green：不得运行 offload、不得创建 workload、不得应用兼容性 patch、不得进入 K2；
也不得进入 K3、K4、P8.3 或 P9。完成回报后保持等待。
