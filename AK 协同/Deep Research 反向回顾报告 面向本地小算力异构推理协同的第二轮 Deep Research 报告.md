# 面向本地小算力异构推理协同的第二轮 Deep Research 报告

## 执行摘要

这一轮补证后，第一轮里最需要纠正的一点是：**“HeteroLLM”与“HeteroInfer”本质上是同一条工作线的预印本/正式发表名称差异**。预印本题名为 *HeteroLLM: Accelerating Large Language Model Inference on Mobile SoCs with Heterogeneous AI Accelerators*，正式发表版本为 *Characterizing Mobile SoC for Accelerating Heterogeneous LLM Inference*，并发表于 SOSP 2025；如果 PPT 里仍把它当成两个独立系统，会重复计数证据。citeturn20view1turn21search2turn21search7

这一轮新增并显著增强了三类关键证据。第一类是 **CPU 不是只做 offload“搬运工”**，而是在特定子路径上直接参与计算：NEO、FlexInfer、LIA、APEX、HybridGen、Fiddler、HybriMoE、KTransformers 等都在不同语境下证明，**只要 CPU 计算能同时降低 HBM 占用、提高有效 batch、并与 GPU/NPU 主路径重叠，它就可能是正收益**；反过来，如果它只引入 PCIe/CXL/同步和格式转换开销，就会反噬。citeturn38search2turn22search0turn23search2turn19search6turn23search11turn10search1turn35search7turn31search2

第二类新增证据是：**KV / Prefix / Context 已经从“引擎内部临时 tensor”演化成外部化、可路由、可迁移、可分层的系统状态对象**。Mooncake、LMCache、vLLM KV Connector / NIXL、SGLang HiCache、UCM for vLLM-Ascend、SYMPHONY、Tutti、Beluga、ITME、SolidAttention、ECHO 等工作共同表明，2025–2026 的主线不是“单点 cache 优化”，而是**状态对象化 + 分层回流 + 直通数据面**。citeturn11search15turn24search18turn27search0turn27search3turn24search0turn26search3turn7search1turn29search14turn29search6turn26search1turn30search0

第三类新增证据是：**阶段拆分已经从论文想法进入工程产品化**。vLLM 的 disaggregated prefilling 与 NixlConnector / MoRI-IO，SGLang 的 EPD，TensorRT-LLM 的 disaggregated serving，Mooncake 的 PD/EPD 集成，以及多模态的 HydraInfer / TriInfer，都说明 Prefill/Decode，甚至 Encode/Prefill/Decode，已经不再只是云端大集群方案，而是在单机、多卡、异构节点里开始变成可部署的工程能力。citeturn27search3turn27search0turn11search10turn11search7turn11search1turn11search17turn24search13turn15search1turn14search5

这一轮还确认：**MoE 专家对象化正在快速收敛**。KTransformers、HybriMoE、Fiddler、DAOP、FineMoE、FluxMoE、DALI、DuoServe-MoE、FloE 证明，专家已从“固定驻留权重”变成“可预测、可分页、可预取、可缓存、可 CPU fallback 的权重对象”。其中 KTransformers、FineMoE、FluxMoE 最适合支撑 PPT 里“expert-object management”这一表述。citeturn31search2turn35search7turn10search13turn35search6turn10search0turn9search0turn8search3turn9search2turn9search9

在 Agent / workflow 方向，新增证据非常关键：KVFlow、Tokencake、PBKV、Continuum、ThunderAgent、以及 “Exploiting Tool-Call Idle Windows for Offloading in Agentic Workloads” 说明，**工具调用带来的 idle window 已经让 KV 生命周期管理从 LRU 问题，变成 program-aware / workflow-aware 状态保活与回收问题**。这直接支持你 PPT 中“状态对象化与分层回流”不是只为长上下文，而是 also 为 agentic workload。citeturn13search17turn13search14turn13search0turn25search5turn13search15turn13search6

在多模态与视频生成方向，本轮找到的是**“分布式 serving / pipeline / feature cache / rolling KV”分散证据链**，但**尚未找到一篇同时满足“视频生成 serving + Noise Cache/rolling KV/latent state 对象化 + DRAM/SSD/CXL 分层回流”四个条件的完整系统论文**。StreamDiffusionV2 提供 rolling KV 与实时系统调度，TeaCache / FasterCache 提供跨 timestep 特征缓存，DisagFusion / GenServe 提供 serving 侧异构调度，但这几条线还没有在同一篇系统论文里收敛。citeturn16search3turn14search18turn14search14turn16search0turn15search3

在“规格反推 / 收益边界”上，本轮强化了两条判断式。第一，**CPU 参与要赚钱，必须把计算重叠与内存扩容收益同时变现**，代表工作是 NEO、LIA、APEX、HybridGen。第二，**SSD/CXL 作为温层/冷层要赚钱，必须把 I/O 做成对象化批量路径，并尽量消除 CPU 作为每次 I/O 控制平面的 bottleneck**，代表工作是 Tutti、Beluga、ITME、SolidAttention。citeturn38search2turn23search2turn19search6turn23search11turn7search1turn29search14turn29search6turn26search1

对 Ascend NPU + Kunpeng CPU 而言，最现实的近端机会不是一上来追求“所有机制全做”，而是优先做三类原型：**NPU↔CPU KV offload / restore 的对象化接口、Mooncake/UCM 式外部 KV 层、以及 PD/EPD 的小集群拆分**。这些方向已经在 vLLM-Ascend、UCM、Mooncake-Ascend 的官方文档里具备工程支点。citeturn24search8turn24search0turn24search4turn24search13turn24search10

## 与第一轮相比新增、修正与删除的条目

### 关键修正

| 条目 | 第一轮常见表述 | 本轮核验后的结论 | 处理 |
|---|---|---|---|
| HeteroLLM / HeteroInfer | 常被当成两篇 | 预印本题名为 **HeteroLLM**，正式发表题名为 **Characterizing Mobile SoC for Accelerating Heterogeneous LLM Inference**，SOSP 2025；应合并为同一工作线 | **修正** citeturn20view1turn21search2turn21search7 |
| Beluga | 常被写成“arXiv/CXL 概念文” | 已检到正式发表信息：**SIGMOD 2026 / Proceedings of the ACM on Management of Data**；不是仅 arXiv | **修正** citeturn28search24turn28search16turn29search14 |
| KTransformers | 常被写成“开源项目” | 已有 **SOSP 2025** 论文与 DOI；开源项目只是实现载体 | **修正** citeturn31search0turn31search2turn31search11 |
| KVCache Cache in the Wild | 常被写成 arXiv only | 预印本为 2025-06，但已明确标注 **USENIX ATC 2025** 录用/发表 | **修正** citeturn7search3turn7search7 |
| SuperInfer | 常被直接写成“MLSys 2026 论文” | 目前我能核到的是 arXiv 预印本；“MLSys 2026 accepted”主要来自作者社交媒体，需保守标为 **C/D 级证据** | **修正** citeturn12search6turn12search2 |
| TriInfer | 常被直接写成“MLSys 2026 正式论文” | 当前公开可核主证据是 **MLSys 2026 slides** 与次级讨论，公开正式论文页/DOI 本轮未检到 | **修正** citeturn14search5turn16search1 |
| Splitwise | 第一轮常作为 PD 相关条目 | 本轮按标题检索未找到与本主题对应的系统论文，反而大量命中同名记账 App；说明**条目名高度可疑或混淆** | **删除或待人工复核** citeturn12search1turn12search5turn12search9 |

### 关键新增

| 新增条目 | 重要性 | 为什么第一轮容易漏掉 |
|---|---|---|
| LIA: *A Single-GPU LLM Inference Acceleration with Cooperative AMX-Enabled CPU-GPU Computation and CXL Offloading* | 非常高 | 它不是传统“offload-only”工作，而是把 **AMX CPU 计算 + CXL 内存**放到同一收益模型里，直接对你的“CPU 参与何时赚钱”有证据价值。citeturn23search2turn23search6 |
| APEX: *Parallel CPU-GPU Execution for LLM Inference on Constrained GPUs* | 很高 | 它给了一个更“工程调度”视角的答案：**CPU/GPU 重叠不是静态切分，而是预测驱动调度**。citeturn19search6turn38search12 |
| HybridGen | 很高 | 它不是简单 KV offload，而是 **CPU–GPU 协同 attention**，本质上更接近你 PPT 里的 A+K 协同。citeturn23search11turn19search3 |
| SYMPHONY | 很高 | 它把 KV 管理和 cluster 级调度耦合起来，证明了“状态对象化”不仅是存储问题，还是**调度与负载均衡问题**。citeturn26search3turn26search7 |
| Tutti | 很高 | 它第一次把 **SSD-backed KV cache** 做成更彻底的 **GPU-centric object store + GPU io_uring** 路线，正面回应“direct storage 不该经 CPU bounce buffer”。citeturn7search1 |
| ECHO | 高 | OSDI 2026 对 **native sparse attention + lossless prefetching + KV offloading** 的结合，是 2026 年直接补强的一条线。citeturn30search0turn30search1 |
| SolidAttention | 高 | 它不是 SSD tiering 泛论，而是面向**memory-constrained PCs**的低延迟 SSD 路线，和“小算力工作站”很贴合。citeturn26search1turn26search17 |
| PBKV / Continuum / ThunderAgent | 高 | 这几篇使“KV 生命周期管理”从多轮对话扩展到 **agent workflow / tool wait**，是第一轮最容易漏但对 PPT 很重要的一块。citeturn13search0turn25search5turn13search15 |
| KernelSight-LM / Kareto / ProfInfer / TokenPowerBench / CCL-Bench | 很高 | 它们把“收益边界”和“规格反推”从经验判断推进到 **simulator / profiler / energy benchmark**。citeturn18search0turn18search1turn32search2turn34search2turn33search0 |

### 本轮删除或降级的条目

本轮对一些名称进行了降级处理。典型例子包括 **MoE-Lightning、Agentix / Autellix、CacheWise、Parrot** —— 它们在二手列表或引用链中频繁出现，但截至 2026-06-30，我没有稳定检到与你这次主题直接匹配的 primary source（正式论文页、arXiv 原文、OpenReview 条目或官方系统文档）。因此本轮不把它们列为“强相关主证据”，而是标成“需进一步人工复核/弱相关”。citeturn9search3turn13search18

## 逐会议查缺补漏表

下表的口径是：**以官方 proceedings / 会议页面 / 论文页为主，辅以 arXiv / OpenReview / 官方项目页交叉核验**。对 2026 年尚未完全公开最终 proceedings 的会议，我保守写作“截至 2026-06-30 未完成最终官方逐篇核对，现有结果以公开页面为准”。

| 会议 / 来源 | 是否找到强相关论文 | 强相关论文列表 | 中相关论文列表 | 弱相关 / 排除 / 说明 | 是否需人工复核 | 官方或主来源 |
|---|---|---|---|---|---|---|
| ICLR 2025 | 是 | **Fiddler** | FasterCache 属于视频缓存加速，但不直接涉及分层回流 | 纯算法/压缩类不纳入主表 | 否 | citeturn10search13turn31search23 |
| ICLR 2026 | 有，但多为边界项 | KV Cache Transform Coding、IceCache、PRKV、SpecOffload 等多与 KV 压缩/稀疏有关 | 多数更偏算法或 memory-efficiency，而非完整异构协同系统 | 许多条目仍以 OpenReview 页面为主，需谨慎使用 | 是 | citeturn25search11turn25search20turn25search25turn25search26 |
| AAAI 2025 | 未检到强相关主论文 | 未发现与 GPU/NPU+CPU+HBM/DRAM/SSD 协同直接相关论文 | — | 本轮未完成 AAAI 2025 全量 TOC 逐篇复核 | 是 |  |
| AAAI 2026 | 有 | **TokenPowerBench** | 能源与基准工作相关，但不直接给出异构机制设计 | 更偏 benchmark，不是执行路径论文 | 否 | citeturn34search11turn34search2 |
| ICML 2025 | 是 | **FloE** | — | 无直接 KV 分层类强相关 | 否 | citeturn9search9turn35search1 |
| ICML 2026 | 截至 2026-06-30 未完成最终官方逐篇核对 | 目前未发现比 MLSys / systems venues 更强的直接证据 | — | 会议仍处当年时间窗内，宜二次人工确认 | 是 | citeturn34search7turn34search1 |
| NeurIPS 2025 | 本轮未检到强相关主论文 | 未发现与本主题直接相关论文 | — | 更常见的是 kernel/quant/speculative 方向 | 是 |  |
| NeurIPS 2026 | 截至 2026-06-30 不适合下结论 | 未完成最终官方核验 | — | 时间尚早 | 是 |  |
| MLSys 2025 | 是 | **NEO、FlexInfer** | 其它 serving/SLO 论文可作背景 | 是这一轮最关键的 CPU 协同证据源之一 | 否 | citeturn38search0turn22search0turn38search1 |
| MLSys 2026 | 是 | **TriInfer**（低置信）、**ProfInfer**（Industry）、可能还有 SuperInfer 的次级录用线索 | 其它 trend/blog 可作旁证 | 需注意 TriInfer / SuperInfer 的公开状态不完全一致 | 是 | citeturn14search5turn32search10turn12search2 |
| OSDI 2025 | 本轮未检到同等级最强条目 | — | — | 没有比 MLSys/FAST/ATC 更核心的直接命中 | 是 |  |
| OSDI 2026 | 是 | **ECHO** | — | 针对 sparse attention + KV offload，很值得补入 | 否 | citeturn30search0turn30search1 |
| SOSP 2025 | 是 | **HeteroInfer、KTransformers** | — | 一个是 mobile SoC heterogeneous，一个是 MoE CPU/GPU hybrid | 否 | citeturn21search2turn21search7turn31search11turn31search2 |
| NSDI 2025 | 本轮未检到最强直系条目 | — | — | 没有超过 2026 NSDI 的直系证据 | 是 |  |
| NSDI 2026 | 是 | **SYMPHONY、ServeGen** | — | 一个偏状态迁移，一个偏 workload characterization | 否 | citeturn26search3turn32search9 |
| USENIX ATC 2025 | 是 | **KVCache Cache in the Wild** | Toppings、Weaver 为中相关 | Toppings 更偏 LoRA adapter；Weaver 更偏多模型 attention offload | 否 | citeturn7search7turn25search0turn25search21turn25search9 |
| USENIX ATC 2026 | 截至 2026-06-30 未完成最终官方逐篇核对 | 未发现比 2025 ATC / 2026 NSDI 更强的直接条目 | — | 需后续再查 | 是 |  |
| FAST 2025 | 是 | **Mooncake、IMPRESS** | — | 该 venue 在 KV / storage tiering 上极强 | 否 | citeturn11search11turn26search2turn26search6 |
| FAST 2026 | 是 | **SolidAttention** | — | 贴近 memory-constrained PCs / 小算力工作站 | 否 | citeturn26search1turn25search3 |
| EuroSys 2025 | 本轮未检到强相关主论文 | — | — | 未发现与主题直接强耦合论文 | 是 | citeturn25search7 |
| EuroSys 2026 | 是 | **FineMoE** | — | 属于 MoE expert-object 关键证据 | 否 | citeturn10search0turn10search12turn25search10 |
| SoCC 2025 | 是 | **Understanding Diffusion Model Serving in Production** | — | 是多模态/扩散生产工作负载最强证据之一 | 否 | citeturn14search0turn16search17turn16search11 |
| SoCC 2026 | 截至 2026-06-30 未完成最终官方逐篇核对 | — | — | 待后续跟进 | 是 |  |
| Middleware 2025 / 2026 | 本轮未检到强相关主论文 | 未发现与 GPU/NPU+CPU+HBM/DRAM/SSD 协同直接相关论文 | — | 需人工复核 | 是 |  |
| ASPLOS 2025 | 是 | **llm.npu** | — | 端侧 NPU/CPU/GPU 协同最强证据之一 | 否 | citeturn37search0turn37search4 |
| ASPLOS 2026 | 本轮未检到比 SIGMOD/FAST/OSDI 更强的直系条目 | — | — | 需人工复核 | 是 |  |
| ISCA 2025 | 是 | **LIA** | — | CPU AMX + GPU + CXL 的核心论文 | 否 | citeturn23search2turn23search6 |
| ISCA 2026 | 本轮未检到比 OSDI/FAST 更强的直系条目 | — | — | 需人工复核 | 是 |  |
| MICRO 2025 / 2026 | 本轮未检到强相关主论文 | 未发现与本主题直接强相关论文 | — | 需人工复核 | 是 |  |
| HPCA 2025 / 2026 | 本轮未检到直接主证据 | 可迁移的 CXL / tiered memory 体系结构论文存在 | — | 更适合作背景而非主表 | 是 | citeturn29search5 |
| SC 2025 / 2026 | 本轮未检到强相关主论文 | 未发现与本主题直接强相关论文 | — | 需人工复核 | 是 |  |
| SIGMOD / VLDB / CIDR 2025 / 2026 | 是 | **Beluga**（SIGMOD 2026） | — | 数据系统 venue 里最强直接命中 | 否 | citeturn28search24turn28search16 |
| MobiSys / SenSys / SEC / IoTDI 2025 / 2026 | 有边缘相关，但最终强证据更多落在 ASPLOS/SOSP/arXiv | llm.npu、HeteroInfer、Challenging GPU Dominance 更适合援引 | — | 会议本身本轮未做完善 TOC 逐篇核对 | 是 | citeturn37search0turn21search2turn36search0 |
| arXiv / OpenReview / 工业技术博客 / 官方文档 | 是 | **APEX、HybridGen、Tutti、ITME、FluxMoE、DALI、GenServe、DisagFusion、KernelSight-LM、Kareto、ProfInfer、vLLM / SGLang / LMCache / TensorRT-LLM / Dynamo / UCM 文档** | — | 这是 2026 上半年最重要的补证来源 | 否 | citeturn19search6turn23search11turn7search1turn29search6turn9search0turn8search3turn15search3turn16search0turn18search0turn18search1turn32search2turn27search0turn11search1turn24search0 |

## 强相关论文总表

下表只列这一轮我认为**最值得进入 PPT 主叙事**的强相关证据。为了保证可读性，我把 26 个字段压缩成最关键的几列；详细解释放在下一节分方向表。

| 方向 | 论文 / 系统 | 来源 / 时间 / 状态 | 关键机制 | 状态对象与数据路径 | 结论标签 |
|---|---|---|---|---|---|
| A | **NEO** | MLSys 2025；预印本 2024；正式发表 | CPU 承担部分 decode attention 与 KV 状态；asymmetric GPU-CPU pipeline；load-aware scheduling | KV 部分驻留 CPU；GPU↔CPU 往返；靠重叠换 batch 提升 | A1、A3 双强证据 citeturn38search0turn38search2 |
| A | **FlexInfer** | MLSys 2025；正式发表 | 动态选择 CPU 计算 / offload 策略；针对资源受限单 GPU | CPU 既是算力也是内存层；GPU↔CPU | A1 的“CPU 不是纯搬运” citeturn22search0turn22search7 |
| A | **Fast On-device LLM Inference with NPUs** | ASPLOS 2025；正式发表 | prompt-chunking、outlier extraction、block scheduling；NPU 主算、CPU/GPU 辅助 | NPU + CPU/GPU 端侧协同；统一内存/静态图约束 | A1 的端侧 NPU 证据 citeturn37search0turn37search2turn37search4 |
| A | **HeteroInfer** | SOSP 2025；预印本名 HeteroLLM | GPU-NPU 层级/张量级并行；CPU 仅 control plane | SoC 统一内存；GPU/NPU 同驻留；CPU 控制 | A1 但“CPU 少算多控”反例也很重要 citeturn20view1turn21search2 |
| A | **LIA** | ISCA 2025；正式发表 | CPU AMX 子计算 + CXL offloading + single-GPU inference | GPU↔CPU↔CXL；CPU 既算又扩容 | A1+A3 的硬件规格反推强证据 citeturn23search2turn23search6 |
| A | **APEX** | arXiv 2025；预印本 | profiling-informed CPU/GPU parallel scheduling | GPU↔CPU；解码期动态重叠 | A3 的“收益判定器”雏形 citeturn19search6turn38search12 |
| A | **HybridGen** | arXiv 2026；预印本 | CPU–GPU collaborative attention；CPU 处理较老 / offloaded KV | GPU local KV + CPU local KV；attention 分摊 | A1 与 B 的交叉证据 citeturn23search11turn19search3 |
| B | **Mooncake** | FAST 2025 + 官方文档/开源 | KVCache-centric disaggregated architecture；PD/远端 KV store | device/host/remote 多层；Transfer Engine / Store | B 的奠基工作 citeturn11search15turn24search7 |
| B | **IMPRESS** | FAST 2025；正式发表 | importance-informed multi-tier prefix KV storage | GPU/CPU/Disk 三层；只回流重要 KV | B 的“重要性选择 + 存储分层” citeturn26search2turn26search6 |
| B | **KVCache Cache in the Wild** | USENIX ATC 2025 | 生产工作负载画像 + workload-aware eviction | KV 复用分布与 eviction 策略 | B、G 的真实世界依据 citeturn7search3turn7search7 |
| B | **SYMPHONY** | NSDI 2026；正式发表 | advisory requests 驱动的 KV 迁移与 disaggregation | KV 从 compute 脱耦到 memory layer | B 的 cluster 级状态管理强证据 citeturn26search3turn26search7 |
| B | **Tutti** | arXiv 2026；预印本 | GPU-centric KV object store；GPU io_uring；slack-aware scheduling | GPU↔SSD direct object I/O；削弱 CPU 介入 | B 的 SSD 对象化最强证据之一 citeturn7search1 |
| B | **SolidAttention** | FAST 2026；正式发表 | SSD-based serving on memory-constrained PCs；按需低重要度块处理 | DDR/SSD/attention block | B 在小算力 PC 上最贴近落地 citeturn26search1turn26search17 |
| B | **Beluga** | SIGMOD 2026；正式发表 | CXL memory pool + Beluga-KVCache | GPU/CPU ↔ CXL shared memory pool | B+A3 的 CXL 强证据 citeturn28search24turn29search14 |
| B | **ITME** | arXiv 2026；预印本 | disaggregated CXL-hybrid memories；TB 级字节可寻址扩容 | GPU server ↔ remote CXL-hybrid memory ↔ NVMe | B+A3 的远程温层路线 citeturn29search6turn29search2 |
| B | **ECHO** | OSDI 2026；正式发表 | native sparse attention + lossless prefetch KV offloading | sparse-attn 下的 KV offload / prefetch | A+B 结合的新证据 citeturn30search0turn30search1 |
| C | **Fiddler** | ICLR 2025；正式发表 | CPU-GPU orchestration for MoE；用 CPU 计算换传输 | GPU↔CPU expert execution | C 的经典基线与正例 citeturn10search13turn10search1 |
| C | **HybriMoE** | DAC 2025；正式发表 | intra-layer CPU/GPU scheduling + inter-layer prefetch + score cache | Expert 对象在 CPU/GPU 间动态分配 | C 的阶段化专家协同 citeturn35search3turn35search7 |
| C | **KTransformers** | SOSP 2025；正式发表 | CPU/GPU hybrid inference for MoE；kernel + layout + scheduling | Expert/weight block 视为可流式对象 | C 的工程实现代表作 citeturn31search0turn31search2 |
| C | **FloE** | ICML 2025；正式发表 | on-the-fly expert I/O reduction + compression | Expert matrices 流式搬运 | C 的 memory-constrained GPU 证据 citeturn9search9turn35search5 |
| C | **DAOP** | DATE 2025；正式发表 | data-aware offloading + predictive pre-calculation | Expert 在 CPU/GPU 间动态放置 | C 的 on-device / graceful degradation 证据 citeturn35search2turn35search6 |
| C | **FineMoE** | EuroSys 2026；正式发表 | fine-grained expert offloading | Expert page / map / hit-rate 优化 | C 的 hit-rate 与 latency tradeoff 证据 citeturn10search0turn10search12turn8search18 |
| C | **FluxMoE** | arXiv 2026；预印本 | expert paging；decouple expert residency | expert transient materialization | C 的“专家不必常驻显存”表述来源 citeturn9search0 |
| C | **DALI** | arXiv 2026；预印本 | workload-aware offloading for MoE | CPU/GPU + workload-aware 策略 | C 的本地 PC 导向证据 citeturn8search3 |
| D | **Cronus** | OpenReview / arXiv 2025 | partially disaggregated prefill on heterogeneous GPUs | prefill 分段; low-end/high-end GPU 协同 | D 的“异构 PD”证据 citeturn11search0turn11search4 |
| D | **TensorRT-LLM Disaggregated Serving** | 官方文档 / 工业博客 2026 | context / generation server 拆分；KV exchange | prefill→decode KV transfer | D 的工业产品化证据 citeturn11search1turn11search17 |
| D | **vLLM PD + NixlConnector / MoRI-IO** | 官方文档 / 博客 2025–2026 | KV connector 抽象；异步 KV transfer；single-node / multi-node PD | prefill instance ↔ decode instance | D 的开源生态主线 citeturn27search3turn27search0turn11search10turn27search19 |
| D | **SGLang EPD** | 官方博客 / RFC 2026 | encoder / prefill / decode 三阶段拆分 | VLM encoder state + LLM KV state | D 在多模态的工程化方向 citeturn11search7turn11search3 |
| D | **HydraInfer** | arXiv 2025；预印本 | hybrid EPD disaggregation for MLLM | encoder state / prefill KV / decode KV | D/F 交叉强证据 citeturn15search1 |
| D | **TriInfer** | MLSys 2026 slides；低置信 | stage-centric abstraction + dual-stream | Encode/Prefill/Decode stage objects | D/F 低置信但方向很重要 citeturn14search5turn16search1 |
| E | **KVFlow** | arXiv / OpenReview 2025 | workflow-aware KV cache management | Agent Execution Graph 引导 prefix/KV 留存 | B 延展到 agent 的关键证据 citeturn13search11turn13search17 |
| E | **Tokencake** | arXiv 2025 | KV-cache-centric serving for multi-agent apps | tool-call stall 期间 proactive offload/upload | E 的强证据 citeturn13search8turn13search14 |
| E | **PBKV** | arXiv 2026 | prediction-based KV-cache management | 预测未来 agent invocation 的 KV pin/offload | E 的 workflow 预测路线 citeturn13search0 |
| E | **Continuum** | OpenReview / arXiv 2025–2026 | TTL-based KV retention for tool-call jobs | GPU KV pin with TTL；到期驱逐 | E 的 “tool wait TTL” 核心证据 citeturn25search5turn13search19 |
| E | **ThunderAgent** | arXiv 2026 | program-aware scheduler + tool resource manager | GPU KV / CPU / remote tools 联合调度 | E 与 A/B/G 的跨层证据 citeturn13search15turn13search9 |
| F | **Understanding Diffusion Model Serving in Production** | SoCC 2025 | 生产 workload / scheduling / resource efficiency 分析 | diffusion pipeline stage/object 画像 | F 的现实工作负载基线 citeturn14search0turn16search17 |
| F | **GenServe** | arXiv 2026 | step-level, preemptible diffusion serving | diffusion step 作为可调度对象 | F 的 serving 化证据 citeturn15search3 |
| F | **DisagFusion** | arXiv 2026 | asynchronous pipeline parallelism + elastic scheduling | disaggregated diffusion stages | F 的阶段拆分证据 citeturn16search0 |
| F | **StreamDiffusionV2** | arXiv 2025 | SLO-aware batching + block scheduler + rolling KV | rolling KV + motion-aware noise control | F 最接近“rolling state”系统证据 citeturn16search3turn16search18 |
| F | **TeaCache / FasterCache** | CVPR 2025 / ICLR 2025 | feature cache across diffusion steps | latent / feature cache | 是“缓存算法”证据，不是完整 serving 分层系统 citeturn14search18turn14search14 |
| G | **KernelSight-LM** | arXiv 2026 | kernel-level LLM inference simulator | roofline + host overhead + batching/cache | G 的细粒度 what-if 工具 citeturn18search0 |
| G | **Kareto** | arXiv 2026 | simulation-driven tiered-storage multi-objective optimizer | KV tier config Pareto search | G 的收益边界建模工具 citeturn18search1turn18search14 |
| G | **ProfInfer** | arXiv 2026；MLSys 2026 Industry | eBPF-based fine-grained profiler | runtime/operator/thread 画像 | G 的低侵入 profiler citeturn32search2turn32search14turn32search10 |
| G | **ServeGen** | NSDI 2026 | production workload characterization + generator | request trace / workload card | G 的现实流量生成证据 citeturn32search9turn32search13 |
| G | **BurstGPT** | KDD 2025 | 10.31M trace / 213 days workload dataset | serving trace | G 的公共 trace 基线 citeturn17search0turn17search12turn17search8 |
| G | **CCL-Bench / Chakra / TokenPowerBench** | arXiv 2026 / MLCommons / AAAI 2026 | trace benchmark / standardized execution trace / energy benchmark | compute-mem-comm evidence + phase-aligned energy | G 的 benchmark / co-design 工具链 citeturn33search0turn32search4turn32search12turn34search2turn34search11 |

## 分方向详细论文表与机制收敛

### 阶段化 A+K 协同计算

#### 代表论文与核验结果

| 论文 / 系统 | 机构 | 状态 | 机制与改动层级 | 硬件 / workload / baseline / 结果 | 迁移到 Ascend + Kunpeng |
|---|---|---|---|---|---|
| **NEO** | Harvard / UC Berkeley 等 | MLSys 2025，A 级 | 在 **Scheduler + KV/Attention 路径** 上重构流水：把部分 decode attention 与 KV 状态放到 CPU，配合 asymmetric GPU-CPU pipeline 与 load-aware scheduling | 覆盖 T4、A10G、H100 和 7B/8B/70B；对 GPU-only baseline，在 T4 / A10G / H100 上分别可达 **7.5× / 26% / 14% throughput** 提升且延迟相当；更强 CPU 时 A10G 可达 **79.3%** throughput 提升。citeturn38search2 | **中**。需要 NPU/CPU 之间的低开销 KV 访问接口、异步调度 hook、attention 子路径切分能力；结果不能直接照搬到 Ascend，因为 NPU kernel 与 host-runtime 形态不同。 |
| **FlexInfer** | Georgia Tech / Meta / Intel Labs 等 | MLSys 2025，A 级 | 在 **Scheduler + Runtime** 层做策略切换：不是死板 offload，而是根据硬件配置和运行时参数，在 CPU 计算与 offload 之间动态选路 | 论文主张在资源受限单 GPU 中，利用 CPU 计算弥补纯 offload 的 PCIe 瓶颈；官方宣传给出 **up to 12.5×** 相比既有方法的性能改善，但使用时必须把 baseline、模型、资源约束放在同一语境比较。citeturn22search0turn22search4 | **中高**。非常适合迁移成 Ascend + Kunpeng 的策略框架，尤其是“CPU 能算就不要只搬”；但需要引擎提供 per-op / per-layer fallback hook。 |
| **llm.npu** | BUPT / Peking University / 等 | ASPLOS 2025，A 级 | 在 **Prompt / Tensor / Block 三层**重构 prompt 与模型：prompt chunking、outlier 提取到 CPU/GPU、block out-of-order scheduling 到 NPU/CPU/GPU | 端侧场景，预填充平均 **22.4×** 加速、平均 **30.7×** 能耗降低、端到端应用最高 **32.8×**，并首次在手机端实现十亿级模型预填充超过 **1000 tok/s**。citeturn37search2 | **高**。因为 Ascend NPU 也存在静态图、shape 敏感、host-side 图管理等共性；但具体收益与手机 SoC 统一内存条件不同。 |
| **HeteroInfer** | SJTU 等 | SOSP 2025，A 级 | **GPU-NPU 层级/张量级并行**，CPU 主要做同步和 GPU kernel scheduling；强调按 prefill/decode 阶段选择不同 partition 策略 | Qualcomm 8 Gen 3 SoC；相对 MLC 和 MNN 的表述里给出 **1.34×–6.02× end-to-end speedup**，也给出 **9.99× / 4.36×** 等不同基线版本数字；关键不是 CPU 算得多，而是 **CPU 作为低开销控制面**。citeturn21search1turn20view1 | **高**。对 Ascend + Kunpeng 的启发正是：CPU 不一定直接做主算，但必须承担细粒度同步、图调度、shape-aware 决策。 |
| **LIA** | University of Illinois / Intel / 等 | ISCA 2025，A 级 | **AMX-enabled CPU 子计算 + CXL offloading + 单 GPU** 协同；改变 **Kernel / Runtime / Memory Placement** 三层 | 官方摘要重点强调 cooperative CPU-GPU computation 与 CXL offloading；适合支撑“CPU SIMD/AMX 能力会改变收益边界”的 PPT 表述。citeturn23search2turn23search6 | **中高**。可迁移逻辑是“Kunpeng SVE/矩阵扩展是否足够强”，但 AMX 细节不可直接照搬。 |
| **APEX** | arXiv 2025 | C 级 | **profiling-informed** CPU/GPU parallel scheduling；不是静态规则，而是预测子任务时长，最大化重叠 | 在 T4 / A10 上、用 Llama-2-7B 与 Llama-3.1-8B，相对 vLLM 等 GPU-only 调度，吞吐提升 **84%–96%**（T4）与 **11%–89%**（A10）；相对已有 hybrid schedulers，在长输出下再高 **49%**（T4）与 **37%**（A10）。citeturn19search6 | **高**。软件上很适合先做原型，因为它依赖 profiler + scheduler，而不是特定 CUDA kernel。 |
| **HybridGen** | arXiv 2026 | C 级 | **CPU–GPU 协同 attention**：GPU 处理近端 token，CPU 处理较老/offloaded KV；本质是 A+K 融合 | 这是第一批把长上下文 attention 明确拆成 CPU/GPU 双局部内存协同的工作之一；它证明 CPU 参与不只是搬 KV，而是直接参与 attention 计算。citeturn23search11 | **中高**。只要 Ascend 生态能拿到足够细的 attention hook 与 CPU-side selection path，就有实验价值。 |

#### 综合分析

这一方向经过第二轮补证后，可以很明确地收敛成一句工程话：**CPU 不是“不得已的 offload 终点”，而是阶段化 A+K 协同中的第二执行平面。** NEO 和 APEX 给的是在线 decode-heavy 场景里的正例；FlexInfer 和 LIA 给的是单机受限 GPU/CPU+内存层的正例；llm.npu、HeteroInfer 给的是端侧 NPU/GPU/CPU 三者分工的正例；HybridGen 则直接把“CPU 参与 attention”拉到了长上下文主路径上。citeturn38search2turn19search6turn22search0turn23search2turn37search2turn21search1turn23search11

这些工作共同说明，CPU 参与之所以可能赚钱，通常来自三种收益叠加。第一，**HBM/VRAM 释放带来的 batch 放大**，这是 NEO/FlexInfer/LIA 的共同逻辑。第二，**把 GPU/NPU 不擅长的小粒度、形状不友好、低并行度、状态相关路径挪到 CPU**，这是 llm.npu 与 HeteroInfer 的核心。第三，**利用 CPU 本地 DRAM 持有旧状态，让 attention 在两边的局部内存上并行**，这是 HybridGen 的价值。citeturn38search2turn22search0turn37search2turn20view1turn23search11

对你的 PPT 来说，这一方向更准确的表述不是“CPU 协助 GPU/NPU 推理”，而是：**“在 Prefill、Decode、Attention、MoE、端侧 NPU、长上下文等不同阶段，CPU 既可以做控制平面，也可以做收益为正的子路径执行平面；关键不在于 CPU 有没有参与，而在于它参与的那段计算能否释放 HBM 并与主生成路径重叠。”** 这句话既和论文机制一致，也直接服务于规格反推。citeturn38search2turn23search2turn19search6turn23search11

### 模型状态对象化与分层回流

#### 代表论文与工程系统

| 条目 | 状态与来源 | 状态对象类型 | 数据驻留层级与搬运路径 | 核心结果 / 价值 | 可靠性 |
|---|---|---|---|---|---|
| **Mooncake** | FAST 2025 + 开源文档 | KV / Prefix / Store handle | device ↔ host ↔ remote store；Transfer Engine / Store | 把 KV 从“引擎内缓存”升级为共享外部对象层，是后续 LMCache / SGLang / vLLM connector 生态的支点之一。citeturn11search15turn24search7 | A |
| **LMCache** | 官方文档 / 博客 / connector | KV / Prefix / external cache object | GPU ↔ CPU memory ↔ disk / remote connector | LMCache 官方叙事已明确把 KV 从临时缓存提升为可外部化、可连接、可跨引擎共享的对象；与 vLLM 的 dynamic connector 集成是 2025 的关键节点。citeturn24search18turn27search1turn27search12 | D |
| **IMPRESS** | FAST 2025 | Prefix KV | GPU / CPU / Disk 三层 | 只回流“重要 token”的 prefix KV，说明分层回流不应该是“整块全搬”。citeturn26search2turn26search6 | A |
| **KVCache Cache in the Wild** | ATC 2025 | KV reuse metadata | 主要是 cache policy 层 | 生产数据表明复用高度偏斜；vLLM 社区引用其统计称 10% KV block 占 77% 复用，这对“热/冷对象”分层极重要。citeturn7search3turn13search19 | A |
| **SYMPHONY** | NSDI 2026 | KV migration object | compute pool ↔ memory layer；迁移前置到关键路径外 | 可在类似延迟下支撑超过 **8×** 请求数，证明状态外移不是单纯存储，而是 cluster scheduling 资源。citeturn26search7 | A |
| **Tutti** | arXiv 2026 | GPU-native KV object | GPU↔SSD direct object I/O，CPU 只异步装载 I/O kernel | 相比 GDS-enabled、SSD-backed LMCache，**TTFT 降 78.3%**、可承载请求率 **2×**、服务成本 **降 27%**，几乎逼近 DRAM-backed LMCache。citeturn7search1 | C |
| **SolidAttention** | FAST 2026 | KV block / attention-selected blocks | DDR / SSD / attention runtime | 在 128k context 下，速度最高 **3.1×**，KV footprint 最高 **降 98%**。citeturn26search1 | A |
| **Beluga** | SIGMOD 2026 | KVCache in CXL pool | GPU/CPU ↔ CXL switch-based memory pool | 正式发表信息已确认；公共摘要强调共享大内存池与 near-local load/store 语义，是 CXL 温层的高质量证据。citeturn28search24turn29search14 | A |
| **ITME** | arXiv 2026 | weights + prefix + KV in tiered remote memory | GPU server ↔ CXL-hybrid memory ↔ NVMe | 通过生产级 CMM 和 Gen5 SSD + FPGA prototype，给出 **最高 35.7% throughput** 提升。citeturn29search6 | C |
| **ECHO** | OSDI 2026 | sparse-attn KV subset | CPU offload + lossless prefetch | 说明 native sparse attention 的 KV offload 不再只是算法，而是系统级 prefetch 问题。citeturn30search0turn30search1 | A |
| **vLLM KV Connector / NixlConnector** | 官方文档 2025–2026 | KV transfer object | prefill instance ↔ decode instance，异步 send/recv | vLLM 已把 KV 传输抽象成 connector，这是“状态对象化”的直接工程体现。citeturn27search0turn27search3turn27search9 | D |
| **SGLang HiCache** | 官方项目/文档 | multi-tier KV cache | device / host / remote | 官方说明把 RadixAttention 扩展为 device-host-remote 多层 KV，是 HiCache 方向的工程证据。citeturn11search15 | D |
| **UCM for vLLM-Ascend** | 官方文档 | external prefix/KV storage | local DRAM + shared backend（NFS/3FS/企业存储） | UCM 官方明说它是 external KV-cache storage layer，而不是设备内 pool aggregation。citeturn24search0turn24search14 | D |

#### 综合分析

这一方向在 2025–2026 已经非常明确地收敛成一个系统命题：**KV / Prefix / Context 不再是“某个 engine 的内部实现细节”，而是“跨实例、跨层级、跨节点、跨介质的状态对象”。** Mooncake、LMCache、vLLM connector、UCM 分别从存储层、引擎层、connector 层和 Ascend 生态层证明了这一点；Tutti、Beluga、ITME 把它推进到 SSD/CXL/远端内存的数据面；SYMPHONY 把它推到调度面。citeturn11search15turn24search18turn27search0turn24search0turn7search1turn29search14turn29search6turn26search3

对你的 PPT，最值得吸收的工程表述是：**“对象化”的真正含义，不只是‘能 cache’，而是能被命名、命中、pin、prefetch、restore、evict、压缩、跨 runtime 迁移，并且有单独的数据面。** 这一点在 vLLM 的 KV connector、Mooncake Store、UCM、Tutti 的 GPU-native object store 里都已经是显式设计，而不再是隐式实现。citeturn27search0turn24search0turn7search1turn24search7

更重要的是，这一方向已经出现明确分层：**HBM/VRAM 是热层，CPU DRAM/DDR 是温热层，CXL pool 更适合作为温层扩容，SSD/NVMe 是冷层或容量层，remote store 则是共享持久层。** 但能不能赚钱，不取决于“有没有更大容量”，而取决于有没有对象布局、批量 I/O、direct path、prefetch 优先级以及 restore 时机控制。Tutti 对此给出了最强的 SSD 证据，Beluga/ITME 对此给出了最强的 CXL 证据。citeturn7search1turn29search14turn29search6

### MoE 专家对象化与阶段拆分

#### 代表论文

| 论文 / 系统 | 状态 | 核心对象 | 系统层 | 结果与边界 | 一句话用途 |
|---|---|---|---|---|---|
| **Fiddler** | ICLR 2025 | Expert | CPU-GPU orchestration | 单张 24GB GPU 上跑未压缩 Mixtral-8x7B，超 **3 tok/s**，较既有方法有量级提升。citeturn10search1 | 证明 CPU 参与 expert 计算有现实价值 |
| **HybriMoE** | DAC 2025 | Expert + cache score | scheduler + prefetch + caching | 动态层内 CPU/GPU 分工、层间预取、score cache；是阶段化专家协同的代表。citeturn35search3turn35search7 | 证明 “expert prediction + prefetch” 是系统问题 |
| **KTransformers** | SOSP 2025 | Expert / weight block | memory layout + kernel + scheduler | 正式论文已确立其不是单纯开源项目，而是完整 hybrid inference 系统。citeturn31search2turn31search11 | 证明 expert 可被“分页化”而非常驻 |
| **FloE** | ICML 2025 | Expert matrices | runtime + compression | OpenReview/ICML 页面给出“几乎 **49×** 更快”的 consumer GPU 结果，但要注意它强依赖其内部压缩/稀疏利用策略。citeturn9search1turn9search9 | 证明 memory-constrained GPU 上专家 I/O 是头号瓶颈 |
| **DAOP** | DATE 2025 | Expert | GPU-CPU execution + prediction | 对传统 expert caching/prefetch 基线最高 **8.20×**，对 offloading 基线 **1.35×**。citeturn10search2turn35search6 | 证明 CPU 预计算 predicted expert 可赚钱 |
| **FineMoE** | EuroSys 2026 | Fine-grained expert map/page | Expert manager | expert hit rate 相对 Mixtral-Offloading / ProMoE / MoE-Infinity 平均提升 **14% / 37% / 68%**。citeturn8search18 | 证明专家对象要做细粒度管理 |
| **FluxMoE** | arXiv 2026 | Expert paging object | paging abstraction | 内存紧张时相对 vLLM 吞吐最高 **3.0×**。citeturn9search0 | 证明 expert residency 可与 KV residency 解耦 |
| **DALI** | arXiv 2026 | Expert | workload-aware offloading | 直接点名支持资源受限本地 PC。citeturn8search3 | 证明本地方向仍在持续推进 |
| **DuoServe-MoE** | arXiv 2025 | Prefill experts / Decode experts | dual-phase scheduling | 端到端延迟 **1.42–7.54×** 改善，峰值显存仅全模型 **15%**。citeturn9search2 | 证明 prefill/decode 的 expert 策略应分开做 |

#### 综合分析

MoE 方向里最重要的收敛，不是“专家 offload”这四个字，而是**专家已经被当成对象而非静态权重页来管理**。从 Fiddler 到 KTransformers，再到 FineMoE、FluxMoE、DALI，几乎都在处理同一件事：**哪些 expert 常驻，哪些 expert 预取，哪些 expert 立即回收，哪些 expert 可在 CPU fallback 执行，哪些 expert 该按 prefill 与 decode 使用不同策略。** citeturn10search1turn31search2turn10search0turn9search0turn8search3

这对你的三条技术方向同时有价值。对方向一，它证明 **expert prediction / cold expert fallback / CPU expert execution** 都已不是想法，而是公开系统论文主题。对方向二，它证明 **expert-object management** 是 2026 年可以正大光明写进 PPT 的术语。对方向三，它证明要反推的硬件规格，不只是 GPU 显存大小，还包括 **CPU SIMD/AMX/SVE 吞吐、主存带宽、prefetch 深度、I/O 并发与 expert hit-rate 稳定性**。citeturn35search7turn31search2turn8search18turn23search9

### 阶段拆分、Agent 工作流与多模态视频流水

#### 阶段拆分与异构放置

| 条目 | 结论 | 证据 |
|---|---|---|
| **Cronus** | 把 prefill 的初段放低端 GPU、其余 prefill 与 decode 放高端 GPU，说明“异构 PD”不一定是跨节点，也可以是**同集群异构 GPU 组合**。 | citeturn11search0turn11search4 |
| **TensorRT-LLM Disaggregated Serving** | NVIDIA 已把 context/generation server、KV exchange、orchestrator 做成官方文档级能力，说明 PD 已产品化。 | citeturn11search1turn11search17 |
| **vLLM PD + NixlConnector / MoRI-IO** | vLLM 把 disaggregated prefilling 与 connector 抽象正式化，MoRI-IO 甚至扩展到 AMD/ROCm 单节点 PD。 | citeturn27search3turn27search0turn11search10turn11search6turn27search19 |
| **SGLang EPD** | EPD 已被明确写成 “Encoder-Prefill-Decode Disaggregation”，并用于 Vision-Language Models。 | citeturn11search7turn11search3 |
| **HydraInfer / TriInfer** | 说明 EPD 已从工程文档进入公开研究；HydraInfer 给出 **up to 4× throughput**，TriInfer slides 给出 **up to 2.4× goodput**。 | citeturn15search1turn14search5 |
| **SuperInfer** | 适合 GH200 / NVLink-C2C 场景，核心是 SLO-aware rotary scheduling 与 DuplexKV；但公开发表状态仍需保守对待。 | citeturn12search6turn12search2 |

#### Agent / workflow-aware KV 生命周期

KVFlow、Tokencake、PBKV、Continuum、ThunderAgent 已经把“KV cache 管理”从单轮 prefix reuse 推进到 **workflow graph、tool wait、program abstraction、TTL retention、prediction-based pin/offload**。这意味着在 agent 场景里，状态回流不再只是“命中就快，不命中就重算”，而是**等待窗口是否足够长、是否值得 pin、是否该迁到 DRAM/SSD、以及何时重新提回到热层**。citeturn13search17turn13search14turn13search0turn25search5turn13search15turn13search6

对 “A+K 协同异构推理” 来说，这一类论文非常重要，因为它们把 **K** 从“KV cache 内部技术细节”升级为**跨 agent step 的生命周期对象**。这恰好为你第二个方向“模型状态对象化与分层回流”提供了最现实的业务驱动。citeturn13search17turn13search15

#### 多模态与视频生成流水

当前公开证据显示，多模态和视频生成正在沿三条线前进。第一条线是 **生产 serving 与 workload characterization**，代表是 *Understanding Diffusion Model Serving in Production*；第二条线是 **异构阶段拆分**，代表是 HydraInfer、TriInfer、DisagFusion、GenServe；第三条线是 **跨 step / 跨 frame 的缓存与 rolling state**，代表是 StreamDiffusionV2、TeaCache、FasterCache。citeturn14search0turn15search1turn14search5turn16search0turn15search3turn16search3turn14search18turn14search14

但需要非常明确地写在报告里：**截至 2026-06-30，我没有找到一篇“视频生成 serving + Noise Cache / rolling KV / latent state 对象化 + DRAM/SSD/CXL 分层回流”一体化的完整系统论文。** StreamDiffusionV2 已经有 rolling KV 与实时流水，TeaCache / FasterCache 已经有 feature cache，但它们还没有像 Mooncake / Tutti / Beluga 那样，把视频状态真正做成跨介质对象层。这个空白点，恰恰适合作为研究机会。citeturn16search3turn14search18turn14search14turn16search0turn15search3

### Trace、Profiler、Simulator、Energy Model 与规格反推

| 条目 | 作用 | 为什么对你的 PPT 重要 |
|---|---|---|
| **KernelSight-LM** | kernel-level simulator，建模 roofline + communication + host overhead + batching/cache | 可直接支撑“收益判定先仿真后落地”的说法。citeturn18search0 |
| **Kareto** | 针对 KV tiered storage 的 simulation-driven Pareto optimizer | 是“收益边界与规格反推”最贴近你问题定义的工具。citeturn18search1turn18search14 |
| **ProfInfer** | eBPF 细粒度 LLM inference profiler，<4% overhead | 适合小算力一体机做非侵入性能画像。citeturn32search2turn32search14 |
| **ServeGen** | 生产级 workload characterization + workload generation | 可以把本地/企业负载画像到更现实，而不是 synthetic benchmark。citeturn32search9turn32search13 |
| **BurstGPT** | 开放真实 trace 数据 | 适合校验“多轮/长尾/峰谷”下 cache 策略。citeturn17search0turn17search12 |
| **CCL-Bench / Chakra** | trace-based benchmark / standardized trace ecosystem | 支撑 what-if、post-hoc metric extension、软硬件共设计。citeturn33search0turn32search4turn32search12 |
| **Characterizing LLM Inference Energy-Performance Tradeoffs across Workloads and GPU Scaling** | 能源–性能权衡分析，已在 CCGrid 2026 出现 | 对功耗预算、单机多卡规模选择很关键。citeturn17search1turn17search17turn17search21 |
| **TokenPowerBench** | 按 prefill / decode 对齐能耗归因 | 直接支撑“阶段不同，能耗模型也不同”。citeturn34search2turn34search11 |

这一方向意味着你的第三个技术方向不应只写“硬件-aware scheduling”，而应写得更具体：**“以 trace / profiler / simulator / phase-aligned energy model 为基础，做 CPU 子计算、KV 回流、专家预取、PD/EPD、SSD tiering 的收益判定与规格反推。”** 这已经有一整条文献链能支撑，而不再是经验判断。citeturn18search0turn18search1turn32search2turn32search9turn34search2

## 反例与收益边界

### 什么时候不应该做 CPU 参与

CPU 参与失败的根本原因，不是“CPU 慢”，而是**CPU 参与的那段工作没有抵消掉新增的数据搬运、同步、格式转换和调度开销**。NEO、LIA、APEX 这些正例都隐含了同一个前提：CPU 计算必须和 GPU 主路重叠，且要换来更大的有效 batch 或更少的 HBM 压力；如果做不到这一点，PCIe/CXL 传输与 host-side 管理就会把收益吃掉。citeturn38search2turn23search2turn19search6

对小算力工作站尤其要警惕三件事。第一，**CPU 子任务太碎**。短到亚毫秒级的 attention 子块、outlier block、tiny matmul，如果需要频繁 GPU↔CPU round-trip，往往会输给纯 GPU 执行。第二，**CPU SIMD/AMX/SVE 不足**。LIA/Fiddler/KTransformers 这类工作之所以能让 CPU “可算”，依赖的是矩阵扩展、缓存/内存局部性和流水重叠；没有这些能力，CPU fallback expert 很容易变成“高延迟救火”。第三，**DRAM 带宽不足**。如果 CPU 端既要跑 expert，又要承担 KV restore / prefix merge / metadata aggregation，它很快就会从计算瓶颈转化成内存瓶颈。citeturn23search2turn10search1turn31search2turn23search9

### 什么时候不应该做 KV offload 与 SSD tiering

KV offload 不赚钱最常见的原因是：**offload 粒度太细，导致 tiny I/O 和 metadata overhead 远大于有用数据搬运**。Tutti 的核心结论恰恰是，传统 SSD-backed KV restore 的问题并不只是 SSD 慢，而是 GPU 内存布局碎片化，导致需要海量 tiny random I/O；即便启用 GDS，CPU 仍然在每次 I/O 发起上成为 bottleneck。citeturn7search1

因此，如果系统还停留在“块很小、布局碎、每次 I/O 由 CPU 单发单收”的实现层面，那么 **顺序带宽再高也救不了 restore latency**。这也是为什么 Tutti 强调 GPU-native object abstraction 与 GPU io_uring，而 SolidAttention 和 IMPRESS 都强调对象选择与重要性缩减，而不是无脑把全部 KV 搬去 SSD。citeturn7search1turn26search1turn26search6

### 什么时候不应该做 PD / EPD

PD/EPD 在低并发、单机、上下文较短时，往往不赚钱。其原因并不神秘：**当 prefill 与 decode 的资源竞争还不严重时，阶段拆分引入的 orchestrator、KV transfer、实例隔离和负载波动可能比干扰本身更贵**。vLLM 与 TensorRT-LLM 官方材料都把 PD 写成“可分开优化 TTFT 与 ITL”的能力，而不是“永远更快”的定理。citeturn27search3turn11search17

这也是为什么 Cronus、HydraInfer、TriInfer 这类工作都强调**异构阶段建模与 SLO 约束**，而不是简单拆开就行。对 1–4 卡小服务器，若并发很低、请求波动弱、KV 传输没有 direct path，那么 colocated serving 可能依旧更实用。citeturn11search0turn15search1turn14search5

### 为什么 CXL 更适合作温层而不一定适合作热路径

Beluga 与 ITME 证明了 CXL memory pooling / hybrid memory 对 LLM 状态管理很有吸引力，但它们也隐含一个边界：**CXL 的价值首先在“容量扩展 + 编程模型简化 + shared warm tier”，而不是直接替代 HBM 的热路径带宽。** Beluga 强调的是 shared large-scale memory pool 的 load/store 语义；ITME 强调的是 proactive management 与 TB-scale expansion。两者都不是在宣称 CXL 能成为所有 decode 热路径的等价替代。citeturn29search14turn29search6

所以在小算力一体机上，CXL 更应被看成：**比 SSD 更热、比 DRAM 更远的温层**。如果把每 token 高复用、低延迟需求的热 KV 直接压到 CXL 上，收益很容易被访问时延和共享争用吃掉。citeturn29search6turn29search18

### 多模态生成里 CPU codec / VAE / postprocess 何时会成为新瓶颈

HydraInfer、TriInfer、DisagFusion 这条线表明，多模态流水一旦做了 Encode/Prefill/Decode 或 diffusion stage disaggregation，**CPU 侧的视频编解码、VAE 前后处理、图像/视频后处理就可能从“边缘成本”升级成“主瓶颈”**。尤其在视频生成或实时流式场景里，如果第一帧时延和帧间 deadline 已经很紧，那么 CPU codec 和 host-side postprocess 没有与 DiT/VAE 流水正确重叠时，会直接破坏整体 SLO。citeturn15search1turn14search5turn16search0turn16search3

## Ascend NPU 与 Kunpeng CPU 迁移表

| 机制 | 对应论文 / 系统 | CUDA / GPU 生态当前实现 | Ascend 生态可用支点 | 纯软件可做 | 需引擎 hook | 需 runtime / DMA / memory API | 需下一代硬件接口 | 最大风险 | 原型优先级 |
|---|---|---|---|---|---|---|---|---|---|
| CPU 参与 attention / decode 子路径 | NEO、APEX、HybridGen | CUDA stream + host scheduling + CPU KV access | CANN、MindIE、Kunpeng SIMD/SVE | 调度器、收益判定器、trace 采集 | attention 子路径切分、KV 选择、异步 restore | NPU↔CPU 异步拷贝 / pinned buffer API | 更低延迟 NPU↔CPU 共享地址 / direct map | Host runtime 开销高于 CUDA 生态 | **P1** citeturn38search2turn19search6turn23search11turn24search10 |
| NPU↔CPU KV offload / restore | vLLM-Ascend KV Cache CPU Offload | GPU KV offloading connector / host offload | **vLLM-Ascend KV Cache CPU Offload** | 直接可做 MVP | block manager / restore priority / pin policy | host memory registration / async copy | 更强 NPU memory map / page-fault-aware offload | 恢复 latency 与 host contention | **P0** citeturn24search8turn30search21 |
| 外部 KV store / Prefix cache | UCM、LMCache、Mooncake | vLLM KV connector / shared FS / Mooncake Store | **UCM、Mooncake on Ascend、vLLM-Ascend** | 先做 shared prefix / external cache | hash 命名、命中协议、生命周期管理 | 存储后端插件、metadata path | NPU direct storage / zero-copy register | 一致性与命中协议复杂 | **P0** citeturn24search0turn24search4turn24search14turn24search1 |
| PD / EPD 阶段拆分 | vLLM PD、SGLang EPD、TensorRT-LLM、HydraInfer | NIXL / MoRI-IO / orchestrator | **Mooncake Ascend、vLLM-Ascend PD-colocated、HCCL** | 同一机柜小集群先做 | prefill/decode/encoder stage API | KV transfer backend、跨实例调度 | 更好的 NPU↔NPU KV 直传与小消息优化 | 单机低并发下不赚钱 | **P0** citeturn24search13turn24search11turn11search7turn11search17 |
| 专家对象化与 CPU fallback expert | KTransformers、HybriMoE、FineMoE、DALI | CPU/GPU hybrid kernels + prefetch cache | Kunpeng SIMD/SVE、vLLM-Ascend EPLB、CANN EP | 先做 expert heatmap / prefetch policy | Expert Manager、router hook、fallback path | host-side expert paging / async prefetch | 更强 CPU matrix extension / NPU expert hot-swap | Kunpeng CPU 单核/带宽不足时易反噬 | **P1** citeturn31search2turn35search7turn10search0turn8search3turn24search16 |
| SSD-backed KV object store | Tutti、SolidAttention | GDS / object I/O / NVMe tiering | openEuler 存储栈、UCM 后端、Mooncake Store | 先做 CPU-bounce 版本验证收益 | object layout、restore batching、I/O prioritization | direct I/O / async polling / queue exposure | **NPU direct storage / GPU-SSD 类似直通** | 没有对象布局和 direct path 时 tiny I/O 反噬 | **P1** citeturn7search1turn26search1turn24search0 |
| CXL / pooled memory warm tier | Beluga、ITME、LIA | GH200 / CXL pool / unified memory experiments | 当前 Ascend 公开生态支点较弱 | 可先做模拟器和 software tiering | memory placement policy | page migration / remote memory API | **真正高效的 CXL / pooled memory 接口** | 当代可用硬件接口不足 | **P2** citeturn29search14turn29search6turn23search2 |
| Profiler / cost model / energy model | ProfInfer、Kareto、TokenPowerBench | Nsight / custom simulator / energy bench | openEuler eBPF、MindIE metrics、vLLM-Ascend metrics | 最适合先做 | operator timeline、KV/expert telemetry | 统一 tracing & counters | 更细的 NPU perf counter 暴露 | 没有数据就无法做收益判定 | **P0** citeturn32search2turn18search1turn34search2turn24search3 |

## 对三条 PPT 技术方向的支撑证据

### 技术方向一：阶段化 A+K 协同计算

**工程问题**：主生成路径仍应留在 GPU/NPU，但很多短粒度、形状不友好、稀疏或旧状态相关子路径，并不一定值得继续硬塞进加速器主路。citeturn38search2turn37search2turn23search11

**业内证据**：NEO、FlexInfer、llm.npu、HeteroInfer、LIA、APEX、HybridGen。citeturn38search2turn22search0turn37search2turn21search2turn23search2turn19search6turn23search11

**关键技术点**：  
- **CPU 不只是 offload 终点**：当 CPU 子计算能释放 HBM/显存并与主路径重叠时，它应被视为第二执行平面，而不是后备仓库。citeturn38search2turn23search2turn19search6  
- **按阶段分工而不是按器件均分**：prefill、decode、attention、expert、outlier、old-KV attention 的最佳执行位置不同，正确做法是阶段化切分，不是平均分流。citeturn37search2turn20view1turn23search11  
- **收益来自“扩容 + 重叠”双重兑现**：只做 CPU 计算但不释放显存，或只释放显存但不把算路重叠起来，都很容易不赚钱。citeturn38search2turn19search6

**未来趋势**：A+K 协同会继续从“CPU 帮 GPU”演变为“CPU/GPU/NPU 各自处理最合适的状态片段与计算片段”。citeturn23search11turn21search2

**不能踩的坑**：把过碎的 attention / tiny matmul / fallback expert 切到 CPU，而没有足够 SIMD、DRAM 带宽和异步重叠，会被同步与搬运反噬。citeturn23search2turn10search1turn19search6

### 技术方向二：模型状态对象化与分层回流

**工程问题**：长上下文、多轮对话、agent workflow、MoE 与多模态流水，使状态规模已经超过“单机 HBM 内临时 cache”的处理范式。citeturn6search6turn11search15turn24search0

**业内证据**：Mooncake、LMCache、SYMPHONY、Tutti、Beluga、ITME、vLLM KV Connector、UCM、SolidAttention。citeturn11search15turn24search18turn26search3turn7search1turn29search14turn29search6turn27search0turn24search0turn26search1

**关键技术点**：  
- **KV 不是 cache，而是状态对象**：它需要命名、命中、pin、prefetch、restore、evict、压缩与跨实例迁移，而不仅是命中/未命中两态。citeturn27search0turn24search0turn7search1  
- **分层不是单纯多放一层内存**：真正赚钱的是对象布局、批量 I/O、direct path、恢复优先级和热/冷状态识别。citeturn7search1turn26search1turn26search6  
- **调度与存储必须联合设计**：状态一旦外部化，就会影响请求放置、负载均衡与工具等待期间的生命周期管理。citeturn26search3turn13search15turn13search17

**未来趋势**：状态管理会进一步从 engine-private 走向 cross-instance、cross-node、cross-storage 的统一插拔层。citeturn24search0turn27search1turn24search14

**不能踩的坑**：没有对象化布局和 direct path 的 SSD/CXL tiering，常常只是在制造 tiny I/O 与 metadata 放大。citeturn7search1turn26search1

### 技术方向三：目标硬件收益预测与规格反推

**工程问题**：不是每一种 CPU 参与、KV 回流、专家预取、PD/EPD、CXL/SSD tiering 都是正收益，必须在目标规格上先算账。citeturn18search1turn18search0turn34search2

**业内证据**：KernelSight-LM、Kareto、ProfInfer、ServeGen、BurstGPT、CCL-Bench、TokenPowerBench、Characterizing LLM Inference Energy-Performance Tradeoffs。citeturn18search0turn18search1turn32search2turn32search9turn17search0turn33search0turn34search2turn17search1

**关键技术点**：  
- **先画像，再分层，再下结论**：没有 trace、operator timeline、KV 热度分布与 phase-aligned energy 数据，就谈不上正确的硬件反推。citeturn32search2turn32search9turn17search0  
- **收益边界是多目标 Pareto 问题**：吞吐、TTFT/ITL、P95/P99、显存占用、cache hit、恢复时延、功耗必须一起看。citeturn18search1turn34search2turn33search0  
- **要反推的是“组合规格”而非单点规格**：CPU 核数、SIMD/AMX/SVE、DRAM 带宽、HBM 容量、SSD IOPS、互联时延与带宽，必须按机制组合来定。citeturn23search2turn29search14turn7search1

**未来趋势**：what-if simulator、trace benchmark 与 energy model 将成为异构推理系统立项前的标准流程。citeturn18search0turn18search1turn32search4

**不能踩的坑**：只看 GPU 峰值算力或 SSD 顺序带宽，不看 host overhead、restore 粒度和尾延迟，结论大概率会错。citeturn7search1turn19search6

## PPT 可直接使用的凝练语句

### 技术方向一：阶段化 A+K 协同计算

- **工程问题**：主生成路径适合留在 NPU/GPU，但很多短粒度、稀疏、旧状态相关子路径，如果继续强塞进加速器会被同步与带宽反噬。  
- **业内证据**：NEO、FlexInfer、llm.npu、HeteroInfer、LIA、APEX。citeturn38search2turn22search0turn37search2turn21search2turn23search2turn19search6  
- **关键技术点：CPU 不是备份仓，是第二执行平面**：当 CPU 子计算能释放 HBM/显存并与主路径重叠时，CPU 参与的价值来自“扩容 + 重叠”的双重兑现，而不是单纯替代 GPU。citeturn38search2turn23search2turn19search6  
- **关键技术点：按阶段切分，不按器件均分**：prefill、decode、attention、old-KV attention、expert fallback、outlier block 的最佳放置位置不同，必须按阶段和状态类型决定 GPU/NPU 与 CPU 的分工。citeturn37search2turn20view1turn23search11  
- **关键技术点：收益由本地状态分布决定**：CPU 只有在能直接利用本地 DRAM 中的 KV/Expert/Prefix，且减少热层数据回搬时，才会形成正收益。citeturn23search11turn10search1  
- **未来趋势**：A+K 协同会从“CPU 帮忙算一点”演进为“不同状态对象由最合适的处理器就地消费”。citeturn23search11turn21search2  
- **不能踩的坑**：offload 粒度过细、CPU SIMD 不足、DRAM 带宽不够时，PCIe/CXL/同步开销会把收益全部吃掉。citeturn23search2turn19search6

### 技术方向二：模型状态对象化与分层回流

- **工程问题**：KV / Prefix / Context / Expert / Latent 不再是短命临时 tensor，而是跨请求、跨阶段、跨节点复用的长期状态资产。  
- **业内证据**：Mooncake、LMCache、vLLM KV Connector、UCM、SYMPHONY、Tutti、Beluga、ITME。citeturn11search15turn24search18turn27search0turn24search0turn26search3turn7search1turn29search14turn29search6  
- **关键技术点：状态对象先于分层策略**：先把 KV/Prefix/Expert 变成可命名、可定位、可 pin、可 restore 的对象，分层卸载和回流才真正可控。citeturn24search0turn27search0turn7search1  
- **关键技术点：温层与冷层要靠对象布局吃到收益**：HBM 是热层，DRAM/DDR 是温热层，CXL 更适合作温层，SSD/NVMe 适合作容量层；决定收益的不是容量本身，而是对象布局、批量 I/O、direct path 与恢复优先级。citeturn29search14turn29search6turn7search1turn26search1  
- **关键技术点：状态管理必须和调度联动**：一旦状态离开本地 HBM，cache hit、restore latency、实例路由、tool wait TTL 与负载均衡就是同一个问题。citeturn26search3turn13search15turn13search17  
- **未来趋势**：外部 KV 层会从“prefix cache 扩容件”演进为“统一状态平面”。citeturn24search0turn27search1turn24search14  
- **不能踩的坑**：没有 direct path 和对象化 layout 的 SSD/CXL tiering，只会带来 tiny I/O、metadata 风暴和 restore 抖动。citeturn7search1turn26search1

### 技术方向三：目标硬件收益预测与规格反推

- **工程问题**：异构协同不是“加功能就会更快”，必须先判断 CPU 子计算、KV 回流、专家预取、PD/EPD、SSD/CXL tiering 的收益是否为正。  
- **业内证据**：KernelSight-LM、Kareto、ProfInfer、ServeGen、BurstGPT、CCL-Bench、TokenPowerBench。citeturn18search0turn18search1turn32search2turn32search9turn17search0turn33search0turn34search2  
- **关键技术点：先有证据化画像，再做机制决策**：没有 trace、operator timeline、KV 热度分布与阶段对齐能耗数据，所谓“硬件-aware”只是经验主义。citeturn32search2turn32search9turn34search2  
- **关键技术点：收益边界是多目标 Pareto，而非单一吞吐最大化**：TTFT、ITL、P95/P99、显存占用、cache hit、SSD IOPS、tokens/J 必须一起看。citeturn18search1turn34search2turn33search0  
- **关键技术点：规格反推要面向机制组合**：CPU 核数、SVE/AMX、DRAM 带宽、HBM 容量、CXL 能力、SSD IOPS 与 direct path 接口要按 A+K 协同、状态分层和 PD/EPD 组合优化。citeturn23search2turn29search14turn7search1  
- **未来趋势**：基于 trace 的 what-if simulator 与 phase-aware energy model 会成为小算力一体机设计的默认方法。citeturn18search0turn18search1turn32search4  
- **不能踩的坑**：只看显存容量、互联峰值或 SSD 顺序带宽，不看 host overhead 与 restore 粒度，会把“纸面规格”误判成“系统收益”。citeturn7search1turn19search6

## 空白点与创新机会

最值得强调的空白点有四个。

第一，**“视频生成 serving + rolling KV / Noise Cache / latent state 对象化 + 分层回流”仍缺完整系统论文**。现有论文要么做 serving 拆分，要么做 feature cache，要么做 rolling KV，但尚未把这三件事与 DRAM/CXL/SSD 外部层统一起来。这个空白非常适合形成你们自己的系统叙事。citeturn16search3turn14search18turn14search14turn16search0turn15search3

第二，**Ascend + Kunpeng 小算力一体机场景的公开学术证据仍明显不足**。已有工程支点主要来自 vLLM-Ascend、UCM、Mooncake-Ascend 文档，而不是成体系统论文。这意味着你们如果先把 NPU↔CPU KV state object、外部 KV store、PD/EPD 在 Ascend 上跑通，很容易形成差异化。citeturn24search0turn24search4turn24search8turn24search13

第三，**CPU fallback expert 的“收益区间”还缺一套对小服务器友好的公开 cost model**。已经有很多 MoE offload / prefetch / paging 论文，但真正能直接回答“多少核、什么 SIMD、多少 DRAM 带宽才值得让 Kunpeng CPU 接 expert”的可迁移模型还不够成熟。citeturn31search2turn10search0turn9search0turn8search3

第四，**小算力单机/小集群上的 direct storage 与对象布局联合设计仍是明显机会**。Tutti 说明仅有 SSD 带宽不够，关键是 GPU-centric object store 与控制路径下放；这在 Ascend 生态里尚未看到同等级公开系统。citeturn7search1turn24search0

## 参考文献与链接清单

以下只列本轮报告的高承重来源，按主题聚类，便于你后续做 PPT 附页或讲稿备注。

### CPU/GPU/NPU 协同执行

- NEO — MLSys 2025 proceedings / arXiv。citeturn38search0turn38search2  
- FlexInfer — MLSys 2025 proceedings。citeturn22search0  
- Fast On-device LLM Inference with NPUs — ASPLOS 2025 / arXiv。citeturn37search0turn37search2turn37search4  
- HeteroInfer — SOSP 2025 / arXiv 预印本 HeteroLLM。citeturn21search2turn20view1  
- LIA — ISCA 2025。citeturn23search2turn23search6  
- APEX — arXiv 2025。citeturn19search6  
- HybridGen — arXiv 2026。citeturn23search11  
- Challenging GPU Dominance — arXiv 2025。citeturn36search0  

### KV / Prefix / 状态对象化与分层回流

- Mooncake — FAST 2025 / 官方文档。citeturn11search15turn24search7  
- LMCache — 官方文档 / 动态 connector。citeturn24search18turn27search1  
- IMPRESS — FAST 2025。citeturn26search2turn26search6  
- KVCache Cache in the Wild — USENIX ATC 2025。citeturn7search3turn7search7  
- SYMPHONY — NSDI 2026。citeturn26search3turn26search7  
- Tutti — arXiv 2026。citeturn7search1  
- SolidAttention — FAST 2026。citeturn26search1  
- Beluga — SIGMOD 2026 / PACMMOD。citeturn28search24turn28search16  
- ITME — arXiv 2026。citeturn29search6  
- ECHO — OSDI 2026。citeturn30search0turn30search1  
- vLLM disaggregated prefilling / NixlConnector。citeturn27search3turn27search0  
- vLLM-Ascend UCM / KV CPU Offload / Mooncake。citeturn24search0turn24search8turn24search4  

### MoE 专家对象化

- Fiddler — ICLR 2025。citeturn10search13turn10search1  
- HybriMoE — DAC 2025。citeturn35search3turn35search15  
- KTransformers — SOSP 2025。citeturn31search2turn31search11  
- FloE — ICML 2025。citeturn9search9turn35search1  
- DAOP — DATE 2025。citeturn35search2turn35search6  
- FineMoE — EuroSys 2026。citeturn10search0turn10search12  
- FluxMoE — arXiv 2026。citeturn9search0  
- DALI — arXiv 2026。citeturn8search3  
- DuoServe-MoE — arXiv 2025。citeturn9search2  

### 阶段拆分、Agent、Multimodal、Profiler

- TensorRT-LLM Disaggregated Serving。citeturn11search1turn11search17  
- SGLang EPD。citeturn11search7turn11search3  
- HydraInfer。citeturn15search1  
- TriInfer。citeturn14search5  
- KVFlow。citeturn13search11turn13search17  
- Tokencake。citeturn13search8turn13search14  
- PBKV。citeturn13search0  
- Continuum。citeturn25search5  
- ThunderAgent。citeturn13search15turn13search9  
- Understanding Diffusion Model Serving in Production。citeturn14search0turn16search17  
- DisagFusion。citeturn16search0  
- GenServe。citeturn15search3  
- StreamDiffusionV2。citeturn16search3  
- TeaCache。citeturn14search18  
- FasterCache。citeturn14search14  
- KernelSight-LM。citeturn18search0  
- Kareto。citeturn18search1  
- ProfInfer。citeturn32search2turn32search14  
- BurstGPT。citeturn17search0turn17search12  
- ServeGen。citeturn32search9turn32search13  
- CCL-Bench。citeturn33search0turn33search13  
- MLCommons Chakra。citeturn32search4turn32search12  
- TokenPowerBench。citeturn34search2turn34search11  
- Characterizing LLM Inference Energy-Performance Tradeoffs across Workloads and GPU Scaling。citeturn17search1turn17search17  

## 搜索关键词清单

本轮实际使用并扩展过的检索词主要包括以下几组。为了可复现性，我保留英文原词。

- CPU GPU collaborative LLM inference  
- CPU offloading online LLM inference  
- CPU assisted attention LLM  
- CPU fallback expert MoE  
- heterogeneous LLM inference CPU GPU  
- NPU LLM inference CPU  
- on-device LLM inference NPU CPU GPU  
- LLM inference KV cache offload CPU memory SSD  
- external KV cache LLM serving  
- KV cache tiering DRAM SSD CXL  
- KV cache object store GPU SSD  
- GPU direct storage KV cache LLM  
- NPU SSD direct storage KV cache  
- CXL memory LLM inference  
- MoE expert offloading CPU GPU  
- MoE expert prefetch LLM serving  
- mixture of experts CPU GPU hybrid inference  
- prefill decode disaggregation heterogeneous  
- encode prefill decode multimodal serving  
- diffusion model serving heterogeneous pipeline  
- video generation serving latent state cache  
- Noise Cache video generation inference  
- rolling KV video generation  
- Agent workflow KV cache  
- tool-aware KV cache TTL  
- LLM serving cost model simulator profiler  
- LLM serving energy model GPU CPU  
- hardware-aware LLM serving  
- 以及按条目精确搜索的标题级关键词，如 “NEO”, “HeteroInfer”, “Tutti”, “Beluga”, “SYMPHONY”, “KTransformers”, “FineMoE”, “TokenPowerBench”, “KernelSight-LM”, “ProfInfer”等。