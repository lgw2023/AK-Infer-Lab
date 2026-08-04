# 开发机 → Ascend 服务器：P6.3C-R3A 代价复分析 + R3B Chunk-budget Pareto 实验

更新日期：2026-08-04

主任务 ID：`p6_3c_r3b_chunk_budget_pareto_2026_0804_run01`

零 NPU 派生任务 ID：`p6_3c_r3a_cost_reanalysis_2026_0804`

状态：已授权。先在独立 worktree 中完成 R3A raw evidence 的零 NPU 只读复分析；随后只有在
NPU 0–7 全局无冲突时执行 R3B。不要自动进入 R3C、P7、P8 或其他任务。

## 1. 本轮真正要完成的研究任务

R3A 已经得到完整且有价值的结果，不需要重跑：

```text
mechanism: confirmed
injected admission-cliff TTFT: 5802.8 ms Off -> 1292.6 ms On (-77.7%)
resident interference P99 TBT: 91.7 ms Off -> 719.4 ms On (+684%)
aggregate output TPS: 129.6 Off -> 118.7 On (-8.5%)
scientific outcome: mechanism_confirmed_tradeoff_only
```

其机制解释很清楚。八个 resident Decode 在首个相关 step 共占用 `D=16` token，
`B=12288` 时剩余 `R=12272`。12281-token Prefill 在 Off 无法整段准入，首步 scheduled=0；
On 则立即调度 12272-token partial chunk。这个近乎占满 batch 的大 chunk 消除了长请求的
admission starvation，却让 resident Decode 经历一个很长的 mixed compute step。

R3B 不再问“Chunked Prefill 是否生效”，而是问：

> 缩小 On 侧 `max_num_batched_tokens` 后，能否保留实用的 injected TTFT 收益，同时把
> resident Decode 尾 TBT 和吞吐代价控制在可接受范围？

本轮分为两个有信息增益的步骤：

1. 零 NPU 原地读取 R3A 服务器 raw JSONL，重建真实相邻 token gap、干扰窗口
   P50/P95/P99/max、pre/post inflation、paired cost effect 和两个 fresh-model pair 的方向；
2. 执行新的 R3B policy comparison：一个 contemporaneous Off baseline 与五档 On budget，
   先校准实际 chunk，再测量 TTFT–TBT–throughput Pareto frontier。

## 2. 不能覆盖的结论 lineage

以下事实全部保留：

- 原 `135168/4096/1` 参考配置仍为
  `blocked_p6_3c_not_strict_single_variable`；
- F4/A1 仍是 `12288/12288/2` atomic co-arrival 下的机制证据；
- R3A 仍是 `12288/12288/9`、Off/On 只差一个开关的 matched A/B，accepted outcome 为
  `mechanism_confirmed_tradeoff_only`；
- R3B 是新 policy variant，不是 strict single-variable A/B，也不得把小预算 On 与 Off 的差异
  表述为单一 boolean 因果效应；
- R3B 完成后也不能声明自然 API 流量、生产 SLO 或普遍 Chunked Prefill 收益。

R3A 的开关因果作用和 R3B 的策略调优作用必须在报告中分开。

## 3. 开发机已经提供的实现

核心资产和 SHA-256：

```text
b197364f1d284a003002738faf491cfb779c20cf7164275680ca280603c1a06d  benchmarks/deepseek_v4_flash/workloads/p6_3c_r3b_chunk_budget_pareto.yaml
3292defe09d124a4bf9e962292791a6b383e3fe49b91f52c94b05f84ae6d58b8  tools/inference_contracts/analyze_deepseek_p6_3c_r3a_costs.py
3cc372c28681b786ceb65b62830375f584386d51486ec4425147b12f5bab6e0e  tools/inference_contracts/p6_3c_r3_decode_resident_observer.py
215315da2414a52004d84214a9a692eb4689f56a806e7257beee78e2d0bdf10b  tools/inference_contracts/run_deepseek_p6_3c_r3a_decode_resident.py
ce34eb55aee093e2959d9a4d661c332d3eef2be8b1ea6cd34a684de83476927a  tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py
26d66b42229888046ab7a9ca85e4222151862f40b5f7eb06909efbb3c6de16b4  tools/inference_contracts/run_deepseek_p6_3c_r3b_mode.sh
a94918858f233a25c45f0e9233b2a1432034aee9fb8c26c4884923993d56969d  tools/inference_contracts/run_deepseek_p6_3c_r3b_experiment.sh
c7d76e554b99f28d4fcd1c2d97312ee805d070c6e49c9cea353b572fecf7502e  tools/inference_contracts/run_deepseek_p6_3c_r3b_server_task.sh
```

实现的实质能力：

- R3A cost analyzer 直接读取 server-local raw timestamp，不启动 vLLM/NPU，不修改源结果；
- future-run `resident_max_stall_ms` 已改为真实 maximum adjacent-token gap，不再误用
  `max(per-request ITL p99)`；
- R3B driver 复用已验证 staged-arrival transport，但只保留 resident-only 和
  admission-cliff 两个有信息量的 cell；
- 五个 observer mechanism lifecycle 分别校准 On budget；
- 十二个 performance lifecycle 使用升序—降序镜像，observer/profiler 均关闭；
- finalizer 输出真实 max stall、P99 TBT、TBT SLO attainment、TPS、paired bootstrap、两个
  mirror-round 中位效应、deployment bound 和非支配配置；
- 自动分类只表示 evidence completeness，不能覆盖 effect size 和 scientific outcome。

旧 R3A 成功执行时的 runner SHA 是 `2bbc6e6e...`；当前 tracked R3A runner SHA 因修正 future
maximum-stall 定义而变化。不要把这一变化误报为旧 R3A 来源不一致。R3A 复分析必须读取旧 raw
timestamp，并在 provenance 中明确“源执行不变、分析定义修正”。

## 4. R3B 科学合同

### 4.1 固定系统配置

所有 policy 共同：

```text
model=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
served_model_name=deepseek-v4-flash-w8a8-mtp
vLLM=0.22.1+empty
vLLM-Ascend=0.22.1rc1
quantization=ascend
TP=8
EP=true
MTP num_speculative_tokens=1
cudagraph_mode=FULL_DECODE_ONLY
block_size=128
async_scheduling=true
Prefix Cache=false
max_model_len=12288
max_num_seqs=9
profiler=disabled
request_retry_count=0
```

策略集合：

| config ID | Chunked Prefill | `max_num_batched_tokens` | 角色 |
| --- | --- | ---: | --- |
| `off_b12288` | Off | 12288 | 合法 contemporaneous baseline |
| `on_b2048` | On | 2048 | 小 chunk 候选 |
| `on_b4096` | On | 4096 | 候选 |
| `on_b6144` | On | 6144 | 候选 |
| `on_b8192` | On | 8192 | 候选 |
| `on_b12288` | On | 12288 | R3A policy anchor |

Off 必须保持 `B>=L` 才能启动，因此 R3B 的小预算比较有意改变完整 policy，不是单变量 A/B。

### 4.2 请求与到达

每个 measured trial：

```text
resident cohort = 8 requests x (256 input + 128 forced output)
injection gate = every resident has streamed >=16 output tokens
injected request = 12281 input + 4 forced output
temperature=0
ignore_eos=true
generated text/token ID not retained
token arrival monotonic_ns retained server-local
```

性能轨道每 lifecycle 的 cell 顺序为：

```text
resident, cliff, cliff, resident,
resident, cliff, cliff, resident,
resident, cliff, cliff, resident
```

因此每 lifecycle 每 cell 六个 trial；每 config 通过两个镜像 lifecycle 得到每 cell 12 个 trial。

### 4.3 生命周期与规模

机制顺序：

```text
mechanism_01 on_b2048
mechanism_02 on_b4096
mechanism_03 on_b6144
mechanism_04 on_b8192
mechanism_05 on_b12288
```

性能镜像顺序：

```text
performance_01 off_b12288
performance_02 on_b2048
performance_03 on_b4096
performance_04 on_b6144
performance_05 on_b8192
performance_06 on_b12288
performance_07 on_b12288
performance_08 on_b8192
performance_09 on_b6144
performance_10 on_b4096
performance_11 on_b2048
performance_12 off_b12288
```

总量：

```text
fresh-model lifecycle=17
mechanism lifecycle=5
performance lifecycle=12
engine request including warmup=1286
local HTTP request including warmup=243
retry in published runner=0
```

## 5. 同步 main 与隔离其他会话

共享 checkout 只用于 fetch、环境和旧 raw result 定位。不要在共享 checkout 中 pull、checkout、
edit tracked file、`update-index --skip-worktree` 或删除其他会话的 lock。

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3b_2026_0804

cd "${SHARED_REPO}"
git fetch origin main
git rev-parse origin/main
git status --short --branch

mkdir -p /data/node0_disk1/liguowei/server_worktrees
git worktree add --detach "${TASK_WORKTREE}" origin/main
cd "${TASK_WORKTREE}"
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --short --branch
```

要求 worktree `HEAD=origin/main`、ahead/behind `0 0`、tracked-clean。若该路径已存在，不要删除；
确认归本任务且 HEAD 正确后复用，或选择一个带时间后缀的新 worktree。

核验第 3 节八项 SHA。若 `origin/main` 包含更新的开发机修复，先审查 diff 和科学影响；不能为了
匹配旧 SHA 值回退正确代码。task-local 适配按第 10 节记录。

## 6. 第一步：R3A 零 NPU 代价复分析

源结果：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01
```

派生结果：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3a_cost_reanalysis_2026_0804
```

这一步不需要 NPU，必须让 keep-alive 继续运行，不启动/停止 vLLM，不修改源目录。即使其他会话
正在运行 NPU，这个只读分析也可以在独立 worktree 中执行，但避免争用其结果目录。

先验证：

```bash
cd "${TASK_WORKTREE}"
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python \
  tools/inference_contracts/analyze_deepseek_p6_3c_r3a_costs.py \
  --source-result /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01 \
  --validate-only
```

应确认 R3A task ID、complete evidence、mechanism、四个 performance lifecycle 各
`19 trial rows / 157 request rows` 和 cleanup。通过后运行：

```bash
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python \
  tools/inference_contracts/analyze_deepseek_p6_3c_r3a_costs.py \
  --source-result /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01 \
  --output-dir /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3a_cost_reanalysis_2026_0804
```

若派生目录已经存在：不要覆盖或删除。先核 `analysis_provenance.json`、五个 candidate 文件和
manifest；若完整则直接复用，若是本任务留下的不完整目录则创建带 `attempt_02` 后缀的新派生目录。

必须在自然语言报告中回答：

1. R3A 的 resident interference P50/P95/P99/true max stall 是多少？
2. 两个 fresh-model pair 的 On−Off cost effect 是否同方向？
3. pre/interference/recovery window 的 inflation 有多大，是否由少数 resident 或少数 trial 主导？
4. 修正 true max stall 后，R3A 的 trade-off 解释是否变化？

这一步的 trial-pair bootstrap 是描述性统计，因为每组六个 trial 共享一个 fresh-model lifecycle；
不得写成 12 个完全独立 replicate 的显著性结论。

## 7. 第二步前的零 NPU R3B 审计

在停止 keep-alive 前执行：

```bash
cd "${TASK_WORKTREE}"
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
REPO_ROOT="${TASK_WORKTREE}" \
P6_3C_SHARED_REPO_ROOT="${SHARED_REPO}" \
bash tools/inference_contracts/run_deepseek_p6_3c_r3b_server_task.sh \
  /audit/p6_3c_r3b
```

审计必须显示：

```text
formal_model_lifecycle_count_exact=17
engine_request_count_exact=1286
http_request_count_exact=243
capacity_contract=max_model_len_12288,max_num_seqs_9,off_budget_12288,on_budgets_2048_4096_6144_8192_12288
performance_order=ascending_then_descending_mirror
performance_trials_per_config_cell=12
comparison_type=policy_pareto_not_strict_single_variable_ab
observer=enabled only for five mechanism lifecycles
profiler=disabled
result_transfer_authorized=true
```

Canonical argv SHA-256：

```text
off_b12288  4ea039e53ba37d52831b4593e9f59d327315b1002865792c3ed68e988123f60b
on_b2048    833d130a5ab318d0de79a671855633db478d6287ff772f49ef2f3152cf8970fd
on_b4096    c7b8a2b333fdd19b105b9754d1af43c170c0cc012f8c3e3f414d7cc877ddcc1f
on_b6144    ce31614f5a203024c3ec6d6d0330779cf12615cf3d09988142e3344afaa947d8
on_b8192    921ff53171a2ab4327b9a82e40995ffaecb792bc9a584abc0e766bd9c92ff83a
on_b12288   77e75a811ffa49224a6e1d534a10e4663fa7c21436fa053a76cc967ce4668d73
```

这些 SHA 只标识 server argv；mechanism/performance 同一 policy 的 argv 相同，因为 observer 是
task-local overlay，不是 vLLM CLI 参数。审计不得触发 NPU、停止 keep-alive、启动 vLLM 或创建
正式 R3B 结果目录。

## 8. 全局 NPU 互斥与正式运行

R3B 使用 NPU 0–7。正式运行前确认：

- NPU 0–7 全部健康且无其他有效 workload；
- 无其他会话正在或即将使用 NPU 0–7；
- 无其他会话正在操作同一 keep-alive 卡集；
- 端口 7000 无 listener；
- 无 DeepSeek-V4-Flash vLLM 残留；
- 正式结果目录不存在。

若通用 K2 或其他八卡任务正在运行，本任务等待，不终止、抢占或修改对方进程。只读 R3A 分析完成
不等于已获得八卡运行权。

正式结果目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_chunk_budget_pareto_2026_0804_run01
```

唯一首次正式入口：

```bash
cd "${TASK_WORKTREE}"
REPO_ROOT="${TASK_WORKTREE}" \
P6_3C_SHARED_REPO_ROOT="${SHARED_REPO}" \
bash tools/inference_contracts/run_deepseek_p6_3c_r3b_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_chunk_budget_pareto_2026_0804_run01
```

不要手工预启动 vLLM。入口会解析真实 editable vLLM/site-packages vLLM-Ascend，创建 task-local
overlay，沿用已验证的 MTP/hybrid-KV repair 和 direct-loopback proxy isolation。

## 9. Keep-alive 与资源恢复

首次正式入口需要停止 NPU 0–7 的低优先级 keep-alive：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

published server task 已在 success、failure、interrupt、early exit 路径恢复完全相同卡集。若服务器
AI 写 task-local resume wrapper，也必须保证每次 attempt 都在所有退出路径恢复 0–7，并报告：

```text
stopped_card_ids=0,1,2,3,4,5,6,7
restored_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_count=16
keep_alive_restored_exact=true
port_7000_listener_count=0
vllm_residual_process_count=0
```

资源恢复失败时，优先恢复资源并保留 evidence；不得为了继续实验忽略残留进程或 keep-alive 缺卡。

## 10. 服务器 AI 的自适应权限与 17-lifecycle 断点策略

先读：

```text
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
```

服务器 AI 可以在独立 worktree、result-local code copy 或 task-local overlay 中修复和重试：

- vLLM/vLLM-Ascend 安装布局、Python/Bash、权限和路径；
- loopback proxy、health/metrics、stream parser、warmup 和 timeout；
- observer 字段解析、finalizer、manifest、cleanup 和报告；
- 不改变 policy/request/metric 的控制面错误；
- 某个 lifecycle 完成后的后续 lifecycle 中断。

R3B 有 17 次模型加载。若中途发生控制面失败，不要删除完整的前序 lifecycle，也不要机械从
`mechanism_01` 重跑。允许创建 task-local resume wrapper：

1. 核验已完成 lifecycle 的 request/trial count、resolved config、cleanup、argv 和 raw SHA；
2. 保留原 `executed_lifecycle_schedule.tsv` 和 attempt history；
3. 从第一个 missing/incomplete lifecycle 继续；
4. 每个 fresh model 仍只服务其预注册 config；
5. 最终 finalizer 同时消费所有完成 lifecycle；
6. 报告每个 lifecycle 来自哪个 attempt。

成功 lifecycle 不能因后续失败被抹除；失败 attempt 也不能从 provenance 删除。每次 adaptation 保存：

```text
server_local/adaptations/attempt_XX/reason.md
server_local/adaptations/attempt_XX/command.sh
server_local/adaptations/attempt_XX/stdout_stderr.tail.txt
server_local/adaptations/attempt_XX/exit_code.txt
server_local/adaptations/attempt_XX/change.patch
server_local/adaptations/attempt_XX/before_after_sha256.tsv
server_local/adaptations/attempt_XX/scientific_impact.json
server_local/adaptations/attempt_XX/lifecycle_provenance.tsv
```

以下变化必须使用新的 variant/task ID，不能在本 run01 内静默修改：

- 六个 policy config 或任何 budget；
- `max_model_len=12288` 或 `max_num_seqs=9`；
- resident 数量、input/output token；
- 16-token injection gate；
- 12281-token injected Prompt 或 4-token output；
- resident-only/admission-cliff cell；
- 每 config-cell 12 个有效 trial；
- TTFT、TBT、true max stall、TPS、SLO 或 Pareto metric 定义。

若真实运行说明某个科学变量应改变，提出 `P6.3C-R3B-V2`：说明实际证据、精确 delta、信息增益
与资源成本，等待开发机授权。服务器不得推送远端 `main`；有效 patch 返回开发机审核。

## 11. 机制门与性能解释

五个 On mechanism lifecycle 必须分别证明：

```text
resident_running_count_first_step=8
resident_decode_tokens_first_step=D>0
trace token_budget=policy B
first injected chunk=min(12281,B-D)
first injected chunk is partial
first step is mixed Decode+Prefill
sum(observed Prefill chunks)=12281
preemption_count=0
```

五档全过后才进入性能轨道。若一个 budget 的观察缺字段，可以修 observer/finalizer 并只重跑该
mechanism lifecycle；若真实 scheduler 行为不满足合同，保留 trace 并停止性能，不为过门修改
workload。

性能主表至少给出每个 config 的：

- injected TTFT median/P95；
- injected E2EL；
- resident interference P50/P95/P99 TBT；
- true maximum adjacent-token stall；
- resident-only 与 interference 的 TBT SLO attainment；
- aggregate output TPS；
- 两个 mirror-round 的分别中位 effect；
- 12 个 paired trial 的描述性 bootstrap interval；
- chunk count、首个 chunk 和 preemption。

Pareto objective：

```text
minimize TTFT
minimize resident P99 TBT
minimize true max stall
maximize aggregate TPS
maximize resident TBT SLO attainment
```

项目部署边界相对 contemporaneous Off：

```text
injected TTFT reduction >=20%
resident P99 TBT increase <=10%
aggregate TPS decrease <=5%
```

若没有 On config 同时满足边界，科学 outcome 应为
`pareto_frontier_observed_no_candidate_within_bounds`。这仍是有效结果，不改阈值、不改 grade
制造候选。若存在候选，也只输出候选集，不自动进入 R3C。

## 12. 结果目录、候选包与传输

R3A cost analysis 会生成自己的 `candidate_manifest.server_local.json`；R3B finalizer 也会生成
独立 manifest。raw token timestamp、scheduler trace、server log、metrics 和完整实验目录均留在
服务器。

每个 manifest 必须列出完整候选集合：

```text
path
bytes
sha256
sensitivity
candidate_file_count
candidate_total_bytes
candidate_total_within_limit
```

每个 outbound body/attachment 总量不超过 70KB。`result_transfer_authorized:true` 表示小包符合
传输资格，不代表已选渠道。完成后先报告两个 manifest 的完整路径、候选清单、总 bytes、SHA、
敏感性，以及：

```text
available_methods=email,upload-api,server-local
recommended_method=upload-api
transfer_method_selected=false
```

等待用户对每个完整 scope 明确选择后再传输。不要沿用之前 A1/R3A 的 upload-api 选择；不要先发
status-only email；401/409/413、代理、redirect、timeout、service 或 hash failure 后也不得自动
切换方法。

## 13. 必须回报的结构

```text
P6_3C_R3B_SERVER_REPORT_BEGIN
task_id=p6_3c_r3b_chunk_budget_pareto_2026_0804_run01
worktree=<path>
head=<HEAD>
origin_main=<origin/main>
ahead_behind=<0 0>
shared_checkout_modified=<true/false>
r3a_cost_source=<path>
r3a_cost_validate_only_exit=<exit>
r3a_cost_analysis_exit=<exit>
r3a_cost_true_max_stall_summary=<key values>
r3a_cost_pair_direction_consistent=<true/false + pair medians>
npu_conflict_check=<passed/waited + evidence>
r3b_audit_only_exit=<exit>
formal_experiment_started=<true/false>
attempt_count=<count>
lifecycle_resume_used=<true/false>
stopped_card_ids=<actual>
restored_card_ids=<actual>
keep_alive_restored_exact=<true/false>
lifecycles=<x/17>
mechanism_lifecycles=<x/5>
performance_lifecycles=<x/12>
engine_requests=<x/1286>
http_requests=<x/243>
retries=<published request retries; adaptation attempts separately>
mechanism_all_budgets_complete=<true/false>
budget_2048_first_chunk_and_count=<values>
budget_4096_first_chunk_and_count=<values>
budget_6144_first_chunk_and_count=<values>
budget_8192_first_chunk_and_count=<values>
budget_12288_first_chunk_and_count=<values>
preemption_count=<count>
performance_complete=<true/false>
off_baseline_metrics=<TTFT,TBT,max stall,TPS,SLO>
on_2048_metrics=<same>
on_4096_metrics=<same>
on_6144_metrics=<same>
on_8192_metrics=<same>
on_12288_metrics=<same>
mirror_round_consistency=<per-config summary>
pareto_config_ids=<list>
deployment_bound_config_ids=<list>
scientific_outcome=<outcome>
scientific_contract_changed_from_r3a=true
scientific_contract_changed_within_r3b=<true/false>
adaptive_attempt_count=<count>
adaptive_patch_paths=<none/paths>
evidence_status=<complete/incomplete>
cleanup_status=<clean/incomplete>
port_7000_listener_count=<count>
vllm_residual_process_count=<count>
r3a_cost_candidate_manifest=<path,count,bytes>
r3b_candidate_manifest=<path,count,bytes>
transfer_method_selected=false
available_methods=email,upload-api,server-local
recommended_method=<method + reason>
next_task_authorized=false
P6_3C_R3B_SERVER_REPORT_END
```

最后用自然语言回答四个问题：

1. R3A 的真实 maximum stall 与两个 lifecycle-pair 的代价方向是什么？
2. 缩小 budget 后，实际 first chunk/chunk count 是否按机制预期变化？
3. 哪些 On 配置位于 Pareto frontier，哪些被其他配置支配？
4. 是否有配置同时保留至少 20% TTFT 收益，并满足 resident P99 TBT 与 TPS 代价边界？

完成后停止。不要自动运行 R3C 或任何其他项目任务。
