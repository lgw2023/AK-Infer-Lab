# P6.3C-R3E-F1-A1 服务器任务：全 rank request-scoped trace 重聚合

本任务是 R3E-F1 的零 NPU 科学证据整理，不是模型实验重跑，也不是为了修改自动评分颜色。
R3E-F1 已经成功完成两条 request-scoped profiler lifecycle；本轮直接读取服务器保留的 raw/
converted trace，把当时仅 rank 0、名称 token 驱动的现场聚合升级为可复现的 8-rank 证据。

核心目标是回答：

1. 两条 lifecycle 的 8 个 rank 是否都完整读到 trace JSON 数组末尾，而不是被 5M event cap
   或 parser 截断；
2. request window 中哪些 timed range 有 schema-level device provenance，哪些只是 runtime/queue、
   host framework range 或名称推断的 operator candidate；
3. collective、attention、matmul/MoE、compiler/graph 等语义类别在 rank 间是否一致，按 scheduler
   relevant step / Prefill chunk 归一化后呈现什么结构；
4. 现有证据能否支持“compiler 按小 chunk 重复”或“HCCL wait 位于 critical path”。如果不能，
   必须明确保留为假设，不提前选择优化方向。

服务器 AI 可以依据真实文件布局做 task-local 兼容修复和零 NPU 重跑。修复必须保留 before/after
SHA、最小 diff、attempt 顺序、原因和 `scientific_impact`。不得修改或覆盖源 F1 结果，不得 push
remote `main`。如果修改事件分类、rank 范围、完整性定义、归一化口径或研究问题，必须作为新
variant 报告，不能冒充未改变的 A1。

## 1. 已完成事实：不要重跑 NPU

源 task：

- task ID：`p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01`
- source HEAD：`90c027e7b97cb8a1ca152b76ca29105ebe74128c`
- server grade：`complete_p6_3c_r3e_f1_request_scoped_profile_evidence`
- scientific outcome：`executor_path_supported_with_request_scoped_device_categories`
- 2/2 lifecycle exit 0，20/20 EngineCore request，6/6 HTTP request，0 retry；
- 两条 lifecycle 的 `/start_profile` 与 `/stop_profile` 均 HTTP 200；
- profiler window 在 warmup 后开始、measured staged-arrival trial 后停止，模型加载不在窗口；
- `profile_f1_01` admission T4096：Prefill chunks=`4096,8185`，5 relevant steps；
- `profile_f1_02` persistent T128：56 Prefill chunks、59 relevant steps、55 pressure chunks；
- 两条 lifecycle 均无 preemption，mechanism gate 完整；
- 任务退出后 0–7 keep-alive=16 markers、端口 7000 无监听、无 vLLM residual。

源结果目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_2026_0808_attempt_01/p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
```

现场报告称已对 16 份 rank profiler data 调用
`torch_npu.profiler.profiler.analyse()` 生成 `trace_view.json`，但 task-local analyzer 设置了
`max_ranks=1`，所以收到的小包只含 rank 0 聚合。rank-0 trace 为：

| lifecycle | trace bytes | 现场 event count | 说明 |
| --- | ---: | ---: | --- |
| `profile_f1_01` | 871,640,034 | 3,788,657 | admission T4096 |
| `profile_f1_02` | 2,928,549,101 | 5,000,001 | persistent T128；必须核实是否 event cap |

不得重跑两个 profiler lifecycle，不得重跑 R3E host lifecycle，不得从 profiler-on trace 重新估计
R3D 的 TTFT/TBT/TPS。

## 2. 本轮身份与完成条件

- task ID：`p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808`
- NPU used：`false`
- keep-alive action：`left_running`
- source result overwritten：`false`
- 目标 rank：每条 lifecycle 8 个唯一 rank，共 16 份 trace view；
- 正式分析 event limit：`None`，必须读到每个 JSON event array 的闭括号；
- 派生结果必须写入独立目录，源目录的小文件 SHA 与 trace size/mtime 前后完全相同；
- 不选择优化 target；完整 outcome 应为
  `descriptive_cross_rank_execution_path_complete_causal_bottleneck_unresolved`。

完整成功需要：

1. 源 F1 task、lifecycle、profile control、mechanism、cleanup 结构化验证通过；
2. `profile_f1_01` 和 `profile_f1_02` 各发现 rank 0–7；
3. 16 份 trace 都有 `parse_complete=true`、`event_limit_reached=false`、空 parse error；
4. 输出 per-trace inventory、per-rank domain/category、cross-rank median/min/max、top operator、
   scheduler normalization 和 hypothesis review；
5. 强 device kernel、runtime/queue wait、host framework range、name-inferred candidate 明确分开；
6. `_C_ascend::npu_sparse_attn_sharedkv`、flash attention、MLA、lightning indexer 归入 attention；
7. `npu_fx_compiler inference` 按 rank 与 Prefill chunk 归一化，但不得仅凭 event count 宣称重编译；
8. HCCL dequeue/sync 若没有 dependency-flow proof，必须报告
   `critical_path_identifiable=false`；
9. bounded candidate package 不超过 70KB，先展示 manifest，等待用户选择传输方式；
10. `next_task_authorized=false`，不得自动进入优化实验。

## 3. 同步 main 与独立 worktree

本轮必须从用户通知的最新 `origin/main` 建立独立 detached worktree，不要修改共享 checkout：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3e_f1_a1_2026_0808

git -C "${SHARED_REPO}" fetch origin main
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" origin/main
git -C "${WORKTREE}" status --short --branch
git -C "${WORKTREE}" rev-parse HEAD
git -C "${WORKTREE}" rev-parse origin/main
git -C "${WORKTREE}" rev-list --left-right --count HEAD...origin/main
```

如果目录已存在，不要删除；核对归属后为新 attempt 建立
`p6_3c_r3e_f1_a1_2026_0808_attempt_02` 等新 worktree。服务器不得 push remote `main`。

完整阅读：

```bash
cd "${WORKTREE}"
sed -n '1,360p' docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
sed -n '1,520p' 通信模块/docs/developer-to-server.P6.md
```

## 4. 发布资产与来源 SHA

以下 SHA 是同步事实，不是禁止现场修复的旧式冻结合同。若资产不同，先确认 worktree 已同步用户
通知的最新 `origin/main`；若仍需修复，按自适应策略在 task-local 副本保存 provenance。

| 文件 | SHA-256 |
| --- | --- |
| `tools/inference_contracts/analyze_torch_profiler_traces.py` | `84ded6fdd1dd05ac7a826754e5504f0cd490989e823d9ca7e15eb6a9fe9266e0` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.py` | `a4088ae6afbcd5c6dd323efc8b78b9137c6be2cabdb86c88410ade406676c90f` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.sh` | `273461be444d840c3ea8447ab263bf21ee978bb49f064c651fca575e8539a9c7` |
| `tests/inference_contracts/test_deepseek_p6_3c_r3e_f1_profile_completion.py` | `5be5bafc9ee37cd5a2073f8c97b319ea3ac5f92c4fabb48f1865c94bb971fc84` |
| `工作记录与进度笔记本/22_P6_3C_R3E_执行路径归因与跨Rank重聚合手稿.md` | `7708d160133cb505b6b7ce94e64f67a7a4472da50bdf89771caea5222af46a14` |

源 F1 小文件应保持：

| 文件 | SHA-256 |
| --- | --- |
| `grading_inputs.json` | `9a231bbbcf37aa74877b11af610f9ec9c31c60a47554a23736bc71ce0497ea6c` |
| `environment_and_hashes.json` | `bcf7cdea78536a99f0b40dfbd558f764a3d904fcf6cfabc916fd7a233973e4c0` |
| `lifecycle_summary.tsv` | `e66059e19ac5196737ec40e846cee669f21c10f0ca299593483cb207c29f1399` |
| `r3e_mechanism_cells.tsv` | `0816c8d500ecb35b61a7e5ba2224664097efa663b2e18adb82e73f561d0e8f58` |
| `r3e_f1_profile_control_summary.tsv` | `77acc9da1ef0d211e02fdcdaef6aff368d793606cbd0f8dfdc375f1109ae49d3` |
| `resource_recovery_summary.json` | `e8822f78d8e650dd57ddcec6edc5740048eb2390a3cc7d58eed6a249c9067a5a` |
| `cleanup_status.txt` | `2e22da2ab13713309ac75219e525b8e06ed02f3f1963b8feef203fa25827f93d` |

核验命令：

```bash
cd "${WORKTREE}"
sha256sum \
  tools/inference_contracts/analyze_torch_profiler_traces.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.sh \
  tests/inference_contracts/test_deepseek_p6_3c_r3e_f1_profile_completion.py \
  工作记录与进度笔记本/22_P6_3C_R3E_执行路径归因与跨Rank重聚合手稿.md

SOURCE_F1=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_2026_0808_attempt_01/p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
sha256sum \
  "${SOURCE_F1}/grading_inputs.json" \
  "${SOURCE_F1}/environment_and_hashes.json" \
  "${SOURCE_F1}/lifecycle_summary.tsv" \
  "${SOURCE_F1}/r3e_mechanism_cells.tsv" \
  "${SOURCE_F1}/r3e_f1_profile_control_summary.tsv" \
  "${SOURCE_F1}/resource_recovery_summary.json" \
  "${SOURCE_F1}/cleanup_status.txt"
```

## 5. 零 NPU preflight

本任务不需要卡，也不要求等待 NPU 空闲。它不得停止 keep-alive、启动 vLLM、访问 7000 端口或
运行 profiler lifecycle。先确认没有误配的正式实验进程，然后只运行来源/trace-view 发现：

```bash
cd "${WORKTREE}"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
SOURCE_F1=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_2026_0808_attempt_01/p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01

pgrep -af 'p6_3c_r3e_f1_a1|run_deepseek_p6_3c_r3e_f1_a1' || true
"${ENV_PREFIX}/bin/python" \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.py \
  validate-only \
  --source-artifact-dir "${SOURCE_F1}" \
  --expected-ranks 8
```

正常输出应显示两条 lifecycle 各 8 个 rank 且 `source_validation_complete=true`。validate-only
只发现文件和核验小证据，不扫描 multi-GB event array。

### Keep-alive 操作规则

本任务是 no-card work，必须让 keep-alive 保持运行，报告
`npu_used=false, keep_alive_action=left_running, stopped_card_ids=none, restored_card_ids=none`。
下面两条命令是项目统一的应急操作规则，不是本任务执行步骤：只有未来经用户授权且确实需要 NPU
的任务，才可在其需要的卡上停止，并在 success/failure/interruption/early exit 后恢复完全相同的卡集。

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

## 6. 正式零 NPU 重聚合

使用独立派生结果目录：

```bash
cd "${WORKTREE}"
SOURCE_F1=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_2026_0808_attempt_01/p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
OUTPUT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_a1_2026_0808
OUTPUT_DIR="${OUTPUT_ROOT}/p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808"

test ! -e "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_ROOT}"
PYTHONUNBUFFERED=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.sh \
  "${SOURCE_F1}" "${OUTPUT_DIR}" \
  2>&1 | tee "${OUTPUT_ROOT}/reaggregation.log"
```

分析 16 份 multi-GB trace 可能长时间没有终端输出；不要因为它不是 NPU 作业就启动第二份并发 A1。
用 `ps`、输出文件大小和 I/O 判断进度，不要设置 event cap，也不要把无输出当成 hang。正式结果中
`event_limit_used` 必须为 false。

## 7. rank trace-view 缺失分支

若 validate-only 只发现 rank 0，但 raw `_ascend_pt` 目录仍在，不得重跑 profiler lifecycle，也不得
改写源结果。使用服务器在 F1 已验证过的
`torch_npu.profiler.profiler.analyse()` 在 task-local `TRACE_WORKSPACE` 中为缺失 rank 生成
`trace_view.json`：

1. `TRACE_WORKSPACE` 建议为
   `/data/node0_disk1/liguowei/server_analysis/p6_3c_r3e_f1_a1_trace_views_attempt_01`；
2. 在该目录下建立 `profile_f1_01/` 与 `profile_f1_02/`；
3. 对每个 raw rank 建 task-local 目录，只读引用 raw input，转换输出写到 task-local 目录；不要让
   `analyse()` 在 `${SOURCE_F1}` 下新增、覆盖或删除文件；
4. 保存 raw rank source path、source size/mtime、conversion command、output size/mtime、rank ID；
5. 转换后将该 workspace 作为 wrapper 第三个参数：

```bash
PYTHONUNBUFFERED=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.sh \
  "${SOURCE_F1}" "${OUTPUT_DIR}" "${TRACE_WORKSPACE}"
```

如果实际 `analyse()` API、raw 布局或输出层级不同，服务器 AI 可在 task-local helper 中修复并继续；
报告 before/after SHA、diff、输入/输出路径和 `scientific_impact=none`。如果转换只能通过触 NPU 或
重跑请求完成，停止并报告，不要扩大授权。

## 8. 解释规则

发布 analyzer 把“来源证明力”和“语义类别”正交分开：

- `device_kernel`：device process metadata、trace category 或 event args 明确支持；
- `runtime_or_queue_wait`：dequeue/enqueue、ACL runtime、stream/event sync；
- `host_framework_range`：`aten::`、`vllm::`、`c10d::`、`_C_ascend::`、`npu::`、compiler range；
- `name_inferred_device_candidate`：仅名称像 operator，没有 schema-level device provenance；
- `unclassified_timed_range`：其余 timed range。

不得把 `name_inferred_device_candidate` 改名为 device kernel，也不得把这些 domain 的 duration sum
相加后称为 wall-clock。`active_time_union_us` 只有在 timestamp 单调时输出；它是重叠消解后的
activity span，不是 dependency-aware critical path。

必须自然语言回答：

1. 每条 lifecycle 是否确有 rank 0–7，16 个数组是否都读到末尾？T128 的 5,000,001 是真实长度
   还是旧 parser cap？
2. 强 device kernel、runtime/queue、host framework 与 name-inferred candidate 的 rank 间分布如何？
3. attention 在新 classifier 中是否可见；旧版 `other` 是否主要来自分类遗漏？
4. `npu_fx_compiler inference` 每 rank 每 Prefill chunk 的 event count 是多少；是否有实际
   recompilation/cache-miss 证据，还是仅有嵌套 range 重复？
5. HCCL queue wait 是否有 dependency-flow/step timestamp 证明位于 critical path？若没有，明确说没有；
6. 现有证据是否足以选择 compiler、collective、MoE 或 attention 优化？默认答案不是预设的，必须
   由结构化证据支持。

## 9. 自适应修复与停止条件

允许的 task-local 修复：

- bare JSON array、gzip、trace-view 名称、rank/path 解析；
- 流式 parser buffer、Unicode、Chrome trace schema；
- source/trace workspace 布局与 `torch_npu.profiler.profiler.analyse()` 兼容；
- finalizer、TSV/JSON serialization、bounded manifest；
- category token 的真实 Ascend 名称补充，但必须保留旧/新分类 diff 和影响行数。

任何修复后使用新 output/attempt 目录；不要覆盖失败目录。若仅 finalizer/package 失败，直接零 NPU
修复并从保留 trace 重聚合，不得重跑模型。

停止并报告：

- 源小文件身份不符且无法解释；
- raw/converted traces 缺失，恢复必须重跑 NPU 请求；
- 需要 event cap 才能完成正式结果；
- 必须改变 rank 范围、分类定义或归一化口径但未建立新 variant；
- 源结果在分析前后发生变化。

## 10. 结果包与传输

`result_transfer_authorized: true`。这表示 bounded package 有资格交付，不表示已选择传输方式。
完成后必须先展示：

- `result_summary.md` 的服务器绝对路径；
- `candidate_manifest.server_local.json` 的 bytes 与 SHA-256；
- manifest 内每个候选文件的 path、bytes、SHA-256、sensitivity；
- candidate 总文件数与总 bytes（不超过 70KB）；
- `email` / `upload-api` / `server-local` 三种可用方法；
- 推荐 `upload-api`，理由是可用一个 named multi-file session 做逐文件 SHA 验证。

等待用户明确选择后再传输。不得自动沿用 F1 的方式，不得先发 status-only email。若 upload-api
出现 401/409/413、proxy/redirect、timeout、service 或 hash failure，停止并要求新的传输选择，
不得自动改用 email。raw traces、完整 event TSV、server log 和 reaggregation log 留在服务器。

## 11. 服务器最终报告格式

```text
P6_3C_R3E_F1_A1_SERVER_REPORT_BEGIN
task_id=p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808
source_task_id=p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
head=...
origin_main=...
ahead_behind=0 0
worktree=...
source_result=...
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
profile_f1_01_rank_count=...
profile_f1_02_rank_count=...
all_trace_arrays_parsed_to_end=true|false
event_limit_used=false|true
profile_f1_01_event_count_by_rank=...
profile_f1_02_event_count_by_rank=...
t128_5000001_explanation=...
strong_device_domain_summary=...
runtime_queue_domain_summary=...
host_framework_domain_summary=...
name_inferred_domain_summary=...
attention_visibility=...
compiler_events_per_rank_per_chunk=...
compiler_recompilation_proven=false|true
hccl_critical_path_identifiable=false|true
optimization_target_selected=false|true
scientific_outcome=...
evidence_status=complete|incomplete
server_grade=...
candidate_manifest=...,file_count,total_bytes,sha256
result_transfer_authorized=true
transfer_method_selected=false
available_methods=email,upload-api,server-local
recommended_method=upload-api
next_task_authorized=false
P6_3C_R3E_F1_A1_SERVER_REPORT_END
```

报告后附六个自然语言问题的答案和完整 bounded manifest。不要自动进入下一任务。
