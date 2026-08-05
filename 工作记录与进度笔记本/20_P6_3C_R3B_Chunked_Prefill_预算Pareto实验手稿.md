# P6.3C-R3B：Decode 驻留条件下 Chunked Prefill 预算—时延 Pareto 实验

日期：2026-08-04

状态：`complete_p6_3c_r3b_policy_evidence / pareto_frontier_observed_no_candidate_within_bounds`

## 摘要

P6.3C-R3A 证明了 Chunked Prefill 能消除一个明确的 admission cliff：当八个 resident
Decode 已占用 16 个 scheduler token、12281-token 新 Prefill 无法完整装入剩余 12272-token
预算时，Off 侧将新请求留在 waiting，On 侧则立即 partial admit 12272 tokens。该机制使新请求
TTFT 大幅下降，却同时放大 resident Decode 的尾延迟。R3B 进一步研究这一收益—代价关系是否可
通过 `max_num_batched_tokens` 调节，而不是继续重复“机制是否存在”的问题。

实验在同一 DeepSeek-V4-Flash W8A8-MTP、TP8+EP、Prefix Cache off、`max_model_len=12288`、
`max_num_seqs=9` 和受控 staged arrival 下，比较一个合法 Off 基线 `B=12288` 与五个 On 策略
`B∈{2048,4096,6144,8192,12288}`。实验完成 5 个 observer-enabled mechanism lifecycle
和 12 个 observer-free performance lifecycle；每个 policy–cell 包含 12 个有效 trial。

机制轨道给出清晰、单调的预算响应：首个 injected chunk 始终等于 `B-D`，即 2032、4080、
6128、8176 和 12272 tokens；完整 12281-token Prefill 分别需要 7、4、3、2 和 2 个 chunk，
全程未观察到 preemption。零 NPU A1 以只读方式对原始结果重新归档，恢复了 144/144 个
measured trial、60/60 个有效 Off/On pair 以及每个 On 策略五项指标均 `n=12` 的不确定性估计。
按 12-trial pooled median 比率，所有 On 策略都将 injected TTFT 降低 47.5%–80.5%，但
resident P99 TBT 增加 345.6%–681.6%，aggregate TPS 下降 6.8%–20.4%。因此没有 On
配置同时满足运行前写入
tracked workload contract 的 TTFT、resident P99 TBT 与 throughput 三项项目内边界。

基于 pooled sample median 的经验五目标 Pareto frontier 为 `off_b12288`、`on_b2048`、
`on_b4096`、`on_b6144` 和 `on_b8192`；`on_b12288` 被 `on_b8192` 在五个目标上支配。
`on_b2048` 之所以保留在 frontier，是因为其点估计在 On 策略中具有最低的 P99 TBT
和 maximum stall，而非因为它是已证实的最优部署点。静态 budget 可以沿收益—代价前沿移动
工作点，但在当前受控 admission-cliff workload 下尚不能同时保留长 Prefill TTFT 收益和
接近 Off 的 resident Decode SLO。

## 1. 研究问题与可检验假设

R3A 已经建立开关本身的因果锚点：在 `B=12288` 的严格 matched A/B 中，
Chunked Prefill 将长 Prefill 从整段等待改为 partial admission，显著缩短 TTFT，但会
干扰已驻留的 Decode 流。R3B 不再重复这一实验，而是把 On 侧 scheduler token budget
视为可调控的策略参数，研究不同预算是否能将该机制移动到可接受的收益—代价区域。

实验预先给出三个可检验命题。

| 假设 | 可检验预期 | 判定结果 |
| --- | --- | --- |
| H1：预算校准会改变实际 chunk 几何 | 首个 injected chunk 应等于 `B-D`，且总 chunk token 精确回收 12281 | 支持 |
| H2：减小 `B` 可缓和 Decode 干扰 | 较小 `B` 应降低 resident P99 TBT/maximum stall，但增加 injected TTFT 或吞吐代价 | 部分支持；总体折中存在，但并非单调 |
| H3：静态预算中存在可部署工作点 | 至少一个 On 策略同时满足 TTFT 改善、P99 TBT 与 TPS 三项边界 | 未支持 |

R3B 不是 strict single-variable A/B。Off 侧必须满足 `B≥L` 才能启动，因此保持
`B=L=12288`；小预算 On 同时改变 Chunked Prefill 开关与预算，代表完整 policy，
而非对单个布尔开关的因果估计。因此，R3A 负责“开关是否导致机制差异”，R3B 负责
“可部署策略之间如何折中”。

## 2. 实验设置

### 2.1 共同运行环境

- 模型：DeepSeek-V4-Flash W8A8-MTP，量化模式为 `ascend_w8a8`；
- 硬件与并行：Atlas 800T A2，八卡 Ascend 910B1，TP=8、EP enabled，NPU 0–7；
- runtime：vLLM 0.22.1 / vLLM-Ascend 0.22.1rc1；
- `max_model_len=12288`，`max_num_seqs=9`；
- Prefix Cache 显式关闭；
- MTP `num_speculative_tokens=1`，graph mode=`FULL_DECODE_ONLY`，
  block size=128，async scheduling enabled；
- 请求固定 `temperature=0`、`ignore_eos=true`，并以相同的
  `min_tokens=max_tokens` 强制输出长度；
- 模型、量化、请求体与 staged-arrival 语义在 policy 间保持一致；
- observer 只用于五个 mechanism lifecycle，十二个 performance lifecycle 不安装 observer 或
  profiler。

每个 trial 先通过一个 batched streaming `/v1/completions` HTTP request 启动八个 resident
sequence，每个 sequence 使用 256-token 输入并生成 128 tokens。八个 resident 不是八次独立
HTTP arrival；它们是同一个请求中的八个 choice。达到注入门后，客户端再通过第二个、独立的
streaming HTTP request 发送 12281-token Prompt，并强制输出 4 tokens。各 policy 使用的请求体
按字节复用，生成文本和 token ID 不进入有界结果包。

只有当八个 resident 均已输出至少 16 tokens 后，才注入 12281-token 长 Prefill。这个门控使
机制 trace 中 injected 首个相关 scheduler step 的 Decode scheduled-token 总量稳定为

\[
D=16,
\]

这里的 `D=16` 指该 scheduler step 上八个 resident 的 scheduled-token 总和，并非八个 resident
历史累计已经输出的 token 总量。由此，On 策略首轮可供 Prefill 使用的预算为

\[
R(B)=B-D.
\]

`max_num_seqs=9` 对应八个 resident sequence 加一个 injected request。injected request
只生成 4 tokens，因此其作用主要是制造 Prefill 压力与测量 TTFT；cliff cell 的 aggregate TPS
分母覆盖完整 trial makespan，分子则为八个 resident 的 1024 个输出 token 加 injected 的 4 个
token。它不代表长输出请求的吞吐。

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

网格由四个按 2048-token 间隔增长的小/中预算点与 R3A 的 B12288 锚点构成，目的是以有限
生命周期覆盖从 7-chunk 到 2-chunk 的调度区间。它不是穷举搜索；例如 B10240 未被纳入，
因此结论必须限定为上述五个 On budget。

机制轨道为五个 On budget 各一个 fresh-model lifecycle。性能轨道采用镜像顺序控制模型加载与
时间漂移：

```text
round 1: Off, On-2048, On-4096, On-6144, On-8192, On-12288
round 2: On-12288, On-8192, On-6144, On-4096, On-2048, Off
```

每个性能 lifecycle 先执行一次 512-token input、32-token output 的 warmup，再执行 12 个
measured trial。两个 cell 以

\[
R,C,C,R,R,C,C,R,R,C,C,R
\]

的平衡序列交替，其中 \(R\) 为 resident-only，\(C\) 为 admission-cliff。每个 lifecycle
因而含六个 control 与六个 cliff trial；合并两个 mirror round 后，每个 policy–cell
有 12 个有效样本。完整任务包括 5 个 mechanism 和 12 个 performance lifecycle，
共产生 144 个 measured trial（其中两个 cell 各 72 个）。

### 2.3 指标、配对与不确定性

主要性能指标为 injected TTFT。代价指标为 resident interference-window P99 TBT、真实 maximum
adjacent-token stall 和 aggregate output TPS。项目内 TBT SLO threshold 定义为
`2× Off-B12288 resident-only pooled median TBT`，只用于本项目的相对策略分析，不是外部标准。

各指标按客户端 monotonic timestamp 定义。Injected TTFT 是独立 injected HTTP request
从 request start 到第一个 streaming token 的时长；E2EL 是同一请求从 start 到完成的时长。
Resident interference window 从 `injection_dispatch_ns` 开始，到 injected first-token timestamp
结束。窗口内把八个 resident 的相邻 token gap 合并，先在每个 trial 内计算线性插值 P99 和
maximum，再在 12 个 trial 上取中位数。Aggregate TPS 等于 cliff trial 的 1028 个输出 token
除以从最早 resident request start 到最晚 request end 的 makespan。

MTP 可能在同一个 Server-Sent Events (SSE) event 中返回多个 token ID。客户端为同一 event
中的 token 赋相同 timestamp，因此相邻 token interval 可以为 0 ms。该约定对所有 policy
一致，但会影响 pooled median、SLO attainment 和尾分位数的绝对解释。Interference window
按 gap 的右端点纳入：右端点位于 `[dispatch, first-token]` 的 gap 被计入；跨越 first-token
边界后才结束的 gap 被排除。该窗口定义与所有结果一同冻结，并在有效性边界中单独讨论。

运行前写入 tracked workload contract 的项目内决策边界要求 On 策略同时满足：

- injected TTFT 相对 Off 至少改善 20%；
- resident P99 TBT 相对 Off 增幅不超过 10%；
- aggregate output TPS 相对 Off 降幅不超过 5%。

Pareto 分析同时最小化 TTFT、P99 TBT 和 maximum stall，最大化 TPS 与 TBT SLO attainment。
支配关系的定义是：一个策略在五个目标上均不差于另一策略，且至少一项严格更好。

每个 On 策略在每轮中与当轮 Off 基线按 repeat index 配对，五个 On 策略各产生
12 个 admission-cliff pair，总计 60 个。不确定性以 On−Off 配对差的中位数表示，
并使用 seed 633 和 10000 次 bootstrap 给出 95% 区间。同一 lifecycle 中的六个 trial
共享同一 fresh-model 环境，因此该区间只表达 trial-pair 层面的方向与量级。
两个 mirror-round 中位数必须同时报告，以暴露 lifecycle order 敏感性。

TBT SLO 仅是项目内分析尺度。Off B12288 的 resident-only pooled token interval 中位数为
86.684 ms，因此阈值被固定为 173.368 ms。它用于比较策略间的 token-level
attainment，不被表述为生产 SLO 或外部标准。

## 3. 任务过程与证据链

整个任务由机制校准、性能采集和零 NPU 再聚合三个阶段组成。这三个阶段解决不同问题：
机制阶段确认预算参数在 scheduler 中确实对应不同 chunk 几何；性能阶段在无 observer
和无 profiler 的 fresh-model lifecycle 中采集终端时延与吞吐；再聚合阶段则从已完成的 raw
证据重建正式统计，不重跑模型。

服务器首先在独立 worktree 和全局 NPU 无冲突条件下完成原 R3B run01。任务共执行
17/17 个 fresh-model lifecycle，包括 5 个机制 lifecycle 和 12 个性能 lifecycle。所有生命周期
均启动成功、exit 0 且 cleanup clean，完成 1286/1286 个 engine request 与 243/243 个
local HTTP request，全程没有 request retry。这些数量可由实验结构完整推导：每个
性能 lifecycle 包含 1 个 warmup、6 个 8-request resident-only trial 和 6 个 9-request
admission-cliff trial，即 103 个 engine request；12 个性能 lifecycle 共 1236 个。五个机制
lifecycle 各 10 个 request，补足总数 1286。

运行期间的两次现场适配分别处理了旧分析器对 warmup 的识别和实际 Ascend 环境中的
`acl_graph` 兼容性。每次适配均保留 before/after 证据，并在退出后恢复环境文件。它们没有改变
六个 policy、staged-arrival workload、trial 次序、样本量、指标定义或 Pareto 规则。因此，
它们属于运行环境适配，而非对科学合同的修改。原 NPU 运行结束后，0–7 号卡的
keep-alive 被精确恢复为 16 个 marker，端口 7000 无监听，也无 vLLM 残留进程。

原 finalizer 没有把 144 个已完成 measured trial 接入正式性能表。开发机修复后，A1 在
`main@143750bd035da1bb914e13198093cd3b70a2078c` 的独立 detached worktree 中对原结果
执行一次零 NPU、只读再聚合。A1 未启动 vLLM，未停止 keep-alive，也未产生现场修复。
它仅对 tracked workload contract 中的 measured trial ID 接受缺失 `phase` 的重建，
warmup 和未知 trial ID 不会被纳入。
原结果的 182 个证据文件共 6,967,125 bytes，联合 SHA-256 为
`1158f7fc74a4576ce73f0fa128afdc68791c7f45011d07072a206fb4ebf83f9d`；再聚合
前后字节不变，且 source result 未被覆盖。

最终完整性不依赖单一等级标签，而由样本结构直接确立：144/144 measured trial、
12/12 policy-summary row 且每行 12 个有效样本、60/60 有效 Off/On pair、每个 On
policy 的五项不确定性均 `n=12`、两个 mirror-round 中位数完整，以及六个 policy
的五个 Pareto 目标均为非空。这一证据链将“实验已运行”与“分析可用”分开，又在最终
归档中重新合一。

模型启动资源也随 policy 改变。`B=12288` 时可用 KV cache 约 15.01 GiB、maximum
concurrency 为 2.29；`B=2048` 时分别约为 16.21 GiB 和 13.66。这进一步说明 R3B
比较的是可运行的完整 policy，不能把全部性能差异解释为 chunk size 的纯单变量作用。

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

这一结果把 R3A 的单点机制扩展为 scheduler-contract response：chunk budget 不是仅影响配置
显示值，而是精确改变 scheduler 对 injected Prefill 的首步 token allocation 和完成轮数。
更大的首个 chunk 理论上减少 Prefill 完成轮数，但性能结果并不随预算单调改善。实测 B8192
的 TTFT 低于 B12288，说明 chunk 轮数、混批效率、graph 行为和资源容量共同决定端到端结果。

## 5. 性能结果：收益与代价形成非单调折中

### 5.1 策略级绝对指标

零 NPU A1 在不覆盖原结果的独立派生目录中完成正式重聚合。源结果共 182 个文件、
6,967,125 bytes，联合 SHA-256 为
`1158f7fc74a4576ce73f0fa128afdc68791c7f45011d07072a206fb4ebf83f9d`；聚合前后字节不变。
最终每个 config-cell 都包含 12 个有效 trial。admission-cliff cell 的正式样本中位数如下。

| 配置 | TTFT (ms) | E2EL (ms) | resident P99 TBT (ms) | max stall (ms) | TPS | SLO attainment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Off B12288 | 5887.0 | 6057.0 | 95.56 | 97.23 | 127.59 | 1.000 |
| On B2048 | 3088.7 | 3917.6 | 425.78 | 425.87 | 101.62 | 0.622 |
| On B4096 | 1875.5 | 2727.3 | 429.08 | 429.13 | 113.32 | 0.696 |
| On B6144 | 1509.2 | 2372.5 | 452.72 | 452.77 | 114.32 | 0.748 |
| On B8192 | 1146.4 | 1981.4 | 551.30 | 551.31 | 118.91 | 0.830 |
| On B12288 | 1368.8 | 2211.3 | 746.87 | 746.90 | 115.64 | 0.830 |

该表显示出一个不能用“预算越大越好”解释的关系。B8192 获得六个 policy 中最低的
TTFT，同时是 On 侧 TPS 最高的点；将预算继续增大到 12288 反而恶化 TTFT、P99 TBT、
maximum stall 和 TPS。另一端的 B2048 确实给出了 On 策略中最低的 resident P99 TBT，
但其 TTFT 仍是 Off 的约一半，而 TPS 代价却最大。静态预算不仅控制单轮干扰，也改变
Prefill 完成轮数、批处理效率和可用 KV cache，导致宏观性能呈非单调响应。

相对 Off 的 pooled-median 变化如下。这一比率估计用于部署边界和 Pareto 分析，不应与下文
median-of-paired-differences 的 bootstrap 估计混为一谈。

| On 配置 | TTFT 变化 | resident P99 TBT 变化 | TPS 变化 | 三项边界 |
| --- | ---: | ---: | ---: | --- |
| B2048 | −47.5% | +345.6% | −20.4% | 未满足 |
| B4096 | −68.1% | +349.0% | −11.2% | 未满足 |
| B6144 | −74.4% | +373.8% | −10.4% | 未满足 |
| B8192 | −80.5% | +476.9% | −6.8% | 未满足 |
| B12288 | −76.7% | +681.6% | −9.4% | 未满足 |

### 5.2 Resident-only 内部对照

各 policy 的 resident-only cell 在没有 injected Prefill 时保持接近，说明 cliff cell 中数百毫秒
的 P99 TBT 不是策略启动后 Decode 基线自然恶化的结果。

| 配置 | resident-only P99 TBT (ms) | resident-only max stall (ms) | resident-only TPS | SLO attainment |
| --- | ---: | ---: | ---: | ---: |
| Off B12288 | 98.13 | 428.56 | 141.81 | 0.997 |
| On B2048 | 97.07 | 423.32 | 146.09 | 0.993 |
| On B4096 | 95.83 | 444.46 | 143.79 | 0.996 |
| On B6144 | 94.64 | 441.19 | 141.43 | 0.996 |
| On B8192 | 96.41 | 414.18 | 145.76 | 0.995 |
| On B12288 | 97.72 | 436.58 | 140.52 | 0.993 |

Off 的 P99 TBT 从 resident-only 的 98.13 ms 到 cliff 的 95.56 ms，基本不变。五个 On
policy 则从约 94.6–97.7 ms 增至 425.8–746.9 ms。该组内对照把主要代价定位在长 Prefill
与 resident Decode 共存的 interference window，而不是模型加载、policy 启动或 resident-only
Decode 的一般性性能差异。Resident-only maximum stall 仍包含完整请求生命周期中的 rare gap，
因此其数值明显高于 P99，且不用于三项部署边界。

### 5.3 配对效应与描述性不确定性

下表给出 12 个 trial-pair 的 On−Off 中位效应和固定 seed=633、10000 次 bootstrap 区间。TPS
为 tokens/s 差，SLO 为 attainment 绝对比例差。六个 trial 共享同一 fresh-model lifecycle，因此
该区间是 trial-pair 层面的 descriptive bootstrap interval，不能当作 12 个完全独立 lifecycle
的总体推断区间。每轮同一组 Off trial 还被五个 On policy 共同使用，因此不同 On effect 之间
也不是独立估计。

| On 配置 | TTFT Δ ms [bootstrap 95%] | P99 TBT Δ ms [bootstrap 95%] | TPS Δ [bootstrap 95%] | SLO Δ [bootstrap 95%] |
| --- | --- | --- | --- | --- |
| B2048 | −2760 [−2830, −2722] | +331 [+319, +353] | −25.3 [−26.3, −24.3] | −0.377 [−0.380, −0.375] |
| B4096 | −4011 [−4085, −3958] | +334 [+320, +357] | −13.0 [−16.9, −6.5] | −0.304 [−0.309, −0.303] |
| B6144 | −4383 [−4512, −4298] | +357 [+347, +364] | −12.8 [−15.6, −9.7] | −0.251 [−0.254, −0.250] |
| B8192 | −4747 [−4820, −4680] | +457 [+420, +472] | −6.4 [−10.2, −3.5] | −0.169 [−0.171, −0.167] |
| B12288 | −4535 [−4629, −4439] | +653 [+643, +680] | −10.2 [−13.1, −8.0] | −0.170 [−0.172, −0.168] |

所有 On 策略的 TTFT、P99 TBT、TPS 和 SLO effect 在两个 mirror round 中方向一致。但 maximum
stall 对 lifecycle order 敏感：B2048/4096/6144/8192/12288 的 round-1 差分中位数为
+316/+315/+348/+435/+645 ms，round-2 只有 +2/+16/+32/+99/+317 ms。配对 bootstrap 因而对五档
budget 都给出跨越零的 maximum-stall 区间。这不否定 P99 TBT 的稳定恶化，但表明单一最大 gap
容易受 lifecycle 内少数异常 gap 和 Off 基线位置影响，不应单独用于选取部署点。

| On 配置 | TTFT Δ, R1 / R2 (ms) | P99 TBT Δ, R1 / R2 (ms) | TPS Δ, R1 / R2 | max stall Δ, R1 / R2 (ms) |
| --- | ---: | ---: | ---: | ---: |
| B2048 | −2815 / −2734 | +329 / +338 | −25.4 / −25.3 | +316 / +2 |
| B4096 | −4050 / −3958 | +320 / +341 | −8.1 / −16.9 | +315 / +16 |
| B6144 | −4383 / −4343 | +357 / +358 | −11.5 / −15.6 | +348 / +32 |
| B8192 | −4759 / −4712 | +455 / +458 | −6.0 / −8.7 | +435 / +99 |
| B12288 | −4535 / −4517 | +658 / +651 | −9.8 / −13.1 | +645 / +317 |

两轮的 TTFT 和 P99 TBT 量级接近；TPS 虽有更明显的轮次波动，方向仍全部一致。maximum
stall 则不同：五档预算的 bootstrap 区间均跨越零，每档都有 4/12 个 pair 呈负向差值。
resident 代价的主要证据因而是两轮方向稳定的 P99 TBT、SLO attainment 和 TPS，maximum
stall 仅作为 rare-event、lifecycle-order-sensitive 的辅助诊断。

### 5.4 部署边界与经验 Pareto frontier

项目内三项边界没有候选。TTFT 门最接近的 B2048 仍已改善 47.5%；P99 TBT 代价最小的
B2048 仍增加 345.6%；TPS 最接近边界的 B8192 仍下降 6.8%，比 −5% 上限多 1.8 个百分点。
因此失败的核心不是 TTFT 收益不足，而是 resident Decode 代价远超约束。

基于 12-trial pooled sample median 的五目标 empirical point-estimate frontier 为
`off_b12288`、`on_b2048`、`on_b4096`、
`on_b6144`和 `on_b8192`。`on_b12288` 被 `on_b8192` 支配：后者 TTFT、P99 TBT、maximum
stall 更低，TPS 更高，SLO attainment 相同。先前根据两个 lifecycle 摘要均值得出的
`on_b4096` 支配 `on_b2048` 不成立；在 12-trial 正式中位数下，B2048 的 P99 TBT 和
maximum stall 分别只低约 3.3 ms 和 3.3 ms，因而按当前点估计仍是非支配点。这一归属对小幅
测量波动可能敏感，不能解释为 B2048 已被证明在尾延迟上稳健优于 B4096。

作为一个直接的点估计敏感性检查，若从 Pareto 目标中移除顺序敏感的 maximum stall，只保留
TTFT、P99 TBT、TPS 和 SLO attainment，非支配集合与唯一支配关系均不改变：
B8192 仍支配 B12288，其余五点仍非支配。该检查说明当前 frontier 不完全由 maximum stall
驱动，但仍未提供 uncertainty-aware 或 epsilon-dominance 结论。

## 6. 与 R3A 的跨实验一致性

R3B 前的零 NPU R3A raw timestamp 复分析确认，admission-cliff 下真实 maximum adjacent-token
stall 的 On−Off 配对中位差为 +620.12 ms，descriptive 95% bootstrap interval 为
[+579.68, +660.85] ms。两个 fresh-model pair 分别为 +601.85 和 +624.49 ms；injected TTFT、
resident P99 TBT、maximum stall 与 TPS 四项在两个 pair 中方向一致。该结果保持 R3A 的
`mechanism_confirmed_tradeoff_only` 结论。

## 7. 讨论

R3B 最重要的系统结论不是找到一个默认最优 budget，而是说明静态 chunk budget 可以移动
收益—代价工作点。较小 budget 增加 chunk 轮数，通常限制单轮 Prefill 对 Decode 的干扰，
但会延长长请求 TTFT 或降低吞吐；较大 budget 加快 Prefill token 的前置处理，却可能提高
resident tail latency。该关系并非严格单调。B8192 在当前五目标点估计上支配 B12288，而
B2048 虽然 TTFT 和 TPS 较差，仍因略低的 On-side P99 TBT 和 max stall 保留在 frontier。
Kernel/batch 效率、调度轮次、KV cache 容量和 Prefill/Decode 混批共同塑造了观测结果。

正式重聚合后，R3B 已回答当前研究问题：在当前硬件、受控 workload 和测试的五个 On budget
中，没有一个静态策略同时获得长 Prefill TTFT 收益和接近 Off 的 resident Decode SLO。
这不支持自动选一个 R3C 候选：B8192 虽有最低 TTFT 并最接近 TPS 边界，但 P99 TBT 仍增加
476.9%；B2048 的 Decode 尾时延代价在 On 中最小，但仍远超边界且吞吐下降 20.4%。
若继续实质性推进，应优先研究
动态 chunk sizing、显式 Decode SLO-aware scheduling 或按负载切换 policy，而不是把某个静态点包装成
普遍最优。

## 8. 有效性边界

结论只覆盖一个受控 staged-arrival admission cliff。八个 resident sequence 来自同一个 batched
HTTP request，injected request 仅生成 4 tokens；该到达模型不能代替自然 API 流量、长输出任务
或生产 SLO 容量评估。预算网格只包含 2048、4096、6144、8192 和 12288，未测试的静态预算
仍可能形成不同工作点。

每个 policy 只有两个 fresh-model performance lifecycle。表中的 `n=12` 是 trial-pair 数，
不是 12 个独立模型生命周期；每组六个 trial 共享同一 lifecycle，每轮同一个 Off trial 还被五个
On policy 复用。当前 bootstrap 只能作为描述性区间。若要作总体统计推断，需要增加独立
lifecycle pair，并采用 cluster 或 hierarchical resampling。

指标本身也有边界。MTP 在同一 SSE event 返回多个 token 时会产生 0-ms adjacent interval。
Interference window 按 gap 右端点筛选，跨过 injected first-token 后才结束的 gap 被排除，
这可能低估恰好跨越窗口上界的 stall，尤其需要在未来 sensitivity analysis 中检查。
不同 budget 产生不同 TTFT 和窗口长度，窗口内有效 gap 数也可能不同；当前有界包没有汇总
per-trial gap count 的分布，后续实验应同时报告该计数，避免在不同有效样本量下孤立比较尾分位数。
Maximum stall 对 lifecycle order 敏感，因此 resident 代价主张依赖 P99 TBT、SLO attainment
和 TPS。当前 Pareto 集是 pooled sample median 的 point-estimate frontier，尚未执行
uncertainty-aware dominance 或 epsilon-dominance 分析。

最后，改变 `max_num_batched_tokens` 同时改变 KV cache 容量与 maximum concurrency。
R3B 是完整 policy comparison，不是 chunk size 的纯因果分解。原 P6.3C 135168/4096/1
blocked 审计、F4 共到达机制证据与 R3A matched A/B 均保留，不被 R3B 覆盖。

## 9. 结论

在固定的 decode-resident admission-cliff workload 上，Chunked Prefill 的首个 Prefill chunk
按 `B-D` 精确变化；五档预算对应 7、4、3、2 和 2 个完成 chunk，验证了预算对 scheduler
token allocation 的直接控制。在测试的五个 On budget 中，injected TTFT 相对 Off 降低
47.5%–80.5%，但 resident P99 TBT 增加 345.6%–681.6%，aggregate TPS 下降
6.8%–20.4%。没有测试点满足项目内 20%/10%/5% 联合边界。

经验 Pareto frontier 说明静态 budget 能够移动工作点，却没有给出普适部署最优。
B8192 在当前点估计上支配 B12288，B2048 则以较低的 On-side 尾时延换取更差的 TTFT 与吞吐。
这一结果把下一步问题从“继续寻找一个固定 budget”推进为“能否根据 Decode 压力动态控制
Prefill chunk”。后续研究应将 resident TBT/SLO 纳入调度反馈，并在自然到达与更多独立
lifecycle 上验证，而不是把本轮任一静态配置直接升级为生产建议。

## 10. 数据与复现入口

- 服务器 raw 结果：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_chunk_budget_pareto_2026_0804_run01`
- 开发机收到的小包：
  `/Volumes/SSD1/Inbox/2026-08-04/p6_3c_r3b_r3a_cost_2026_0804_run01`
- A1 服务器派生结果：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3b_a1_performance_reaggregation_2026_0804`
- A1 开发机小包：
  `/Volumes/SSD1/Inbox/2026-08-04/p6_3c_r3b_a1_reagg_2026_0804`
- workload：
  `benchmarks/deepseek_v4_flash/workloads/p6_3c_r3b_chunk_budget_pareto.yaml`
- runner/finalizer：
  `tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py`
- 零 NPU 再聚合任务：
  `p6_3c_r3b_a1_performance_reaggregation_2026_0804`

原始 token timestamps、scheduler trace 和 server logs 继续留在服务器。A1 有界包为 17 文件、
47,726 bytes，包含 manuscript-ready summary、paired effects、uncertainty、Pareto、provenance 和资源恢复证据；
182 文件、6.97MB 的源证据 manifest 留在服务器。开发机收到的目录与服务器报告的
文件数和总 bytes 精确相符，且所有 JSON/TSV 语义可一致复算；但 server-local
`candidate_manifest.server_local.json` 未随包返回，因而开发机本轮不声称已完成逐文件跨机 SHA 对照。

## 附录 A：分析完整性与审计过程

### A.1 为什么需要 A1 再聚合

原 R3B NPU 实验已经完整执行，但第一版 finalizer 没有把性能 trial 纳入汇总。Measured request
row 含 `phase=measured`，复用的 staged-trial summary 却缺少 `phase`。Finalizer 仅接受
`trial.phase == measured`，导致 144 个成功 trial 全部被过滤。第一版输出因而表现为
12 个 summary row 的 `valid_trial_count=0`、60 个 Off/On pair 全部 invalid、
uncertainty `n=0`，以及五个 objective 全为空的伪 frontier。生命周期、请求和资源门均通过，
但性能分析实际上不可用。

修复没有放宽到“接受所有缺少 phase 的记录”。Future-run 会在 raw trial summary 写盘前显式
保存 `phase`；对既有 run01，只有 trial ID 精确属于 tracked workload 中的 measured plan
时才重建 `phase=measured`，warmup 和未知 ID 继续拒绝。新的完整性条件同时要求
144/144 measured trial、12 个 summary row 各 12 个有效样本、60/60 valid pair、每个
On-policy × metric 的 uncertainty `n=12`、两个 mirror round 中位数和六个 policy 的
五个 Pareto objective。A1 在真实旧数据上满足全部条件，说明修复恢复了既有证据，而不是用
合成 fixture 制造完成状态。

### A.2 两层 provenance 与资源动作

原 R3B NPU 运行和 A1 再聚合是两个不同的 provenance 层。原实验在
`main@86eeeda0369354be6266591e4c6644ab862a32d5` 完成 17 个 lifecycle，使用 NPU 0–7，
并在退出后精确恢复同一组卡的 keep-alive。A1 则在
`main@143750bd035da1bb914e13198093cd3b70a2078c` 执行零 NPU 只读分析，
`keep_alive_action=left_running`，未启动 vLLM，也未覆盖源目录。
因此，`resource_recovery_summary.json` 中的停卡与恢复记录描述原 R3B 运行，
`analysis_provenance.json` 中的 `npu_used=false` 描述 A1；二者并不矛盾。

A1 记录的 runner SHA-256 为
`fb2432a25aaeffde3d295c6d1849400a24f101058ea4e7a1faba1efeeff918ac`，
workload SHA-256 为
`b197364f1d284a003002738faf491cfb779c20cf7164275680ca280603c1a06d`，
observer SHA-256 为
`3cc372c28681b786ceb65b62830375f584386d51486ec4425147b12f5bab6e0e`。
这些标识足以定位本项目内的分析与实验合同，但 A1 小包没有单独归档 CANN、driver、
Python、PyTorch 和 torch-npu 的完整版本矩阵；严格环境复现仍需读取服务器 raw 结果和原运行日志。

### A.3 开发机验收边界

开发机核验了 A1 小包中的 17 个文件及 47,726-byte 集合大小，所有 JSON/TSV 均可解析；
并从结构化文件独立复算了 12/12 summary row、60/60 valid pair、五目标 dominance 和
deployment-bound 结论。包内没有返回服务器生成的
`candidate_manifest.server_local.json`，因此本地只能确认内容内部一致性、文件数和总大小，
不能声称已完成 manifest 所列逐文件 SHA 的跨机比对。这一限制不改变结果数值，但属于交付审计
边界，后续打包器应把 candidate manifest 纳入同一有界传输 scope。
