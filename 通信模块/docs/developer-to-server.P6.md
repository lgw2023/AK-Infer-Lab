# 开发机 → Ascend 服务器：P6.3C-R3B-A1 零 NPU 性能再聚合

更新时间：2026-08-04

任务 ID：`p6_3c_r3b_a1_performance_reaggregation_2026_0804`

源任务 ID：`p6_3c_r3b_chunk_budget_pareto_2026_0804_run01`

任务性质：`zero-NPU / read-only source evidence / derived refinalization`

## 1. 本轮唯一目标

不要重跑 R3B 的 17 个 NPU lifecycle。读取服务器已保留的 R3B run01 raw JSONL 与 scheduler
trace，在一个新的派生结果目录中重新生成性能 summary、60 个 Off/On pair、uncertainty、
resident TBT SLO attainment 和五目标 Pareto frontier。

本轮要关闭的是“正式性能聚合”而不是“实验执行”：

- 17/17 lifecycle、1286/1286 engine request、243/243 HTTP、五档 chunk 机制和资源恢复已经完成；
- 原 finalizer 因 measured trial summary 缺少 `phase`，把 144 个有效 trial 全部过滤；
- 原顶层包在 0 trial / 0 valid pair / uncertainty n=0 时仍错误标为 complete；
- 开发机已修复 trial 识别，并把性能样本完整性纳入 fail-closed evidence gate。

完成后停在 A1。不要进入 R3C、P7、P8、P9 或其他服务器任务。

## 2. 科学背景与不能改变的内容

R3B 的研究对象是一个完整 policy comparison：

```text
Off baseline: chunked_prefill_off, B=12288
On policies:  chunked_prefill_on,  B=2048/4096/6144/8192/12288
max_model_len=12288
max_num_seqs=9
Prefix Cache=false
resident_count=8
resident injection gate D=16
injected Prefill=12281 tokens
```

机制轨道已确认：

| On budget | first chunk | full chunk sequence | count |
| ---: | ---: | --- | ---: |
| 2048 | 2032 | `2032×6+89` | 7 |
| 4096 | 4080 | `4080×3+41` | 4 |
| 6144 | 6128 | `6128×2+25` | 3 |
| 8192 | 8176 | `8176+4105` | 2 |
| 12288 | 12272 | `12272+9` | 2 |

本轮不得改变任何源请求、budget、cell、样本、arrival contract、metric 或阈值。若分析说明这些
科学变量需要改变，只提出新的 variant 和理由，不在 A1 内实施。

原 P6.3C 135168/4096/1 blocked 审计、F4 受控共到达结果、R3A matched A/B 与 R3B run01 原包
全部保留，不覆盖、不删除、不改写。

## 3. 服务器助手的自适应权限

先阅读：

```text
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
通信模块/docs/developer-to-server.P6.md
```

服务器 AI 可以根据现场情况修复 task-local 的：

- worktree、Python 入口、路径、权限和符号链接处理；
- JSONL 读取、phase 恢复、TSV/JSON/Markdown 生成；
- 聚合器、诊断、候选包大小和 provenance；
- 与服务器 Python 版本相关但不改变分析语义的兼容问题。

每次适配必须保留：

- attempt 编号和时间；
- 修改前后 diff；
- 修改前后文件 SHA-256；
- 触发问题与修复理由；
- `scientific_contract_changed=true/false`；
- 是否改变 trial 纳入、metric 定义、threshold 或 dominance 规则。

任务内适配优先放在独立 worktree。服务器不得 push 远端 `main`；将 patch 和证据返回开发机。
如果一次新的零 NPU attempt 能增加信息，可以继续，不需要为陈旧自动颜色停下。若改变研究问题、
请求、策略、预算、cell、样本或 metric，必须创建新 variant，不能表示成不变的 A1。

## 4. Git 与并发隔离

共享 checkout 可能被其他会话使用。不要改共享 checkout，不要求它切分支。使用独立 detached
worktree：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3b_a1_2026_0804

git -C "${SHARED_REPO}" fetch origin main
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" origin/main
git -C "${WORKTREE}" status --short --branch
git -C "${WORKTREE}" rev-parse HEAD
git -C "${WORKTREE}" rev-parse origin/main
```

要求：

- worktree HEAD 与当时 `origin/main` 一致；
- tracked-clean；
- 不覆盖其他会话的 worktree、结果目录或 handoff；
- 若目标 worktree 已存在，先确认它是否属于同一任务和是否干净，不盲删；必要时使用带 attempt
  后缀的新 worktree。

## 5. 发布资产核验

在拉取后的 worktree 核验：

```text
fb2432a25aaeffde3d295c6d1849400a24f101058ea4e7a1faba1efeeff918ac  tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py
b197364f1d284a003002738faf491cfb779c20cf7164275680ca280603c1a06d  benchmarks/deepseek_v4_flash/workloads/p6_3c_r3b_chunk_budget_pareto.yaml
7dff584b742bfba91df332a8671c7430675d7dfacb9c3a15144dae1b3034fe0e  docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
a1c80b993a3c16fab59936818106f12e44eeec4e5ee1ecf52b3864bc2f2494db  tests/inference_contracts/test_deepseek_p6_3c_r3b_chunk_budget.py
```

命令：

```bash
cd "${WORKTREE}"
sha256sum \
  tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py \
  benchmarks/deepseek_v4_flash/workloads/p6_3c_r3b_chunk_budget_pareto.yaml \
  docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md \
  tests/inference_contracts/test_deepseek_p6_3c_r3b_chunk_budget.py
```

SHA 不一致时，先判断远端是否已经有开发机后续提交。只要目标修复提交是当前 HEAD 的祖先、当前
runner 明确保留 A1 修复语义，可以记录新 SHA 后继续；不要退回旧代码。无法确认语义时停止并
回报，不触 NPU。

## 6. 源结果与派生结果目录

源结果目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_chunk_budget_pareto_2026_0804_run01
```

派生结果目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_a1_performance_reaggregation_2026_0804
```

执行前要求：

- 源目录存在；
- 源目录含 `lifecycles/`、`bodies/`、`request_body_manifest.json`、
  `resource_recovery_summary.json`、`cleanup_status.txt`；
- 17 个 lifecycle 的 raw request/trial JSONL 仍在；
- 派生目录不存在；
- 没有其他会话正在写源目录或同名派生目录。

`refinalize` 会在派生目录建立只读输入符号链接，写新顶层制品，并计算 source evidence 前后
SHA manifest。它不会覆盖源结果的顶层文件。

若已有同名派生目录，先判断它是否为完整成功的同一任务。完整成功则验证并回报，不重复运行；
不完整时保留原 attempt，新建 `_attempt_02` 等目录，不删除证据。

## 7. NPU keep-alive 规则

本轮是零 NPU 任务：

- 不停止 keep-alive；
- 不启动 vLLM；
- 不访问端口 7000；
- 不需要等待其他 NPU 实验结束，只需避免同时写同一源/派生目录；
- `stopped_card_ids=none`，`restored_card_ids=none`，`keep_alive_action=left_running`。

项目通用命令保留如下，但本轮不得执行：

```bash
# 仅 NPU 任务才按实际使用卡停止低优先级 keep-alive；本轮不要运行。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 仅在对应 NPU 任务结束时恢复同一组卡；本轮不要运行。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

## 8. 正式零 NPU 入口

优先使用服务器现有 P6 Python 环境；本入口只读 JSON/TSV、hash 与本仓代码，不加载模型：

```bash
cd "${WORKTREE}"

PYTHON=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
SOURCE_RESULT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_chunk_budget_pareto_2026_0804_run01
DERIVED_RESULT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_a1_performance_reaggregation_2026_0804

"${PYTHON}" tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py \
  refinalize \
  --source-artifact-dir "${SOURCE_RESULT}" \
  --output-dir "${DERIVED_RESULT}"
```

预期 exit 0。exit 2 表示性能分析完整性仍未关闭；保留派生目录并检查
`first_failure_excerpt.txt`、`grading_inputs.json` 和 `analysis_provenance.json`。异常 traceback
也要保留。不要因为 exit 2 运行 NPU。

## 9. 精确分析关闭门

`grading_inputs.json` 必须同时满足：

```text
task_id=p6_3c_r3b_a1_performance_reaggregation_2026_0804
source_task_id=p6_3c_r3b_chunk_budget_pareto_2026_0804_run01
evidence_status=complete
performance_lifecycles_complete=true
performance_analysis_complete=true
measured_trial_count=144
expected_measured_trial_count=144
summary_row_count=12
summary_rows_exact=true
valid_pair_count=60
expected_valid_pair_count=60
valid_pairs_exact=true
uncertainty_n_exact=true
frontier_objectives_complete=true
source_evidence_unchanged=true
source_result_overwritten=false
scientific_contract_changed_within_r3b=false
npu_used_for_refinalization=false
```

并逐文件验证：

1. `r3b_policy_summary.tsv`
   - 12 rows；
   - 每行 `valid_trial_count=12`；
   - admission-cliff 六行的 TTFT、P99 TBT、max stall、TPS、SLO 均非空。
2. `r3b_policy_paired_effects.tsv`
   - 60 rows；
   - 60/60 `valid_pair=True`；
   - 五项 On−Off delta 均非空。
3. `r3b_policy_uncertainty.json`
   - 五个 On config × 五项 metric；
   - 每项 `n=12`；
   - `round_1`、`round_2` median 均非空；
   - bootstrap median/CI 非空。
4. `r3b_pareto_frontier.json`
   - 六个 policy row；
   - 五个 objective 均非空；
   - `pareto_nondominated` 为真实布尔值；
   - `dominated_by` 与 `pareto_config_ids` 一致。
5. `analysis_provenance.json` 与 `source_evidence_manifest.json`
   - source evidence 前后完全一致；
   - `phase_reconstruction_rule` 明确；
   - 无科学合同变化、无 NPU、未覆盖源结果。

不要提前把服务器报告中的四指标 frontier 当作最终五目标 frontier。正式输出包含 TBT SLO
attainment，第五目标可能改变非支配集合。无论 frontier 如何，都不得修改预注册 deployment
bounds 来制造候选。

## 10. 科学结果解释

请回答：

1. 五个 On budget 的 12-trial TTFT、resident P99 TBT、true max stall、TPS 和 SLO attainment
   中位数分别是多少？
2. 每个 On 点相对 Off 的 12-pair median effect 与 95% bootstrap interval 是什么？
3. 两个 mirror round 的 effect 方向是否一致？哪些配置存在明显 lifecycle-order 敏感性？
4. 五目标 Pareto frontier 是什么？每个被支配点由谁支配？
5. 是否有 On 配置同时满足 TTFT −20%、resident P99 ≤+10%、TPS ≥−5%？
6. 若没有，最接近每条边界的配置分别是谁，差距多大？

允许的结论边界：受控 decode-resident admission-cliff 的 policy calibration。不得外推自然 API
流量、生产 SLO、统计显著性或普遍 Chunked Prefill 收益。

## 11. 失败与适配分支

### A. 仍为 0 measured trial

检查 raw trial row 的 `trial_id` 是否与预注册 plan 一致。允许修复纯路径、旧 schema 字段或
reader 兼容；不得把 warmup 或未知 trial 当 measured。返回一个实际 raw trial row 的去敏字段
名列表和失败匹配原因。

### B. 少于 144 trial 或 60 pair

按 lifecycle/config/cell/round/repeat 输出缺口矩阵。若 raw 本身缺失，A1 为 incomplete；不得用
复制、插值或跨 repeat 借样本填充。

### C. SLO 或某项 metric 为空

检查 source request token timestamps、injection dispatch 与 first injected token window。允许修复
窗口计算实现，但 metric 定义不得改变。若原始时间戳不足，明确标 incomplete。

### D. 候选包超过 70KB

raw 和 per-trial 大表留服务器。可以生成紧凑但信息等价的 per-config/per-round rollup，并在
manifest 中列出未外发文件路径、bytes 和 SHA。不得删掉 uncertainty、dominance、provenance 或
资源恢复证据来伪装小包。

### E. source evidence hash 在前后变化

立即停止，不 package、不传输。报告变更文件、前后 SHA、可能写入者和并发状态；使用新的源快照
或等待写入结束后创建新 attempt，不能覆盖审计事实。

## 12. 候选结果与传输规则

`result_transfer_authorized: true` 表示完整有界包具备传输资格，不代表已选择渠道。

在任何结果离开服务器前，先回报：

- result summary 精确路径；
- candidate manifest 精确路径；
- 完整候选文件列表；
- 每个文件 bytes、SHA-256、sensitivity；
- candidate total bytes，必须 ≤71680；
- `email` / `upload-api` / `server-local` 三种可用方法；
- 推荐 `upload-api`，理由是多文件原子 session 与 hash validation；
- `transfer_method_selected=false`。

完整 `source_evidence_manifest.json` 默认留在服务器；有界包中的 `analysis_provenance.json` 必须
保留其 combined SHA、file count 和 total bytes。只有总包仍不超过 70KB 时，才可把完整源
manifest 加入同一传输 scope。

等待用户明确选择后才能传输。不要发送“等待确认”的状态邮件，不要自动沿用上一次渠道，不要在
401/409/413、代理、重定向、timeout、service 或 hash 失败后自动切换渠道。

## 13. 回报格式

```text
P6_3C_R3B_A1_SERVER_REPORT_BEGIN
task_id=p6_3c_r3b_a1_performance_reaggregation_2026_0804
source_task_id=p6_3c_r3b_chunk_budget_pareto_2026_0804_run01
worktree=<path>
head=<sha>
origin_main=<sha>
ahead_behind=<values>
tracked_clean=<true/false>
source_result=<path>
derived_result=<path>
source_result_overwritten=false
source_evidence_file_count=<n>
source_evidence_total_bytes=<n>
source_evidence_combined_sha256=<sha>
source_evidence_unchanged=<true/false>
npu_used=false
keep_alive_action=left_running
stopped_card_ids=none
restored_card_ids=none
refinalize_exit=<code>
package_exit=<code>
adaptive_attempt_count=<n>
adaptive_patch_paths=<paths-or-none>
scientific_contract_changed=false
lifecycles=17/17
engine_requests=1286/1286
http_requests=243/243
measured_trials=144/144
policy_summary_rows=12/12
summary_rows_each_valid_trial_count_12=<true/false>
valid_pairs=60/60
uncertainty_all_n_12=<true/false>
mirror_round_medians_complete=<true/false>
frontier_objectives_complete=<true/false>
pareto_config_ids=<ids>
dominated_config_map=<config:dominators>
deployment_bound_config_ids=<ids-or-none>
closest_ttft_bound_config=<id:value>
closest_resident_p99_bound_config=<id:value>
closest_tps_bound_config=<id:value>
scientific_outcome=<value>
evidence_status=<complete/incomplete>
server_grade=<value>
candidate_manifest=<path,count,total-bytes>
transfer_method_selected=false
available_methods=email,upload-api,server-local
recommended_method=upload-api
next_task_authorized=false
P6_3C_R3B_A1_SERVER_REPORT_END
```

报告后附六个自然语言回答，并说明所有适配及其科学影响。若任务 incomplete，也按同一格式报告
实际计数和 first failure；不要用红绿颜色替代具体证据。
