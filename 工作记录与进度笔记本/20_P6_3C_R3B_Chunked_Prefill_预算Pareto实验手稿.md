# P6.3C-R3B：Decode 驻留条件下 Chunked Prefill 预算—时延 Pareto 实验

日期：2026-08-04

状态：`execution_and_mechanism_complete / performance_reaggregation_required`

## 摘要

P6.3C-R3A 证明了 Chunked Prefill 能消除一个明确的 admission cliff：当八个 resident
Decode 已占用 16 个 scheduler token、12281-token 新 Prefill 无法完整装入剩余 12272-token
预算时，Off 侧将新请求留在 waiting，On 侧则立即 partial admit 12272 tokens。该机制使新请求
TTFT 大幅下降，却同时放大 resident Decode 的尾延迟。R3B 进一步研究这一收益—代价关系是否可
通过 `max_num_batched_tokens` 调节，而不是继续重复“机制是否存在”的问题。

实验在同一 DeepSeek-V4-Flash W8A8-MTP、TP8+EP、Prefix Cache off、`max_model_len=12288`、
`max_num_seqs=9` 和受控 staged arrival 下，比较一个合法 Off 基线 `B=12288` 与五个 On 策略
`B∈{2048,4096,6144,8192,12288}`。17 个 fresh-model lifecycle 全部完成，获得 1286/1286
engine requests、243/243 local HTTP requests、零 retry，并精确恢复 NPU 0–7 keep-alive。

机制轨道给出清晰、单调的预算响应：首个 injected chunk 始终等于 `B-D`，即 2032、4080、
6128、8176 和 12272 tokens；完整 12281-token Prefill 分别需要 7、4、3、2 和 2 个 chunk，
全程未观察到 preemption。服务器对 raw 结果的直接读数显示，所有 On 策略均显著缩短 injected
TTFT，但 resident P99 TBT 和 maximum stall 明显恶化，且吞吐下降；没有配置同时满足预注册的
TTFT、resident P99 TBT 与 throughput 三项部署边界。

本轮同时发现：原 finalizer 因 measured trial summary 缺少 `phase` 字段，将 144 个有效性能
trial 全部过滤，继而在零有效样本时仍把分析判为 complete。因此 NPU 执行、资源恢复和机制证据
已经闭环，原包中的正式 Pareto 表与 uncertainty 尚不能作为最终论文数值。开发机已修复 trial
识别和 fail-closed 完整性门；下一步只需在服务器读取既有 raw JSONL 做零 NPU 再聚合，无需
重跑 17 个 lifecycle。

## 1. 研究问题

R3B 回答三个彼此关联但不可互相替代的问题：

1. scheduler token budget 是否直接控制长 Prefill 的首个 chunk 与完成轮数；
2. 减小 chunk budget 能否在保留 admission-cliff TTFT 收益的同时，降低 resident Decode 的
   P99 TBT 与 maximum stall；
3. 在 injected TTFT、resident tail latency、aggregate output throughput 和项目内 TBT SLO
   attainment 的联合目标下，是否存在可供后续自然流量实验采用的非支配策略。

R3B 不是 strict single-variable A/B。Off 侧必须满足 `B≥L` 才能启动，因此保持
`B=L=12288`；小预算 On 同时改变 Chunked Prefill 开关与预算，代表完整部署策略。开关本身的
因果作用仍由 R3A 的 `B=12288` matched A/B 提供。

## 2. 实验设置

### 2.1 共同运行环境

- 模型：DeepSeek-V4-Flash W8A8-MTP；
- 并行：TP8 + EP，NPU 0–7；
- runtime：vLLM 0.22.1 / vLLM-Ascend 0.22.1rc1；
- `max_model_len=12288`，`max_num_seqs=9`；
- Prefix Cache 显式关闭；
- MTP、graph、block size、模型、量化、请求体与 staged-arrival 语义保持一致；
- observer 只用于五个 mechanism lifecycle，十二个 performance lifecycle 不安装 observer 或
  profiler。

每个 trial 先启动八个 resident request，每个 resident 使用 256-token 输入并生成 128 tokens。
只有当八个 resident 均已输出至少 16 tokens 后，才注入 12281-token 长 Prefill。这个门控使
注入时的 Decode token 消耗稳定为

\[
D=16,
\]

从而 On 策略首轮可供 Prefill 使用的预算为

\[
R(B)=B-D.
\]

### 2.2 策略与执行顺序

策略集合为：

| 配置 | Chunked Prefill | `max_num_batched_tokens` |
| --- | --- | ---: |
| `off_b12288` | Off | 12288 |
| `on_b2048` | On | 2048 |
| `on_b4096` | On | 4096 |
| `on_b6144` | On | 6144 |
| `on_b8192` | On | 8192 |
| `on_b12288` | On | 12288 |

机制轨道为五个 On budget 各一个 fresh-model lifecycle。性能轨道采用镜像顺序控制模型加载与
时间漂移：

```text
round 1: Off, On-2048, On-4096, On-6144, On-8192, On-12288
round 2: On-12288, On-8192, On-6144, On-4096, On-2048, Off
```

每个性能 lifecycle 包含一次 warmup、六个 resident-only trial 与六个 admission-cliff trial；
每个 config-cell 因而有 12 个有效 trial。完整任务包括 5 个 mechanism 和 12 个 performance
lifecycle。

### 2.3 指标与判据

主要性能指标为 injected TTFT。代价指标为 resident interference-window P99 TBT、真实 maximum
adjacent-token stall 和 aggregate output TPS。项目内 TBT SLO threshold 定义为
`2× Off-B12288 resident-only pooled median TBT`，只用于本项目的相对策略分析，不是外部标准。

预注册部署边界要求 On 策略同时满足：

- injected TTFT 相对 Off 至少改善 20%；
- resident P99 TBT 相对 Off 增幅不超过 10%；
- aggregate output TPS 相对 Off 降幅不超过 5%。

Pareto 分析同时最小化 TTFT、P99 TBT 和 maximum stall，最大化 TPS 与 TBT SLO attainment。

## 3. 执行过程与证据完整性

服务器在独立 worktree、全局 NPU 无冲突条件下运行。第一次分析尝试修正了 R3A cost analyzer
对 warmup phase 的过滤；第二次现场适配为 `acl_graph.py` 增加兼容性 guard，并在退出时恢复
conda 环境文件。两次适配均未改变 R3B 的请求、策略集合、预算、cell、指标或执行顺序。

最终运行得到：

- 17/17 lifecycle exit 0，cleanup 均为 clean；
- 1286/1286 engine requests；
- 243/243 HTTP requests；
- 零 retry；
- 0–7 号卡停止与恢复集合一致，keep-alive 16/16 markers；
- 端口 7000 无残留 listener，vLLM residual process count 为 0；
- 共享 checkout 未修改。

模型启动资源随 budget 改变。`B=12288` 时可用 KV cache 约 15.01 GiB、maximum concurrency
2.29；`B=2048` 时分别约 16.21 GiB 和 13.66。这个变化说明 R3B 比较的是可部署的完整 policy，
不能把性能差异全部解释为 chunk size 的纯单变量作用。

## 4. 机制结果：预算直接决定 chunk 序列

五档机制观测全部满足首轮 eight-resident running、`D=16`、partial+mixed admission、完整
Prefill token sum 和零 preemption：

| On budget | 首个 chunk `B-D` | 完整 chunk 序列 | chunk 数 |
| ---: | ---: | --- | ---: |
| 2048 | 2032 | `2032×6 + 89` | 7 |
| 4096 | 4080 | `4080×3 + 41` | 4 |
| 6144 | 6128 | `6128×2 + 25` | 3 |
| 8192 | 8176 | `8176 + 4105` | 2 |
| 12288 | 12272 | `12272 + 9` | 2 |

这一结果把 R3A 的单点机制扩展为剂量—响应关系：chunk budget 不是仅影响配置显示值，而是精确
改变 scheduler 对 injected Prefill 的首步 token allocation 和完成轮数。它也解释了为什么
`B=12288` 可能带来最大 TTFT 收益和最严重 Decode stall：几乎整个 Prefill 在第一轮与 resident
Decode 混合执行。

## 5. 性能结果：收益与代价形成非单调折中

下表是服务器从 raw JSONL 直接提取并在报告中给出的两个 mirror round 中位数的再汇总，用于
描述方向和量级；正式 trial-pair bootstrap、SLO attainment 与五目标 Pareto 集仍等待修复后的
零 NPU finalizer 生成。

| 配置 | injected TTFT (ms) | aggregate TPS | resident P99 TBT (ms) | max stall (ms) |
| --- | ---: | ---: | ---: | ---: |
| Off B12288 | 5869.5 | 127.865 | 95.385 | 96.670 |
| On B2048 | 3087.0 | 101.815 | 427.220 | 428.205 |
| On B4096 | 1856.0 | 114.065 | 424.600 | 425.260 |
| On B6144 | 1503.0 | 114.355 | 451.470 | 451.995 |
| On B8192 | 1153.0 | 119.890 | 529.275 | 550.880 |
| On B12288 | 1363.5 | 115.050 | 717.975 | 749.325 |

相对 Off，五个 On 策略的 TTFT 改善约为 47%–80%，说明 Chunked Prefill 在 admission cliff
处的收益并不局限于最大 budget。然而所有 On 策略都把 resident P99 TBT 提高到 Off 的数倍；
即使最小 budget 也没有恢复到接近 Off 的 Decode tail latency。TPS 同样全部低于 Off，其中
`on_b8192` 最接近吞吐边界，但两个 mirror round 并非都满足 5% 上限。

四个已报告性能指标下，`on_b4096` 同时优于 `on_b2048`，`on_b8192` 同时优于
`on_b12288`；这两个支配关系较为稳定。但正式实现还包含 TBT SLO attainment 第五目标，原结果
包未成功计算该字段，因此当前不把服务器报告中的四点 frontier 写成最终归档事实。

更重要的是，“没有部署边界内候选”的方向对聚合 bug 不敏感：所有 On 点的 resident P99 TBT
代价都远超 10% 上限。修复再聚合的主要任务是恢复准确 effect size、uncertainty、SLO 和
五目标 dominance，而不是通过改变阈值制造绿色候选。

## 6. R3A 代价复分析

R3B 前的零 NPU R3A raw timestamp 复分析确认，admission-cliff 下真实 maximum adjacent-token
stall 的 On−Off 配对中位差为 +620.12 ms，95% bootstrap interval 为
[+579.68, +660.85] ms。两个 fresh-model pair 分别为 +601.85 和 +624.49 ms；injected TTFT、
resident P99 TBT、maximum stall 与 TPS 四项在两个 pair 中方向一致。该结果保持 R3A 的
`mechanism_confirmed_tradeoff_only` 结论。

## 7. 聚合缺陷、影响范围与修复

R3B measured request row 包含 `phase=measured`，但复用的 R3A `run_staged_trial()` 返回的 measured
trial summary 没有 `phase`。原 finalizer 仅接收 `trial.phase == measured`，因此把 144 个已成功
执行的 measured trial 全部丢弃。随后完整性判定只检查 lifecycle、request、HTTP、启动、配置
与资源恢复，没有要求性能 trial、valid pair 或 uncertainty 非空，最终造成：

- 12 个 policy summary row 的 `valid_trial_count` 全为 0；
- 60 个 Off/On pair 全部 `valid_pair=false`；
- uncertainty 的所有 `n=0`；
- 五个 Pareto objective 全为 null，却把六个配置都标为 nondominated；
- 顶层结果被错误标为 evidence complete。

修复遵循两条原则。第一，未来 raw trial summary 在写盘前显式补入 `phase`。第二，为兼容既有
run01，仅当 phase 缺失且 `trial_id` 精确属于预注册 measured trial plan 时重建
`phase=measured`；warmup 和未知 trial 不会被接收。新的 finalizer 只有在以下条件全部满足时才
允许性能证据 complete：144/144 measured trial、12 个 summary row 各 12 个有效 trial、60/60
有效 pair、每个 On-config × metric 的 uncertainty `n=12` 且两个 mirror round 均有中位值、
六个策略的五个 Pareto objective 均非空。

新的 `refinalize` 入口在独立派生目录中以只读符号链接访问原 `lifecycles/`、`bodies/` 与资源
证据，计算源文件前后 SHA-256 manifest，并明确记录 `source_result_overwritten=false`、
`scientific_contract_changed=false` 和 `npu_used=false`。

## 8. 讨论

R3B 最重要的系统结论不是找到一个默认最优 budget，而是显示静态 chunk budget 只能在不同代价
之间移动。较小 budget 增加 chunk 轮数，能限制单轮 Prefill 对 Decode 的阻塞，却会增加调度轮次
和长请求完成时间；较大 budget 更快清空长 Prefill，但会制造更长的 resident stall。实测关系又
不是简单单调：B4096 支配 B2048，B8192 支配 B12288，说明 kernel/batch 效率、调度轮次和
Prefill/Decode 混批共同塑造结果。

因此下一步不应立即扩大自然流量矩阵或选择单一 On policy。先完成零 NPU正式再聚合，确认五目标
frontier 和两个 mirror round 的 uncertainty。如果没有配置进入部署边界，R3B 本身已经回答了
研究问题：在当前硬件与 workload 下，静态 budget 校准不能同时获得长 Prefill TTFT 收益和接近
Off 的 resident Decode SLO。后续若继续，应研究动态 chunk sizing、显式 Decode SLO-aware
scheduling 或按负载选择 policy，而不是把某个静态点包装成普遍最优。

## 9. 有效性边界

- 结论只覆盖受控 staged-arrival admission cliff，不代表自然 API 到达过程。
- 每个 config 只有两个 fresh-model lifecycle；trial-pair bootstrap 不能消除同 lifecycle 内共享
  环境带来的相关性，因此必须同时报告两个 mirror-round effect。
- 改变 `max_num_batched_tokens` 同时改变 KV cache 容量与 maximum concurrency，R3B 是完整 policy
  comparison，不是 chunk size 的纯因果分解。
- 当前不声明生产 SLO、统计显著性或普遍 Chunked Prefill 收益。
- 原 P6.3C 135168/4096/1 blocked 审计、F4 共到达机制证据与 R3A matched A/B 均保留，不被
  R3B 覆盖。

## 10. 数据与复现入口

- 服务器 raw 结果：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_chunk_budget_pareto_2026_0804_run01`
- 开发机收到的小包：
  `/Volumes/SSD1/Inbox/2026-08-04/p6_3c_r3b_r3a_cost_2026_0804_run01`
- workload：
  `benchmarks/deepseek_v4_flash/workloads/p6_3c_r3b_chunk_budget_pareto.yaml`
- runner/finalizer：
  `tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py`
- 零 NPU 再聚合任务：
  `p6_3c_r3b_a1_performance_reaggregation_2026_0804`

原始 token timestamps、scheduler trace 和 server logs 继续留在服务器。派生小包只返回
manuscript-ready summary、paired effects、uncertainty、Pareto、provenance、资源恢复和 SHA
manifest，并继续遵守 70KB 与显式传输渠道选择规则。
