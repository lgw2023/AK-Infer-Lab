# Developer to Server

## 当前唯一服务器动作：执行 official-MTP P8.1 六请求 observe-only matrix

~~~text
task_id: p8_1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0716
execution_mode: authorized_official_mtp_observe_only_six_request_matrix
workload: benchmarks/deepseek_v4_flash/workloads/p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
result_transfer_authorized: false
lifecycle_count_max: 1
request_count_exact: 6
profiler_authorized: false
offload_authorized: false
placement_or_payload_mutation_authorized: false
next_stage_after_task: wait_for_developer_review
claim_boundary: official_mtp_multicontext_shared_prefix_observe_only_trace_not_performance
~~~

本任务替代上一版尚未在服务器执行的单请求 tracer，原因是一次八卡轮次只发一个短请求的信息密度不足。
旧 `p8_official_mtp_baseline_contract.yaml`、旧单请求 workload/runner/finalizer 全部保留为 provenance，不执行、
不删除、不改写。本任务仍属于 P8.1 observe-only，不进入 P8.2。

已经闭合的 P6 状态保持不变：P6.1C-R1 official context、P6.1 unprofiled、P6.2 profiled、P6.3A
matched MTP 与 same R2 repair 的 P6.3B-R4-R1 explicit Prefix Cache 均为开发机接受的 green，后者 grade 为
`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`；P6.3C 因冻结配置 `4096 < 135168` 继续是
`blocked_p6_3c_not_strict_single_variable`，没有 executable workload。本任务不重跑这些实验。

本轮只启动一个 fresh W8A8 TP8+EP/MTP lifecycle，按固定顺序运行 `4096/65536/131072 × 2` 共六个
streaming `+64,c1` 请求。64K prime/follower 的 token-LCP 固定为 `58880`，预期 Prefix Cache hit 为
`49152`；其余请求的首 128 token 互异，预期 hit 为零。每请求分别形成 Prefix、MTP、health/queue 与
request-stage 证据，六请求完成后对同一 observation 构建两份 bundle，检查 `replay_determinism` 和
`join_coverage`。timing 只用于事件排序，不是性能结果。

### 1. 同步、tracked-clean、哈希和合同门

只在服务器主镜像 fast-forward 同步。允许既有 untracked runtime artifacts，但 tracked 文件必须干净；
不得做破坏性历史操作、运行自定义同步脚本、创建服务器侧提交或改写远程。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
TASK_ID=p8_1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0716
WORKLOAD=${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml
BASELINE=${REPO_ROOT}/benchmarks/deepseek_v4_flash/p8/p8_official_mtp_observe_matrix_contract.yaml
PREPARER=${REPO_ROOT}/tools/inference_contracts/prepare_deepseek_p8_1_observe_matrix.py
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_1_observe_only_matrix.sh
FINALIZER=${REPO_ROOT}/tools/inference_contracts/finalize_deepseek_p8_1_observe_only_matrix.py
OBSERVER=${REPO_ROOT}/tools/ak_state_runtime/vllm_ascend_observer.py
CLI=${REPO_ROOT}/tools/ak_state_runtime/cli.py
ADAPTER=${REPO_ROOT}/tools/ak_state_runtime/adapters/vllm_ascend.py
P6_MANIFEST=${REPO_ROOT}/benchmarks/deepseek_v4_flash/p6/p6_artifact_manifest.yaml
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}_run01

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"

test "$(sha256sum "${BASELINE}" | awk '{print $1}')" = 9405853cea52683828c99dfa55bc0093270102b4fe27110494502854d7dc49cb
test "$(sha256sum "${WORKLOAD}" | awk '{print $1}')" = 9d7de84a917111befd25bb28d67cb6c20f0467afe8a4480cfb4e1e233c9792c4
test "$(sha256sum "${PREPARER}" | awk '{print $1}')" = 9f331af8ff7e08f0c41b1d250beb1a7114a960fd18500ba610203024e91641bc
test "$(sha256sum "${RUNNER}" | awk '{print $1}')" = 3ebf162761db4be0c08777699eba8036c8288d7f34f5ea1e5649eb6034d4b9b1
test "$(sha256sum "${FINALIZER}" | awk '{print $1}')" = 845cb929790bf3c88fa57a21d686efc199c437103687171751f57af7b404aafe
test "$(sha256sum "${OBSERVER}" | awk '{print $1}')" = ecc7122b01c0b56cdc4817d2be780f18266097db2d16b19de0f471668765f201
test "$(sha256sum "${CLI}" | awk '{print $1}')" = 9eb3ab2d408b84361916d61fadc981ec2674be9ea154b0f47205524d5b4af5f6
test "$(sha256sum "${ADAPTER}" | awk '{print $1}')" = 17b4d344b66324a8703e8bf5599dfa2082d60fedea5db9ef208cfdb625ef158e
test "$(sha256sum "${P6_MANIFEST}" | awk '{print $1}')" = 01eda1e4b93dd6145343459ea83fe9178a18b1f3fd99ac0714ada33e7599ef9f

grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'execution_mode: authorized_official_mtp_observe_only_six_request_matrix' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'npu_execution_authorized: true' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'next_task_authorized: true' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'result_transfer_authorized: false' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'request_count: 6' "${WORKLOAD}"
grep -F 'stop_on_first_request_failure: true' "${WORKLOAD}"
grep -F 'expected_server_command_sha256: 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19' "${WORKLOAD}"

bash -n "${RUNNER}"
"${PYTHON_BIN}" -m py_compile "${PREPARER}" "${FINALIZER}" "${OBSERVER}" "${CLI}" "${ADAPTER}"
"${PYTHON_BIN}" -m pytest \
  tests/ak_state_runtime/test_baseline_contract.py \
  tests/ak_state_runtime/test_vllm_ascend_adapter.py \
  tests/ak_state_runtime/test_vllm_ascend_observer.py \
  tests/inference_contracts/test_deepseek_p8_1_official_mtp_observe_only.py \
  tests/inference_contracts/test_deepseek_p8_1_official_mtp_observe_only_matrix.py \
  -q

test ! -e "${RESULT_DIR}"
printf 'task_id=%s\n' "${TASK_ID}"
printf 'HEAD=%s\n' "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
printf 'origin/main=%s\n' "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
printf 'result_dir=%s\n' "${RESULT_DIR}"
~~~

任一同步、tracked-clean、hash、source、test 或既有结果目录门失败，评级
`blocked_p8_1_matrix_source_or_resource_gate` 并停止；不得启动 vLLM 或发送请求。

### 2. 八卡 keep-alive 与资源门

执行前先把 marker `#0#`–`#7#`、PID、PGID、命令行和每卡 HBM 写入 server-local inventory。只允许终止
这八个已核对的 keep-alive process group；不得触碰其他用户、其他任务或非 marker 进程。终止后确认：

- NPU 0–7 均无运行进程；
- 端口 7000 空闲；
- 没有 residual vLLM/engine worker；
- 八卡 health 正常，模型路径与 runtime 路径仍可读。

任何一项不满足均按 resource gate blocked 停止，不创建正式结果目录。停止前 inventory、八个 PGID、停止后
`npu-smi info` 与端口证据留在服务器；不进入 bounded transfer candidates。

### 3. 执行六请求 P8.1 matrix

资源门通过后只运行以下一次 runner。runner 会先从冻结的 4K source payload 生成六份 server-local body 并重算
pairwise token-LCP，再启动一个 official-MTP lifecycle。固定顺序为：

1. `short_isolated_a = 4096+64`，预期 hit=0；
2. `medium_shared_prime = 65536+64`，预期 hit=0；
3. `medium_shared_follower = 65536+64`，与 prime 的 LCP=58880、预期 hit=49152；
4. `long_isolated_a = 131072+64`，预期 hit=0；
5. `short_isolated_b = 4096+64`，预期 hit=0；
6. `long_isolated_b = 131072+64`，预期 hit=0。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0716
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_1_observe_only_matrix.sh
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
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
grading = json.loads((root / "grading_inputs.json").read_text(encoding="utf-8"))
for key in (
    "grade",
    "successful_request_count",
    "request_matrix_exact",
    "shared_prefix_exact",
    "isolated_zero_hit",
    "per_request_mtp_ok",
    "health_queue_ok",
    "transfer_boundary_ok",
    "replay_deterministic",
    "join_coverage_complete",
    "trace_validation_errors",
    "request_stage_event_count",
    "state_object_count",
    "placement_decision_count",
    "cleanup",
):
    print(f"{key}={grading[key]}")
delivery = root / "delivery_candidates.tsv"
if delivery.is_file():
    print(delivery.read_text(encoding="utf-8"), end="")
    print(f"candidate_total_bytes={(root / 'candidate_total_bytes.txt').read_text().strip()}")
PY
else
  printf '%s\n' 'server_grade=blocked_red_or_partial_before_finalizer'
  find "${RESULT_DIR}" -maxdepth 3 -type f -printf 'existing_artifact\t%p\t%s\n' | sort
fi

git -C "${REPO_ROOT}" status --short --branch --untracked-files=no
exit "${runner_exit}"
~~~

恢复动作必须等价于：

~~~bash
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

无论 runner 成功或失败都必须恢复。恢复后核对 marker `#0#`–`#7#`、16 个预期进程和每卡 HBM；若恢复失败，
在回报中标红，但不得用额外模型请求验证恢复。不得发送第 7 个请求，也不得在任一 slot 失败后补发或 retry。

### 4. Candidate green、停止分级与证据边界

只有以下全部成立，服务器才可给
`candidate_green_p8_1_official_mtp_observe_only_matrix`：

- 6/6 请求按固定顺序首次成功；prompt 为 `4096/65536/65536/131072/4096/131072`，每个 generated 与
  streamed 均为 64，HTTP 200、finish=`length`、SSE done；
- 六个 request body hash 唯一；除 64K prime/follower 外，任意两 body 的 token-LCP `<128`；
- follower 的 Prefix hit 精确为 49152，其余五个请求 hit 精确为 0，每请求 query delta 正增；
- 每请求 MTP drafts 与 draft tokens 正增、accepted counter 不倒退；每请求前后 health 正常，完成后
  running/waiting 均为 0；
- 同一 session 内有 18 个 request-stage event、6 个 Prefix proxy StateObject、6 个 observe-only no-op
  decision；所有 decision `executed=false`、所有 payload ref 为 null、`trace_validation_errors=0`；
- 两份 bundle 的相对文件集合与 SHA-256 完全一致，`replay_determinism=true`；
- request→runtime→object join 完整。public metrics 未提供 request→device/rank join 时必须记录
  `unavailable_with_explicit_reason`，不得伪造 device identity；
- cleanup clean、端口释放、无 residual vLLM，并恢复八卡 keep-alive。

分级：preflight/resource/hash 失败为 `blocked_p8_1_matrix_source_or_resource_gate`；server 未 ready 为
`red_p8_1_matrix_server_not_ready`；零成功请求为 `red_p8_1_matrix_request_no_success`；只有 1–5 个成功请求为
`yellow_p8_1_matrix_partial`；六请求成功但 Prefix/MTP/queue/trace/replay/join 任一不完整为
`yellow_p8_1_matrix_trace_invalid`。任何首错都保留并停止，不改 context、MTP、Prefix Cache、Chunked Prefill、
graph、token budget、`max_num_seqs`、block size、runtime 或 patch；不启用 profiler/offload，不得自动进入 P8.2、
P7 或 P9。

### 5. 回报与外发禁令

在当前任务通道回报：task_id、HEAD/origin/main、tracked status、定向 pytest、keep-alive 停止/恢复清单、runner
exit、server grade、6 个 slot 的 request/Prefix/MTP/health/queue 摘要、trace/replay/join/cleanup、精确结果目录，
以及 `delivery_candidates.tsv` 的完整逐文件 bytes/SHA-256/sensitivity 与候选总 bytes。

raw server log、Prometheus snapshots、六份 request body、逐请求 observations、两个完整 bundle 与生成 token IDs
留服务器，不得加入候选。bounded candidates 仅限 workload 声明的 13 个小文件，总量不得超过 70KB。
当前 `result_transfer_authorized:false`：必须先报告完整候选范围、`email / upload-api / server-local` 三种方法与
一个推荐方法及理由；用户重新选择一个方法前不得外发、不得创建发送附件、不得调用外发接口。服务器只能给
candidate grade，开发机独立复核前不得升级为 accepted green，也不得自动进入下一阶段。
