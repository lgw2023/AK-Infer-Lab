# Developer to Server

## 当前唯一服务器动作：只读同步复核并等待，不执行 NPU

~~~text
task_id: p6_3c_strict_single_variable_blocked_closeout_sync_review_2026_0716
execution_mode: authorized_read_only_sync_review_and_wait_no_npu
server_sync_review_authorized: true
workload: none
npu_execution_authorized: false
next_task_authorized: false
standing_npu_and_vllm_consumption_authorization: true
current_completed_lineage: P6.3B-R4-R1
developer_accepted_grade: green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
p6_3c_feasibility_grade: blocked_p6_3c_not_strict_single_variable
p6_3c_executable_workload: none
next_stage_candidate: none_pending_user_decision_after_p6_3c_blocked
claim_boundary: repository_sync_and_frozen_source_contract_review_only
~~~

本任务只要求服务器同步最新远程 `main`，读取并复核已发布的 P6.3 收口证据，然后停止等待。它不授权
启动推理服务或 vLLM、占用 NPU、发送模型请求、修改 runtime/checkpoint/tracked 文件、创建实验结果目录或外发文件。

开发机已关闭的证据门保持不变：

- P6.1C-R1=`green_mtp_official_context_ladder`；
- P6.1=`green_mtp_unprofiled_baseline`；
- P6.2=`green_mtp_profiled_evidence`；
- P6.3A=`green_p6_3a_mtp_matched_ab`；
- P6.3B-R4-R1=`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`，只接受 primary scope 内
  explicit Prefix Cache mechanism effect，不外推普遍命中或性能收益；
- P6.3C=`blocked_p6_3c_not_strict_single_variable`。冻结 vLLM CLI 有显式 Chunked Prefill
  true/false，但 frozen `max_num_batched_tokens=4096 < max_model_len=135168`（即 `4096 < 135168`）使 off 侧在 resolved
  runtime config 与任何请求前被 validation 拒绝；改变 token budget 或 max model length 都是禁止的第二变量。

P6.3B-R4-R1 的已验收结构为 same R2 repair、显式
`--no-enable-prefix-caching` / `--enable-prefix-caching`、`16/16` prime、`48/48` measured、总计
`64/64` request；on 侧三个 primary group 为 `9/9` positive，其余 `15` 条 boundary follower 仍为零命中。
原 P6.3B yellow、R1 red、R3 on-vs-on yellow 与 R4 root-squash blocked 均保留为历史 provenance，
本次只读同步复核不得重跑或改写它们。

服务器只读执行以下命令：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
TASK_ID=p6_3c_strict_single_variable_blocked_closeout_sync_review_2026_0716
AUDIT_PATH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/p6_3c_chunked_prefill_feasibility_audit.yaml
HANDOFF_PATH=${REPO_ROOT}/通信模块/docs/developer-to-server.md

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"

grep -F "task_id: ${TASK_ID}" "${HANDOFF_PATH}"
grep -F "server_sync_review_authorized: true" "${HANDOFF_PATH}"
grep -F "npu_execution_authorized: false" "${HANDOFF_PATH}"
grep -F "next_task_authorized: false" "${HANDOFF_PATH}"

test "$(stat -c '%s' "${AUDIT_PATH}")" = 7489
test "$(sha256sum "${AUDIT_PATH}" | awk '{print $1}')" = aeb91adc8b0b432765392ff85d7d39a3bff5a28aa9df85024a2580189726e7f6
grep -F "grade: blocked_p6_3c_not_strict_single_variable" "${AUDIT_PATH}"
grep -F "max_model_len: 135168" "${AUDIT_PATH}"
grep -F "max_num_batched_tokens: 4096" "${AUDIT_PATH}"
grep -F "formal_matched_ab_allowed: false" "${AUDIT_PATH}"

test -z "$(find "${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads" -maxdepth 1 -type f -name 'p6_3c*.yaml' -print -quit)"
test -z "$(find "${REPO_ROOT}/tools/inference_contracts" -maxdepth 1 -type f -iname '*p6_3c*' -print -quit)"

cd "${REPO_ROOT}"
"${PYTHON_BIN}" -m pytest \
  tests/inference_contracts/test_deepseek_p6_3b_r4_r1_closeout.py \
  tests/inference_contracts/test_deepseek_p6_3c_chunked_prefill_feasibility.py \
  -q

printf 'task_id=%s\n' "${TASK_ID}"
printf 'HEAD=%s\n' "$(git rev-parse HEAD)"
printf 'origin/main=%s\n' "$(git rev-parse origin/main)"
printf 'audit_bytes=%s\n' "$(stat -c '%s' "${AUDIT_PATH}")"
printf 'audit_sha256=%s\n' "$(sha256sum "${AUDIT_PATH}" | awk '{print $1}')"
printf '%s\n' 'p6_3c_workload=none'
printf '%s\n' 'p6_3c_mode_runner=none'
printf '%s\n' 'npu_or_vllm_started=false'
git status --short --branch
~~~

执行后在当前任务通道中回报：`task_id`、HEAD、`origin/main`、tracked status、两份定向合同的 pytest
摘要、audit bytes/SHA-256、P6.3C grade、`p6_3c_workload=none`、`p6_3c_mode_runner=none` 与
`npu_or_vllm_started=false`。不得创建新的任务结果目录，不得外发任何文件；不要创建或发送附件，
不要调用任何外发接口，不要把状态回报写成新的
tracked 文件。回报后停止并等待用户和开发机决定下一阶段；不得通过改变第二参数伪造 P6.3C matched A/B，
也不得自动进入 P7、P8 或 P9。
