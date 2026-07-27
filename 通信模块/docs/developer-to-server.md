# Developer to Server

## 当前唯一任务：R16 — 用 R15 原始轨迹裁定 H2D 异步完成语义

```text
task_id: p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727
execution_mode: authorized_offline_r15_raw_trace_completion_adjudication
server_sync_review_authorized: true
offline_parent_gate_required: true
parent_task_id: p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725
parent_source_sha_gate_required: true
parent_raw_trace_required: true
parent_source_mutation_authorized: false
result_directory_creation_authorized: true
npu_execution_authorized: false
keep_alive_action: leave_running
keep_alive_stop_authorized: false
vllm_server_start_authorized: false
model_requests_authorized: false
model_request_count_exact: 0
formal_model_lifecycle_count_exact: 0
server_side_code_edit_authorized: false
runtime_or_dependency_mutation_authorized: false
profiler_authorized: false
context_change_authorized: false
capacity_change_authorized: false
pressure_search_or_sweep_authorized: false
h2d_poll_live_pending_is_diagnostic_only: true
async_completion_same_worker_sets_required: true
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
bounded_transfer_max_bytes: 71680
next_task_authorized: false
k2_authorized: false
p8_3_i1_authorized: false
```

本文件已清空上一轮内容，只描述当前 R16。服务器助手不要设计实验、不要补代码、
不要启动 NPU/vLLM、不要发送请求，也不要创建 run02。

## 零、给服务器助手的“照做即可”执行摘要

服务器端不需要查外部资料，也不需要理解或改写 observer。开发机已经把 R16 所需
判断写进唯一入口；服务器助手只负责：

1. fast-forward 同步远程 `main`，确认 HEAD=origin/main 且 tracked-clean；
2. 运行本文件第四节的开发检查和自动 preflight；
3. preflight 通过后，只运行第五节唯一正式命令一次；
4. 从终端 `R16_SERVER_REPORT_BEGIN` 到 `R16_SERVER_REPORT_END` 收集回报，并补上
   focused test/compile/Bash/audit-only 的 exit code；
5. 报完整 7-file 清单后暂停，等待用户选择传输方式。

禁止服务器助手自行：

- 写 Python/Bash/YAML 修补结果；
- 人工修改 grade、manifest、worker count 或 SHA；
- 因为看到 R15 是 RED 就启动 NPU 补跑；
- 因为看到 R16 是 GREEN 就进入 R17/K2/P8.3-I1；
- 删除已存在的 R16 目录后重跑，或创建 run02；
- 停止 keep-alive。本轮不占卡。

入口会自动执行四层硬门：

```text
repository input SHA gate
→ R15 six-file SHA + fact gate
→ raw trace digest-before-read / digest-after-read immutability gate
→ complete 7-file result-package bytes/SHA/sensitivity/control self-verification
```

任何一层失败都应原样回报错误并停止，不由服务器助手临场“修到通过”。

## 一、为什么本轮是实质推进，而不是再做一次形式评分

R15 已经把 accepted-capacity 主链闭合到：

```text
16K logical hit
→ physical FA CPU-only window
→ delayed_external_prefill
→ update_state_after_alloc
→ task-local compress-aware repair applied
→ _reqs_to_load
→ load scheduled
→ H2D 8 workers / 1076510720 bytes
→ restore request completed
```

R15 的真实运行证据同时是：

```text
h2d_worker_count = 8
h2d_completed_worker_count = 8
h2d_enqueued_worker_count = 8
h2d_copy_blocks_entered_worker_count = 8
h2d_copy_blocks_returned_worker_count = 8
h2d_restore_complete = true
async_copy_failure_event_count = 0
h2d_poll_event_visible_worker_count = 7
h2d_async_copy_pipeline_exact = false
```

旧判据把 `h2d_poll_event_visible_worker_count` 当作完成硬门。这个字段只统计某次
`transfer_poll_entered` 时同时满足：

```text
pending_event_count > 0
copy_thread_alive = true
```

但 observer 的真实事件顺序是：

```text
transfer_poll_entered
→ 原 _poll_stream_events 返回
→ transfer_poll_returned
→ high-water mark 前进时 transfer_completed
```

所以 `transfer_completed` 是 poll 已返回并推进完成状态之后的证据；某 worker 在后续
poll 入口处看不到“线程仍活着且队列仍 pending”，不能反推它没有完成。R16 用 R15
服务器本地保留的 raw trace 把 poll entered / returned / completed / live-pending 四类
证据分开，并按同一 worker 集合离线裁定。只有 raw trace 真的闭合全部完成边时才给
机制 green；若少一个真实 completion、poll return 或出现 failure，仍保持 RED。

本轮不改 accepted `128 CPU blocks/rank`、16K logical restore、fixed `36800` 的任何
结论，也不重新花费一次 NPU lifecycle。

## 二、代码已经写好；服务器只同步、校验、执行

唯一入口：

```text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r16_server_task.sh
```

内部分析器：

```text
tools/inference_contracts/p8_2_k1a_r5_f1_r16_async_completion_adjudication.py
```

分析器会：

1. 从 audit 合同精确校验 6 个仓库执行输入 SHA-256，防止服务器代码漂移。
2. 精确校验 R15 六个父文件 SHA-256 与父事实。
3. 在读取前先计算
   `R15_ROOT/runtime/offload_trace/h2d-residency.*.jsonl` tree digest。
4. 只读 raw trace，再次计算 tree digest，证明分析期间父证据未变。
5. 重算 D2H/H2D submitted、enqueued、copy entered、copy returned、poll entered、
   poll returned、live-pending 与 completed worker 集合。
6. 用不带 raw PID 的 direction-local worker ordinal 产出紧凑 rollup。
7. 将 live-pending 保留为诊断覆盖，不再替代完成证据。
8. 生成严格不超过 `71680 bytes` 的 6 payload + 1 manifest。
9. 逐文件复核结果 bytes、SHA-256、sensitivity、完整文件集合与全部 manifest
   control；任何不一致或超限都会直接失败。
10. 在终端输出带 begin/end 标记的回报素材，服务器助手不必手工拼字段。

## 三、R15 父证据与精确 SHA 门

默认父目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725_run01
```

必须匹配：

```text
29a240d1eb5cce44eb63e94c297cbf4051123e40046e999259fb4343ac14e7c5  grading_summary.json
1107daccdaad77863d655dc2ae6c07b359328275151e498e36cc35ca2e4b709a  h2d_trigger_summary.json
d8bc7fe07e24e0878714969364c530201a2ac4370d33ff85c3dd70e7966a37a2  transfer_trace_summary.json
5e4795b6ddbebee7b8fb213ae9a2702c937333bf4ee0809c30a69e9cb141b4fe  resource_recovery_summary.json
2e22da2ab13713309ac75219e525b8e06ed02f3f1963b8feef203fa25827f93d  cleanup_status.txt
a9defd7d0167e1048a652dee68b788ffbce6cc201f082b89872f6279e4f9b40c  candidate_manifest.server_local.json
```

父事实硬门：

```text
server_grade = red_p8_2_k1a_r5_f1_r15_h2d_evidence_incomplete
experimental_terminal = restore_request_completed
operational_grade = operational_recovery_clean
restore_step_lineage_primary_class = delayed_external_then_reqs_to_load
restore_h2d_path_class = via_reqs_to_load
restore_pairing_repair_applied = true
restore_any_entered_reqs_to_load = true
h2d_trigger_summary.h2d_restore_mechanism_candidate = true
h2d_trigger_summary.target_cpu_only_residency_observed = true
transfer_trace_summary.h2d_restore_complete = true
transfer_trace_summary.h2d_completed_worker_count = 8
transfer_trace_summary.h2d_poll_event_visible_worker_count = 7
transfer_trace_summary.h2d_async_copy_pipeline_exact = false
transfer_trace_summary.async_copy_failure_event_count = 0
```

若父目录不在默认位置，只允许在命令前导出实际 R15 run01 根：

```bash
export P8_2_K1A_F1_R15_ROOT=/实际/R15/run01/绝对路径
```

不要复制、改写或重命名 raw trace 来迎合分析器。父 SHA 或 raw trace 缺失时停止并回报，
不得启动 NPU 补跑。

## 四、同步与零 NPU 预检

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"

PYTHON_BIN=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python

"${PYTHON_BIN}" -m pytest -q \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r16_async_completion_semantics.py

"${PYTHON_BIN}" -m py_compile \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/p8_2_k1a_r5_f1_r16_async_completion_adjudication.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r16_async_completion_semantics.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r16_server_task.sh

P8_2_K1A_F1_R16_AUDIT_ONLY=1 \
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r16_server_task.sh \
  /tmp/p8_2_k1a_r5_f1_r16_audit_unused

P8_2_K1A_F1_R16_PREFLIGHT_ONLY=1 \
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r16_server_task.sh \
  "/tmp/p8_2_k1a_r5_f1_r16_preflight_unused_$$"
```

audit-only 必须明确输出：

```text
npu_execution_authorized=false
vllm_server_start_authorized=false
model_requests_authorized=false
keep_alive_action=leave_running
h2d_poll_live_pending_is_diagnostic_only=true
async_completion_same_worker_sets_required=true
repository_input_sha_gate_required=true
result_package_self_verification_required=true
copy_ready_server_report_emitted=true
result_transfer_authorized=true
transfer_method_selected=false
next_task_authorized=false
```

自动 preflight 还必须输出：

```text
preflight_status=pass
repository_input_hashes_exact=true
parent_source_hashes_exact=true
parent_contract_exact=true
raw_trace_unchanged_during_preflight=true
npu_started=false
vllm_started=false
model_requests_sent=0
keep_alive_action=leave_running
```

任一开发检查或自动 preflight 失败就停止；不要临时改服务器代码。

## 五、唯一正式命令

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727_run01
test ! -e "${RESULT_DIR}"

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r16_server_task.sh \
  "${RESULT_DIR}"
```

不要预先 `mkdir "${RESULT_DIR}"`；分析器会创建。不要手工拆内部步骤，不要运行第二次。

这条命令内部已经固定顺序：

```text
确认 HEAD=origin/main 与 tracked-clean
→ 自动 preflight
→ 只读分析
→ 结果包逐文件自校验
→ 输出 R16_SERVER_REPORT_BEGIN ... R16_SERVER_REPORT_END
```

正式命令退出码为 0 表示“离线裁定流程和结果包完成”，不等于 grade 必然 GREEN。
若 grade 是 RED 但包自校验通过，任务同样已经完成，应回报 RED 后暂停，不能补跑。

## 六、精确判定逻辑

### GREEN：R15 的机制证据闭合

只有以下全部成立：

```text
parent_contract_exact = true
d2h_store_complete = true
h2d_restore_complete = true
d2h_async_copy_pipeline_exact = true
h2d_async_copy_pipeline_exact = true
h2d_poll_returned_completion_exact = true
h2d_worker_count = 8
h2d_completed_worker_count = 8
async_copy_failure_event_count = 0
```

则：

```text
server_grade = green_p8_2_k1a_r5_f1_r16_restore_h2d_mechanism_closed
h2d_restore_mechanism_accepted = true
```

若同时：

```text
h2d_poll_live_pending_coverage_exact = false
```

应报告：

```text
r15_false_negative_gate_observed = true
```

含义仅为：R15 同一 lifecycle 的 raw trace 已闭合 CPU offload → logical hit →
`_reqs_to_load` → H2D restore 机制证据，7/8 live-pending 是瞬时观察覆盖，不是 H2D
少一个 worker。

### RED：真实完成边仍缺失

任一 required same-worker set 不等、少 `transfer_completed`、已完成 worker 没有
`transfer_poll_returned`、copy thread 未启动，或出现 launch/poll/thread/copy failure：

```text
server_grade = red_p8_2_k1a_r5_f1_r16_async_completion_trace_incomplete
h2d_restore_mechanism_accepted = false
```

回报缺失的具体 count/worker ordinal 后停止。不要把 RED 改写成需要立即 NPU 重跑；
下一任务仍未授权。

### 无论 GREEN/RED 都禁止的外推

- 不宣称性能收益、带宽峰值或延迟改善。
- 不宣称 compress-aware pairing 是所有模型/版本的普遍唯一根因。
- 不改变 R15 operational recovery 事实。
- 不进入 K2、P8.3-I1、P8.4、P8.5 或 P9。
- `next_task_authorized=false`。

## 七、keep-alive 规则

本轮零 NPU，**必须让 keep-alive 全程运行，不执行 stop/restart**。服务器回报：

```text
stopped_card_ids = []
restored_card_ids = []
keep_alive_action = leave_running
```

项目长期规则仍如下，供以后真正需要卡的任务使用；这两条命令本轮不要执行：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

以后需要卡时只处理实际所需 card IDs，并在成功、失败、中断或提前退出后恢复完全相同
卡集；命令末尾数字是卡号。停 keep-alive 是常规操作，不要把它当成异常风险；关键是
任务后同卡恢复。NPU 任务必须回报实际停卡卡号、实际恢复卡号与恢复状态；本轮则按空集
回报。

## 八、严格紧凑的有界结果包

R15 的 transferred server-local evidence set 为 `110062 bytes`，超过 70KB。本轮不能
再次把大 timeline / logical rows / target rows 放进候选包。raw trace 和全部大证据继续
留服务器，只在 provenance 中报告文件数、总字节与 tree digest。

R16 完整候选固定为：

1. `result_summary.md`
2. `task_grade.txt`
3. `grading_summary.json`
4. `async_completion_adjudication_summary.json`
5. `worker_completion_rollup.json`
6. `source_evidence_provenance.json`
7. `candidate_manifest.server_local.json`

manifest 必须同时满足：

```text
payload_file_count = 6
transfer_file_count = 7
transfer_total_bytes <= 71680
bounded_transfer_package_exact = true
raw_trace_content_retained = false
raw process/request/token/hash values retained = false
generated_content_retained = false
result_transfer_authorized = true
transfer_method_selected = false
automatic_transfer_allowed = false
```

入口在生成后会再次执行 `verify-output`；终端必须看到：

```text
package_verification_status=pass
payload_file_count=6
manifest_file_count=1
transfer_file_count=7
bounded_transfer_package_exact=true
```

## 九、完成后一次性回报

请一次性回报：

1. `HEAD`、`origin/main`、ahead/behind、tracked-clean。
2. R15 六个 parent 文件逐项 bytes/SHA-256/MATCH。
3. raw trace file count、total bytes、before/after tree digest、unchanged。
4. focused pytest、py_compile、Bash syntax、audit-only 结果。
5. `npu_started=false`、`vllm_started=false`、`model_requests_sent=0`、
   `stopped_card_ids=[]`、`restored_card_ids=[]`、keep-alive 留运行。
6. D2H/H2D submitted/enqueued/copy-entered/copy-returned/poll-entered/
   poll-returned/live-pending/completed worker counts。
7. 16 个 direction-local worker rollup 的完成分类，特别指出
   `completion_without_live_pending_worker_count`，不回传 raw PID。
8. `parent_contract_exact`、`async_completion_evidence_exact`、
   `h2d_poll_live_pending_coverage_exact`、
   `r15_false_negative_gate_observed`、最终 grade。
9. claim boundary 与所有未授权项。
10. `result_summary.md` 绝对路径和完整 7-file 清单：
    filename / bytes / full SHA-256 / sensitivity，以及 payload/manifest/transfer 合计。
11. 可用方式 `email / upload-api / server-local`，推荐一种并说明原因；然后暂停等待
    用户明确选择，不能自动传输。

优先使用正式命令打印的 `R16_SERVER_REPORT_BEGIN ... R16_SERVER_REPORT_END` 作为
回报依据。它已经包含 Git 状态、零 NPU/零请求/keep-alive 空集、详细结果摘要、
grading、adjudication、16-worker rollup、source provenance 与完整 manifest。
不要省略其中不符合预期的字段，也不要只回一句 grade。

`result_transfer_authorized: true` 只表示完整有界包具备候选资格，不选择渠道、不扩大
范围。不要先发 status-only 邮件，不要在失败后自动切换渠道。

## 十、失败分支对照表

| 看到的失败 | 含义 | 唯一允许动作 |
|---|---|---|
| HEAD != origin/main | 未同步到发布版本 | 停止；只允许重新 fetch + ff-only，再核对 |
| tracked worktree 非 clean | 服务器有 tracked 修改 | 原样列出；不得 reset/restore/stash/覆盖 |
| `repository SHA mismatch` | 执行输入不是开发机发布版本 | 停止；不得编辑文件凑 SHA |
| R15 默认目录不存在 | parent 路径不同或证据缺失 | 只可用实际 run01 根设置 `P8_2_K1A_F1_R15_ROOT` |
| `R15 parent SHA mismatch` | 父有界证据不是冻结 run01 | 停止并回报 expected/actual；不得复制改名凑门 |
| `no retained R15 trace files` | 服务器原始轨迹缺失 | 停止；不得启动 NPU 补跑 |
| raw trace before/after digest 不同 | 分析期间父证据被改动 | 停止，保留现场，不重跑 |
| RESULT_DIR 已存在 | run01 已执行或目录冲突 | 不删除、不覆盖、不建 run02；检查并回报现有目录 |
| `package ... mismatch/exceeds` | 候选包不完整或超限 | 不传输，回报错误与服务器本地路径 |
| formal grade RED | 真实 completion 边仍不闭合 | 回报缺失 worker/count 后完成任务并暂停 |
| formal grade GREEN | R15 同 lifecycle 机制证据闭合 | 只回报本轮边界；不得扩展到性能/唯一根因/下一任务 |

如进程因 SSH/终端中断但 `RESULT_DIR` 已出现，也视为“可能已经执行”，不要重发正式
命令。先只读检查目录和 manifest，再把现场回报给开发机。

## 十一、当前仓库合同输入 SHA-256

服务器预检要逐项匹配下列文件；该清单由开发机在最终修改后生成：

```text
0c44e312fc386d172adef92d40256630b211db59b97908fcae958bb47d461cee  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r16_async_completion_semantics_audit.yaml
6c81398e9adeeb05efaf6397a588115e55463942c2f424e436890250b2b5fcd9  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r16_async_completion_semantics.yaml
43801af40010490ae51a7545dcff762dee831f3af937b23192514a95523add85  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
7a2bd0789d932249b77520d6f4927463c83481b937e226d73bc7a793bb4e323b  tools/inference_contracts/p8_2_k1a_r5_f1_r16_async_completion_adjudication.py
5432a21bd055c1c22f077da5fe1137393e17bc58181f807dae8581028b8d13dc  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r16_async_completion_semantics.sh
7af6136f38aad8f24cd864a7aeba652ed893f49bcc56fe78b28bbd96921bc4ba  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r16_server_task.sh
df09b22723ea08a70dcfa7dc7c70bf9855597279ef94901d450914a9931bf4ef  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r16_async_completion_semantics.py
```

## 完成后停止

回报 R16 run01 后暂停。不要自动开 R17、run02、NPU 重跑、K2 或 P8.3-I1。
