# 2025 至 2026 年小算力大模型推理系统优化与推理仿真系统构建深度研究报告

## 研究范围与核验口径

本报告聚焦 2025–2026 年公开的正式会议论文、正式录用论文、arXiv 预印本、官方技术报告与官方项目文档，主题限定为小算力条件下的大模型推理优化，以及面向推理部署决策的性能建模、trace、benchmark 与仿真系统。研究问题的拆解延续了你上一轮回顾中已经明确的主线：CPU 进入计算路径、MoE expert 与 KV cache 的状态管理、分层内存、Prefill/Decode 拆分、硬件互联带宽，以及 Ascend/Kunpeng 迁移。fileciteturn0file0

我优先核验了以下一手来源：arXiv/OpenReview、USENIX/ACM/官方会议页面，以及 vLLM、vLLM-Ascend、LMCache、TensorRT-LLM、NIXL 等官方文档与开源仓库。对于无法在截至 2026 年 7 月 1 日公开页面中完成“正式 proceedings 级”核验的条目，我在文中明确标注为“仅预印本”“仅项目文档”或“仍需人工复核”，避免把预印本误写成正式会议论文。citeturn9academia1turn9academia2turn1view0turn11academia0turn11academia1turn11academia2turn21academia0turn21academia1turn21academia3turn17view0turn13view0turn30view0turn31view0

## 执行摘要

- 2025–2026 年业内最关注的问题，不再是单点 kernel 提速，而是**如何把 KV、Expert、Weight 等运行时状态从“模型内部张量”提升为可迁移、可缓存、可预取、可驱逐的系统对象**，并在 HBM、DDR、SSD、远端内存之间做层次化编排。LMCache、Mooncake、vLLM 的 APC/KV connector、FluxMoE、Tutti 共同体现了这一趋势。citeturn15academia0turn11academia2turn13view0turn14view0turn25academia2turn11academia1

- 论文最密集的方向有三类：**CPU/GPU/NPU 协同推理**、**MoE expert offload/prefetch/cache**、以及 **KV cache 的分层内存与外部化**。代表性工作包括 NEO、FlexInfer、llm.npu、KTransformers、HybriMoE、DALI、FluxMoE、Mooncake、Bidaw、CacheSlide、Tutti、Strata。citeturn9academia1turn9academia2turn1view0turn25academia1turn25academia0turn25academia2turn11academia2turn12search6turn12search1turn11academia1turn38academia0

- 仍然明显空白的方向包括：**统一 state-object runtime**、**NPU-SSD direct path for KV/state**、**非 x86 CPU 的 expert fallback 体系化设计**、以及**面向小算力单机/小集群的 serving simulator**。现有公开系统分别覆盖 KV、Expert 或某一条 I/O 路径，但很少把这些对象放进同一运行时抽象。citeturn15academia0turn25academia2turn11academia1turn17view0

- CPU 参与推理**确实有收益**，但主要收益点不是“替代 GPU 做大块 dense 计算”，而是四个更窄的角色：冷路径 attention/KV 相关子计算、MoE 冷专家 fallback、outlier/小矩阵/稀疏子图处理、以及 I/O/metadata/control plane。NEO、llm.npu、KTransformers、ScoutAttention 都支持这个判断。citeturn9academia1turn1view0turn22academia1turn22search14

- CPU 参与会被反噬的边界也很清楚：**当子图过于规则、数据搬运与同步大于计算本身、或者 DDR/PCIe 不能被流水线重叠时**，CPU 协同会拖慢 decode。HeteroLLM、FlexInfer、Select-N、ScoutAttention 都把收益边界与 phase 差异说得很直接。citeturn33academia0turn9academia2turn38academia3turn22academia1

- MoE expert 与 KV cache 正在变成同一类问题。两者都在争夺 HBM；两者都需要热度估计、放置策略、预取窗口、miss penalty 建模；两者都开始脱离“模型常驻数据”身份，转向“可分页、可分层、可外部化对象”。FluxMoE、FineMoE、LMCache 和 Tutti 的设计语言已经非常接近。citeturn25academia2turn21search1turn15academia0turn11academia1

- 小算力落地最值得优先做的，不是直接追求 SSD 冷层极致，而是先做 **P0 级可观测 + 热/温层状态管理**：prefix/KV 复用、CPU KV offload、phase-aware 调度、profiler/timeline、真实 workload trace。没有这些，后面的 expert paging、SSD-backed KV、CXL/remote tier 都很难做对。citeturn13view0turn35view0turn21academia0turn8academia1turn21academia2turn21academia3

- 构建推理仿真系统最缺的输入，不是 FLOPs，而是**真实 workload 分布、KV/expert 热度、I/O 粒度、control-path 开销、互联实测带宽-延迟曲线、以及 phase-aware 能耗遥测**。ServeGen、BurstGPT、ProfInfer、Chakra、CCL-Bench 都指出了这一点。citeturn8academia1turn21academia2turn21academia0turn21academia3turn21academia1

- 正式会议的强相关论文主要集中在 **MLSys、ASPLOS、SOSP、FAST、EuroSys、NSDI、OSDI**，以及少量 USENIX ATC；相反，在 ICLR、ICML、NeurIPS、AAAI 的已公开 venue/program/proceedings 中，我没有核验到与本题同等聚焦的 S 级系统论文，因此它们更像补充来源，而不是这两年的主战场。citeturn17search2turn25search2turn17search3turn22search6turn27search3turn21search1turn16search0turn11search3turn23search12turn20search0turn20search10turn20search19turn20search5

- Ascend/Kunpeng 的公开生态已经有了可落地支点：vLLM-Ascend 文档列出了 KV Cache CPU Offload、UCM Store、LMCache-Ascend、Weight Prefetch、PD-Colocated with Mooncake、Large-Scale Expert Parallelism、Dynamic Batch 与 Flash Attention 3 等功能入口；但围绕这些能力的**公开系统论文与 artifact 仍明显少于 CUDA 生态**。citeturn17view0turn35view0turn35view1turn35view2turn35view3

## 研究问题地图与会议查缺补漏

### 研究问题地图

| 方向 | 核心瓶颈 | 代表论文或系统 | 主路线 | 依赖的硬件能力 | 对小算力部署的意义 | 对仿真系统的建模要求 |
|---|---|---|---|---|---|---|
| CPU 可卸载计算 | 显存不足、GPU batch 上不去、decode 被容量卡死 | NEO、FlexInfer、llm.npu、ScoutAttention | CPU 参与 attention/KV 子图、outlier、小矩阵与 fallback 计算 | CPU SIMD、DDR 带宽、PCIe 或 UMA、异步 copy | 先把“放不下”变成“冷热分工” | 必须建 CPU compute、H2D/D2H、同步开销三个代价项。citeturn9academia1turn9academia2turn1view0turn22academia1 |
| MoE 专家管理 | Expert 很大但稀疏激活；HBM 与 KV 争容量 | KTransformers、FineMoE、HybriMoE、DALI、FluxMoE、MoE-APEX | expert prefetch、paging、CPU fallback、adaptive precision、cache replacement | CPU/GPU 协同、专家热度预测、异步权重迁移 | 是本地机器跑大 MoE 的最关键路线之一 | 需要 expert 热度、next-use probability、miss penalty、prefetch lead time。citeturn22search14turn21search1turn25academia1turn25academia0turn25academia2turn39search0 |
| KV 与 Prefix 分层内存 | KV 线性增长，restore/recompute 难权衡 | Mooncake、LMCache、Bidaw、CacheSlide、Tutti、Strata、Select-N | external KV layer、hierarchical cache、SSD/GDS、cache-aware scheduling | HBM/DDR/SSD、I/O 并行度、调度器 | 长上下文与多轮会话的 first bottleneck 往往是 KV 而非算力 | 要把 KV 建成对象，而不是一个总字节数。citeturn11academia2turn15academia0turn12search6turn12search1turn11academia1turn38academia0turn38academia3 |
| 权重与其他状态对象 | Weight、KV、Expert、latent 分散管理 | LMCache、FluxMoE、ITME、vLLM connectors | 对象化、分层驻留、按状态类型做生命周期管理 | 远端内存、KV connector、weight prefetch | 这是下一阶段系统创新的空白区 | 需要统一 object lifecycle、hotness、size、tier、migration 接口。citeturn15academia0turn25academia2turn33view6turn14view0 |
| Prefill/Decode 拆分与互联 | TTFT/TPOT 优化目标冲突；KV 传输代价大 | Mooncake、TensorRT-LLM DS、TaiChi、NIXL | disaggregation、KV exchange、overlap、smart routing | RDMA/NVLink/UCX/NIXL、多 GPU 协同 | 适合长上下文、高并发与高复用场景 | 必须单独建 prefill、decode、transfer、router 四类事件。citeturn11academia2turn30view0turn37academia2turn31view0 |
| 仿真、trace、benchmark | 缺真实工作负载与细粒度证据 | ServeGen、BurstGPT、ProfInfer、Chakra、CCL-Bench | production trace、eBPF profile、execution trace、replay benchmark | profiler、counter、telemetry、trace schema | 没有这些就无法做硬件 sizing 与 what-if | 需要 workload 分布、timeline、resource overlap、energy telemetry。citeturn8academia1turn21academia2turn21academia0turn21academia3turn21academia1 |
| Ascend/Kunpeng 迁移 | 公开文献少、接口碎片化 | vLLM-Ascend、LMCache-Ascend、Mooncake、MindIE | 先做 CPU offload、UCM、KV store，再做 expert/paging | NPU-runtime hook、DMA、外部存储 API | 有明确软件落点，但仍缺学术化收敛 | 仿真器要支持 NPU↔CPU、NPU↔store 的非 CUDA 数据路径。citeturn17view0turn35view0turn35view1turn35view2turn35view3 |

### 会议查缺补漏表

从已核验的一手来源看，**强相关论文最集中的 venue** 是 MLSys 2025、ASPLOS 2025–2026、SOSP 2025、FAST 2025–2026、EuroSys 2026、NSDI 2026、OSDI 2026，以及少量 USENIX ATC 2025；而 ICLR、ICML、NeurIPS、AAAI 在本题上更多提供相邻方法与模型层工作，并不是这两年“小算力推理系统论文”的主要产地。对一些 2026 venue，我只能核验到 program、accepted list 或公开论文页，而不是完整 proceedings，因此统一标成“部分公开，仍需人工复核”。citeturn17search9turn17search3turn22search6turn27search3turn23search7turn21search1turn16search0turn23search6turn23search12turn20search0turn20search10turn20search19turn20search5turn40search1turn40search2turn40search3

| 会议 | 2025 结论 | 2026 结论 | 强相关代表 |
|---|---|---|---|
| ICLR | 已检查官方 venue，未核验到 S 级系统主干 | 已检查官方 venue，未核验到 S 级系统主干 | 更偏模型方法，不是本主题主场。citeturn20search0turn20search8 |
| AAAI | proceedings 已公开，但本轮未核验到主干系统论文 | proceedings 已公开，但本轮未核验到主干系统论文 | 可补充 benchmark/profiler，相对边缘。citeturn20search5turn20search9turn20search21 |
| ICML | 已检查官方入口，未核验到 S 级主干 | 2026 仅部分公开，未完成完整复核 | 更偏算法与模型。citeturn20search10turn20search14 |
| NeurIPS | 已检查公开页面，未核验到本题主干系统论文 | 2026 官方页面已上线，但本轮未完成完整复核 | 本题上不是主战场。citeturn20search19turn20search15 |
| MLSys | 强相关最密集 | 2026 公共信息较少，本轮未完成完整复核 | NEO、FlexInfer、Context Parallelism。citeturn17search2turn25search2turn38search7 |
| ASPLOS | llm.npu 强相关 | MoE-APEX、shadowNPU 等继续延伸 | CPU/NPU 协同与 edge/offload 很强。citeturn17search3turn39search0turn18search5 |
| SOSP | KTransformers、端侧异构 SoC 很强 | 2026 尚未完整公开 | MoE/heterogeneous inference 主 venue 之一。citeturn22search6turn18search2 |
| OSDI | 2025 本轮未完成完整复核 | ECHO 强相关明确 | 稀疏注意力与 KV offload。citeturn23search2turn23search6 |
| NSDI | 2025 本轮未完成完整复核 | ServeGen 强相关明确 | workload characterization。citeturn16search0turn16search4 |
| USENIX ATC | Toppings、Weaver、Cache in the Wild 中相关到强相关 | 2026 未完成完整复核 | 真实部署与 serving 行为研究。citeturn23search12turn23search0turn23search1turn26search9 |
| FAST | Mooncake、IMPRESS 强相关 | Bidaw、CacheSlide、SolidAttention 强相关 | KV/state/storage 主 venue。citeturn27search3turn27search19turn12search6turn12search1turn29view5 |
| EuroSys | 2025 本轮未核验到主干 | FineMoE 强相关 | MoE expert 管理的重要 venue。citeturn21search0turn21search1 |
| SoCC | 2025 仅核验到官网，未找到直接主干 | 2026 部分公开，未完成完整复核 | 仍需人工翻 papers。citeturn40search8 |
| Middleware | 2025 仅核验到官网，未找到直接主干 | 2026 部分公开，未完成完整复核 | 仍需人工翻 program。citeturn40search1turn40search17 |
| SC / ISCA / MICRO / HPCA | 有相关硬件与并行背景工作，但本轮未核验到本题主干系统论文 | 多数 2026 页面不全或需人工复核 | 更适合作为硬件建模补充。citeturn40search2turn40search3turn40search6 |

## 强相关论文总表与分方向分析

### 强相关论文总表

下表只放我判为 **S/A 级** 的条目。S 表示直接命中“小算力推理”或“推理仿真系统”核心问题；A 表示虽然不完全等同，但机制和建模方法可以直接借鉴。

| 方向 | 等级 | 论文或系统 | 来源 | 状态 | 核心问题 | 核心机制 | 主要收益 | 对小算力推理的价值 | 对仿真系统的价值 |
|---|---|---|---|---|---|---|---|---|---|
| CPU 异构协同 | S | NEO | MLSys 2025 | 正式发表 | CPU 协同是否能在在线推理中真正赚钱 | CPU 参与部分 attention 与 KV 路径，做 asymmetric pipelining 与 load-aware scheduling | 在 T4/A10G/H100 上分别最高 7.5×、26%、14% 吞吐提升，同时保持延迟。citeturn9academia1 | 证明 CPU 是容量扩展与并发扩展工具 | 需要 phase-aware CPU/GPU 双代价模型 |
| CPU 异构协同 | S | FlexInfer | MLSys 2025 | 正式发表 | 单卡/小内存环境如何灵活 offload | async prefetch、balanced memory locking、flexible tensor preservation | 在资源受限环境相对已有方法最高 12.5×。citeturn9academia2 | 适合单机小卡路线 | 需要按 phase 与 tensor 类别建模 |
| CPU/NPU 协同 | A | llm.npu | ASPLOS 2025 | 正式发表 | 端侧长 prompt prefill 太慢 | chunk-sharing、shadow outlier execution、out-of-order subgraph scheduling | 平均 22.4× prefill、30.7× 能耗改善，端到端最高 32.8×。citeturn1view0 | 说明“小算力”不只是一台 PC，也包括 NPU SoC | 需要 outlier 与 block affinity 建模 |
| CPU/GPU/NPU 协同 | A | HeteroLLM | arXiv 2025 | 预印本 | 移动 SoC 上异构处理器如何分工 | layer/tensor-level 异构执行、快速同步、利用统一内存 | 相对 MLC/MNN 分别 9.99×、4.36×。citeturn33academia0 | 说明 CPU 更适合 control plane 与特殊子图 | 需要 UMA 与同步成本模型 |
| MoE 专家管理 | S | KTransformers | SOSP 2025 | 正式录用 | 本地机器如何跑超大 MoE | AMX-specialized CPU expert kernel、Expert Deferral、async CPU-GPU scheduling | 预填充与解码均显著优于已有本地 MoE 框架。citeturn22search14 | 是 CPU fallback expert 的最强公开证据之一 | 需要 CPU expert kernel 与 deferral overlap 建模 |
| MoE 专家管理 | S | FineMoE | EuroSys 2026 | 正式发表 | 如何更准确地预取和缓存 expert | expert map、相似输入近邻、fine-grained prefetch/offload | 延迟下降 47%，expert hit rate 提升 39%。citeturn21search1 | 说明 expert 热度建模是成败关键 | 需要 next-use probability 与 hit-rate model |
| MoE 专家管理 | A | HybriMoE | arXiv 2025 | 预印本 | CPU-GPU MoE 调度和 cache 不稳定 | dynamic intra-layer scheduling、impact-driven prefetch、score-based cache | prefill 平均 1.33×、decode 1.70×。citeturn25academia1 | 适合小机器先做软件原型 | 需要 layer-wise scheduling 与 cache score 建模 |
| MoE 专家管理 | A | DALI | arXiv 2026 | 预印本 | 静态 expert 分配导致 CPU/GPU 失衡 | 0-1 分配、Residual-Based Prefetch、Workload-Aware Cache Replacement | 对多模型多设置均有显著加速。citeturn25academia0 | 适合把 expert hotness 做成在线模块 | 需要 workload-aware assignment 模型 |
| MoE 专家管理 | S | FluxMoE | arXiv 2026 | 预印本 | expert 常驻 HBM 挤压 KV capacity | expert paging，把 expert 变成瞬时对象 | memory-intensive 条件下最高 3× 吞吐提升。citeturn25academia2 | 直接把专家管理转为状态对象管理 | 需要 transient object residency 模型 |
| KV 分层内存 | S | Mooncake | FAST 2025 | 正式发表 | 长上下文与过载场景如何做 KV-centric serving | PD 分离、全局 KV cache、SLO-aware scheduler | 长上下文场景有效请求能力显著提升。citeturn11academia2 | 是 KV 外部化的工业基石 | 需要 global cache 与 scheduler 联合建模 |
| KV 分层内存 | S | LMCache | 技术报告/开源 | 官方技术报告 | KV 如何成为引擎间共享层 | connector、batched movement、I/O pipeline、control API | 与 vLLM 结合可最高 15× 吞吐改善。citeturn15academia0 | 把 KV 变成一等系统对象 | 需要 pin/lookup/move/compress 语义 |
| KV 分层内存 | A | Select-N | arXiv 2025 | 预印本 | host offload 如何满足 latency SLO | offline + online 选取 offloading interval | 吞吐相对已有方案提升 1.85×。citeturn38academia3 | 小机器部署中很实用 | 提供 SLO-aware placement 变量 |
| KV 分层内存 | A | SpeCache | arXiv 2025 | 预印本 | 从 CPU 动态恢复 KV 太慢 | speculative KV prefetch based on next-token attention | 10× 高压缩下仍保持精度并减小显存。citeturn22academia0 | 适合大内存 CPU 热层 | 需要 restore vs predict 命中率模型 |
| KV 分层内存 | A | ScoutAttention | arXiv 2026 | 预印本 | CPU 协同 KV offload 易把 GPU 拖慢 | layer-ahead CPU pre-computation + block-wise sparse attention | 相对已有 offloading 方法 2.1×。citeturn22academia1 | 为 CPU attention 子路径提供更强证据 | 需要 layer-ahead overlap 建模 |
| KV 分层内存 | S | Tutti | arXiv 2026 | 预印本 | SSD-backed KV 为什么经常不实用 | GPU-native object store、GPU io_uring、slack-aware I/O | TTFT 降 78.3%，请求率 2×。citeturn11academia1 | 是 SSD 冷层路线最重要论文之一 | 需要 tiny-I/O、control path、GPU stall 建模 |
| 长上下文层次缓存 | A | Strata | arXiv 2025 | 预印本/生产系统文档级 | 层级 cache 恢复受 paged layout 碎片影响 | GPU-assisted I/O、cache-aware scheduling | TTFT 相比 vLLM+LMCache 最高降低 5×。citeturn38academia0 | 说明调度与 layout 同等重要 | 需要 layout fragmentation 特征 |
| 仿真/trace | S | ServeGen | NSDI 2026 | 正式发表 | 缺真实 serving workload characterization | per-client 生产工作负载建模与生成 | 避免 50% under-provisioning。citeturn8academia1 | 是仿真器 workload 输入基座 | 直接提供 arrival/process/reuse 分布 |
| 仿真/trace | S | ProfInfer | arXiv 2026 | 预印本 | LLM engine 细粒度可观测性不足 | eBPF probes、timeline、operator graph、counter trend | 低于 4% 开销。citeturn21academia0 | 是原型系统 P0 能力 | 给仿真器提供 timeline 校验 |
| 仿真/trace | A | BurstGPT | dataset / arXiv | 数据集 | 缺真实 bursty serving trace | 5.29M 真实请求轨迹 | 揭示 burstiness、长度分布、失败模式。citeturn21academia2 | 是 realistic replay 的必要输入 | 直接提供 trace replay 种子 |
| 仿真/trace | A | Chakra | arXiv 2026 / MLCommons | 项目 | 缺统一 execution trace schema | 标准化 execution trace 生态 | 面向 simulator/emulator/replay 复用。citeturn21academia3 | 便于仿真器与 benchmark 对接 | 提供 trace schema |
| 仿真/trace | A | CCL-Bench | arXiv 2026 | 预印本 | summary number 不足以支撑因果解释 | trace + workload card + scripts | 可计算 compute/memory/comm efficiency。citeturn21academia1 | 适合作为仿真校验集 | 提供 evidence-first benchmark |
| 工业实现 | A | TensorRT-LLM Disaggregated Serving | 官方文档 | 官方文档 | P/D 拆分与 KV 交换如何工程化 | modular KV exchange、NIXL/UCX、overlap、layout transform | 官方给出 overlap 与 backend 配置。citeturn30view0 | 可作为工业数据面参考 | 需要 KV exchange backend 模型 |
| 工业实现 | A | NIXL | GitHub/官方 | 官方仓库 | 推理数据面如何抽象多类 backend | 统一 CPU/GPU memory 与 file/block/object store 抽象 | 面向 inference xfer 的模块化架构。citeturn31view0 | 有利于 state-object runtime 设计 | 是 interconnect/storage model 的接口参考 |

### 分方向详细分析

#### CPU 可卸载计算与异构协同

2025–2026 年 CPU 重新进入推理主路径，背后的逻辑并不是 CPU 算力突然变强，而是 **HBM/显存成了最昂贵的瓶颈资源**。NEO 的关键贡献是把 CPU 用在“释放 GPU batch 上限”的位置：它不是简单把状态扔到 host，而是让 CPU 承担部分 attention 计算与 KV 状态路径，并通过 asymmetric GPU-CPU pipelining 和 load-aware scheduling 争取吞吐，在保持延迟的同时让 batch 与并发 올라가。citeturn9academia1

FlexInfer 则进一步把问题做成 **phase-aware policy selection**。这类工作最重要的启发，是不要问“要不要 offload 到 CPU”，而要问“哪一阶段、哪一类张量、哪一种形状、在哪种 SLO 下 offload or compute 才划算”。这也是小算力部署和大规模云部署最大的共同点：**收益来自 phase mismatch 的利用，而不是来自 CPU 本身的绝对算力**。citeturn9academia2turn38academia3

端侧路线更极端。llm.npu 把 prompt、tensor、block 三层一起重构：prompt 做 chunk-sharing，tensor 把 outlier 抽给 CPU/GPU，block 再按硬件亲和性调度给 NPU 或 CPU/GPU。它说明了一条非常适合 NPU 生态迁移的经验：CPU 真正适合的是 outlier、浮点小路径、控制面，而不是大块 INT8 主矩阵。HeteroLLM 也得到类似结论，只是它更强调移动 SoC 的统一内存和快同步。citeturn1view0turn33academia0

从边界上看，CPU 参与计算最容易失败在三种情况：被卸载子图过于稠密；同步与 copy 无法和计算重叠；DDR/PCIe 压力比节省的 HBM 更快成为新瓶颈。Select-N 与 ScoutAttention 都是在试图把这个边界向外推：前者用 SLO-aware offloading interval 控制 host 参与深度，后者则通过 layer-ahead CPU pre-computation 避免 CPU 变成 decode 临界路径。citeturn38academia3turn22academia1

对小算力部署的直接建议是：**优先让 CPU 承担 metadata manager、prefix/KV warm tier、cold attention path、outlier path 与 MoE fallback；不要一开始就把大块 dense FFN 主算放到 CPU。** 对仿真器来说，CPU 路线不是一个“CPU FLOPS”参数可以解决的，至少要分成 CPU kernel latency、host orchestration latency、D2H/H2D latency 三个项。citeturn9academia1turn1view0turn22academia1

#### MoE 专家权重卸载、预取、缓存与冷热判断

MoE 方向在 2025–2026 年之所以突然密集，是因为它把一个非常现实的部署矛盾放大了：**大量 expert 并不活跃，但一旦全部常驻 HBM，就和 KV cache 抢掉真正影响吞吐的热容量。** 这就是 FluxMoE 之所以重要的原因。它直接提出 expert paging，把 expert 从常驻参数变成 streamed transient resource，让 HBM 优先留给吞吐更敏感的 runtime state。citeturn25academia2

KTransformers 是这一方向最强的工程证据之一。它证明 CPU fallback expert 不是“临时补丁”，而可以成为正式设计点，前提是 CPU 侧真的有高效矩阵内核，例如 x86 的 AMX。FineMoE 则把主题从“有没有 offload”推进到“热度预测准不准”：它用 expert map 与历史相邻输入预测下一轮热点 expert，从而把 prefetch 与 cache 做细做准。citeturn22search14turn21search1

HybriMoE、DALI 与 FlashMoE 则分别代表三类更细的工程思路。HybriMoE 做的是 CPU-GPU 动态调度与 score-based cache；DALI 把 expert 分配建模成 0-1 优化，再做 residual-based prefetch；FlashMoE 则开始把 SSD 作为冷专家层，并用机器学习型 cache replacement 提高 hit rate。它们共同说明：MoE offload 真正难的不是“读盘”，而是**如何判定哪些 expert 会在接下来的很窄时间窗口里被再次访问**。citeturn25academia1turn25academia0turn26academia1

这一方向的反例也很明确。若 gate pattern 高度不稳定、prefetch 窗口很短、CPU fallback 内核不强、或 expert load size 太大，那么错误预取和重复搬运很快就会吞掉收益。换句话说，MoE expert offload 只有在 **top-k 稀疏性足够强、热点重用足够明显、CPU 或 warm tier 足够快** 时才真正赚钱。citeturn21search1turn25academia0turn25academia1turn25academia2

对仿真系统而言，MoE 不应该被视为“稀疏 FFN”而已，而应被建模为一组对象：每个 expert 有 size、tier、热度、quantization format、next-use probability、load latency、CPU fallback latency、prefetch lead time。没有这组变量，MoE 模型就只能做很粗糙的 curve fitting。citeturn25academia0turn25academia1turn25academia2turn39search0

#### KV cache 容量管理、卸载、恢复与预取

KV cache 在这两年已经从“注意力副产品”升级成“推理系统中的主要资产”。Mooncake 的工业意义在于，它把 KV cache 提到调度器中心；LMCache 的方法论意义在于，它把 KV 暴露为可 pin、lookup、cleanup、movement、compression 的独立接口层；vLLM 则把 APC、KV offloading、Mooncake connector、NixlConnector 全部做成了产品化入口。citeturn11academia2turn15academia0turn13view0turn14view0

2025–2026 年真正的新变化，是 KV 管理开始穿透到 **HBM/DDR/SSD/CXL/远端层级**。Select-N、SpeCache、ScoutAttention 解决的是 CPU/DRAM 热层与 warm tier 的问题；Bidaw、CacheSlide、Strata 则开始正视真实 workload 下的层次 cache 与前缀偏移；Tutti 则把冷层一直推到 NVMe SSD，并指出现有 SSD-backed KV 失败的根源往往不是介质带宽，而是 paged layout 造成的 tiny I/O，加上 CPU 仍在关键 I/O 控制路径中。citeturn38academia3turn22academia0turn22academia1turn12search6turn12search1turn38academia0turn11academia1

这里最值得强调的收益边界有三条。第一，**KV offload 并不总比 recompute 好**：若 prefix reuse 低、restore latency 高、或对象粒度过碎，则重算反而更稳。第二，**SSD 冷层必须是 object-aware、batch-aware、GPU-aware 的**；否则 tiny random I/O 和 CPU control path 会把理论带宽完全吃掉。第三，**CXL 或 remote memory 更像温层与容量层，而不是极热层**；至少当前公开论文还没有把它证明成 decode 热路径首选。citeturn11academia1turn33view6turn38academia3

借鉴到小算力部署时，优先级通常应是：先做 prefix/APC、再做 CPU DRAM warm tier、再做分层 restore/recompute 决策，最后才是 SSD cold tier。原因很简单：前两步带来的收益更多、更稳、工程复杂度更低；SSD 层通常只有在上下文足够长、复用足够高、工作负载足够稳定时才值得。citeturn13view0turn15academia0turn11academia1turn38academia0

#### 权重、latent、activation 与统一状态对象运行时

这一方向的最大结论，不是“已经成熟”，而是“已经露出清晰空白”。LMCache 在 KV 上已经做出对象化接口；FluxMoE 在 expert residency 上已经做出分页抽象；ITME 则把 context/weights/activations 放进 CXL-hybrid memory 的分层讨论；vLLM 和 vLLM-Ascend 的 connector、UCM、weight prefetch 又把运行时状态进一步显式化。**但真正统一 KV、Expert、Weight、Latent、Prefix 的 runtime 还没出现。** citeturn15academia0turn25academia2turn33view6turn14view0turn35view1turn35view0

这恰好是一个非常适合你当前任务的切入点。因为从系统角度看，这几类东西虽然语义不同，但调度语义高度相似：都有 size、热度、寿命、访问模式、tier、迁移成本、恢复策略和 SLO 敏感度；只不过 KV 更像 request-scoped state，expert/weight 更像 model-scoped state，latent 更像 pipeline-scoped state。把它们统一成同一对象模型，会直接减少运行时和仿真器的重复设计。citeturn15academia0turn25academia2turn33view6

#### 硬件流水线、互联带宽、并发与 Prefill/Decode 拆分

P/D 拆分已经不再只是云上大集群的事。Mooncake 说明了为什么长上下文服务必须把 KV 作为跨阶段资产管理；TensorRT-LLM 官方文档则把 disaggregated serving 的工程要点写得非常清楚：prefill 和 decode 分别运行在不同 GPU 池上，KV cache exchange 模块与底层通信库解耦，支持 UCX/NIXL/MPI，并通过与其他请求计算重叠来隐藏传输开销。citeturn11academia2turn30view0

TaiChi 这篇预印本把很多工程师心里的问题讲透了：aggregation 并不“落后”，disaggregation 也不“天然更先进”；它们分别适合不同的 TTFT/TPOT 约束，平衡型 SLO 反而常常需要二者混合。这个结论对小集群尤其重要，因为小集群往往没有大到足以自动摊平 KV 传输和调度开销。citeturn37academia2

NIXL 的价值则在于把数据面抽象出来。它面向 inference xfer，统一 CPU/GPU memory 与 file/block/object storage backend，说明工业界已经在把“状态跨层/跨节点迁移”当成运行时一等能力，而不是某个框架的附属脚本。citeturn31view0

从收益边界看，P/D 拆分只有在以下场景明显赚钱：上下文长、请求并发高、prefix/KV 复用高、或者 TTFT 与 TPOT 目标相互冲突时。相反，若上下文短、并发低、transfer overlap 做不起来，或者控制面开销太高，P/D 拆分很可能不如单实例 aggregated serving。citeturn30view0turn37academia2

#### 推理仿真、trace、profiling 与性能建模

如果前面几条是“机制层”，这一条就是“知道机制是否值得做”的证据层。ServeGen 与 BurstGPT 说明，没有真实 workload characterization，系统评估会高估很多优化的泛化性；ProfInfer 说明，没有细粒度 timeline 与 counter，就无法判断瓶颈到底在 compute、memory、scheduler 还是 host runtime；而 Chakra 与 CCL-Bench 则进一步说明，未来 benchmark 应该交付可复用证据，而不只是 end-to-end summary number。citeturn8academia1turn21academia2turn21academia0turn21academia3turn21academia1

在这个方向上，最值得采纳的不是某一篇论文里的公式，而是共同的方法论：**结构参数 + microbenchmark + production trace + profiler timeline + what-if replay**。仿真器必须同时尊重模型结构、硬件实测与真实 workload，缺任何一层都会让结果失真。尤其在你关心的小算力场景里，主瓶颈很容易在不同硬件之间迁移：从 HBM 容量迁到 DDR 带宽，再迁到 SSD IOPS、PCIe、host orchestration 或功耗墙。citeturn8academia1turn21academia0turn21academia2turn21academia3turn23academia2

## 推理仿真系统蓝图

我建议把你的“模型推理算力仿真系统”定义为一个**离散事件仿真器 + 硬件实测标定代价模型 + trace replay 框架**，而不是纯 analytical model。原因是现有论文几乎都表明：真正影响收益的，往往是对象粒度、控制路径、阶段切分和重叠率，而这些都很难靠一个平均 token cost 捕获。citeturn8academia1turn21academia0turn21academia1turn21academia3

### 输入层

输入层至少应包含四类数据。模型结构参数方面，需要 layers、hidden size、heads、KV bytes per token、FFN size、precision、top-k experts、expert size、router overhead。硬件侧需要 microbenchmark：GPU/NPU matmul by shape、CPU FFN/expert kernel throughput、HBM/DDR/SSD/PCIe/NVLink/CXL 的带宽与单次开销、host runtime overhead、power telemetry。工作负载侧需要 ServeGen/BurstGPT 类 arrival process、prompt/output length、session reuse、prefix reuse、burstiness、失败模式。对象侧则要有 KV hotness、expert hotness、以及 restore/recompute policy 的历史数据。citeturn8academia1turn21academia2turn21academia0turn23academia2turn15academia0turn25academia0turn25academia2

### 代价模型

代价模型建议拆成九个子模型，而不是一个统一黑箱：prefill cost、decode cost、CPU offload cost、expert placement cost、KV object cost、memory-tier cost、interconnect transfer cost、SSD I/O cost、scheduler/queueing cost。若考虑能耗，再加一个 phase-aware energy model。这样设计的原因，是 NEO/FlexInfer 强调 phase 差异，FluxMoE/FineMoE 强调 expert 热度与分页，Tutti/Strata 强调 I/O 路径和 layout，TensorRT-LLM 强调 transfer overlap，而 ProfInfer/CCL-Bench 强调证据可解释性。citeturn9academia1turn9academia2turn25academia2turn21search1turn11academia1turn38academia0turn30view0turn21academia0turn21academia1

### 离散事件核心

核心事件至少包括：request arrival、prefill start/end、KV hit/miss、KV restore、KV recompute、expert hit/miss、expert prefetch、HBM eviction、CPU fallback expert、decode step、batch formation、transfer overlap、stall attribution、request completion。把这些事件对象化后，仿真器才能自然回答你真正关心的问题：某个硬件改动带来的收益到底来自更多并发、更少 miss、更低 TTFT，还是来自更好的 overlap。citeturn11academia2turn15academia0turn25academia2turn30view0

### 输出指标

输出指标不能只有 throughput、TTFT、TPOT。至少还应输出 P50/P95/P99 latency、HBM occupancy、DDR bandwidth、SSD throughput/IOPS、PCIe/NVLink/CXL utilization、KV restore stall、expert miss penalty、CPU/GPU/NPU utilization、energy per token，以及 bottleneck attribution。否则即便仿真正确，也无法支持后续硬件 sizing 和系统选型。citeturn21academia1turn21academia3turn21academia0turn23academia2

### 校验方法

校验最好分四层。第一层，用 microbenchmark 对齐单算子与单路径传输。第二层，用 ProfInfer 风格 timeline 对齐 phase 内 operator 与 host overhead。第三层，用 BurstGPT/ServeGen 做 trace replay，对齐 TTFT/TPOT/P95。第四层，做 sensitivity analysis 和 what-if sizing，比如增加 CPU 核数、提高 DDR 带宽、换更高 IOPS SSD，看瓶颈是否按预期迁移。只有做完这四层，仿真器才真正具备“从实测条件推回硬件配置需求”的价值。citeturn21academia0turn21academia2turn8academia1turn21academia1turn23academia2

## Ascend 与 Kunpeng 迁移路线

公开文档已经表明，Ascend 生态并不是“从零开始”。vLLM-Ascend 首页明确列出了 **KV Cache Pool、Layerwise KV Pool、KV Cache CPU Offload、Distributed DP Server With Large-Scale Expert Parallelism、UCM Store、Weight Prefetch、Dynamic Batch、Dynamic Chunked Pipeline Parallel、Flash Attention 3、LMCache-Ascend** 等功能入口；Feature Tutorials 还列出了 **PD-Colocated with Mooncake Multi-Instance** 与两类 Prefill-Decode Disaggregation 教程。citeturn35view0turn35view1turn35view2turn35view3

这意味着在 Ascend + Kunpeng 上，P0 级能做而且最应该做的，是三件事。第一，用 vLLM-Ascend 的 KV Cache CPU Offload、KV Cache Pool、UCM/LMCache-Ascend 把 **Kunpeng CPU 变成 warm tier、metadata manager、I/O aggregation 点**。第二，用已有的 Dynamic Batch、P/D 教程与 Mooncake 相关入口，先完成 **phase-aware scheduling 与 KV externalization**。第三，把 profiler 与 simulator 放在 Kunpeng 端运行，优先打通 timeline、trace、counter 和 workload replay。citeturn35view0turn35view1turn35view2

P1 级是 MoE 与 expert 方向。vLLM-Ascend 已公开 Large-Scale Expert Parallelism 与 Weight Prefetch 入口，这说明 **专家管理路径至少已有接口雏形**；但围绕 CPU fallback expert、expert paging、expert hotness prediction 的公开论文与开源 artifact 仍明显不足。因此这条线适合做“公开论文机会”，但不适合作为第一阶段落地的唯一押注。citeturn35view0turn35view3turn25academia0turn25academia2

P2 级才应该考虑 NPU-SSD direct path。原因是 Tutti 的关键创新不是“用了 SSD”，而是把 CPU 从 GPU↔SSD 的关键控制路径移开；而在 Ascend 公开文档里，我能明确核验到 CPU offload、KV pool、UCM、Mooncake 入口，但还不能核验到与 Tutti 等价的 NPU-native object I/O 路线。也就是说，这一块更像未来论文与系统创新机会，而不是今天就能稳定复用的现成功能。citeturn11academia1turn35view0turn35view1

综合来看，Kunpeng CPU 适合承担的角色排序如下：**P0 为 metadata manager、KV warm tier、I/O aggregation、profiler/simulator host；P1 为 expert warm tier 与部分 CPU fallback expert；P2 才是更深入的 direct-storage control-path 替换。** 这里最大的技术风险不是算子实现，而是接口：如果 NPU runtime 不暴露足够低开销的异步 copy、KV object API、以及 store/DMA 回调，那么很多设计只能停留在“CPU 管控一切”的半成品状态。citeturn35view0turn35view1turn35view3turn11academia1

## 研究空白、创新机会、精读清单与参考来源

### 研究空白与创新机会

- **统一 state-object runtime。** 现有公开系统分散管理 KV、Expert、Weight。下一步值得做的是统一对象生命周期、热度、tier、prefetch、eviction、QoS 语义。citeturn15academia0turn25academia2turn33view6
- **NPU-SSD direct path for KV/state。** Tutti 已经把 GPU 路线讲清楚，但公开 Ascend 生态还缺等价系统。citeturn11academia1turn35view0
- **非 x86 CPU 的 expert fallback。** KTransformers 证明了 x86-AMX 的可行性，但 Kunpeng/SVE 路线公开论文仍少。citeturn22search14turn35view3
- **expert hotness 与 KV hotness 联合建模。** 现在两者基本各自建模，但现实里它们共享 HBM 预算。citeturn21search1turn25academia2turn15academia0
- **restore vs recompute 自动决策。** Select-N、SpeCache、ScoutAttention、Tutti 都各做一部分，还没有统一策略框架。citeturn38academia3turn22academia0turn22academia1turn11academia1
- **面向小算力单机/小集群的 serving simulator。** Current work 有 trace 与 profiler，但缺能直接反推 CPU/DDR/SSD/HBM 规格的开源工具。citeturn8academia1turn21academia0turn21academia1turn21academia3
- **Ascend/Kunpeng 的公开系统论文机会。** 公开文档已具备功能支点，学术产出却还稀缺。citeturn35view0turn35view1turn35view2turn35view3
- **prefix/KV/expert 的跨模型共享。** SwiftCache、TableCache、LMCache 已出现苗头，但仍未形成统一框架。citeturn36academia1turn36academia3turn15academia0

### 精读清单

**P0 必读。**  
NEO、KTransformers、Mooncake、LMCache、Tutti、ServeGen、ProfInfer、FineMoE。前五篇基本决定“小算力推理”的工程主线；后二者决定你能否把这些机制变成可验证、可仿真的系统。citeturn9academia1turn22search14turn11academia2turn15academia0turn11academia1turn8academia1turn21academia0turn21search1

**P1 应读。**  
FlexInfer、llm.npu、Select-N、SpeCache、ScoutAttention、FluxMoE、DALI、Strata、TensorRT-LLM Disaggregated Serving、NIXL。这一层用来补齐 phase-aware offload、端侧异构、SLO-aware placement、细粒度 I/O 与工业数据面的理解。citeturn9academia2turn1view0turn38academia3turn22academia0turn22academia1turn25academia2turn25academia0turn38academia0turn30view0turn31view0

**P2 背景。**  
BurstGPT、Chakra、CCL-Bench、HeteroLLM、TaiChi、ITME、FlashMoE。它们不一定直接决定第一阶段原型路线，但会极大改善你对真实 workload、trace、调度边界和未来硬件层级的判断。citeturn21academia2turn21academia3turn21academia1turn33academia0turn37academia2turn33view6turn26academia1

### 参考文献与搜索日志

本轮最核心的一手来源包括：NEO、FlexInfer、llm.npu、KTransformers、FineMoE、DALI、FluxMoE、Mooncake、LMCache、Tutti、Strata、Select-N、SpeCache、ScoutAttention、ServeGen、ProfInfer、BurstGPT、Chakra、CCL-Bench、TensorRT-LLM Disaggregated Serving、NIXL，以及 vLLM 与 vLLM-Ascend 官方文档。对应 primary source 已在正文逐段给出。citeturn9academia1turn9academia2turn1view0turn22search14turn21search1turn25academia0turn25academia2turn11academia2turn15academia0turn11academia1turn38academia0turn38academia3turn22academia0turn22academia1turn8academia1turn21academia0turn21academia2turn21academia3turn21academia1turn30view0turn31view0turn13view0turn17view0

搜索日志方面，我实际使用并扩展了以下关键词族：CPU/GPU/NPU collaborative inference、CPU offloading online LLM inference、CPU fallback expert、MoE expert offloading/paging/prefetch/cache replacement、KV cache offloading/tiering/SSD-backed/prefix caching/external store、disaggregated serving/KV exchange/NIXL、LLM serving simulator/trace-based benchmark/eBPF profiler/energy-performance tradeoff、Ascend KV cache CPU offload/UCM/Mooncake/LMCache-Ascend。会议方面，优先核验了 MLSys、ASPLOS、SOSP、FAST、EuroSys、NSDI、OSDI、USENIX ATC，并对 ICLR、ICML、NeurIPS、AAAI 做了 venue 级检查；对 SoCC、Middleware、SC、ISCA 等只完成了部分公开页面核验，仍建议后续人工逐页翻 program/proceedings 做查缺补漏。citeturn17search2turn17search3turn22search6turn27search3turn21search1turn16search0turn23search6turn23search12turn20search0turn20search10turn20search19turn20search5turn40search1turn40search2turn40search3