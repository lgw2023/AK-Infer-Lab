# 面向本地小算力异构推理协同的系统性 Deep Research 报告

## 执行摘要

截至 **2026 年 6 月 30 日**，这个方向最清晰的主线不是“再造一个更快 kernel”，而是把**推理拆成阶段、把状态变成对象、把内存做成层次、把收益做成可预测**。2025–2026 年最有价值的公开证据基本都围绕这四件事展开。 citeturn31view0turn32view0turn23search1turn23search0turn36view0

第一，**CPU 正在重新进入推理主路径**，但不再是“什么都干的慢速兜底”，而是被放到更适合它的子路径上：小粒度 attention、部分 decode、稀疏专家、短矩阵、索引/预测、控制面同步、数据平铺与状态管理。NEO、llm.npu、HeteroLLM/HeteroInfer、KTransformers 都表明：当 GPU/NPU 侧是 dense 主生成路径，而 CPU 处理短小、不规则、状态相关子路径时，收益往往来自**减少 swap、放大 batch、隐藏通信、提升利用率**；反之，一旦 PCIe/同步/格式转换成为瓶颈，CPU 参与就会反噬。 citeturn26view0turn38view0turn38view4turn39search3turn39search6turn39search7turn11search13turn21search3turn26view3

第二，**KV / Prefix / Context / Expert 已经从“引擎内部临时 tensor”转向“可命名、可迁移、可 pin、可 prefetch、可持久化的状态对象”**。LMCache 明确把 KV cache 抽成独立层，提供 pin / lookup / cleanup / movement / compression 这样的控制 API；Mooncake、HiCache、UCM、vLLM connector 则把这个对象沿着 GPU HBM、CPU DRAM、SSD、远端分布式存储继续外化。 citeturn31view0turn31view1turn30view0turn24search0turn29view3turn29view6turn24search1

第三，**HBM/显存 → DRAM/CXL → SSD/NVMe → Remote Store** 的状态分层已经从“经验技巧”变成了正式系统议题。Beluga、ITME、Tutti、HiCache、UCM 代表了 2025–2026 年最重要的几条路线：CXL 共享内存池、CXL 混合远端内存、GPU 直达 SSD 的 KV object store、以及 GPU/Host/Remote 三层 KV cache。趋势很明确：不是只问“能不能 offload”，而是问“**卸到哪里、何时回流、怎么避免碎片化 tiny I/O、谁负责 metadata 与调度**”。 citeturn23search1turn23search0turn23search3turn30view0turn30view1turn29view3

第四，**CPU 参与是否正收益**，越来越取决于是否满足三个条件：其一，CPU 子计算足够小且不规则，GPU/NPU 做它反而浪费；其二，CPU 计算或 CPU 发起的传输能被 GPU dense 计算完全隐藏；其三，调度器能在每轮 runtime 上判断“这次该不该让 CPU 进来”。NEO 明确提出 load-aware scheduling 和 asymmetric pipelining；KTransformers 用 Expert Deferral 提高 CPU-GPU overlap；HeteroInfer 则显示在统一内存移动 SoC 上，GPU-NPU 协同的收益很大程度来自更高的总带宽利用，而不是单核峰值。 citeturn38view0turn38view4turn21search3turn26view3turn11search10turn39search7

第五，**MoE 是本地小服务器最值得做异构协同的模型类型**。原因不是它“自然更快”，而是它把计算分成 dense 与 sparse 两类路径：attention、shared experts、router 适合留在 GPU/NPU；低频 routed experts、冷专家、预测与预取逻辑更适合放到 CPU/DRAM 侧。KTransformers、HybriMoE、FineMoE、FluxMoE、FloE、DuoServe-MoE 都在做这个方向，只是技术手法不同：有的偏 CPU 计算协同，有的偏专家对象 paging，有的偏 phase-specialized prefetch。 citeturn21search3turn21search4turn25view3turn21search1turn20search3turn20search6

第六，**Prefill / Decode，甚至 Encode / Prefill / Decode 的阶段拆分，已经不只是大集群课题**。Cronus 讨论异构 GPU 上的 partially disaggregated prefill；vLLM、TensorRT-LLM、SGLang、Dynamo/NIXL、Mooncake 都已经提供了可部署的 PD/EPD 机制；vLLM 的 MORI-IO 案例甚至把单机 8x MI300X 的 PD 拆分做到 2.5× goodput。对 1–4 卡小服务器而言，这意味着“阶段化异构协同”已经具备工程抓手。 citeturn22search1turn24search4turn29view8turn29view9turn37view0turn32view1

第七，**Agent / workflow-aware serving 正在改变 KV 生命周期**。KVFlow、TokenCake、Continuum、PBKV、KVCache Cache in the Wild 的共同结论是：多轮对话、工具等待、工作流分叉、共享前缀与动态 agent 调用会让传统 LRU 失效。接下来更关键的不是“缓存多大”，而是“**谁值得被 pin、谁应该 TTL 保活、谁值得从 DRAM/SSD 提前拉回**”。 citeturn14search3turn14search1turn15search0turn14search4turn16search0

第八，**多模态与视频生成把同样的问题又放大了一遍**。SoCC 2025 的生产扩散服务分析和 2026 年的 GENSERVE、DisagFusion 表明，多阶段流水、可预判 step、可中断 latent state、编码器与 DiT/VAE 结构差异，使得 Encode/DiT/VAE/后处理天然适合异构放置。Mooncake 的 EPD 与 embedding cache 进一步证明，多模态状态也正在对象化。 citeturn13search3turn13search5turn13search2turn32view1

第九，**性能预测与规格反推已经开始从经验判断转向 simulator / benchmark / energy model / hardware-aware forecasting**。KernelSight-LM、LIFE、Kareto、Watt Counts、CCL-Bench、能效表征论文给出的共同启发是：本地小服务器选型不能只看 FLOPS，要把**HBM 容量、CPU SIMD/AMX 能力、DRAM 带宽、PCIe/CXL、SSD IOPS、host overhead、能耗预算**放进统一收益函数里。 citeturn36view0turn36view2turn17search0turn36view6turn36view5turn36view3

## 总论文矩阵

下表只纳入与 **GPU/NPU + CPU + HBM/DRAM/SSD/CXL/NVMe/互联/Runtime 协同** 直接相关、且在 2025–2026 有正式发表、公开预印本或官方工程资料更新的条目；纯 kernel、纯量化、纯 speculative decoding 若没有改变状态管理或硬件协同路径，只在后文“弱相关/空白点”中简述。 citeturn31view0turn29view6turn29view8turn29view9

| 方向 | 论文/系统 | 来源与时间 | 类型 | 为什么重要 |
|---|---|---|---|---|
| A | **NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference** | MLSys 2025 citeturn25view1turn26view0 | 正式发表 | 在线推理里把 CPU 作为 decode/attention 协同执行资源，而不是单纯 swap 终点。 |
| A | **Fast On-device LLM Inference with NPUs (llm.npu)** | ASPLOS 2025；早期预印本 2024 citeturn39search3turn39search6 | 早期预印本 + 正式发表 | NPU 主跑 prefill，CPU/GPU 承担 outlier 与硬件不亲和 block。 |
| A | **HeteroLLM / HeteroInfer** | 2025 arXiv；SOSP 2025 公开资料 citeturn39search7turn11search13 | 预印本 + 正式发表 | 统一内存 SoC 上 GPU+NPU 分工与同步机制的代表作。 |
| A | **Challenging GPU Dominance: When CPUs Outperform for On-Device LLM Inference** | arXiv 2025 citeturn10search14 | 预印本 | 反例研究：说明 CPU 不一定慢，关键在 transfer 与线程配置。 |
| B | **LMCache** | arXiv/Tech Report 2025 citeturn31view0turn31view1 | 预印本 + 开源系统 | 把 KV cache 提升为独立层与可编排对象。 |
| B | **MOONCAKE** | FAST 2025；早期预印本 2024 citeturn32view0turn32view1 | 早期预印本 + 正式发表 | KVCache-centric 全局缓存与 PD 架构。 |
| B | **KVCache Cache in the Wild** | USENIX ATC 2025 citeturn16search0turn16search12 | 正式发表 | 首个大云厂真实 KV reuse 分析。 |
| B | **Beluga** | 2025 arXiv；2026 ACM 发表信息 citeturn23search1turn23search5 | 预印本 + 正式发表 | CXL switch 共享内存池直通 GPU/CPU 管理 KV。 |
| B | **ITME** | arXiv 2026 citeturn23search0 | 预印本 | CXL-hybrid 远端内存扩展 + 前缀/权重的主动管理。 |
| B | **Tutti** | arXiv 2026 citeturn23search3 | 预印本 | GPU-centric KV object store + GPU io_uring，绕开 CPU tiny I/O 瓶颈。 |
| B | **SGLang HiCache** | 官方文档 2025–2026 citeturn30view0turn30view1 | 工程框架文档 | GPU/Host/Distributed 三层 KV cache 的工程实现。 |
| B | **UCM for vLLM-Ascend** | 官方文档 2025–2026 citeturn29view3turn34search6 | 工程框架文档 | 面向 Ascend 的外部持久 KV 层。 |
| C | **KTransformers** | SOSP 2025 citeturn21search3turn26view2 | 正式发表 | CPU/GPU 混合 MoE 推理的标志性系统。 |
| C | **HybriMoE** | arXiv 2025 citeturn21search4turn21search12 | 预印本 | 动态 CPU/GPU 调度 + expert 预取/缓存。 |
| C | **FineMoE** | EuroSys 2026 citeturn25view3turn27view4 | 正式发表 | 细粒度 expert map 与 fine-grained offloading。 |
| C | **FluxMoE** | arXiv 2026 citeturn21search1turn21search10 | 预印本 | expert paging，把专家从常驻权重变成流式对象。 |
| C | **FloE** | arXiv 2025 citeturn20search3turn20search11 | 预印本 | 内存受限 GPU 上的按需专家流化与压缩。 |
| C | **DuoServe-MoE** | arXiv 2025 citeturn20search6 | 预印本 | 利用 prefill/decode 阶段差异做 phase-specialized expert 预取。 |
| D | **Cronus** | arXiv 2025；ICLR 2026 submission citeturn22search1turn22search0 | 预印本 + OpenReview | 异构 GPU 的 partially disaggregated prefill。 |
| D | **TensorRT-LLM Disaggregated Serving** | 官方文档 2025–2026 citeturn29view9 | 工程框架文档 | KV 传输与计算重叠、layout transform。 |
| D | **NVIDIA Dynamo / NIXL** | 官方博客、仓库、文档 2025–2026 citeturn29view4turn29view5turn37view0 | 工业技术博客 + 框架文档 | 统一异构 memory/storage data plane。 |
| D | **vLLM PD + MORI-IO** | 官方文档/博客 2026 citeturn24search1turn24search4 | 工程框架文档 + 技术博客 | 单机 MI300X 上也可做 PD 拆分。 |
| E | **KVFlow** | arXiv 2025；NeurIPS 2025 接收信息公开 citeturn14search3turn14search14 | 预印本 + 会议接收公开信息 | workflow-aware KV eviction 和预取。 |
| E | **TokenCake** | arXiv 2025 citeturn14search1turn14search5 | 预印本 | 面向工具等待与多 agent 的时空双调度。 |
| E | **Continuum** | arXiv/OpenReview 2025–2026 citeturn15search0turn15search2 | 预印本 + OpenReview | KV TTL pinning + program-level scheduling。 |
| E | **PBKV** | arXiv 2026 citeturn14search4turn25view8 | 预印本 | 动态 agent 调用预测驱动的 GPU 保活与预取。 |
| F | **Understanding Diffusion Model Serving in Production** | SoCC 2025 citeturn13search0turn13search3 | 正式发表 | 生产扩散服务工作负载与阶段不均衡的顶层分析。 |
| F | **GENSERVE** | arXiv 2026 citeturn13search5turn28view0 | 预印本 | 同集群 T2I/T2V 混部与 step-level 调度。 |
| F | **DisagFusion** | arXiv 2026 citeturn13search2 | 预印本 | DiT/encoder/decoder 异构拆分与弹性调度。 |
| F | **Mooncake EPD / embedding cache** | 官方站点更新 2025–2026 citeturn32view1 | 工程实践 | 多模态 encoder embedding 也已对象化与远距离传输。 |
| G | **KernelSight-LM** | arXiv 2026 citeturn36view0 | 预印本 | token/kernel 级推理 simulator。 |
| G | **Kareto** | arXiv 2026 citeturn17search0turn17search4 | 预印本 | HBM/DRAM/SSD KV tier 的 Pareto 配置搜索。 |
| G | **LIFE** | arXiv 2025 citeturn35search1turn36view2 | 预印本 | 异构 CPU/NPU/iGPU 设备上的硬件感知性能预测。 |
| G | **Characterizing LLM Inference Energy-Performance Tradeoffs** | CCGrid 2026；预印本 2025 citeturn35search2turn36view3 | 早期预印本 + 正式发表 | 直接告诉你 prefill/decode 的能耗差异。 |
| G | **Watt Counts** | arXiv 2026 citeturn36view6 | 预印本 | 异构 GPU 能耗 benchmark/data set。 |
| G | **CCL-Bench** | arXiv 2026 citeturn36view5 | 预印本 | trace-based 基础设施 benchmark。 |
| H | **vLLM APC / NixlConnector / Cache Connector** | 官方文档 2025–2026 citeturn29view6turn29view8turn24search1 | 工程框架文档 | 业界最完整的开放接口之一。 |
| H | **SGLang HiCache / PD / EPD** | 官方文档与站点更新 2025–2026 citeturn30view0turn32view1 | 工程框架文档 | 三层 KV cache 与多模态阶段拆分。 |
| H | **TensorRT-LLM / KV Cache Reuse / Disagg** | 官方文档 2025–2026 citeturn19search2turn16search21turn29view9 | 工程框架文档 | 工业级 KV reuse / exchange / layout transform。 |
| H | **Dynamo / NIXL** | 官方博客/仓库 2025–2026 citeturn29view4turn29view5turn37view0 | 工业技术博客 + 框架 | 统一 data plane、KVBM、planner。 |
| H | **OpenVINO Hetero Execution** | 官方文档 2026 citeturn29view0turn29view1 | 工程框架文档 | CPU fallback 与 fast startup 的官方路径。 |
| H | **AMD Ryzen AI Software** | 官方文档 2026 citeturn29view2 | 工程框架文档 | NPU/iGPU 分工与 ONNX Runtime EP 落地。 |
| H | **vLLM-Ascend / Mooncake / UCM** | 官方文档与 release notes 2025–2026 citeturn33view0turn29view3turn33view1turn33view2 | 工程框架文档 | Ascend 生态里最关键的开放实现。 |
| H | **MindIE** | 官方站点与公开资料 2025–2026 citeturn34search1turn34search4turn34search12 | 官方资料 | 商业化部署能力较成熟，但公开系统细节少于 vLLM-Ascend。 |

## 分方向详细研究

为兼顾可读性，下文把你要求的 18 个字段折叠成五个复合维度：**基本信息、问题与背景、机制与系统层、硬件/评估/收益、迁移性/局限/可靠性**。每一行仍然覆盖你要的关键信息，包括数据搬运路径、状态驻留层、三类趋势映射，以及对小算力一体机的启发。所有数字均尽量保留 baseline、硬件与 workload 语境。 citeturn31view0turn32view0turn36view0

**方向 A：CPU/GPU 或 CPU/NPU 协同推理执行**

| 论文/系统 | 基本信息与问题 | 机制与数据路径 | 评估与收益 | 三趋势映射、启发、迁移、风险 |
|---|---|---|---|---|
| **NEO** | Harvard / UC Berkeley 等；MLSys 2025；正式发表。背景是在线服务想增大 batch、保住延迟，但 GPU 显存不够。它不是简单把所有层 offload，而是针对 online serving 做 **CPU attention kernels + asymmetric pipelining + load-aware scheduling**。 citeturn25view1turn26view0 | 改动层：**Scheduler + Executor + CPU Kernel**。数据路径是 **GPU HBM ↔ PCIe ↔ CPU DRAM**；目标不是反复整层 swap，而是让 CPU 参与部分 decode attention，并由调度器动态决定 GPU-only 还是 CPU-GPU 两子批并行。论文明确强调：若通信可被 dense GPU 计算隐藏，CPU offload 才会赚；若不能隐藏，sub-batch 变小反而吞吐下降。 citeturn38view0turn38view4 | 在 AWS g4(T4)、g5(A10G) 和本地 8×H100 上，针对 7B/8B/70B 模型和在线 workload，NEO 相比非 offload 版本可在**相同延迟**下提升吞吐，最高达到 **T4 上 7.5×、A10G 上 26%、H100 上 14%**。 citeturn26view0 | **方向一**很强：CPU 参与 decode-side attention；**方向二**中等：KV swap-in/out 受 sched 控制但未完整对象化；**方向三**很强：明确给出“通信隐藏 vs. sub-batch 缩小”收益边界。对 1–4 卡小机的启发是：CPU 参与更适合**低到中等并发、长输出、GPU 显存吃紧**场景。迁移到 **Ascend+Kunpeng** 为**中**：需要 Ascend 侧能够把部分 attention/KV 操作留给 CPU 并允许细粒度同步；风险在于 PCIe/UB 带宽、CPU 内存带宽与 runtime host overhead。可靠性：**高置信**。 citeturn38view0turn38view4 |
| **llm.npu** | 北京大学/北邮等；ASPLOS 2025，早期预印本 2024。问题是移动端 prefill 太慢，NPU 虽高能效但只擅长有限数据形状与 INT8 路径。 citeturn39search3turn39search6 | 改动层：**Runtime + Partitioner + Block Scheduler**。prompt 级 chunk 化、tensor 级 outlier 抽离、block 级异序调度：**NPU 跑主 INT8 dense 路径，CPU/GPU 并行处理 outlier 和不亲和块**。这是非常接近你“GPU/NPU 主生成路径，CPU 参与 outlier/小粒度/状态相关子路径”的公开系统。 citeturn39search3turn39search6 | 论文报告平均 **22.4× prefill 加速、30.7× 能耗节省**，端到端最高 **32.8×**，并首次让十亿级模型移动端 prefill 超过 **1000 tokens/s**。INT8 MatMul 在移动 NPU 上相对 CPU INT8 快 **4.5–5.8×**，相对 GPU FP16 快 **1.8–3.5×**；但 FP16 在 NPU 上甚至可能慢 **159×**，说明 dtype/shape 亲和性极关键。 citeturn39search3turn39search6 | **方向一**极强；**方向二**弱到中：聚焦执行分工而非外部状态层；**方向三**很强：明确告诉你 NPU 值得参与的前提是 INT8/固定形状/可 chunk 化。对小一体机启发是：若本地 NPU 对 dense matmul 友好，应把 CPU 放在 **outlier、extract、postprocess、codec、控制面**。迁移到 Ascend+Kunpeng 为**高**：思路高度可迁移，只是 Ascend 的 operator 支持与图模式能力会改变最优切分。局限是移动 SoC 的统一内存与桌面 PCIe 语境不同。可靠性：**高置信**。 citeturn39search3turn39search6 |
| **HeteroLLM / HeteroInfer** | 上海交大等；2025 arXiv，SOSP 2025 公开资料。背景是移动 SoC 已有 GPU+NPU+CPU，但现有引擎常只用一个加速器。 citeturn39search7turn11search13 | 改动层：**Partitioner + Sync Runtime + Unified-Memory-aware Scheduler**。核心是根据 prefill 与 decode 的差异采用不同 tensor partition 策略，并利用统一地址空间减少 GPU-NPU 同步成本。CPU 主要在控制面和 GPU kernel scheduling，不做高能耗主算。作者直接观察到：协同执行可把 aggregate 带宽利用提升到约 **60 GB/s**，但 GPU-NPU 同步开销单次可达约 **400 微秒**，过细粒度切分会反噬。 citeturn11search10turn10search2 | 相比 MLC 和 MNN，性能分别达到 **9.99×** 和 **4.36×**；在边运行游戏边推理的场景中，能维持稳定帧率，prefill 仅 **2.2%** 放缓、decode **17.7%** 放缓。 citeturn39search7turn11search13 | **方向一**极强；**方向二**弱；**方向三**强：它把“同步开销足以淹没 kernel 计算”讲得很清楚。对 PC/塔式机启发是：如果是 UMA/NUMA 更紧耦合的平台，CPU/NPU/GPU 协作会比 PCIe 分离平台更容易赚钱。迁移到 Ascend+Kunpeng 为**中到高**：如果是 Ascend superchip / 异构共享内存形态，原则很匹配；若是普通 PCIe 分离卡，则收益要重估。可靠性：**中高置信**。 citeturn39search7turn11search10turn11search13 |
| **Challenging GPU Dominance** | arXiv 2025；问题是“GPU 一定比 CPU 适合 on-device LLM 吗”。 citeturn10search14 | 改动层较少，更偏 measurement。它在 iPhone 15 Pro 上用 llama.cpp 发现：低线程数 CPU-only 有时能比 GPU 更快，原因不是 CPU 算力更强，而是 **GPU memory transfer overhead + thread oversubscription**。 citeturn10search14 | 在 1B 级模型上，CPU-only（2 线程、F16）达到 **17 tok/s**，超过 GPU 加速时的 **12.8 tok/s**。 citeturn10search14 | 这是很好的**收益边界反例**：CPU 参与为正收益，不一定要因为 CPU 算得更快，而可能是因为避免了不值得的 accelerator path。对你 PPT 的工程化表述非常有用。迁移到 Ascend+Kunpeng 为**中**：结论方向可迁移，具体数字不可迁移。可靠性：**中置信**，因为是单设备单栈测量。 citeturn10search14 |

**方向 B：KV / Prefix / Context 分层卸载、外部 KV、状态恢复、CXL/SSD/NVMe 分层**

| 论文/系统 | 基本信息与问题 | 机制与数据路径 | 评估与收益 | 三趋势映射、启发、迁移、风险 |
|---|---|---|---|---|
| **LMCache** | TensorMesh/Chicago；2025 tech report + 开源。问题是今天的引擎把 KV 限死在单实例、单请求生命周期里，导致 prefix reuse 与 PD 都很难做。 citeturn31view0turn31view1 | 改动层：**KV Manager + Connector + Control API + Storage/Data Plane**。KV 被“提纯”为独立对象，支持 **pinning、lookup、cleanup、movement、compression**，并可存放到 **CPU memory、local disk、remote disk、Redis**，经由 **Ethernet、RDMA、NVLink** 转移。这个设计非常符合你说的“状态对象化”。 citeturn31view0turn31view1 | 报告称与 vLLM 结合后，在多轮 QA、文档分析等 workload 上可达 **最高 15× 吞吐提升**。注意这是强依赖前缀复用率与 workload 的，不能横向误比到一般聊天场景。 citeturn31view0 | **方向二**极强；**方向一**中等：为分阶段执行提供状态接口；**方向三**中等到强：控制 API 使得成本模型可显式化。对小服务器最重要的启发，是优先把 KV 做成**可观测、可恢复、可迁移的对象层**，而不是先写更多 ad-hoc offload code。迁移到 Ascend+Kunpeng 为**高**：接口思想完全可迁移。可靠性：**高置信**。 citeturn31view0turn31view1 |
| **MOONCAKE** | Moonshot AI/清华；FAST 2025，早期预印本 2024。背景是 Kimi 这类长上下文聊天的请求容量受 KVCache 束缚。 citeturn32view0 | 改动层：**Global Cache + Scheduler + Transfer Engine**。其核心不是单点缓存，而是 **KVCache-centric disaggregated architecture**：分离 prefill/decode cluster，并利用 GPU 集群中被低估的 **CPU、DRAM、SSD、NIC** 形成解耦 KVCache。也就是说，数据驻留层级被显式扩成 HBM 之外的全局 cache。 citeturn32view0 | 在真实 trace 下，相对基线有效请求容量提升 **59%–498%**；实际线上在 NVIDIA A800/H800 集群分别多处理 **115%** 和 **107%** 请求。 citeturn32view0 | **方向二**极强；**方向四**也强：为 PD 提供 transfer plane；**方向三**中等：其调度本质上就是收益判定。对小服务器的重要启发是：即使你没有大规模网络，也可以把 Mooncake 的“全局 KV + transfer engine”缩成**单机多卡 / 小集群版可共享 KV 层**。迁移到 Ascend+Kunpeng 为**高**，因为官方站点已公开 vLLM-Ascend、SGLang、TensorRT-LLM 等集成进展。可靠性：**高置信**。 citeturn32view0turn32view1 |
| **KVCache Cache in the Wild** | 上海交大 IPADS；USENIX ATC 2025。问题是许多 KV caching 设计基于合成 workload，不知道真实云厂 reuse 长什么样。 citeturn16search0turn16search12 | 改动层：**KV Eviction Policy**。论文基于真实服务商 trace 得出：KV reuse 在不同请求类别、单轮/多轮请求间都高度偏斜且可预测，因此应按 workload 类别而不是统一 LRU 来做 eviction。 citeturn16search0turn16search2 | 论文强调“理想 cache 所需容量其实适中”，并提出 workload-aware eviction policy，在真实 trace 上优于现有策略。摘要未统一给出单一 speedup 数字，因此此处不做夸大。 citeturn16search0turn16search2 | **方向二**强；**方向三**强：它直接告诉你 prefix/KV 容量和策略要按 workload category 反推。对小机启发是：不要只堆 DRAM，先看系统 prompt、RAG、agent 流和多轮聊天的 reuse skew。迁移到 Ascend+Kunpeng 为**高**。可靠性：**高置信**。 citeturn16search0turn16search2 |
| **Beluga** | 2025 arXiv；2026 ACM 信息已公开。问题是仅靠 CPU DRAM 撑长上下文，容量/通道数不够；而 RDMA disaggregated memory 延迟高、同步复杂。 citeturn23search1turn23search5 | 改动层：**Memory Architecture + KVCache System**。通过 **CXL switch** 让 GPU 和 CPU 共访大规模共享内存池，以 load/store 语义替代传统 RDMA 消息语义。数据驻留层级可理解为 **HBM ↔ CXL memory pool**，CPU/GPU 都能低复杂度访问。 citeturn23search1 | 相比 RDMA 方案，Beluga-KVCache 在 vLLM 上实现 **TTFT 降低 89.6%**、吞吐 **7.35×**。这是 2025–2026 CXL 与 KV 管理结合中最强的一批公开数字。 citeturn23search1 | **方向二**极强；**方向三**也很强：给出了“为什么 CXL 比 RDMA 更适合作共享状态池”的实证。对 1–4 卡服务器的启发是：如果下一代本地工作站能挂 CXL.mem 扩展条或交换机，KV 容量问题会被大幅重写。迁移到 Ascend+Kunpeng 为**中**：看 Ascend 把 CXL 暴露到 NPU 访存路径的能力；若只是 CPU 可见，收益会缩水。可靠性：**中高置信**。 citeturn23search1 |
| **ITME** | arXiv 2026。背景是 agentic + long-context 正把共享上下文基础设施推向 TB 级。 citeturn23search0 | 改动层：**Tiered Memory Expansion Architecture**。用 **CXL-hybrid memory + PCIe Gen5 NVMe SSD** 构造 byte-addressable 远端扩展层，利用 prefix cache 与权重访问模式的可预测性做主动数据管理。它更像是在 CPU offload 之上再加一层远端内存。 citeturn23search0 | 论文用 SK Hynix CMM、Gen5 NVMe 与 FPGA 原型验证，报告最高 **35.7% 吞吐提升**。 citeturn23search0 | **方向二**强；**方向三**强：非常适合做“下一代 CXL + SSD 规格反推”。对小机的启发是：如果你做不了大 CXL pool，也可以先做**本地 DRAM + 远端 CXL/SSD 的策略原型**。迁移到 Ascend+Kunpeng 为**中**：依赖 CXL 生态成熟度。可靠性：**中置信**，因为目前仍是预印本与原型。 citeturn23search0 |
| **Tutti** | arXiv 2026。问题是 SSD-backed KV restore 之所以慢，不只是 SSD 带宽不够，而是**GPU 内存碎片导致大量 tiny random I/O，CPU 成为提交 I/O 的瓶颈**。 citeturn23search3 | 改动层：**GPU-centric KV Object Store + GPU I/O Stack + Scheduler**。数据路径是 **HBM ↔ NVMe SSD**，CPU 只在每层异步加载 I/O kernel，不在关键 I/O control/data path 上。核心是 GPU-native object abstraction、GPU io_uring、slack-aware I/O scheduling。 citeturn23search3turn23search11 | 相比 GDS-enabled SSD-backed LMCache，在严格 SLO 下 **TTFT 降低 78.3%**、可达请求率 **2×**、服务成本 **下降 27%**，并接近 DRAM-backed LMCache 的性能。 citeturn23search3 | **方向二**极强；也是你“GPU/NPU-SSD direct path 是否正收益”的最关键证据之一：**一旦 I/O 发起仍依赖 CPU，小 I/O 仍会被 CPU 反噬**。对小服务器启发极大：若要走 SSD KV tiering，优先解决**object 化、批量 I/O、I/O overlap、layout 对齐**。迁移到 Ascend+Kunpeng 为**中低**：思想可迁移，但需要 Ascend 侧等价的 direct storage/runtime primitive。可靠性：**中高置信**。 citeturn23search3turn23search11 |

**方向 C：MoE 专家卸载、专家预取、专家热度预测、CPU fallback expert、expert-object management**

| 论文/系统 | 基本信息与问题 | 机制与数据路径 | 评估与收益 | 三趋势映射、启发、迁移、风险 |
|---|---|---|---|---|
| **KTransformers** | 清华等；SOSP 2025。问题是大 MoE 模型虽然稀疏，但现有 hybrid inference 仍受 CPU compute 与 CPU-GPU sync 限制。 citeturn21search3turn26view2 | 改动层：**CPU Kernel + Async Scheduler + MoE Runtime**。dense attention/共享路径优先放 GPU，routed experts 利用 CPU/DRAM 容量；其 **AMX-specialized kernels** 提升 CPU 可用性，**Expert Deferral** 增强 CPU/GPU overlap。路径是 **GPU VRAM 持有 dense/runtime state，CPU DRAM 持有专家权重，按需流式调度**。 citeturn21search3turn26view3 | 相比现有系统，full-accuracy 版本实现 **4.62–19.74× prefill** 与 **1.25–4.09× decode** 提升；Expert Deferral 继续带来 **最高 1.45×** 额外吞吐，精度下降不超过 **0.5%**。 citeturn26view2turn26view3 | **方向一**与 **方向三**都极强，且是本地 MoE 的一号参考。对小机启发是：如果目标是 DeepSeek 类模型，本地 1–4 卡场景必须把 CPU 看成**专家执行与对象管理端**。迁移到 Ascend+Kunpeng 为**中高**：Kunpeng 若具备足够 SIMD/矩阵扩展与内存带宽，思路成立；但 Ascend 与 GPU 的 kernel/runtime 差异会影响 deferral 粒度。可靠性：**高置信**。 citeturn26view2turn26view3 |
| **HybriMoE** | arXiv 2025。问题是 expert 激活模式不稳定，固定 CPU/GPU 映射效率很低。 citeturn21search4turn21search12 | 改动层：**CPU-GPU Scheduling + Prefetch + Cache Management**。提出动态 intra-layer 调度、impact-driven inter-layer prefetch、score-based caching，构建在 kTransformers 之上。数据驻留仍以 GPU 持热专家、CPU 持冷专家为主。 citeturn21search4turn21search12 | 相比 SOTA hybrid MoE 框架，prefill 平均 **1.33×**、decode 平均 **1.70×**。 citeturn21search4turn21search12 | **方向一**和 **方向三**都强；说明仅有 CPU fallback 不够，还要有 expert cache score。对小机启发是：专家热度预测不必太复杂，先做低成本 score/prefetch 就有明显价值。迁移到 Ascend+Kunpeng 为**中**。可靠性：**中置信**。 citeturn21search4turn21search12 |
| **FineMoE** | EuroSys 2026。问题是现有 expert offloading 粒度太粗，导致要么显存占用大，要么 miss 多、延迟高。 citeturn25view3 | 改动层：**Expert Map + Prefetch/Caching/Offloading Policy**。核心是细粒度 **expert map**，结合语义与轨迹信息指导 prefetch、cache、offload。它实际上在把 expert selection pattern 做成可查询状态对象。 citeturn25view3turn26view9 | 在不同 cache limit 下，FineMoE 平均 expert hit rate 分别比 Mixtral-Offloading、ProMoE、MoE-Infinity 高 **14%、37%、68%**；prefetch/search/update 等操作异步执行，额外系统开销通常低于迭代时间的 **1%**。 citeturn27view4turn27view1 | **方向二**很强：expert object management 已经出现；**方向一**中等；**方向三**强：适合做 expert cache 大小与预取距离反推。对小机启发是：专家对象层不一定要先做复杂神经预测器，先把 map 与元数据做好。迁移到 Ascend+Kunpeng 为**中高**。可靠性：**高置信**。 citeturn25view3turn27view4 |
| **FluxMoE** | arXiv 2026。问题是专家参数常驻 GPU 会挤占更关键的 runtime state，尤其是 KV cache。 citeturn21search1turn21search10 | 改动层：**Expert Paging Abstraction**。论文直接把专家权重从“常驻参数”改成“**streamed, transient resources**”，按需 materialize、用后立刻 evict，让 GPU 把内存优先留给 throughput-critical state。 citeturn21search1turn21search10 | 摘要未给出统一 speedup 数字，但明确强调目标是 severe memory constraints 下的高吞吐 MoE serving。 citeturn21search1turn21search10 | 这是**状态对象化**在 expert 维度的非常纯粹实现，非常符合你的方向二。对本地小机启发是：若 MoE 无法整驻，优先把“专家驻留资格”做成调度对象，而不是先讨论再量化一点。迁移到 Ascend+Kunpeng 为**中**。可靠性：**中置信**。 citeturn21search1turn21search10 |
| **FloE / DuoServe-MoE** | FloE 为 arXiv 2025；DuoServe-MoE 为 arXiv 2025。前者针对单卡内存受限 GPU，后者针对 prefill/decode phase disparity。 citeturn20search3turn20search6 | FloE 通过 expert 内部矩阵压缩与低成本 sparse prediction 降低 PCIe 流量；DuoServe-MoE 显式区分 prefill 与 decode 的专家加载/缓存策略。二者都说明：**专家不是一个静态 tensor，而是和阶段、热度、内存预算耦合的对象**。 citeturn20search3turn20search6 | FloE 在 Mixtral-8x7B 上达到 **9.3× 参数压缩 / 专家**，让 11GB VRAM 也能部署，并相对 DeepSpeed-MII 在 RTX 3090 上获得 **48.7×** 速度提升；DuoServe-MoE 摘要强调 QoS-oriented、phase-specialized scheduling，但此处不夸大未在摘要中统一给出的数字。 citeturn20search3turn20search11turn20search6 | 对 1–4 卡塔式机尤其重要：如果要跑超大 MoE，本地机真正的路线不是“全模型常驻”，而是**专家流式化 + phase-aware prefetch**。迁移到 Ascend+Kunpeng 为**中**。可靠性：FloE **中高置信**，DuoServe-MoE **中置信**。 citeturn20search3turn20search6 |

**方向 D：Prefill/Decode 或 Encode/Prefill/Decode 阶段拆分与异构放置**

| 论文/系统 | 基本信息与问题 | 机制与数据路径 | 评估与收益 | 三趋势映射、启发、迁移、风险 |
|---|---|---|---|---|
| **Cronus** | arXiv 2025，ICLR 2026 submission。问题是 heterogeneous GPU cluster 上，直接做 PD 或 DP/PP 都会失衡。 citeturn22search1turn22search0 | 改动层：**Scheduler + Partially Disaggregated Prefill Runtime**。不是把全部 prefill 丢低端卡，而是把 prefill 前段放到低端 GPU，剩余 prefill 与旧请求 decode 在高端 GPU 重叠执行。路径是 **低端 GPU 预处理 prompt → 高端 GPU 接续 prefill/保 decode 热路径**。 citeturn25view7 | 相比 Disaggregated Low-High，**TTFT P99 最多下降 84%**；相比 PP，**TTFT P99 最多下降 58%**、**TBT P99 最多下降 70%**。 citeturn26view5 | **方向一**和 **方向三**都很强：说明阶段切分不必是二元 P/D，可以是“部分 prefill in low-end + remainder on high-end”。对小机启发是：你完全可以让 iGPU/NPU/小 GPU 承担 prefix 前段、embedding、轻量 encoder，把后半段留给主卡。迁移到 Ascend+Kunpeng 为**中高**，尤其适合“Kunpeng/小 NPU 先做一段，大 NPU 接主路径”的原型。可靠性：**中高置信**。 citeturn25view7turn26view5 |
| **TensorRT-LLM Disaggregated Serving** | 官方文档 2025–2026。 | 改动层：**KV Exchange / Scheduler / Cache Layout Transformation**。NIXL 后端支持多通信栈，系统支持**KV 传输与其他请求计算重叠**，并对 context/generation 不同 parallel strategy 做 cache layout conversion。数据路径是 **device memory ↔ device memory / fabric**，而不是先回 host 组装。 citeturn29view9 | 文档没有给统一 benchmark 表，但把工程上最容易漏掉的点写清楚了：**overlap optimization** 和 **cache layout transformation**。这对小机尤其重要，因为一体机互联弱、转换开销更容易吃掉收益。 citeturn29view9 | **方向二**和 **方向三**都强：它让 KV 版图映射成为一等公民。迁移到 Ascend+Kunpeng 为**中**：若 Ascend runtime 暴露等价 layout-aware transfer 接口，可迁移；否则会卡在格式转换和 host staging。可靠性：**高置信**。 citeturn29view9 |
| **NVIDIA Dynamo / NIXL** | NVIDIA 官方博客、开源仓库与文档，2025–2026。 | 改动层：**Data Plane + Router + Planner + KV Block Manager**。NIXL 为 inference data movement 提供统一抽象，覆盖 CPU/GPU memory 与 file/block/object store；Dynamo 的 KVBM 则把 KV 从 **GPU → CPU → SSD → remote storage** 做多层管理，配合 KV-aware routing、PD disaggregation、SLA planner。 citeturn29view4turn29view5turn37view0 | 工程结果里，Dynamo 仓库列出 **2× 更快 TTFT（KV-aware routing）**、**7× 更快启动（weight streaming）** 等结果；这些结果依赖具体模型与平台，但趋势很明确：**data plane 统一化**本身就是生产收益来源。 citeturn37view0 | **方向二**和 **方向三**都极强。对小服务器启发是：即使做不了完整 Dynamo，也应抽出一个本地版 **state transfer plane**，把 KV、embedding、expert、weight stream 使用同语义处理。迁移到 Ascend+Kunpeng 为**中**：关键不是 NVIDIA-specific API，而是 NIXL 这类统一语义思想。可靠性：**高置信**。 citeturn29view4turn29view5turn37view0 |
| **vLLM PD + MORI-IO** | 官方文档/博客 2026。 | vLLM 的 PD 通过 connector 把 prefill instance 与 decode instance 解耦；2026 的 MORI-IO 博客把这一机制落到单机 **8× MI300X**，展示即使在单节点也可做阶段拆分。 citeturn24search1turn24search4 | 在 Qwen3-235B-A22B-FP8、8 req/s、2000-token prompt / 1000-token output 下，相比 collocated serving，单机 PD goodput 达 **2.5×**。它很适合拿来说明“PD 并不是大规模集群专利”。 citeturn24search4 | 对 1–4 卡小机的启发非常直接：先跑本地 1P1D 或 1E1P1D 原型，再考虑跨节点。迁移到 Ascend+Kunpeng 为**中高**：vLLM-Ascend、Mooncake、UCM 已提供足够多的路径。可靠性：**高置信**。 citeturn24search1turn24search4turn33view2 |

**方向 E：Agent / workflow-aware serving 与工具等待期间 KV 生命周期管理**

| 论文/系统 | 基本信息与问题 | 机制与数据路径 | 评估与收益 | 三趋势映射、启发、迁移、风险 |
|---|---|---|---|---|
| **KVFlow** | arXiv 2025；NeurIPS 2025 接收信息公开。问题是 workflow 中 agent 共享固定 prompt，但传统 LRU 无法预见下一步复用。 citeturn14search3turn14search14 | 改动层：**Workflow-aware KV Manager + Prefetcher**。把 workflow 抽成 Agent Step Graph，用 steps-to-execution 指导 node-level eviction，并在后台线程把下一步所需 KV 从 CPU 预取到 GPU。路径是 **GPU miss → CPU prefetch → 下一步 agent 直接命中**。 citeturn14search3 | 相比 SGLang hierarchical radix cache，单 workflow 大 prompt 场景可达 **1.83×**，多并发 workflow 可达 **2.19×**。 citeturn14search3 | **方向二**和 **方向三**强：它把 workload graph 变成 cache policy 输入。对 coding agent、小团队本地工具链很有启发。迁移到 Ascend+Kunpeng 为**高**。可靠性：**中高置信**。 citeturn14search3turn14search14 |
| **TokenCake** | arXiv 2025。问题是多 agent + 工具调用会同时带来空间争用和时间闲置：等待工具时，GPU 里的 KV 其实在“睡觉”。 citeturn14search1turn14search5 | 改动层：**Temporal Scheduler + Spatial Scheduler**。空间上动态内存分区保护关键 agent；时间上对等待工具的 agent 做 proactive offload 与 predictive upload，把 GPU 空间让给活跃 agent。 citeturn14search1turn14search5 | 对代表性多 agent benchmark，端到端延迟降低 **47.06%+**，有效 GPU 内存利用率提升 **最高 16.9%**。 citeturn14search1 | **方向二**极强：KV 生命周期被显式建模；**方向三**也强：offload/upload 是否值得，要看工具等待时长分布。对本地一体机启发是：工具调用场景特别适合“KV TTL + upload window”。迁移到 Ascend+Kunpeng 为**高**。可靠性：**中高置信**。 citeturn14search1turn14search5 |
| **Continuum** | arXiv / OpenReview 2025–2026。问题是 tool call 会打断连续批处理，导致每一轮都可能 KV 被驱逐、重新 prefill。 citeturn15search0turn15search2 | 改动层：**Tool-aware KV TTL + Program-level Scheduler**。核心不是永远 pin，而是根据 tool call duration prediction 与 turn count 给 KV 设 **TTL**，过期后自动驱逐。 citeturn15search0turn15search4 | 摘要未给单一 speedup，但明确在 SWE-Bench、BFCL 上用 Llama-3.1 8B/70B，跨不同硬件与 DRAM offloading 都优于基线。 citeturn15search0 | 这是非常适合你 PPT 的“状态对象化与恢复优先策略”表述。对小机启发是：别把 pin/unpin 做成二选一，应做 **TTL-based soft pinning**。迁移到 Ascend+Kunpeng 为**高**。可靠性：**中高置信**。 citeturn15search0turn15search4 |
| **PBKV** | arXiv 2026。问题是现实 workflow 常是动态的，未来调用哪个 agent 不固定。 citeturn14search4turn25view8 | 改动层：**Prediction-based KV Cache Management**。通过历史 workflow 与当前上下文预测未来几步 agent 调用，用 conservative 策略同时指导 eviction 与 prefetch，并显式权衡 prefetch 的成本与收益，避免“预测错了反而更慢”。 citeturn14search4turn25view8 | 在动态 workflow 上延迟最多 **1.85×** 优于 LRU、KV hit rate 最多 **2.55×**，在静态 workflow 上也比 KVFlow 高 **1.26×**。 citeturn25view8turn26view7 | **方向二/三**都很强。对本地 agent server 的启发是：如果 workflow 动态，prefix cache 不能只看字符串前缀，还要看 **future invocation likelihood**。迁移到 Ascend+Kunpeng 为**高**。可靠性：**中高置信**。 citeturn25view8turn26view7 |

**方向 F：多模态生成 / 视频生成流水中的 CPU-GPU/NPU 协同、Noise Cache、rolling KV、VAE/codec/后处理**

| 论文/系统 | 基本信息与问题 | 机制与数据路径 | 评估与收益 | 三趋势映射、启发、迁移、风险 |
|---|---|---|---|---|
| **Understanding Diffusion Model Serving in Production** | SoCC 2025。它不是提一个单点算法，而是回答“生产扩散服务到底在忙什么”。 citeturn13search0turn13search3 | 改动层：**Workload Analysis + Scheduling + Resource Efficiency**。关键结论是扩散服务是多阶段流水，encoder / DiT / decoder 资源画像很不一样，不能把它当成“另一种 LLM”。 citeturn13search3 | 这篇论文更偏 top-down 分析与 trace/dataset 贡献，适合做方向性证据，而非直接抄数字。 citeturn13search3 | 对你最重要的启发是：**多模态/视频流水天然适合分阶段异构放置**，而不是单卡 monolithic 部署。迁移到 Ascend+Kunpeng 为**高**。可靠性：**高置信**。 citeturn13search0turn13search3 |
| **GENSERVE** | arXiv 2026。问题是同集群混合服务 T2I/T2V 时，视频与图像请求在 per-step cost、SLO、并行度需求上差很多。 citeturn13search5turn28view0 | 改动层：**SLO-aware Scheduler + Step-level Adaptation**。抓住 diffusion step 可预测、可在 step 边界 preempt 的特点，引入 intelligent video preemption、elastic sequence parallelism、dynamic batching。状态驻留对象不再是 KV，而是**compact latent state**。 citeturn28view0turn28view1 | 在不同配置下，SLO attainment rate 提升 **最高 44%**；视频 latent state 通常只是几十 MB，暂停/恢复代价很小。 citeturn28view0turn28view1 | 这是“状态对象化”从 KV 扩展到 diffusion latent state 的最好工程例子。对本地工作站启发是：多模态服务中应该把**encoder 输出、latent state、VAE buffer**都对象化。迁移到 Ascend+Kunpeng 为**高**。可靠性：**中高置信**。 citeturn28view0turn28view1 |
| **DisagFusion** | arXiv 2026。问题是 commodity GPU 上，encoder / DiT / decoder 权重和算力极不均衡，单体部署既占内存又难调度。 citeturn13search2 | 改动层：**Asynchronous Pipeline Parallelism + Elastic Instance Scheduling**。把阶段拆成异步流水并重叠 stage handoff；调度器用轻量预测 + runtime feedback 动态调实例比。 citeturn13search2 | 相比 monolithic baseline，吞吐可提升 **3.4×–20.5×**，端到端延迟可降低 **18.5×**。注意这是面向现代 diffusion model 的大幅结构性收益。 citeturn13search2 | **方向一**和 **方向三**都强：非常适合映射到“AR+DiT/VAE/后处理流水重叠”。迁移到 Ascend+Kunpeng 为**中高**：要看视频编解码、VAE、NPU graph 支持与互联。可靠性：**中高置信**。 citeturn13search2 |
| **关于 Noise Cache / rolling KV / video generation** | **未找到 2025–2026 直接聚焦“视频生成 serving + Noise Cache / rolling KV 全系统协同” 的高置信正式系统论文。**最接近的是 Future-aware KV policy、Forcing-KV、BWCache 这类模型/推理优化论文，它们确实改变 state reuse，但多数还没延伸成完整的 serving runtime。 citeturn12search3turn12search10turn12search0 | 这说明你在视频生成的“rolling state / Noise Cache 对象化 + 分层回流 + 编解码重叠”方向上仍有明显创新窗口，尤其适合与 Mooncake/LMCache/HiCache 一类对象层结合。 citeturn12search3turn12search10turn12search0 | 迁移到 Ascend+Kunpeng 的潜力反而不低，因为这里公开系统实现仍少。可靠性：**高置信**，因为结论是“公开直接文献仍少”。 citeturn12search3turn12search10turn12search0 |

**方向 G：Trace / Benchmark / Profiler / Simulator / Cost Model / Energy Model / Hardware parameter back-solving**

| 论文/系统 | 基本信息与问题 | 机制与数据路径 | 评估与收益 | 三趋势映射、启发、迁移、风险 |
|---|---|---|---|---|
| **KernelSight-LM** | arXiv 2026。问题是系统设计者需要在没烧大量 GPU-hour 的情况下预测 serving 延迟与各项开销。 citeturn36view0 | 改动层：**Simulator**。把每个 serving step 分解成 roofline kernel model、communication model、host-overhead model，并用离散事件调度器复合，支持 prefix caching/continuous batching。 citeturn36view0 | 在 unseen GPU generation 上，cross-generation tier 的 per-kernel latency 预测误差 **12.1%**，相比 roofline baseline 的 **22.0%** 好 **1.8×**。 citeturn36view0 | 这是你做“目标硬件性能预测、收益边界与规格反推”最应该引用的一类工具。迁移到 Ascend+Kunpeng 为**中**：需要补 NPU microbenchmark 与 host model。可靠性：**中高置信**。 citeturn36view0 |
| **Kareto** | arXiv 2026。问题是 HBM/DRAM/SSD 的 KV tier configuration 是多目标耦合的，解析公式很难写。 citeturn17search0turn17search4 | 改动层：**Simulator + Optimizer**。在 end-to-end simulator 之上搜索 Pareto frontier，联动 cache eviction policy 与 KV block access pattern，为 throughput/latency/cost 三目标配置 tiered storage。 citeturn17search0turn17search4 | 相比固定 1024GB DRAM 配置，最多能提升 **9.3% 吞吐**、降低 **58.3% 延迟** 或降低 **20.2% 成本**。 citeturn17search0 | 这正好对应你的方向三。对小机启发是：本地机也该做“HBM/DDR/SSD 配比搜索”，而不是靠经验拍脑袋。迁移到 Ascend+Kunpeng 为**高**。可靠性：**中高置信**。 citeturn17search0turn17search4 |
| **LIFE** | arXiv 2025。问题是本地 agent 设备常同时有 CPU、NPU、iGPU，但缺少可泛化性能预测。 citeturn35search1turn36view2 | 改动层：**Hardware-aware performance forecasting**。验证覆盖 AMD Ryzen CPU/NPU/iGPU 与 NVIDIA V100，模型为 Llama2-7B 变体。 citeturn35search1turn36view2 | 它的价值不在单一 accuracy 数字，而在建模范式：把设备差异映射进预测器，而不是单 GPU 实测拟合。 citeturn35search1turn36view2 | 这对 Ascend+Kunpeng 非常重要，因为你需要一个能处理 **NPU + CPU + iGPU/显卡** 的成本模型。迁移到 Ascend+Kunpeng 为**中高**。可靠性：**中置信**。 citeturn35search1turn36view2 |
| **Characterizing LLM Inference Energy-Performance Tradeoffs** | CCGrid 2026；预印本 2025。问题是不同 workload / phase / GPU scaling 下的能耗—性能权衡。 citeturn35search2turn36view3 | 改动层：**Benchmark + Phase-aware energy analysis**。非常关键的结论是：decode 占推理时间 **77–91%**，对 GPU 频率不敏感；因此把 GPU 频率从 **2842 MHz** 降到 **180 MHz**，平均可节省 **42% 能耗**，延迟只增 **1–6%**。 citeturn36view3 | 这对“小功耗预算的一体机”非常重要：decode 既然 memory-bound，盲目堆 GPU 频率不一定值。 citeturn36view3 | **方向三**极强。迁移到 Ascend+Kunpeng 为**中**：频率控制接口和能耗计量方式不同，但结论方向可迁移。可靠性：**中高置信**。 citeturn36view3 |
| **Watt Counts / CCL-Bench** | arXiv 2026。前者是 energy-aware benchmark，后者是 trace-based infra benchmark。 citeturn36view6turn36view5 | Watt Counts 给出 50 LLM × 10 GPU × 5K+ 实验、14M+ power samples，并指出 server scenario 在几乎不伤用户体验时可节能 **最高 70%**；CCL-Bench 则把 operator/kernel/communication/timestamp/workload card 一起标准化，包含 compute-communication overlap、memory-transfer overhead、resource utility 等指标。 citeturn36view6turn36view5 | 对你而言，前者可用于“功耗预算反推”，后者可用于“trace/benchmark/profiler 体系化”。迁移到 Ascend+Kunpeng 都是**中高**；难点在于采集栈与 trace schema 适配。可靠性：**中置信**。 citeturn36view6turn36view5 |

**方向 H：工业框架与工程实践**

| 系统/文档 | 关键公开信息 | 对三趋势的意义 | 对 Ascend/Kunpeng 的含义 |
|---|---|---|---|
| **vLLM APC / NixlConnector / Connector 抽象** | APC 明确指出 prefix cache 只优化 prefill、不优化 decode；NixlConnector 提供 fully asynchronous send/receive；PD 文档将 KV transfer 抽象为统一 connector。 citeturn29view6turn29view8turn24search1 | 方向二的接口基石。 | Ascend 若继续跟进 vLLM 插件机制，可以最小代价复用 connector 抽象。 citeturn33view0 |
| **SGLang HiCache** | GPU=L1、Host=L2、Distributed=L3；支持 prefetch / write-back / page_first_direct / GPU-assisted I/O kernels，CPU→GPU 传输可达 **最高 3×**。 citeturn30view0turn30view1 | 方向二与方向三非常契合。 | 很适合被搬到 Ascend+Kunpeng 上做“本地 DRAM + 远端存储”的原型。 citeturn30view3 |
| **TensorRT-LLM** | 官方文档公开了 KV cache reuse、quantized KV cache、disaggregated serving、NIXL backend 与 layout transform。 citeturn19search2turn16search21turn29view9 | 强化状态对象与阶段拆分。 | 适合作为对标基线，不一定是直接复用对象。 |
| **Dynamo / NIXL** | NIXL 统一 memory/storage 语义；Dynamo KVBM 做 GPU→CPU→SSD→remote 多层 offload。 citeturn29view4turn37view0 | 是“统一数据面”的工业答案。 | Ascend 生态值得补的不是某个 kernel，而是这类统一 state plane。 |
| **OpenVINO** | Heterogeneous execution 支持 accelerator 跑重算部分、CPU 跑 fallback op；官方还强调可先用 CPU 做 first inference 再切换设备以降低首次响应。 citeturn29view0turn29view1 | 是方向一和方向三在通用框架中的成熟范式。 | 很适合给 Kunpeng+Ascend 做“CPU first token / NPU steady-state”启发。 |
| **AMD Ryzen AI** | 官方文档说明 Vitis AI EP 会自动决定哪些部分跑 NPU，并同时支持 NPU 与 iGPU。 citeturn29view2 | 说明 PC 侧已经默认把模型切片执行当成标准能力。 | 对 Ascend PC / edge form factor 很有参考价值。 |
| **vLLM-Ascend / UCM / Mooncake** | vLLM-Ascend 是官方推荐 Ascend 后端插件；UCM 建立 HBM→DRAM→Storage 三层 KV；Release notes 持续补齐 DeepSeek、prefix cache、KV 管理、PD、INT8 KV 等能力；Mooncake 对 Ascend 已有可运行集成。 citeturn33view0turn29view3turn33view1turn33view2 | 方向二与方向四最关键的现成落脚点。 | 这是你近期原型最应该直接利用的开源底座。 |
| **MindIE** | 官方资料强调支持单节点/多节点部署、大规模 expert parallelism，以及适配性 PD 分离与长序列切分，但公开系统细节不如 vLLM-Ascend 透明。 citeturn34search1turn34search4turn34search12 | 更多像产品栈，而非论文级公开设计。 | 如果你要做产品验证可参考；如果要做研究创新，公开资料更适合从 vLLM-Ascend/UCM/Mooncake 入手。 |

## 综合机制分析与对三条技术趋势的映射

从公开材料看，**业内真正正在做的事情**可以压缩成一句话：**把“推理”从单卡单进程里的即时算子执行，改造成跨 CPU/GPU/NPU 与多级存储的状态编排系统。**换句话说，过去优化对象是算子、kernel、图；现在优化对象增加了 **阶段、状态、对象、转移、等待、保活与恢复**。 citeturn31view0turn32view0turn37view0turn29view9

从 **Agent Runtime / Router / Scheduler** 这一层看，Cronus、TokenCake、Continuum、PBKV、Dynamo 都在把“下一步可能发生什么”引入调度决策：下一段 prefill 该给谁做，哪个 agent 的 KV 应该保活，哪个 decode worker 更值得接手，哪个视频请求可以在下一个 denoising step 被抢占。它们的共同收益不是某个 kernel 变快，而是**减少无效 prefill、减少错误驱逐、降低阶段互扰、缩短 P99**。 citeturn22search1turn14search1turn15search0turn14search4turn37view0

从 **KV Manager / Expert Manager / Storage/Data Plane** 这一层看，LMCache、Mooncake、HiCache、UCM、Beluga、Tutti、KVBM 的共同方向非常一致：第一步是让状态有稳定 ID 与 metadata；第二步是让状态知道自己落在哪一层；第三步是让迁移/恢复走统一语义；第四步才是针对具体介质做 layout、批量 I/O、零拷贝与 overlap 优化。你提出的“可命名、可定位、可迁移、可 pin、可预取、可恢复、可压缩、可观测”在公开系统里已经是主流路线，而不是边缘想法。 citeturn31view0turn32view0turn30view0turn29view3turn23search1turn23search3turn37view0

从 **Kernel / Hardware Runtime** 这一层看，2025–2026 年有两个最值得吸收的判断。第一，CPU 参与是否赚钱，取决于**是不是在处理 GPU/NPU 不擅长的小而不规则路径**，以及能否被 dense 计算完全隐藏；第二，SSD/CXL 是否赚钱，取决于**你能否把状态布局从 tensor 视角转成 object/page 视角**，避免被 tiny random I/O 与 metadata 往返拖死。NEO、llm.npu、KTransformers、Tutti、HiCache 都在从不同维度证明这点。 citeturn38view4turn39search3turn21search3turn23search3turn30view1

把这些结论映射到你的三条技术趋势，可以形成几乎可以直接写进 PPT 的工程表述：

对于 **方向一：阶段化 A+K / 异构协同计算**，建议表述成：  
**“将生成主路径与不规则子路径解耦：GPU/NPU 持续占用 dense 主生成图，CPU 以子路径执行器身份接管短序列、小矩阵、稀疏选择、冷专家、索引/预测、编解码与后处理；收益条件由 runtime 基于阶段、batch、互联和尾延迟预算做在线判定。”** 这句话有 NEO、llm.npu、HeteroInfer、KTransformers、OpenVINO 等多篇/多框架背书。 citeturn38view0turn39search3turn39search7turn21search3turn29view0

对于 **方向二：模型状态对象化与分层回流**，建议表述成：  
**“把 KV/Prefix/Context/Expert/Embedding/Latent 从引擎内部临时张量提升为统一状态对象层，建立 HBM/DRAM/CXL/SSD/Remote 的层级驻留、pin/prefetch/evict/restore/recompute/compress 机制；以对象粒度而非张量粒度调度状态流动。”** 这正是 LMCache、Mooncake、HiCache、UCM、Beluga、Tutti、Dynamo 正在做的事情。 citeturn31view0turn32view0turn30view0turn29view3turn23search1turn23search3turn37view0

对于 **方向三：目标硬件收益预测与规格反推**，建议表述成：  
**“建立统一收益模型，对 CPU 子计算、KV 分层回流、专家预取、PD/EPD 拆分、GPU/NPU-SSD 直通与压缩/重算进行 what-if 分析；输入为 HBM 容量、DRAM 带宽、CPU SIMD/AMX、互联带宽/时延、SSD IOPS/吞吐、功耗预算，输出为延迟/吞吐/成本/能效的 Pareto 选择。”** 对应证据正来自 KernelSight-LM、Kareto、LIFE、能效表征与 benchmark 体系。 citeturn36view0turn17search0turn36view2turn36view3turn36view6turn36view5

更具体地回答你最关心的那句——**“为什么 CPU 参与是正收益，或者为什么可能反噬”**——可以归纳为一个很实用的判断式：

当下面四个条件同时满足时，CPU 参与通常是正收益：  
其一，子路径**低算术强度、低张量规则性、或存在 accelerator 不支持的 dtype/shape/op**；  
其二，CPU 处理的数据体积可控，**PCIe/同步/格式转换**不会超过其自身计算时间；  
其三，CPU 计算或 CPU 发起的数据移动能被 GPU/NPU 的 dense 计算**完全或大部分隐藏**；  
其四，调度器能限制 CPU 只在**边际收益为正**的时段介入。NEO、llm.npu、HeteroInfer、KTransformers 都是正例。 citeturn38view4turn39search3turn11search10turn21search3

而当下面三类情况出现时，CPU 很容易反噬：  
其一，decode 太短、batch 太小，GPU 还没忙起来，CPU 介入只增加同步；  
其二，状态粒度太细，导致 **tiny I/O、频繁 pin/unpin、碎片化 DMA**；  
其三，CPU 需要承担大块 dense matmul，而自身 SIMD/AMX 不足、内存带宽不够，或 host runtime overhead 过高。Tutti 对 tiny I/O 与 CPU 关键路径问题给了最强证明，HeteroInfer 与 Challenging GPU Dominance 也都表明“同步/传输成本完全可能压过 accelerator 获益”。 citeturn23search3turn11search10turn10search14

## 面向 Ascend NPU 加 Kunpeng CPU 小算力一体机的技术布局建议

**近期可做的软件/框架原型**，我建议按“最小可行、连续收敛”的路线来，而不是一上来就追求全栈创新。

第一步，优先做一个 **状态对象层原型**，直接建立在 **vLLM-Ascend + UCM + Mooncake** 之上，把 KV / Prefix / 多模态 embedding / expert metadata 统一成对象，先实现 **命名、版本、pin、热度、prefetch、restore、TTL、观测** 这几个最小接口。原因很简单：Ascend 生态里最接近你目标的现成支点已经公开存在，而不是从零开始。 citeturn33view0turn29view3turn33view2turn32view1

第二步，在这个对象层之上做 **阶段化原型**，但不要同时做八件事。建议从三个最有确定性的场景起步：  
其一，**Prefill/Decode 分离**，先在单机 NPU + CPU DRAM + 本地 SSD 上验证 TTFT 与 ITL 改善；  
其二，**冷/低频 expert fallback 到 Kunpeng**，把 CPU 当专家执行器和预取控制器，而非密集主算器；  
其三，**多模态 encoder / embedding cache 与语言主干解耦**，把 embedding 作为 first-class object。  
这些方向分别有 Mooncake、UCM、KTransformers、TokenCake、Mooncake EPD 的公开启发。 citeturn32view1turn29view3turn21search3turn14search1

第三步，尽快补一套 **收益判定与 profiling 工具**。不是为了发表 simulator 论文，而是为了避免做出“机制本身很好，但在你们机器上不赚钱”的原型。最少应统计：  
**HBM 占用、DRAM 带宽、PCIe/UB 方向流量、SSD IOPS/吞吐、CPU core/NUMA 占用、host runtime 时间、prefetch 命中率、restore stall 时间、P99 TTFT/ITL、能耗**。  
没有这套 profiler，你很难回答“为什么这次 CPU 参与赚钱，下次不赚钱”。KernelSight-LM、Kareto、Watt Counts、CCL-Bench 这几类工作都在说明：**先把证据采好，再谈机制**。 citeturn36view0turn17search0turn36view6turn36view5

**需要硬件接口支持的能力**，我建议聚焦六项：

其一，**更低开销的 NPU↔CPU 状态迁移接口**。最好支持 page/object 粒度 pin/unpin、批量 register、异步回调，而不是每个 tensor 都走重路径。没有这个，状态对象层会在 host runtime 上吃亏。参考 NIXL、Mooncake、vLLM connector 抽象。 citeturn29view4turn29view8turn32view1

其二，**NPU 或 DMA engine 对本地 SSD / 分布式存储的 direct path**。公开直接针对 NPU-SSD 的论文仍少，但 Tutti 已说明：**只要 I/O control plane 还卡在 CPU 上，SSD tiering 的收益会被 tiny I/O 与 host overhead 吃掉**。如果 Ascend 未来能给出更直接的 object/page I/O primitive，会非常有价值。 citeturn23search3

其三，**Kunpeng 侧的高效小矩阵 / 稀疏 / dequant / expert kernel**。KTransformers 之所以成立，很大程度依赖 AMX-specialized kernel；对 Kunpeng 来说，对应的 SIMD/SVE/矩阵扩展越强，CPU fallback expert 越能从“能跑”变成“值得跑”。 citeturn21search3turn26view3

其四，**更强的 host memory bandwidth 与 NUMA 可控性**。因为无论是 HiCache、UCM 还是本地 expert offload，CPU DRAM 都不再只是“普通系统内存”，而是活跃的 L2 状态层。没有足够 DRAM 带宽，CPU 只会从计算瓶颈变成内存瓶颈。 citeturn30view3turn29view3

其五，**图模式与异步流水的细粒度共存**。如果 NPU 图模式只能跑 monolithic graph，而不能容纳 PD/EPD、后台 prefetch、跨层 overlap，那阶段化协同很难工程化。vLLM-Ascend release notes 已说明其在 DeepSeek/DSA attention/KV cache 上持续补 graph 与 cache 能力，这条线值得持续跟。 citeturn33view1

其六，**硬件可见的状态遥测**。最好让 runtime 能比较低成本地知道：某对象位于 HBM/DRAM/SSD 哪一层，最近访问时间、迁移时长、恢复时长、I/O 队列积压、异步传输 outstanding 数量。这类透明度会大大降低调参成本。 citeturn31view1turn36view5

**下一代硬件应反推的规格**，如果你的目标是“Mini 工作站 / 塔式服务器 / 1–4 卡小服务器 / 2–8 节点小集群”，我会给出以下明确排序：

最先反推的是 **HBM 容量与 CPU DRAM 带宽的配比**，而不是单纯算力。因为公开系统反复表明，长上下文、MoE、agent、多模态的关键矛盾都首先落在状态容量与流动，而不是算子峰值。Beluga、ITME、LMCache、HiCache、UCM、Tutti 的共同结论都是：**状态层设计决定了上下文上限、并发上限与成本曲线**。 citeturn23search1turn23search0turn31view0turn30view0turn29view3turn23search3

第二优先级是 **CPU 核数与 SIMD/矩阵扩展能力**。如果目标含 DeepSeek/大 MoE，本地机绝不能把 CPU 当纯管理面。更现实的反推方式是：令 CPU 至少能承担**冷专家、部分 decode、outlier、小矩阵、dequant、embedding/rerank、codec/postprocess**；否则 CPU 总是在“会参与，但一参与就拖后腿”的尴尬区间。 citeturn21search3turn21search4turn20search3

第三优先级是 **本地 SSD 的带宽与 IOPS，而非只看顺序带宽**。Tutti 的结论已经很明确：KV reset/restore 的痛点往往来自碎片化随机 I/O 与 CPU 提交开销，不是标称 GB/s 不够。因此，如果未来硬件/固件能给 KV object 提供更友好的 page/object I/O path，会比单纯把 SSD 峰值翻倍更有意义。 citeturn23search3

第四优先级是 **NPU/GPU 与 CPU 的互联语义**。对本地一体机而言，能否以低 overhead 做 object/page 级 register、异步迁移、layout-aware transfer，往往比理论链路带宽数字更重要。Cronus、TensorRT-LLM、NIXL、HiCache 都在说明：**互联不是“够快”就行，还要“够好用”**。 citeturn25view7turn29view9turn29view4turn30view1

最后才是 **峰值计算与功耗预算**。原因不是它不重要，而是很多 decode 与状态管理场景早已 memory-bound。CCGrid 2026 那篇能效论文已经说明 decode 对频率不敏感；因此下一代规格评估应尽量从 **tokens/J、TTFT/W、ITL/W、恢复开销/W** 出发，而不是只看 TOPS。 citeturn36view3turn36view6

## 空白点、研究机会与参考文献

当前最明显的**空白点**有五个，而且都很适合转化成你的创新点。

第一，**NPU-SSD direct storage for KV / state object** 的公开高置信论文仍然很少。GPU 侧有 Tutti、Dual-Blade 一类工作，Ascend/NPU 侧更多还是 UCM/Mooncake 这类上层系统与文档，缺少“**NPU 原生 object I/O + 低 host-overhead 控制平面**”的正式体系论文。这意味着你们完全可以在 Ascend+Kunpeng 上做一条很新的系统线。 citeturn23search3turn8search4turn29view3turn33view2

第二，**专家对象化与 KV 对象化还没有被统一为一个通用状态层**。现在社区通常是把 KV、Expert、Embedding、Latent 分别优化，但真正适合本地小服务器的方向，也许是做一个统一的 **state object runtime**：同一 metadata、同一 pin/prefetch/evict/restore 语义，不同 state type 只是在代价模型上不同。公开系统已经给了拼图，但还没看到很完整的统一框架。 citeturn31view0turn25view3turn21search1turn32view1

第三，**面向小算力机型的收益判定模型仍不够“可落地”**。KernelSight-LM、Kareto、LIFE 都很好，但大多还没形成“拿到一台新机器，输入几项规格和少量 microbenchmark，就能告诉你 CPU fallback / KV tiering / expert prefetch 是否赚钱”的成品路线。这个空白非常适合做成你所说的“规格反推”卖点。 citeturn36view0turn17search0turn36view2

第四，**多模态/视频生成 side state 的系统化研究明显落后于 LLM KV**。公开论文开始讨论 latent pause/resume、扩散阶段拆分与视频 KV/缓存，但还没有像 LMCache/Mooncake 那样成熟的“latent / Noise Cache / rolling state 对象层 + 分层回流 + 编解码重叠”的标准答案。你在这个方向上做工程化提炼，命中率会很高。 citeturn13search5turn13search2turn12search3turn12search10

第五，**Ascend+Kunpeng 的公开系统资料虽然快速丰富，但学术级公开证据仍少于 CUDA 生态**。这既是风险，也是机会。风险在于很多结论要做迁移假设；机会在于只要你把“迁移假设、收益边界、接口缺口”讲清楚，就很容易形成差异化系统创新。 citeturn33view0turn33view1turn29view3turn34search1

本报告最后给出一份**高价值参考条目清单**，优先级按“对你当前问题最有用”排序，而不是按时间排序：

**最值得先读的正式论文/系统论文**：  
LMCache、MOONCAKE、NEO、KTransformers、KVCache Cache in the Wild、FineMoE、Beluga、Understanding Diffusion Model Serving in Production。 citeturn31view0turn32view0turn25view1turn21search3turn16search0turn25view3turn23search1turn13search0

**最值得先看实现的工程框架文档**：  
vLLM Automatic Prefix Caching、vLLM Disaggregated Prefilling、vLLM NixlConnector、SGLang HiCache、TensorRT-LLM KV Cache Reuse / Disaggregated Serving、Dynamo/NIXL、vLLM-Ascend UCM、Mooncake x vLLM / SGLang / Ascend 文档。 citeturn29view6turn24search1turn29view8turn30view0turn19search2turn16search21turn29view9turn29view4turn29view3turn32view1

**最值得用来写“收益边界与规格反推”的论文**：  
KernelSight-LM、Kareto、LIFE、Characterizing LLM Inference Energy-Performance Tradeoffs、Watt Counts、CCL-Bench。 citeturn36view0turn17search0turn36view2turn36view3turn36view6turn36view5

**最值得用来写“Agent / workflow-aware serving”一页的论文**：  
KVFlow、TokenCake、Continuum、PBKV。 citeturn14search3turn14search1turn15search0turn14search4

**最值得用来写“本地 MoE 异构协同”一页的论文**：  
KTransformers、HybriMoE、FineMoE、FluxMoE、FloE、DuoServe-MoE。 citeturn21search3turn21search4turn25view3turn21search1turn20search3turn20search6

**开放问题与局限**：  
一，用户给出的检索范围延伸到 **2026-12-31**，但当前日期为 **2026-06-30**，因此报告只能覆盖此日前公开信息；  
二，部分 2025–2026 条目仍是 arXiv/OpenReview/官方文档，尚未完成同行评审或公开 artifact 细节；  
三，Ascend+Kunpeng 的公开细节少于 NVIDIA/CUDA 生态，所以本报告对 Ascend 的部分建议属于“**高可迁移假设**”而非“已有论文直接证明”；  
四，关于 **Noise Cache / rolling KV for video generation**、**NPU-SSD direct storage** 的直接论文仍少，后文建议因此带有更强的研究推断成分。 citeturn12search3turn23search3turn33view0turn34search1