# Developer to Server

## 当前唯一服务器动作：P8.2-K0-R1 既有 raw evidence 离线重分级

~~~text
task_id: p8_2_k0_r1_offline_refinalization_2026_0717
execution_mode: authorized_offline_existing_raw_evidence_refinalization_no_npu
server_sync_review_authorized: true
offline_refinalization_authorized: true
npu_execution_authorized: false
next_task_authorized: false
result_transfer_authorized: false
lifecycle_count_exact: 0
request_count_exact: 0
source_request_count_exact: 20
source_evidence_file_count_exact: 29
original_result_dir_must_remain_unchanged: true
new_model_requests_authorized: false
keep_alive_mutation_authorized: false
profiler_authorized: false
offload_authorized: false
p8_2_k1_execution_authorized: false
no_k1_k2_k3_k4_p8_3_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

当前任务只修正 P8.2-K0 finalizer 合同并复核既有证据，不是新的 NPU workload。原 K0 在四个
fresh lifecycle 中已完成 20/20 请求、12/12 measured、6/6 matched pair，AB/BA 顺序、body pairing、
显式 Prefix Cache 单变量、同 R2 repair、resolved config、MTP/queue、6 个 on follower 各 hit=`49152`、
off hit total=`0` 与 cleanup 均通过。服务器 red 的直接原因是旧 finalizer 读取了不存在的
`generated_tokens` / `streamed_tokens`，而真实 request producer 写入 `generated_token_count` /
`streamed_token_count`；旧单测 fixture 也使用了错误别名。本轮必须从原 raw evidence 只读重算，不能
启动 vLLM、不能使用 NPU、不能发送模型请求，也不能把 standing 资源许可解释为本任务的占卡许可。

保留且不撤销的 lineage：P6.3B-R4-R1=`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`；
P8.1 parent=`yellow_p8_1_matrix_trace_invalid`；P8.1-R1=
`green_p8_1_r1_official_mtp_observe_only_matrix` 且 `cause_proven_as_unique: false`；P6.3C=
`blocked_p6_3c_not_strict_single_variable`。K0-R1 只修 finalizer，不重开上述阶段。

## 1. 同步门与冻结仓库合同

服务器从自己的干净 `main` 镜像执行普通快进同步；不得使用 reset、stash、rebase、checkout 覆盖、
`sync.sh`、server commit 或 push。153 个左右服务器本地 `??` 产物可以保留，但 tracked 状态必须干净。

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
    "tools/inference_contracts/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py": "6d698a6ebcba8808ffe8ca4117a7dc845aa2ab2162d64586bdb5f523e48f6882",
    "tests/inference_contracts/test_deepseek_p8_2_k0_order_balanced_prefix_baseline.py": "2680dcec49e516742867335a6f3d908828cf76f79e18a6c8c9707aee8050a3d3",
    "benchmarks/deepseek_v4_flash/workloads/p8_2_k0_order_balanced_prefix_cache_baseline.yaml": "f8287d4a0954b03a227fbffaff0f0f70a5f8776ab40bedb85174602d5cc5b796",
    "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml": "23c0ab2fc7f41f155736f567f2d0d16c146a0d93dadecaf932e7a980e3cce822",
}
for relative, wanted in expected.items():
    path = Path(relative)
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != wanted:
        raise SystemExit(f"frozen repo hash mismatch: {relative} {got} != {wanted}")
print("frozen_repo_hash_gate=pass")
PY

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k0_order_balanced_prefix_baseline.py -q
python3 -m py_compile \
  tools/inference_contracts/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py
~~~

若同步、tracked-clean、四个冻结 hash、定向合同或 compile 任一失败，立即给
`blocked_p8_2_k0_r1_source_or_contract_gate` 并停止；不得创建派生目录、不得改原结果、不得启动 runtime。

## 2. 零资源扰动门与原始证据预检

固定服务器路径：

~~~text
SOURCE_RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k0_deepseek_v4_flash_order_balanced_prefix_cache_baseline_2026_0717_run01
DERIVED_RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k0_r1_offline_refinalization_2026_0717_run01
REFINALIZER=/data/node0_disk1/liguowei/AK-Infer-Lab/tools/inference_contracts/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py
~~~

本节只读查看 keep-alive 与 NPU 状态。不得停止或重启 keep-alive，不得 `kill` 任意进程，不得清卡，
不得启动 vLLM，不得发送模型请求。记录 refinalization 前的 marker/PGID/进程数、每卡 HBM、端口 7000；
端口若被既有无关进程占用也不得处置，因为本任务完全不使用该端口。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
SOURCE_RESULT_DIR="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k0_deepseek_v4_flash_order_balanced_prefix_cache_baseline_2026_0717_run01"
DERIVED_RESULT_DIR="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k0_r1_offline_refinalization_2026_0717_run01"

test -d "${SOURCE_RESULT_DIR}"
test ! -e "${DERIVED_RESULT_DIR}"
ps -eo pid,ppid,pgid,stat,cmd | grep -E 'npu_keep_alive|#0#|#1#|#2#|#3#|#4#|#5#|#6#|#7#' || true
npu-smi info
ss -ltnp | grep ':7000' || true

python3 - "${SOURCE_RESULT_DIR}" <<'PY'
from pathlib import Path
import json
import sys

from tools.inference_contracts import (
    run_deepseek_p8_2_k0_order_balanced_prefix_baseline as runner,
)

source = Path(sys.argv[1])
inventory = runner.inspect_k0_source_evidence(source)
print(json.dumps({
    "source_evidence_file_count": inventory["source_evidence_file_count"],
    "source_evidence_inventory_sha256": inventory["source_evidence_inventory_sha256"],
}, sort_keys=True))
if inventory["source_evidence_file_count"] != 29:
    raise SystemExit("source evidence count drift")
PY
~~~

预检要求 29 个必需输入全部存在、四个 lifecycle 各 5 行、总计 20 行，并且每行都有真实 producer
字段 `generated_token_count` 和 `streamed_token_count`。任一缺失、旧别名替代、task identity/count 错误，
给 `blocked_p8_2_k0_r1_raw_evidence_missing_or_drifted` 并停止；不得静默重跑 K0，不得创建新请求。

## 3. 离线 refinalization 与双向不变性复核

只允许执行一次下面的 `refinalize`。它先冻结 29 个源文件的 relative path/bytes/SHA-256，再创建独立派生
目录；原 K0 目录只读。不得把 `DERIVED_RESULT_DIR` 改到原目录内，不得覆盖已存在目录，不得 retry。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
SOURCE_RESULT_DIR="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k0_deepseek_v4_flash_order_balanced_prefix_cache_baseline_2026_0717_run01"
DERIVED_RESULT_DIR="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k0_r1_offline_refinalization_2026_0717_run01"
REFINALIZER="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py"

set +e
python3 "${REFINALIZER}" refinalize \
  --source-artifact-dir "${SOURCE_RESULT_DIR}" \
  --output-dir "${DERIVED_RESULT_DIR}"
refinalize_exit=$?
set -e

test -d "${DERIVED_RESULT_DIR}"
test -f "${DERIVED_RESULT_DIR}/grading_inputs.json"
test -f "${DERIVED_RESULT_DIR}/environment_and_hashes.json"

python3 - "${SOURCE_RESULT_DIR}" "${DERIVED_RESULT_DIR}" "${refinalize_exit}" <<'PY'
from pathlib import Path
import csv
import hashlib
import json
import sys

source = Path(sys.argv[1])
derived = Path(sys.argv[2])
exit_code = int(sys.argv[3])
grading = json.loads((derived / "grading_inputs.json").read_text())
environment = json.loads((derived / "environment_and_hashes.json").read_text())
request_summary = json.loads((derived / "mtp_queue_health_summary.json").read_text())

assert exit_code == 0, exit_code
assert grading["server_grade"] == "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
assert grading["successful_request_count"] == 20
assert grading["request_evidence_exact"] is True
assert grading["first_request_evidence_failure"] is None
assert grading["source_evidence_file_count"] == 29
assert grading["source_evidence_unchanged"] is True
assert grading["on_measured_hit_exact_count"] == 6
assert grading["off_prefix_hit_total"] == 0
assert grading["cleanup"] == "clean"
assert environment["execution_mode"] == "offline_existing_raw_evidence_only"
assert environment["npu_started"] is False
assert environment["vllm_started"] is False
assert environment["model_request_sent"] is False
assert environment["source_evidence_file_count"] == 29
assert (derived / "request_body_manifest.json").read_bytes() == (source / "request_body_manifest.json").read_bytes()

counts = request_summary["request_evidence_predicate_counts"]
assert len(counts) == 15, counts
for predicate, count in counts.items():
    assert count == {"passed": 20, "total": 20}, (predicate, count)

with (derived / "delivery_candidates.tsv").open(newline="", encoding="utf-8") as handle:
    candidates = list(csv.DictReader(handle, delimiter="\t"))
assert len(candidates) == 14
assert sum(int(row["bytes"]) for row in candidates) <= 71680
for row in candidates:
    path = Path(row["path"])
    assert path.is_file()
    assert path.stat().st_size == int(row["bytes"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    assert row["sensitivity"] == "bounded_operational_metadata_no_content_or_token_ids"

candidate_text = "\n".join(Path(row["path"]).read_text(errors="replace") for row in candidates)
for forbidden in ('"prompt":', "generated_content", "returned_token_ids"):
    assert forbidden not in candidate_text
print("offline_refinalization_validation=pass")
PY

ps -eo pid,ppid,pgid,stat,cmd | grep -E 'npu_keep_alive|#0#|#1#|#2#|#3#|#4#|#5#|#6#|#7#' || true
npu-smi info
ss -ltnp | grep ':7000' || true
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
~~~

离线重算前后 keep-alive marker/PGID/进程形态和每卡 HBM 必须保持观察上一致；不得因 refinalizer 失败而
停止/恢复 keep-alive。若派生目录已存在、源 inventory 前后不一致、15 个 predicate 非 20/20、candidate
hash/size/sensitivity 不一致或 tracked 工作区被改动，给 `red_p8_2_k0_r1_offline_refinalization_invalid`
并停止，不 retry、不重新运行原 workload。

## 4. 分级、报告与停止边界

- 同步、仓库 hash、定向合同失败：`blocked_p8_2_k0_r1_source_or_contract_gate`；
- 原 raw evidence 缺失、canonical fields 不全或 inventory 漂移：
  `blocked_p8_2_k0_r1_raw_evidence_missing_or_drifted`；
- refinalizer/派生候选/15 predicate/不变性任一失败：
  `red_p8_2_k0_r1_offline_refinalization_invalid`；
- 所有门通过：服务器只能给
  `candidate_green_p8_2_k0_r1_offline_refinalization`，等待开发机独立复核。

回报必须包括：同步前后 HEAD/origin/main/tracked 状态、四个冻结仓库 hash、定向 pytest、原始与派生
结果目录、29-file source inventory hash、refinalize exit、K0 server grade、20/20 请求与 15 项 predicate
计数、6/6 on hit、off hit total、MTP/queue/repair/resolved/body/order/cleanup、原目录 unchanged 证明、
refinalization 前后 keep-alive/NPU/端口只读快照，以及派生 14 个候选的逐文件 path/bytes/SHA-256/
sensitivity 和总 bytes。

raw logs、raw metrics、request bodies、generated content/token IDs 与原实验树继续留服务器。候选总量必须
不超过 70KB，且 `result_transfer_authorized:false`。外发前先在当前任务通道报告 summary 精确路径、完整
候选清单、逐文件 bytes/SHA-256/sensitivity、可用 `email / upload-api / server-local` 与一个推荐方法及
理由；用户对这次完整范围重新选择前不得外发（包括不得自动外发），不得继承旧选择或失败后自动切换。

完成后停止等待开发机复核。不得接受 K0 green、不得自动进入 K1、不得执行 K1/K2/K3/K4、不得运行 profiler/HBM sampler、
不得启用 KV Cache CPU Offload/UCM/External KV、不得改变 placement/payload/runtime/repair，也不得进入
P8.3/P9。K0-R1 的 candidate green 只说明原 K0 既有证据经正确 schema 重分级完整，不自动形成通用
Prefix Cache 性能收益或新 performance reference。
