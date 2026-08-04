# P6.3C-R3A：Decode 驻留条件下 Chunked Prefill 的准入收益与时延代价

更新日期：2026-08-04

状态：R3A 实验与证据审查完成；结论为 `mechanism_confirmed_tradeoff_only`；R3B chunk-budget
校准实验已进入开发完成、待服务器执行阶段

## 摘要

已有 P6.3C-R2-F4 实验确认了 Chunked Prefill 在多个 Prefill 请求共同超过 scheduler token
budget 时会改变 token allocation，但没有观察到短请求 TTFT 或 batch throughput 收益。其主要
局限在于竞争双方都处于 Prefill 阶段，未覆盖在线推理中更典型的情形：一组请求已经持续
Decode，新的长 Prefill 此时进入系统。

P6.3C-R3A 在八卡 Ascend 910B1、DeepSeek-V4-Flash W8A8-MTP 和 vLLM 0.22.1 V1
scheduler 上构造了受控 staged-arrival matched A/B。八个 resident 请求先进入 Decode；只有
每个请求都返回至少 16 个 output token 后，客户端才注入一个长 Prefill。两侧共同冻结
`max_model_len=max_num_batched_tokens=12288`、`max_num_seqs=9`、Prefix Cache off、MTP、
graph、模型、量化和请求体，唯一差异是 Chunked Prefill Off/On。

机制轨道直接观察到：resident Decode 在相关 step 共使用 (D=16) 个 scheduler token，剩余
预算为 (R=12288-16=12272)。对 12000-token fit control，Off 与 On 都完整准入；对
12281-token admission cliff，Off 首步给新 Prefill 分配 0 token，而 On 分配 12272 token，
形成 resident Decode 与 partial Prefill 的 mixed step。全轨道无 preemption。

这一机制差异产生了大幅而高度一致的长请求收益：admission-cliff median TTFT 从 Off 的
5802.8 ms 降至 On 的 1292.6 ms，相对下降 77.7%；12 个配对 trial 全部有利于 On，配对
中位差约为 −4.52 s。与此同时，resident 干扰窗口 P99 TBT 从 91.7 ms 增至 719.4 ms，
aggregate output throughput 从 129.6 降至 118.7 token/s。由此可见，在该配置下 Chunked
Prefill 确实消除了整段 Prefill 准入饥饿，但近乎占满整个 batch 的首个 chunk 把代价转移为
Decode 尾延迟和吞吐损失。本实验因此支持一个明确的调度折中，而不是无条件性能改进。

## 1. 研究问题

本实验回答三个相互独立的问题。

1. 当持续 Decode 已占用部分 scheduler budget 时，Chunked Prefill 是否改变一个近长度上限
   Prefill 的准入决定？
2. 如果 On 侧允许 partial admission，这一变化是否转化为 injected request 的 TTFT 改善？
3. 长 Prefill 提前进入同一计算 step 后，resident Decode 的 tail TBT 和系统总吞吐付出什么
   代价？

这三个问题不能合并成“Chunked Prefill 是否更快”。一个策略可以在调度公平性意义上消除
Prefill starvation，同时恶化已有 Decode 流的尾时延；也可以改变 scheduler 行为却不形成
用户可见收益。因此本实验把机制、收益和代价作为三条证据链分别测量。

## 2. 实验设计

### 2.1 系统与共同冻结配置

实验运行于 DeepSeek-V4-Flash-w8a8-mtp，使用 TP8、expert parallel、Ascend W8A8 量化、
MTP `num_speculative_tokens=1`、`FULL_DECODE_ONLY` graph、block size 128 和 async
scheduling。共同调度配置为：

```text
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=9
enable_prefix_caching=false
```

两侧唯一差异为：

```text
--no-enable-chunked-prefill
--enable-chunked-prefill
```

实际 canonical argv 的长度、位置和归一化内容均通过核验；差异只出现在第 28 个参数。性能
轨道没有安装 scheduler observer，也没有开启 profiler。

### 2.2 Staged-arrival workload

每个 measured trial 先建立八个 resident request，每个请求为 256 input token 和 128 forced
output token。resident cohort 通过一个 batched streaming HTTP request 发出，客户端逐 choice
记录 token arrival monotonic timestamp。只有八个 choice 都至少收到 16 个 token，独立的
第二个 streaming request 才会发送 injected Prefill。

实验包含三个 cell：

| cell | resident cohort | injected request | 目的 |
| --- | --- | --- | --- |
| resident-only | (8\times(256+128)) | 无 | resident Decode 基线 |
| fit-control | 同上 | (12000+4) | 验证剩余预算足够时两侧都完整准入 |
| admission-cliff | 同上 | (12281+4) | 构造 (P>B-D) 的整段准入边界 |

`12281+4<12288`，因此 injected request 本身满足模型长度约束；它之所以成为 admission
cliff，不是因为请求非法，而是 resident Decode 已经消耗了当轮 16 个 token。

### 2.3 执行与样本结构

实验使用六个 fresh-model lifecycle。前两个为 observer-enabled mechanism scout，顺序是 Off、
On；只有机制合同成立后，才执行 Off→On→On→Off 四个 observer-free performance lifecycle。
每个 performance lifecycle 对每个 cell 运行六个有效 trial，因此每个 mode-cell 有 12 个样本。

最终完成：

- 6/6 fresh-model lifecycle；
- 682/682 engine request；
- 136/136 local HTTP request；
- 0 retry；
- 全部 lifecycle server-ready、exit 0、cleanup clean；
- NPU 0–7 的 keep-alive 精确停止并恢复，16 个 marker 完整；
- 端口 7000 无残留 listener，无 vLLM 残留进程。

## 3. 机制结果

在注入发生后的首个相关 scheduler step，八个 resident request 均处于 RUNNING，resident
Decode 总 scheduled token 为：

\[
D=16.
\]

因此该 step 留给 WAITING Prefill 的最大预算为：

\[
R=B-D=12288-16=12272.
\]

观察结果与调度假设逐项吻合：

| cell | mode | resident running | (D) | injected scheduled | partial | mixed |
| --- | --- | ---: | ---: | ---: | --- | --- |
| fit-control 12000 | Off | 8 | 16 | 12000 | false | true |
| fit-control 12000 | On | 8 | 16 | 12000 | false | true |
| admission-cliff 12281 | Off | 8 | 16 | 0 | false | false |
| admission-cliff 12281 | On | 8 | 16 | 12272 | true | true |

Off 并没有降低 RUNNING Decode 的调度优先级；它是在 WAITING Prefill 不能完整装入 (R) 时
拒绝本轮准入。On 同样先给 resident Decode 分配 token，但允许新 Prefill 使用全部剩余预算。
因此两侧差异可以更准确地描述为 whole-Prefill admission 与 partial admission 的差异。

fit control 是这一解释的关键反事实。若 On 的收益只是模型生命周期、缓存热度或客户端时序导致，
则 12000-token cell 也应出现同方向的大幅变化；实际两侧都在首步完整准入，并没有出现
admission-cliff 量级的差异。

## 4. 性能结果

### 4.1 Injected request TTFT

admission-cliff 的 median TTFT 为：

| mode | median TTFT | P95 TTFT |
| --- | ---: | ---: |
| Off | 5802.8 ms | 6000.4 ms |
| On | 1292.6 ms | 1394.2 ms |

相对变化为：

\[
\frac{1292.6-5802.8}{5802.8}=-77.7\%.
\]

两个 fresh-model pair 中的 12 个 matched trial 全部得到负的 On−Off TTFT difference。按固定
seed 633、10000 次 trial-pair bootstrap 复算，中位差约为 −4517.5 ms，95% interval 约为
[−4566.9, −4452.5] ms。由于每组六个 trial 共享同一 fresh-model lifecycle，这一区间只作为
方向稳定性的描述，不把 12 个样本表述为完全独立的统计重复。

### 4.2 Fit control

fit-control median TTFT 为 Off 885.2 ms、On 902.3 ms，配对中位差约 +1.4 ms；12 个 trial
中只有 5 个有利于 On，配对区间跨过零。这个结果说明：当完整 Prompt 可以装入剩余 budget、
没有 partial-admission 压力时，单纯打开开关并不会产生 admission-cliff 上的 4.5 s 收益。

### 4.3 Resident Decode 和总吞吐代价

admission-cliff 下 resident interference-window P99 TBT 中位数为：

| mode | resident P99 TBT | aggregate output TPS |
| --- | ---: | ---: |
| Off | 91.7 ms | 129.6 |
| On | 719.4 ms | 118.7 |

On 相对 Off 的 resident P99 TBT 增幅约 684%，aggregate output TPS 下降约 8.5%，分别超过
预注册的 10% 和 5% 部署代价边界。R3A 中 On 的首个 Prefill chunk 为 12272 token，几乎占满
整个 scheduler budget。虽然 resident Decode 在调度顺序上先被选中，它仍要与一个计算量很大
的 Prefill chunk 共同经历该 device step；“调度优先”因而不等价于“token arrival 不发生长
stall”。

原 R3A runner 还有一个不影响上述正式结论、但必须在后续研究中修正的指标实现问题：
`resident_max_stall_ms` 曾保存 `max(per-request ITL p99)`，而不是真实的最大相邻 token gap。
本轮已把 future-run 定义改为逐 timestamp 计算最大 gap，并新增服务器端零 NPU 复分析器，从
R3A raw JSONL 重建 per-trial P50/P95/P99/max、pre/interference/recovery window 和 paired
cost effect。R3A 的正式结论使用的是 interference P99 TBT 和 aggregate TPS，因此这一修正不
推翻 `mechanism_confirmed_tradeoff_only`，但在 R3B 选择 Pareto 点前必须补齐真实 max stall。

## 5. 讨论

R3A 的主要科学价值是把“Chunked Prefill 是否有收益”转化为一个更精确的调度问题。在 Off
策略下，长 Prefill 必须等待能够完整准入的时刻；当 resident Decode 持续消耗少量 budget 时，
一个只比 (B-D) 多 9 token 的请求可能等待数秒。On 立即使用 12272-token partial chunk，
消除了这种离散的 admission cliff，因此 TTFT 收益并不是小幅的 kernel 优化，而是调度状态
转换带来的数秒级差异。

同一个机制也解释了代价。`B=12288` 允许首个 chunk 极大，On 并非让 Prefill 对 Decode “无
干扰”，而是把一个长计算 step 提前到 resident Decode 尚未完成时。R3A 因而揭示的不是开关
本身的最终部署答案，而是一个可调控制量：On 侧 `max_num_batched_tokens` 决定首个 chunk 的
上限，并可能在 Prefill 公平性、Decode tail latency 与吞吐之间形成 Pareto frontier。

这直接导出 R3B 的研究问题。R3B 不再重复 Off/On 机制证明，而是保持 Off 合法基线
`B=12288`，在 On 侧扫描 `B∈{2048,4096,6144,8192,12288}`。较小 B 预期会把 Prefill 分成
更多轮、增加 injected TTFT，却可能显著缩短 resident token stall；是否存在同时满足 TTFT
改善、P99 TBT 和吞吐边界的配置只能由实测回答。

## 6. 有效性边界

本结果可以支持：在固定 Ascend/vLLM 栈、`12288/12288/9`、八个 resident Decode、16-token
injection gate 和受控 12281-token Prefill 下，Chunked Prefill 改变准入、显著降低 injected
TTFT，并产生严重 Decode tail-latency 与 throughput 代价。

本结果不能支持：

- 自然 API arrival 下的普遍行为；
- 任意 resident 数量、输出长度或 Prompt 分布；
- 其他 token budget 的收益或代价；
- 生产环境的 P99 SLO capacity；
- Chunked Prefill 普遍优于 Off；
- 12 个 trial 是 12 个完全独立系统重复。

原 `135168/4096/1` blocked 审计、F4 controlled co-arrival 机制结论和 R3A trade-off 是三条
不同的 evidence lineage，任何一条都不覆盖另外两条。

## 7. 结论

在 decode-resident admission cliff 上，Chunked Prefill On 把一个等待完整准入的 12281-token
Prefill 转化为首轮 12272-token partial admission，使 median TTFT 降低 77.7%。这一收益在 12
个配对 trial 中方向一致，且 fit control 不出现相同现象，机制归因清晰。代价是 resident P99
TBT 增至约 7.8 倍、aggregate output TPS 下降 8.5%。因此 R3A 证明了 Chunked Prefill 可以
解决特定的长 Prefill admission starvation，但 `B=12288` 不是可直接接受的部署点。下一步应
校准 chunk budget 并寻找 Pareto operating point，而不是把本结果压缩成简单的成功或失败标签。

## 8. 数据与代码可用性

开发机收到的 14-file bounded package 位于：

```text
/Volumes/SSD1/Inbox/2026-08-04/p6_3c_r3a_2026_0803_run01
```

服务器保留约 490 MB raw scheduler trace、token timestamp 和 log。代码入口包括
`run_deepseek_p6_3c_r3a_decode_resident.py`、`p6_3c_r3_decode_resident_observer.py` 和
R3A workload。零 NPU 代价复分析器为
`analyze_deepseek_p6_3c_r3a_costs.py`；R3B 的完整策略校准合同见
`p6_3c_r3b_chunk_budget_pareto.yaml`。
