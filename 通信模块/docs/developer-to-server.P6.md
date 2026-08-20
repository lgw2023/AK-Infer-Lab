# P6.3C-R3E-F2 服务器任务：最小 request-scoped dependency-marker canary

本文件是当前唯一 P6 服务器交接。不再执行已完成的 A2 零 NPU 重聚合，不重跑 R3D 的
17 lifecycle 或五档 budget sweep。本任务只回答：新增 scheduler/worker 结构化标记能否在
真实 Ascend profiler 中连到 runtime launch 与 actual device kernel。

## 1. 任务身份与结论边界

- task ID：`p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820`；
- source A2 task ID：`p6_3c_r3e_f1_a2_step_flow_causal_linkage_2026_0809`；
- source A1 task ID：`p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808`；
- source F1 task ID：`p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01`；
- source A2 outcome：
  `temporal_step_attribution_complete_dependency_linkage_unavailable`；
- 新 variant 原因：A2 已证明 58/58 pressure step 具有 8/8 rank 时间覆盖，但没有
  host→runtime→device 共同依赖链；
- `result_transfer_authorized: true`；
- transfer method：尚未选择；
- next/larger task authorized：`false`；
- 服务器不得 push remote `main`。

必须保留 R3D 的 `persistent_prefill_tradeoff_no_candidate_within_bounds`、A1 的全 rank
描述完整但 causal unresolved，以及 A2 的 dependency linkage unavailable。本 canary 不产生
TTFT/TBT/TPS 收益结论，不自动选择 collective、compiler、MoE、attention 或任何 kernel target。

“任务执行完成”与“得到正向因果结论”是两件事。若 S1 标记完整但 profiler schema 仍无法
连上最后一段 edge，这是完整的阴性结果；不得为 green grade 改写为 temporal causal path。

## 2. 固定科学合同

| 项目 | 固定值 |
| --- | --- |
| model | `DeepSeek-V4-Flash-w8a8-mtp` |
| tensor/expert parallel | TP8 / EP |
| max model len / batch tokens / seqs | 12288 / 12288 / 9 |
| chunked prefill / prefix cache | on / off |
| resident workload | 8 请求，各256 prompt + 128 output |
| injected workload | 12281 prompt + 4 output |
| request retry | 0 |
| profiler window | warmup 后，只包含 measured staged-arrival trial |
| S1 policy | `admission_on_t4096` |
| S2 policies | `admission_on_t4096`, `persistent_on_t128` |

标记只允许 `lifecycle_id/policy_id/timing_context_id/step_index/worker_rank`。禁止 prompt、生成文本、
token ID、request ID 或其他请求内容。`record_function` range 只是 worker execute-model 的结构化
范围。它到 host op 可用范围包含；host→runtime 和 runtime→actual-kernel 必须有 profiler
flow/correlation 共同标识。

## 3. 发布资产与 SHA-256

SHA 用于确认拉取到发布资产，不禁止 task-local 真实路径/API 适配。适配仍必须返回
before/after diff、SHA、attempt 与 scientific impact。

| 文件 | SHA-256 |
| --- | --- |
| `benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_f2_request_scoped_dependency_marker_canary.yaml` | `e6ef75cbaf58aadc88885fa4e64503a8a51e4a6f14bbe6494c817795017e611e` |
| `tools/inference_contracts/p6_3c_r3e_f2_dependency_marker.py` | `d31671a9910ffd92c7f7c3e4de1ccf027971dd68013d6614963ae836a3e1be24` |
| `tools/inference_contracts/smoke_p6_3c_r3e_f2_dependency_marker.py` | `2e4ee711669f1a1580a345fe39a8410e19a9aef23b1fd97cfab9d8534ed28809` |
| `tools/inference_contracts/analyze_p6_3c_r3e_f2_dependency_markers.py` | `6ba096dbb8d3d120368000ac3cb613e84d0fc8e5ac55874a6ec4dd3208f4b927` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_dependency_marker_canary.py` | `e328af22dd713d368d38f6fb55b05b16b34309d53b33a9ce0a43e776ad98c6e0` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_mode.sh` | `e034e6098fd684cbe41ff312d961b12a7d0215de00700f9ced4bfe65a36a068c` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_experiment.sh` | `cd19a205725534c987e404deff4f0a318b7c3388ad0d5bc38dc543bf82c55ee7` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_server_task.sh` | `feaab416b3237b6ccf1795780096514ce1a6bfdba09fb651ebec81a6cadc251b` |
| `tests/inference_contracts/test_deepseek_p6_3c_r3e_f2_dependency_marker.py` | `3ca9cb7e5aafa02d61a2f1cd5211b62c049c291a5c6740298c770f24f9c8e267` |
| `tests/inference_contracts/test_deepseek_p6_3c_r2_capacity_calibrated.py` | `67a12b6bb644c1a73b1677f054f55a29cc16be97b140f12c12588b0ecbe687c0` |
| `工作记录与进度笔记本/22_P6_3C_R3E_执行路径归因与跨Rank重聚合手稿.md` | `25363345e131f0529a64f92399a0e1e4f1d3fa1af4eeca06cab38c727b48fdc4` |

```bash
sha256sum \
  benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_f2_request_scoped_dependency_marker_canary.yaml \
  tools/inference_contracts/p6_3c_r3e_f2_dependency_marker.py \
  tools/inference_contracts/smoke_p6_3c_r3e_f2_dependency_marker.py \
  tools/inference_contracts/analyze_p6_3c_r3e_f2_dependency_markers.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_dependency_marker_canary.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_mode.sh \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_experiment.sh \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_server_task.sh \
  tests/inference_contracts/test_deepseek_p6_3c_r3e_f2_dependency_marker.py \
  tests/inference_contracts/test_deepseek_p6_3c_r2_capacity_calibrated.py \
  工作记录与进度笔记本/22_P6_3C_R3E_执行路径归因与跨Rank重聚合手稿.md
```

## 4. 同步、独立 worktree 与资源门

不得修改共享 checkout，不得与其他 NPU 会话共用 0–7 卡。immutable Inbox prompt 会给出
`AK_SERVER_TASK_COMMIT`；必须确认该 commit 仍等于实时 `origin/main`，否则停止并等待新 prompt。

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820
AK_SERVER_TASK_COMMIT=${AK_SERVER_TASK_COMMIT:?set from immutable Inbox prompt}
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3e_f2_2026_0820

git -C "${SHARED_REPO}" fetch origin main
test "$(git -C "${SHARED_REPO}" rev-parse origin/main)" = \
  "${AK_SERVER_TASK_COMMIT}"
git -C "${SHARED_REPO}" cat-file -e "${AK_SERVER_TASK_COMMIT}^{commit}"
test ! -e "${WORKTREE}"
git -C "${SHARED_REPO}" worktree add --detach \
  "${WORKTREE}" "${AK_SERVER_TASK_COMMIT}"

cd "${WORKTREE}"
test "$(git rev-parse HEAD)" = "${AK_SERVER_TASK_COMMIT}"
test "$(git rev-parse origin/main)" = "${AK_SERVER_TASK_COMMIT}"
test "$(git rev-list --left-right --count HEAD...origin/main)" = $'0\t0'
test -z "$(git status --porcelain --untracked-files=no)"
sed -n '1,420p' docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
sed -n '1,520p' 通信模块/docs/developer-to-server.P6.md
```

若 worktree 目录已存在，不要删除；核对归属后使用 `..._attempt_02`。开始 S1 前检查：

```bash
pgrep -af 'p6_3c_r3e_f2|run_deepseek_p6_3c' || true
pgrep -af '[v]llm.*serve.*DeepSeek-V4-Flash' || true
ss -ltnp | grep ':7000' || true
npu-smi info
```

除本项目 low-priority keep-alive 外，任何 0–7 卡有其他作业、端口 7000 被占用或另一个 P6.3C
任务正在执行时，停止并报告；不得终止别人的作业。

## 5. 零 NPU audit 与 S0

先运行纯合同 audit：

```bash
cd "${WORKTREE}"
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_server_task.sh \
  "/audit/${TASK_ID}"
```

必须显示：S0 零 NPU；S1 一个 lifecycle/一个 pressure step；S2 仅条件执行；最多 3 lifecycle；
budget sweep/performance comparison 均为 false。

正式入口在任何 NPU stop 前自动执行 S0：

- 用目标 conda Python 解析真实 vLLM/vLLM-Ascend 路径；
- 读取 vLLM、vLLM-Ascend、torch、torch-npu 版本与源路径/SHA；
- 核对 `Scheduler.schedule`、`MultiprocExecutor.execute_model`、
  `WorkerWrapperBase.execute_model`、`NPUWorker.execute_model` 与
  `NPUModelRunner.execute_model` 签名/源 SHA；
- 验证 `SchedulerOutput` 私有 context pickle round-trip 和 marker parse round-trip；
- 证明已安装源文件前后未变且未请求 NPU operation。

S0 失败时必须在停 keep-alive 之前退出。真实 API 漂移可做 task-local 最小适配；保留原始错误、
source path/signature、before/after SHA/diff 与 scientific-impact statement。

## 6. S1 与条件 S2 正式执行

使用新 attempt 根，不删除或覆盖旧结果：

```bash
ATTEMPT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_2026_0820_attempt_01
RESULT_DIR="${ATTEMPT_ROOT}/${TASK_ID}"
test ! -e "${RESULT_DIR}"
mkdir -p "${ATTEMPT_ROOT}"

cd "${WORKTREE}"
REPO_ROOT="${WORKTREE}" \
P6_3C_SHARED_REPO_ROOT="${SHARED_REPO}" \
PYTHONUNBUFFERED=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_server_task.sh \
    "${RESULT_DIR}" \
  2>&1 | tee "${ATTEMPT_ROOT}/server_task.log"
```

固定顺序：

1. S0 真实源/API/import/pickle smoke，NPU 未使用；
2. S0 通过后停止 0–7 low-priority keep-alive；
3. S1 `f2_s1_01`：`admission_on_t4096`，一个 selected mixed pressure step；
4. 完整解析 S1 的 8 rank trace；
5. 仅当 trace 8/8 完整无 cap、marker 每 rank 恰好一个，且 marker→host、host→runtime、
   runtime→actual-kernel 三段在 8/8 rank 均闭合时放行 S2；
6. S1 阴性时立即停止，不运行 S2；
7. S1 正向时才运行 `f2_s2_01=admission_on_t4096` 与
   `f2_s2_02=persistent_on_t128`，每 policy 只选两个 pressure step；
8. 无论成功、失败、中断或提前退出，恢复恰好同一组 0–7 keep-alive，检查端口、残留进程、
   worktree cleanliness，再 finalize/package。

## 7. Keep-alive 与资源恢复

S0 不需 NPU，keep-alive 必须保持运行。S1/S2 是 TP8，确认 0–7 只有 low-priority keep-alive 后，
可停止恰好这八卡：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

正式入口已将 stop/restore 置于 trap，不要外层重复 stop。报告必须包含 S0
`npu_used=false/keep_alive_action=left_running`，以及 S1/S2 的 stopped/restored card IDs、
keep-alive marker count/card IDs、恢复状态、port 7000 listener、vLLM residual、tracked cleanliness 和
success/failure/interruption/early-exit 的实际资源恢复。恢复失败时先处理资源，不开始新 attempt 或传输。

## 8. Analyzer 与因果判定

`step_rank_marker_coverage.tsv` 逐 step×rank 报告 marker presence/count、三段 edge count 与
final-edge signature。`dependency_edge_summary.tsv` 按 policy/段报告 required link kind、total count、
pressure-step/rank-row 的 expected/complete count 和 coverage rate、是否跨多 step 重复与 missing reason。

1. `marker_to_host_op`：只接受结构化 worker range 对 host framework op 的包含；
2. `host_op_to_runtime_launch`：只接受共同 flow/correlation identifier；
3. `runtime_launch_to_actual_device_kernel`：只接受共同 identifier 且 device event 具有
   trace category/event args 的 actual-kernel provenance。

`Free/Computing/Communication/Communication(Not Overlapped)/Notify_Wait` 是 derived analysis timeline，
永远不得满足 actual-kernel edge。仅位于 marker/scheduler 时间窗内也不是 dependency proof。

只有同一 `link-kind + actual-kernel category/name` signature 在两个 S2 policy 中，每 policy 至少
两个 pressure step，且每 step 8/8 rank 都重复，才允许 `causal_bottleneck_resolved=true`。
该字段为 true 也不允许 `optimization_target_selected=true`。

## 9. 自适应权限、新 variant 与停止条件

可在 task-local overlay/attempt 修复真实源路径、符号/签名/import 时序、serialization、worker plugin
bootstrap、profiler API/trace schema、health check、warmup、端口、超时、清理、progress 和 bounded serialization；
可在新 attempt 能增加证据时重试。优先放入 attempt-local 文件并用已有环境变量指向，保持
tracked worktree clean。不得修改安装包或共享 checkout。

每次 adaptation 写入 `adaptive_execution_review.json`：attempt、原始错误、patch path、before/after SHA、
最小 diff、scientific impact、是否改变科学合同。若改变 research question、请求集、policy/A-B
difference、cell、参数、marker 负载、event-domain/link 定义或 metric，必须设置
`scientific_contract_changed=true`，创建新 variant/task ID 并报告精确 delta。

以下情况停止并返回当前证据：

- 真实源身份/安装版本不一致，且修复会改变科学问题；
- S0 无法在零 NPU 下证明 serialization/worker 插桩点；
- S1 任一 rank 缺 marker、marker 重复、trace 不完整或三段链任一缺失；
- 必须使用 event cap 才能完成；
- 0–7 卡有其他作业，或 keep-alive 无法精确恢复；
- 小包超 70KB 且无法不丢失必需证据地有界化。

不得自动进入更大性能实验、下一 optimization task 或新 profiler sweep。

## 10. 有界结果包与传输选择门

raw profiler trace、server log、完整 rank detail 与实验目录全部留服。候选小包最多 70KB，建议：

```text
result_summary.md
environment_and_hashes.json
marker_propagation_summary.json
step_rank_marker_coverage.tsv
dependency_edge_summary.tsv
cross_domain_link_chains.tsv
bottleneck_hypothesis_review.json
adaptive_execution_review.json
resource_recovery_summary.json
grading_inputs.json
scientific_outcome.json
candidate_manifest.server_local.json
```

在任何结果离服前，先一次报告：结果摘要 server path；完整附件清单；每文件 bytes、SHA-256、
sensitivity；总大小/manifest SHA；可用 `email/upload-api/server-local`；一个建议方式与原因。
然后等待用户对这一完整 scope 显式选择。`result_transfer_authorized=true` 不表示方式已选，
也不扩大文件范围。不先发 status-only 邮件，不自动切换方式。`401/409/413`、proxy/redirect、
timeout、service 或 hash 失败后必须重新获得用户选择。

## 11. 服务器报告模板

```text
P6_3C_R3E_F2_SERVER_REPORT_BEGIN
task_id / attempt_id / task_status / scientific_outcome:
repo_head / origin_main / ahead_behind / tracked_clean / shared_mutated:

S0_npu_used: false
S0_keep_alive_action: left_running
S0_source_import_smoke_complete:
vllm, vllm_ascend, torch, torch_npu versions/source paths/source SHAs:
target symbols/signatures and before/after source SHAs:
pickle_marker_roundtrip / installed_source_files_mutated:

S1_executed / lifecycle / selected_pressure_step:
S1_trace_rank_coverage / marker_exactly_once_rank_coverage:
S1_marker_to_host / host_to_runtime / runtime_to_actual_kernel coverage:
S1_dependency_linkage_gap / S2_authorized:

S2_executed / lifecycle_ids / pressure_steps_per_policy:
stable_final_edge_signature / rank_step_coverage:
causal_bottleneck_resolved:
optimization_target_selected: false
performance_gain_claimed: false

adaptation_attempts / patch paths / before_after_sha / scientific_impact:
scientific_contract_changed:

stopped_card_ids / restored_card_ids:
keep_alive_marker_count_and_card_ids / keep_alive_restored_exact:
port_7000_listener_count / vllm_residual_process_count:
tracked_worktree_clean / cleanup_complete:

server_local_raw_trace_paths / result_summary_path:
candidate_files_with_bytes_sha_sensitivity:
candidate_total_bytes / candidate_manifest_sha256:
available_transfer_methods: email, upload-api, server-local
recommended_transfer_method_and_reason:
transfer_method_selected: false
result_transfer_authorized: true
next_task_authorized: false
P6_3C_R3E_F2_SERVER_REPORT_END
```

最后明确：本任务是 request-scoped dependency-marker canary，不是性能比较。若
`causal_bottleneck_resolved=false`，精确说明是 marker→host、host→runtime 还是
runtime→actual-kernel 缺失，不得从 derived timeline 或时间重叠推断优化目标。
