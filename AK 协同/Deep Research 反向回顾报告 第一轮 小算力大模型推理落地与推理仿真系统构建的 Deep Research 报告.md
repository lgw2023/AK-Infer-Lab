# 小算力大模型推理落地与推理仿真系统构建的 Deep Research 报告

## 执行摘要

过去一年里，这一方向最明显的收敛，不是“再做一个更快 kernel”，而是把**CPU、KV/Expert 状态、分层内存、阶段拆分、以及仿真/trace 观测**同时纳入一个系统问题：如何在显存很小、CPU/DDR/SSD 很便宜、互联并不豪华的小型设备上，让模型既能放得下，又能保持可接受的 TTFT、TPOT 与并发。NEO、FlexInfer、KTransformers、FineMoE、Tutti、ECHO、Mooncake、LMCache、ServeGen、ProfInfer 这几条线索，已经足以勾勒出 2025–2026 年的主干技术脉络。citeturn17search2turn25search2turn22search14turn21search1turn11search2turn11search3turn27search3turn27search6turn16search0turn29view9

第一条主线是 **CPU 从“host/控制器”回到计算路径**。NEO 和 FlexInfer 都不是简单“把东西丢到 CPU 内存”，而是按 prefill/decode 阶段差异，决定何时让 CPU 真正参与 attention 或相关子计算；KTransformers、DAOP、HybriMoE、DALI 则把 CPU 明确拉入 MoE 专家执行、预取与缓存决策。收益来自两点：一是释放 HBM/显存，使 batch/concurrency 올라가；二是让 GPU 留在更高算强/更高并行度的主路径，把低频、冷、稀疏或短矩阵子任务交给 CPU。与此同时，这些论文也共同承认：一旦 PCIe/DDR/同步开销压过被卸载计算本身，CPU 参与就会立刻反噬。citeturn30view0turn25search2turn30view3turn32view4turn32view5turn39search2

第二条主线是 **状态对象化**。LMCache 明确把 KV cache 从“引擎内部临时张量”提升为可持久化、可跨引擎共享、可 pin / lookup / cleanup / compress 的一等对象；vLLM 在 2025–2026 年文档里进一步把 automatic prefix caching、KV connector、offloading connector、NixlConnector、mooncake/lmcache connector 等抽象成显式接口；SGLang HiCache、Mooncake、UCM for vLLM-Ascend 也都把“状态在哪一层、如何迁移、何时恢复、如何持久化”变成了部署期可配置能力。citeturn27search6turn14search12turn19search0turn19search1turn19search2turn19search5turn12search0turn27search3turn13search0

第三条主线是 **KV cache 不再只看 HBM 和 DRAM**。FAST’26 的 Bidaw、CacheSlide、SolidAttention，OSDI’26 的 ECHO，加上 Tutti、ITME 这些预印本，都在讨论 KV 如何跨 HBM / DRAM / CXL / SSD / 远端层级流动。这里的关键结论非常一致：真正的瓶颈经常不是“SSD 顺序带宽不够”，而是**KV 的 layout 太碎，tiny I/O 太多，CPU 还在控制路径上**。Tutti 之所以重要，不是因为它证明了“SSD 一定快”，而是它把问题精确地落到了“GPU-native object + async GPU io_uring + slack-aware I/O scheduling”上，说明如果不改对象布局和 I/O control path，SSD-backed KV 很可能比重算还糟。citeturn12search6turn32view9turn30view6turn11search3turn32view7turn33view6

第四条主线是 **MoE 权重正快速从“常驻参数”变成“按热度流动的对象”**。KTransformers 通过 CPU/GPU hybrid inference 和 AMX-specialized kernels 证明，本地机器跑超大 MoE 并非只能“全上 GPU”；FineMoE、DALI、FluxMoE、MoE-APEX 则进一步说明，expert paging / prefetch / cache replacement / adaptive precision offloading 已经成为一个独立系统问题。这里最重要的工程判断是：对小机器而言，KV 和 expert 在竞争同一块 HBM，谁常驻、谁分页、谁短驻，直接决定 TTFT、TPOT 与最大并发。citeturn30view3turn32view6turn39search2turn39search3turn39search0

第五条主线是 **Prefill/Decode 拆分从“云上大集群技巧”下沉成单机/小集群部署技术**。Mooncake 是这条线的工业标志，TensorRT-LLM、vLLM、Dynamo/NIXL 则把 “disaggregated serving / KV cache exchange / connector” 工程化；TaiChi 这样的 2025 预印本甚至开始直接讨论“aggregation or disaggregation”的收益边界，给出按 TTFT/TPOT SLO 自适应切换的框架。对 1–4 卡小服务器、2–8 节点小集群来说，这意味着阶段拆分不再只是规模化问题，而是**如何把预填充、解码、KV 传输和状态驻留放到最便宜的资源组合上**。citeturn27search3turn27search1turn27search9turn19search5turn27search12turn26search3

第六条主线是 **仿真系统正在从“只给一个端到端吞吐数字”走向“trace + structure + microbenchmark + what-if”**。ServeGen 提供了生产 workload characterization 与生成；BurstGPT 提供真实轨迹；ProfInfer 提供 eBPF 级 timeline、DAG 与硬件行为关联；CCL-Bench 把 trace、workload card、launch scripts 打包成可复现实验；MLCommons Chakra 则正在把这一切标准化为 execution trace 生态；能耗方面，Characterizing LLM Inference Energy-Performance Tradeoffs 证明 workload heterogeneity 与 phase heterogeneity 会显著改变能效最优点。对“推理算力仿真系统”而言，这意味着输入不能只是一串 FLOPs，必须包含**shape、phase、KV 命中/恢复、expert 热度、I/O 颗粒度、host overhead 与能耗遥测**。citeturn16search0turn15search0turn29view9turn15search1turn15search11turn29view8

第七条主线是 **Ascend + Kunpeng 已经具备“局部移植”的软件支点，但还没有足够公开的系统论文来证明完整路线**。可用支点已经出现：vLLM-Ascend 的 KV cache CPU offload、UCM、PD-colocated with Mooncake、distributed expert parallelism、weight prefetch；Mooncake 文档明确支持 vLLM Ascend；MindIE-LLM 开源后也已具备 Continuous Batching、PagedAttention、FlashDecoding 等基础能力。真正缺的不是“有没有框架”，而是**围绕 NPU↔CPU、NPU↔SSD、状态对象化、direct path、以及收益预测模型的公开系统论文和 artifact**。citeturn14search0turn13search0turn14search16turn13search15turn14search1turn14search13turn14search10

第八条主线是 **研究空白非常明确**。公开文献里，真正把 KV / Expert / Weight / Latent 统一成一套 state-object runtime 的系统还没有形成；NPU-SSD direct storage for KV/state 也未见成熟公开论文；针对小算力单机/小集群、可直接反推 CPU 核数/DDR 带宽/SSD IOPS/HBM 容量的 serving simulator 依然缺位；视频生成中的 rolling KV / noise cache / latent state 分层回流，目前也还没有一篇公认的“完整系统论文”把对象化、tiering 与 serving pipeline 全部打通。citeturn27search6turn32view7turn33view6turn15search1turn15search11turn29view9

## 研究问题地图与会议查缺补漏

### 研究问题地图

| 方向 | 核心瓶颈 | 代表论文/系统 | 主要方法 | 主要硬件协同点 | 对小算力意味着什么 |
|---|---|---|---|---|---|
| CPU 可卸载计算 | 显存不够；GPU 利用率不高；阶段特性差异大 | NEO, FlexInfer, APEX, llm.npu, HeteroInfer | 阶段感知调度、异步 CPU-GPU/NPU 协同、outlier/短矩阵拆分、online estimator | GPU/NPU↔CPU，HBM↔DDR，host runtime | 让“放不下”问题先变成“能否把冷/小/短子路径扔给 CPU” citeturn17search2turn25search2turn32view2turn36view0turn18search0 |
| MoE 专家管理 | 专家权重大而稀疏激活；HBM 与 KV 争容量 | KTransformers, FineMoE, HybriMoE, DALI, FluxMoE, MoE-APEX | expert offload、prefetch、paging、cache replacement、CPU fallback、adaptive precision | GPU↔CPU，HBM↔DDR/SSD，CPU SIMD/AMX | 本地机器运行百亿/千亿级 MoE 的关键不是“全放下”，而是“热门专家常驻、冷专家低成本 miss” citeturn30view3turn32view6turn32view5turn39search2turn39search3turn39search0 |
| KV / Prefix 分层内存 | KV 体积持续增长；restore/recompute 取舍困难 | Mooncake, LMCache, HiCache, Tutti, ECHO, Bidaw, CacheSlide, ITME | prefix/KV 对象化、tiering、prefetch、eviction、external store、GPU-centric I/O | HBM↔DRAM↔SSD↔Remote/CXL | 并发与长上下文往往先死于 KV 容量，而非算力；KV 管理本身成为“主系统” citeturn27search3turn27search6turn12search0turn32view7turn11search3turn12search6turn32view9turn33view6 |
| 硬件流水与并发 | prefill/decode 资源形态不同；传输与计算难重叠 | Mooncake, TensorRT-LLM DS, vLLM KV connector/NIXL, TaiChi, Context Parallelism | PD 拆分、KV exchange、connector、通信-计算 overlap、相位感知调度 | GPU↔GPU、GPU↔CPU、GPU↔SSD、RDMA/UCX/NIXL | 小集群可通过阶段拆分换取更高 goodput，但低并发下反而可能亏损 citeturn27search3turn27search1turn27search9turn19search5turn26search3turn38search11 |
| 仿真与建模 | 缺真实工作负载、分层状态与 I/O 的可解释模型 | ServeGen, BurstGPT, ProfInfer, CCL-Bench, Chakra, Energy-Tradeoffs | 生产 trace、eBPF、execution trace schema、workload replay、energy model | CPU/GPU/NPU counters、SSD I/O、power telemetry | 没有 trace 和 calibrated model，很难反推出 CPU 核数、DDR 带宽、SSD IOPS 和 HBM 容量的真实需求 citeturn16search0turn15search0turn29view9turn15search1turn15search11turn29view8 |

### 逐会议查缺补漏表

下表只列出**本轮已完成官方页面或正式论文页核验**的会议；其余会议列入“待人工复核队列”。这样做是为了避免把二手列表误当成正式会议信息。citeturn20search0turn20search5turn20search10turn20search19turn16search9turn22search6turn16search4turn23search12turn23search7turn21search0turn39search4turn40search2turn40search8turn40search1turn40search3

| 会议 | 本轮结论 | 强相关论文 | 中相关论文 | 备注 |
|---|---|---|---|---|
| MLSys 2025 | 已核验，强相关较多 | NEO, FlexInfer, Marconi, Context Parallelism | - | 本轮最密集的一年之一。citeturn17search9turn25search4turn26search1turn38search7 |
| ASPLOS 2025 | 已核验，端侧/NPU 强 | llm.npu | - | 偏 on-device/NPU 路线。citeturn17search3turn22search16 |
| SOSP 2025 | 已核验，强相关明确 | KTransformers, HeteroInfer | - | CPU/GPU 混合 MoE 与移动 SoC 异构推理都落在这里。citeturn22search6turn18search2turn18search0 |
| USENIX ATC 2025 | 已核验，系统与工作负载价值高 | Toppings, Weaver, KVCache Cache in the Wild | Resource Multiplexing in Tuning and Serving LLMs | 偏“部署/Serving 实战”而非理论。citeturn23search12turn23search0turn23search1turn26search9 |
| FAST 2025 | 已核验，强相关明确 | Mooncake, IMPRESS | - | 强在 KV/state/storage 路线。citeturn27search3turn27search19turn29view4 |
| NSDI 2026 | 已核验，仿真/trace 强 | ServeGen | - | 更偏 workload characterization 与 benchmark generation。citeturn16search0turn29view7 |
| FAST 2026 | 已核验，KV 层最强 | SolidAttention, Bidaw, CacheSlide | - | 强相关论文集中在 KV reuse / two-tier cache / storage-awareness。citeturn23search7turn12search6turn12search1turn29view5turn32view9 |
| EuroSys 2026 | 已核验，MoE 强相关明确 | FineMoE | AdaGen, TokenFlow | FineMoE 是本轮 MoE 热点之一。citeturn21search0turn21search1turn32view6 |
| ASPLOS 2026 | 已核验，MoE/offloading 与端侧 NPU 有亮点 | MoE-APEX, shadowNPU | TurboInfer | 强相关主题继续向 edge / offload 收敛。citeturn39search4turn39search0turn18search5turn18search4 |
| OSDI 2026 | 已核验，KV offload 强相关明确 | ECHO | - | 稀疏注意力 + 无损预取是亮点。citeturn11search3turn23search6 |
| ICLR 2025 / 2026 | 已看官方 OpenReview 入口，未发现本轮主线的正式强相关会刊论文 | 未发现直接强相关论文 | 若干长上下文/缓存压缩预印本 | 该主题近两年明显更多出现在 MLSys/系统会。citeturn20search0turn20search8 |
| ICML 2025 | 已看 OpenReview 入口，未见与本轮最核心问题同量级的正式系统论文 | 未发现直接强相关论文 | 少量高效推理/长上下文工作 | 需人工继续翻 session。citeturn20search10turn20search14 |
| NeurIPS 2025 / 2026 | 已看官方 venue 页，未见本轮主线的已核验正式系统论文 | 未发现直接强相关论文 | 少量 serving/缓存预印本散落 | 需人工复核具体 accepted list。citeturn20search19turn20search15 |
| AAAI 2025 / 2026 | 官方 proceedings 已公开，但本轮未核验到强相关主干论文 | 未发现直接强相关论文 | 可能有 profiler / benchmark 边缘论文 | 建议人工继续搜。citeturn20search5turn20search9turn20search21 |
| ISCA 2025 | 官方 program 已上线；本轮未核验到直接对应五大方向的主干论文 | 未发现直接强相关论文 | 体系结构侧可迁移工作 | 需人工继续翻 accepted list。citeturn40search2turn40search6 |
| SoCC 2025 | 官方站已上线；本轮未核验到本主题主干论文 | 未发现直接强相关论文 | 可能有云端 serving/scheduling 中相关论文 | 需人工复核 papers 目录。citeturn40search8 |
| Middleware 2025 | 官方站已上线；本轮未核验到直接主干论文 | 未发现直接强相关论文 | 可能有 middleware-style serving 工作 | 需人工复核。citeturn40search1turn40search17 |
| SC25 | 官方 program 已上线；本轮未核验到直接主干论文 | 未发现直接强相关论文 | 有性能建模/系统软件环境可迁移工作 | 需人工复核 contributed papers。citeturn40search3turn40search7 |

**待人工复核队列**：OSDI 2025、NSDI 2025、USENIX ATC 2026、SoCC 2026、Middleware 2026、ISCA 2026、MICRO 2025/2026、HPCA 2025/2026、SC 2026、SIGMOD/VLDB/CIDR 2025–2026、MobiSys/SenSys/SEC/IoTDI 2025–2026；这些会议本轮没有全部完成官方目录级逐页核验，因此不在这里给出“未发现”的强结论。citeturn23search2turn16search4turn40search8turn40search1turn40search2turn40search3

## 强相关论文总表

下表优先汇总**最能支撑“小算力大模型推理 + 推理仿真系统”**的正式论文、正式 accepted 论文、预印本与工业文档。对未正式发表者，我明确标注状态，避免把 arXiv 当成已发表会议。citeturn17search2turn25search2turn22search14turn21search1turn11search2turn11search3turn16search0turn27search6

| 方向 | 名称 | 机构 | 来源/时间 | 状态 | 一句话定位 |
|---|---|---|---|---|---|
| CPU 可卸载计算 | NEO | Harvard / UC Berkeley / UChicago | MLSys 2025 | 正式发表 | 以在线场景为目标的 CPU-offloading 系统，用异步流水与负载感知调度把 CPU 真正拉入 attention 相关路径。citeturn17search2turn30view0 |
| CPU 可卸载计算 | FlexInfer | Georgia Tech 等 | MLSys 2025 | 正式发表 | 针对单卡、CPU/内存有限场景，按 prefill/decode 动态选择执行策略。citeturn25search2turn16search10 |
| CPU/NPU 协同 | llm.npu | Peking Univ. / BUAA | ASPLOS 2025 | 正式发表 | NPU 主算、CPU/GPU 处理 outlier/block，解决端侧 prefill 主导延迟。citeturn17search3turn36view0 |
| GPU/NPU 协同 | HeteroInfer | Shanghai Jiao Tong Univ. / collaborators | SOSP 2025 | 正式发表 | 在移动 SoC 上把 NPU 做主算、GPU 做补偿，CPU 做控制平面。citeturn18search0turn33view1 |
| CPU/GPU 调度 | APEX | preprint | arXiv 2025 | 预印本 | profiling-informed hybrid scheduling，强调在线推理下 CPU/GPU 并行调度。citeturn32view2 |
| MoE 专家管理 | KTransformers | Tsinghua / Approaching.AI | SOSP 2025 | 正式 accepted + 论文 PDF | 用 AMX-specialized CPU kernels + async CPU-GPU scheduling 跑大 MoE。citeturn22search6turn30view3 |
| MoE 专家管理 | FineMoE | Stevens / Rice / Waterloo / Rutgers | EuroSys 2026 | 正式发表 | 以 expert map 追踪迭代级专家行为，做细粒度 prefetch / offload / caching。citeturn21search1turn32view6 |
| MoE 专家管理 | HybriMoE | PKU | arXiv 2025 | 预印本 | CPU-GPU hybrid scheduling + score-based caching + impact-driven prefetch。citeturn32view5turn33view4 |
| MoE 专家管理 | DAOP | preprint | arXiv 2025 | 预印本 | 预测下一层激活并在 CPU 侧预计算/近似计算冷专家。citeturn32view4 |
| MoE 专家管理 | DALI | preprint | arXiv 2026 | 预印本 | 运行时 0-1 分配、残差驱动预取、workload-aware cache replacement。citeturn39search2turn39search6 |
| MoE 专家管理 | FluxMoE | CUHK / collaborators | arXiv 2026 | 预印本 | expert paging，把 expert 从“常驻”变成“流式、瞬时对象”。citeturn39search3turn39search7 |
| MoE 专家管理 | MoE-APEX | SJTU / CUHK 等 | ASPLOS 2026 | 正式发表 | 用 adaptive-precision expert offloading 进一步压缩专家迁移代价。citeturn39search0turn39search4 |
| KV / 状态管理 | Mooncake | Moonshot AI / Tsinghua | FAST 2025 / TOCS 2025 | 正式发表 | KVCache-centric disaggregated serving，把 CPU/DRAM/SSD 变成 KV pool。citeturn27search3turn27search19turn38search14 |
| KV / 状态管理 | LMCache | UChicago / community | tech report 2025 + docs | 技术报告/开源系统 | 把 KV cache 变成可跨 engine 共享、可观察、可压缩的独立层。citeturn27search6turn14search12 |
| KV / 状态管理 | Cache in the Wild | SJTU | USENIX ATC 2025 | 正式发表 | 基于真实云厂商轨迹研究 KV reuse 与 workload-aware eviction。citeturn26search2turn38search9 |
| KV / 状态管理 | Bidaw | Tsinghua / 中国电信 | FAST 2026 | 正式发表 | 双向 aware 的计算-存储协同 KV caching。citeturn12search6turn12search2 |
| KV / 状态管理 | CacheSlide | SJTU | FAST 2026 | 正式发表 | 位置感知 KV reuse，把 agent/multi-turn 的 prefix shift 转化为可复用对象。citeturn12search1turn32view9 |
| KV / 状态管理 | SolidAttention | Intel / collaborators | FAST 2026 | 正式发表 | 用 solid-state hierarchical KV 把超长上下文 KV footprint 压到极低。citeturn29view5turn30view6 |
| KV / 状态管理 | ECHO | SJTU / Huawei | OSDI 2026 | 正式发表 | 面向 native sparse attention 的 lossless prefetch + KV offloading。citeturn11search3 |
| KV / 状态管理 | Tutti | preprint | arXiv 2026 | 预印本 | GPU-centric object I/O，把 CPU 从 HBM↔SSD 关键控制路径移除。citeturn32view7turn34view3 |
| CXL / tiered memory | ITME | SK hynix America 等 | arXiv 2026 | 预印本/vision | 用 disaggregated CXL-hybrid memory 做 TB-scale context / weight 扩展。citeturn33view6 |
| 阶段拆分 | Context Parallelism | Meta / Google | MLSys 2025 | 正式发表 | 证明长上下文 prefill 的可扩展并行化边界。citeturn38search7turn38search11 |
| 阶段拆分 | TaiChi | CUHK / Huawei Cloud 等 | arXiv 2025 | 预印本 | 直接研究 aggregation vs disaggregation 的 SLO/ goodput 边界。citeturn26search3 |
| 工业框架 | vLLM APC / KV connectors / OffloadingConnector | vLLM | docs 2025–2026 | 官方文档 | 把 prefix/KV transfer/offload 变成引擎内显式接口。citeturn19search0turn19search1turn19search2turn19search5 |
| 工业框架 | TensorRT-LLM Disaggregated Serving | NVIDIA | docs 2026 | 官方文档 | 官方化的 PD/KV exchange / overlap 优化。citeturn27search1turn27search9 |
| 工业框架 | NVIDIA Dynamo / NIXL | NVIDIA | docs/repo 2026 | 官方文档/开源库 | 把 KV offload、KV transfer、memory/storage backends 做成可插拔 data plane。citeturn27search0turn27search12turn28view0 |
| Ascend 生态 | vLLM-Ascend UCM / CPU Offload / Mooncake | Huawei / vLLM-Ascend 社区 | docs 2025–2026 | 官方文档 | Ascend 上已经有 prefix/KV offload、UCM、PD-colocated 的可落地支点。citeturn13search0turn14search0turn14search16 |
| 仿真 / trace | ServeGen | PKU / Alibaba | NSDI 2026 | 正式发表 | 生产服务工作负载表征与生成。citeturn16search0turn29view7 |
| 仿真 / trace | BurstGPT | HKBU / Azure traces | ACM 2025 / arXiv | 正式发表 | 大规模真实 LLM serving traces。citeturn15search4turn15search8 |
| 仿真 / trace | ProfInfer | arXiv | 2026 | 预印本 | eBPF-based fine-grained profiler，支持 CPU/GPU/NPU/llama.cpp 路线。citeturn29view9turn30view7 |
| 仿真 / trace | CCL-Bench 1.0 | Cornell / collaborators | arXiv 2026 | 预印本 | 用 trace + workload card + launch scripts 取代只报 summary number。citeturn15search1turn15search9 |
| 仿真 / trace | MLCommons Chakra | MLCommons WG | arXiv 2026 + MLCommons project | 项目/预印本 | execution trace 标准化。citeturn15search11turn15search3turn15search7 |
| 能耗建模 | Characterizing LLM Inference Energy-Performance Tradeoffs | TU Wien / UvA | arXiv 2025 | 预印本 | phase-aware、workload-aware 的 GPU DVFS 能耗边界。citeturn15search2turn29view8 |

## 分方向详细分析

### CPU 可卸载计算与模型内协同计算

这一方向在 2025–2026 年突然变重要，根本原因不是“CPU 更快了”，而是**小算力场景里的 GPU/NPU 变成了最稀缺的高价值资源**。NEO 直接指出，在线推理里单纯依赖 GPU-only 常常被显存容量困住，批量上不去，导致 GPU 算力空转；它在 T4、A10G、H100 上分别拿到最高 7.5×、26%、14% 的吞吐提升，并保持相同延迟，说明 CPU 参与的首要收益其实是**扩大可用 batch / concurrency**，而不是替 GPU 做“更快的算”。citeturn30view0turn30view2

FlexInfer 的重要性在于，它把“是否让 CPU 参与”从静态策略变成了**phase-aware policy selection**。论文明确把 prefill 与 decode 分开，因为两阶段的算子形状、KV 成长方式与 PCIe 压力完全不同；其结果是，相比以 FlexGen 为代表的传统 offload 路线，在两种不同服务器配置上平均可把端到端延迟降 75% 与 76%。从方法论上看，这说明小机器上不该问“要不要 offload”，而该问“哪一阶段、哪一类张量、哪一种形状，在当前硬件/上下文/输出长度下值得 offload 或 CPU compute”。citeturn25search2turn31search12

端侧方向则更进一步。llm.npu 在 ASPLOS 2025 中做了三个层次的切分：chunk-level 处理 prefill 依赖、tensor-level 抽出 outlier 到 CPU/GPU 并行处理、block-level 按硬件亲和性把 Transformer blocks 乱序调度到 CPU/GPU/NPU。它报告最高 22.4× 的 prefill 提速、30.7× 的能耗节省，并在实际应用中达到最高 32.8× 端到端加速；更关键的是，它把收益来源讲得非常清楚：移动 NPU 对大块规则 matmul 很强，但对动态 shape、outlier、控制相关路径很弱，因此 CPU/GPU 不是替代品，而是**补洞器**。citeturn37view0turn36view0

HeteroInfer 则给出另一个端侧结论：在 Snapdragon 8 Gen 3 这类 SoC 上，CPU 最适合做 control plane 与 synchronization，NPU 负责大部分主算，GPU 负责补足 NPU 的下界与特殊 shape；作者甚至强调 CPU 并不适合承担主要计算，因为能效太差。它在移动场景下拿到 1.34×–6.02× 的端到端加速，并给出一个很有价值的硬件观察：尽管 SoC 有统一内存地址空间，但单个处理器依然无法吃满系统总带宽，因而 GPU-NPU 协同在某些阶段是真收益。这个观察对 Ascend + Kunpeng 也很重要：统一地址空间本身不等于自动高效，真正决定收益的是**shape 匹配、DMA 开销与 runtime 调度质量**。citeturn33view1turn34view7

APEX 则代表了 2025 年开始出现的一类“把 hybrid execution 当作调度问题”的预印本。它不是再发明一种新算子，而是用 profiling-informed scheduling 让 CPU-GPU 并行度最大化，在 A10 上据称可获得 11%–89% 的吞吐提升，并在长输出场景中优于已有 hybrid schedulers。尽管它仍是预印本，但它强化了一个关键认识：在小算力机器上，**CPU 参与是否赚钱，往往在 scheduler，而不单在 kernel**。citeturn32view2

从小算力部署视角看，这一方向已经形成两条清晰路线。第一条是 NEO/FlexInfer 路线：CPU 主要承担 memory-expansion 后引入的 attention/KV 相关计算与数据搬运；第二条是 llm.npu/HeteroInfer 路线：CPU 主要承担控制、同步、outlier、小块补偿计算，而 NPU/GPU 共同承担主图。共同点是都在避免“把整层 FFN 或大块 dense GEMM 直接挪给 CPU”。分歧点是：NEO/FlexInfer 更适合 PCIe 离散卡 + x86 服务器，llm.npu/HeteroInfer 更依赖统一内存/SoC 内部互联与端侧 NPU 编译器。citeturn30view0turn25search2turn36view0turn33view1

对 Ascend + Kunpeng 的迁移性，我判断为**中到高**。纯软件上最容易迁的是 phase-aware scheduling、prefix/KV 命中预测、CPU-side metadata / I/O aggregation、以及冷路径小算子卸载；较难的是 GPU/NPU 侧 outlier handling、异步细粒度 tensor split、以及高度依赖特定 NPU 图编译器的 block-level 乱序调度。需要的 hook 包括：引擎层暴露 per-stage shape、per-op latency、CPU offload callback、以及 NPU↔CPU 异步 copy 的 completion 事件。需要的硬件接口则包括更低开销的 NPU↔Host shared buffer / pinned memory / DMA 提交路径。citeturn14search0turn13search15turn14search10

### MoE 专家权重卸载、预取、缓存与冷热判断

这条线路是 2025–2026 年最适合“小机器落大模型”的方向之一。原因很简单：对大 MoE 来说，**大部分参数不是每个 token 都会用上**，但如果让专家全常驻 HBM，就会和 KV cache 抢最贵的容量；一旦驱逐专家，又会遭遇 page-in、PCIe 拖尾和 miss penalty。KTransformers、FineMoE、DALI、FluxMoE、MoE-APEX 其实都在解决同一个问题：如何把 expert 从“静态权重”变成“按热度流动的运行时对象”。citeturn30view3turn32view6turn39search2turn39search3turn39search0

KTransformers 的信号最强，因为它已经是 SOSP 2025 accepted work。其核心不只是“expert offload”，而是两个更重要的机制：一是用 **AMX-specialized CPU kernels** 把 CPU expert execution 做到真正可用；二是提出 **Expert Deferral**，刻意创造 CPU 与 GPU 之间的可重叠区间。论文报告对现有系统有 4.62–19.74× prefill 加速、1.25–4.09× decode 加速，Expert Deferral 还能再带来最高 1.45× 吞吐收益。这里非常关键的一点是：作者不是把 CPU 当作“慢 CPU fallback”，而是把 CPU 当作**异步专家处理器**。这对 Kunpeng 的启发极大，因为它意味着如果 Kunpeng 的向量/矩阵能力足够，CPU fallback expert 完全可能成为正式设计点，而不是 emergency path。citeturn30view3turn30view4

FineMoE 则把问题推进到了**专家热度建模**。它提出 expert map，记录 gate 输出的 iteration-level probability distribution，再结合输入语义 embedding 找历史近邻，用于指导 prefetch、cache、offload。相比已有方案，它在六张 RTX 3090 的实验平台上把推理延迟降低 47%，expert hit rate 提升 39%。这说明对 MoE 来说，决定成败的不只是“有没有 offload”，而是**你能不能比 LRU/静态策略更早、更准地知道下一个热专家是谁**。citeturn32view6turn33view5

HybriMoE 与 DALI 属于进一步工程化的两种代表。HybriMoE 在 ktransformers 之上加入 warmup-based performance sensing、score-based expert cache 与 impact-driven prefetch，平均 prefill 1.33×、decode 1.70× 提升，强调 CPU/GPU 负载平衡与 runtime adaptation。DALI 则明确把 expert 到 CPU/GPU 的分配建模成 0-1 integer optimization 问题，再用 Greedy Assignment 在线近似求解，同时用 residual-based prefetch 与 workload-aware cache replacement 去减少错误预取。二者共同说明，MoE offload 成败高度依赖**workload-aware expert hotness model**。citeturn32view5turn33view4turn39search2turn39search6

FluxMoE 把方向再推一步：它主张与其纠结哪些专家要“长期驻留”，不如直接把 expert residency 解耦，采用 **expert paging** 思路，把专家视为 transient streamed resources，按需 materialize、用后立即驱逐，把更多 HBM 留给 KV cache。它在 memory-intensive regime 下报告最高 3.0× 吞吐增益。这对小算力推理非常关键，因为在本地部署里，**吞吐和最大并发常常更受 KV 容量限制，而不是受专家常驻与否限制**。citeturn39search3turn39search7

MoE-APEX 则表明 2026 年开始，专家对象化不再只做 placement，还开始做 **precision-aware placement**。官方 program 已明确其题目为 “Adaptive Precision Expert Offloading”，这代表一个值得追踪的趋势：冷专家不一定只下沉到 DRAM/SSD，也可以在下沉时改变数值格式，进一步压低传输与容量成本。只是目前公开可访问的一手材料还不足以精确核验其全部 baseline 与硬件细节，因此本轮只把它列为强相关，但保留部分细节“需人工复核”。citeturn39search0turn39search4

对小算力机器，MoE 的工程结论可以非常直接地写成三句。第一，**热门专家应当像 KV 热块一样管理**，而不是像静态权重一样管理。第二，**prefill 与 decode 的专家策略不应相同**：prefill 的激活面更宽、可预取窗口更大；decode 的专家 miss penalty 对单 token 延迟更敏感。第三，**CPU fallback expert 是否值得做，取决于 CPU SIMD/AMX/SVE 与 DDR 带宽**；如果 CPU 只能做标量或低带宽访问，那么“在 CPU 上算专家”往往不如“预取到加速器后算”。KTransformers 之所以成功，和其 AMX-specialized kernel 是绑定的。citeturn30view3turn32view6turn32view5

### KV Cache 容量管理、卸载、恢复、预取与分层内存

这一方向的核心变化，是 KV 不再被当作引擎私有缓存，而被当作系统级可编排状态。LMCache 的表述最明确：它把 KV cache 变成可持久化、可跨引擎重用、可观测、可变换的“AI-native knowledge”；Mooncake 则在生产系统里把 KV 直接当作调度中心；vLLM 进一步将 APC、KVTransferConfig、OffloadingConnector、NixlConnector 做成显式接口。换句话说，2025–2026 的主流思想已经不是“KV 是 attention 的副产物”，而是“KV 是 serving system 的主要资产之一”。citeturn14search12turn27search6turn27search3turn19search0turn19search3turn19search5

从正式论文看，Mooncake 仍是工业级主轴。它把 prefill 与 decode 拆开，并利用 GPU 集群中低利用率的 CPU、DRAM、SSD 资源构建 disaggregated KV cache；在 FAST’25 与后续 TOCS 版本中，作者反复强调其核心是 KVCache-centric global cache 与面向 SLO 的 scheduler，而不是单一层级的缓存实现。它在真实工作负载下的有效请求容量提升达到 59%–498%，在 Kimi 生产场景里能处理更多请求。虽然 Mooncake 的原始论文早于 2025，但它在 2025 年的正式发表与后续工程集成，仍然是本轮不能绕开的基石。citeturn38search14turn38search2turn38search6

LMCache 的价值则在于**接口层抽象**。技术报告把其贡献概括为三个层次：高效 KV movement、connector abstraction、以及 first-class control API。和 Mooncake 相比，LMCache 更像“把 KV 变成独立基础设施层”的尝试：它既支持跨 query 的 cache offloading，也支持 prefill-decode disaggregation 下的跨 engine transfer；控制 API 里甚至出现了 pinning、lookup、cleanup、movement、compression 这些明显带有“对象管理”含义的操作。对构建仿真系统也很重要，因为一旦 KV 变成对象，就能对其 size、lifetime、movement 单独建模。citeturn27search6turn27search2

2026 年 FAST/OSDI 的一组论文把“分层 KV”做得更细。Bidaw 强调 compute engine 与 two-tier storage 的双向感知，核心不在替换存储介质，而在让 scheduler 知道 KV 所在层与 load latency；CacheSlide 处理的是 multi-turn / agent 场景中前缀位置滑移导致的 cache miss，把原本不能复用的位置错位 KV 重新变成可复用对象，并在多个 LLM 和 agent benchmark 上拿到 3.11–4.3× 的延迟下降；ECHO 面向 native sparse attention LLM，把 offload 与 lossless prefetch 结合，说明“稀疏模型”并不天然绕开 KV 问题，反而更依赖正确的恢复策略。citeturn12search6turn32view9turn11search3

SolidAttention 代表另一条路线：不是把更多 KV 外移，而是让 KV footprint 本身收缩。它在 AIPC prototype 上对 128K context 实现最高 3.1× 性能提升，并把 KV 内存压到最高 98% 的削减；在 SYCL backend 上还能相对 Offload+Sparse 获得 1.7× throughput gain。严格说，它不是传统意义上的“offload 系统”，但它和层次化内存管理直接相关，因为一旦热层 KV 足够小，整个分层系统的 restore/evict 频率都会改变。对小机器而言，这种“先减少状态体积，再做分层”的路线经常比盲目加 SSD tier 更划算。citeturn30view6turn30view5

最值得高度关注的是 Tutti 与 ITME 这两个 2026 预印本。Tutti 直接指出，现有 SSD-backed KV 的主要问题是 fragmented GPU memory layout 导致大量 tiny random I/O，哪怕用了 GDS，CPU 仍在每次 I/O 的控制路径上，最终出现 70%–80% 的 GPU stall；它通过 GPU-native object abstraction、GPU io_uring 和 slack-aware I/O scheduling，把 TTFT 相对 GDS-enabled LMCache 降低 78.3%，请求率提高 2×，成本下降 27%。ITME 则把问题推到 CXL-hybrid-memory：它认为 activations 和 working KV 更适合留在 GPU/host 的热层，而 model weights 与 long-context KV 更适合进入远端 TB-scale 扩容层，并用硬件预取 + DMA pipeline 去掩蔽 SSD、网络和 host memory 级联延迟。二者共同表达的结论非常鲜明：**分层内存设计的关键不是“多一层”，而是“每一层承载哪类对象、对象是否可预测、数据路径是否能 pipeline”**。citeturn32view7turn34view3turn33view6

从数据搬运路径来看，这一方向已经形成几个工程共识。第一，**HBM/GDDR/Bailu 热层优先留给 working set**：当前 step 的 active KV、decode 热状态、短时间必须命中的专家或激活。第二，CPU DRAM 更适合作为 warm tier，承接 prefix cache、近似热点专家、以及短期可恢复状态。第三，CXL memory 目前更像容量扩展/温层，不像真正热层；ITME 自己也把 working KV 放在 GPU/host，而把 long-context KV 和 weights 放远端扩容层。第四，SSD/NVMe 只有在对象布局与批量 I/O 设计正确时才适合作冷层，否则 tiny I/O 和 CPU bounce buffer 会吞掉理论带宽。citeturn14search14turn19search2turn33view6turn32view7

### 硬件流水线、互联带宽、并发提升与部署策略

P/D 拆分之所以从云端问题下沉到本地小集群，有两个现实动因。其一，长上下文与多轮会话让 prefill 与 decode 的资源形态差异变得过大；其二，开源引擎已经开始显式地把 KV transfer 做成 connector/data plane。Mooncake 是工业原型，TensorRT-LLM 的 “Disaggregated Serving in TensorRT LLM” 和 “KV Cache Exchange” 把这件事纳入官方功能；vLLM 则通过 KVTransferConfig、NixlConnector、OffloadingConnector 提供可组合的数据面。citeturn27search3turn27search1turn27search9turn19search3turn19search5turn19search2

Context Parallelism 虽然不是“小机型部署”论文，但它说明了长上下文 prefill 的一个重要事实：随着 context 越来越长，attention FLOPs、KV footprint 与通信成本同时膨胀，因此即便在推理中，**phase-level decomposition 也是必要的**。作者在 MLSys 2025 报告 1M-token inference with Llama3-405B in 77s，并保持 93% parallel efficiency。这对小集群的意义不是要照搬其 128 H100 设定，而是提供一个方法：应该先把 prefill 的通信-计算特征和 decode 的状态-带宽特征分开建模，再决定是否要拆。citeturn38search11turn38search3

TaiChi 这篇 2025 预印本之所以值得看，是因为它直接问出了本地部署最关心的问题：**Prefill-Decode aggregation or disaggregation 到底谁更好**。结论不是单边站队，而是条件化：aggregation 更适合严苛 TTFT、宽松 TPOT；disaggregation 更适合严苛 TPOT、宽松 TTFT；平衡型 SLO 下，两者都不最佳，因此它提出 unified disaggregation-aggregation architecture，在不同 GPU 类型与 chunk size 之间调 knob。这个结论对单机/小集群尤其重要，因为小机器常常没有“多租户海量并发”去摊平固定传输开销。citeturn26search3

工业框架文档也给出了很具体的数据路径启发。TensorRT-LLM 明确写到，为优化 disaggregated serving 的整体性能，它会将 **KV transmission 与其他独立请求的 computation overlap**；如果 context/generation instance 使用多 GPU，传输还可以并行。NVIDIA Dynamo 则通过 KV Block Manager 和 NIXL，把 KV offloading 扩展到 CPU memory、local SSD 与 NAS；NIXL 的 README 进一步表明它本身就是面向 inference 的点到点通信库，抽象了 CPU/GPU memory 与 file/block/object store 等多种 backend。也就是说，工业界已经把“KV 是一种可搬运对象，data plane 是可替换的”当成了基本设计前提。citeturn27search9turn27search12turn28view0

对小算力一体机与小集群，部署策略上的关键不是“有没有 P/D”，而是三个更细的问题。第一，**是否有足够多的 in-flight 请求让传输重叠成立**；第二，**KV layout 是否适合跨实例/跨设备传输**；第三，**控制面开销是否会吞掉阶段拆分收益**。如果只有单机低并发、短上下文，则 aggregated serving 往往更稳；如果是多轮长上下文、高 prefix reuse 或 coding/agent 会话，则 P/D 拆分和 external KV store 往往更值钱。Mooncake、TaiChi、vLLM connector 与 TensorRT-LLM docs 共同支撑这一判断。citeturn38search14turn26search3turn19search3turn27search9

### 推理仿真、性能建模与硬件实测方法

如果把前四个方向都看成“部署机制”，那么这一方向就是“如何知道机制值得不值得做”。ServeGen 证明真实 production workload 与 naive synthetic workload 差别很大，因此 benchmarking 必须基于已表征工作负载；BurstGPT 公开了大规模真实 serving traces；ProfInfer 则告诉我们，只做端到端 profiling 不够，必须把 op timeline、DAG、counter 趋势与 model structure 关联起来。citeturn16search0turn15search0turn29view9

CCL-Bench 进一步把“可复验”落成了格式：每个 benchmark data point 不是一个汇总表格，而是 trace、workload card、launch scripts 的组合。Chakra 则朝着 MLCommons execution trace 标准前进，目标是让 trace 能在 simulator、emulator、replay 工具之间复用。这两项工作虽然许多案例来自训练基础设施，但它们对推理仿真系统的启示非常直接：**不要只存 summary metrics，要存证据对象**。否则 later-stage what-if analysis 很容易变成无法解释的 curve fitting。citeturn15search1turn15search11turn15search7

能耗方面，Characterizing LLM Inference Energy-Performance Tradeoffs 给出一个对小机器非常实用的结论：输入长度并不总是 workload difficulty 的最好预测器，轻量语义特征在某些情况下更好；同时不同 query、不同 phase 的能效最优点不同，因此统一的 DVFS 或统一部署策略很可能不是最优。对仿真系统来说，这意味着 energy model 不能只按 tokens/s 拟合，至少要区分 prefill/decode，并考虑 workload heterogeneity。citeturn29view8

综合这些论文，本轮研究最值得吸收的建模思想有三条。第一，**用模型结构参数生成静态资源模板**，例如 layers、hidden size、KV size/token、MoE experts/top-k、expert size、precision。第二，**用 hardware microbenchmark 标定动态代价函数**，例如 matmul throughput by shape/precision、CPU SIMD matmul/FFN/expert throughput、HBM/DDR/SSD/PCIe/NVLink/CXL bandwidth-latency、host runtime overhead、I/O submission overhead。第三，**用 workload trace 提供分布而非均值**，包括 prompt/output length、session reuse、expert hotness、arrival process、tool idle time 与 prefix reuse probability。ServeGen、BurstGPT、ProfInfer、Chakra、CCL-Bench 合起来，几乎正好覆盖了这三层输入。citeturn16search0turn15search0turn29view9turn15search11turn15search1

## 推理仿真系统设计参考

### 可落地的仿真系统蓝图

我建议把“小算力大模型推理仿真系统”设计成一个**分层、可校准、可回放、可 what-if 的离散事件 + 代价模型混合系统**。它不应直接模拟每条指令，而应模拟**状态对象、阶段队列、传输事件、调度决策与容量占用**。这一路线最符合 ServeGen、CCL-Bench、Chakra 与 ProfInfer 所体现的方法学：保留足够细的证据，用可解释中间量替代黑箱拟合。citeturn16search0turn15search1turn15search11turn29view9

#### 输入层

**模型结构输入**至少应包括：层数、hidden size、head 数、GQA/MQA 配置、FFN size、KV size per token、precision、activation/workspace size；若是 MoE，还要加入 experts 数、top-k、shared expert、expert size 与 gate/router 代价。之所以必须做到这一层，是因为 KTransformers、FineMoE、DALI、FluxMoE 全都表明 expert shape 与 top-k 直接决定 prefetch window、CPU fallback 粗细与 HBM pressure；而 llm.npu、HeteroInfer 则表明 tensor shape 与 outlier 位置会改变 CPU/GPU/NPU 的最优映射。citeturn30view3turn32view6turn39search2turn39search3turn36view0turn33view1

**硬件实测输入**应来自 microbenchmark 与 profiler，而不是来自 marketing datasheet。具体需要：GPU/NPU matmul throughput by shape and precision；CPU matmul, FFN, expert kernel throughput；HBM 带宽；DDR 带宽；SSD 顺序/随机读写带宽与 IOPS；PCIe/NVLink/CXL/RDMA 单次提交开销与 steady-state 带宽；host runtime overhead；CPU/NPU/GPU power telemetry。NEO、FlexInfer、KTransformers、Tutti 与 ITME 都表明，真正决定收益的常常不是峰值带宽，而是“当前 shape + 当前层级 + 当前同步模式”下的实测代价。citeturn30view0turn25search2turn30view3turn34view3turn33view6

**工作负载输入**至少应包括：prompt length、output length、batch、concurrency、arrival process、session reuse、prefix reuse probability、KV hit/miss distribution、expert hotness distribution、tool idle time、以及长上下文会话的生命周期。ServeGen 和 BurstGPT 提醒我们，真实 workload 的 burstiness、reuse skew 与 failure pattern 会显著改变结论；如果仿真器只有均匀分布的 prompt/output 长度，它对 small-box deployment 几乎没有指导意义。citeturn16search0turn15search0

#### 建模模块

**prefill/decode 双模型**应单独建立，而不是共用一个平均 token cost。理由很直接：NEO、FlexInfer、TaiChi、Context Parallelism、llm.npu、HeteroInfer 都把 phase disparity 当成一等问题。prefill 主要受 attention/FLOPs/长上下文通信影响；decode 更受 KV 命中、KV restore stall、单 token 级同步与专家 miss 影响。citeturn30view0turn25search2turn26search3turn38search11turn36view0turn33view1

**KV cache memory model**应把 KV 看成对象集合，而不是一个总字节数。对象的属性应包括：所属会话/前缀、层号、token span、storage tier、是否 pinned、restore cost、recompute cost、reuse probability、TTL。这样才能模拟 APC、LMCache 的 pin/lookup/cleanup、HiCache 的 multi-tier pages、Bidaw 的 compute-storage aware scheduling、Tutti 的 object I/O、以及 UCM 的 external KV store。citeturn19search0turn27search6turn12search0turn12search6turn32view7turn13search0

**MoE expert placement model**也要做成对象层。每个 expert 需有 residency tier、热度、next-use probability、load size、quantization format、prefetch lead time、CPU fallback latency。这样才能覆盖 FineMoE 的 expert map、DALI 的 Greedy Assignment + residual-based prefetch、FluxMoE 的 paging、MoE-APEX 的 adaptive precision、KTransformers 的 Expert Deferral。citeturn32view6turn39search2turn39search3turn39search0turn30view3

**CPU offload model**不应只是“CPU 算力上限”，而应明确拆成三部分：CPU compute latency、H2D/D2H latency、以及 host orchestration overhead。NEO、APEX、llm.npu 与 HeteroInfer 都表明，同样一段 CPU 协同逻辑，可能赢在计算、也可能输在同步与 runtime。ProfInfer 的价值就在于它提供了把这些 overhead 单独观测出来的路径。citeturn30view0turn32view2turn36view0turn33view1turn29view9

**interconnect / transfer model**必须支持至少五类路径：GPU/NPU↔CPU、GPU/NPU↔SSD、CPU↔SSD、GPU/NPU↔CXL、GPU/NPU↔remote store，并标记是否 direct path、是否经过 CPU bounce buffer。Tutti 与 ITME 共同证明，路径结构本身就决定收益边界。citeturn34view3turn33view6

**queueing / scheduler model**应是离散事件核心：请求进入、分配实例、prefill 开始、KV 命中/恢复、expert hit/miss、decode step、eviction、prefetch、stall、completion。Mooncake、Bidaw、TaiChi、Dynamo/TensorRT-LLM docs 都表明，不建 scheduler，就无法评估 continuous batching、phase-aware routing、KV-aware routing 与 overlap 的真实收益。citeturn38search14turn12search6turn26search3turn27search9turn27search12

#### 输出与校验

输出不应只有 TTFT、TPOT、throughput。还应包括：HBM occupancy、DRAM traffic、SSD IOPS/throughput、PCIe/NVLink/CXL 利用率、KV restore stall time、expert miss penalty、pipeline bubbles、energy per token / per task、以及 bottleneck attribution。CCL-Bench、Chakra 与 ProfInfer 都在强调“解释性输出”的必要。citeturn15search1turn15search11turn29view9

校验建议分四层。第一层，用 microbenchmark 校准 per-op/per-transfer 代价。第二层，用 ProfInfer 一类工具校准 operator timeline、DMA 重叠率与 host overhead。第三层，用 BurstGPT/ServeGen 类 trace 做端到端 replay，对齐 TTFT、TPOT、P95/P99。第四层，做 sensitivity analysis 与 what-if validation，例如把 DDR 带宽减半、把 SSD IOPS 提高一倍、把 CPU expert throughput 提高 2×，观察系统 bottleneck 是否按预期迁移。只有经过这四层，仿真器才真正具备“规格反推”的价值。citeturn29view9turn15search0turn16search0turn15search1turn29view8

## 收益边界与 Ascend NPU 加 Kunpeng CPU 迁移路线

### 收益边界与反例

**CPU gating / FFN / expert compute 什么时候不值得做**：当被卸载子图过于稠密、过于规则、可直接被加速器高效处理时，CPU compute 很容易被 PCIe/DDR/同步开销反噬。NEO、FlexInfer、KTransformers 的成功都依赖于“只让 CPU 处理值得处理的部分”；HeteroInfer 更直接表明，在移动 SoC 上 CPU 只适合 control plane，不适合主算。换言之，如果你准备把大块 dense FFN 长期放到 CPU，你需要极强的 CPU SIMD/AMX/SVE 和充足 DDR 带宽，否则大概率不赚钱。citeturn30view0turn25search2turn30view3turn33view1

**expert offload 什么时候不值得做**：当 expert hit rate 太低、prefetch lead time 太短、CPU fallback 太慢，或者请求分布高度随机时，expert paging/prefetch 会退化成频繁 miss。FineMoE、DALI、HybriMoE 都必须引入更细的 hotness / trajectory / residual 建模，恰恰说明朴素 offload 很容易失败。尤其在 decode 阶段，单 token miss 对 TPOT 伤害极大。citeturn32view6turn32view5turn39search2

**KV offload 什么时候不值得做**：当 prefix reuse 很低、restore latency 高于 recompute、或者 KV 需要被切成大量碎块时，offload 会失败。Tutti 把这个问题讲得最透彻：现有 CPU-centric SSD-backed KV 路线会因 tiny random I/O、CPU intervention、DRAM-HBM copy 与 CPU-GPU sync 带来高达 70%–80% 的 GPU stall，甚至比重算更慢。对短上下文、低复用、低并发请求而言，直接 recompute 往往更稳。citeturn34view3turn32view7

**CXL 什么时候不适合做热层**：ITME 自己都把 activations 和 working KV 放在 GPU/host 热层，而把 long-context KV 与 weights 放到远端 CXL-hybrid 扩容层。这其实已经给出答案：如果对象缺乏可预测性、访问频繁、单次 miss 会卡住 decode，那么 CXL 更适合做温层/容量层，而不是热路径。citeturn33view6

**SSD direct path 什么时候会被 tiny I/O 反噬**：当 KV/layout 仍按细碎 tensor/page 暴露给 SSD、没有 object/page coalescing、没有 batched submission、没有 GPU-side control path 时，即便名义上是 GDS/direct path，也可能因为单 I/O 软件开销与 PRP 管理而严重退化。Tutti 用 GPU-native object 和 Tensor-Stripe layout 正是在修这个问题。citeturn34view2turn34view3

**P/D 拆分什么时候不赚钱**：TaiChi 已经明确表明 aggregation 与 disaggregation 各自只在部分 SLO 区域占优。对单机、低并发、短上下文或 KV 很少复用的场景，拆分出来的 orchestration / KV transfer / connector 开销可能超过收益。换言之，P/D 不是“默认更先进”，而是“在特定 phase imbalance 与 SLO 结构下更有利”。citeturn26search3

**增加并发什么时候会从算力瓶颈转为容量/带宽瓶颈**：NEO 与 Mooncake 一起说明，batch/concurrency 的问题很快会从 FLOPs 不够转成 HBM 不够，再转成 DDR/SSD/调度开销不够；Tutti 进一步说明，当 KV restore 路径上 tiny I/O 爆炸时，SSD IOPS 会先崩而不是 GPU 算力先崩。对小算力机器来说，并发不是越大越好，而是要找到 HBM occupancy、KV hit rate 与 transfer overlap 的拐点。citeturn30view0turn38search14turn32view7

### Ascend NPU 加 Kunpeng CPU 迁移路线

从公开文档看，Ascend 生态在 2025–2026 年已经具备若干关键支点：vLLM-Ascend 已支持 KV Cache CPU Offload、UCM、PD-colocated with Mooncake、多实例 PD、Weight Prefetch、Distributed DP Server With Large-Scale Expert Parallelism；Mooncake 文档也已明确支持 vLLM Ascend；MindIE-LLM 则开始公开 Continuous Batching、PagedAttention、FlashDecoding 等 serving 基础能力。这意味着，你现在就能在 Ascend 上做**状态分层、KV offload、PD-colocated 和部分专家并行原型**，而不是从零开始。citeturn14search0turn13search0turn14search16turn13search15turn14search1turn14search13turn14search10

| 机制 | 代表论文/系统 | CUDA/GPU 生态做法 | Ascend 可用支点 | Kunpeng CPU 角色 | 纯软件可做 | 需要引擎 hook | 需要 runtime / DMA / memory API | 需要下一代硬件接口 | 优先级 | 最大风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| KV cache CPU offload | NEO, vLLM OffloadingConnector | cudaMemcpyAsync + pinned host memory | vLLM-Ascend KV Cache CPU Offload | warm tier、restore buffer、metadata manager | 是 | 需要 per-block pin/restore/lookup | 需要低开销 NPU↔CPU async copy | 更好的 shared pinned memory | P0 | host overhead 过大时 decode 抖动 citeturn30view0turn19search2turn14search0 |
| External KV store / prefix cache | LMCache, UCM, Mooncake | LMCache/Mooncake connectors | UCM, Mooncake on Ascend | 存储编排、I/O aggregation | 是 | 需要 connector / object ID / TTL | 需要 NPU 侧异步恢复接口 | NPU↔SSD direct path 更佳 | P0 | object layout 不稳、兼容性碎片化 citeturn27search6turn13search0turn14search1turn14search13 |
| PD / KV transfer | Mooncake, TensorRT-LLM DS, vLLM NixlConnector | UCX/NIXL/KV exchange | PD-colocated with Mooncake, vLLM-Ascend kv_transfer 代码结构 | 调度、缓冲、路由 | 部分可以 | 需要 phase-aware scheduler | 需要高性能 NPU↔NPU / NPU↔CPU transfer API | 更低开销 KV DMA path | P1 | 低并发下拆分不赚钱 citeturn27search9turn19search5turn14search16turn13search17 |
| CPU fallback expert | KTransformers, DAOP, DALI | x86 AMX / AVX-512 + async CPU-GPU | Kunpeng SIMD/SVE 可尝试 | expert compute / low-frequency expert | 部分可以 | 需要 router/expert manager hook | 需要 expert tensor layout 导出 | 更强 CPU matrix ISA / 更高 DDR 带宽 | P1 | 如果 Kunpeng kernel 不够强，会被传输开销吃掉 citeturn30view3turn32view4turn39search2 |
| Expert paging / prefetch | FineMoE, FluxMoE, MoE-APEX | vLLM/HF expert manager 改造 | vLLM-Ascend distributed expert parallel + weight prefetch | prefetch planner、warm tier | 部分可以 | 必须改 expert manager | 需要异步 weight prefetch / eviction API | NPU 本地页式权重管理更佳 | P1 | 公开 artifact 少，热度模型难迁移 citeturn32view6turn39search3turn39search4turn13search15 |
| SSD-backed KV object I/O | Tutti | GPU-native object + GPU io_uring | 当前公开支点较弱 | I/O control fallback | 很有限 | 需要 storage-aware KV manager | 需要 NPU-side async storage submission | 需要真正 NPU↔SSD direct path | P2 | 这是当前 Ascend 公开生态最大缺口之一 citeturn32view7turn34view3 |
| CXL / remote memory tier | ITME | CXL-hybrid + RDMA + DMA pipeline | 当前公开支点有限 | host memory proxy / coordinator | 很有限 | 需要 memory tier policy | 需要远程内存地址化接口 | 需要未来硬件与 runtime 协同 | P2 | 公开商用品与论文都少，落地风险高 citeturn33view6 |
| Trace / profiler / simulator | ProfInfer, Chakra, CCL-Bench | eBPF + execution trace + replay | openEuler/eBPF + MindIE/vLLM-Ascend logs | tracer / offline simulator host | 是 | 需要 engine event hooks | 需要 counter/telemetry 暴露 | 更丰富 NPU counter API | P0 | 没有统一 trace schema 会导致仿真器失真 citeturn29view9turn15search11turn15search1 |

我对原型优先级的建议是：**P0 先做可观测 + KV 分层**，即 ProfInfer 风格 trace、vLLM-Ascend CPU KV offload、UCM/Mooncake external KV；**P1 再做 MoE expert paging / CPU fallback expert**；**P2 才考虑 NPU-SSD direct path 与 CXL-like tier**。原因并不复杂：前两类已经有公开 engineering hooks，后两类还主要停留在预印本或非 Ascend 的实现中。citeturn14search0turn13search0turn14search16turn29view9turn32view7turn33view6

## 研究空白、精读清单与参考文献

### 研究空白与创新机会

最明显的空白，是**缺少面向小算力单机/小集群的统一 state-object runtime**。LMCache 只覆盖 KV；FineMoE/FluxMoE 只覆盖 expert；vLLM-Omni 文档已开始把 stage-specific multimodal state 接到 prefix caching 机制上，但还没有一套公开系统把 KV、Expert、Weight、Embedding、Latent、Noise/rolling state 放到同一抽象下管理。这个空白一旦补上，调度、隔离、观测、定价和仿真都会一下子清晰很多。citeturn27search6turn39search3turn19search8

第二个空白，是**NPU-SSD direct storage for KV / state object**。Tutti 把 GPU-SSD direct object I/O 讲明白了，但在公开材料里，还没有与 Ascend NPU 相对应的成熟公开系统论文。换句话说，Ascend 生态里缺的不是“有无 KV offload”，而是“能否把 CPU 从 NPU↔SSD 的关键控制路径里移走”。这很可能是未来几年最值得做的系统创新点之一。citeturn32view7turn34view3turn14search0

第三个空白，是**服务收益判定与规格反推模型**。虽然 NEO、FlexInfer、TaiChi、FineMoE、Tutti 都在各自场景里给出收益，但公开论文仍缺一套统一模型，能接受硬件实测参数后自动判断“CPU 子计算是否赚钱、KV offload 是否比 recompute 更好、expert prefetch 深度多少合适、P/D 是否该拆”。这正是小算力推理仿真系统最应该补的空白。citeturn30view0turn25search2turn26search3turn32view6turn32view7

第四个空白，是**Ascend + Kunpeng 的公开系统论文明显不足**。公开文档已经说明 vLLM-Ascend、UCM、Mooncake、MindIE-LLM 都在快速完善，但对应的正式学术系统论文远少于 CUDA 生态。对企业/研究机构而言，这反而是机会：要做的不是再复刻一遍 GPU-only 优化，而是围绕 NPU↔CPU 传输、KV/object 管理、MoE expert paging 与 simulator/trace 方法论，形成第一批可复验的公开系统工作。citeturn13search0turn14search0turn14search16turn14search10

### 最值得精读的论文清单

**P0 必读**

- **NEO**：因为它最清楚地解释了在线推理里 CPU offload 为什么可能赚钱，也最清楚地展示了何时会被 CPU 带宽反噬。citeturn17search2turn30view2
- **KTransformers**：因为它把 CPU fallback expert 从“概念”做成了可运行的高性能实现，并把 CPU ISA 能力（AMX）与系统收益直接绑定。citeturn30view3turn30view4
- **Mooncake**：因为今天所有 KV-centric state disaggregation 的工程思路，几乎都能在它身上找到原型。citeturn27search3turn38search14
- **Tutti**：因为它最准确地点破了 SSD-backed KV 的真正瓶颈是 tiny I/O 与 CPU-centric control path。citeturn32view7turn34view3
- **FineMoE**：因为它把 expert hotness / trajectory / prefetch 准确度做成了可量化系统设计。citeturn32view6turn33view5
- **ServeGen + BurstGPT + ProfInfer + Chakra/CCL-Bench**：因为要做仿真系统，这四条线分别提供 workload、trace、profile 与标准化证据。citeturn16search0turn15search0turn29view9turn15search11turn15search1

**P1 应读**

- **FlexInfer**：补齐 phase-aware offload 与单卡受限环境下的策略空间。citeturn25search2turn16search10
- **llm.npu**：理解 on-device NPU 场景下 outlier/tensor/block 三层切分是怎么做的。citeturn36view0turn37view0
- **HeteroInfer**：理解移动 SoC 上 CPU/GPU/NPU 的实际角色分配。citeturn33view1turn34view7
- **Cache in the Wild / Bidaw / CacheSlide / ECHO**：理解 KV 生命周期从真实 workload、storage-awareness 到 sparse attention 恢复的完整谱系。citeturn26search2turn12search6turn32view9turn11search3
- **DALI / FluxMoE / MoE-APEX**：理解 MoE 专家对象化正在往哪边演化。citeturn39search2turn39search3turn39search0

**P2 背景参考**

- **Context Parallelism**：虽偏大规模，但有助于建模长上下文 prefill 的规模边界。citeturn38search11
- **TaiChi**：虽仍是预印本，但非常适合做 P/D 收益边界讨论。citeturn26search3
- **ITME**：更像 vision paper，但对 CXL/remote memory tier 的分层思维很有启发。citeturn33view6
- **SolidAttention**：适合理解“先减小状态体积，再做 tiering”这一路线。citeturn30view6

### 参考文献与链接清单

以下仅列 primary source 或作者/官方项目页，不列二手媒体总结。

NEO, MLSys 2025。citeturn17search2turn17search6  
FlexInfer, MLSys 2025。citeturn25search2turn16search10  
Marconi, MLSys 2025。citeturn26search1turn26search8  
Context Parallelism, MLSys 2025。citeturn38search7turn38search11  
Fast On-device LLM Inference with NPUs, ASPLOS 2025。citeturn17search3turn36view0  
Characterizing Mobile SoC for Accelerating Heterogeneous LLM Inference, SOSP 2025。citeturn18search0turn18search2  
KTransformers, SOSP 2025。citeturn22search6turn22search14  
Toppings, USENIX ATC 2025。citeturn23search1turn23search5  
Weaver, USENIX ATC 2025。citeturn23search0turn23search4  
KVCache Cache in the Wild, USENIX ATC 2025。citeturn26search2turn26search9  
Mooncake, FAST 2025 / TOCS 2025。citeturn27search3turn27search19  
IMPRESS, FAST 2025。citeturn29view4  
SolidAttention, FAST 2026。citeturn29view5  
Bidaw, FAST 2026。citeturn12search6turn12search2  
CacheSlide, FAST 2026。citeturn12search1turn32view9  
FineMoE, EuroSys 2026。citeturn21search1turn32view6  
ServeGen, NSDI 2026。citeturn16search0turn29view7  
ECHO, OSDI 2026。citeturn11search3turn23search6  
APEX, arXiv 2025。citeturn32view2  
HybriMoE, arXiv 2025。citeturn32view5  
DAOP, arXiv 2025。citeturn32view4  
DALI, arXiv 2026。citeturn39search2turn39search6  
FluxMoE, arXiv 2026。citeturn39search3turn39search7  
Tutti, arXiv 2026。citeturn32view7  
ITME, arXiv 2026。citeturn33view6  
LMCache technical report / docs。citeturn27search2turn14search12  
SGLang HiCache docs。citeturn12search0turn12search12  
vLLM APC / KV connector / OffloadingConnector / NixlConnector docs。citeturn19search0turn19search1turn19search2turn19search5  
TensorRT-LLM docs。citeturn27search1turn27search9  
NVIDIA Dynamo / NIXL docs & repo。citeturn27search0turn27search12turn28view0  
vLLM-Ascend UCM / CPU Offload / Mooncake guides。citeturn13search0turn14search0turn14search16  
MindIE / MindIE-LLM。citeturn14search2turn14search10  
BurstGPT。citeturn15search4turn15search8  
CCL-Bench 1.0。citeturn15search1turn15search9  
MLCommons Chakra。citeturn15search11turn15search3  
ProfInfer。citeturn29view9turn30view7  
Characterizing LLM Inference Energy-Performance Tradeoffs。citeturn15search2turn29view8

### 搜索关键词清单

本轮实际采用并验证过的关键词，覆盖了你要求的三种检索方式中的“按问题域关键词搜索”部分，并结合论文名进行了 citation expansion：

`CPU GPU collaborative LLM inference`  
`CPU offloading online LLM inference`  
`CPU assisted attention LLM`  
`CPU fallback expert MoE`  
`CPU FFN acceleration LLM inference`  
`CPU GPU hybrid inference MoE`  
`on-device LLM inference NPU CPU GPU`  
`heterogeneous LLM inference CPU GPU NPU`  
`Fast On-device LLM Inference with NPUs`  
`Characterizing Mobile SoC for Accelerating Heterogeneous LLM Inference`  
`KTransformers CPU GPU hybrid inference MoE`  
`FineMoE expert offloading`  
`DALI MoE inference local PCs`  
`FluxMoE expert residency`  
`MoE-APEX adaptive precision expert offloading`  
`KV cache offload CPU memory SSD`  
`external KV cache LLM serving`  
`KV cache tiering DRAM SSD CXL`  
`SSD-backed KV cache LLM`  
`GPU direct storage KV cache`  
`SGLang HiCache`  
`LMCache KV cache layer`  
`Mooncake KVCache disaggregated serving`  
`vLLM KV connector`  
`NixlConnector`  
`KVCache Cache in the Wild`  
`Bidaw KV caching interactive LLM`  
`CacheSlide KV cache reuse`  
`SolidAttention hierarchical KV cache`  
`Tutti SSD-backed KV cache`  
`ITME CXL hybrid memory LLM inference`  
`prefill decode disaggregation`  
`disaggregated serving TensorRT-LLM`  
`NVIDIA Dynamo NIXL KV cache offloading`  
`LLM serving simulator`  
`LLM serving profiler eBPF`  
`LLM serving trace replay`  
`ServeGen production workload characterization`  
`BurstGPT trace dataset`  
`CCL-Bench trace-based benchmark`  
`MLCommons Chakra execution trace`  
`Characterizing LLM Inference Energy-Performance Tradeoffs` citeturn17search2turn25search2turn17search3turn18search0turn22search14turn21search1turn39search2turn39search3turn39search0turn27search6turn27search3turn19search1turn19search5turn12search6turn12search1turn29view5turn11search2turn11search1turn16search0turn15search0turn15search1turn15search11turn29view8