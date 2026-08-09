# P6.3C-R3E-F1-A2 服务器任务：scheduler step × profiler flow 因果连接

本轮不是重跑 Chunked Prefill 性能实验，也不是为了改变自动评分颜色。R3E-F1-A1 已经完整解析
两条 request-scoped profiler lifecycle 的 16 份 rank trace，但只能形成整窗、跨 rank 的描述性
执行路径：现有结果没有把 scheduler mixed step、runtime enqueue/wait 与真实 device execution
通过共同标识连接起来，因此不能选择 collective、compiler、MoE 或 attention 优化方向。

本任务以零 NPU、只读方式复用 F1 raw result 与 A1 derived result，完成两个独立证据轨道：

1. 从 F1 scheduler observer JSONL 恢复每个 `timing_context_id` 的 execute window，把 profiler
   timestamp 对齐到 scheduler monotonic clock，并生成 step×rank 的 temporal attribution；
2. 完整扫描 Chrome `s/t/f` flow 与 correlation/external/record-function/sequence/connection IDs，
   检查是否有共同标识跨越 host framework、runtime/queue 与 device execution candidate。

时间上落入同一 step 只是 temporal evidence；共同 flow/correlation ID 才是 dependency candidate。
两者都不能在缺少重复 final-edge 证据时直接改写成 causal critical path。

## 1. 已知事实与必须保留的结论边界

源 F1：

- task ID：`p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01`；
- 两条 lifecycle：`profile_f1_01=admission_on_t4096`，
  `profile_f1_02=persistent_on_t128`；
- F1 结果目录：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_2026_0808_attempt_01/p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01`；
- 2/2 lifecycle、20/20 EngineCore request、6/6 HTTP request、零 retry；
- profiler window 位于 warmup 后、单次 measured staged-arrival trial 内；
- T4096 为 `4096,8185` 两块/5 relevant steps；T128 为 56 chunks/59 relevant steps；
- 0–7 keep-alive 已恢复，源结果后续只读。

源 A1：

- task ID：`p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808`；
- derived 目录：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_a1_2026_0808/p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808`；
- 16/16 trace arrays 读到闭括号，无 event cap；
- T4096 共 30,310,171 events，T128 共 99,784,353 events；
- outcome：
  `descriptive_cross_rank_execution_path_complete_causal_bottleneck_unresolved`；
- `optimization_target_selected=false`。

A1 报告中的 candidate manifest 在 adaptive review 最终补写前生成：manifest 记录该文件为
355 bytes/`0e5a...`，实际终态为 1,013 bytes/
`8e9abfb01a0ee424558d48b7e0b088435ccc7200b07f7180f6f6700a0be35407`。其余文件与科学结论不受
影响。A2 不把旧 A1 manifest 当作终态传输身份，只核验 A1 的 task/outcome；A2 自己必须在所有
adaptation 记录写完后最后运行 `package`。

必须保留：

- R3D：`persistent_prefill_tradeoff_no_candidate_within_bounds`；
- A1：全 rank 描述完整、causal bottleneck unresolved；
- 原 P6.3C：135168/4096/1 下 Off 无法启动，严格单变量 A/B blocked；
- 本轮不是性能比较，不从 profiler-on trace 推导 TTFT/TBT/TPS 收益。

## 2. 本轮身份与完成条件

- task ID：`p6_3c_r3e_f1_a2_step_flow_causal_linkage_2026_0809`；
- NPU used：`false`；keep-alive action：`left_running`；
- source F1/A1 overwritten：`false`；
- 两条 lifecycle、每条 rank 0–7、正式分析 event cap=`None`；
- 派生目录必须新建，不覆盖 F1 或 A1；
- `result_transfer_authorized=true`，但 transfer method 保持未选择；
- 不自动进入 R3E-F2，不启动 vLLM，不访问 7000，不停止卡。

完成的描述性证据要求：

1. F1 来源验证与 A1 task/outcome 验证通过；
2. scheduler observer 的四事件 timing context 能恢复；
3. 16 份 trace 全部再次读到数组末尾，无 event cap；
4. 对每个 rank 报告 clock transform、flow/link field census、temporal attribution；
5. 输出 cross-domain link chains、step×rank path、cross-rank activity-end skew；
6. 明确区分 actual kernel、device analysis timeline 与 device-process range；
7. 所有 source size/mtime 与小文件 SHA 在分析前后不变；
8. bounded package ≤70KB，manifest 在 adaptive review 终态之后生成。

`causal_bottleneck_resolved` 不属于必须为 true 的工程 gate。若 trace schema 缺少 clock/link 字段，
精确识别缺口就是本轮的有效科学结果；不得为了得到绿色标签虚构 correlation chain。

## 3. 同步 main 与并发隔离

从用户通知的最新 `origin/main` 建立独立 detached worktree。不得使用正在执行其他任务的 worktree，
不得修改共享 checkout，不得 push remote `main`：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3e_f1_a2_2026_0809

git -C "${SHARED_REPO}" fetch origin main
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" origin/main
git -C "${WORKTREE}" status --short --branch
git -C "${WORKTREE}" rev-parse HEAD
git -C "${WORKTREE}" rev-parse origin/main
git -C "${WORKTREE}" rev-list --left-right --count HEAD...origin/main
```

若该目录已存在，不要删除；核验归属后使用 `..._attempt_02`。开始前检查没有另一个 A2 scan；这是
I/O 密集型全 trace 分析，即使不占 NPU 也不要并发扫描同一 30GB trace 集合。

完整阅读：

```bash
cd "${WORKTREE}"
sed -n '1,420p' docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
sed -n '1,520p' 通信模块/docs/developer-to-server.P6.md
```

## 4. 发布资产核验

SHA 用于确认拉取到本轮发布代码，不是禁止服务器做 task-local 兼容修复的冻结合同：

| 文件 | SHA-256 |
| --- | --- |
| `tools/inference_contracts/analyze_torch_profiler_traces.py` | `c99507ac09921b10a9e86d50ac16833e3e4d911d7957a8a1993b6b2a39277374` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.py` | `cbe2080b64dd6b77fcb384258ba2524eedde8975fa089c1638a6af084c2fc3b1` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a2_causal_linkage.py` | `c37f4522a1682044b43bbe760bac9f46682767e5b818eeeaaecd649e48f65636` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a2_causal_linkage.sh` | `fb17d391ab2ebf90235f60aff01533c5898e19a97afa270a4c3f214ad81f44c1` |
| `tests/inference_contracts/test_deepseek_p6_3c_r3e_f1_profile_completion.py` | `398df49e6cc3533df2d015cbdee648172405564c68e4903a8bf0048e0843b309` |
| `工作记录与进度笔记本/22_P6_3C_R3E_执行路径归因与跨Rank重聚合手稿.md` | `bd53ead2e7075d6e0f3abd2740acd08efc328439f22c6e3412685c7fc93bf5c2` |

```bash
cd "${WORKTREE}"
sha256sum \
  tools/inference_contracts/analyze_torch_profiler_traces.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a2_causal_linkage.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a2_causal_linkage.sh \
  tests/inference_contracts/test_deepseek_p6_3c_r3e_f1_profile_completion.py \
  工作记录与进度笔记本/22_P6_3C_R3E_执行路径归因与跨Rank重聚合手稿.md
```

若不同，先确认 `HEAD=origin/main`；仍不同时记录实际 SHA 与原因。允许在 task-local 副本修复真实
trace schema/path/serialization，必须保存 before/after SHA、最小 diff、attempt 顺序和
`scientific_impact`。不得在源 F1/A1 目录内写 helper 或结果。

## 5. 零 NPU preflight

```bash
cd "${WORKTREE}"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
SOURCE_F1=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_2026_0808_attempt_01/p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
SOURCE_A1=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_a1_2026_0808/p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808

test -x "${ENV_PREFIX}/bin/python"
test -d "${SOURCE_F1}"
test -f "${SOURCE_A1}/scientific_outcome.json"
pgrep -af 'p6_3c_r3e_f1_a2|run_deepseek_p6_3c_r3e_f1_a2' || true

"${ENV_PREFIX}/bin/python" \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a2_causal_linkage.py \
  validate-only \
  --source-artifact-dir "${SOURCE_F1}" \
  --source-a1-result "${SOURCE_A1}" \
  --expected-ranks 8
```

validate-only 只核验结构和 trace inventory，不读完整 event array。必须看到 F1 source validation、
A1 task ID、A1 cross-rank complete 均为 true。

### Keep-alive 规则

本任务不需要 NPU，必须让 keep-alive 保持运行，并报告：

```text
npu_used=false
keep_alive_action=left_running
stopped_card_ids=none
restored_card_ids=none
```

以下是项目统一应急规则，不是本任务步骤。只有未来明确授权的 NPU 任务才可在需要的卡上停止，并在
success/failure/interruption/early exit 后恢复完全相同卡集：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

## 6. 正式 A2 分析

```bash
cd "${WORKTREE}"
OUTPUT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_a2_2026_0809
OUTPUT_DIR="${OUTPUT_ROOT}/p6_3c_r3e_f1_a2_step_flow_causal_linkage_2026_0809"

test ! -e "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_ROOT}"
PYTHONUNBUFFERED=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a2_causal_linkage.sh \
  "${SOURCE_F1}" "${SOURCE_A1}" "${OUTPUT_DIR}" \
  2>&1 | tee "${OUTPUT_ROOT}/a2_analysis.log"
```

16 份 trace 合计约 130M events，可能较长时间无输出。不要设置 `--max-events-per-trace`，不要并发
启动第二个 A2。用 `ps`、I/O 与结果文件变化判断进度。若需要进度输出，可在 task-local 副本增加
每 trace START/END，不改变 event selection、clock inference 或 link fields。

关键输出：

- `scheduler_step_windows.tsv`：完整 observer execution windows，server-local；
- `trace_linkage_inventory.tsv`：每 rank parse/clock/link census；
- `link_field_summary.tsv`：每种 link field 的唯一值与跨域值计数；
- `cross_domain_link_chains.tsv`：只返回哈希后的 top host→runtime→device chain；
- `step_rank_path_full.server_local.tsv`：完整 step×rank×role，不进入小包；
- `step_rank_path_summary.tsv`：每 lifecycle/rank 主要 role 的有界摘要；
- `step_cross_rank_summary.tsv`：每步 rank 覆盖、最晚活动 rank、activity-end skew；
- `bottleneck_hypothesis_review.json`：证据充分性和下一步。

## 7. 分类、时间与因果解释规则

事件来源域：

- `actual_device_kernel`：只有 trace category 或 event args 明确支持 kernel；
- `device_analysis_timeline`：`Free`、`Computing`、`Communication`、
  `Communication(Not Overlapped)`、`Notify_Wait`；它们是 profiler 派生分析轨道；
- `device_process_timed_range`：仅由 device process metadata 支持、但没有 kernel-level 证明；
- `runtime_or_queue_wait`、`host_framework_range`、`name_inferred_device_candidate` 与
  `unclassified_timed_range` 保持各自边界。

不得：

- 把 `Communication(Not Overlapped)` 直接称为 HCCL kernel 或 causal wait；
- 把 clipped duration sum 称为 interval union、wall-clock decomposition 或 critical path；
- 因为同一事件同时落入 two-batch async 的两个 execution window 就重复解释为两次执行；
- 把 stream ID 单独当 dependency ID；
- 输出原始 correlation/flow values 到小包；代码只输出带 kind 的 SHA 前缀。

clock alignment 允许返回 unresolved。如果真实 trace 的 timestamp schema 未覆盖已发布候选单位/origin，
服务器 AI 可在 task-local 副本增加有证据的 transform，必须返回原始 timestamp 数量级、observer
clock 数量级、推导公式、before/after 覆盖率与 scientific impact。不得人工平移到“看起来重合”。

## 8. 自适应修复、变体与停止条件

允许的 task-local 修复：

- 真实 flow/correlation key 的大小写、嵌套 args 或 Chrome schema 兼容；
- scheduler trace path、多个 PID JSONL、trace workspace 布局；
- timestamp unit/origin 的证据化扩展；
- progress、内存、TSV/JSON、bounded package、manifest 终态刷新；
- 只读重试与新 attempt 目录。

每次 adaptation 必须写入 `adaptive_execution_review.json`：attempt、原因、patch path、before/after
SHA/diff、scientific impact。若改变 link field 定义、clock alignment 判定、step window、event domain
或 causal gate，必须报告 `scientific_contract_changed=true` 并给新 variant ID，不能冒充原 A2。

停止并返回当前证据：

- F1/A1 源身份或 trace 缺失且恢复需要重跑 NPU；
- 必须使用 event cap 才能完成；
- 源目录在分析前后变化；
- 现有 trace 没有可用 correlation/flow linkage。

最后一种不是失败：报告每种字段的实际计数、clock 是否对齐、哪个 host/runtime/device edge 缺失，
并给出 R3E-F2 的最小 instrumentation 方案。A2 不自动执行 F2，不自动触 NPU。

## 9. 必须自然语言回答的问题

1. F1 的 scheduler observer 恢复出多少 execution window？T4096/T128 各多少，mixed step 各多少？
2. 每个 rank 的 profiler timestamp 最终选择什么 unit/origin？16/16 是否可靠对齐？覆盖率与
   multi-window event count 是多少？
3. trace 中实际有哪些 flow/correlation field？多少 unique values 能跨 domain，多少能形成
   host→runtime→device candidate chain？
4. `Free/Computing/Communication/Notify_Wait` 重新分类后，actual kernel、analysis timeline 与
   device-process range 的主要 role 分布如何？
5. pressure step 的 8-rank activity-end skew 是否稳定指向某个 rank？该 rank 的最后活动 role 是什么？
6. 是否存在多数 pressure step 重复出现的 dependency-linked final edge？若没有，明确缺哪一环。
7. 现有证据是否足以选择 collective/compiler/MoE/attention 优化？若选择，给出结构化链和适用
   step/rank；若不选择，给出最小 R3E-F2 instrumentation，不要建议重复 budget sweep。

## 10. 终态 package 与传输边界

任何 adaptation/provenance 写入后，必须把 package 作为最后一次写操作重新执行：

```bash
"${ENV_PREFIX}/bin/python" \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a2_causal_linkage.py \
  package --output-dir "${OUTPUT_DIR}"
```

随后逐项核对 `candidate_manifest.server_local.json` 的 bytes/SHA 与实际文件；不得在 package 后再改
候选文件。完整 raw trace、完整 step-rank TSV 与 log 留在服务器。

`result_transfer_authorized=true` 只表示 bounded package 有资格交付，不表示已选择渠道。完成后先展示：

- `result_summary.md` 与 manifest 的服务器绝对路径；
- 每个候选文件 path、bytes、SHA-256、sensitivity；
- 总文件数/bytes（≤70KB）；
- 可用 `email` / `upload-api` / `server-local`；推荐 `upload-api`，因为可在一个 named session 中
  逐文件校验 SHA。

等待用户明确选择后再传输。不得沿用上轮选择，传输失败后不得自动切换渠道。

## 11. 服务器最终报告格式

```text
P6_3C_R3E_F1_A2_SERVER_REPORT_BEGIN
task_id=p6_3c_r3e_f1_a2_step_flow_causal_linkage_2026_0809
source_f1_task_id=p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
source_a1_task_id=p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808
head=...
origin_main=...
ahead_behind=0 0
worktree=...
source_f1_result=...
source_a1_result=...
derived_result=...
source_result_overwritten=false
source_evidence_unchanged=true|false
npu_used=false
keep_alive_action=left_running
stopped_card_ids=none
restored_card_ids=none
adaptive_attempt_count=...
adaptive_patch_paths=...
scientific_contract_changed=false|true
scheduler_window_count=...
profile_f1_01_window_count=...
profile_f1_02_window_count=...
trace_rank_coverage=16/16
all_trace_arrays_parsed_to_end=true|false
event_limit_used=false|true
clock_alignment_complete=true|false
clock_transform_by_rank=...
step_rank_coverage_complete=true|false
multi_window_event_count=...
link_field_kinds=...
cross_domain_link_value_count=...
host_runtime_device_link_value_count=...
device_analysis_timeline_separated=true|false
pressure_step_rank_skew_summary=...
repeated_dependency_linked_final_edge=none|...
causal_bottleneck_resolved=false|true
optimization_target_selected=false|true
scientific_outcome=...
evidence_status=complete|incomplete
server_grade=...
candidate_manifest=...,file_count,total_bytes,sha256
manifest_matches_final_files=true|false
result_transfer_authorized=true
transfer_method_selected=false
available_methods=email,upload-api,server-local
recommended_method=upload-api
next_task_authorized=false
P6_3C_R3E_F1_A2_SERVER_REPORT_END
```

报告后附七个自然语言回答和完整 bounded manifest。不要自动进入 R3E-F2。
