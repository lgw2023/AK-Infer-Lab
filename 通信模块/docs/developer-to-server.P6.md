# P6.3C-R3E-F2 服务器后续任务：marker 路径原位诊断与有界 S1 重试

本文件是当前唯一 P6 服务器交接。首轮 F2 已安全完成 S0 和一个 S1 lifecycle，但返回包只证明
`dependency_marker_canary_evidence_incomplete`：analyzer 未完整解析 trace，且 8/8 rank 均未发现
worker marker。它不是“profiler 已完整证明 marker 不可传播”的阴性科学结论。

本轮先在首轮原始结果上做零 NPU 原位诊断；只有诊断定位到不改变科学合同的实现/解析问题，且新的
最小 S1 能增加证据时，才允许一次 task-local 修复后的 S1 重试。即使重试转为正向，本轮也不执行
S2，不进入性能比较或 optimization task。

## 1. 任务身份与当前事实

- follow-up task ID：
  `p6_3c_r3e_f2_d1_marker_path_diagnosis_and_bounded_s1_retry_2026_0820`；
- source experiment task ID：
  `p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820`；
- source commit：`b146b5005b9774aed134701119b1bf233f68ac11`；
- source result package（开发机已读）：
  `/Volumes/SSD1/Inbox/2026-08-20/p6_3c_r3e_f2_2026_0820/`；
- source server result root（首选核对路径，不得凭此覆盖任何内容）：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_2026_0820_attempt_01/p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820`；
- source evidence status：`incomplete`；
- source scientific outcome：`dependency_marker_canary_evidence_incomplete`；
- S0 source/import/pickle：通过；installed/shared source 未修改；
- S1 lifecycle：`f2_s1_01`，selected mixed pressure step=`31`；
- S1 analyzer：`trace_parse_complete=false`、`trace_rank_coverage_complete=false`、
  `observed_marker_rank_row_count=0/8`；
- S2：未授权、未执行；这是正确的 staged stop；
- source experiment exit code：`2`；0–7 keep-alive 已精确恢复，端口 7000 与 vLLM 残留均为 0；
- `causal_bottleneck_resolved=false`、`optimization_target_selected=false`、
  `performance_gain_claimed=false`；
- `result_transfer_authorized: true`；
- transfer method：尚未选择；
- next/larger task authorized：`false`；
- 服务器不得 push remote `main`。

首轮 package 还缺少完成诊断所需的 `trace_marker_inventory.server_local.tsv`、raw trace 精确路径、
parse error/cap 字段、按 PID/rank 的 observer/marker 事件计数，以及终态
`candidate_manifest.server_local.json`。本轮首先补这些证据，不允许把 0 marker 直接写成完整阴性结论。

## 2. 科学合同与声明边界保持不变

若执行新的 S1，必须复用首轮固定合同：

| 项目 | 固定值 |
| --- | --- |
| model | `DeepSeek-V4-Flash-w8a8-mtp` |
| tensor/expert parallel | TP8 / EP |
| max model len / batch tokens / seqs | 12288 / 12288 / 9 |
| chunked prefill / prefix cache | on / off |
| resident workload | 8 请求，各 256 prompt + 128 output |
| injected workload | 12281 prompt + 4 output |
| request retry | 0 |
| profiler window | warmup 后，只包含 measured staged-arrival trial |
| S1 policy | `admission_on_t4096` |
| selected pressure step count | 1 |

marker payload 仍只允许
`lifecycle_id/policy_id/timing_context_id/step_index/worker_rank`，不得包含 prompt、生成文本、token ID、
request ID 或其他请求内容。marker→host 只接受结构化 worker range 包含；host→runtime 与
runtime→actual-kernel 只接受 profiler flow/correlation 共同标识。`Free/Computing/Communication/`
`Communication(Not Overlapped)/Notify_Wait` 继续是 derived analysis timeline，不得满足 actual-kernel edge。

本轮只判断 marker 产生、worker 传播、trace 发现与 parser 覆盖是否真实闭合。时间重叠不是 dependency
proof；自动 grade 不得覆盖结构化事实。即使一次 S1 的三段链 8/8 闭合，也只能说明 S1 canary 正向，
不能设置 `causal_bottleneck_resolved=true`，不能选择优化 target，且必须停止等待开发机复核。

## 3. 同步、独立 worktree 与只读源结果保护

immutable Inbox prompt 会设置 `AK_SERVER_TASK_COMMIT`。先确认它仍等于实时 `origin/main`，再创建新的
detached worktree。不得修改共享 checkout、已安装 package 或首轮 source result root。

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
FOLLOWUP_TASK_ID=p6_3c_r3e_f2_d1_marker_path_diagnosis_and_bounded_s1_retry_2026_0820
AK_SERVER_TASK_COMMIT=${AK_SERVER_TASK_COMMIT:?set from immutable Inbox prompt}
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3e_f2_d1_2026_0820
SOURCE_RESULT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_2026_0820_attempt_01/p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820

git -C "${SHARED_REPO}" fetch origin main
test "$(git -C "${SHARED_REPO}" rev-parse origin/main)" = "${AK_SERVER_TASK_COMMIT}"
git -C "${SHARED_REPO}" cat-file -e "${AK_SERVER_TASK_COMMIT}^{commit}"
test ! -e "${WORKTREE}"
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" "${AK_SERVER_TASK_COMMIT}"
cd "${WORKTREE}"
test "$(git rev-parse HEAD)" = "${AK_SERVER_TASK_COMMIT}"
test "$(git rev-list --left-right --count HEAD...origin/main)" = $'0\t0'
test -z "$(git status --porcelain --untracked-files=no)"
test -d "${SOURCE_RESULT_ROOT}"
```

若 worktree 已存在，不要删除，核对归属后使用 `..._attempt_02`。若 source result root 不存在，只可
在 `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/` 下按 source task ID 只读查找；报告最终
canonical path、目录 mtime 与首层文件清单。不得创建一个空目录来满足路径检查，也不得覆盖首轮文件。

进入 worktree 后完整阅读：

```text
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
通信模块/docs/developer-to-server.P6.md
tools/inference_contracts/p6_3c_r3e_f2_dependency_marker.py
tools/inference_contracts/analyze_p6_3c_r3e_f2_dependency_markers.py
tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_experiment.sh
tools/inference_contracts/run_deepseek_p6_3c_r3e_f2_server_task.sh
```

## 4. D0：零 NPU 原位诊断，keep-alive 保持运行

D0 不启动 vLLM、不停止 keep-alive、不写首轮结果目录。所有派生诊断写入新的：

```bash
DIAG_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_d1_2026_0820_attempt_01
test ! -e "${DIAG_ROOT}"
mkdir -p "${DIAG_ROOT}"
```

依次完成以下检查：

1. 记录 source result root 的文件/目录 inventory、bytes、mtime；核对 `f2_s1_01` lifecycle、
   `scheduler_trace`、`torch_profiler`、`torch_profiler_output_files.txt`、stage analysis、server log、
   cleanup 与 package 实际存在位置。
2. 读取首轮已经生成的
   `stage_analysis/s1/trace_marker_inventory.server_local.tsv`；若不存在，在 `DIAG_ROOT` 中以发布版
   analyzer 对首轮 raw trace 做只读重跑。必须记录每个 trace 的 rank、path、bytes、两遍 event count、
   parse complete、event-limit reached 与精确 parse error。analyzer exit `2` 不能被简化为“无 marker”。
3. 对所有 `scheduler_trace/trace.*.jsonl` 按 `event + pid + worker_rank + lifecycle_id` 聚合以下事件：
   `observer_installed`、`dependency_marker_scheduled`、`dependency_marker_worker_enter`、
   `dependency_marker_worker_exit`。同时报告每个 PID 的首末时间、环境中的 trace root 与 rank 字段缺失。
4. 核对 `dependency_marker_scheduled` 的 `timing_context_id/step_index` 是否与 step 31 一致；检查私有
   context 是否确实进入 MultiprocExecutor RPC 序列化后的 worker 对象。不能用 S0 的单进程 pickle
   probe 代替真实 worker 进程证据。
5. 核对真实 vLLM worker 启动方式、`PYTHONPATH`/overlay/sitecustomize bootstrap、
   `WorkerWrapperBase.execute_model` 实际 callable identity 与每个 worker PID 的 patch-installed flag。
   父进程中 `worker_wrapper_installed=true` 不足以证明 8 个 worker 子进程已安装 wrapper。
6. 直接扫描每份 raw profiler trace 中 `AK_P6_R3E_F2|` 名称出现次数，并与 analyzer 的 marker count
   交叉核对。区分：trace 根发现错误、rank 识别错误、JSON parser 不完整、profiler 未导出
   `record_function`、worker wrapper 未安装、context RPC 丢失、或 marker selection 未触发。
7. 核对首轮 task-local `sitecustomize.py` adaptation 的实际文件内容/最小 diff/SHA。保留已报告
   SHA `ab8cac5e9f7c81d40adddc8f0e78b611f94040c5354011fa68cca8f9f67bf091`，但不能仅凭描述宣称可复现。
8. 生成 `d0_root_cause_review.json`。必须逐一评价以下互斥或可并存假设，并列出直接证据：
   `worker_wrapper_not_installed_in_real_workers`、`scheduler_context_lost_before_worker_rpc`、
   `marker_emitted_but_profiler_trace_discovery_incomplete`、`marker_range_not_exported_by_ascend_profiler`、
   `trace_parser_failed_before_marker_scan`、`other_precise_cause`。

D0 至少输出：

```text
d0_result_summary.md
source_result_inventory.tsv
trace_marker_inventory.server_local.tsv
marker_event_pid_rank_summary.tsv
worker_bootstrap_review.json
trace_discovery_and_parse_review.json
d0_root_cause_review.json
adaptive_execution_review.json
candidate_manifest.server_local.json
```

若 D0 已能完整证明 raw trace 8/8 解析、marker 真实存在或一个明确不可修复的 profiler schema 边界，
直接返回该证据，不消耗 NPU。若根因仍不明确，或同一阻塞已重复且新重试不能增加信息，也必须停止。

## 5. D1：task-local 修复门与一次最小 S1 重试

只有同时满足以下条件才允许新 S1：

- D0 定位到可复现的 task-local 实现/解析/bootstrap 问题；
- 修复不改变研究问题、measured 请求、policy、参数、marker payload、profiler window、event-domain/
  link 定义或 metric；
- 修复有 before/after diff、SHA、zero-NPU smoke 和明确 scientific-impact statement；
- 0–7 卡除 low-priority keep-alive 外无其他作业；端口 7000 无占用；没有其他 P6.3C NPU 会话；
- 预计一次新的 S1 lifecycle 能区分至少两个剩余假设。

允许修复 task-local overlay、worker bootstrap、trace path/rank discovery、parser、bounded diagnostics、
health/warmup/timeout/cleanup。不得修改安装包或共享 checkout。若改变科学合同，设置
`scientific_contract_changed=true`，创建新 variant/task ID，报告精确 delta，并停止等待批准；本轮不得
执行该新变体。

重试使用全新、不覆盖的 attempt root：

```bash
RETRY_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_2026_0820_attempt_02
RETRY_RESULT_DIR=${RETRY_ROOT}/p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820
test ! -e "${RETRY_RESULT_DIR}"
mkdir -p "${RETRY_ROOT}"
```

正式重试前先运行原交接的 S0 和一个额外的真实子进程 bootstrap smoke，证明 scheduler/engine PID 与
8 个 worker 预期启动路径都会加载相同 task-local marker module。S0/诊断阶段不需 NPU，keep-alive
必须保持运行。

S1 是 TP8；确认资源门后只停止 0–7：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the low-priority keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

stop/restore 必须由 trap 覆盖成功、失败、中断与提前退出。只运行一个
`f2_s1_01=admission_on_t4096` lifecycle 和一个 selected mixed pressure step。重试中应保留 per-PID
observer/marker counters，使“context 未到 worker”和“marker 到 worker但未进 profiler”可区分。

无论 S1 阴性或正向，本轮都不运行 S2。完成 analyzer、资源恢复、finalize/package 后停止等待开发机
复核。不得运行 R3D 17 lifecycle、五档 budget sweep、新性能比较或更大 profiler sweep。

## 6. 自适应记录与资源恢复

每个 adaptation/attempt 写入 `adaptive_execution_review.json`：原始错误、修改原因、patch path、
before/after SHA、最小 diff、命令、退出码、首个有效故障、scientific impact、是否改变科学合同、
采用/拒绝该尝试的原因。不得用后一次结果覆盖前一次历史。

D0 必须报告 `npu_used=false/keep_alive_action=left_running`。若执行 D1/S1，必须报告 stopped/restored
card IDs、keep-alive marker count/card IDs、`keep_alive_restored_exact`、端口 7000 listener、vLLM
residual process、worktree tracked cleanliness，以及 shared/installed/source result 是否被修改。恢复失败时
先恢复资源，不得开始新 attempt 或传输。

## 7. 有界结果包与传输选择门

raw profiler trace、server log、完整 rank detail、task-local patch 与实验目录留在服务器。候选小包必须
小于 70KB，优先包含 D0 的九个文件；若执行 D1/S1，再加入：

```text
result_summary.md
environment_and_hashes.json
marker_propagation_summary.json
step_rank_marker_coverage.tsv
dependency_edge_summary.tsv
cross_domain_link_chains.tsv
resource_recovery_summary.json
grading_inputs.json
scientific_outcome.json
```

`candidate_manifest.server_local.json` 必须在所有 adaptive review 写入后最后生成；manifest 自身不列入
候选集合。先在服务器会话中一次报告：result summary 精确路径；完整候选清单；每文件 bytes、SHA-256、
sensitivity；总 bytes 与 manifest SHA；可用 `email/upload-api/server-local`；一个建议方式与原因。

当前 `transfer_method_selected=false`。`result_transfer_authorized=true` 只表示候选包可被选择，不选择方式、
不扩大范围。没有用户对这一次完整 scope 的明确选择前，不得 email 或 upload-api 传输，不发送
status-only 邮件，不沿用首轮传输选择。任何 `401/409/413`、代理/重定向、timeout、service 或 hash
失败后停止并重新取得用户选择。

## 8. 服务器报告模板

```text
P6_3C_R3E_F2_D1_SERVER_REPORT_BEGIN
followup_task_id / source_task_id / attempt_id / task_status:
repo_head / origin_main / ahead_behind / tracked_clean / shared_mutated:
source_result_root / source_result_unchanged:

D0_npu_used: false
D0_keep_alive_action: left_running
raw_trace_paths_and_rank_count:
trace_inventory_complete / first_second_pass_parse_errors / event_caps:
event_counts_by_pid_rank: observer_installed / marker_scheduled / worker_enter / worker_exit
scheduler_context_reached_rpc / worker_wrapper_loaded_by_pid:
raw_marker_name_counts_by_rank / analyzer_marker_counts_by_rank:
root_cause / hypotheses_rejected / remaining_uncertainty:

D1_fix_applied / patch_paths / before_after_sha / minimal_diff:
scientific_impact / scientific_contract_changed:
S1_retry_executed / lifecycle / selected_pressure_step:
S1_trace_rank_coverage / marker_exactly_once_rank_coverage:
S1_marker_to_host / host_to_runtime / runtime_to_actual_kernel coverage:
S1_dependency_linkage_gap:
S2_executed: false
causal_bottleneck_resolved: false
optimization_target_selected: false
performance_gain_claimed: false

stopped_card_ids / restored_card_ids:
keep_alive_marker_count_and_card_ids / keep_alive_restored_exact:
port_7000_listener_count / vllm_residual_process_count / cleanup_complete:

server_local_raw_trace_paths / result_summary_path:
candidate_files_with_bytes_sha_sensitivity:
candidate_total_bytes / candidate_manifest_sha256:
available_transfer_methods: email, upload-api, server-local
recommended_transfer_method_and_reason:
transfer_method_selected: false
result_transfer_authorized: true
next_larger_task_authorized: false
P6_3C_R3E_F2_D1_SERVER_REPORT_END
```

最终结论必须区分：首轮返回包证据不完整、D0 是否补齐了 trace/parser/worker 路径事实、以及 D1 新 S1
是否执行。不能把 `0/8 marker` 与 `trace_parse_complete=false` 合并成完整的 profiler 能力阴性结论。
