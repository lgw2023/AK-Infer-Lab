# 小算力大模型推理落地与推理仿真系统构建 Deep Research 可核验整合版

核验日期：2026-07-01  
输入材料：第一轮提示词、第一轮报告、第二轮报告、本地 `AK 协同/references/` 文献库与网页快照。  
用途：支持 A+K / Ascend NPU + Kunpeng CPU 小算力一体机技术立项、论文精读、原型系统设计和推理仿真器建模。

## 核验口径与本轮修正

本报告不是重新包装 PPT 文案，而是把已有两轮 Deep Research 的主结论整理成可复核技术路线调研。正文只把有一手来源或官方文档支撑的条目放入主表；只能从预印本或项目页核验的条目标为“预印本”或“官方文档/开源系统”；没有完成官方 proceedings 级核验的会议条目不做强结论。

本轮发现三点需要修正：

1. 第二轮提示词文件为空，实际可执行要求来自第一轮提示词。
2. 第一轮/第二轮报告正文中的 `turn...` 引用是上一轮工具环境的临时引用，不能作为长期文献引用。本报告统一替换为真实 URL。
3. 本地 `AK 协同/references/papers/Tutti__arxiv-2602.04182.pdf` 内容不是 Tutti，而是 `HoloEv-Net`。Tutti 的可核验来源应使用 arXiv `2605.03375`：https://arxiv.org/abs/2605.03375。

研究问题：在显存、算力、互联和工程资源受限的小型服务器、单机多卡、边缘设备或 CPU+GPU/NPU 异构平台上，如何高效服务 dense LLM、long-context LLM 与 MoE LLM，并如何构建可用于容量反推的推理仿真系统。

方法：会议优先、关键词扩展、种子论文扩展和工程系统文档核验并行。高置信来源优先级为官方 proceedings / ACM / USENIX / OpenReview / arXiv / 官方文档 / 官方 GitHub；二手博客仅作为线索，不进入主结论证据链。

## A. 执行摘要

- 2025-2026 年最集中的系统问题不是单一 kernel 加速，而是 **runtime state management**：KV cache、MoE expert、weight、prefix、latent 等状态正在从“模型内部张量”变成可迁移、可缓存、可预取、可驱逐、可计费和可观测的对象。证据链：LMCache、Mooncake、vLLM NixlConnector、KTransformers、FineMoE、Tutti。
- 论文和系统最密集的方向是三类：CPU/GPU/NPU 异构推理，MoE expert offload/cache/prefetch，以及 KV/prefix 分层内存。代表来源包括 NEO、FlexInfer、llm.npu、KTransformers、FineMoE、Mooncake、LMCache、Tutti。
- CPU 参与推理的收益主要来自窄角色：attention/KV 冷路径、MoE 冷专家 fallback、outlier 或小矩阵路径、metadata/control plane、I/O aggregation 和 profiler/simulator host。NEO、KTransformers、llm.npu 与 vLLM-Ascend KV CPU Offload 支持这个判断。
- CPU 参与会被 PCIe/DDR/同步开销反噬。NEO、FlexInfer、KTransformers 和 llm.npu 的共同启发是：CPU 要参与“可重叠、可预测、低频或稀疏”的路径，而不是替代加速器主算。
- MoE expert 和 KV cache 正在变成同一类对象管理问题：两者都争 HBM，都需要 hotness、next-use probability、prefetch lead time、miss penalty、eviction policy 和 tier placement。证据链：FineMoE、DALI、FluxMoE、LMCache、Tutti。
- KV cache 的难点已经从“放到 CPU/SSD 上”升级为“对象布局、恢复/重算决策、I/O 颗粒度和控制路径”。Tutti 对 SSD-backed KV 的核心提醒是：tiny random I/O 和 CPU-centric control path 会让 SSD 账面带宽失效。
- Prefill/Decode disaggregation 不是默认更优。Mooncake、TensorRT-LLM Disaggregated Serving、vLLM NixlConnector 和 NVIDIA Dynamo 共同说明，收益依赖长上下文、高并发、高 prefix reuse 和可重叠的 KV transfer。
- 小算力落地优先级应是：P0 可观测 + KV warm tier + prefix reuse；P1 MoE expert hotness/offload；P2 SSD/CXL/remote cold tier；P3 NPU-native direct storage。这个排序来自 vLLM-Ascend、MindIE、KTransformers、FineMoE、Tutti 和 ITME 的可用接口与风险边界。
- 推理仿真系统最缺的不是 FLOPs，而是真实 workload trace、KV/expert 热度、I/O 粒度、host overhead、互联带宽-延迟实测曲线、能耗遥测和可对齐 profiler timeline。ServeGen、BurstGPT、ProfInfer、Chakra/CCL-Bench、LLMServingSim 2.0 分别覆盖这些输入的一部分。
- Ascend + Kunpeng 已有可落地软件支点：vLLM-Ascend 的 KV Cache CPU Offload、UCM Store、Mooncake/PD 相关入口，以及 MindIE LLM 对 Continuous Batching、Page Attention、FlashDecoding 的官方说明。缺口是围绕 NPU↔CPU、NPU↔SSD、状态对象化和 simulator 的公开系统论文与 artifact。

## B. 研究问题地图

| 方向 | 核心瓶颈 | 代表论文/系统 | 主要技术路线 | 依赖硬件能力 | 对小算力部署的意义 | 对仿真系统的建模要求 |
|---|---|---|---|---|---|---|
| CPU 可卸载计算 | 显存不足、GPU batch 上不去、decode 阶段被 KV 容量卡死 | NEO, FlexInfer, llm.npu, ScoutAttention | CPU 参与 attention/KV 子路径、outlier、小矩阵、冷路径计算 | CPU SIMD/AMX/SVE、DDR、PCIe/UMA、异步 copy | 先把“放不下”变成“冷热分工” | CPU kernel latency、H2D/D2H、同步、overlap ratio |
| MoE expert 管理 | expert 大但稀疏激活，HBM 与 KV 争容量 | KTransformers, FineMoE, HybriMoE, DALI, FluxMoE, MoE-APEX | expert offload/paging/prefetch/cache、CPU fallback、adaptive precision | CPU/GPU/NPU 协同、专家热度预测、异步权重迁移 | 本地/小机跑大 MoE 的关键路线 | expert size、tier、hotness、next-use、miss penalty、prefetch lead time |
| KV / Prefix / State 分层内存 | KV 随上下文线性增长，restore/recompute 难权衡 | Mooncake, LMCache, Bidaw, CacheSlide, SolidAttention, Tutti | external KV layer、prefix cache、hierarchical cache、SSD/GDS、cache-aware scheduling | HBM/DDR/SSD/CXL/remote memory，direct path | 长上下文和 agent 会话通常先卡 KV 容量 | KV object size/lifetime/tier/hit/miss/restore/recompute |
| 权重 / latent / activation / 统一 state object | KV、expert、weight、latent 分散管理 | LMCache, FluxMoE, ITME, vLLM connectors, vLLM-Omni | 对象化、分层驻留、迁移/预取/驱逐统一接口 | runtime object ID、存储层、NPU/GPU memory API | 是下一阶段系统创新空白 | object lifecycle、QoS、ownership、pin/lookup/move/compress |
| Prefill/Decode 拆分与调度 | TTFT/TPOT 目标冲突，KV 传输代价大 | Mooncake, TensorRT-LLM DS, vLLM NixlConnector, Dynamo/NIXL, TaiChi | P/D disaggregation、KV exchange、overlap、phase-aware routing | RDMA/UCX/NIXL/NVLink/PCIe，多实例调度 | 小集群可按阶段利用不同资源 | request arrival、prefill/decode event、transfer overlap、queueing |
| 硬件互联与流水线 | 提升并发后瓶颈从算力迁移到 HBM/DDR/SSD/PCIe | Tutti, ITME, TensorRT-LLM, NIXL | direct storage、object I/O、CXL tier、通信-计算重叠 | I/O submit latency、bandwidth、IOPS、DMA path | 决定 SSD/CXL/remote tier 是否值得做 | per-path latency/bandwidth/IOPS、tiny I/O、CPU bounce buffer |
| 仿真、trace、profiling、benchmark | 缺真实 workload 和细粒度证据 | ServeGen, BurstGPT, ProfInfer, Chakra, CCL-Bench, LLMServingSim 2.0 | production trace、eBPF timeline、execution trace、profile-based simulator | profiler/counter/power telemetry | 没有证据层就无法规格反推 | workload distribution、timeline、counter、energy、validation error |
| Ascend/Kunpeng/NPU 迁移 | CUDA 生态文献多，Ascend 公开系统论文少 | vLLM-Ascend, MindIE LLM, Mooncake, LMCache-Ascend | KV CPU offload、UCM、PD、Page Attention、CB、FlashDecoding | NPU runtime hook、NPU↔CPU async copy、Kunpeng DDR/IO | 有工程支点，但缺系统化 artifact | NPU-specific path、CPU warm tier、event hooks、counter API |

## C. 会议查缺补漏表

说明：“已检查”表示本轮或已有本地快照中存在官方/一手来源；“未完成”表示没有完成逐页 proceedings 级复核，不能把“未发现”当成严格负结论。

| 会议 | 年份 | 官方来源核验 | 强相关论文/系统 | 中相关论文/系统 | 结论与人工复核点 | 来源 |
|---|---:|---|---|---|---|---|
| ICLR | 2025 | 部分 | 未发现 S/A 主线 | 长上下文/缓存方法若干 | 本题不是主战场，需按 OpenReview venue 继续人工筛 | https://openreview.net/group?id=ICLR.cc/2025/Conference |
| ICLR | 2026 | 部分 | 未发现 S/A 主线 | 若干高效推理方法 | 需复核 accepted list 与 withdrawn 状态 | https://openreview.net/group?id=ICLR.cc/2026/Conference |
| AAAI | 2025 | 部分 | 未发现 S/A 主线 | benchmark/profiler 线索 | proceedings 可继续关键词复核 | https://aaai.org/conference/aaai/aaai-25/ |
| AAAI | 2026 | 部分 | 未发现 S/A 主线 | 未定 | 需完整复核 proceedings | https://aaai.org/conference/aaai/aaai-26/ |
| ICML | 2025 | 部分 | 未发现 S/A 主线 | 高效推理相邻工作 | 系统类主线少于 MLSys/OSDI/FAST | https://openreview.net/group?id=ICML.cc/2025/Conference |
| ICML | 2026 | 未完成 | 未定 | 未定 | 会议时间与公开状态需复核 | https://icml.cc/ |
| NeurIPS | 2025 | 部分 | 未发现 S/A 主线 | KVCOMM 等相邻线索 | 需复核正式 accepted paper 与 workshop | https://neurips.cc/ |
| NeurIPS | 2026 | 未完整公开 | 未定 | 未定 | 截至 2026-07-01 不应作未发现强结论 | https://neurips.cc/ |
| MLSys | 2025 | 已检查 | NEO, FlexInfer, Context Parallelism | Marconi, LServe, QServe | 小算力/推理系统强相关密集 | https://dblp.org/db/conf/mlsys/mlsys2025 |
| MLSys | 2026 | 部分 | LLMServingSim 2.0, FlexiCache 线索 | OPKV, MoE tax 线索 | 需完整核验 session/proceedings | https://mlsys.org/virtual/2026 |
| ASPLOS | 2025 | 已检查 | llm.npu | LIA 等异构内存/硬件线索 | NPU/端侧异构强相关 | https://www.asplos-conference.org/asplos2025/ |
| ASPLOS | 2026 | 已检查 | MoE-APEX | shadowNPU, TurboInfer | edge/offload/MoE 延伸 | https://www.asplos-conference.org/asplos2026/program/index.html |
| OSDI | 2025 | 未完成 | 未定 | 未定 | 需按 technical sessions 复核 | https://www.usenix.org/conference/osdi25 |
| OSDI | 2026 | 已检查 | ECHO | 若干 serving/scheduling | KV offload 强相关 | https://www.usenix.org/conference/osdi26/technical-sessions |
| SOSP | 2025 | 已检查 | KTransformers, HeteroInfer | 其他 serving 系统 | CPU/GPU hybrid MoE 与端侧异构主会之一 | https://dl.acm.org/doi/10.1145/3731569.3764843 |
| SOSP | 2026 | 未完整公开 | 未定 | 未定 | 不作负结论 | https://sigops.org/s/conferences/sosp/ |
| NSDI | 2025 | 未完成 | 未定 | 未定 | 需官方技术会议页逐项复核 | https://www.usenix.org/conference/nsdi25 |
| NSDI | 2026 | 已检查 | ServeGen | JITServe 等线索 | workload/trace 对仿真器重要 | https://www.usenix.org/conference/nsdi26/presentation/xiang-servegen |
| USENIX ATC | 2025 | 已检查 | KVCache in the Wild | Toppings, Weaver, Resource Multiplexing | 实际部署与 KV behavior 价值高 | https://www.usenix.org/conference/atc25 |
| USENIX ATC | 2026 | 未完成 | 未定 | 未定 | 需复核 | https://www.usenix.org/conference/atc26 |
| FAST | 2025 | 已检查 | Mooncake, IMPRESS | storage/I/O 相关 | KV/state/storage 主 venue | https://www.usenix.org/conference/fast25/presentation/qin |
| FAST | 2026 | 已检查 | Bidaw, CacheSlide, SolidAttention | programmable page cache 等 | SSD/KV 层次缓存密集 | https://www.usenix.org/conference/fast26 |
| EuroSys | 2025 | 未完成 | 未定 | 未定 | 需复核 | https://2025.eurosys.org/ |
| EuroSys | 2026 | 已检查 | FineMoE | AdaGen, TokenFlow | MoE expert 管理强相关 | https://2026.eurosys.org/papers.html |
| SoCC | 2025 | 部分 | 未发现 S/A 主线 | Diffusion serving production | 相邻 serving 方向，非本题核心 | https://acmsocc.org/2025/ |
| SoCC | 2026 | 未完整公开 | 未定 | 未定 | 不作负结论 | https://acmsocc.org/ |
| Middleware | 2025 | 部分 | 未发现 S/A 主线 | middleware-style serving 线索 | 需复核 papers | https://middleware-conf.github.io/2025/ |
| Middleware | 2026 | 未完整公开 | 未定 | 未定 | 不作负结论 | https://middleware-conf.github.io/ |
| SC | 2025 | 部分 | 未发现 S/A 主线 | 建模/并行/能耗相邻 | 适合作硬件建模补充 | https://sc25.supercomputing.org/ |
| SC | 2026 | 未完整公开 | 未定 | 未定 | 不作负结论 | https://sc26.supercomputing.org/ |
| ISCA | 2025 | 部分 | LIA 等异构线索 | CXL/AMX/GPU 相邻 | 需复核 ACM/IEEE proceedings | https://iscaconf.org/isca2025/ |
| ISCA | 2026 | 未完成 | 未定 | 未定 | 不作负结论 | https://iscaconf.org/ |
| MICRO | 2025 | 未完成 | 未定 | 未定 | 需人工复核 | https://microarch.org/micro58/ |
| MICRO | 2026 | 未完整公开 | 未定 | 未定 | 不作负结论 | https://microarch.org/ |
| HPCA | 2025 | 未完成 | 未定 | 未定 | 需人工复核 | https://hpca-conf.org/2025/ |
| HPCA | 2026 | 未完成 | 未定 | 未定 | 需人工复核 | https://hpca-conf.org/ |
| SIGMOD/VLDB/CIDR | 2025-2026 | 未完成 | 未定 | agent/data-system/KV store 线索 | 数据系统方向可扩展查 | https://sigmod.org/ |
| MobiSys/SenSys/SEC/IoTDI | 2025-2026 | 未完成 | llm.npu/HeteroInfer 相邻 | 端侧 NPU/SoC | 移动/边缘场景应二次检索 | https://www.sigmobile.org/mobisys/ |

## D. 强相关论文与系统总表

| 方向 | 等级 | 名称 | 机构/来源 | 时间/状态 | 硬件与模型场景 | 核心问题 | 核心策略 | 主要收益/证据 | 小算力价值 | 仿真价值 | 链接 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CPU 异构协同 | S | NEO | Harvard/UC Berkeley/UChicago, MLSys | 2025 正式 | GPU + host CPU, online LLM | GPU memory 限制 batch/concurrency | attention/KV 部分 offload, asymmetric CPU-GPU pipelining, load-aware scheduling | offload KV/attention 到 CPU 以提高 batch 和吞吐 | CPU 是容量扩展工具，不是主算替代 | 需要 CPU/GPU phase-aware 代价模型 | https://arxiv.org/abs/2411.01142 |
| CPU 异构协同 | S | FlexInfer | Georgia Tech 等, MLSys/OpenReview | 2025 正式 | 单 GPU + CPU/memory limited | offload 数据搬运开销大 | runtime policy selection, tensor preservation, async prefetch | 资源受限环境最高约 12.5x | 单卡小内存路径直接相关 | 需要按 phase 和 tensor 类别建模 | https://openreview.net/forum?id=sFNRNTduKO |
| CPU/NPU 协同 | A | llm.npu | Peking Univ./BUAA, ASPLOS | 2025 正式 | edge NPU + CPU/GPU | 端侧 prefill 延迟高 | chunk-sharing, shadow outlier execution, OOO subgraph scheduling | 平均 prefill/能耗显著改善 | 说明 NPU 主算 + CPU/outlier 路径可行 | 需要 outlier/block affinity 模型 | https://arxiv.org/abs/2407.05858 |
| CPU/GPU/NPU 协同 | A | HeteroInfer | SOSP | 2025 正式 | mobile SoC NPU/GPU/CPU | heterogeneous SoC 如何分工 | NPU 主算，GPU/CPU 做补偿/控制 | 移动端异构推理证据 | CPU 更偏 control/special path | UMA/同步/调度模型 | https://arxiv.org/abs/2501.14794 |
| CPU/GPU 调度 | A | APEX | arXiv | 2025 预印本 | CPU/GPU online inference | CPU/GPU hybrid scheduling | profiling-informed scheduling | 预印本，需复核 artifact | 作为调度思想参考 | 可纳入 CPU offload policy | https://arxiv.org/abs/2506.03296 |
| MoE expert | S | KTransformers | Tsinghua/Approaching.AI, SOSP | 2025 正式 | x86 AMX CPU + GPU, large MoE | 本地大 MoE 放不下且 CPU 计算弱 | AMX expert kernels, async CPU-GPU scheduling, Expert Deferral | prefilling 4.62-19.74x, decoding 1.25-4.09x | CPU fallback expert 最强证据之一 | expert kernel + overlap 模型 | https://dl.acm.org/doi/10.1145/3731569.3764843 |
| MoE expert | S | FineMoE | Stevens/Rice/Waterloo/Rutgers, EuroSys | 2026 正式 | GPU + CPU memory, MoE | 粗粒度 offload latency-memory tradeoff 差 | fine-grained expert offloading, expert map, semantic hints | 6GB GPU memory 下 TPOT 降低 | hotness/prefetch 精度决定收益 | next-use/hit-rate/miss penalty | https://2026.eurosys.org/papers.html |
| MoE expert | A | HybriMoE | arXiv | 2025 预印本 | local CPU-GPU MoE | cache/prefetch 不稳定 | intra-layer scheduling, impact-driven prefetch, score cache | prefill/decode 均加速 | 小机器软件原型可借鉴 | layer-wise assignment 模型 | https://arxiv.org/abs/2501.04595 |
| MoE expert | A | DALI | arXiv | 2026 预印本 | local PC CPU+GPU, MoE | 静态 expert 分配、预取错误、cache 低效 | 0-1 assignment, residual-based prefetch, workload-aware replacement | 多模型多设置显著加速 | 在线 hotness 模块参考 | workload-aware expert object model | https://arxiv.org/abs/2602.03495 |
| MoE expert | S | FluxMoE | arXiv | 2026 预印本 | memory-intensive MoE serving | expert 常驻挤压 KV capacity | expert paging, transient expert object | 最高约 3x throughput | expert 直接状态对象化 | residency/tier/migration 模型 | https://arxiv.org/abs/2601.07343 |
| MoE expert | A | MoE-APEX | ASPLOS/ACM | 2026 正式 | edge architectures, MoE | expert offload 精度与带宽权衡 | adaptive precision expert offloading | ACM DOI 可核验 | edge MoE 降低迁移成本 | precision-tier tradeoff | https://dl.acm.org/doi/10.1145/3779212.3790187 |
| KV/state | S | Mooncake | Moonshot/Tsinghua, FAST | 2025 正式 | LLM chatbot serving, GPU cluster + CPU/DRAM/SSD/NIC | 长上下文 KV 与 P/D 调度 | KVCache-centric disaggregation, global cache, SLO scheduler | real traces 下有效请求容量提升 | KV 外部化工业基石 | global cache + scheduler model | https://www.usenix.org/conference/fast25/presentation/qin |
| KV/state | S | LMCache | Tensormesh/UChicago, arXiv/docs | 2025 技术报告/开源 | vLLM/SGLang, GPU/CPU/storage/network | KV 跨 query/engine 重用和迁移 | batched movement, connector, pin/lookup/cleanup/move/compress API | vLLM 结合最高 15x throughput | KV 一等对象层 | object API 直接可仿真 | https://arxiv.org/abs/2510.09665 |
| KV/state | A | KVCache in the Wild | USENIX ATC | 2025 正式 | cloud traces | 真实 KV reuse 与 eviction | workload-aware analysis | 真实 workload 证据 | 帮助判断 prefix/cache hit | reuse distribution | https://arxiv.org/abs/2503.01526 |
| KV/state | S | Bidaw | FAST | 2026 正式 | interactive LLM serving, storage-aware KV | KV caching 与计算/存储双向感知 | computation-storage aware scheduling | FAST 2026 官方页/PDF 可核验 | KV warm/cold tier 决策 | two-tier storage model | https://www.usenix.org/conference/fast26/presentation/hu-shipeng |
| KV/state | S | CacheSlide | FAST | 2026 正式 | multi-turn / agent prefix shift | 位置变化导致 KV 复用失败 | cross position-aware reuse | USENIX PDF 可核验 | agent 多轮场景重要 | prefix shift / reuse model | https://www.usenix.org/system/files/fast26-liu-yang.pdf |
| KV/state | A | SolidAttention | FAST | 2026 正式 | memory-constrained PCs, SSD | SSD latency 与 sparse attention | sparse attention + storage management co-design | USENIX PDF 可核验 | 小 PC 上 SSD 低延迟推理 | SSD block/granularity model | https://www.usenix.org/system/files/fast26-zheng.pdf |
| KV/state | S | ECHO | OSDI | 2026 正式 | native sparse attention LLM | sparse LLM KV offload restore | lossless prefetching | OSDI technical session 可核验 | 稀疏注意力仍需 KV 管理 | sparse KV restore model | https://www.usenix.org/conference/osdi26/presentation/liu-guangda |
| KV/state | S | Tutti | arXiv | 2026 预印本 | NVMe SSD-backed KV, vLLM | tiny I/O + CPU-centric GDS 控制路径 | GPU-native object store, GPU io_uring, slack-aware I/O | TTFT -78.3%, request rate 2x | SSD 冷层能否落地的关键论文 | tiny I/O/control-path/stall 模型 | https://arxiv.org/abs/2605.03375 |
| CXL/tier | A | ITME | arXiv | 2026 预印本 | disaggregated CXL-hybrid memory | TB-scale context/weight expansion | tiered memory expansion | vision/prototype 需复核 | CXL 更像温层/容量层 | CXL latency/bandwidth tier | https://arxiv.org/abs/2606.12556 |
| P/D scheduling | A | TensorRT-LLM Disaggregated Serving | NVIDIA docs | 2026 官方文档 | context/generation instance, multi-GPU | P/D KV transfer overhead | overlap KV transmission with other request compute | 官方文档可核验 | 工业 data plane 参考 | transfer overlap model | https://nvidia.github.io/TensorRT-LLM/blogs/tech_blog/blog5_Disaggregated_Serving_in_TensorRT-LLM.html |
| P/D transfer | A | vLLM NixlConnector | vLLM docs | 2026 官方文档 | disaggregated prefill | P/D KV cache transfer | async send/receive via NIXL | 官方文档可核验 | 小集群可复用 connector | connector latency/QoS model | https://docs.vllm.ai/en/latest/features/nixl_connector_usage/ |
| P/D transfer | A | NVIDIA Dynamo/NIXL | NVIDIA docs/GitHub | 2026 官方文档 | disaggregated serving, KV block manager | cross-pool KV movement | NIXL transport, CPU/GPU/file/object store backend | 官方文档可核验 | KV data plane 工业化 | backend transfer model | https://docs.nvidia.com/dynamo/dev/user-guides/disaggregated-serving |
| simulation | S | ServeGen | NSDI/USENIX | 2026 正式 | production LLM workloads | synthetic workload 不真实 | per-client workload characterization/generation | 避免 50% under-provisioning | 仿真 workload 输入基座 | arrival/prompt/output/reuse distribution | https://www.usenix.org/conference/nsdi26/presentation/xiang-servegen |
| simulation | S | ProfInfer | arXiv | 2026 预印本 | LLM engine profiling | 端到端 profiling 不可解释 | eBPF probes, timeline, operator graph, counters | 低开销 profiler | P0 可观测能力 | timeline validation | https://arxiv.org/abs/2601.20755 |
| simulation | A | BurstGPT | arXiv/dataset | 2024 背景基石 | real serving trace | bursty workload 缺失 | 5.29M request trace | 背景 trace | replay seed | trace replay | https://arxiv.org/abs/2401.17644 |
| simulation | A | Chakra / CCL-Bench | MLCommons / arXiv | 2026 | execution trace / benchmark package | trace 不可复用 | trace schema, workload card, launch scripts | 标准化证据 | 仿真器证据对象 | trace schema | https://arxiv.org/abs/2605.11333 |
| simulation | S | LLMServingSim 2.0 | KAIST, arXiv | 2026 预印本 | heterogeneous + disaggregated LLM serving | 现有仿真器不能联合建模 runtime/hardware | runtime loop, placement/offload/memory/power modeling | 平均误差 0.95% | 最接近“规格反推”路线 | system-level simulator blueprint | https://arxiv.org/abs/2602.23036 |
| Ascend/Kunpeng | S | vLLM-Ascend KV Cache CPU Offload | vLLM-Ascend docs | 2026 官方文档 | NPU memory limited | inactive KV blocks offload to CPU memory | async restore on prefix miss | 官方文档可核验 | Kunpeng warm tier P0 | NPU↔CPU restore model | https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html |
| Ascend/Kunpeng | S | vLLM-Ascend UCM Store | vLLM-Ascend docs | 2026 官方文档 | external KV capacity | offload KV cache to external storage | storage-backed prefix/cache capacity | 官方文档可核验 | external KV P0/P1 | storage tier model | https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html |
| Ascend/Kunpeng | A | MindIE LLM | Huawei Ascend docs | 2026 官方文档 | Ascend LLM inference | CB/PA/FlashDecoding serving primitives | Page Attention, KV Cache 管理, Continuous Batching | 官方文档可核验 | 昇腾基础 serving 能力 | NPU page/KV/block model | https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0001.html |

## E. 分方向详细分析

### 1. CPU 可卸载计算与异构协同

CPU 参与推理在 2025-2026 年重新变重要，根本原因是显存容量而不是 CPU 峰值 FLOPs。小机器上，很多请求不是因为 GPU 算力不够，而是因为 KV cache 或模型状态挤占 HBM，导致 batch/concurrency 上不去。NEO 的路线是把部分 attention compute 和 KV cache state 从 GPU 放到 host CPU，并用 asymmetric pipelining 与 load-aware scheduling 避免 CPU 成为串行临界路径。FlexInfer 则强调 CPU/memory-limited single GPU 下要动态选择执行策略，不是固定 offload。

llm.npu 和 HeteroInfer 把同一思路扩展到 NPU/SoC。它们的启发不是“CPU 也能当主算力”，而是 NPU/GPU 做规则高吞吐主路径，CPU/GPU 处理 outlier、block、shadow execution 或控制面。对于 Ascend + Kunpeng，这意味着 P0 不应从“CPU 跑大块 FFN”开始，而应从 metadata manager、KV warm tier、outlier/sparse path、prefetch planner 和 profiler host 开始。

适用边界：CPU 适合低频、可预测、可并行重叠、数据搬运小于计算收益的路径。不适合大块 dense FFN 主路径、单 token decode 临界路径上无法提前启动的重计算、以及 PCIe/DDR 已接近饱和的工作负载。

仿真变量：CPU kernel by shape/precision、DDR bandwidth、PCIe/NPU-copy latency、async overlap ratio、host scheduling overhead、CPU/NPU/GPU utilization、phase-specific stall。

### 2. MoE 专家权重卸载、预取、缓存与冷热判断

MoE 的系统矛盾比 dense LLM 更尖锐：expert 权重大，但每个 token 只激活少数 expert。KTransformers 证明在低并发本地场景中，CPU/GPU hybrid inference 是自然路线，前提是 CPU 侧有足够强的 expert kernel，并且调度能把 CPU/GPU 计算重叠起来。FineMoE、DALI、HybriMoE、FluxMoE 进一步把问题从“能否 offload”推进到“能否预测下一步要用哪个 expert”。

这里的关键不是把 expert 存到 CPU 或 SSD，而是建立 expert object：size、tier、hotness、next-use probability、prefetch lead time、CPU fallback latency、quantization/precision、eviction cost。FluxMoE 的 expert paging 和 MoE-APEX 的 adaptive precision 都说明 expert 的驻留状态可以被动态管理。

适用边界：expert hotness 稳定、top-k 稀疏性明显、prefetch window 足够、CPU fallback kernel 不弱时赚钱；gate pattern 随机、warm tier 带宽不足、错误预取频繁、decode miss 卡临界路径时不赚钱。

仿真变量：expert activation trace、router output predictability、expert migration bytes、CPU expert throughput、GPU resident set、cache replacement policy、miss penalty。

### 3. KV cache 容量管理、卸载、恢复与预取

KV cache 是长上下文、多轮对话和 agent workflow 的第一瓶颈。Mooncake 把 KVCache 放到 serving 架构中心，LMCache 把 KV 变成可跨 query/engine 共享的对象层，vLLM 和 vLLM-Ascend 则把 KV connector、CPU offload、UCM、NIXL 等接口工程化。

2026 年的新变化是 KV 管理开始进入 SSD/CXL/remote tier。Tutti 是关键反例和正例：如果 KV layout 仍然碎片化，SSD-backed KV 会被 tiny random I/O 和 CPU-centric control path 吃掉收益；如果用 GPU-native object store、GPU io_uring 和 slack-aware I/O scheduling，则 SSD 冷层才有实际可能。SolidAttention、CacheSlide、Bidaw、ECHO 分别从 SSD serving、prefix shift、compute-storage awareness 和 sparse attention KV restore 角度推进这一问题。

适用边界：prefix reuse 高、上下文长、KV 对象可批量恢复、传输可重叠时 offload 值得做；短上下文、低复用、碎片 I/O、高同步开销时 recompute 可能更稳。

仿真变量：KV bytes/token、block/page size、object span、tier、hit/miss、restore latency、recompute cost、prefix shift、SSD IOPS、CPU control overhead、NPU/GPU stall。

### 4. 权重、latent、activation 与统一 state object runtime

已有系统大多只解决单类状态：LMCache 管 KV，FineMoE/FluxMoE 管 expert，vLLM connector 管 KV transfer，ITME 讨论 CXL-hybrid memory 中的 weights/context。真正统一 KV、Expert、Weight、Prefix、Embedding、Latent、Activation 的 runtime 还没有形成。这正是小算力一体机的创新机会。

统一 state-object runtime 至少应具备：object ID、类型、所属 request/session/model、大小、精度、生命周期、热度、tier、placement、pin、lookup、prefetch、evict、compress、restore、recompute、QoS 和审计日志。对工程实现而言，这可以先在 simulator 中做，再向 runtime hook 映射。

适用边界：统一抽象不能掩盖对象语义差异。KV 是 request/session scoped；expert/weight 是 model scoped；latent/activation 可能是 pipeline scoped。调度器应统一成本模型，但保留不同一致性和生命周期规则。

### 5. 硬件流水线、互联带宽、并发与 P/D 拆分

Prefill 和 decode 的资源画像不同。Prefill 更像大批量矩阵/attention 计算；decode 更像高频小步、KV 访问和调度问题。Mooncake、TensorRT-LLM、vLLM NixlConnector、Dynamo/NIXL 都把 KV transfer 变成显式 data plane。TensorRT-LLM 官方文档特别强调用其他请求的计算来 overlap KV transmission，这说明 P/D 拆分的收益来自 pipeline，而不是拆分本身。

小算力部署要谨慎：1-4 卡单机或小集群如果没有足够 in-flight 请求、没有长上下文或高 prefix reuse，P/D 拆分的固定开销可能超过收益。反过来，agent/RAG/coding workflow 中系统 prompt、tool history、长上下文复用高，P/D + external KV store 就更可能赚钱。

仿真变量：arrival rate、concurrency、prefill length、decode length、KV transfer size、transfer backend、overlap ratio、queueing policy、TTFT/TPOT SLO、P95/P99。

### 6. 推理仿真、trace、profiling 与性能建模

仿真器必须从“平均 token cost”升级为“离散事件 + profile-based cost model + trace replay”。ServeGen 提供真实 workload 生成思路，BurstGPT 提供 bursty serving trace，ProfInfer 提供 eBPF/timeline/counter 关联，Chakra/CCL-Bench 提醒我们要保存 trace、workload card、launch scripts，而不是只保存 summary metrics。LLMServingSim 2.0 已经明确把 heterogeneous hardware、disaggregated serving、placement/offload/memory/power 放进统一 runtime loop，是本题最接近的系统雏形。

仿真器的关键输出不应只有 throughput/latency，还应包含瓶颈归因：HBM occupancy、DDR bandwidth、SSD IOPS、PCIe/NVLink/CXL utilization、KV restore stall、expert miss penalty、CPU/NPU/GPU utilization、energy per token。

### 7. Ascend NPU + Kunpeng CPU 可迁移路线

公开资料显示，Ascend 生态已有工程支点：vLLM-Ascend 官方文档有 KV Cache CPU Offload 和 UCM Store；Mooncake 文档提到 vLLM-Ascend 与 Mooncake Transfer Engine；MindIE LLM 官方文档说明其支持多并发调度、Continuous Batching、Page Attention 和 FlashDecoding。基于这些可核验信息，迁移路线应从软件可控且风险低的状态管理开始。

P0：KV CPU offload、prefix/APC、UCM/external KV、profiler/timeline、workload trace、simulator host。Kunpeng 角色是 metadata manager、KV warm tier、I/O aggregation、profiler/simulator host。  
P1：MoE expert warm tier、expert hotness prediction、weight prefetch、CPU fallback expert 原型。需要 router/expert manager hook 和 Kunpeng SIMD/SVE kernel 评测。  
P2：SSD-backed KV/state object cold tier。需要对象化 KV layout、批量 I/O、NPU↔CPU/NPU↔SSD 异步接口。  
P3：NPU-native direct storage / NPU-SSD direct path。当前公开 Ascend 资料还不足以证明已有 Tutti 等价能力，应作为论文机会和下一代接口诉求。

最大风险：NPU runtime hook、异步 copy、KV object API、counter/telemetry 暴露不足。如果这些接口不可用，很多设计会退化成 CPU 控制路径，导致 decode 抖动。

## F. 推理仿真系统蓝图

目标：构建一个可校准、可回放、可 what-if、可规格反推的离散事件仿真器。它不模拟每条指令，而模拟 request、phase、state object、transfer、scheduler、capacity 和 stall。

### 输入层

| 输入类 | 字段 |
|---|---|
| 模型结构 | layers, hidden size, heads, GQA/MQA, FFN size, precision, KV bytes/token, activation/workspace |
| MoE 参数 | expert count, top-k, shared expert, expert size, router overhead, expert activation trace |
| 状态对象 | KV/prefix/expert/weight/latent object size, owner, lifetime, hotness, tier, pin/evict/compress flags |
| 硬件实测 | NPU/GPU matmul by shape, CPU FFN/expert kernel, HBM/DDR bandwidth, SSD seq/random/IOPS, PCIe/NVLink/CXL latency/bandwidth |
| workload trace | arrival process, prompt/output length, session reuse, prefix reuse, tool idle time, agent DAG, burstiness |
| energy telemetry | CPU/NPU/GPU power, DDR/SSD power, phase-specific energy/token |

### 代价模型

- prefill cost model：按 prompt length、attention mode、parallelism、phase placement 估计。
- decode cost model：按 active batch、KV hit/miss、expert hit/miss、scheduler step 估计。
- CPU offload cost model：CPU compute + H2D/D2H + host orchestration + overlap。
- expert placement model：resident tier、next-use、prefetch window、fallback latency、precision。
- KV object model：object size、block layout、restore/recompute、prefix shift、compression。
- memory tier model：HBM、DDR、SSD、CXL、remote pool 的容量、带宽、延迟、并发。
- interconnect model：NPU/GPU↔CPU、NPU/GPU↔SSD、CPU↔SSD、NPU/GPU↔remote。
- SSD I/O model：object-aware bulk I/O、tiny random I/O、submission overhead、queue depth。
- scheduler/queueing model：continuous batching、P/D routing、priority、preemption、QoS。
- energy model：phase-aware energy/token 与 idle/tool-call window。

### 离散事件核心

request arrival -> admission -> prefix lookup -> prefill start/end -> KV object creation -> KV hit/miss -> KV restore/recompute -> expert routing -> expert hit/miss -> expert prefetch/fallback -> HBM eviction -> decode step -> batching update -> transfer overlap -> stall attribution -> completion -> object cleanup。

### 输出指标

throughput、TTFT、TPOT、P50/P95/P99 latency、goodput under SLO、HBM occupancy、DDR bandwidth、SSD throughput/IOPS、PCIe/NVLink/CXL utilization、KV restore stall、expert miss penalty、CPU/NPU/GPU utilization、energy/token、bottleneck attribution、硬件规格反推建议。

### 校验方法

1. microbenchmark calibration：校准单算子、单路径 copy、SSD I/O、CPU expert kernel。
2. profiler timeline validation：用 ProfInfer/eBPF/NPU profiler 对齐 phase timeline 和 host overhead。
3. trace replay validation：用 ServeGen/BurstGPT/本地业务 trace 对齐 TTFT、TPOT、P95/P99。
4. sensitivity analysis：改变 CPU 核数、DDR 带宽、SSD IOPS、HBM 容量、互联带宽，检查瓶颈迁移是否合理。
5. what-if hardware sizing：输出满足目标 workload/SLO 的 CPU、DDR、SSD、HBM、NPU/GPU 数量组合。

## G. 收益边界与反例

- CPU 执行 FFN/expert/attention 子路径赚钱条件：子路径稀疏或低频，CPU kernel 足够强，迁移 bytes 小，可提前启动并与 NPU/GPU 重叠。
- CPU 参与被反噬条件：大块 dense 计算、decode 临界路径同步、PCIe/DDR 饱和、CPU control overhead 频繁、batch 太小无法重叠。
- MoE expert offload 赚钱条件：expert hotness 稳定、top-k 稀疏、prefetch lead time 足够、warm tier 带宽够、fallback latency 可控。
- expert prefetch 失败条件：router pattern 随机、prompt 分布突变、prefetch window 短、错误预取挤占 HBM。
- KV offload 比 recompute 更差的条件：prefix reuse 低、restore latency 高、KV layout 碎、对象粒度过小、CPU 控制路径阻塞。
- SSD-backed KV 被反噬条件：tiny random I/O、CPU 每次 submit、缺 object coalescing、queue depth 不够、GDS 仍 CPU-centric。
- CXL/remote memory 位置：更适合 warm/capacity tier，不宜假设为 decode 热层；热层仍应留给 HBM/host DRAM 中可预测 working set。
- P/D 拆分不赚钱条件：短上下文、低并发、低复用、transfer overlap 做不起来、调度控制面过重。
- 提升并发后的瓶颈迁移：通常从 NPU/GPU compute -> HBM capacity -> DDR bandwidth -> SSD IOPS -> PCIe/CXL/RDMA -> scheduler/host overhead。

## H. Ascend + Kunpeng 迁移路线

| 机制 | 可用支点 | Kunpeng 角色 | 纯软件可做 | 需要 runtime hook | 需要硬件/接口 | 优先级 | 风险 |
|---|---|---|---|---|---|---|---|
| KV Cache CPU Offload | vLLM-Ascend 官方 guide | warm tier, restore buffer, metadata manager | 是 | per-block restore/lookup | 低开销 NPU↔CPU async copy | P0 | host overhead 导致 TPOT 抖动 |
| UCM / external KV | vLLM-Ascend UCM Store | I/O aggregation, object metadata | 是 | object ID/TTL/connector | storage/NPU copy API | P0 | object layout 与兼容性 |
| Continuous Batching / Page Attention | MindIE LLM docs | scheduler host | 是 | block table/KV manager | NPU page attention support | P0 | 和上层引擎重复调度 |
| P/D with Mooncake/NIXL | Mooncake/vLLM-Ascend/NIXL docs | router, buffer manager | 部分 | phase-aware scheduler | NPU↔NPU/NPU↔CPU transfer | P1 | 低并发不赚钱 |
| Expert warm tier | vLLM-Ascend expert parallel / weight prefetch 线索 | prefetch planner | 部分 | router/expert manager | async weight prefetch | P1 | 热度模型难迁移 |
| CPU fallback expert | KTransformers/DALI 思路 | expert compute | 部分 | expert tensor export | Kunpeng SIMD/SVE kernel | P1/P2 | CPU kernel 不够强 |
| SSD-backed KV/state | Tutti 思路，Ascend 未见等价公开系统 | control fallback, I/O batching | 很有限 | storage-aware KV manager | NPU-side async storage submission | P2/P3 | 当前公开生态缺口 |
| Profiler/simulator | ProfInfer/LLMServingSim 思路 | simulator host | 是 | event hooks/counters | 更丰富 NPU telemetry | P0 | trace schema 不统一 |

## I. 研究空白与创新机会

| 机会 | 问题定义 | 为什么未解决 | 技术路线 | 需要接口 | 评估指标 | 投稿方向 |
|---|---|---|---|---|---|---|
| 统一 state-object runtime | KV/expert/weight/latent 分散管理 | 现有系统各管一类对象 | object ID + tier + lifecycle + QoS | engine object API, memory hooks | hit rate, stall, HBM occupancy | OSDI/SOSP/EuroSys |
| NPU-SSD direct path | CPU 仍在 NPU↔SSD 控制路径 | Ascend 公开资料不足 | NPU-native object I/O + batched DMA | NPU storage submission, async callback | TTFT, SSD IOPS, stall | ASPLOS/FAST/OSDI |
| 小算力 serving simulator | 现有仿真器难直接规格反推 | workload、state、hardware 缺统一 | DES + profile cost + trace replay | profiler/counter schema | sizing error, P95 error | MLSys/NSDI/SIGMETRICS |
| 非 x86 CPU expert fallback | KTransformers 偏 x86 AMX | Kunpeng/SVE 公开证据少 | SVE expert kernel + hotness scheduler | expert tensor layout export | TPOT, CPU util, energy | ASPLOS/EuroSys |
| KV hotness + expert hotness 联合建模 | 两者共享 HBM 预算 | 论文多分开优化 | unified HBM budget allocator | KV/expert trace | goodput, miss penalty | OSDI/SOSP |
| KV restore vs recompute 自动决策 | offload 并不总赢 | 缺跨层成本模型 | online policy + predictor | restore/recompute cost hooks | TTFT/TPOT, accuracy | MLSys/FAST |
| Agent workflow idle-window offload | tool call 产生空闲窗口 | serving 系统仍按普通对话建模 | idle-window state migration | agent event trace | goodput, stall hidden | NSDI/SoCC |
| Ascend/Kunpeng 公开系统论文 | 工程支点有，公开 artifact 少 | CUDA 生态更成熟 | vLLM-Ascend + UCM + simulator artifact | NPU profiler, KV hooks | reproducibility, SLO | ASPLOS/MLSys |
| KV layout / object coalescing | tiny I/O 破坏 SSD tier | 传统 paged KV 颗粒太碎 | Tensor-stripe / object block layout | KV block remap API | IOPS, TTFT, stall | FAST/OSDI |
| Energy-aware 小算力推理 | 小机受功耗墙影响 | 现有能耗模型粗 | phase-aware energy scheduler | power telemetry | energy/token, SLO | MLSys/SC |

## J. 精读清单

### P0 必读：直接决定技术路线

- NEO：看 CPU offload 的 phase-aware pipeline 和 load-aware scheduling。https://arxiv.org/abs/2411.01142
- KTransformers：看 CPU expert kernel、Expert Deferral 和本地 MoE hybrid inference。https://dl.acm.org/doi/10.1145/3731569.3764843
- Mooncake：看 KVCache-centric serving、P/D 拆分和 global cache。https://www.usenix.org/conference/fast25/presentation/qin
- LMCache：看 KV 作为 first-class object layer 的 API。https://arxiv.org/abs/2510.09665
- Tutti：看 SSD-backed KV 失败边界和 GPU-centric object I/O。https://arxiv.org/abs/2605.03375
- ServeGen：看真实 workload characterization 如何变成生成器。https://www.usenix.org/conference/nsdi26/presentation/xiang-servegen
- LLMServingSim 2.0：看 heterogeneous/disaggregated simulator 的 runtime loop。https://arxiv.org/abs/2602.23036
- vLLM-Ascend KV CPU Offload / UCM：看 Ascend 上 P0 可落地点。https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html

### P1 应读：补齐机制理解

- FlexInfer：看单 GPU + CPU/memory limited 条件下的动态执行策略。https://openreview.net/forum?id=sFNRNTduKO
- llm.npu：看 NPU 主路径和 outlier/shadow execution。https://arxiv.org/abs/2407.05858
- FineMoE：看 fine-grained expert offload 和 expert map。https://2026.eurosys.org/papers.html
- DALI：看 residual-based prefetch 和 workload-aware cache replacement。https://arxiv.org/abs/2602.03495
- FluxMoE：看 expert paging 与 transient expert object。https://arxiv.org/abs/2601.07343
- ECHO / CacheSlide / SolidAttention：看 KV restore、prefix shift 与 SSD/sparse attention co-design。https://www.usenix.org/conference/osdi26/presentation/liu-guangda
- TensorRT-LLM Disaggregated Serving 与 vLLM NixlConnector：看工业 KV transfer data plane。https://nvidia.github.io/TensorRT-LLM/blogs/tech_blog/blog5_Disaggregated_Serving_in_TensorRT-LLM.html

### P2 背景：了解相邻方向

- BurstGPT：真实 bursty workload trace。https://arxiv.org/abs/2401.17644
- ProfInfer：eBPF profiler/timeline/counter。https://arxiv.org/abs/2601.20755
- Chakra / CCL-Bench：execution trace 与 benchmark evidence packaging。https://arxiv.org/abs/2605.11333
- ITME：CXL-hybrid memory 作为容量/温层的 vision。https://arxiv.org/abs/2606.12556
- MindIE LLM docs：Ascend serving 基础能力和术语。https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0001.html

## K. 参考文献与搜索日志

### 参考文献与一手来源

- NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference. arXiv / MLSys 2025. https://arxiv.org/abs/2411.01142
- FlexInfer: Flexible LLM Inference with CPU Computations. OpenReview / MLSys 2025. https://openreview.net/forum?id=sFNRNTduKO
- llm.npu: Fast On-device LLM Inference with NPUs. ASPLOS 2025 / arXiv. https://arxiv.org/abs/2407.05858
- KTransformers: Unleashing the Full Potential of CPU/GPU Hybrid Inference for MoE Models. SOSP 2025. https://dl.acm.org/doi/10.1145/3731569.3764843
- FineMoE: Taming Latency-Memory Trade-Off in MoE-Based LLM Serving via Fine-Grained Expert Offloading. EuroSys 2026. https://2026.eurosys.org/papers.html
- DALI: A Workload-Aware Offloading Framework for Efficient MoE Inference on Local PCs. arXiv 2026. https://arxiv.org/abs/2602.03495
- FluxMoE: arXiv 2026. https://arxiv.org/abs/2601.07343
- MoE-APEX: An Efficient MoE Inference System with Adaptive Precision Expert Offloading. ASPLOS 2026 / ACM. https://dl.acm.org/doi/10.1145/3779212.3790187
- Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving. FAST 2025. https://www.usenix.org/conference/fast25/presentation/qin
- LMCache: An Efficient KV Cache Layer for Enterprise-Scale LLM Inference. arXiv 2025. https://arxiv.org/abs/2510.09665
- KVCache in the Wild. USENIX ATC 2025 / arXiv. https://arxiv.org/abs/2503.01526
- Bidaw: Enhancing Key-Value Caching for Interactive LLM Serving via Bidirectional Computation-Storage Awareness. FAST 2026. https://www.usenix.org/conference/fast26/presentation/hu-shipeng
- CacheSlide: Unlocking Cross Position-Aware KV Cache Reuse for Accelerating LLM Serving. FAST 2026. https://www.usenix.org/system/files/fast26-liu-yang.pdf
- SolidAttention: Low-Latency SSD-based Serving on Memory-Constrained PCs. FAST 2026. https://www.usenix.org/system/files/fast26-zheng.pdf
- ECHO: Efficient KV Cache Offloading with Lossless Prefetching for Serving Native Sparse Attention LLMs. OSDI 2026. https://www.usenix.org/conference/osdi26/presentation/liu-guangda
- Tutti: Making SSD-Backed KV Cache Practical for Long-Context LLM Serving. arXiv 2026. https://arxiv.org/abs/2605.03375
- ITME: Inference Tiered Memory Expansion with Disaggregated CXL-Hybrid Memories. arXiv 2026. https://arxiv.org/abs/2606.12556
- TensorRT-LLM Disaggregated Serving. NVIDIA official docs. https://nvidia.github.io/TensorRT-LLM/blogs/tech_blog/blog5_Disaggregated_Serving_in_TensorRT-LLM.html
- vLLM NixlConnector Usage Guide. vLLM docs. https://docs.vllm.ai/en/latest/features/nixl_connector_usage/
- NVIDIA Dynamo Disaggregated Serving. NVIDIA docs. https://docs.nvidia.com/dynamo/dev/user-guides/disaggregated-serving
- vLLM-Ascend KV Cache CPU Offload Guide. https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html
- vLLM-Ascend UCM Store Deployment Guide. https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html
- MindIE LLM 开发指南. Huawei Ascend docs. https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0001.html
- MindIE forward_tensor API说明. Huawei Ascend docs. https://www.hiascend.com/document/detail/zh/mindie/100/mindiellm/llmdev/mindie_llm0180.html
- ServeGen: Workload Characterization and Generation of Large Language Model Serving in Production. NSDI 2026 / USENIX. https://www.usenix.org/conference/nsdi26/presentation/xiang-servegen
- ProfInfer. arXiv 2026. https://arxiv.org/abs/2601.20755
- BurstGPT. arXiv 2024. https://arxiv.org/abs/2401.17644
- Chakra. arXiv 2026. https://arxiv.org/abs/2605.11333
- LLMServingSim 2.0. arXiv 2026. https://arxiv.org/abs/2602.23036

### 搜索日志

使用过的核心查询包括：

- `NEO CPU-offloading LLM inference MLSys 2025`
- `FlexInfer Flexible LLM Inference with CPU Computations MLSys 2025 OpenReview`
- `KTransformers SOSP 2025 CPU GPU hybrid inference MoE`
- `Mooncake KVCache-centric Disaggregated Architecture FAST 2025`
- `FineMoE expert offloading EuroSys 2026`
- `DALI workload-aware offloading framework efficient MoE inference local PCs arXiv`
- `Tutti SSD-backed KV cache LLM arXiv GPU io_uring`
- `FAST 2026 Bidaw CacheSlide SolidAttention KV cache`
- `OSDI 2026 ECHO KV cache offloading sparse attention`
- `ASPLOS 2026 MoE-APEX adaptive precision expert offloading`
- `ServeGen NSDI 2026 LLM serving workload characterization`
- `vLLM Ascend KV Cache CPU Offload UCM Mooncake documentation`
- `vLLM KV connector OffloadingConnector NixlConnector documentation`
- `TensorRT-LLM disaggregated serving KV cache exchange NIXL documentation`
- `site:hiascend.com/document MindIE "Continuous Batching"`
- `site:hiascend.com/document MindIE "PagedAttention"`
- `site:hiascend.com/document MindIE "FlashDecoding"`

未发现或仍需人工复核：

- ICLR/ICML/NeurIPS/AAAI 2025-2026 尚未在本轮核验到同等强度的 S 级系统主线论文，但需要继续逐页复核 accepted list。
- SOSP 2026、NeurIPS 2026、SC 2026、部分 2026 venue 截至 2026-07-01 未完整公开或未完成逐页复核。
- MICRO/HPCA/ISCA/SC 的硬件侧论文可能对仿真器建模有价值，但本轮未完成全量筛选。
- 本地 `Tutti__arxiv-2602.04182.pdf` 缓存错误，不能作为 Tutti 证据；应重新下载 `https://arxiv.org/pdf/2605.03375`。

AI 辅助披露：本报告使用 AI 辅助检索、归纳和写作；关键结论尽量绑定一手来源，但未完成全会议逐页复核的部分已明确标注。
