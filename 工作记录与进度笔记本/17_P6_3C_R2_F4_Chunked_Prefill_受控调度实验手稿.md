# P6.3C-R2-F4：受控原子共到达条件下 Chunked Prefill 调度机制实验手稿

日期：2026-08-03

实验执行：2026-07-31

证据接收与再归档：2026-08-01 至 2026-08-03

状态：`accepted_chunked_prefill_scheduler_mechanism_observed`

## 摘要

原 P6.3C 只能证明，在 P6.1 参考配置 `max_model_len=135168`、
`max_num_batched_tokens=4096`、`max_num_seqs=1` 完全不变时，Chunked Prefill Off
侧无法启动，因而不能形成 131K+c1 的严格单变量对照。该结论不回答 Chunked Prefill
能否在另一组共同冻结、具有明确调度压力的环境中改变请求准入与 token 分配。为此，本实验
构造了一个容量可行且具有机制辨识力的双请求场景：两侧共同冻结
`max_model_len=max_num_batched_tokens=12288`、`max_num_seqs=2`，显式关闭 Prefix
Cache，并保持模型、量化、并行策略、MTP、graph mode、block size、请求体和运行时修复一致；
唯一 A/B 差异为 Chunked Prefill 的显式 Off/On 开关。

实验包含 `4K+4K` 无压力对照、`10K+6K` 非对称压力和 `8K+8K` 对称压力三个 cell。
为消除 OpenAI multi-prompt 在 EngineCore 中逐条到达造成的调度可见性偏差，两个 measured
request 在两侧共同使用 request-ID-normalized atomic admission，使其在同一次首次
`Scheduler.schedule` 前同时可见。机制轨道使用只读 scheduler observer；性能轨道关闭 observer
和 profiler，并按 Off→On→On→Off 运行四个 fresh lifecycle。六个 lifecycle 共完成
90/90 engine request、48/48 batched HTTP call、42/42 measured pair release，且 6/6
首轮调度合同与资源恢复全部闭合。

机制结果与设计假设一致。无压力 cell 中，两侧均在首轮调度 `4096+4096`，没有 partial
prefill。两个压力 cell 的 Off 侧均先整段准入第一个请求并延后第二个请求；On 侧则在首轮把
剩余 token budget 分配给第二个请求，分别形成 `10240+2048` 和 `8192+4096`，第二个请求
随后完成剩余 prefill。由此直接观察到 Chunked Prefill 在总 Prefill token 超过 batch budget
时改变 scheduler token allocation。固定性能样本没有显示短请求 TTFT 或 batch throughput
收益：非对称压力下 On-Off 的短请求平均 TTFT 为 `+43.327 ms`，三组 batch throughput
差分别为 `-0.083`、`-0.152` 和 `-0.180 token/s`。这些性能数字只描述本实验的受控原子
共到达样本，不支持自然生产到达、统计显著性、普遍收益或普遍负面结论。

**关键词：** Chunked Prefill；LLM serving；scheduler；prefill；atomic co-arrival；
Ascend；vLLM

## 1. 研究问题与实验定位

### 1.1 原参考配置为什么不能回答机制问题

Chunked Prefill Off 侧的启动约束要求 batch token budget 不小于最大模型长度，即

\[
B \geq L.
\]

单请求又满足输入长度不超过最大模型长度：

\[
P \leq L.
\]

因此，如果只把原配置的 `max_num_batched_tokens` 提高到足以启动 Off 侧，同时仍只发送一个
请求，则必然有 `B >= P`。单个输入可以完全装入一个调度批次，Chunked Prefill 即使开启也
不一定产生实际分块。这种配置在形式上合法，却缺少机制辨识力。

本实验不修改或覆盖原 P6.3C 的审计结论。原
`blocked_p6_3c_not_strict_single_variable` 继续表示：`135168/4096/1` 参考配置不能只切换
Chunked Prefill 开关形成严格 A/B。P6.3C-R2-F4 是独立命名、共同重新冻结的 scheduler-pressure
实验，研究对象是多请求总 Prefill token 超过 batch budget 时的调度行为。

### 1.2 研究问题

实验回答两个层次不同的问题。

第一，在两个请求确定同时对 scheduler 可见、且总 Prefill token 超过共同冻结预算时，
Chunked Prefill 是否改变首次调度的 token 分配和后续 prefill 轮次？这是机制问题，也是本实验
的主要问题。

第二，在同一受控共到达环境中，这种调度变化是否伴随短请求 TTFT、请求完成均衡性或 batch
throughput 的描述性变化？这是次要的性能观察，不预设正向收益，也不承担统计推断。

## 2. 方法

### 2.1 测试平台与共同冻结配置

| 项目 | 冻结值 |
| --- | --- |
| 服务器 | Atlas 800T A2，8 × Ascend 910B1 |
| 模型 | `DeepSeek-V4-Flash-w8a8-mtp` |
| 推理框架 | vLLM `0.22.1+empty`；vLLM-Ascend `0.22.1rc1` |
| 量化 | Ascend W8A8 |
| 并行 | tensor parallel size=8，expert parallel=true |
| MTP | `num_speculative_tokens=1` |
| graph mode | `FULL_DECODE_ONLY` |
| scheduler | async scheduling=true，block size=128 |
| 容量 | `max_model_len=12288`，`max_num_batched_tokens=12288`，`max_num_seqs=2` |
| Prefix Cache | 两侧显式关闭 |
| hybrid-KV repair | 两侧加载完全相同的 task-local repair |
| profiler | 全部关闭 |
| 输出长度 | 每个请求固定 64 tokens |

服务器在六个 lifecycle 中均报告 `15.01 GiB` available KV cache、`28182` GPU KV cache
tokens、模型权重最大观测值 `39.5764 GB` 和理论 maximum concurrency `2.29`。六次服务均
ready，说明 `12288/12288/2` 是本环境中可执行的共同容量点。上述启动资源数字只用于确认
实验可运行，不被解释为 KV 容量上限或物理 HBM headroom。

### 2.2 单变量 A/B

两侧 normalized server argv 长度相同，唯一差异出现在第 28 个参数：

```text
Off: --no-enable-chunked-prefill
On:  --enable-chunked-prefill
```

五组跨 lifecycle 的 argv 对照均满足 `delta_count=1`。resolved config 同时证明 Off/On
分别解析为 `False/True`，且 Prefix Cache 在两侧均为 `False`。因此，atomic admission、
request-ID normalization、hybrid-KV repair 和 loopback transport 都是两侧共同的实验环境，
不是第二个 A/B 变量。

### 2.3 调度压力 cell

| cell | 同时到达的输入 | 总 Prefill tokens | 相对 12288 预算 | 设计作用 |
| --- | ---: | ---: | --- | --- |
| `no_pressure_4k_4k` | 4096 + 4096 | 8192 | 低于预算 | 检查无压力时两侧是否保持一致 |
| `asymmetric_pressure_10k_6k` | 10240 + 6144 | 16384 | 超预算 4096 | 观察长请求后短请求能否取得剩余预算 |
| `symmetric_pressure_8k_8k` | 8192 + 8192 | 16384 | 超预算 4096 | 观察对称请求的调度分配与完成差 |

每个单请求都不超过 `max_model_len=12288`，而两个压力 cell 的总 Prefill token 明确超过
`max_num_batched_tokens=12288`。这一结构同时满足单请求合法性和多请求预算竞争。

### 2.4 原子共到达控制

早期 F2 结果表明，一个 OpenAI multi-prompt HTTP 请求虽然携带两个 prompt，内部仍会被拆成
两个 `engine_client.generate()` 调用。EngineCore 收到第一个请求后即可触发 scheduler work，
第二个请求可能直到下一 step 才进入 waiting queue。此时总 token 数虽然超预算，两个请求却没有
在同一次调度决策中竞争预算，因而无法辨识 Chunked Prefill。

F4 在 Off 和 On 两侧共同安装 task-local atomic admission。它只识别带 F4 实验标签的 measured
pair。运行时实际 request ID 必须符合
`cmpl-<canonical-pair>-<0|1>-<8-hex-suffix>`；controller 同时保存 actual ID 和 canonical
ID。第一个 pair member 在进入原始 `EngineCore.add_request` 前短暂等待，第二个 member 到达后
按 index 0→1 连续释放。普通请求和 singleton warmup 直接进入原始路径。controller 不修改
scheduler 的 chunking 逻辑、token budget 或返回值。

这是一种实验性 scheduler-visibility 控制，用于确保两个请求在首次 schedule 前共同可见。它不
模拟自然生产流量，也不应部署为服务策略。42 个 measured pair 的共同 barrier 等待中位数为
`4.664 ms`，最大值为 `6.485 ms`；该等待被单独审计，并同时存在于 Off 与 On。

### 2.5 两条证据轨道

机制轨道包含两个 fresh lifecycle，顺序为 Off→On。每个 lifecycle 执行一个 4K warmup 和三个
measured pair，共 7 个 engine request、4 个 batched HTTP call。只读 scheduler observer 记录
首次 waiting order、每轮 scheduled token、prefill round 和 partial prefill count。机制轨道的
接受条件是 6 个 mode-cell 首轮合同全部精确匹配，同时满足 Off 三个 cell 无 partial prefill、
On 两个压力 cell 有 partial prefill、无压力 cell 两侧均无 partial prefill。

性能轨道包含四个 fresh lifecycle，顺序为 Off→On→On→Off。每个 lifecycle 执行一个 4K
warmup，以及三个 cell 各三次 measured pair，共 19 个 engine request、10 个 batched HTTP
call。scheduler observer 和 profiler 均关闭，只保留两侧共同的 atomic-pair release audit。
记录指标包括 TTFT、E2EL、TPOT、ITL、batch output tokens per second、两个请求的完成时间差，
以及非对称 cell 中 6K 短请求的 TTFT。

六个 lifecycle 合计 90 个 engine request、48 个 batched HTTP call 和 42 个 measured pair；
14 份 canonical request body 在各 mode 与 lifecycle 间逐字节复用。输出文本和生成 token ID
没有进入结果包。

## 3. 执行过程与实验适配

### 3.1 从容量可行到机制可辨识

实验链的多次修订分别关闭了不同的方法学缺口。R1 使用 `69632/69632/2`，但服务器启动时估算
需要 `36.66 GiB` KV cache，实际只有 `8.27 GiB`，因此没有进入 scheduler。R2 将共同容量校准
为 `12288/12288/2`。随后，R2 run01 修复混合 editable/site-packages 布局，F1 修复 localhost
健康检查被 HTTP 代理误路由，F2 暴露两个内部请求没有原子共到达，F3 又发现 vLLM 在 canonical
request ID 后追加 8 位十六进制 suffix。F4 的 request-ID normalization 与 atomic admission
最终使设计中的预算竞争真实发生。

这些失败不构成 Chunked Prefill 的负面证据。它们分别对应容量、运行时布局、传输、调度可见性
和 request identity 问题。每次修订都保持研究问题不变；只有共同实验环境发生实质变化时才使用
新的 R/F lineage，历史结果没有被后续成功覆盖。

### 3.2 服务器现场 warmup 修复

F4 首次执行时，singleton warmup 的 request ID 也匹配 measured-pair parser。由于 warmup 只有
一个 prompt，第一个 member 会等待不存在的第二个 member，最终超时。服务器助手在 task-local
副本中加入 warmup passthrough：规范化 pair key 以 `_warmup` 结尾时，立即调用原始
`EngineCore.add_request`。成功执行发生在报告的第 3 个 attempt。

修复前 controller SHA-256 为
`6cf48b4f96d779a108bac30aba46bf075ba5e72fd39526d76f9699c1b3ee4a9d`；成功执行和仓库正式发布
的 controller SHA-256 均为
`a396ba49f94922592854192de139e497232e8952f718cc791d36e372a7a42f4b`。该修复只改变 singleton
warmup 的控制路径，没有改变 42 个 measured pair 的准入语义，也没有改变 cell、请求体、
A/B 开关、指标或调度器实现。共享工作树在实验后恢复为 clean。

### 3.3 运行时隔离与服务可用性

运行环境同时包含 editable vLLM 和环境内 vLLM-Ascend。任务通过目标 Python 的
`importlib.find_spec` 解析真实包路径，在 task-local overlay 中物化 1645 个文件和 265 个目录；
`symlink_count=0`、`realpath_escape_count=0`，基础环境和 site-packages 均未修改。MTP repair、
hybrid-KV repair、atomic admission 和机制 observer 均在 overlay 中安装。

六个 lifecycle 全部完成服务启动。loopback health、metrics 和 streaming request 均固定访问
`http://127.0.0.1:7000`，显式绕过环境代理；代理变量名被记录，但其值和凭据没有进入证据包。
这一控制消除了 F1 的本地请求误走外部代理问题。

### 3.4 A1 零 NPU 接收与再归档

F4 原始 finalizer 把 atomic admission capability 与任务名中的 `_r2_f3_` 子串绑定。F4 明明在
六个 lifecycle 中启用了 `P6_3C_ATOMIC_PAIR_ADMISSION=1`，却被旧逻辑误判为 runtime gate
不完整，产生
`red_p6_3c_r2_f4_chunked_prefill_mechanism_evidence_incomplete`。这个 RED 是分类错误，不是
请求、共到达或机制证据失败。

F4-A1 没有重新使用 NPU，也没有产生新样本。它只读验证服务器保留的 F4 raw result，改为从
实际 execution capability、full execution、runtime/transport、co-arrival 和 mechanism
证据形成结论。源结果目录包含 23 个顶层文件、81383 bytes；A1 派生小包包含 20 个文件、
59951 bytes。源任务、90/90 请求、48/48 batch、42/42 release、request-ID normalization、
mechanism、terminal state 和资源恢复等 13 项验证全部通过。

A1 与开发机已接收的 F4 小包共有 19 个同名文件，其中 15 个机制、性能、请求、lifecycle、
transport、runtime 与恢复文件逐字节相同。只有 `environment_and_hashes.json`、
`grading_inputs.json`、`result_summary.md` 和 `first_failure_excerpt.txt` 被重新生成，并新增
`adaptive_execution_review.json`。因此 A1 改变的是来源解释和分类，不是原始实验观测。

## 4. 结果

### 4.1 完整性与可执行性

| 轨道 | lifecycle | 顺序 | request | batch | observer | exit / cleanup |
| --- | ---: | --- | ---: | ---: | --- | --- |
| 机制 | 2/2 | Off→On | 14/14 | 8/8 | 只读开启 | 全部 `0 / clean` |
| 性能 | 4/4 | Off→On→On→Off | 76/76 | 40/40 | 关闭 | 全部 `0 / clean` |
| 合计 | 6/6 |  | 90/90 | 48/48 |  | 全部成功 |

42/42 measured pair 均恰好释放一次，failure event 为 0。六个机制 mode-cell 的 actual ID
合同、canonical waiting order、scheduled token map 和 total scheduled token 均精确匹配预期。
三次 lifecycle 从 shutdown trace 取得 clean terminal state，另外三次从最后一个 post-release
checkpoint 取得 `completed=expected`、`pending=0`、`failed=0`。因此 shutdown callback 只出现
3/6 并不表示另三个 lifecycle 未清理。

### 4.2 首轮调度与分块行为

| cell | Off 首轮 scheduled tokens | On 首轮 scheduled tokens | 后续行为 | 机制判断 |
| --- | --- | --- | --- | --- |
| 4K+4K | 4096 + 4096 | 4096 + 4096 | 两请求均一轮完成 prefill | 无压力时两侧一致 |
| 10K+6K | 10240 + 0 | 10240 + 2048 | Off 的 6K 请求下一 step 整段准入；On 的 6K 请求以 2048 + 4096 两轮完成 | On 出现 partial prefill |
| 8K+8K | 8192 + 0 | 8192 + 4096 | Off 的第二个 8K 请求下一 step 整段准入；On 的第二个请求以 4096 + 4096 两轮完成 | On 出现 partial prefill |

Off 三个 cell 的每个请求都只有一次 prefill round，partial prefill round count 全部为 0。On 的
无压力 cell 同样没有 partial prefill；两个压力 cell 的第二个请求均有两次 prefill round，其中
一次为 partial prefill。该模式同时满足正对照和负对照：机制只在总 Prefill token 超过预算时
出现，不是 observer 或 atomic admission 对所有请求造成的普遍分轮。

这组结果直接回答了主要研究问题。在共同冻结的多请求压力环境中，Chunked Prefill 确实改变
scheduler 的 token allocation。Off 采用整段准入或串行等待；On 把当前 step 的剩余预算分配
给后续请求，并在下一 step 完成其剩余 prefill。

### 4.3 性能结果

下表按每个 mode-cell 的 12 个 measured request、6 个 measured batch 聚合。差值统一定义为
On minus Off；正的时延差表示 On 更慢，负的 throughput 差表示 On 更低。

| cell | Off TTFT mean (ms) | On TTFT mean (ms) | ΔTTFT (ms) | ΔE2EL (ms) | ΔTPOT (ms) | Δbatch throughput (token/s) | Δcompletion gap (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4K+4K | 543.457 | 541.482 | -1.975 | +128.778 | +2.075 | -0.083 | +0.002 |
| 10K+6K | 926.588 | 989.453 | +62.865 | +243.385 | +2.865 | -0.152 | +3.976 |
| 8K+8K | 834.878 | 925.437 | +90.558 | +282.495 | +3.047 | -0.180 | +17.752 |

非对称压力 cell 中，6K 短请求的平均 TTFT 从 Off 的 `1155.443 ms` 增至 On 的
`1198.770 ms`，差值为 `+43.327 ms`。两个顺序平衡 pair 的短请求差值分别为
`+34.854 ms` 和 `+51.800 ms`，方向一致。因此，本固定样本没有显示 Chunked Prefill 降低
短请求首 token 等待。

压力 cell 的总体 TTFT 差值在两个平衡 pair 中也同向：10K+6K 分别为 `+59.568 ms` 和
`+66.161 ms`，8K+8K 分别为 `+85.130 ms` 和 `+95.986 ms`。相比之下，batch throughput
和 completion gap 的 pair-level 方向并不完全一致。例如，10K+6K throughput 在 pair 01 为
`+0.099 token/s`，在 pair 02 为 `-0.404 token/s`；completion gap 分别为 `-8.085 ms`
和 `+16.038 ms`。因此，当前数据不足以声称 Chunked Prefill 改善或恶化调度公平性。

机制变化没有自动转化为用户侧性能收益。一个可能的解释是，在本模型、64-token decode、
12288-token budget 和受控共到达条件下，增加 prefill 轮次与调度切换的成本抵消了潜在的并行
准入收益。然而，本实验没有对 scheduler overhead、kernel timeline 或队列等待进行因果分解，
该解释只能作为后续假设，不能作为已证实归因。

### 4.4 资源恢复

正式实验停止并恢复 NPU 0–7 的低优先级 keep-alive。退出后共有 16 个 marker，恢复卡集合与
停止卡集合完全相同；端口 7000 listener count 为 0，vLLM residual process count 为 0，
tracked worktree clean，experiment exit code 为 0。资源证据支持本轮数据来自完整结束的实验，
而非残留服务或未清理进程。

## 5. 讨论

### 5.1 主要发现

本实验最重要的结果不是“Chunked Prefill 提升了性能”，而是建立了机制存在性的直接证据。
在两个请求首次调度前同时可见且总 Prefill token 超过预算时，On 侧会利用当前 step 的剩余
budget 为第二个请求调度 partial prefill；Off 侧则要求请求整段满足剩余预算，否则将其延后。
无压力 cell 的一致行为排除了“只要开启 Chunked Prefill 就必然多轮 prefill”的过度解释。

性能轨道给出的结论同样具有研究价值。在这组固定样本中，On 侧没有带来短请求 TTFT 或 batch
throughput 收益，并在两个压力 cell 中表现出更高的平均 TTFT。机制成立而优化收益未出现，说明
“调度过程发生变化”和“用户指标改善”是两个必须分开验证的问题。后续研究不应仅凭机制文档或
partial-prefill trace 推断性能收益。

### 5.2 与 F2/F3 的关系

F2 的 90/90 request 成功并不能回答本实验的问题，因为两个内部 request 在相邻 scheduler step
到达。F3 安装了 atomic admission，但实际 request ID 的 8-hex suffix 使全部 42 个 measured pair
绕过 controller。F4 同时修复运行时 request identity 和分析侧 canonical mapping，才使“两个请求
在同一首次调度中竞争预算”成为可观察事实。

这条 lineage 表明，服务层 batch、EngineCore input queue 和 Scheduler waiting queue 是不同的
实验层级。只在客户端同时发出请求，不能自动等价为 scheduler 共到达。对 continuous batching
或 prefill scheduling 的机制实验，必须直接记录首次 waiting set 和 scheduled-token map。

### 5.3 A1 的科学意义

A1 说明自动 grade 应被视为证据索引，而不是科学结论本身。F4 的原始 RED 来自 task-ID 字符串
推断 capability 的分类错误；请求、机制和恢复证据已经完整。A1 保留原 RED 作为 provenance，
同时给出 `candidate_green_p6_3c_r2_f4_chunked_prefill_request_id_normalized_atomic_coarrival_matched_ab`
和开发机接受的
`accepted_chunked_prefill_scheduler_mechanism_observed`。这种处理既不篡改历史输出，也避免
让错误分类覆盖实质实验事实。

服务器现场 warmup 修复也体现了同一原则。修复针对实验控制面的单例死锁，执行字节与仓库发布
字节一致，且没有改变 measured pair 或科学变量。允许服务器助手在真实环境中保留 diff、SHA、
attempt 和科学影响后继续执行，比机械遵守失真的冻结限制更有利于取得可解释证据。

## 6. 有效性边界与局限

**受控到达而非自然流量。** atomic admission 人为保证两个 tagged request 同时对 scheduler
可见。本结果证明受控调度压力下的机制，不证明自然 OpenAI API 到达分布中出现相同频率或收益。

**样本规模有限。** 性能轨道每个 mode-cell 只有 12 个 request 和 6 个 batch，且采用固定的
Off→On→On→Off 顺序，没有随机化、置信区间或显著性检验。性能数字只能作描述。

**工作负载范围有限。** 只覆盖 12288-token budget、三种双请求 cell、64-token decode、
`max_num_seqs=2` 和当前 DeepSeek-V4-Flash W8A8-MTP 栈。不同 batch budget、并发度、输出长度、
模型或自然 arrival process 可能产生不同结果。

**没有性能归因。** 性能轨道有意关闭 observer 和 profiler，避免插桩干扰。因此，本实验可以报告
用户侧时延和吞吐，但不能把差异归因于某个 operator、NPU 利用率、HBM traffic 或 scheduler
overhead。

**A1 派生视图存在一个归档瑕疵。** A1 再终结时没有把源结果的 `bodies/` 目录映射进派生视图，
使派生 `grading_inputs.json` 中 `body_pairing_exact` 和 `manifest_files_exact` 为 false。原 F4
结果中两项均为 true，`request_body_manifest.json` 在 F4 与 A1 间逐字节相同，且 A1 的 13 项
source validation 全部通过。该问题不改变请求或机制结论，但后续再归档工具应补齐只读 body
映射，避免把派生视图缺文件误写成源实验缺证据。

## 7. 结论与后续研究

P6.3C-R2-F4 在 `12288/12288/2`、Prefix Cache off、受控 atomic co-arrival 的三组双请求
环境中，直接观察到 Chunked Prefill 改变超预算请求的 scheduler token allocation。Off 三组均
没有 partial prefill；On 只在两个压力 cell 出现 partial prefill；无压力 cell 两侧一致。该结果
足以关闭受控 scheduler-pressure 下的机制门。

固定性能样本没有显示短请求 TTFT 或 batch throughput 收益，因而本轮不把 Chunked Prefill
列为已验证的正向性能优化。更准确的项目表述是：**机制已观察到，性能收益未观察到。**

原 `135168/4096/1` P6.3C strict-single-variable block 继续保留。它与 F4 分别回答“原参考配置
能否直接 A/B”和“共同重新冻结的多请求压力环境中机制是否发生”两个问题，不能相互覆盖。

F4 不需要为追求自动标签再次使用 NPU。若继续研究，应建立新的实验问题，例如带可复现到达间隔
分布的 natural-arrival replay、不同 `max_num_seqs`/batch budget 的 scheduler calibration，或
将 prefill scheduler trace 与轻量性能归因分开的新 variant。这些工作必须使用新的 task ID，并
明确其相对 F4 改变的 arrival process、容量或测量定义。

## 8. 数据与证据可用性

服务器原始结果保留于：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/
p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01/
```

开发机收到的 F4 小包：

```text
/Volumes/SSD1/Inbox/2026-08-01/
p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01/
```

A1 零 NPU 接收包：

```text
/Volumes/SSD1/Inbox/2026-08-03/
p6_3c_r2_f4_a1_adaptive_acceptance_2026_0801/
```

A1 包共 20 个文件、59951 bytes。主要证据包括
`adaptive_execution_review.json`、`mechanism_scheduler_summary.json`、
`mechanism_atomic_pair_first_step.tsv`、`mechanism_request_chunk_summary.tsv`、
`performance_mode_cell_summary.tsv`、`performance_order_balanced_pairs.tsv`、
`atomic_pair_admission_summary.json`、`atomic_pair_release_summary.tsv` 和
`resource_recovery_summary.json`。包中不含生成文本或生成 token ID。

对应实验合同位于：

```text
benchmarks/deepseek_v4_flash/workloads/
p6_3c_r2_f4_request_id_normalized_atomic_coarrival_matched_ab.yaml

benchmarks/deepseek_v4_flash/workloads/
p6_3c_r2_f4_a1_adaptive_acceptance.yaml
```
