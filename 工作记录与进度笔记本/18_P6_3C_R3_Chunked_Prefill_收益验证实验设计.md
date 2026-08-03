# P6.3C-R3：Chunked Prefill 收益验证实验设计

更新日期：2026-08-03

状态：R3-S0 与 R3A 执行包已开发并通过开发机验证；已授权服务器在全局八卡无冲突后先执行 S0，S0 通过后自动进入 R3A

## 摘要

P6.3C-R2-F4 已在 DeepSeek-V4-Flash W8A8-MTP、八卡 Ascend 910B1 和 vLLM
0.22.1 环境中证明：当两个 Prefill 请求同时对 scheduler 可见且总输入超过共同冻结的
12288-token batch budget 时，Chunked Prefill On 会产生 partial prefill，Off 则采用整段
准入或等待。该实验关闭了机制存在性问题，但固定样本没有显示短请求 TTFT 或 batch
throughput 收益。

本设计把后续研究从“增加 F4 重复次数”改为“制造在途 Decode 与新长 Prefill 的真实资源
竞争”。对 vLLM 0.22 的实际 V1 scheduler 源码复核显示，scheduler 在 Off 和 On 两种模式下
都先调度 RUNNING 请求，再处理 WAITING 请求。Chunked Prefill Off 的关键限制不是 Decode
失去优先级，而是新 Prefill 只有在其完整 token 数可以装入剩余预算时才能准入；On 则可以把
该 Prefill 截断到剩余预算并立即开始。因此，在当前 `max_model_len=max_num_batched_tokens`
的严格匹配环境中，最有辨识力的收益假设是“避免长 Prefill 在持续 Decode 前台下发生准入
饥饿”，而不是预设“On 一定降低在途 Decode 的 TBT”。后者在这一配置中更可能体现为需要
量化的代价。

后续实验分为三层。R3-S0 只校准八个驻留 Decode 的实际 scheduler token 消耗与 KV 容量；
R3A 使用 Off/On 仅差一个开关的 matched A/B，检验长 Prefill 准入和 TTFT 收益，同时测量
驻留 Decode 的 ITL/TBT 代价；R3B 在 On 侧扫描 batch token budget，寻找长 Prefill TTFT、
Decode 尾延迟与总 goodput 的 Pareto 点。只有前两层形成清晰证据后，才进入 R3C 自然到达的
混合在线负载。

## 1. 已有证据与未回答问题

### 1.1 F4 已经回答的机制问题

[P6.3C-R2-F4 实验手稿](./17_P6_3C_R2_F4_Chunked_Prefill_受控调度实验手稿.md)
记录了共同 `12288/12288/2`、Prefix Cache off 和受控 atomic co-arrival 条件下的直接
scheduler 证据。4K+4K 无压力 cell 在 Off/On 两侧均整段准入；10K+6K 与 8K+8K 压力
cell 只在 On 侧发生 partial prefill。因而本项目已接受：

> Chunked Prefill 在多请求总 Prefill token 超过 batch budget 时确实改变 scheduler token
> allocation。

这个结论不等价于性能收益。F4 的请求都处于 Prefill 阶段，输出长度仅 64 token，实验没有
构造稳定驻留的 Decode 前台，也没有让一个新长 Prefill 在 Decode 进行中到达。

### 1.2 原讨论中需要修正的假设

vLLM 0.22 的 V1 scheduler 先遍历 RUNNING 请求并扣减 token budget，随后才遍历 WAITING
请求。对一个新到达的 Prefill，设：

- `B` 为单个 scheduler iteration 的 token budget；
- `D` 为该 iteration 已分配给 RUNNING 请求的 token 总量；
- `P` 为 WAITING Prefill 尚未计算的 token 数。

剩余预算为：

\[
R = B - D.
\]

Off 侧的准入条件为：

\[
P \le R.
\]

若 `P > R`，Off 在 WAITING loop 中停止，Prefill 本轮不获得 token。On 侧则调度：

\[
P_{\text{scheduled}} = \min(P, R).
\]

因此，当 `P > B-D` 时，matched A/B 的直接差异是：

- Off：Decode 继续推进，长 Prefill 等待完整准入机会；
- On：Decode 仍先获得 token，长 Prefill 使用剩余预算立即执行一个 chunk。

这意味着 `B=L=12288` 的 R3A 应把长 Prefill 的 scheduler admission delay 和 TTFT 设为
主要收益指标，把驻留 Decode 的 TBT/ITL inflation 设为主要代价指标。若直接把“Decode
保护”写成预期成功条件，实验很可能错误解释当前 V1 scheduler 的真实行为。

### 1.3 仍需回答的研究问题

R3 需要依次回答四个问题。

1. 当在途 Decode 占用少量 scheduler budget、使一个接近 `max_model_len` 的新 Prefill 只差
   少量 token 不能整段装入时，On 是否消除 Off 的准入等待？
2. 这种提前准入能否转化为长请求 TTFT、等待时间或请求完成时间的实用改善？
3. 提前执行的大 Prefill chunk 会给驻留 Decode 的 P95/P99 TBT、最大 stall 和 SLO attainment
   带来多大代价？
4. 缩小 On 侧 batch token budget 后，是否存在同时改善长 Prefill 等待和控制 Decode 尾延迟
   的 Pareto operating point？

## 2. 研究假设

### H1：matched admission mechanism

在 `B=L=12288`、八个驻留 Decode 已进入稳定生成、`P=12281` 的条件下，Off 首个相关
scheduler step 不为长 Prefill 分配 token；On 在同一 step 同时调度 resident Decode token
与长 Prefill 的 partial chunk。

### H2：long-prefill starvation relief

在相同 arrival phase 下，On 会降低临界长 Prefill 的 scheduler admission delay 和 TTFT。
该假设只针对接近预算边界且存在稳定 Decode 前台的负载，不外推所有 Prompt 长度或自然流量。

### H3：decode interference cost

On 的提前准入可能提高驻留 Decode 在干扰窗口内的 TBT，特别是 `B=12288` 时首个 chunk
接近完整长 Prompt。R3A 不预设这一代价很小，而是把它与长 Prefill 收益并列报告。

### H4：calibrated policy benefit

在 On 侧降低 `max_num_batched_tokens` 会缩小单轮 Prefill chunk，并可能降低 Decode TBT
inflation，但也会增加 Prefill round、调度开销和长请求 TTFT。预期结果是非单调的 Pareto
frontier，而不是单个配置在所有指标上占优。

## 3. R3-S0：容量与调度语义校准

R3-S0 是一个独立命名的 mechanism-only scout，不生成性能结论。它必须在正式 R3A 前确认
真实服务器行为，避免把开发机对上游源码的理解当作 Ascend 运行证据。

### 3.1 共同候选配置

| 项目 | 候选值 |
| --- | --- |
| 模型与量化 | DeepSeek-V4-Flash-w8a8-mtp，`ascend_w8a8` |
| 并行 | TP8 + EP |
| MTP | `num_speculative_tokens=1` |
| graph | `FULL_DECODE_ONLY` |
| block size | 128 |
| Prefix Cache | 显式关闭 |
| `max_model_len` | 12288 |
| `max_num_batched_tokens` | 12288 |
| `max_num_seqs` | 9 |
| async scheduling | 与 F4 相同 |

F4 启动证据给出 `gpu_kv_cache_tokens=28182`。R3A 的理论最大活跃 token 约为：

\[
8\times(256+128)+(12281+4)=15357,
\]

明显低于 28182，但该估算不代替实际启动、KV block 分配、MTP lookahead 与 preemption
核验。

### 3.2 Scout 必须直接观察的事实

- `max_num_seqs=9` 在两种模式下均可 ready；
- 八个 resident request 在注入前均为 RUNNING，且各已返回至少 16 个输出 token；
- 一个 scheduler iteration 中 resident cohort 的实际 scheduled token 总量 `D`；
- MTP 下每个 resident request 的 scheduled token 数上下界；
- `P=12000` 是否满足 `P <= B-D`，`P=12281` 是否满足 `P > B-D`；
- 峰值 running/waiting 数、KV cache 使用和 cumulative preemption count；
- observer 只读返回原 SchedulerOutput，不改变调度结果。

若 `D` 不落在能够同时满足上述两个不等式的范围内，应结束 S0，并以新的 R3A variant 明确
调整 Prompt 长度。不得在正式 performance lifecycle 中临时改变请求体。

## 4. R3A：Decode-resident admission-cliff matched A/B

建议正式命名：

> P6.3C-R3A Chunked Prefill decode-resident admission-cliff matched A/B

### 4.1 严格 A/B 边界

两侧共同冻结 R3-S0 通过的 `12288/12288/9` 配置、模型、量化、TP/EP、MTP、graph、
block size、Prefix Cache、hybrid-KV repair、async scheduling、请求体和到达控制。唯一 A/B
差异仍为：

```text
--no-enable-chunked-prefill
--enable-chunked-prefill
```

R3A 是 F4 之后的新实验链，不覆盖原 `135168/4096/1` blocked 审计，也不覆盖 F4 机制结论。

### 4.2 分阶段到达协议

每个 trial 按以下时序执行。

1. 通过一个 batched streaming request 同时建立八个 resident Decode：每个请求为
   `256 input tokens + 128 forced output tokens`，`temperature=0`、`ignore_eos=true`。
2. 客户端逐 choice 记录 token arrival timestamp。只有八个 choice 都已返回至少 16 个输出
   token 时，才打开 Prefill injection gate。
3. 通过第二个独立 streaming request 注入一个长 Prefill。记录客户端发送、首个响应 token、
   最后响应 token和 HTTP 完成时间。
4. resident cohort 与长请求全部完成后结束 trial。若任一 resident 在注入前完成、未达到
   16-token gate，或长请求在 gate 前进入 EngineCore，该 trial 标为 arrival-contract invalid，
   不得静默纳入性能统计。

### 4.3 三个实验 cell

| cell | Resident cohort | 注入请求 | 作用 |
| --- | --- | --- | --- |
| resident-only | `8 × (256 in, 128 out)` | 无 | 得到无 Prefill 干扰的 Decode 基线 |
| fit-control | 同上 | `(12000 in, 4 out)` | 预期在 `B-D` 内，Off/On 都可整段准入 |
| admission-cliff | 同上 | `(12281 in, 4 out)` | 预期只比剩余预算多少量 token，辨识 Off 等待与 On partial admission |

`12281+4=12285 < 12288`，单请求满足模型长度约束。`P=12281` 不是任意选择：八个 RUNNING
请求每轮至少各消耗一个 token 时，`B-D <= 12280`，从而构造合法但明确的 admission cliff。

### 4.4 两条证据轨道

**机制轨道。** Observer 开启、profiler 关闭，每个 mode-cell 执行一个有效 trial。除 F4
已有字段外，trace 需要新增：

- request phase：resident prefill、resident decode、injected prefill、injected decode；
- 注入前后的 running/waiting order；
- resident cohort 的 scheduled token 总量 `D`；
- injected request 首次进入 waiting、首次 scheduled 和完成 prefill 的 step index；
- 每个 mixed step 的 decode token、prefill token、总 token 与 chunk ordinal；
- Off 等待 step 数和 On partial-prefill round 数；
- preemption/recompute event。

**性能轨道。** Observer 和 profiler 均关闭，继续采用 Off→On→On→Off 的 fresh-model
生命周期平衡。每个 performance lifecycle 对每个 cell 执行 6 个有效 trial，两个同 mode
lifecycle 合计 12 个有效 trial。cell 顺序使用预生成的平衡序列，不能让同一种 cell 总在冷机
或热机位置。所有 mode 使用逐字节相同的 token payload 与到达门规则。

### 4.5 主要结果指标

**长 Prefill 收益指标：**

- injected request TTFT；
- injection 到首个响应 token的 wall time；
- mechanism 轨道中的 scheduler admission delay 和 waiting step count；
- injected request E2EL；
- trial makespan。

**resident Decode 代价指标：**

- 注入前稳定窗口、注入后干扰窗口与恢复窗口的 P50/P95/P99 TBT；
- 每个 resident request 的 maximum token stall；
- post/pre TBT inflation ratio；
- resident completion-time spread；
- TBT SLO attainment。

固定毫秒阈值容易被当前模型的基础 ITL 混淆。R3A 应同时报告固定阈值和相对阈值，其中相对
阈值以 resident-only 基线为准，例如 `1.25×`、`1.5×` 和 `2×` baseline median TBT。

**系统代价与完整性指标：**

- aggregate output tokens/s；
- total successful request、streamed token exactness 和 retry count；
- KV preemption/recompute count；
- NPU lifecycle、server ready、cleanup 和 keep-alive 精确恢复。

### 4.6 预注册解释规则

R3A 不使用单一 RED/GREEN 代替结果。至少区分四种 outcome。

| outcome | 解释 |
| --- | --- |
| mechanism confirmed, user benefit observed | On 发生 partial admission，长请求 TTFT 实用改善，并完整报告 Decode 代价 |
| mechanism confirmed, trade-off only | On 改善长请求，但 Decode 尾延迟或吞吐代价超过部署容忍范围 |
| mechanism confirmed, no material benefit | 调度变化成立，但长请求指标没有达到预注册实用阈值 |
| mechanism not identified | arrival、running-set、scheduled-token 或请求完整性不足，不能解释性能数字 |

建议把“实用改善”预注册为长请求 median TTFT 至少下降 20%，并报告 paired bootstrap 95%
confidence interval。这个阈值是项目决策阈值，不是外部标准。若样本量不足以支持稳定区间，只能
报告 effect size 和方向，不能写统计显著性。

部署候选还应满足独立代价边界，例如 resident P99 TBT 增幅不超过 10%、aggregate throughput
下降不超过 5%。这些阈值必须在运行前冻结；若项目更重视长请求公平性，可以另建 variant 调整
权重，不能在看到结果后修改成功定义。

## 5. R3B：Chunk-budget calibrated policy comparison

R3A 回答开关的因果作用，但 `B=L` 会形成很大的首个 Prefill chunk，未必是合理部署点。
R3B 允许 On 侧调整 token budget，回答“正确调优后的完整策略是否优于 Off 的合法基线”。它
不是 strict single-variable A/B，必须使用独立任务名和结论。

### 5.1 候选配置

Off 基线保持：

```text
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=9
```

On 侧扫描：

```text
max_model_len=12288
max_num_seqs=9
max_num_batched_tokens ∈ {2048, 4096, 6144, 8192, 12288}
```

这些数值均为 block size 128 的整数倍。`1024` 暂不进入首轮，因为当前八卡大 MoE 模型可能
产生过多 Prefill round；只有 2048 仍显示显著 TBT 压力且系统稳定时，才以新 calibration
variant 向下扩展。

### 5.2 负载与选择规则

R3B 复用 R3A 的 resident-only 与 admission-cliff workload，并只增加预算维度。每个预算先用
observer 验证实际 chunk size、mixed batch 组成、chunk count 和 preemption，再进入无插桩
性能测量。

结果不按单指标排序，而是画出：

- injected-request TTFT 与 resident P99 TBT；
- total output throughput 与 resident P99 TBT；
- SLO goodput 与 offered load；
- Prefill chunk count 与 maximum Decode stall。

只有非支配点进入后续在线流量实验。若所有 On 点都被 Off 基线支配，结论应写为“在当前模型、
硬件和负载下未找到收益点”，而不是继续修改自动 grade。

## 6. R3C：自然到达的混合在线负载

R3C 只比较 Off 合法基线与 R3B 选出的 1–2 个 On Pareto 配置。其目的不是再次证明机制，而是
检验 controlled admission-cliff 的收益能否在自然到达下转化为 SLO goodput。

建议流量由三类请求组成：

- 交互短请求：短输入、128–512 输出 token；
- Decode-resident 请求：128–512 输入、1024 左右输出 token，用于维持稳定 Decode 前台；
- Prefill-heavy 请求：8K–12K 输入、1–32 输出 token，用于产生长 Prefill burst。

到达过程至少包括 Poisson 与 bursty 两种。请求率不能凭空设定固定 QPS，而应先测单配置
saturation throughput，再在其 `0.25×`、`0.50×`、`0.75×` 和 `0.90×` 附近运行。主图应报告
load–P99 TTFT、load–P99 TBT、load–goodput 与 TTFT–TBT Pareto frontier。

“短请求位于长 Prefill 之后”的 HoL 实验暂不作为 R3A 主任务。其结果同时受 running/waiting
状态、FCFS 顺序、partial-prefill concurrency 和 short-prompt queue jumping 影响，容易把多个
机制混成一个收益。只有 R3A/R3B 关闭后，才单独建立 R3D 研究该问题。

## 7. 实现要求

下一开发轮只实现 R3-S0 与 R3A，不一次性开发 R3B/R3C。核心代码应围绕以下实质能力展开：

1. 新的 staged-arrival streaming driver，能够在 resident cohort 全部达到 token gate 后再注入
   独立长请求，并为每个 choice 保存 token-level monotonic timestamp。
2. 在现有只读 scheduler observer 上增加 request phase、running/waiting、injected admission、
   mixed-step token composition 与 preemption 字段；wrapper 必须返回原始 SchedulerOutput。
3. 独立的 mechanism 与 performance 执行入口，性能生命周期不安装 observer/profiler。
4. 生成 token payload manifest、arrival-contract evidence、per-trial/per-request TSV、paired
   summary、资源恢复摘要和有界结果包。
5. 沿用 F4 已验证的 runtime layout、loopback proxy-safe transport、warmup passthrough、MTP 与
   hybrid-KV overlay；不要重新引入已关闭的路径和代理问题。

服务器 AI 可以依据真实 Ascend 环境在独立 worktree 或 task-local overlay 内修复路径、健康
检查、warmup、采集与清理逻辑，并进行能增加证据的重试。任何改变 `12288/12288/9`、resident
cohort、注入 Prompt、token gate、A/B 差异或指标定义的调整，都必须建立新 variant 并保存
before/after diff、SHA、attempt、科学影响与资源恢复证据。

## 8. 决策与下一步

当前最小、最有信息量的下一轮不是大规模在线 sweep，而是 R3-S0 加 R3A：先证明 vLLM 0.22
在真实 Ascend 栈上确实出现“Off 等待、On partial admission”的 Decode-resident admission
cliff，再判断提前准入带来的长请求收益是否值得其 Decode 代价。

若 R3A 机制门关闭且出现明确 trade-off，进入 R3B 调预算；若 R3A 未观察到 admission cliff，
应优先检查实际 `D`、MTP scheduled token、request running state 和 Prompt token exactness，
而不是扩大样本；若 R3A 机制成立但没有长请求收益，则在本项目条件下停止把 matched On/Off
作为性能优化候选，R3B 只在仍有明确部署问题时继续。

## 9. 2026-08-03 实现收束与服务器执行合同

本设计已被落实为可执行实验，而不再停留在方案层。代码提交
`6175ac9f13b9e881bbf09d57c90f3299ae88abb8` 新增 staged-arrival driver、R3 只读
scheduler observer、独立 mode/experiment/server 入口和共同冻结 workload。实现保留 F4 已验证
的 runtime-layout resolver、物化 overlay、MTP/hybrid-KV repair 与 direct-loopback transport，
同时允许从独立 detached worktree 运行，避免与服务器其他会话共享 checkout。

客户端把八个 resident prompt 放在一个 batched streaming request 中，但把 injected Prefill 放在
第二个独立 streaming request 中。resident reader 在后台持续消费 SSE；只有八个 choice 的
streamed token count 都达到 16，主线程才记录 gate timestamp 并发出 injection。每个 choice
保留 token arrival `monotonic_ns`、TTFT、E2EL 和窗口化 TBT；生成文本和 token ID 不落盘。
arrival contract 同时要求 gate 完整、injection timestamp 不早于 gate、注入瞬间 resident stream
仍存活且无读取异常。

R3 observer 仍通过 F4 overlay 的 connector bootstrap 安装，但只在 mechanism lifecycle 启用。
它在调用原始 `Scheduler.schedule()` 前后读取 waiting/running/request snapshot，并从原始
`SchedulerOutput.num_scheduled_tokens` 分解 resident Decode 与 injected Prefill token；额外记录
partial flag、mixed step、schedule order、preempted request IDs 和配置。wrapper 的返回值就是原
`SchedulerOutput`，性能生命周期既不物化 observer，也不设置 trace 目录。

正式任务把 S0 写成执行序列中的科学门，而不是事后颜色判断。`mechanism_01` 与
`mechanism_02` 完成后，driver 立即汇总六个 mode-cell。只有八个 resident running、正的 `D`、
12000 两侧完整准入、12281 Off 首步零 Prefill 等待、12281 On mixed partial admission 和零
preemption 同时成立，才启动后四个 performance lifecycle。S0 失败时保留原始 trace 并结束；
若要改变 Prompt 或容量，必须新建 R3A variant。

性能轨道每 lifecycle 包含一个 warmup 和 18 个 measured trial，每 cell 六次；Off→On→On→Off
合计每 mode-cell 12 个有效样本。六个 lifecycle 总计 682 个 engine request 和 136 个本地 HTTP
request。统计器报告 mode-cell median/P95、两个 order-balanced lifecycle pair 的逐样本 On-Off
TTFT 差和固定 seed 的 10000 次 paired bootstrap median 95% interval。材料完整性与科学结果分开：
完整运行仍可得到 benefit、trade-off 或 no-material-benefit，任何一种都属于有效研究结果。

开发机验证覆盖完整 payload 矩阵、12281-token 精确 body、S0 synthetic scheduler 语义、observer
mixed-step 与 preemption 摘要、bootstrap 和 benefit/cost outcome，共同 P6.3C 合同为 43 项通过；
零 NPU audit 确认 `12288/12288/9`、六 lifecycle、682 engine request、136 HTTP request，以及
canonical Off/On argv 只差 Chunked Prefill 开关。开发机未启动 vLLM 或 NPU；真实容量、`D`、
preemption 与性能仍只由 Ascend 服务器给出。

专用交接已更新为 `通信模块/docs/developer-to-server.P6.md`。服务器 AI 可依据
`docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md` 在独立 worktree/task-local overlay 内修复路径、
代理、stream、observer、warmup 与清理并保留 attempt provenance；改变科学变量时必须显式分支。

## 10. 证据来源

1. 项目内实测：[P6.3C-R2-F4 受控调度实验手稿](./17_P6_3C_R2_F4_Chunked_Prefill_受控调度实验手稿.md)。
2. 官方源码型证据：[vLLM 0.22 V1 Scheduler API/source](https://docs.vllm.ai/en/v0.22.0/api/vllm/v1/core/sched/scheduler/)。其 `schedule()` 先调度 RUNNING，再调度 WAITING；关闭 Chunked Prefill 时，若 WAITING 请求不能完整装入剩余 token budget，则停止该轮 waiting scheduling。
3. 官方配置型证据：[vLLM SchedulerConfig 0.22](https://docs.vllm.ai/en/v0.22.0/api/vllm/config/scheduler/)。`max_num_batched_tokens` 定义单 iteration token 上限，`max_num_seqs` 定义单 iteration sequence 上限。
4. 机制论文：[SARATHI: Efficient LLM Inference by Piggybacking Decodes with Chunked Prefills](https://arxiv.org/abs/2308.16369)。该工作把 chunked prefill 与 decode-maximal batching 的价值表述为 Prefill/Decode 混批与吞吐—时延折中。
5. 系统论文：[Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve](https://arxiv.org/abs/2403.02310)。该工作在 tail-latency constraint 下评估 stall-free scheduling 和 serving capacity；其结果用于提出应测 Pareto frontier，而不是作为本项目 Ascend 收益的替代证据。
