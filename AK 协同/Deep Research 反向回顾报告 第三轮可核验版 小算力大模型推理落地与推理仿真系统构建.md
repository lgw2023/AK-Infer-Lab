# Deep Research 反向回顾报告 第三轮可核验版：小算力大模型推理落地与推理仿真系统构建

核验日期：2026-07-01  
项目语境：A+K / Ascend NPU + Kunpeng CPU 小算力一体机技术路线研究。刘力维（ACS Lab）为本项目语境联系人，本报告不重新指定任何组织 owner 或 lead。  
输入材料：两轮提示词、两轮 Deep Research 报告、既有可核验整合版、`AK 协同/references/` 本地 PDF 与网页快照、2026-07-01 增量检索日志。  
新增证据日志：`AK 协同/references/inference_sim_incremental_search_2026-07-01.json`。

## 核验口径与本轮修正

本轮不是从零泛化综述，而是在已有 128 份 PDF、92 个网页快照和两份 bibliography 的基础上做增量核验。第二轮提示词并非空文件，而是无 Markdown 标题的收敛版需求；因此本报告以第二轮的五大方向和 A-K 结构为主，吸收第一轮对统一 state object、会议查缺补漏和字段抽取的更细要求。

证据优先级为：官方 proceedings / 会议 technical sessions / ACM 或 USENIX 页面 / OpenReview / arXiv / 官方文档 / 官方 GitHub。二手博客只作为线索，不进入强结论证据链。所有 2026 年尚未完整公开的 venue 均标注为“尚未完整公开”或“需继续逐项复核”，不写成严格负结论。

本轮新增或修正如下：

- 补下载正确 Tutti PDF：`references/papers/Tutti__arxiv-2605.03375.pdf`。旧缓存 `Tutti__arxiv-2602.04182.pdf` 内容不符，不能作为 Tutti 证据。
- 补下载 LLMServingSim2.0 新版本线索：`references/papers/LLMServingSim-2.0__arxiv-2511.07229.pdf`。本地旧资料仍保留 `2602.23036` 版本线索，报告中按“版本线索待最终 canonical 确认”处理。
- 补抓 FAST 2026、NSDI 2026、vLLM-Ascend release/UCM/KV CPU offload/KV Pool、NVIDIA Dynamo KV offloading、Mooncake 官网、vLLM Mooncake Store 博客等一手网页快照。
- 官方核验确认：FAST 2026 technical sessions 明列 SolidAttention、CacheSlide、Bidaw 和 model loading PPC；NSDI 2026 technical sessions 明列 ServeGen；vLLM-Ascend 文档已经有 KV Cache CPU Offload、UCM Store、KV Pool with Mooncake 和 Mooncake SSD offload；NVIDIA Dynamo 文档已经把 KV Cache Offloading、KVBM、LMCache、FlexKV、CPU/disk tiers 和 NIXL 作为 vLLM backend 能力列出。

## A. 执行摘要

- 2025-2026 年最密集的研究线不是单个 kernel，而是推理 runtime 的状态管理：KV cache、prefix、MoE expert、weight、activation、latent 正在被对象化，进入热度预测、迁移、预取、驱逐、持久化和跨实例共享的系统层。
- CPU 参与推理的有效角色更窄但更清晰：host/scheduler、metadata manager、I/O aggregator、KV warm tier、expert warm tier、fallback expert、小矩阵/稀疏/异常路径、profiler/simulator host。CPU 直接接管主干 attention/FFN 通常不成立，除非可重叠、低频、稀疏或有 AMX/SVE 等明确算力支撑。
- MoE expert offload 与 KV cache offload 的问题正在收敛：两者都需要对象大小、热度、reuse distance、next-use probability、prefetch lead time、miss penalty、tier bandwidth、eviction cost 和 restore/recompute 策略。
- KV cache 已从“HBM 不够就 offload”转为“对象布局 + I/O 粒度 + 控制路径 + pipeline slack”的问题。Tutti 的增量核验证据表明，SSD-backed KV 的主要反噬来自 tiny random I/O、CPU-centric control path、DRAM-HBM copy 和同步开销，而不是 SSD 账面带宽不足。
- Prefill/Decode 或 E/P/D 拆分不是默认正收益。只有当长上下文、共享 prefix、高并发、可重叠 KV transfer 和合理 routing 同时成立时，Mooncake、vLLM NixlConnector、TensorRT-LLM、NVIDIA Dynamo 这一类 data plane 才能赚到收益。
- 推理仿真系统最缺的是 evidence layer：真实 workload trace、prefix/KV/expert 热度、operator timeline、host runtime overhead、PCIe/UB/RDMA/SSD/CXL 的带宽-延迟曲线、power telemetry 和可复现实验卡片。ServeGen、BurstGPT、ProfInfer、Chakra/CCL-Bench、LLMServingSim2.0 分别补了其中一部分。
- Ascend + Kunpeng 的可落地路线比上一轮更明确：vLLM-Ascend 的 CPU KV Cache Offload 与 UCM/KV Pool/Mooncake 已经提供 P0 工程支点；Kunpeng 更适合作为 CPU warm tier、metadata manager、I/O aggregation 和 simulator/profiler host，而不是泛化为主算设备。
- 小算力一体机优先级应是 P0 可观测与 KV warm tier，P1 prefix/UCM/Mooncake 与 expert hotness，P2 SSD/CXL/remote cold tier，P3 NPU-native direct storage 与 NPU-SSD direct path。
- 公开论文空白仍然集中在 Ascend/Kunpeng 公开系统 artifact、NPU-SSD direct path、统一 state-object runtime、CPU expert execution on non-x86、KV/expert 联合热度预测和小算力 serving simulator。
- 本报告的负结论只限“在已核验的一手来源中未发现强相关”，不等价于全网穷尽不存在。

## B. 研究问题地图

| 方向 | 核心瓶颈 | 代表论文/系统 | 主要方法 | 涉及硬件组件 | 解决类别 | 仿真建模要求 |
|---|---|---|---|---|---|---|
| CPU 可卸载计算 | HBM 小、decode 小 batch、冷路径低利用 | NEO, FlexInfer, llm.npu, KTransformers, HybridGen | CPU/NPU/GPU 异构放置、attention/KV/outlier/expert fallback、异步重叠 | CPU SIMD/AMX/SVE、DDR、PCIe/UB、NPU/GPU HBM | 放得下、跑得快 | CPU kernel latency、H2D/D2H、同步、overlap ratio、shape-specific throughput |
| MoE expert 管理 | 专家参数大但 token 激活稀疏，HBM 与 KV 争空间 | KTransformers, FineMoE, HybriMoE, DALI, FluxMoE, MoE-APEX | expert cache/offload/paging/prefetch、hotness、adaptive precision、CPU fallback | HBM、DDR、SSD、PCIe、CPU/GPU/NPU | 放得下、并发上得去 | expert size、top-k、routing distribution、miss penalty、prefetch accuracy |
| KV/Prefix/State 分层内存 | KV 随 context 和 concurrency 线性增长 | Mooncake, LMCache, Bidaw, CacheSlide, SolidAttention, Tutti, ECHO | prefix cache、external KV、tiering、SSD/GDS/GPU-native I/O、restore/recompute | HBM、DRAM、SSD/NVMe、CXL、remote store | 放得下、并发上得去 | KV bytes/token、hit/miss、reuse distance、restore latency、I/O粒度 |
| 统一 state object runtime | KV、expert、weight、latent 分散管理 | LMCache, FluxMoE, UCM, vLLM connectors, Tutti | object ID、lifecycle、pin/move/compress/evict、multi-tier placement | runtime metadata、storage backend、connector API | 能仿真预测、可扩展 | object lifecycle、ownership、QoS、TTL、placement policy |
| 硬件流水线与 P/D 拆分 | TTFT/TPOT 冲突，KV transfer 卡链路 | Mooncake, TensorRT-LLM DS, vLLM NixlConnector, NVIDIA Dynamo/NIXL | P/D、E/P/D、KV exchange、overlap、phase-aware routing | NVLink、PCIe、RDMA、NIXL、HCCL/HCCS/UB | 跑得快、并发上得去 | event loop、queueing、transfer overlap、routing policy |
| 推理仿真与 profiling | 平均 FLOPs 无法解释尾延迟和容量瓶颈 | ServeGen, ProfInfer, BurstGPT, Chakra, CCL-Bench, LLMServingSim2.0 | workload generation、trace replay、operator profiler、hardware profile | counters、power、timeline、microbench | 能仿真预测 | workload distribution、operator latency、memory/IO/power、validation error |
| Ascend/Kunpeng 迁移 | CUDA 生态证据多，Ascend 公开系统论文少 | vLLM-Ascend, MindIE, Mooncake, UCM, LMCache-Ascend | KV CPU offload、KV Pool、UCM、PD、Mooncake backend、NPU stream | Ascend NPU、Kunpeng CPU、CANN、HCCL、Fabric Mem、SSD | 放得下、并发上得去 | NPU-specific copy、event hooks、host overhead、CANN counters |

## C. 逐会议查缺补漏表

| 会议 | 年份 | 官方来源核验 | 强相关论文/系统 | 中相关论文/系统 | 结论与复核点 | 来源 |
|---|---:|---|---|---|---|---|
| ICLR | 2025 | 部分 | 在已查来源未发现 S/A 主线 | 长上下文/缓存算法线索 | 需 OpenReview 全量筛 | https://openreview.net/group?id=ICLR.cc/2025/Conference |
| ICLR | 2026 | 部分 | 在已查来源未发现 S/A 主线 | 高效推理相邻方法 | 需区分 accepted/submission/withdrawn | https://openreview.net/group?id=ICLR.cc/2026/Conference |
| AAAI | 2025 | 部分 | 在已查来源未发现 S/A 主线 | benchmark/profiler 线索 | 需 proceedings 关键词复核 | https://aaai.org/conference/aaai/aaai-25/ |
| AAAI | 2026 | 部分 | 在已查来源未发现 S/A 主线 | 高效推理相邻 | 需 proceedings 逐项复核 | https://aaai.org/conference/aaai/aaai-26/ |
| ICML | 2025 | 部分 | SpeCache 属 KV/prefix 相邻 | compression/cache 方法 | 系统主线弱于 MLSys/OSDI/FAST | https://openreview.net/group?id=ICML.cc/2025/Conference |
| ICML | 2026 | 尚未完整公开/未完成 | 不作负结论 | 不作负结论 | 截止 2026-07-01 需继续复核 | https://icml.cc/ |
| NeurIPS | 2025 | 部分 | 在已查来源未发现 S/A 主线 | KVCOMM 等相邻线索 | 需正式 accepted 与 workshop 分开 | https://neurips.cc/ |
| NeurIPS | 2026 | 尚未完整公开 | 不作负结论 | 不作负结论 | 不应写“未发现”强结论 | https://neurips.cc/ |
| MLSys | 2025 | 已检查 | NEO, FlexInfer, Context Parallelism | Marconi 等 | 小算力/推理系统强相关密集 | https://dblp.org/db/conf/mlsys/mlsys2025 |
| MLSys | 2026 | 部分 | LLMServingSim2.0 线索 | OPKV, MoE tax, FlexiCache 线索 | 需最终 proceedings 确认 canonical 版本 | https://mlsys.org/virtual/2026 |
| ASPLOS | 2025 | 已检查 | llm.npu | LIA 等 | NPU/端侧异构主线之一 | https://www.asplos-conference.org/asplos2025/ |
| ASPLOS | 2026 | 已检查 | MoE-APEX | shadowNPU, TurboInfer 线索 | TurboInfer 未找到同名正式论文，保留人工复核 | https://www.asplos-conference.org/asplos2026/program/index.html |
| OSDI | 2025 | 未完成 | 不作负结论 | serving/scheduling 线索 | 需 official sessions 逐项复核 | https://www.usenix.org/conference/osdi25 |
| OSDI | 2026 | 已检查 | ECHO | scheduling/serving 相邻 | KV offload 强相关 | https://www.usenix.org/conference/osdi26/technical-sessions |
| SOSP | 2025 | 已检查 | KTransformers, HeteroInfer | 其他 serving 系统 | CPU/GPU hybrid MoE 与端侧异构强相关 | https://dl.acm.org/doi/10.1145/3731569.3764843 |
| SOSP | 2026 | 尚未完整公开 | 不作负结论 | 不作负结论 | 等待完整公开 | https://sigops.org/s/conferences/sosp/ |
| NSDI | 2025 | 未完成 | 不作负结论 | routing/scheduling 相邻 | 需官方页逐项复核 | https://www.usenix.org/conference/nsdi25 |
| NSDI | 2026 | 已检查 | ServeGen | REAL 等 simulator 相邻 | workload/trace 对仿真器是核心输入 | https://www.usenix.org/conference/nsdi26/technical-sessions |
| USENIX ATC | 2025 | 已检查 | KVCache in the Wild | Toppings, Weaver, Resource Multiplexing | 真实部署与 KV behavior 价值高 | https://www.usenix.org/conference/atc25 |
| USENIX ATC | 2026 | 未完成 | 不作负结论 | 不作负结论 | 需复核 | https://www.usenix.org/conference/atc26 |
| FAST | 2025 | 已检查 | Mooncake, IMPRESS | storage/I/O 相邻 | KV/state/storage 主 venue | https://www.usenix.org/conference/fast25/presentation/qin |
| FAST | 2026 | 已检查 | Bidaw, CacheSlide, SolidAttention | PPC model loading | 官方 technical sessions 已明列 AI and LLMs I 论文 | https://www.usenix.org/conference/fast26/technical-sessions |
| EuroSys | 2025 | 未完成 | HCache/Cake 等相邻需核验 | serving/cache 相邻 | 需复核 accepted list | https://2025.eurosys.org/ |
| EuroSys | 2026 | 已检查 | FineMoE | AdaGen, TokenFlow | MoE expert 管理强相关 | https://2026.eurosys.org/papers.html |
| SoCC | 2025 | 部分 | 在已查来源未发现 S/A 主线 | Diffusion serving production | 相邻 serving，不是本题核心 | https://acmsocc.org/2025/ |
| SoCC | 2026 | 尚未完整公开 | 不作负结论 | 不作负结论 | 等待完整公开 | https://acmsocc.org/ |
| Middleware | 2025 | 部分 | 在已查来源未发现 S/A 主线 | middleware serving 线索 | 需 papers 复核 | https://middleware-conf.github.io/2025/ |
| Middleware | 2026 | 尚未完整公开 | 不作负结论 | 不作负结论 | 等待完整公开 | https://middleware-conf.github.io/ |
| SC | 2025 | 部分 | 在已查来源未发现 S/A 主线 | 并行/能耗/建模相邻 | 可补硬件建模 | https://sc25.supercomputing.org/ |
| SC | 2026 | 尚未完整公开 | 不作负结论 | 不作负结论 | 等待完整公开 | https://sc26.supercomputing.org/ |
| ISCA | 2025 | 部分 | LIA 异构线索 | CXL/AMX/GPU 相邻 | 需 ACM/IEEE proceedings 复核 | https://iscaconf.org/isca2025/ |
| ISCA | 2026 | 未完成 | 不作负结论 | 不作负结论 | 需复核 | https://iscaconf.org/ |
| MICRO | 2025 | 未完成 | 不作负结论 | 硬件/内存相邻 | 需逐项人工复核 | https://microarch.org/micro58/ |
| MICRO | 2026 | 尚未完整公开 | 不作负结论 | 不作负结论 | 等待完整公开 | https://microarch.org/ |
| HPCA | 2025 | 未完成 | 不作负结论 | CXL/PIM/accelerator 相邻 | 需逐项人工复核 | https://hpca-conf.org/2025/ |
| HPCA | 2026 | 未完成 | 不作负结论 | 不作负结论 | 需复核 | https://hpca-conf.org/ |
| SIGMOD/VLDB/CIDR | 2025-2026 | 未完成 | 不作负结论 | data system / KV store / trace 相邻 | 可作为 state object 数据面补充 | https://sigmod.org/ ; https://vldb.org/ ; https://www.cidrdb.org/ |
| MobiSys/SenSys/SEC/IoTDI | 2025-2026 | 部分 | llm.npu/HeteroInfer 相邻 | edge NPU/SoC/IoT serving | 端侧 NPU 需继续二次检索 | https://www.sigmobile.org/mobisys/ |

## D. 强相关论文与系统总表

| 方向 | 等级 | 名称 | 机构/来源 | 时间/状态 | 硬件/模型/工作负载 | 核心问题 | 核心策略 | 主要收益或证据 | 小算力价值 | 仿真价值 | 链接 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CPU 异构协同 | S | NEO | MLSys/arXiv | 2025 正式/预印本 | GPU + CPU online LLM | HBM 限制 batch/concurrency | CPU offload attention/KV 冷路径与异步 pipeline | 提升可服务 batch 和吞吐 | CPU 做容量扩展 | phase-aware offload cost | https://arxiv.org/abs/2411.01142 |
| CPU 异构协同 | S | FlexInfer | MLSys/OpenReview | 2025 正式 | 单 GPU + CPU | offload 策略不稳 | runtime policy、vTensor、async prefetch | 资源受限场景最高约 12.5x | 单卡小内存直接相关 | tensor/phase policy model | https://openreview.net/forum?id=sFNRNTduKO |
| CPU/NPU 协同 | A | llm.npu | ASPLOS/arXiv | 2025 正式 | edge NPU + CPU/GPU | 端侧 prefill 与 outlier block | chunk-sharing、shadow outlier、OOO subgraph | prefill/能耗改善 | NPU 主算 + CPU/特殊路径 | outlier/block affinity | https://arxiv.org/abs/2407.05858 |
| CPU/GPU/NPU | A | HeteroInfer/HeteroLLM | SOSP/arXiv | 2025 正式 | mobile SoC | SoC 异构推理分工 | NPU/GPU/CPU placement | 端侧异构证据 | control/special path | UMA/同步模型 | https://arxiv.org/abs/2501.14794 |
| MoE expert | S | KTransformers | SOSP/ACM | 2025 正式 | CPU AMX + GPU，大 MoE | 本地大 MoE 放不下 | AMX expert kernels、Expert Deferral、async scheduling | prefill 4.62-19.74x，decode 1.25-4.09x | CPU fallback expert 强证据 | expert kernel + overlap | https://dl.acm.org/doi/10.1145/3731569.3764843 |
| MoE expert | S | FineMoE | EuroSys | 2026 正式 | GPU + CPU memory, MoE | 粗粒度 expert offload 延迟大 | fine-grained expert map、semantic hints | 6GB GPU 下 TPOT 降低 | hotness/prefetch 原型 | next-use/miss model | https://2026.eurosys.org/papers.html |
| MoE expert | A | HybriMoE | arXiv | 2025 预印本 | local CPU-GPU MoE | cache/prefetch 不稳定 | intra-layer scheduling、score cache | 多场景加速 | 本地 PC 参考 | layer assignment model | https://arxiv.org/abs/2501.04595 |
| MoE expert | A | DALI | arXiv | 2026 预印本 | local PC CPU+GPU | 静态 expert 放置差 | 0-1 assignment、residual prefetch、replacement | workload-aware 加速 | 在线 hotness | workload-aware expert object | https://arxiv.org/abs/2602.03495 |
| MoE expert | S | FluxMoE | arXiv | 2026 预印本 | memory-intensive MoE | expert 挤占 KV | expert paging、transient expert object | throughput 提升线索 | expert 状态对象化 | residency/tier/migration | https://arxiv.org/abs/2601.07343 |
| MoE expert | A | MoE-APEX | ASPLOS/ACM | 2026 正式 | edge MoE | expert offload 精度和带宽 | adaptive precision expert offloading | ACM DOI 可核验 | edge MoE 降低迁移量 | precision-tier tradeoff | https://dl.acm.org/doi/10.1145/3779212.3790187 |
| KV/state | S | Mooncake | FAST/USENIX | 2025 正式 | Kimi/KVCache-centric serving | 长上下文 KV 与 P/D 调度 | KVCache-centric disaggregation、global cache、SLO scheduler | 真实服务架构证据 | KV 外部化基石 | global cache + scheduler | https://www.usenix.org/conference/fast25/presentation/qin |
| KV/state | S | LMCache | arXiv/docs | 2025 技术报告/开源 | vLLM/SGLang + multi-tier storage | KV 跨 query/engine 复用 | pin/lookup/move/compress、connector | vLLM 结合高吞吐线索 | KV 一等对象层 | object API | https://arxiv.org/abs/2510.09665 |
| KV/state | A | KVCache in the Wild | USENIX ATC/arXiv | 2025 正式 | cloud traces | 真实 KV reuse 分布未知 | workload characterization | 真实 workload 证据 | prefix/cache hit 判断 | reuse distribution | https://arxiv.org/abs/2503.01526 |
| KV/state | S | Bidaw | FAST/USENIX | 2026 正式 | interactive LLM, host memory+SSD | 两级存储加载拖慢响应 | compute-storage awareness、response-guided eviction | latency up to 3.58x, throughput up to 1.83x | two-tier KV 直接可用 | KV tier latency/hit | https://www.usenix.org/conference/fast26/technical-sessions |
| KV/state | S | CacheSlide | FAST/USENIX | 2026 正式 | agent workflow/prefix shift | 绝对位置变化导致复用失败 | relative-position-dependent caching、weighted correction | latency 3.11-4.3x reduction | agent 多轮场景关键 | prefix shift model | https://www.usenix.org/conference/fast26/technical-sessions |
| KV/state | A | SolidAttention | FAST/USENIX | 2026 正式 | memory-constrained PCs, SSD | sparse attention + SSD 管理 | coarse KV blocks、speculative prefetch、I/O orchestration | 128k context 下 up to 3.1x, KV footprint up to 98% lower | AIPC/小 PC | sparse KV/SSD model | https://www.usenix.org/conference/fast26/presentation/zheng |
| KV/state | S | ECHO | OSDI/USENIX | 2026 正式 | native sparse attention LLM | sparse LLM KV offload restore | lossless prefetch | OSDI 页面可核验 | 稀疏注意力仍需 KV 管理 | sparse restore model | https://www.usenix.org/conference/osdi26/presentation/liu-guangda |
| KV/state | S | Tutti | arXiv | 2026 预印本 | vLLM, H100, NVMe SSD, long-context | SSD-backed KV 被 tiny I/O 和 CPU path 反噬 | GPU-native KV object store、GPU io_uring、slack-aware I/O | vs GDS-enabled SSD LMCache: TTFT -78.3%, request rate 2x, cost -27% | SSD 冷层落地关键边界 | tiny I/O/control-path/stall | https://arxiv.org/abs/2605.03375 |
| CXL/tier | A | ITME | arXiv | 2026 预印本 | CXL-hybrid memory | TB-scale context/weight | tiered memory expansion | vision/prototype | CXL 更像温/容量层 | CXL latency/bandwidth | https://arxiv.org/abs/2606.12556 |
| P/D transfer | A | TensorRT-LLM Disaggregated Serving | NVIDIA docs | 2026 官方文档 | context/generation instance | P/D KV transfer overhead | overlap KV transmission with computation | 官方文档 | 工业 data plane 参考 | transfer overlap model | https://nvidia.github.io/TensorRT-LLM/blogs/tech_blog/blog5_Disaggregated_Serving_in_TensorRT-LLM.html |
| P/D transfer | A | vLLM NixlConnector | vLLM docs | 2026 官方文档 | disaggregated prefill | P/D KV cache transfer | async send/recv via NIXL | 官方文档 | 小集群 connector | connector latency/QoS | https://docs.vllm.ai/en/latest/features/nixl_connector_usage/ |
| P/D/KV | A | NVIDIA Dynamo KVBM/LMCache/FlexKV | NVIDIA docs | 2026 官方文档 | vLLM aggregated/disaggregated serving | KV capacity beyond GPU memory | KVBM CPU/disk tiers, LMCache, FlexKV, NIXL | 官方文档明列 CPU/disk offload | 工业化 KV data plane | backend transfer model | https://docs.nvidia.com/dynamo/backends/v-llm/kv-cache-offloading |
| simulation | S | ServeGen | NSDI/USENIX | 2026 正式 | production LLM workloads | synthetic workload 不真实 | per-client workload characterization/generation | 官方页说明开源 | 仿真 workload 输入 | arrival/prompt/output/reuse | https://www.usenix.org/conference/nsdi26/technical-sessions |
| simulation | S | LLMServingSim2.0 | arXiv | 2025/2026 版本线索 | RTX3090/TPU-v6e/vLLM/ShareGPT/MoE | 仿真器不能覆盖异构、MoE、prefix、P/D | trace-driven operator profiler、memory/power/system simulator | 新版本摘要称 GPU serving error 约 1.9% | 最接近规格反推雏形 | full event simulator | https://arxiv.org/abs/2511.07229 |
| simulation | S | ProfInfer | arXiv | 2026 预印本 | LLM engine profiling | 端到端 profiling 不可解释 | eBPF/timeline/counters | 低开销 profiler 线索 | P0 可观测 | timeline validation | https://arxiv.org/abs/2601.20755 |
| simulation | A | BurstGPT | arXiv | 2024 背景基石 | bursty LLM workload | 请求到达分布缺失 | serving trace | 负载生成基座 | 小集群压力测试 | arrival burst model | https://arxiv.org/abs/2401.17644 |
| Ascend/Kunpeng | S | vLLM-Ascend KV Cache CPU Offload | vLLM-Ascend docs | 2026 官方文档 | Ascend NPU + CPU memory | NPU memory 不足 | OffloadingConnector, NPUOffloadingSpec, D2H/H2D streams, LRU CPU pool | 官方指南 | P0 可落地 | NPU-CPU transfer model | https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html |
| Ascend/Kunpeng | S | vLLM-Ascend UCM Store | vLLM-Ascend docs | 2026 官方文档 | HBM->DRAM->storage backend | prefix cache 容量与持久化 | UCM external KV, NFS/3FS/storage, PD modes | 官方指南称 3-10x latency reduction 场景 | P0/P1 external KV | storage tier model | https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html |
| Ascend/Kunpeng | S | vLLM-Ascend KV Pool with Mooncake | vLLM-Ascend docs | 2026 官方文档 | Ascend A2/A3, Mooncake, SSD offload | KV pool 与 PD | MooncakeConnectorV1 + AscendStoreConnector, SSD offload | 官方配置路径 | P1/P2 KV pool | connector/fabric mem model | https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_pool.html |
| Ascend/Kunpeng | A | Mooncake Transfer Engine / vLLM Ascend | Mooncake docs | 2025 官方项目 | vLLM-Ascend/Mooncake | PD 与 KV connector | Mooncake Transfer Engine, KV Pool backend | 项目主页列出集成时间线 | P1 生态支点 | transfer backend model | https://kvcache-ai.github.io/Mooncake/ |

B 级线索不进入主表强结论，但应保留在后续精读候选：Oneiros/MIRAGE、vTensor、Cake/HCache、Strata、SwiftCache、TableCache、KVPR、CacheBlend、SGLang HiCache、Mooncake Store for vLLM blog、Dynamo third-party storage integrations。

## E. 分方向详细分析

### 1. CPU 可卸载计算与异构协同

业内关注的是 CPU 何时能参与推理而不拖慢关键路径。NEO、FlexInfer、llm.npu、HeteroInfer、KTransformers 给出的共同答案不是“CPU 替代 GPU/NPU”，而是把 CPU 放到冷路径、稀疏路径、fallback expert、metadata/control plane、I/O aggregation 和可重叠的数据搬运上。CPU 赚钱的前提是被 offload 的子图低频、可预测、可批处理或可以被主算 pipeline 隐藏；如果 CPU 参与导致频繁 D2H/H2D、同步栅栏、格式转换或 DDR 带宽竞争，则收益会被反噬。

对小算力一体机的直接建议是先做 CPU 侧状态管理和冷 KV/expert warm tier，再评估 AMX/SVE/向量化 expert kernel。对 Ascend + Kunpeng，Kunpeng 可以优先承担 metadata manager、prefetch planner、CPU KV warm tier、I/O aggregation 和 profiler/simulator host；是否做 FFN/expert fallback 需要实测 Kunpeng SIMD/SVE 的 shape-specific throughput。

仿真器必须把 CPU 建模为多个角色，而不是一个总 FLOPs 数：host overhead、scheduler delay、copy engine、DDR bandwidth、pinned memory、CPU kernel latency、NPU stream overlap、synchronization barrier 都要单独建模。

### 2. MoE 专家权重卸载、预取、缓存与冷热判断

MoE 的核心矛盾是 expert 参数大、激活稀疏、routing 有局部性但不稳定。KTransformers 证明 CPU/GPU hybrid MoE 在本地大模型上可行；FineMoE、DALI、HybriMoE、FluxMoE 则把 expert 从“权重文件”变成可缓存、可分页、可预取和可迁移的 runtime object。

已形成共识的是：热专家应常驻 HBM，温专家在 DRAM/CPU 或更近的 warm tier，冷专家可放 SSD/remote，但 miss penalty 必须被 prefetch window 或计算重叠覆盖。仍有争议的是 router/gate 是否足够可预测，错误预取是否会挤占 HBM，以及 CPU fallback expert 在非 x86 CPU 上是否有足够算力。

对小算力部署，P1 原型应先记录 expert routing trace、top-k 分布、per-layer expert hit/miss、load time 和 miss penalty，再做 expert cache。仿真器需要 expert object size、expert placement、routing distribution、prefetch lead time、eviction policy、CPU fallback latency、interconnect bytes 和 all-to-all communication。

### 3. KV Cache 容量管理、卸载、恢复、预取与分层内存

KV 是长上下文、多轮对话、agent workflow 和高并发时最先触顶的资源。Mooncake、LMCache、vLLM connectors 和 UCM 都把 KV 变成外部状态对象；FAST 2026 的 Bidaw、CacheSlide、SolidAttention 说明 KV 管理已经进入 storage-aware、position-aware、sparse-attention-aware 阶段。

Tutti 是本轮最重要的反例/正例。反例是：直接把 KV 放 SSD 不一定赚钱，fragmented GPU page layout 会导致 tiny random I/O，CPU-centric GDS/control path 会让 CPU 成为瓶颈，DRAM-HBM copy 和同步会制造 GPU stall。正例是：GPU-native object store、GPU io_uring 和 slack-aware I/O 让 SSD 冷层接近 DRAM-backed LMCache 性能，同时大幅扩展容量。

对小算力一体机，优先级应是 HBM 内 prefix/APC、CPU DRAM warm tier、UCM/Mooncake external KV，最后再上 SSD cold tier。仿真器需要 KV bytes/token、layer/block layout、prefix reuse probability、hit/miss、restore vs recompute、SSD queue depth、I/O size distribution、CPU bounce buffer、DMA path 和 stall attribution。

### 4. 权重、latent、activation 与统一 state object runtime

第一轮提示词提出的统一 state object runtime 是合理创新点。KV、expert、weight、latent、activation、adapter 的共同点是都有生命周期、大小、热度、位置、迁移代价、可压缩性和一致性需求。不同点在于访问粒度和正确性边界：KV 与 prefix 强依赖位置和 layer，expert 依赖 routing，weight 更适合静态加载或 lazy loading，latent/noise 可能来自多模态/视频生成 pipeline。

现有系统还没有给出统一对象层。LMCache 更偏 KV object，FluxMoE 更偏 expert object，UCM 偏外部 KV/prefix，Tutti 偏 GPU-native KV object store。下一步可做的创新是把 object schema、event hooks、placement policy 和 profiler trace 统一，为仿真器和 runtime 同时服务。

### 5. 硬件流水线、互联带宽、并发与 P/D 拆分

Prefill 是计算密集，decode 是内存/KV/调度密集。P/D 拆分的收益来自资源画像差异和 transfer overlap，而不是拆分本身。Mooncake、TensorRT-LLM、vLLM NixlConnector、NVIDIA Dynamo/NIXL 都把 KV transfer 显式化为 data plane，这说明小集群必须先把 transfer cost 量清楚。

低并发、短上下文、低 prefix reuse、网络慢、KV transfer 不可重叠、scheduler overhead 高时，P/D 拆分不赚钱。高并发、长上下文、共享 prefix、P/D 资源不对称且 KV transfer 可被其他请求计算隐藏时才赚钱。

仿真器需要 request arrival、prefill/decode event、queueing、KV transfer bytes、per-link bandwidth/latency、DMA setup cost、NIXL/RDMA path、HCCL/HCCS/UB path、pipeline bubbles 和 routing policy。

### 6. 推理仿真、trace、profiling 与性能建模

推理仿真不能只做 FLOPs roofline。ServeGen 说明 workload 生成要按真实 client 行为、模型类型、prompt/output、arrival 和 reuse 组成；ProfInfer 说明 profiler 要能把 eBPF/timeline/operator/counter 对齐；LLMServingSim2.0 把 heterogeneous hardware、MoE、prefix cache、P/D、operator-level profiler、memory/power/system simulator 放进统一 loop，是本题最接近的公开雏形。

对小算力规格反推，仿真器输出不应只给 throughput，还要给 TTFT、TPOT、P95/P99、max concurrency、HBM occupancy、DDR traffic、SSD IOPS、PCIe/UB/RDMA utilization、KV restore stall、expert miss penalty、CPU/NPU utilization、energy/token 和 bottleneck attribution。

### 7. Ascend NPU + Kunpeng CPU 可迁移路线

vLLM-Ascend 的最新文档把迁移路线从“概念可行”推进到“已有 P0/P1 工程支点”。KV Cache CPU Offload 指南明确 inactive KV 可从 NPU memory offload 到 CPU memory，使用 OffloadingConnector、NPUOffloadingSpec、独立 NPU stream 和 CPU LRU block pool。UCM 指南明确 HBM->DRAM->Storage Backend 的三层 external KV 设计，支持 prefix cache、sparse attention 和 PD disaggregation。KV Pool 指南明确 Mooncake 作为 backend，可在 Ascend 上做 PD、AscendStoreConnector、MooncakeConnectorV1 和 SSD offload。

迁移难点仍然存在：公开资料还不足以证明已有 NPU-native SSD direct path 等价于 Tutti 的 GPU-native control path；Mooncake SSD offload 当前仍需仔细处理 fabric memory、buffer、TTL、metadata 和 failure policy；Kunpeng CPU 的 expert fallback 需要单独 microbenchmark 证明。

## F. 推理仿真系统蓝图

### 输入层

| 输入 | 字段 |
|---|---|
| 模型结构 | layers, hidden size, FFN size, attention heads, GQA/MQA, KV size/token, precision, activation/workspace |
| MoE 参数 | expert count, top-k, expert size, routing trace, all-to-all bytes, expert hotness, expert placement |
| KV/prefix 参数 | block size, layer layout, prefix tree/radix tree, reuse probability, hit/miss, TTL, pin/evict policy |
| 硬件实测 | NPU/GPU matmul by shape, CPU matmul/FFN/expert, HBM/DDR bandwidth, SSD seq/random bandwidth and IOPS, PCIe/UB/NVLink/CXL/RDMA latency, DMA setup, host overhead |
| workload | prompt length, output length, batch, concurrency, arrival process, session reuse, agent/tool idle time, multimodal encode/prefill/decode phases |
| 能耗 | CPU package power, NPU/GPU power, DRAM/SSD power, energy/token, energy/task |

### 代价模型

- prefill model：attention/FFN/operator latency by shape，chunked prefill，context parallel。
- decode model：per-token matmul、KV read/write、batch evolution、iteration scheduling。
- CPU offload model：CPU compute、D2H/H2D、DDR、pinned memory、sync、overlap。
- expert placement model：hotness、prefetch accuracy、miss penalty、fallback compute、precision tier。
- KV cache object model：HBM/DRAM/SSD/CXL/remote tier、restore/recompute、compression、eviction、prefix shift。
- interconnect model：PCIe/UB/NVLink/RDMA/NIXL/HCCL path、latency、bandwidth、setup cost。
- storage model：I/O size distribution、queue depth、random/sequential mix、GDS/NPU direct/CPU bounce。
- scheduler/queueing model：request routing、continuous batching、P/D split、KV-aware routing、SLO。
- energy model：per-phase power curve、idle power、transfer energy、stall energy。

### 离散事件核心

事件序列包括 request arrival、routing、prefill enqueue/start/end、KV allocation、KV hit/miss、KV restore/recompute、expert routing、expert hit/miss、expert prefetch、HBM eviction、decode step、batch merge/split、P/D transfer、I/O submit/complete、stall attribution、completion、cache cleanup。事件日志必须能 replay，并能导出到报告和调参脚本。

### 输出指标

throughput、goodput、TTFT、TPOT/ITL/TBT、P50/P95/P99、max concurrency、HBM occupancy、DRAM traffic、SSD bandwidth/IOPS、PCIe/UB/NVLink/CXL/RDMA utilization、KV restore stall、expert miss penalty、CPU utilization、NPU/GPU utilization、queueing delay、pipeline bubbles、energy/token、energy/task、bottleneck attribution、simulation error。

### 校验方法

1. microbenchmark calibration：逐 shape 测 matmul、copy、DDR、SSD、NPU stream、host overhead。
2. operator trace alignment：用 profiler timeline 对齐 prefill/decode/operator boundaries。
3. end-to-end replay：使用 ServeGen/BurstGPT/本地 trace，校验 TTFT、TPOT、P95/P99。
4. per-stage error：分别报告 compute、transfer、queueing、I/O、cache hit/miss 的误差。
5. sensitivity analysis：扫 HBM、DDR、SSD、PCIe/UB、CPU cores、NPU cards、concurrency、context length。
6. what-if validation：小规模实机验证仿真器反推的 CPU/DDR/SSD/NPU 规格是否成立。

## G. 收益边界与反例

| 机制 | 赚钱条件 | 不赚钱/反噬条件 | 证据线索 |
|---|---|---|---|
| CPU gating/FFN/expert | 低频、稀疏、可批处理、AMX/SVE 强、可与 NPU/GPU 重叠 | 小矩阵频繁同步、PCIe/UB 往返、DDR 带宽不足、CPU kernel 弱 | NEO, KTransformers, llm.npu |
| expert offload | routing 有局部性、hotness 稳定、prefetch window 足、miss 可隐藏 | routing 随机、错误预取挤占 HBM、decode miss 在关键路径 | FineMoE, DALI, FluxMoE |
| KV CPU offload | prefix reuse 高、CPU DRAM 足、H2D/D2H 可异步、CPU pool 命中 | 每次都 miss、CPU 内存不足、同步阻塞、host OOM | vLLM-Ascend KV Cache CPU Offload |
| SSD-backed KV | 大容量冷层、高 hit、I/O 粗粒度、direct/object path、slack 可隐藏 | tiny random I/O、CPU-centric control path、DRAM-HBM copy、GPU stall | Tutti, SolidAttention, Bidaw |
| CXL/remote memory | 做温层/容量层、访问局部性强、延迟可被隐藏 | 当作热层、随机小粒度、网络/协议开销高 | ITME, CXL whitepaper |
| P/D 拆分 | 长上下文、高并发、P/D 资源画像差异大、KV transfer 可 overlap | 短上下文、低并发、transfer 大于计算、路由复杂度高 | Mooncake, TensorRT-LLM, Dynamo |
| 增加并发 | HBM/KV 尚有余量，batch 提高利用率 | HBM 触顶后转为 DDR/SSD/PCIe/调度瓶颈 | KVCache in the Wild, ServeGen |

## H. Ascend + Kunpeng 迁移路线

| 优先级 | 原型 | Kunpeng 角色 | 需要的软件接口 | 需要硬件/运行时 | 风险 |
|---|---|---|---|---|---|
| P0 | workload/profiler/simulator host | profiler host, trace collector | vLLM-Ascend event hooks, MSProbe/AISBench, JSON trace schema | NPU counters, CPU/DDR/SSD telemetry | trace schema 不统一 |
| P0 | KV Cache CPU Offload | CPU DRAM warm tier, LRU manager | OffloadingConnector, NPUOffloadingSpec, KV events | NPU D2H/H2D stream, pinned memory | host OOM, copy stall |
| P0 | Prefix/APC/UCM external KV | metadata manager, storage client | UCM connector, prefix cache API | local DRAM + NFS/3FS/storage | object consistency, TTL |
| P1 | Mooncake KV Pool / PD | I/O aggregation, Mooncake control | MooncakeConnectorV1, AscendStoreConnector, kv_load_failure_policy | HCCL/HCCS/UB/Fabric Mem, CANN | connection/memory overhead |
| P1 | MoE expert hotness trace | routing trace collector | EPLB/hotness metrics, expert placement hooks | CPU memory for warm experts | no public Kunpeng expert kernel evidence |
| P2 | SSD-backed KV/state cold tier | SSD I/O aggregation | Mooncake SSD offload, UCM storage backend | NVMe, fabric memory alignment | tiny I/O and CPU control path |
| P3 | NPU-native SSD/direct path | control-plane fallback only | new NPU storage submission API | NPU->SSD direct or NPU RDMA path | current public ecosystem gap |

推荐先做 P0：KV CPU offload + UCM/prefix cache + profiler/simulator。P1 再做 Mooncake PD/KV Pool 和 expert hotness。P2/P3 需要硬件接口或 CANN/MindIE/vLLM-Ascend 更深 hook，适合作为论文和下一代规格诉求。

## I. 研究空白与创新机会

| 机会 | 问题定义 | 为什么未解决 | 技术路线 | 系统接口 | 指标 | 会议方向 |
|---|---|---|---|---|---|---|
| 统一 state-object runtime | KV/expert/weight/latent 分散管理 | 现有系统只覆盖单类对象 | object schema + lifecycle + placement policy | vLLM/MindIE connector, storage API | hit rate, miss penalty, TTFT | OSDI/SOSP/MLSys |
| Ascend/Kunpeng serving simulator | 小算力规格反推缺公开工具 | CUDA simulator 多，Ascend 少 | trace-driven + NPU/CPU microbench | CANN counters, MSProbe, vLLM-Ascend hooks | simulation error, sizing accuracy | MLSys/ASPLOS |
| NPU-SSD direct KV path | SSD KV 仍易被 CPU path 反噬 | 公开 NPU direct storage 证据不足 | NPU-side async storage submission | CANN storage/DMA API | GPU/NPU stall, IOPS | FAST/OSDI |
| CPU expert execution on non-x86 | KTransformers 偏 x86 AMX | Kunpeng SVE 证据不足 | SVE expert kernel + routing trace | CPU kernel ABI, expert manager | TPOT, energy/token | ASPLOS/MLSys |
| KV/expert 联合热度 | KV 与 expert 同时争 HBM | 论文常分开优化 | joint hotness predictor | unified cache manager | HBM occupancy, miss penalty | EuroSys/OSDI |
| restore vs recompute 自动决策 | KV 加载不一定比重算快 | 缺 per-request cost model | online predictor + simulator feedback | profiler + scheduler hook | TTFT, cost, error | NSDI/MLSys |
| P/D/E/P/D 小集群 scheduler | 大集群方法不适合 1-4 卡 | transfer overhead 占比高 | phase-aware discrete event scheduler | NIXL/Mooncake/HCCL hooks | goodput, P95/P99 | SOSP/NSDI |
| 多模态 latent/noise cache 分层 | VLM/video 也有状态对象 | LLM KV 论文未覆盖 | latent object tiering | VLM runtime hooks | latency, memory, quality | MLSys/NeurIPS Systems |
| Energy-aware 小算力 serving | 小机受功耗墙约束 | 能耗模型粗 | phase-aware power model | power telemetry | tokens/J, tasks/J | SC/MLSys |
| 可复现实验证据包 | 论文结果难迁移 | trace/config/硬件缺失 | workload card + microbench card + replay | artifact schema | reproducibility score | MLSys Artifact |

## J. 精读清单

### P0 必读：直接决定技术路线

- vLLM-Ascend KV Cache CPU Offload Guide：看 Ascend 上最直接的 P0 KV warm tier 原型。https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html
- vLLM-Ascend UCM Store / KV Pool with Mooncake：看 external KV、PD、Mooncake、SSD offload 在 Ascend 上的实际接口。https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html
- Tutti：看 SSD-backed KV 的失败边界和 GPU/NPU-native object I/O 思路。https://arxiv.org/abs/2605.03375
- KTransformers：看 CPU/GPU hybrid MoE 和 CPU expert fallback 的系统设计。https://dl.acm.org/doi/10.1145/3731569.3764843
- ServeGen：看真实 workload characterization 如何转化成仿真器输入。https://www.usenix.org/conference/nsdi26/technical-sessions
- LLMServingSim2.0：看异构硬件、MoE、prefix cache、P/D 和 power/memory 的统一仿真 loop。https://arxiv.org/abs/2511.07229

### P1 应读：补齐机制理解

- Mooncake：KVCache-centric disaggregation 与 KV data plane。https://www.usenix.org/conference/fast25/presentation/qin
- LMCache：KV object API、跨 engine reuse 和 storage connector。https://arxiv.org/abs/2510.09665
- FineMoE / DALI / FluxMoE：expert offload、hotness、prefetch 和 transient expert object。https://2026.eurosys.org/papers.html
- Bidaw / CacheSlide / SolidAttention：FAST 2026 KV/storage/prefix/sparse 方向。https://www.usenix.org/conference/fast26/technical-sessions
- NVIDIA Dynamo KV Cache Offloading：工业化 KVBM、LMCache、FlexKV 与 NIXL backend。https://docs.nvidia.com/dynamo/backends/v-llm/kv-cache-offloading

### P2 背景：相邻方向

- BurstGPT：bursty workload trace。https://arxiv.org/abs/2401.17644
- ProfInfer：profile/timeline/counter 设计。https://arxiv.org/abs/2601.20755
- Chakra / CCL-Bench：execution trace 与 benchmark evidence packaging。https://arxiv.org/abs/2605.11333
- ITME：CXL-hybrid memory 作为温层/容量层的 vision。https://arxiv.org/abs/2606.12556
- MindIE LLM docs：Ascend serving 基础能力、Page Attention、Continuous Batching、FlashDecoding 等术语。https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0001.html

## K. 参考文献与搜索日志

### 参考文献与一手来源

- NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference. MLSys 2025 / arXiv. https://arxiv.org/abs/2411.01142
- FlexInfer: Flexible LLM Inference with CPU Computations. MLSys 2025 / OpenReview. https://openreview.net/forum?id=sFNRNTduKO
- llm.npu: Fast On-device LLM Inference with NPUs. ASPLOS 2025 / arXiv. https://arxiv.org/abs/2407.05858
- KTransformers: Unleashing the Full Potential of CPU/GPU Hybrid Inference for MoE Models. SOSP 2025 / ACM. https://dl.acm.org/doi/10.1145/3731569.3764843
- FineMoE. EuroSys 2026. https://2026.eurosys.org/papers.html
- DALI. arXiv 2026. https://arxiv.org/abs/2602.03495
- FluxMoE. arXiv 2026. https://arxiv.org/abs/2601.07343
- MoE-APEX. ASPLOS 2026 / ACM. https://dl.acm.org/doi/10.1145/3779212.3790187
- Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving. FAST 2025. https://www.usenix.org/conference/fast25/presentation/qin
- LMCache. arXiv 2025. https://arxiv.org/abs/2510.09665
- KVCache in the Wild. USENIX ATC 2025 / arXiv. https://arxiv.org/abs/2503.01526
- FAST 2026 Technical Sessions: Bidaw, CacheSlide, SolidAttention. https://www.usenix.org/conference/fast26/technical-sessions
- ECHO. OSDI 2026. https://www.usenix.org/conference/osdi26/presentation/liu-guangda
- Tutti: Making SSD-Backed KV Cache Practical for Long-Context LLM Serving. arXiv 2026. https://arxiv.org/abs/2605.03375
- TensorRT-LLM Disaggregated Serving. NVIDIA docs. https://nvidia.github.io/TensorRT-LLM/blogs/tech_blog/blog5_Disaggregated_Serving_in_TensorRT-LLM.html
- vLLM NixlConnector Usage Guide. https://docs.vllm.ai/en/latest/features/nixl_connector_usage/
- NVIDIA Dynamo KV Cache Offloading. https://docs.nvidia.com/dynamo/backends/v-llm/kv-cache-offloading
- NVIDIA Dynamo Introduction. https://docs.nvidia.com/dynamo/getting-started/introduction
- vLLM-Ascend Release Notes. https://docs.vllm.ai/projects/ascend/en/main/user_guide/release_notes.html
- vLLM-Ascend KV Cache CPU Offload Guide. https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html
- vLLM-Ascend UCM Store Deployment Guide. https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html
- vLLM-Ascend KV Cache Pool Guide. https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_pool.html
- Mooncake project site. https://kvcache-ai.github.io/Mooncake/
- ServeGen. NSDI 2026. https://www.usenix.org/conference/nsdi26/technical-sessions
- LLMServingSim2.0. arXiv version line. https://arxiv.org/abs/2511.07229
- ProfInfer. arXiv 2026. https://arxiv.org/abs/2601.20755
- BurstGPT. arXiv 2024. https://arxiv.org/abs/2401.17644
- Chakra / MLCommons trace. arXiv 2026. https://arxiv.org/abs/2605.11333

### 搜索日志

本轮使用的核心查询已记录在 `AK 协同/references/inference_sim_incremental_search_2026-07-01.json`，包括：

- `2026 LLM serving simulator hardware-aware performance model KV cache offloading MoE expert offloading`
- `Tutti Making SSD-Backed KV Cache Practical long-context LLM serving 2605.03375`
- `Ascend Kunpeng vLLM-Ascend KV cache CPU offload UCM Mooncake LLM inference`
- `FAST 2026 Bidaw CacheSlide SolidAttention official USENIX`
- `NSDI 2026 ServeGen official USENIX`
- `vLLM Ascend KV Cache CPU Offload UCM Store Mooncake official docs 2026`
- `NVIDIA Dynamo KV cache offloading NIXL official docs 2026`

本轮新增下载/快照：

- PDF：`Tutti__arxiv-2605.03375.pdf`、`LLMServingSim-2.0__arxiv-2511.07229.pdf`。
- 网页：`FAST-26-Technical-Sessions.html`、`NSDI-26-Technical-Sessions.html`、`vLLM-Ascend-release-notes-live.html`、`vLLM-Ascend-UCM-deployment-live.html`、`vLLM-Ascend-KV-pool-live.html`、`vLLM-Ascend-KV-CPU-offload-live.html`、`NVIDIA-Dynamo-KV-offloading-live.html`、`NVIDIA-Dynamo-introduction-live.html`、`Mooncake-home-live.html`、`vLLM-Mooncake-Store-blog-2026-05-06.html`、`Tutti-arxiv-html-live.html`、`LLMServingSim-2.0-arxiv-2511.07229-abs.html`。
- 失败路径：`https://arxiv.org/html/2511.07229` 返回 404，已改存 arXiv abs 页和 PDF。

仍需人工复核：

- ICLR/ICML/NeurIPS/AAAI 2025-2026 尚未完成全 accepted-list 筛查；本报告只说“已查来源未发现同等强度 S/A 主线”。
- MICRO/HPCA/ISCA/SC 的硬件侧论文可能影响 simulator microarchitecture model，本轮仍是部分覆盖。
- SOSP 2026、NeurIPS 2026、SC 2026 等截至 2026-07-01 不应作严格负结论。
- LLMServingSim2.0 的 `2511.07229` 与本地旧 `2602.23036` 版本线索需要等作者或 proceedings 明确 canonical 版本后再去重。

AI 辅助披露：本报告使用 AI 辅助检索、证据整理和写作；关键结论尽量绑定一手来源，未完成全量核验的部分已经显式标注。
