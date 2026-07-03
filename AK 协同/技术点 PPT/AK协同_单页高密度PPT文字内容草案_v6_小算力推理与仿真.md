# A+K 协同单页高密度 PPT｜文字内容草案 V6

> 用途：基于 V5 与 Deep Research 反向回顾报告，重写一页 PPT 中应放的具体文字，不生成 PPT。  
> 本版改动：从“泛化 A+K 协同”收敛到两个首要任务：  
> 1）小算力上运行大模型：CPU 可卸载计算、MoE 专家权重卸载/预取、KV/Prefix/状态容量管理、冷热状态计算、流水线互联带宽与并发提升；  
> 2）推理算力仿真系统：用硬件实测 + 工作负载 trace + 状态对象模型，反推 CPU / 内存 / 存储 / 互联 / NPU 规格。  
> 页面逻辑：顶部一句话结论；中部 4 个技术方向卡片；底部一条“落地优先级 + 硬件诉求”横条。  
> PPT 主页面建议不放论文名；论文与系统映射可放讲稿或备份页。

---

## 0. 页面标题与主结论

### 标题

**A+K 协同异构推理：面向小算力大模型的计算卸载、状态分层与仿真反推**

### 副标题

从“模型放得下”走向“推理跑得快、状态调得准、硬件规格可反推”

### 顶部一句话结论

**A+K 协同的核心不是简单把模型搬到 CPU/DDR/SSD，而是在 Ascend NPU 主算保持连续的前提下，把 gate / router / 冷专家 / KV 选择 / 状态恢复 / I/O 编排 / trace 仿真交给 Kunpeng CPU 与多级内存系统，形成可验证、可预测、可扩并发的小算力推理底座。**

### 场景牵引短句

- **AI Coding Agent：**744B MoE、M 级上下文、长会话重入；核心矛盾是专家权重与 KV 同时挤占近端内存，prefix/KV/专家恢复决定 TTFT、TPOT 与最大并发。
- **办公助手 Agent：**30B/70B/120B、本地文档、多轮上下文；核心矛盾是重复前缀复用、冷热 KV 判断、低尾延迟交互和长期会话状态保留。
- **多模态生成：**Helios-14B、Wan-27B、AR+DiT/DiT/VAE 流水；核心矛盾是主生成算力、rolling KV / latent / noise cache / 视频后处理状态共同造成容量与带宽压力。
- **系统目标：**大模型放得下、冷路径可卸载、热状态留得住、数据回得快、并发上得去、规格可反推。

---

## 1. CPU 可卸载计算：从“CPU 当 host”变成“CPU 承接冷/短/稀疏子路径”

### 问题

- **NPU 主路径不能被小粒度低效区拖慢：**Prefill / Decode / Attention / MoE / 多模态生成中存在 gate、router、top-k、outlier、短矩阵、稀疏块、KV 选择、冷专家 fallback 等不适合全部塞进 NPU 主图的子任务。
- **CPU 计算收益必须严格过收益边界：**CPU gate / FFN 冷路径 / expert fallback 只有在 `T_CPU_compute + T_copy + T_sync < T_NPU_stall_saved + T_memory_released` 时才成立；大块 dense FFN 长期放 CPU 通常不应作为默认路线。
- **Prefill 与 Decode 的卸载策略不同：**Prefill 适合批量化、宽窗口预取和较粗粒度 CPU 并行；Decode 对单 token miss、同步和尾延迟敏感，更适合 CPU 做决策、索引、预取、冷路径补算，而不是频繁阻塞式计算。
- **多模态状态辅助计算需要隔离主生成链路：**rolling KV、noise/latent state、分段生成状态筛选可下沉 CPU，但不能破坏 DiT/VAE/NPU 主流水连续性。

###  关键技术点

- **阶段感知 A/K 分工。**按 Prefill、Decode、MoE routing、Attention restore、多模态生成 5 类阶段建立 offload 白名单：NPU 跑密集主算，CPU 跑 gate/router/top-k、KV 命中判断、冷专家 fallback、I/O 聚合、状态打分与回退路径。
- **CPU gate / router / 冷 FFN 加速。**把 MoE gate、expert top-k、shared expert 决策、低频专家小批量 GEMM、异常 outlier / sparse block、短序列补偿计算抽象为 CPU candidate kernels；通过 Kunpeng SIMD/SVE、NUMA 亲和、DDR 预取和异步队列做 microbenchmark 标定。
- **异步流水与可掩盖执行。**CPU 子任务必须被嵌入 NPU iteration 间隙或 KV/专家预取窗口，形成 “NPU compute ↔ CPU decision/compute ↔ DDR/SSD transfer” 的 overlap，而不是把 CPU 做成同步阻塞点。
- **卸载准入模型。**每类子任务必须输出准入条件：shape、batch、token 阶段、数据量、搬运路径、CPU 利用率、NPU stall、DDR 带宽占用、对 TPOT/P99 的影响；不满足收益边界则回到 NPU 或重算。

### 未来趋势

CPU 参与推理会从“粗粒度 offload”演进为**收益受控的选择性混合执行**：CPU 不替代 NPU 主算，而是把 NPU 不擅长或会挤占近端容量的冷、短、稀疏、状态相关子路径变成可批量、可预测、可观测的协同计算。

---

## 2. MoE / KV / Weight 状态对象化：冷热计算、分层驻留、预取与恢复

### 问题

- **KV 与专家权重竞争同一块近端容量：**长上下文 KV、MoE expert、共享权重、activation/workspace、rolling state 会共同挤压 Bailu/HBM；并发提升往往先被 KV/Expert 容量卡住，而不是被峰值算力卡住。
- **专家不再适合按静态权重管理：**MoE 专家是按 token、层、任务和会话阶段动态激活的对象；全常驻浪费容量，简单 LRU 换出会造成冷专家 miss 和 decode 尾延迟。
- **KV offload 不能只看容量收益：**DDR/SSD 中的 KV 如果 layout 碎、tiny I/O 多、CPU 控制路径长，恢复可能比重算更慢；必须显式比较 restore cost、recompute cost 与质量损失。
- **冷热判断不能只靠访问频次：**代码仓、系统提示、文档片段、长期上下文、专家路由都存在阶段性和语义相关性，需结合 gate 概率、prefix reuse、next-use probability、miss penalty 和 load cost。

###  关键技术点

- **统一 state-object runtime。**把 KV block、Prefix span、Expert weight、Shared weight、Activation workspace、Latent/Noise cache 都抽象为状态对象，记录 `size / tier / owner / lifetime / next-use / restore-cost / recompute-cost / quality-risk / pinned`。
- **专家冷热评分与预取。**对每个 expert 计算热度：`HotScore = α·P_next + β·reuse_freq + γ·miss_penalty + δ·prefetch_window - ε·load_cost - ζ·capacity_pressure`；按热/温/冷分为 NPU 常驻、DDR 预取、SSD 可恢复、CPU fallback 四类。
- **KV 容量管理与恢复预期。**对 KV/Prefix 分层执行：热 KV 留近端；温 KV 放 DDR 并异步回温；冷 KV/长尾 prefix 放 SSD 或重算；每个对象必须输出 restore ETA、命中概率、重算替代成本和对 TTFT/TPOT 的影响。
- **对象布局与批量 I/O。**将冷 KV/冷专家从碎片 tensor/page 改造成可合并 object / stripe / block，减少 tiny I/O、CPU bounce buffer 和同步次数；优先验证 NPU↔CPU pinned buffer、CPU 聚合预取，再探索 NPU↔SSD direct path。
- **恢复优先的缓存策略。**缓存替换不以“释放空间最大”为目标，而以 `SLO 风险 × miss penalty × 恢复不确定性` 最小为目标；P99/TPOT 敏感对象优先保留或提前回温。

### 未来趋势

模型状态会从引擎内部缓存演进为 A+K 推理数据面的一等对象：CPU 负责热度计算、对象编排和预取决策，NPU 保持主推理连续执行，Bailu/HBM、DDR、SSD、未来 HMM/PIM 共同形成可度量、可恢复、可调度的状态层级。

---

## 3. 硬件流水线与并发：把“加 batch”改成“容量、带宽、调度三者同时闭环”

### 问题

- **并发不是单纯提高 batch：**并发提升会同时放大 KV footprint、expert working set、DDR traffic、SSD IOPS、CPU 调度开销和 NPU iteration stall；瓶颈会从算力转移到容量、带宽或恢复抖动。
- **组件互联决定协同收益边界：**NPU↔CPU、NPU↔DDR、CPU↔DDR、CPU↔SSD、NPU↔SSD、NPU↔NPU、UB↔Bailu/HBM 的实际带宽、延迟、提交开销和 overlap 能力必须进入设计，而不能只看理论峰值。
- **Prefill / Decode / Restore 资源形态不同：**Prefill 偏算力与长上下文 attention，Decode 偏 KV 命中与单 token 同步，Restore 偏 I/O 与内存层级；混在一个队列里容易造成头阻塞和尾延迟。
- **P/D 拆分并非默认收益：**低并发、短上下文、低 prefix reuse 时拆分可能亏；长上下文、多轮会话、高复用或多实例时，P/D、KV exchange 和 external KV store 才更容易赚钱。

###  关键技术点

- **阶段化流水线建模。**建立 `Prefill → KV materialize → Decode step → Expert route/load → KV/Expert restore → Evict/prefetch` 的事件流水，并显式记录每段的 CPU、NPU、Bailu/HBM、DDR、SSD、互联占用。
- **带宽预算表。**为每类模型/场景建立 token 级资源公式：KV bytes/token、expert bytes/token、restore bytes/request、prefetch bytes/step、CPU cycles/token、DDR GB/s、SSD IOPS、NPU stall us；判断哪个链路先饱和。
- **并发准入控制。**用 `near-memory occupancy + KV hit rate + expert hit rate + transfer overlap ratio + P99 TPOT` 决定最大 in-flight 请求数；超过拐点后降并发、降上下文保留、压缩/重算冷 KV 或改变专家驻留策略。
- **P/D 与多实例策略。**在单机/小集群上按 SLO 选择 aggregated、PD-colocated、PD-disaggregated、external KV store；让 KV 传输与其他请求计算重叠，避免把 transfer 做成全局同步。
- **流水线反压与降级。**当 SSD IOPS、DDR 带宽或 CPU runtime overhead 接近阈值时，触发 prefix 只保热段、冷专家只预取 top-M、KV 低价值对象重算、多模态状态分段落盘等降级策略。

### 未来趋势

A+K 并发优化会从“提高 batch size”转向**状态容量、互联带宽、流水线 overlap 与 SLO 反压**的联合控制；最大并发要由硬件实测和对象热度动态决定，而不是由静态显存公式决定。

---

## 4. 推理算力仿真系统：用实测硬件画像反推规格与收益边界

### 问题

- **没有仿真器就无法判断机制是否值得做：**CPU gate/FFN、专家 offload、KV 分层、NPU-SSD direct path、P/D 拆分都可能被搬运、同步、layout 和 runtime overhead 抵消。
- **只报端到端吞吐无法定位瓶颈：**TTFT、TPOT、throughput 之外，还需要看到每个阶段的 NPU stall、CPU cycles、DDR/SSD traffic、KV restore time、expert miss penalty、pipeline bubble 和能耗。
- **硬件规格必须由场景反推：**CPU 核数、DDR 带宽、SSD IOPS、Bailu/HBM 容量、UB 带宽、NPU↔CPU/NPU↔SSD 通路、功耗上限，应由模型结构、工作负载和状态对象流动共同反推。
- **仿真输入不能只有 FLOPs：**必须包含 shape、phase、KV 命中/恢复、expert 热度、I/O 颗粒度、host overhead、arrival burst、prefix reuse、tool idle、energy telemetry。

###  关键技术点

- **三层输入。**  
  1）模型结构：layers、hidden、heads、GQA/MQA、FFN size、KV bytes/token、MoE experts/top-k、expert size、precision、activation/workspace；  
  2）硬件实测：NPU matmul/attention throughput by shape、CPU gate/FFN/expert throughput、DDR/SSD/互联 bandwidth-latency、I/O submission overhead、power counters；  
  3）工作负载：prompt/output 分布、arrival process、session reuse、prefix hit、KV hit/miss、expert hotness、并发、SLO。
- **离散事件 + 代价模型。**模拟 request 到达、prefill、KV materialize、decode step、expert route/load、KV/Expert restore、evict、prefetch、stall、completion；每个事件绑定资源占用和状态对象迁移。
- **收益判定模型。**对每项 A+K 机制输出收益边界：CPU 子计算是否赚钱、KV restore 是否优于 recompute、expert prefetch 深度多少、P/D 是否拆分、SSD tier 是否引入、并发拐点在哪里。
- **证据包式评估。**每次实验输出 trace、workload card、run card、硬件 microbenchmark、瓶颈归因和 what-if 结果；避免只交付 summary score。
- **扰动验证。**逐项收紧 NPU 算力、近端容量、DDR 带宽、SSD IOPS、CPU 核数、互联延迟、功耗上限，验证瓶颈是否按模型预测迁移，形成硬件规格建议。

### 未来趋势

推理仿真会从“跑分预测”演进为**小算力一体机规格反推器**：给定模型、工作负载与实测硬件参数，提前判断 A+K 协同机制是否收益为正，并输出 CPU/DDR/SSD/互联/NPU 的最小可行规格与扩容优先级。

---

## 5. 底部横条：落地优先级与硬件诉求摘要

### P0：先做可观测 + KV/Prefix 分层

**交付：**trace schema、硬件 microbenchmark、vLLM-Ascend / MindIE 侧事件埋点、KV CPU offload、UCM/Mooncake external KV 原型、KV restore vs recompute 判定模型。  
**目标：**先把 TTFT/TPOT/P99 中到底卡在 NPU、CPU、DDR、SSD、KV restore 还是 runtime overhead 讲清楚。

### P1：再做 MoE 专家对象化 + CPU 冷路径计算

**交付：**expert hotness map、专家常驻/预取/换出策略、CPU gate/router/top-k/fallback expert microkernel、专家 miss penalty 模型、expert prefetch precision/recall 评估。  
**目标：**让 MoE 大模型不是“全专家常驻”，而是“热专家留近端、温专家可预取、冷专家可恢复或 CPU fallback”。

### P2：最后做直通 I/O、HMM/PIM 与更激进分层

**交付：**NPU↔SSD direct path 可行性、对象化 KV/Expert layout、SSD 批量 I/O、HMM/PIM 状态层、跨层 QoS 与硬件计数器接口。  
**目标：**把 DDR/SSD/HMM/PIM 从容量补丁变成可 pipeline、可预测、可规格化的数据回流层。

### 硬件诉求摘要

**Mini / DV100 Lite：**验证 CPU gate/短矩阵/冷专家/KV restore 的 A+K 分工，沉淀 trace 与收益边界。  
**塔式 / n+1 分级内存系统：**验证 Bailu/HBM、DDR5、SSD、UB、NPU↔CPU、NPU↔SSD 的流水线互联带宽与并发拐点。  
**n+2 HMM/PIM 异构 SoC：**用 HMM 承载大容量 KV/Weight/Expert/Latent 状态，用 PIM/近存高带宽承接 KV/激活访问，并暴露性能计数器、QoS、DMA/直通与仿真器接口。

---

## 6. 讲稿/备份页：本版技术映射

- **CPU 可卸载计算：**对应 NEO / FlexInfer / llm.npu / HeteroInfer / APEX；吸收其阶段感知、异步 CPU-NPU/GPU 协同、outlier/短矩阵拆分、CPU 参与 attention/KV 或冷路径计算的思路。
- **MoE 专家管理：**对应 KTransformers / FineMoE / HybriMoE / DALI / FluxMoE / MoE-APEX；吸收 expert hotness、CPU fallback expert、expert paging、prefetch、cache replacement、adaptive precision offload。
- **KV / Prefix 分层：**对应 Mooncake / LMCache / HiCache / Tutti / ECHO / Bidaw / CacheSlide / SolidAttention；吸收 KV 对象化、prefix reuse、external KV store、多级内存、SSD object I/O、restore/recompute 判定。
- **流水线与并发：**对应 Mooncake、vLLM connector、TensorRT-LLM DS、NIXL/Dynamo、TaiChi；吸收 P/D 拆分、KV exchange、transfer-compute overlap、按 SLO 选择 aggregation / disaggregation 的收益边界。
- **仿真与规格反推：**对应 ServeGen / BurstGPT / ProfInfer / CCL-Bench / Chakra / Energy-Tradeoffs；吸收 workload trace、eBPF timeline、execution trace schema、microbenchmark、what-if、能耗与尾延迟联合建模。
- **A+K 迁移支点：**vLLM-Ascend KV Cache CPU Offload、UCM、PD-colocated with Mooncake、distributed expert parallelism、weight prefetch、MindIE-LLM serving 基础能力；短板是 NPU↔SSD direct object I/O、统一 state-object runtime 和公开可复验的规格反推模型。
