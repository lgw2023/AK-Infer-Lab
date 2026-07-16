# Developer to Server

## 当前唯一服务器动作：执行官方 MTP P8.1 observe-only 单请求 tracer bullet

~~~text
task_id: p8_1_deepseek_v4_flash_official_mtp_observe_only_trace_2026_0716
execution_mode: authorized_official_mtp_observe_only_single_request
workload: benchmarks/deepseek_v4_flash/workloads/p8_1_vllm_ascend_official_mtp_observe_only_adapter_smoke.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
result_transfer_authorized: false
request_count_max: 1
profiler_authorized: false
offload_authorized: false
placement_or_payload_mutation_authorized: false
next_stage_after_task: wait_for_developer_review
claim_boundary: official_mtp_4096_64_c1_observe_only_trace_not_performance
~~~

本任务承接已经闭合的 P6 evidence chain，不重跑 P6.3B，也不通过第二变量重开 P6.3C。已接受状态保持：

- P6.1C-R1=`green_mtp_official_context_ladder`；
- P6.1=`green_mtp_unprofiled_baseline`；
- P6.2=`green_mtp_profiled_evidence`；
- P6.3A=`green_p6_3a_mtp_matched_ab`；
- P6.3B-R4-R1=`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`，两侧使用 same R2 repair，仅限 primary-scope mechanism effect；
- P6.3C=`blocked_p6_3c_not_strict_single_variable`，冻结关系为 `4096 < 135168`，没有 executable workload。

P6 五份汇总交付物已物化在 `benchmarks/deepseek_v4_flash/p6/`。本任务保留历史 no-MTP
`p8_baseline_contract.yaml / frozen_degraded`，只使用新的
`p8_official_mtp_baseline_contract.yaml / frozen_official`，复用已验收 P6.1 `4096+64+c1` 形态。

### 1. 同步、tracked-clean 与冻结文件门

只在服务器主镜像执行 fast-forward 同步；允许服务器已有 untracked runtime artifacts，但 tracked 文件必须干净。
不得 reset、stash、checkout 覆盖、调用任何同步脚本、创建服务器提交或 push。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
TASK_ID=p8_1_deepseek_v4_flash_official_mtp_observe_only_trace_2026_0716
WORKLOAD=${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p8_1_vllm_ascend_official_mtp_observe_only_adapter_smoke.yaml
BASELINE=${REPO_ROOT}/benchmarks/deepseek_v4_flash/p8/p8_official_mtp_baseline_contract.yaml
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_1_observe_only.sh
FINALIZER=${REPO_ROOT}/tools/inference_contracts/finalize_deepseek_p8_1_observe_only.py
ADAPTER=${REPO_ROOT}/tools/ak_state_runtime/adapters/vllm_ascend.py
P6_MANIFEST=${REPO_ROOT}/benchmarks/deepseek_v4_flash/p6/p6_artifact_manifest.yaml
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}_run01

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"

test "$(sha256sum "${BASELINE}" | awk '{print $1}')" = 128907207f23c91e4383a8c58d32d006372214c329dfaf77ab2bc15d057b91e4
test "$(sha256sum "${WORKLOAD}" | awk '{print $1}')" = 5358f8fd264c0d84c266d4eee3c5a950efe74f90d4ccb0096fd8bdb1acbc10aa
test "$(sha256sum "${RUNNER}" | awk '{print $1}')" = d3efcd8f7207dafde49854cd473de40743c93e87f9cf3d03be78860387ed8e24
test "$(sha256sum "${FINALIZER}" | awk '{print $1}')" = c5807422de1c1faa80d5712543290cdfe7cd13d7cca1ce826410258614c398ed
test "$(sha256sum "${ADAPTER}" | awk '{print $1}')" = 17b4d344b66324a8703e8bf5599dfa2082d60fedea5db9ef208cfdb625ef158e
test "$(sha256sum "${P6_MANIFEST}" | awk '{print $1}')" = 01eda1e4b93dd6145343459ea83fe9178a18b1f3fd99ac0714ada33e7599ef9f

grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'npu_execution_authorized: true' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'next_task_authorized: true' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'result_transfer_authorized: false' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'contract_status: frozen_official' "${BASELINE}"
grep -F 'speculative_mtp:' "${WORKLOAD}"
grep -F 'request_count: 1' "${WORKLOAD}"
grep -F 'no_second_request: true' "${WORKLOAD}"
grep -F 'expected_server_command_sha256: 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19' "${WORKLOAD}"

bash -n "${RUNNER}"
"${PYTHON_BIN}" -m py_compile "${FINALIZER}"
"${PYTHON_BIN}" -m pytest \
  tests/ak_state_runtime/test_baseline_contract.py \
  tests/ak_state_runtime/test_vllm_ascend_adapter.py \
  tests/ak_state_runtime/test_vllm_ascend_observer.py \
  tests/inference_contracts/test_deepseek_p6_closeout_deliverables.py \
  tests/inference_contracts/test_deepseek_p8_1_official_mtp_observe_only.py \
  -q

test ! -e "${RESULT_DIR}"
printf 'task_id=%s\n' "${TASK_ID}"
printf 'HEAD=%s\n' "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
printf 'origin/main=%s\n' "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
printf 'result_dir=%s\n' "${RESULT_DIR}"
~~~

### 2. 八卡 keep-alive 与资源门

服务器上一只任务结束后已恢复官方八卡 keep-alive。执行本任务前，先列出 marker `#0#`–`#7#` 对应的
全部 PID/PGID，并复用上一只只读任务中已经验证的范围化操作：只向这 8 个 keep-alive process group 发送
`SIGTERM`，不得杀其他用户、其他任务或非 marker 进程。然后确认 NPU 0–7 均无运行进程、端口 7000 空闲、
没有残留 vLLM；任一资源不满足则写 `blocked_p8_1_source_or_resource_gate` 并停止，不创建结果目录。

把停止前 inventory、实际停止的 8 个 PGID、停止后 `npu-smi info` 与端口检查结果保留在任务通道或
server-local 临时文件中。不要把 keep-alive 进程当作模型 workload，也不要修改官方脚本。

### 3. 执行唯一 P8.1 workload

资源门通过后运行下列命令。runner 自带 frozen source/payload/patch/command hash 门，使用 NFS-safe
task-local overlay，启动一个 fresh W8A8 TP8+EP/MTP lifecycle，只发送一个 streaming `4096+64` 请求，
随后生成 observe-only bundle 并清理服务。不得手工修改 runner 参数或在失败后补发。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_1_deepseek_v4_flash_official_mtp_observe_only_trace_2026_0716
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_1_observe_only.sh
KEEP_ALIVE=/data/node0_disk1/Public/npu_keep_alive.sh

restore_keep_alive() {
  bash "${KEEP_ALIVE}" 0 1 2 3 4 5 6 7
}
trap restore_keep_alive EXIT

set +e
bash "${RUNNER}" "${RESULT_DIR}"
runner_exit=$?
set -e

restore_keep_alive
trap - EXIT

printf 'runner_exit=%s\n' "${runner_exit}"
test -f "${RESULT_DIR}/cleanup_status.txt"
printf 'cleanup=%s\n' "$(cat "${RESULT_DIR}/cleanup_status.txt")"

if test -f "${RESULT_DIR}/grading_inputs.json"; then
  "${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python" - "${RESULT_DIR}" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
grading = json.loads((root / "grading_inputs.json").read_text(encoding="utf-8"))
print(f"server_grade={grading['grade']}")
print(f"request_exact={str(grading['request_exact']).lower()}")
print(f"mtp_activity_ok={str(grading['mtp_activity_ok']).lower()}")
print(f"trace_validation_errors={grading['trace_validation_errors']}")
print(f"request_stage_event_count={grading['request_stage_event_count']}")
print(f"state_object_count={grading['state_object_count']}")
print(f"placement_decision_count={grading['placement_decision_count']}")
print(f"observe_only_decisions_ok={str(grading['observe_only_decisions_ok']).lower()}")
print(f"payload_refs_absent={str(grading['payload_refs_absent']).lower()}")
for path in sorted(root.iterdir()):
    if path.is_file() and path.name in {
        "result_summary.md",
        "environment_and_hashes.json",
        "request_result.json",
        "prefix_cache_metrics.json",
        "transfer_availability.json",
        "trace_summary.json",
        "grading_inputs.json",
        "cleanup_status.txt",
        "first_failure_excerpt.txt",
    }:
        content = path.read_bytes()
        print(f"candidate\t{path}\t{len(content)}\t{hashlib.sha256(content).hexdigest()}\toperational_metadata")
PY
else
  printf '%s\n' 'server_grade=blocked_or_red_before_finalizer'
  find "${RESULT_DIR}" -maxdepth 2 -type f -printf 'existing_artifact\t%p\t%s\n' | sort
fi

git -C "${REPO_ROOT}" status --short --branch --untracked-files=no
exit "${runner_exit}"
~~~

恢复命令等价于 `bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7`。恢复后必须确认 8 卡各自 marker `#0#`–`#7#`、进程数与 HBM 占用回到官方 keep-alive 预期；若 runner
失败也必须恢复。恢复 keep-alive 不改变实验 grade，但缺失恢复必须在回报中标红。

### 4. 成功门、停止门与回报

只有以下全部成立，服务器才可给
`candidate_green_p8_1_official_mtp_observe_only_trace`：唯一请求 HTTP 200，prompt/generated/streamed
为 `4096/64/64`、finish=`length`、SSE done；MTP drafts/draft tokens 正增且 counters 连续；3 个
request-stage event、1 个 Prefix proxy StateObject、1 个 observe-only no-op decision，decision
`executed=false`、所有 payload ref 为 null、`trace_validation_errors=0`；transfer 不可用时只记录 unavailable，
不得伪造 event；cleanup clean、端口释放、无残留 vLLM，并恢复 keep-alive。

任一 source/resource/hash 门失败即 `blocked_p8_1_source_or_resource_gate`；server 未 ready 即
`red_p8_1_official_mtp_server_not_ready`；唯一请求失败即 `red_p8_1_official_mtp_request_no_success`；请求成功但
trace/MTP/observe-only 结构不完整即 `yellow_p8_1_official_mtp_trace_invalid`。任何失败均保留首错并停止：
不得发送第二个请求，不得 retry，不得改变 context、MTP、Prefix Cache、Chunked Prefill、graph、token budget、
`max_num_seqs`、block size、runtime 或 patch；不得启用 profiler/offload，不得自动进入 P8.2、P7 或 P9。

在当前任务通道回报：task_id、HEAD/origin/main、tracked status、定向 pytest 摘要、keep-alive 停止/恢复清单、
runner exit、server grade、request/MTP/trace/cleanup 结构、精确结果目录、完整 bounded candidate 列表的逐文件
bytes/SHA-256/sensitivity、候选总 bytes，以及 `email / upload-api / server-local` 三种可用方法和一个推荐方法及理由。
当前 `result_transfer_authorized:false`：在用户对这次完整范围重新选择单一方法前，不得外发文件、不得创建或发送
附件、不得调用任何外发接口。server candidate green 也必须等待开发机独立复核，不能自行升级为 accepted green。
