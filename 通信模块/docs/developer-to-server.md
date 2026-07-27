# Developer to Server

## 当前唯一任务：R17 — 完整重放 R15 双轨迹源并裁定 H2D restore 机制

```text
task_id: p8_2_k1a_r5_f1_r17_full_trace_source_replay_2026_0727
execution_mode: authorized_offline_r15_complete_trace_source_replay
server_sync_review_authorized: true
offline_parent_gate_required: true
r15_parent_task_id: p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725
r16_parent_task_id: p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727
parent_source_sha_gate_required: true
r15_parent_raw_trace_required: true
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
canonical_trace_reader: combined_json_else_all_jsonl
dual_trace_file_family_coverage_required: true
r15_replay_field_parity_required: true
coverage_mismatch_is_mechanism_red: false
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

本文件已经清空 R16 的旧执行内容，只描述当前 R17。R15、R16 都已执行完毕，不得
重跑、删目录或创建 run02。本轮是零 NPU 的服务器本地只读重放；服务器助手不要设计
实验、不要补代码、不要启动 vLLM/NPU、不要发送模型请求。

## 零、服务器助手只需照做的摘要

服务器助手不需要查外部资料，也不需要理解或修改 observer。开发机已经把所有选择、
对账、裁决、打包和自校验逻辑写入唯一入口。严格按以下顺序：

1. fast-forward 同步远程 `main`，确认 `HEAD=origin/main`、ahead/behind=`0 0`、
   tracked-clean；
2. 确认 R15 raw trace 与 R15/R16 bounded parent 仍在默认服务器目录；
3. 运行第四节的 focused test、compile、Bash、audit-only 和自动 preflight；
4. preflight 无结构性错误后，只运行第五节唯一正式命令一次；
5. 从终端 `R17_SERVER_REPORT_BEGIN` 到 `R17_SERVER_REPORT_END` 原样收集完整回报；
6. 报告固定 8-file 有界清单后暂停，等待用户选择
   `email / upload-api / server-local`；不得自动传输。

服务器助手禁止自行：

- 修改 Python、Bash、YAML、audit、parent JSON、raw trace 或 grade；
- 为了让结果变 GREEN 而复制/合并/改名轨迹文件；
- 只读 `h2d-residency.*.jsonl`，或只读 `trace.*.jsonl`；
- 同时读取 `combined.json` 和 JSONL，造成重复计数；
- 因 R16 formal RED 而启动 NPU 重跑 R15/R16；
- 删除已存在的 R17 run01，或创建 R17 run02；
- 自动进入 K2、P8.3-I1、P8.4、P8.5 或 P9；
- 停止 keep-alive。本轮不占卡。

唯一入口自动执行：

```text
HEAD/origin/main/tracked-clean gate
→ repository input SHA gate
→ R15 six-file SHA + fact gate
→ R16 five-file SHA + fact gate
→ canonical raw-trace discovery
→ raw-trace before/read/after immutability gate
→ R15 1369-event and transfer-field replay parity gate
→ async completion adjudication only when coverage exact
→ complete 8-file result-package bytes/SHA/sensitivity/control verification
→ copy-ready report emission
```

结构性门失败时原样回报并停止，不临场“修到通过”。轨迹覆盖不一致不是结构性异常：
分析器会正常生成正式 `BLOCKED` 包，明确说明它不是机制 RED。

## 一、这轮为什么是项目机制推进，而不是换颜色

### 1. R15 已经闭合到真实 H2D

R15 在 accepted-capacity 单 lifecycle 内已经观察到：

```text
accepted CPU capacity = 128 blocks/rank
shared prefix = 32768 tokens
restore logical hit = 16384 tokens / 128 logical hash blocks
pressure context = 36800
physical target keys = 40
physical FA CPU-only window = true
logical + physical restore window = true
delayed_external_prefill = observed
compress-aware pairing repair = applied
entered _reqs_to_load = true
load scheduled = true
D2H workers/completed = 8/8
H2D workers/completed = 8/8
H2D bytes = 1076510720
restore request = completed
async failure events = 0
```

所以以下机制链已有同一 lifecycle 的父证据：

```text
physical CPU-only target
→ logical CPU hit
→ allocate_slots delayed_external_prefill
→ update_state_after_alloc
→ compress-aware GPU/CPU pairing repair
→ _reqs_to_load
→ load schedule
→ H2D copy
→ restore completion
```

R15 旧 grader 仍给 RED，是因为把 `transfer_poll_entered` 时
`pending_event_count>0 && copy_thread_alive=true` 的瞬时覆盖 7/8 当作 H2D 完成硬门。
这个字段是时点诊断，不等价于完成。

### 2. R16 服务器没有执行错；错误在开发机发布的 selector

R16 服务器正确同步 `main@07d535a35594e9a37b9a5bea5a5dc0bbd0707da1`，所有父
SHA、repo SHA、package SHA/bytes、tracked-clean、零 NPU 和 keep-alive 规则都通过。
但 R16 开发机代码中的 `_find_trace_paths` 只做：

```text
h2d-residency.*.jsonl
```

真实 observer 写入位置是：

```text
async copy events:
  runtime/offload_trace/trace.<pid>.jsonl

residency and keyspace events:
  runtime/offload_trace/h2d-residency.<pid>.jsonl
```

R16 因而只选中：

```text
10 files
4450889 bytes
319 events
```

并自然得到：

```text
D2H workers = 0
H2D workers = 0
D2H/H2D bytes = 0
```

而 R15 finalizer 的 canonical reader 是：

```text
if runtime/offload_trace/combined.json exists:
    read combined.json only
else:
    read every runtime/offload_trace/*.jsonl
```

它在同一父目录重放了：

```text
trace_event_count = 1369
D2H workers/completed = 8/8
H2D workers/completed = 8/8
H2D bytes = 1076510720
```

因此 R16 formal grade
`red_p8_2_k1a_r5_f1_r16_async_completion_trace_incomplete` 必须历史保留，但其科学/
机制状态是 `invalid/inconclusive_source_selection`，不是“已证明异步完成边缺失”。
R16 不否定 R15 accepted capacity、CPU-only window 或 H2D 8/8。

### 3. R17 修的是证据读取链，并先做覆盖奇偶校验

R17 不依赖服务器助手手选文件，直接复用 R15 canonical reader。它先要求：

```text
full replay trace_event_count = frozen R15 trace_event_count
all frozen R15 worker/count/bytes/lineage fields replay exact
required async and restore events all nonzero
all-jsonl mode selects both trace.* and h2d-residency.* families
```

只有覆盖完全一致，才允许判断 completion。若 coverage 不完整，正式结果只能是：

```text
blocked_p8_2_k1a_r5_f1_r17_source_trace_coverage_mismatch
mechanism_adjudication_performed = false
source_coverage_failure_is_mechanism_red = false
```

这防止采集/选择错误再次伪装成机制失败。

## 二、代码已完成，服务器不得补代码

唯一入口：

```text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_server_task.sh
```

内部正式 runner：

```text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_full_trace_source_replay.sh
```

内部分析器：

```text
tools/inference_contracts/p8_2_k1a_r5_f1_r17_full_trace_source_replay.py
```

审计与 workload：

```text
benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r17_full_trace_source_replay_audit.yaml
benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r17_full_trace_source_replay.yaml
```

focused contract test：

```text
tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r17_full_trace_source_replay.py
```

测试真实模拟两个独立文件族：

```text
h2d-residency.* = 319 residency events
trace.*         = 1050 async/restore events
full replay     = 1369 events
```

另有两个关键分支：

- 缺 `trace.*` 时必须 `BLOCKED`，不得机制 RED；
- `combined.json` 存在时只读 combined，不与两个 JSONL 重复读取。

## 三、冻结父证据与精确 SHA

### 3.1 R15 parent

默认目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725_run01
```

必须精确匹配：

```text
29a240d1eb5cce44eb63e94c297cbf4051123e40046e999259fb4343ac14e7c5  grading_summary.json
1107daccdaad77863d655dc2ae6c07b359328275151e498e36cc35ca2e4b709a  h2d_trigger_summary.json
d8bc7fe07e24e0878714969364c530201a2ac4370d33ff85c3dd70e7966a37a2  transfer_trace_summary.json
5e4795b6ddbebee7b8fb213ae9a2702c937333bf4ee0809c30a69e9cb141b4fe  resource_recovery_summary.json
2e22da2ab13713309ac75219e525b8e06ed02f3f1963b8feef203fa25827f93d  cleanup_status.txt
a9defd7d0167e1048a652dee68b788ffbce6cc201f082b89872f6279e4f9b40c  candidate_manifest.server_local.json
```

R15 事实门至少冻结：

```text
server_grade = red_p8_2_k1a_r5_f1_r15_h2d_evidence_incomplete
experimental_terminal = restore_request_completed
operational_grade = operational_recovery_clean
restore_step_lineage_primary_class = delayed_external_then_reqs_to_load
restore_h2d_path_class = via_reqs_to_load
restore_pairing_repair_applied = true
restore_any_entered_reqs_to_load = true
target_cpu_only_residency_observed = true
trace_event_count = 1369
D2H submitted/enqueued/copy-entered/copy-returned/completed = 8/8/8/8/8
H2D submitted/enqueued/copy-entered/copy-returned/completed = 8/8/8/8/8
D2H poll live-pending = 8
H2D poll live-pending = 7
D2H bytes = 4386781184
H2D bytes = 1076510720
async_copy_failure_event_count = 0
d2h_store_complete = true
h2d_restore_complete = true
```

### 3.2 R16 parent

默认目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727_run01
```

必须精确匹配：

```text
a7f6eddecad3659dd32b9ac0d2f9b79d84030c509aa07556540be074ca1da60c  grading_summary.json
a722f8577685fdccbecba0a83a94c40a0d1f3967862451cdd6ad19fcb4cc2825  async_completion_adjudication_summary.json
ca4055681dd5a2130bcea3702b9e362cb65af2dd29b034b16975f9955374b8db  source_evidence_provenance.json
50226a367352a3be929abd860f922ae25faf265f4b96dba01e1c6efdfd6bc4d2  task_grade.txt
44714051a99ab05939485489ac8ae6c0e44563556f9b13b4ddbd3e82eca687ff  candidate_manifest.server_local.json
```

R16 事实门冻结：

```text
formal grade = red_p8_2_k1a_r5_f1_r16_async_completion_trace_incomplete
parent_contract_exact = true
async_completion_evidence_exact = false
selected trace_event_count = 319
selected D2H/H2D worker count = 0/0
selected D2H/H2D bytes = 0/0
raw_trace file_count = 10
raw_trace total_bytes = 4450889
raw_trace tree_sha256 = e7629a9740ef6a66911c359d7f5944a496ffcd8cf3630e5faca8b91379f9c750
```

若父目录不在默认位置，只允许在命令前设置实际 run01 绝对根：

```bash
export P8_2_K1A_F1_R15_ROOT=/实际/R15/run01/绝对路径
export P8_2_K1A_F1_R16_ROOT=/实际/R16/run01/绝对路径
```

不允许复制、改写、合并、重命名或重新生成父证据。SHA 不匹配就停止。

## 四、同步、开发检查与自动 preflight

### 4.1 同步并确认 Git

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git fetch origin main
git merge --ff-only origin/main

git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --porcelain --untracked-files=no

test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test "$(git rev-list --left-right --count HEAD...origin/main)" = "0	0"
test -z "$(git status --porcelain --untracked-files=no)"
```

如果服务器存在 untracked `server_local/` 结果目录是正常的；tracked-clean 检查明确
忽略 untracked。若有 tracked 修改，不得 reset/restore/stash/覆盖，原样回报并停止。

### 4.2 focused checks

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

PYTHON_BIN=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
test -x "${PYTHON_BIN}"

"${PYTHON_BIN}" -m pytest -q \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r17_full_trace_source_replay.py \
  tests/communication/test_npu_keep_alive_handoff_policy.py

"${PYTHON_BIN}" -m py_compile \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/p8_2_k1a_r5_f1_r17_full_trace_source_replay.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_full_trace_source_replay.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_server_task.sh

P8_2_K1A_F1_R17_AUDIT_ONLY=1 \
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_server_task.sh \
  /tmp/p8_2_k1a_r5_f1_r17_audit_unused
```

audit-only 必须输出：

```text
task_id=p8_2_k1a_r5_f1_r17_full_trace_source_replay_2026_0727
execution_mode=authorized_offline_r15_complete_trace_source_replay
canonical_trace_reader=combined_json_else_all_jsonl
dual_trace_file_family_coverage_required=true
r15_replay_field_parity_required=true
coverage_mismatch_is_mechanism_red=false
parent_source_sha_gate_required=true
repository_input_sha_gate_required=true
npu_execution_authorized=false
vllm_server_start_authorized=false
model_requests_authorized=false
keep_alive_action=leave_running
result_package_self_verification_required=true
copy_ready_server_report_emitted=true
bounded_transfer_max_bytes=71680
result_transfer_authorized=true
transfer_method_selected=false
next_task_authorized=false
```

### 4.3 自动 preflight

```bash
P8_2_K1A_F1_R17_PREFLIGHT_ONLY=1 \
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_server_task.sh \
  "/tmp/p8_2_k1a_r5_f1_r17_preflight_unused_$$"
```

必须无 Python traceback、无 SHA mismatch，并至少输出：

```text
preflight_status=pass
repository_input_hashes_exact=true
parent_source_hashes_exact=true
parent_contract_exact=true
trace_selection_mode=all_jsonl
selected_trace_event_count=1369
trace_source_coverage_exact=true
r16_source_selector_fault_confirmed=true
prospective_grade=green_p8_2_k1a_r5_f1_r17_restore_h2d_mechanism_closed
raw_trace_unchanged_during_preflight=true
npu_started=false
vllm_started=false
model_requests_sent=0
keep_alive_action=leave_running
```

`trace_source_file_count` 与每个文件族的文件数要如实回报，但不手工固定为某个数字；
正式硬门是 canonical selection、两个文件族、1369 events 和 R15 replay fields 全匹配。

如果 preflight 正常生成 `trace_source_coverage_exact=false` 与 prospective BLOCKED，
不要改文件；仍可运行唯一正式命令产出有界 BLOCKED 包。如果出现 SHA mismatch、
parent fact mismatch、JSON 解析错误、源在读取期间改变等结构性异常，则停止，不运行
正式命令。

## 五、唯一正式命令

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r17_full_trace_source_replay_2026_0727_run01
test ! -e "${RESULT_DIR}"

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_server_task.sh \
  "${RESULT_DIR}"
```

不要提前 `mkdir "${RESULT_DIR}"`。不要手工拆 runner 内部步骤，不要运行第二次。正式
命令退出码 0 表示“离线重放、裁决与有界包生成完成”，不代表 grade 必然 GREEN。

内部顺序已固定：

```text
Git parity/clean
→ automatic preflight
→ canonical source replay
→ source immutability recheck
→ parent/repository SHA recheck
→ formal grade
→ package verify-output
→ Git parity/clean recheck
→ R17_SERVER_REPORT_BEGIN ... R17_SERVER_REPORT_END
```

如果 SSH/终端中断但 `RESULT_DIR` 已出现，视为“可能已执行”。不要删除或重发正式
命令；先只读检查现有目录、manifest 和终端日志，再回报现场。

## 六、formal grade 的三个互斥分支

### 6.1 BLOCKED：输入覆盖不等于 R15 canonical evidence

出现任一情况：

- all-jsonl 模式没有同时选中 async-transfer 与 residency 文件族；
- 任一 required key event 为 0；
- full replay event count 不等于 R15 的 1369；
- 任一冻结 R15 worker/count/bytes/lineage replay field 不一致。

正式结果：

```text
server_grade = blocked_p8_2_k1a_r5_f1_r17_source_trace_coverage_mismatch
trace_source_coverage_exact = false
mechanism_adjudication_performed = false
async_completion_evidence_exact = null
h2d_restore_mechanism_accepted = false
source_coverage_failure_is_mechanism_red = false
```

这是证据源阻断，不是 H2D 机制失败。不得改写成 RED，不得启动 NPU补跑。

### 6.2 GREEN：完整父轨迹闭合同 worker completion

只有 coverage exact 且以下全部成立：

```text
d2h_store_complete = true
h2d_restore_complete = true
d2h_async_copy_pipeline_exact = true
h2d_async_copy_pipeline_exact = true
d2h_poll_returned_completion_exact = true
h2d_poll_returned_completion_exact = true
D2H submitted/completed workers = 8/8
H2D submitted/completed workers = 8/8
async_copy_failure_event_count = 0
```

正式结果：

```text
server_grade = green_p8_2_k1a_r5_f1_r17_restore_h2d_mechanism_closed
trace_source_coverage_exact = true
mechanism_adjudication_performed = true
async_completion_evidence_exact = true
h2d_restore_mechanism_accepted = true
r16_source_selector_fault_confirmed = true
r16_historical_grade_superseded_for_mechanism_claim = true
```

“superseded”只针对 R16 的机制结论，不删除或篡改 R16 formal grade 和包。

### 6.3 RED：覆盖完整，但真实 completion edge 仍缺

只有 source coverage 与 R15 replay parity 已完全成立，才可能发出：

```text
server_grade = red_p8_2_k1a_r5_f1_r17_async_completion_evidence_incomplete
trace_source_coverage_exact = true
mechanism_adjudication_performed = true
async_completion_evidence_exact = false
h2d_restore_mechanism_accepted = false
```

此时报告具体 missing worker ordinal/count/failure event 后完成任务并暂停，不补跑。

### 6.4 所有分支都不得外推

- accepted-capacity invalidated 始终为 false；
- 不宣称 H2D 性能收益、带宽峰值或延迟改善；
- 不宣称 repair 是跨模型/版本的唯一普遍根因；
- 不把 1.08GB copy 直接变成生产收益；
- 不进入下一阶段；
- `next_task_authorized=false`。

## 七、keep-alive 规则

本轮零 NPU，keep-alive 必须全程运行，不执行 stop/restart。回报：

```text
stopped_card_ids = []
restored_card_ids = []
keep_alive_action = leave_running
```

项目长期规则仍需完整保留。下面两条是以后真正用卡时的标准命令，本轮不要执行：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

以后有 NPU 需求时，可以按常规随时停实际需要的卡；无论成功、失败、中断或提前退出，
都必须恢复完全相同卡集并回报实际停卡卡号、实际恢复卡号与恢复状态。两条命令的
末尾数字是卡号，只能收窄到实际需要的卡。停 keep-alive 本身不是严重事件，恢复同卡集
才是硬要求。

## 八、固定有界结果包

raw trace、请求内容、token、raw PID、raw request/block hash、大日志和大 timeline 全部
留服务器。R17 候选固定为：

1. `result_summary.md`
2. `task_grade.txt`
3. `grading_summary.json`
4. `full_trace_replay_summary.json`
5. `trace_source_coverage_summary.json`
6. `worker_completion_rollup.json`
7. `source_evidence_provenance.json`
8. `candidate_manifest.server_local.json`

manifest 必须满足：

```text
payload_file_count = 7
transfer_file_count = 8
transfer_total_bytes <= 71680
bounded_transfer_package_exact = true
raw_trace_content_retained = false
raw_process_ids_retained = false
request_ids_retained = false
token_ids_retained = false
raw_hash_values_retained = false
generated_content_retained = false
result_transfer_authorized = true
transfer_method_selected = false
automatic_transfer_allowed = false
```

入口生成后自动 `verify-output`，必须看到：

```text
package_verification_status=pass
payload_file_count=7
manifest_file_count=1
transfer_file_count=8
bounded_transfer_package_exact=true
```

## 九、完成后一次性回报的完整清单

请一次性回报以下 13 项，不只回一句 grade：

1. `HEAD`、`origin/main`、ahead/behind、tracked-clean；
2. focused pytest 的通过数和 exit code，py_compile、Bash syntax、audit-only exit code；
3. R15 六个 parent 文件逐项 filename/bytes/full SHA-256/MATCH；
4. R16 五个 parent 文件逐项 filename/bytes/full SHA-256/MATCH；
5. raw trace canonical selection mode、全部源文件数、selected 文件数、两个文件族各自
   available/selected file count 与 selected row count；
6. raw trace total bytes、before/after tree digest、unchanged；
7. R16 selected event count、R17 full replay event count、recovered event count；
8. required key-event histogram，以及 R15 replay field parity 是否全匹配；若不匹配，
   列出完整 `coverage_mismatch_reasons`；
9. D2H/H2D submitted/enqueued/copy-entered/copy-returned/poll-entered/
   poll-returned/live-pending/completed worker counts和 bytes；
10. 16 个 direction-local worker rollup，特别报告
    `completion_without_live_pending_worker_count`，不回 raw PID；
11. `trace_source_coverage_exact`、`mechanism_adjudication_performed`、
    `async_completion_evidence_exact`、`r16_source_selector_fault_confirmed`、
    `r16_historical_grade_superseded_for_mechanism_claim` 和最终 grade；
12. `npu_started=false`、`vllm_started=false`、`model_requests_sent=0`、
    stopped/restored 空集、keep-alive 留运行，以及 claim boundary/未授权项；
13. `result_summary.md` 绝对路径和完整 8-file 清单：
    filename/bytes/full SHA-256/sensitivity，再报 payload/manifest/transfer 合计。

优先以正式命令打印的
`R17_SERVER_REPORT_BEGIN ... R17_SERVER_REPORT_END` 为依据。不要省略不符合预期的
字段，也不要人工把 BLOCKED/RED 改成 GREEN。

完成清单后报告可用方式 `email / upload-api / server-local`，推荐一种并说明原因，
然后暂停等待用户明确选择。`result_transfer_authorized:true` 只表示完整有界包具备候选
资格，不选择渠道、不扩大范围。不要先发 status-only 邮件，不要自动切换渠道。

## 十、失败与终态对照表

| 现场 | 含义 | 唯一允许动作 |
|---|---|---|
| HEAD != origin/main 或 ahead/behind 非 0 0 | 未同步发布版本 | 只允许 fetch + ff-only 后复核 |
| tracked worktree 非 clean | 服务器存在 tracked 修改 | 原样列出并停止；不得 reset/restore/stash |
| repository SHA mismatch | 执行输入漂移 | 停止；不得编辑凑 SHA |
| R15/R16 默认目录不存在 | parent 路径不同或缺失 | 只可设置实际 run01 绝对根 |
| R15/R16 parent SHA mismatch | 不是冻结 parent | 停止并报 expected/actual |
| 没有 retained trace source | R15 raw trace 不在现场 | 停止；不得 NPU 补跑 |
| JSON/JSONL 解析失败 | raw source 不可读 | 保留现场并停止 |
| before/after trace tree 不同 | 分析期间父源变化 | 停止，不重跑 |
| preflight coverage=false | canonical replay 与 R15 不一致 | 运行唯一正式命令，生成 BLOCKED 包 |
| RESULT_DIR 已存在 | 已执行或目录冲突 | 不删、不覆盖、不建 run02；只读回报 |
| package mismatch/exceeds | 候选包不完整或超限 | 不传输，回报错误与本地路径 |
| formal BLOCKED | 输入覆盖不完整 | 回报 mismatch，任务完成并暂停 |
| formal RED | 覆盖完整但 completion edge 缺失 | 回报缺失边，任务完成并暂停 |
| formal GREEN | R15 同 lifecycle restore H2D 机制闭合 | 回报边界，任务完成并暂停 |

## 十一、当前仓库合同输入 SHA-256

下列值由开发机在最终修改后生成。服务器的 analyzer 会从 audit 自动校验其中的直接
执行输入；服务器助手不要手工更新。

```text
cc35d57c5b1e586875a9472864f56d05f058698a8a493797d80ef8ea0f027317  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r17_full_trace_source_replay_audit.yaml
d7fac55bd00de647d7657cedbd85617b848790d06725c8520534bad532abd525  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r17_full_trace_source_replay.yaml
43801af40010490ae51a7545dcff762dee831f3af937b23192514a95523add85  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
7a2bd0789d932249b77520d6f4927463c83481b937e226d73bc7a793bb4e323b  tools/inference_contracts/p8_2_k1a_r5_f1_r16_async_completion_adjudication.py
201b81d4b2545b8813f256ebe840864842c9e2eef2b6eb5cc706575166e8eee9  tools/inference_contracts/p8_2_k1a_r5_f1_r17_full_trace_source_replay.py
e958a0ddaf3960a8d55a7bac2930a8aae6255e590727add1dda2103259cd2b31  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_full_trace_source_replay.sh
000a3bd53c881b3ea3b2a0f18f34604f36dd5da250236add4316b4df39ff7f31  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r17_server_task.sh
06c3aef4781b3893a64e9e733c6d2c08125bf4f702939ab896c3809349e61e2c  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r17_full_trace_source_replay.py
```

## 完成后停止

回报 R17 run01 与完整候选清单后暂停。不要自动传输，不要自动开 R18、run02、NPU
重跑、K2 或 P8.3-I1。
