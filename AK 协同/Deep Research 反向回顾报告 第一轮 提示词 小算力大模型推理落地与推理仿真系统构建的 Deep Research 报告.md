请你执行一次严格、可核验、尽量穷尽的 Deep Research。研究主题是：

**2025–2026 年小算力条件下大模型推理系统优化，以及模型推理算力仿真系统构建。**

我的目标不是做 PPT，而是系统收集业内和学术界在以下方向的最新论文、预印本、系统工作、工业技术报告和高质量技术博客，并提炼它们对“小算力部署”和“推理仿真系统”的具体启发。

## 1. 研究背景与核心问题

我关注的首要矛盾是：

**如何在显存/算力受限的小型服务器、单机多卡、边缘设备、CPU+GPU/NPU 异构平台上，实现大模型，尤其是长上下文模型和 MoE 模型的高效推理。**

请重点围绕以下技术点检索和分析：

1. **CPU 参与推理计算**
   - CPU gating / CPU-side gating
   - CPU 执行 FFN、MoE expert、attention 子路径、outlier block、小矩阵或稀疏路径
   - CPU/GPU、CPU/NPU、CPU/GPU/NPU hybrid inference
   - 哪些子图适合卸载到 CPU，哪些不适合
   - CPU 计算收益与 PCIe/DDR/同步开销之间的边界
2. **MoE 专家权重卸载、缓存、预取与冷热判断**
   - MoE expert offloading
   - expert paging
   - expert prefetching
   - expert cache replacement
   - expert hotness prediction
   - router/gate 结果预测
   - adaptive precision expert offloading
   - CPU fallback expert execution
   - 热专家常驻、冷专家卸载到 CPU DRAM / SSD / CXL / remote memory 的策略
3. **KV cache 容量管理、卸载、恢复与预取**
   - KV cache offloading
   - prefix caching
   - automatic prefix caching
   - KV cache tiering
   - KV cache external store
   - KV cache compression / eviction / reuse
   - KV restore vs recompute tradeoff
   - HBM / GPU memory / CPU DRAM / SSD / CXL / remote KV pool
   - 长上下文、多轮对话、agent workflow、prefix shift、cache hit/miss 规律
4. **模型权重、状态对象和其他可分层管理对象**
   - model weight offloading
   - activation / latent / embedding / intermediate state offload
   - KV、Expert、Weight、Latent、Prefix 是否可以统一为 runtime state object
   - 多级内存里的对象生命周期、热度、迁移、预取和驱逐
5. **硬件流水线、互联带宽与并发提升**
   - HBM / GDDR、CPU DDR、SSD/NVMe、CXL、PCIe、NVLink、RDMA、NPU interconnect
   - GPU/NPU ↔ CPU、GPU/NPU ↔ SSD、CPU ↔ SSD、GPU/NPU ↔ remote memory 的数据路径
   - direct storage、GPU Direct Storage、NPU direct path、CPU bounce buffer
   - prefill/decode disaggregation
   - KV transfer / KV exchange
   - continuous batching
   - phase-aware scheduling
   - concurrency / batch size / TTFT / TPOT / P95 / P99 之间的收益边界
   - 什么时候提升并发会从算力瓶颈转为 HBM、DDR、SSD IOPS、PCIe 或调度瓶颈
6. **模型推理算力仿真系统**
   - LLM serving simulator
   - inference performance model
   - trace-based simulator
   - workload characterization
   - benchmark generation
   - profiler / eBPF / execution trace / hardware counter
   - hardware microbenchmark calibrated model
   - 能否根据实测硬件条件预测不同推理场景下的吞吐、延迟、KV 占用、expert miss、I/O stall、能耗
   - 如何从仿真结果反推 CPU 核数、DDR 带宽、SSD IOPS、HBM 容量、互联带宽、NPU/GPU 数量需求

## 2. 时间范围

重点搜索 **2025 年和 2026 年** 发表、录用或公开的工作。

包括：

- 正式会议论文
- journal extension
- arXiv 预印本
- OpenReview submission / accepted paper
- artifact / technical report
- 工业技术博客、官方文档、开源系统文档

如果某个关键系统发表于 2024 或更早，但在 2025–2026 年正式发表、被大量后续工作引用、或成为当前系统基础，可以放入“背景基石”小节，不要混入 2025–2026 主表。

## 3. 必查会议与来源

请按“会议优先 + 关键词搜索 + 引文扩展”的方式检索，不要只做关键词搜索。

### 必查学术会议

逐一检查这些会议 2025 和 2026 年的 accepted papers / proceedings / program / OpenReview venue 页面：

- ICLR
- AAAI
- ICML
- NeurIPS / NIPS
- MLSys
- ASPLOS
- OSDI
- SOSP
- NSDI
- USENIX ATC
- FAST
- EuroSys
- SoCC
- Middleware
- SC
- ISCA
- MICRO
- HPCA

如有相关内容，也扩展检查：

- MobiSys
- SenSys
- SEC
- IoTDI
- SIGMOD
- VLDB
- CIDR

对于尚未完整公开 proceedings 的会议，请明确标注“截至搜索日期未完整公开”或“仅检索到 program/accepted list/预印本”，不要把未核验论文误标为正式录用。

### 必查论文库与平台

- arXiv
- OpenReview
- ACM Digital Library
- USENIX proceedings
- IEEE / IEEE Xplore
- Semantic Scholar
- Google Scholar
- Papers with Code
- GitHub artifact / official project page

### 必查工业与开源系统来源

优先检查官方文档、技术博客、repo，而不是媒体转述：

- vLLM
- vLLM-Ascend
- SGLang
- LMCache
- Mooncake
- KTransformers
- TensorRT-LLM
- NVIDIA Dynamo / NIXL
- NVIDIA Triton / TensorRT ecosystem
- llama.cpp
- Hugging Face TGI
- DeepSpeed / DeepSpeed-FastGen
- Huawei Ascend / MindIE / MindIE-LLM
- AMD ROCm / AMD inference stack
- Intel AMX / oneAPI / CPU inference stack

## 4. 种子论文与系统

请把以下名称作为 seed set，但不要局限于它们。需要做 forward citation、backward citation 和 related work 扩展，寻找遗漏论文。

CPU / heterogeneous inference：

- NEO
- FlexInfer
- llm.npu / Fast On-device LLM Inference with NPUs
- HeteroInfer
- APEX
- Heterogeneous LLM inference
- CPU-GPU collaborative LLM inference

MoE expert management：

- KTransformers
- FineMoE
- HybriMoE
- DAOP
- DALI
- FluxMoE
- MoE-APEX
- expert offloading / expert paging / expert prefetching

KV cache / memory tiering：

- Mooncake
- LMCache
- SGLang HiCache
- KVCache Cache in the Wild
- Bidaw
- CacheSlide
- SolidAttention
- ECHO
- Tutti
- ITME
- KV cache offloading
- SSD-backed KV cache
- CXL memory for LLM inference

Prefill/decode disaggregation and scheduling：

- Context Parallelism
- TaiChi
- TensorRT-LLM Disaggregated Serving
- vLLM KV connector / NixlConnector
- NVIDIA Dynamo / NIXL
- KV transfer / KV exchange

Simulation / trace / profiling：

- ServeGen
- BurstGPT
- ProfInfer
- CCL-Bench
- MLCommons Chakra
- Characterizing LLM Inference Energy-Performance Tradeoffs
- LLM serving simulator
- inference trace replay
- hardware-calibrated inference performance model

## 5. 关键词组合

请至少使用以下关键词组合，并根据结果继续扩展同义词和相关术语。

### CPU / heterogeneous compute

- CPU GPU collaborative LLM inference
- CPU NPU collaborative LLM inference
- CPU offloading LLM inference
- CPU-assisted LLM inference
- CPU FFN LLM inference
- CPU gating LLM inference
- CPU expert execution MoE
- CPU fallback expert MoE
- hybrid CPU GPU inference MoE
- heterogeneous LLM inference CPU GPU NPU
- on-device LLM inference NPU CPU GPU
- outlier-aware LLM inference CPU GPU
- edge LLM inference NPU
- small GPU LLM inference offloading

### MoE

- MoE expert offloading
- MoE expert paging
- MoE expert prefetching
- MoE expert cache
- MoE expert hotness
- MoE inference memory management
- MoE inference CPU GPU hybrid
- adaptive precision expert offloading
- sparse expert inference system
- router prediction expert prefetch
- expert cache replacement LLM

### KV cache / state / memory

- KV cache offloading
- KV cache tiering
- KV cache CPU offload
- KV cache SSD offload
- SSD-backed KV cache
- CXL KV cache LLM
- external KV cache LLM serving
- prefix caching LLM serving
- automatic prefix caching
- KV cache reuse multi-turn agent
- KV cache compression
- KV cache eviction
- KV cache restore recompute tradeoff
- hierarchical KV cache
- long context LLM inference memory
- GPU Direct Storage KV cache
- NPU SSD direct storage KV cache

### Disaggregated serving / scheduling

- prefill decode disaggregation
- disaggregated LLM serving
- KV transfer LLM serving
- KV exchange LLM inference
- phase-aware LLM inference scheduling
- continuous batching LLM serving
- LLM serving concurrency memory bottleneck
- TTFT TPOT optimization LLM serving
- LLM serving interconnect bandwidth

### Simulation / profiling / benchmarking

- LLM serving simulator
- LLM inference simulator
- LLM inference performance model
- trace-based LLM serving simulation
- LLM serving workload characterization
- LLM inference profiler
- eBPF LLM inference profiler
- execution trace LLM inference
- hardware calibrated LLM inference model
- LLM inference energy performance model
- LLM serving benchmark generation
- LLM inference what-if simulator

### Ascend / Kunpeng / NPU-specific

- Ascend LLM inference KV cache offload
- vLLM-Ascend KV cache CPU offload
- vLLM-Ascend Mooncake
- vLLM-Ascend UCM
- MindIE LLM inference
- Kunpeng CPU LLM inference
- Ascend NPU CPU offload
- Ascend NPU KV cache
- Ascend MoE expert prefetch
- NPU SSD direct storage inference

## 6. 检索和核验要求

请严格执行以下要求：

1. 每篇论文必须尽量核验：
   - 论文标题
   - 作者和机构
   - 会议/期刊/平台
   - 发表或公开时间
   - 状态：正式发表、正式录用、预印本、技术报告、官方文档、工业博客
   - primary source 链接
   - PDF / OpenReview / proceedings / arXiv / official docs 链接
2. 不要把 arXiv 预印本写成会议论文，除非有官方 accepted/proceedings 证据。
3. 不要把二手博客、新闻稿或 GitHub README 当作论文证据；它们可以作为工程补充，但必须单独标注。
4. 对于每个目标会议，请给出“查到强相关 / 查到中相关 / 未发现直接相关 / 尚未完整公开”的结论。
5. 不要遗漏负结果。需要有一个“会议查缺补漏表”，说明每个会议是否已经检查，以及是否找到相关论文。
6. 对同一论文的 arXiv、OpenReview、conference、project page 做去重。主表只保留一行，其它链接放到“来源链接”字段。
7. 对相关性分级：
   - S：直接命中小算力大模型推理或推理仿真核心问题
   - A：强相关，可直接借鉴机制或建模方法
   - B：中相关，涉及相邻系统问题
   - C：弱相关，只作为背景，不放入主表
8. 主表只放 S 和 A。B 级放附录。C 级只在必要时一句话提及。

## 7. 每篇论文需要抽取的字段

请为每篇 S/A 级论文或系统整理以下信息：

- 方向分类
- 相关性等级
- 论文名称
- 作者机构
- 会议/来源
- 发表时间
- 状态
- primary source 链接
- 研究背景和需求
- 要解决的核心问题
- 面向的硬件或部署场景
- 涉及的模型类型：dense LLM、MoE、long-context、multimodal、agent workload 等
- 核心贡献
- 核心策略 / 系统机制
- 是否涉及 CPU 计算
- 是否涉及 MoE expert offload / cache / prefetch
- 是否涉及 KV cache offload / reuse / compression / eviction
- 是否涉及多级内存：HBM、DDR、SSD、CXL、remote memory
- 是否涉及 prefill/decode 拆分
- 是否涉及并发、batching、scheduling
- 是否涉及 profiler、trace、simulator、performance model
- 结果收益：吞吐、延迟、TTFT、TPOT、P95/P99、显存占用、并发、成本、能耗
- 评估方式：硬件平台、模型、数据集、workload、baseline、指标
- 关键限制和适用边界
- 对“小算力推理落地”的启发
- 对“推理仿真系统”的可用变量或建模启发

## 8. 输出结构

请按以下结构输出最终报告。

### A. 执行摘要

用 8–12 条 bullet 总结 2025–2026 年该领域的关键趋势。

必须回答：

- 业内最关注的问题是什么？
- 哪些方向论文最密集？
- 哪些方向还很空白？
- CPU 参与推理到底主要在哪里有收益？
- MoE expert 与 KV cache 是否正在变成同一类“状态对象管理”问题？
- 小算力场景下最值得优先做什么？
- 构建推理仿真系统最缺哪些输入和校验数据？

### B. 研究问题地图

给出一张表：

列包括：

- 方向
- 核心瓶颈
- 代表论文/系统
- 主要技术路线
- 依赖的硬件能力
- 对小算力部署的意义
- 对仿真系统的建模要求

方向至少包括：

- CPU 可卸载计算
- MoE 专家管理
- KV / Prefix / State 分层内存
- 权重 / Latent / 其他状态对象管理
- Prefill/Decode 拆分与调度
- 硬件互联与流水线
- 推理仿真、trace、profiling、benchmark
- Ascend/Kunpeng/NPU 生态迁移

### C. 会议查缺补漏表

按会议和年份列出：

- 会议
- 年份
- 是否检查官方来源
- 是否找到强相关论文
- 强相关论文
- 中相关论文
- 未发现的说明
- 仍需人工复核的地方
- 来源链接

请不要只列找到的会议，也要列未找到的会议。

### D. 强相关论文总表

按方向分组，每篇论文一行。

字段包括：

- 方向
- 相关性等级
- 论文名称
- 机构
- 来源/会议
- 时间
- 状态
- 硬件平台
- 模型/工作负载
- 核心问题
- 核心策略
- 主要收益
- 对小算力推理的价值
- 对仿真系统的价值
- 链接

### E. 分方向详细分析

每个方向写成独立小节：

1. CPU 可卸载计算与异构协同
2. MoE 专家权重卸载、预取、缓存与冷热判断
3. KV cache 容量管理、卸载、恢复与预取
4. 权重、latent、activation 与统一 state object runtime
5. 硬件流水线、互联带宽、并发与 P/D 拆分
6. 推理仿真、trace、profiling 与性能建模
7. Ascend NPU + Kunpeng CPU 的可迁移路线

每个小节都需要总结：

- 该方向为什么在 2025–2026 变重要
- 主要论文各自解决什么问题
- 技术路线之间的差异
- 适用边界和反例
- 对小算力部署的直接建议
- 对仿真器应建模哪些变量

### F. 推理仿真系统设计启发

请专门输出一个“推理仿真系统蓝图”。

至少包括：

1. 输入层
   - 模型结构参数
   - MoE 参数
   - KV cache size/token
   - precision
   - hardware microbenchmark
   - workload trace
   - arrival process
   - prefix reuse
   - expert hotness
   - energy telemetry
2. 代价模型
   - prefill cost model
   - decode cost model
   - CPU offload cost model
   - expert placement model
   - KV cache object model
   - memory tier model
   - interconnect transfer model
   - SSD I/O model
   - scheduler / queueing model
   - energy model
3. 离散事件仿真核心
   - request arrival
   - prefill start/end
   - KV hit/miss
   - KV restore/recompute
   - expert hit/miss
   - expert prefetch
   - HBM eviction
   - decode step
   - batching
   - transfer overlap
   - stall attribution
   - completion
4. 输出指标
   - throughput
   - TTFT
   - TPOT
   - P50/P95/P99 latency
   - HBM occupancy
   - DDR bandwidth
   - SSD throughput / IOPS
   - PCIe / NVLink / CXL utilization
   - KV restore stall
   - expert miss penalty
   - CPU utilization
   - GPU/NPU utilization
   - energy per token
   - bottleneck attribution
5. 校验方法
   - microbenchmark calibration
   - profiler timeline validation
   - trace replay validation
   - sensitivity analysis
   - what-if hardware sizing

### G. 收益边界与反例

请明确分析这些问题：

- CPU 执行 FFN / expert / attention 子路径什么时候赚钱？
- 什么时候 CPU 参与会被 PCIe、DDR、同步开销反噬？
- MoE expert offload 什么时候赚钱？
- expert prefetch 什么时候会失败？
- KV cache offload 什么时候比 recompute 更差？
- SSD-backed KV 什么时候被 tiny I/O 和 CPU control path 反噬？
- CXL / remote memory 适合热层、温层还是冷层？
- P/D 拆分什么时候不赚钱？
- 提升并发什么时候会转化为 HBM、DDR、SSD、互联或调度瓶颈？
- 哪些论文给出了这些边界的实验证据？

### H. Ascend + Kunpeng 迁移路线

请单独分析：

- vLLM-Ascend 是否已有 KV cache CPU offload、UCM、Mooncake、PD 相关能力
- MindIE / MindIE-LLM 是否已有 continuous batching、paged attention、flash decoding 或类似能力
- Kunpeng CPU 可能承担哪些角色：
  - metadata manager
  - prefetch planner
  - KV warm tier
  - expert warm tier
  - CPU fallback expert
  - I/O aggregation
  - profiler / simulator host
- 哪些机制纯软件可做
- 哪些需要 runtime hook
- 哪些需要 NPU DMA / memory API
- 哪些需要下一代硬件接口
- 优先级排序：P0、P1、P2
- 最大技术风险

### I. 研究空白与创新机会

请输出 8–12 个值得进一步研究或落地的创新机会。

每个机会包括：

- 问题定义
- 为什么已有论文还没解决
- 可能的技术路线
- 需要的系统接口
- 可能的评估指标
- 适合投稿的会议方向

请特别关注：

- 统一 state-object runtime
- NPU-SSD direct path for KV/state
- 小算力单机/小集群 serving simulator
- CPU expert execution on non-x86 CPU
- expert hotness + KV hotness 联合建模
- KV restore vs recompute 自动决策
- 面向 Ascend/Kunpeng 的公开系统论文机会

### J. 精读清单

请给出三档精读清单：

- P0 必读：直接决定技术路线
- P1 应读：补齐机制理解
- P2 背景：了解相邻方向

每篇说明为什么值得读，以及读的时候重点看什么。

### K. 参考文献与搜索日志

最后输出：

1. 参考文献列表
   - 只列 primary source 或官方 source
   - 每条包含标题、作者/机构、来源、年份、链接
2. 搜索日志
   - 使用过的关键词
   - 检查过的会议
   - 未发现结果的查询
   - 仍需人工复核的来源

## 9. 输出风格要求

- 用中文写报告，论文标题保留英文原名。
- 不要写成泛泛综述，要写成技术路线调研。
- 不要只总结论文摘要，要提炼系统机制、硬件假设、收益来源和失败边界。
- 对不确定信息要明确标注“未核验”“仅预印本”“官方 proceedings 未确认”。
- 避免夸大“所有论文都找到了”。请使用“尽量穷尽”“在已检查来源中”这类严格表述。
- 每个关键结论都要有来源支撑。
- 优先引用论文、官方 proceedings、OpenReview、arXiv、官方项目文档，不优先引用二手媒体。
- 最终结果应能直接支持后续技术立项、论文精读、原型系统设计和推理仿真器建模。