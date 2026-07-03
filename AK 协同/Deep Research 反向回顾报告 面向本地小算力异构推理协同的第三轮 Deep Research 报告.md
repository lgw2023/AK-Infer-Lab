# 面向本地小算力异构推理协同的研究问题与技术路线深度报告

## 执行摘要

截至 **2026 年 7 月 1 日**，这一方向最明显的变化不是“又出现了一个更快 kernel”，而是**推理系统的研究对象正在从单个模型执行器，转成“计算路径 + 状态对象 + 分层存储 + 调度器 + 数据搬运面”的联合系统**。2025–2026 年最强的一批论文和框架，几乎都在围绕这五个面做重构。citeturn36search3turn15search2turn15search17turn37search0turn37search1

第一，**CPU 不再只是 host/control plane**。在强相关工作里，CPU 已经重新承担了四类明确角色：状态管理面、I/O 聚合面、warm-tier memory、以及模型内的选择性计算面。NEO、FlexInfer、LIA、KTransformers、HybriMoE 分别把 CPU 拉进 attention、短矩阵/小粒度算子、专家计算、prefetch 与 metadata orchestration；但这些收益都建立在**“算子低算强比、状态可留在 CPU 侧、搬运可与 GPU/NPU 主路径重叠”**这三个前提上。citeturn14search3turn35search0turn34search1turn8search1turn8search9

第二，**KV / Prefix / Context 正在被系统层“对象化”**。Mooncake、LMCache、SGLang HiCache、vLLM NixlConnector、TensorRT-LLM KV reuse、Ascend UCM 都不再把 KV 当成 engine-private tensor，而是把它做成可命名、可持久化、可跨实例转移、可分层 pin/evict 的对象；这使得 prefix reuse、P/D 拆分、状态外部化、shared cache routing 和 observability 成为同一个问题。citeturn15search2turn37search0turn20search17turn21search18turn37search12turn22search1

第三，**HBM/DRAM/CXL/SSD/remote store 的问题已经从“能不能 offload”变成“对象布局与数据路径怎么设计”**。Beluga、ITME、Tutti、Kareto、KV stores/LSM 系统这些工作共同表明：收益不再主要取决于“设备带宽标称值”，而更取决于**对象粒度、元数据路径、是否存在 CPU bounce buffer、是否能批量化/顺序化 I/O、恢复是否能与计算重叠**。这也是为什么 CXL 与 SSD-backed KV 在 2025–2026 年都出现了明显分化：有人拿到大收益，也有人明确指出 tiny I/O 与控制面开销会把收益吃掉。citeturn8search3turn8search8turn28search1turn30search0turn28search0

第四，**MoE 正在从“路由算法问题”转成“专家对象管理问题”**。KTransformers、HybriMoE、MoE-Lightning、CommitMoE 与相关论文的共同点，是不再把 expert 只看成静态权重，而是把它看成有热度、有 miss penalty、有 prefetch depth、有 CPU/GPU 位置选择的“可管理对象”。这对本地小算力场景尤其关键，因为专家常驻 HBM 的预算本来就不够。citeturn8search1turn8search9turn7search15turn24search1

第五，**P/D 与 E/P/D 拆分已经从云端大集群概念扩展到单机工作站、小集群与多模态场景**。DistServe 奠定了 P/D 作为系统原语的地位；随后 Mooncake、vLLM、Dynamo/NIXL、TensorRT-LLM 把它工程化；ModServe、EPDServe、HydraInfer 则把这一思想扩展到 multimodal encode/prefill/decode。趋势非常清晰：**阶段拆分正在从“资源池分离”走向“状态连接器标准化”**。citeturn9search0turn15search2turn21search18turn9search20turn26search1turn26search0turn26search2

第六，**Agent serving 改变了 KV 生命周期的时间结构**。KVFlow、Continuum、PBKV、Tokencake 这批工作说明：一旦 workload 里出现 tools、workflow DAG、agent step graph、tool idle window，传统 LRU 与单轮对话式 prefix cache 就不够了。系统目标也会从 TTFT/TPOT 扩展到 JCT、workflow SLO、step-level continuation。citeturn10search0turn10search13turn10search7turn10search1

第七，**多模态/视频方向已经开始系统化，但“latent / Noise Cache / rolling KV 的系统级对象化与分层回流”仍未收敛**。SoCC’25 的 diffusion serving 生产分析、GenServe、DisagFusion、HydraInfer、EPDServe 已经把多阶段 pipeline、异构设备放置、SLO-aware scheduling 做出来了；但 TeaCache、FasterCache、FlowCache 更多还是算法/推理复用层，尚未形成像 Mooncake/LMCache 那样成熟的“外部状态对象层”。这是一个真实空白。citeturn11search0turn11search1turn26search3turn26search2turn26search0turn11search17turn11search9turn27search10

第八，**收益边界判断正在迅速专业化**。ServeGen、ProfInfer、KernelSight-LM、Kareto、TokenPowerBench、Chakra 代表了一条很重要的路线：不是再凭直觉说“CPU 参与可能有用”，而是用 production trace、eBPF timeline、kernel-level simulator、能耗 benchmark、Pareto-style storage tuner 去回答“什么时候赚钱、什么时候反噬、硬件规格应该怎么反推”。citeturn13search16turn12search2turn12search0turn30search0turn13search3turn13search9

第九，**公开的 Ascend + Kunpeng 学术系统论文仍然稀缺，公开证据主要来自框架文档与生态集成**。这意味着该方向在学术论文层面的直接证据薄弱，但工程链条并非空白：MindIE、vLLM-Ascend、UCM、Mooncake on Ascend 已经公开了 prefix cache、external KV、PD-colocated/PD transfer、tiered KV 的若干能力，因此“可迁移原型”是可以立即做的，只是**论文证据链需要更多可发表的系统化实验**。citeturn22search0turn22search11turn22search1turn22search13turn22search16

第十，**对本地小算力一体机最值得吸收的不是单点加速，而是三条技术路线**：其一，阶段化异构协同计算；其二，状态对象化与分层回流；其三，收益判定与规格反推。前两条已经有较多工程证据，第三条仍然是高价值空白。citeturn14search3turn15search2turn8search3turn28search1turn13search16turn12search0turn30search0

## 研究问题地图

### CPU 在推理系统中的角色重排

2025–2026 年的证据显示，CPU 至少被重新定义为五种角色。其一是 **host/control plane**，这仍然存在于多数框架中；其二是 **state manager / metadata plane**，负责 KV page、prefix tree、restore/prefetch 元数据；其三是 **warm memory tier**，承担 DRAM 缓冲与 staging；其四是 **I/O aggregator**，负责 KV/expert/adapter 的聚合式搬运；其五才是 **selective compute device**，只在 attention、短序列矩阵、小专家、outlier block 或小粒度 fallback 上进入模型内计算路径。NEO、FlexInfer、LIA、KTransformers 和 HybriMoE 都是第五类的代表，但它们的共同点不是“CPU 什么都算”，而是**只算 GPU/NPU 不值得算的一小段**。citeturn14search3turn35search0turn34search1turn8search1turn8search9

这也解释了为什么“CPU 参与”为正收益时通常发生在三类区间：第一，算子本身偏 memory-bound、算强比低、且无须反复搬运大权重；第二，状态本来就留在 CPU/DRAM/SSD 一侧，CPU 计算可避免来回 PCIe/CXL 往返；第三，CPU 计算能与 GPU/NPU 主干并行，从而形成 pipeline overlap。反过来，如果 CPU 计算需要高频小块搬运、频繁同步、layout transform、或受限于 DDR 带宽与 SIMD 吞吐，那么收益就会被互联与 control overhead 吃掉。NEO、LIA 与 on-device CPU-vs-GPU 研究都直接支持这一判断。citeturn14search3turn34search1turn34search0

### 状态对象化为何成为主线

Mooncake、LMCache、HiCache、NixlConnector、UCM、TensorRT-LLM KV reuse 共同指向一个技术收敛：**KV 不再只是运行时临时张量，而是系统级状态对象**。一旦 KV 被对象化，系统会自然拥有对象名称、对象位置、对象热度、对象 TTL、对象压缩格式、对象迁移/恢复 API，以及对应的路由与观测接口。Mooncake 把 KV store 外部化并与 prefill/decode 解耦；LMCache 明确提出把 KV 从“temporary state”变成可持久化与跨 engine 复用的“AI-native knowledge”；HiCache 和 UCM 把 GPU/host/external backend 做成分层 cache；vLLM 的 NixlConnector 与 TensorRT-LLM 的 KV exchange 则把阶段间状态传输做成明确连接器与协议。citeturn15search2turn37search0turn20search17turn22search1turn21search18turn37search5

这类对象化最重要的系统后果有四个。第一，**调度目标变了**：调度器不再只分配 request，而是要决定“哪个 worker 已经命中哪个状态对象”。第二，**存储问题显性化**：对象大小、布局、冷热分层、持久化策略成为一等问题。第三，**恢复与容错变成基础设施能力**：状态能否在进程、节点、阶段之间恢复，会直接决定 P/D、agent、multi-instance 的有效性。第四，**观测与安全也被抬出来了**：当 KV 可复用、可共享、可跨 tenant 流动时，缓存污染、泄漏和隔离会变成系统设计问题，而不是“附加问题”。这正是 2025–2026 年从论文到工业文档同时出现的变化。citeturn15search17turn10search19turn37search0turn22search1

### 分层内存如何改变系统设计

Beluga、ITME、Tutti、Kareto 与 KV-stores/LSM 这组工作给出了一个比“HBM 很快、SSD 很慢”更细的视角。它们共同表明：**热层是否真的热，不由介质命名决定，而由访问粒度、控制路径、对象布局、恢复可并行度决定**。CXL memory 在 Beluga 与 ITME 中被用作大容量、低编程复杂度、近 load/store 语义的共享池或扩展池，适合放大容量并减少 RDMA-style software overhead；但 Kareto 之类工作又说明，最终性能收益很依赖 workload access pattern 与 tier 配置，不能把 CXL 想象成“便宜版 HBM”。citeturn8search3turn8search8turn30search0

SSD/NVMe 的趋势更值得注意。Tutti 直接把问题挑明：即使有 GDS/Direct Storage，如果对象仍是碎片化 page、I/O 仍是 tiny random access、每次 I/O 仍要靠 CPU 发起与控制，那么 SSD 很容易只带来“账面容量”，却带不来“系统吞吐”。与之相对，Mooncake、LMCache、HiCache、SGLANG-LSM 则都在想办法把 KV 做成可批量、可顺序、可对象化的外部存储，因此真正的议题是 **object/page layout + batch I/O + connector/runtime 协议**，而不是“有没有 NVMe”。citeturn28search1turn15search2turn37search4turn20search17turn28search0

### MoE 与阶段拆分为何更适合本地小算力

MoE 的问题在本地场景被放大，因为单机 1–4 卡通常不可能让全部 experts 常驻 HBM。KTransformers、HybriMoE、MoE-Lightning、CommitMoE 说明，**专家管理**已经成为一个独立层面：它既是内存问题，也是调度问题，还是 CPU/GPU 分工问题。对于小机器，最关键的不是“怎么把每个专家算得更快”，而是“哪些专家热、应该常驻哪一层、什么时候预取、miss 了是否让 CPU 兜底”。citeturn8search1turn8search9turn7search15turn24search1

阶段拆分也是同理。DistServe 证明 P/D 拆分本身能够提升 goodput；Mooncake、TensorRT-LLM、Dynamo/vLLM 把状态交换与路由工程化；ModServe、EPDServe、HydraInfer 则说明一旦进入 multimodal，单纯的“prefill/decode”已经不够，需要 encode/prefill/decode 三级，甚至更多 stage。对小算力场景，这条路线的研究意义不在于拿来“照搬云架构”，而在于它揭示了**不同阶段的资源画像完全不同**：prefill 更偏算力，decode 更偏状态容量与带宽，encode/vision/codec/VAE 又有各自的资源指纹。citeturn9search0turn15search2turn37search5turn21search4turn26search1turn26search0turn26search2

### Agent 与多模态将问题从“单请求”变成“状态生存期”

KVFlow、Continuum、PBKV、Tokencake 的共同点，是把 workload 从单轮 request 链接到 workflow graph。这样一来，“最近最少使用”会失效，因为一个看似 idle 的 agent session 可能马上要从 tool call 返回；一份看似冷的 KV 也可能是 workflow 下一步的关键前缀。Agent serving 的研究焦点因此从 prefix hit rate 向 **JCT、tool-aware TTL、prediction-based prefetch、step-aware eviction** 转移。citeturn10search0turn10search13turn10search7turn10search1

多模态与视频方向则把问题进一步推向“类型异构”。SoCC’25 的 diffusion serving 生产研究、GenServe、DisagFusion、HydraInfer 和 EPDServe 共同证明：text encoder、vision encoder、DiT/U-Net 主干、VAE decode、codec/post-process 并不是同构算子流，而是不同硬件偏好的 stage。与此同时，TeaCache、FasterCache、FlowCache 说明 latent/noise/flow 这一类“非 LLM-KV 状态”已经有大量可复用信号，但当前公开系统论文还很少把它们提升为可迁移、可 pin、可 tiering 的系统对象。citeturn11search0turn11search1turn26search3turn26search2turn26search0turn11search17turn11search9turn27search10

## 逐会议查缺补漏表

下面的表不是“全会议所有论文”，而是按用户问题域，对 **official proceedings / program / OpenReview / 官方文档** 做面向强相关主题的检索结论。由于当前日期为 **2026-07-01**，不少 **2026 下半年会议** 尚未公开完整接收结果或程序，因此对这些会议统一保留“需人工复核”的标记。citeturn25search0turn25search1turn25search2turn15search0

| 会议 | 强相关论文 | 中相关论文 | 结论 | 官方来源 |
|---|---|---|---|---|
| ICLR 2025 | 未发现直接聚焦 GPU/NPU+CPU+HBM/DRAM/SSD 协同的强相关论文 | SwiftKV、若干 KV/sparse long-context 工作 | 以算法/稀疏/压缩为主，系统级异构协同不强。citeturn14search0 | OpenReview ICLR 2025/论文页 |
| ICLR 2026 | 未确认强相关已正式接收 | Cronus 当前可见为 ICLR 2026 submission；其余需后续复核 | 截至 2026-07-01，仍应视为“submission/需人工复核”。citeturn25search0turn31search11 | OpenReview ICLR 2026 |
| AAAI 2025 | 未发现强相关系统论文 | 少量 KV/长上下文优化 | 强相关不足。 | AAAI 官方检索结果 |
| AAAI 2026 | Async KV prefetch；CommitMoE 可视为中到强相关 | SlimInfer、Lethe、多-context KV | AAAI 2026 有若干与 KV/专家/预取相关条目，但多数偏模型/单设备优化，系统层不如 MLSys/USENIX/SOSP 强。citeturn24search0turn24search1turn24search2turn24search9 | AAAI-26 proceedings |
| ICML 2025 | 未发现强相关“系统-异构协同”主论文 | 若干长上下文与模型高效推理论文 | 强相关不足。citeturn23search0 | ICML 2025 proceedings |
| ICML 2026 | 程序临近会期，但本主题强相关公开证据未形成集中列表 | 需人工复核 | 官方会期已到，但截至 2026-07-01 本主题公开检索结果仍分散。citeturn25search2 | ICML 2026 官方站 |
| NeurIPS 2025 | KVFlow | Test-Time Memory、GenCache、MoE-CAP 等 | NeurIPS 2025 在 agent-aware KV 生命周期和 cache reuse 上有实质进展，但 GPU/CPU/storage 协同仍不是主战场。citeturn14search2turn14search9turn14search14turn14search20 | NeurIPS 2025 proceedings |
| NeurIPS 2026 | 尚未通知接收 | 需人工复核 | 2026 论文通知要到 9 月。citeturn25search1turn25search9 | NeurIPS 2026 CFP |
| MLSys 2025 | NEO、FlexInfer、Marconi | SampleAttention 等 | 这是 2025 年最密集的强相关来源之一，覆盖 CPU 参与计算、prefix caching、serving state 管理。citeturn36search3turn35search15turn19search1 | MLSys 2025 proceedings/OpenReview |
| MLSys 2026 | KernelSight-LM、TriInfer/相关 multimodal serving、若干 video/diffusion serving 工作需后续统一核验 | StreamDiffusionV2 等 | 2026 的 MLSys 主题明显向 multimodal/video/simulator 扩张，但部分条目当前更容易在 arXiv/项目页上看到，正式会议信息需后续统一复核。citeturn12search0turn26search9 | MLSys/OpenReview+项目页 |
| OSDI 2025 | 无新增同量级强相关超越 DistServe/Mooncake 的公开证据 | 若干相关系统引用 DistServe/Mooncake | OSDI 2025 本主题并未像 2024/FAST’25 那样形成代表作。citeturn15search20turn15search24 | USENIX OSDI |
| OSDI 2026 | 尚未到会期 | 需人工复核 | 会期 2026-07-13 至 15。citeturn15search0 | OSDI 2026 |
| SOSP 2025 | KTransformers、HeteroInfer、Jenga | 其他 LLM serving/heterogeneity 工作 | SOSP 2025 是异构协同与状态管理最关键的一届之一。citeturn15search23turn32search21turn18search3 | ACM SOSP 2025 proceedings |
| NSDI 2025 | 未发现强相关 | 中相关有限 | 本主题不集中。 | USENIX NSDI 2025 |
| NSDI 2026 | ServeGen、JITServe、DroidSpeak 可视为中到强相关 | 其余 serving/SLO 工作 | NSDI 2026 明显加强了 trace/workload/serving state 研究，但更偏 workload & serving 特征层。citeturn15search1turn27search20turn15search28 | NSDI 2026 technical sessions |
| USENIX ATC 2025 | KVCache Cache in the Wild、Weaver、Toppings | CLONE、QFactory 等 | ATC 2025 是 cache 生命周期、attention offloading、CPU-assisted adapter serving 的高密度来源。citeturn16search0turn17search0turn16search7turn17search9 | USENIX ATC 2025 |
| USENIX ATC 2026 | 未检到同量级强相关集中成果 | 需人工复核 | 公开材料仍分散。 | USENIX ATC |
| FAST 2025 | Mooncake | — | FAST 2025 是“KVCache-centric architecture”最关键的会议来源。citeturn15search2turn15search21 | FAST 2025 |
| FAST 2026 | Bidaw、CacheSlide 为中相关 | — | 更偏 cache/reuse 改进；分层协同思想仍相关，但不如 Mooncake 直接。citeturn15search25turn15search31 | FAST 2026 |
| EuroSys 2025 | CacheBlend | HCache 可作相关背景 | EuroSys 2025 在 RAG/prefix reuse 与 state restoration 上有直接价值。citeturn28search8turn28search7 | ACM/论文页 |
| EuroSys 2026 | 尚未形成可核验强相关全集 | 需人工复核 | 截至 2026-07-01 公开信息不足。 | EuroSys 官方 |
| SoCC 2025 | ModServe、Understanding Diffusion Model Serving in Production、Oneiros、DyOrc | — | SoCC 2025 是 multimodal serving 与 KV/parameter-memory 重构的重要来源。citeturn26search6turn11search0turn30search3turn15search8 | SoCC 2025 proceedings |
| SoCC 2026 | Kareto 所在 arXiv 工作与未来论文映射需人工复核 | — | 2026 公开论文尚未统一。citeturn30search0 | ACM/预印本 |
| Middleware 2025/2026 | 未发现强相关集中代表作 | 少量 serving/edge 论文需后续补查 | 当前证据不强。 | 需人工复核 |
| ASPLOS 2025 | llm.npu、MoE-Lightning、AiF、LIA 可作为体系结构/异构支撑组 | — | 这是 on-device NPU、MoE on memory-constrained GPU、CPU+AMX 支撑的重要来源。citeturn33search0turn7search15turn33search19turn34search1 | ASPLOS 2025 |
| ASPLOS 2026 | 公开结果分散 | 需人工复核 | 以 2026 论文与二次引用为主。citeturn33search3 | ACM |
| ISCA 2025 | LIA | — | 对 CPU+GPU+AMX+CXL 的启发很直接。citeturn34search1 | ACM/ISCA 2025 |
| ISCA 2026 / MICRO 2025 / MICRO 2026 / HPCA 2025 / HPCA 2026 / SC 2025 / SC 2026 | 未发现已公开且与本题高度直接的集中成果 | 若干 poster / architecture 侧参考 | 当前公开证据更分散，需人工复核。 | 各会议 proceedings |
| SIGMOD / VLDB / CIDR 2025–2026 | Kareto、KV-store/LSM external KV 属强相关预印本/数据系统路线 | 一些 workflow/cache/storage 论文 | 数据系统方向的核心贡献主要体现在 external KV、KV-store layout、tier tuning，而非模型本身。citeturn30search0turn28search0 | arXiv/数据系统路线 |
| MobiSys / SenSys / SEC / IoTDI 2025–2026 | llm.npu、HeteroLLM/HeteroInfer、CPU-vs-GPU on-device | 边缘部署/安全/能耗 | 端侧异构协同的重要来源之一，但公开条目更多以 arXiv/ASPLOS/SOSP/行业实现呈现。citeturn33search1turn32search3turn34search0 | 论文页/项目页 |
| CAIS 2026 / Agentic workshops | Continuum、PBKV、Pythia、Tokencake 等更多以 arXiv/OpenReview 出现 | — | Agent serving 的强作品目前主要还在预印本和 OpenReview。citeturn10search3turn10search7turn10search4turn10search1 | OpenReview/arXiv |

## 强相关论文总表

下表只列我认为对你研究主题最有“机制含量”的强相关核心条目；不把纯 kernel、纯量化、纯 speculative、纯 agent orchestration 强行塞进来。

| 方向 | 论文/系统 | 来源 | 状态 | 为什么强相关 | 可靠性 |
|---|---|---|---|---|---|
| CPU/GPU 协同 | NEO | MLSys 2025 | 正式发表 | CPU 直接承担部分 decode attention 与 KV 驻留，解决 online serving 的 GPU memory crisis。citeturn36search3turn14search3 | A |
| CPU/GPU 协同 | FlexInfer | MLSys 2025 | 正式发表 | 明确研究“CPU computations”作为灵活 offload 维度。citeturn35search15turn35search9 | B |
| CPU/GPU/CXL | LIA | ISCA 2025 | 正式发表 | cooperative AMX-enabled CPU-GPU + CXL offloading。citeturn34search1 | B |
| On-device NPU | llm.npu | ASPLOS 2025 | 正式发表 | 以 NPU 为 prefill 主力，并显式安排 CPU/GPU 处理 outlier 与 block affinity。citeturn33search0turn33search1 | A |
| Mobile heterogeneous | HeteroLLM | arXiv 2025 | 预印本 | 统一内存 SoC 上的 GPU+NPU tensor/layer 异构执行。citeturn32search3 | C |
| Mobile heterogeneous | HeteroInfer | SOSP 2025 | 正式发表 | 移动 SoC 异构处理单元上的高速 LLM inference。citeturn32search0turn32search21 | B |
| State object / external KV | Mooncake | FAST 2025 | 正式发表 | KVCache-centric architecture；CPU/DRAM/SSD/NIC 组成外部 KV 层。citeturn15search2turn15search7 | A |
| State object / KV layer | LMCache | arXiv + docs 2025 | 预印本 + 开源系统 | 明确把 KV 从临时状态变成可持久化、可观测、可跨 engine 共享的层。citeturn37search0turn37search4turn22search14 | C/D |
| GPU memory manager | Jenga | SOSP 2025 | 正式发表 | heterogeneous embeddings / layer-specific eviction，把 state 管理推进到 allocator 层。citeturn18search3turn18search6 | A |
| KV trace / eviction | KVCache Cache in the Wild | USENIX ATC 2025 | 正式发表 | 真实云 traces 上的 KV 生命周期与 workload-aware eviction。citeturn16search0turn16search2 | A |
| CXL tiering | Beluga | ACM TECS 2026 + arXiv 2025 | 正式发表 + 预印本 | GPU/CPU 通过 CXL switch 直接访问 pooled memory 做 KV 管理。citeturn8search7turn8search3 | B |
| CXL-hybrid memory | ITME | arXiv 2026 | 预印本 | 把 agentic/long-context shared context 扩展到 CXL-hybrid disaggregated memory。citeturn8search8 | C |
| SSD-backed KV | Tutti | arXiv 2026 | 预印本 | GPU-centric HBM-SSD object store，目标就是去掉 CPU 干预。citeturn28search1 | C |
| Expert object | KTransformers | SOSP 2025 | 正式发表 | CPU/GPU hybrid MoE inference，AMX kernels + async scheduling + expert 管理。citeturn15search23turn8search1 | B |
| Expert object | HybriMoE | arXiv / DAC 2025 | 预印本/正式发表版本待核验 | 动态 intra-layer scheduling + inter-layer prefetch + score-based caching。citeturn8search9turn15search14 | C/B |
| MoE serving | MoE-Lightning | ASPLOS 2025 | 正式发表 | memory-constrained GPU 上的高吞吐 MoE inference。citeturn7search15 | B |
| P/D disaggregation | DistServe | OSDI 2024 | 正式发表 | 虽早于 2025，但仍是 2025–2026 全部工业实现的直接技术源头。citeturn9search0 | A |
| P/D on heterogeneous GPUs | Cronus | arXiv 2025 / ICLR 2026 submission | 预印本 | partial disaggregated prefill，面向异构 GPU 组合。citeturn31search0turn31search11 | C |
| E/P/D multimodal | EPDServe | OpenReview / 代码 2025 | OpenReview + 开源 | 把 multimodal serving 明确拆成 Encode/Prefill/Decode 三段。citeturn26search0turn11search11 | C/D |
| Multimodal disaggregation | ModServe | SoCC 2025 | 正式发表 | modality- and stage-aware disaggregation for LMM serving。citeturn26search6turn26search15 | B |
| Multimodal E/P/D | HydraInfer | arXiv 2025 | 预印本 | Hybrid EPD disaggregation，显式建模 stage heterogeneity。citeturn26search2 | C |
| Agent-aware KV life cycle | KVFlow | NeurIPS 2025 | 正式发表 | workflow-aware eviction + background prefetch。citeturn14search2turn10search0 | A |
| Agent-aware KV life cycle | Continuum | arXiv/OpenReview 2025–2026 | 预印本 / OpenReview | tool-aware TTL + program-level scheduling。citeturn10search13turn10search3 | C |
| Agent-aware KV life cycle | PBKV | arXiv 2026 | 预印本 | prediction-based cache reuse value for dynamic workflows。citeturn10search7 | C |
| Agent-aware KV life cycle | Tokencake | arXiv 2025 | 预印本 | KV-cache-centric serving framework for multi-agent apps。citeturn10search1turn10search11 | C |
| Diffusion serving | Understanding Diffusion Model Serving in Production | SoCC 2025 | 正式发表 | 生产视角分析 workload、scheduling、heterogeneous memory。citeturn11search0turn11search5 | B |
| Diffusion co-serving | GenServe | arXiv 2026 | 预印本 | heterogeneous T2I/T2V diffusion co-serving。citeturn11search1turn11search6 | C |
| Diffusion disaggregation | DisagFusion | arXiv 2026 | 预印本 | async pipeline parallelism + elastic scheduling。citeturn26search3 | C |
| Trace / workload | ServeGen | NSDI 2026 | 正式发表 | 真实 serving traces + workload generation。citeturn13search16turn15search1 | A |
| Profiler | ProfInfer | arXiv 2026 | 预印本 | eBPF-based fine-grained inference profiler。citeturn12search2 | C |
| Simulator | KernelSight-LM | arXiv 2026 | 预印本 | token-level discrete-event + kernel-level roofline simulator。citeturn12search0 | C |
| Cost model / tier tuning | Kareto | arXiv 2026 | 预印本 | 用高保真 simulator 反推 tiered KV 配置 Pareto frontier。citeturn30search0 | C |
| Energy benchmark | TokenPowerBench | AAAI 2026 | 正式发表 | phase-aligned 能耗 benchmark，支持 prefill/decode energy attribution。citeturn13search13turn13search3 | B |
| Trace ecosystem | Chakra | arXiv/MLCommons 2026 | 官方生态/预印本 | 标准化 AI trace 与 co-design 生态。citeturn13search9turn13search19 | D |

## 分方向详细分析

### CPU/GPU 或 CPU/NPU 协同推理执行

这一方向真正研究的不是“把 GPU 算不下的东西搬给 CPU”，而是**哪些子路径天然更适合 CPU/NPU/GPU 异构放置**。从现有论文看，最常见的切入点有四类：其一，decode attention 或 memory-bound token-path；其二，NPU 对固定形状大矩阵友好而对异常值、动态 shape 不友好，因此把 outlier/irregular block 留给 CPU/GPU；其三，MoE 小专家、低频专家、fallback expert；其四，短矩阵、索引/预测/候选选择这类“管理型计算”。citeturn14search3turn33search1turn8search1turn8search9

**NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference**。机构为 Harvard / UC Berkeley，来源 MLSys 2025，正式发表。它要解决的问题不是离线大 batch 吞吐，而是 **online serving 下显存限制导致 batch size 上不去**。核心贡献是只把 **decode attention 及其 KV** 选一部分请求 offload 到本地 CPU，而不是整层 swap；机制层面包括 **asymmetric GPU-CPU pipelining** 与 **load-aware scheduling**。CPU 角色同时是 attention compute、state manager 与 warm-tier memory；数据驻留层级是 GPU HBM + CPU DRAM；关键数据路径是 GPU ↔ CPU，经主机内存往返，但通过仅 offload 对 attention 相关的状态与计算，避免反复搬回整层权重。论文摘要与论文页明确强调，它的目标是在不显著恶化延迟的前提下提高 online throughput；这正说明 CPU 参与只在 **低算强比 + 可与 GPU 主路径重叠** 时才有价值。公开摘要没有暴露一个可跨实验复述的单一 headline 数字，因此具体提升幅度仍建议直接查 MLSys 正文表格。对 Ascend + Kunpeng 的可迁移性我评为 **中**：思路高度可迁移，但需要 NPU runtime 暴露 attention/KV 的切分点和跨设备流水化 hook。可靠性为 **A**。citeturn36search1turn14search3turn36search3

**FlexInfer: Flexible LLM Inference with CPU Computations**。Georgia Tech 等，MLSys 2025，正式发表。它的关键词是 “flexible”，本质上是在问：**CPU 计算份额能不能成为一个连续可调的资源维度**，而不是二元的“offload / 不 offload”。从公开摘要和项目页可见，它明确把 CPU computations 本身作为设计主轴；虽然我没有在公开摘要中抓到统一 headline speedup，但从会议状态与论文主题判断，它是 2025 年最直接讨论“CPU 进入模型内算子路径”的正式论文之一。对你的研究最有价值的不是某个数字，而是它把 CPU 从“容量扩展器”推进成“可调度算力池”。对 Ascend + Kunpeng 的迁移性为 **中到高**：如果 Kunpeng 的 SIMD/SVE 与 NPU runtime 能提供稳定的张量分块与异步调度接口，这一路线天然可复用。可靠性为 **B**。citeturn35search0turn35search9turn35search15

**LIA: A Single-GPU LLM Inference Acceleration with Cooperative AMX-Enabled CPU-GPU Computation and CXL Offloading**。ISCA 2025 正式论文。它的重要性在于把 **CPU 参与计算**、**AMX** 与 **CXL offloading** 放到同一篇系统里，直接回答了“CPU 参与什么时候值得做”的硬件条件问题。公开摘要明确写到 cooperative **AMX-enabled CPU-GPU computation** 与 **CXL offloading**，这说明 LIA 并不把 CPU 仅看成 DRAM 容量，而是把带矩阵扩展单元的 CPU 当成真正的协同算力。你如果要给小算力一体机反推规格，这篇论文最重要的启发是：**没有 AMX/SVE/高带宽 DDR 的 CPU fallback，通常很难成为稳定正收益路径**。对 Ascend + Kunpeng 的迁移性为 **中**：机制成立，但需要确认 Kunpeng 的矩阵/向量扩展与 CXL/Unified Memory 路径能否提供相近的 host-side compute economics。可靠性为 **B**。citeturn34search1

**Fast On-device LLM Inference with NPUs**。北京邮电大学/北京大学等，ASPLOS 2025，正式论文，系统名通常写作 **llm.npu**。这是 2025 年端侧异构协同里最强的一篇，因为它明确不是“把整模扔给 NPU”，而是三层次重构：prompt-level chunking、tensor-level outlier extraction、block-level out-of-order scheduling，让 **NPU 负责高吞吐固定形状路径，CPU/GPU 并行处理 outlier 与不适配块**。论文报告平均 **22.4× prefill speedup**、**30.7× energy saving**、端到端应用最高 **32.8×**，并首次让 billion-scale 模型在移动端达到 **1000+ tokens/s 的 prefilling**。这直接证明：在 NPU 场景里，CPU/GPU 的价值往往不是主生成路径，而是**处理 NPU 不擅长的异类张量与调度边角料**。对 Ascend + Kunpeng 的迁移性为 **高**：因为 Ascend NPU + Kunpeng CPU 的生态本来就接近“加速器主干 + CPU 处理不规则路径”的范式；但需要 CANN/MindIE/vLLM-Ascend 暴露 block assignment、outlier branch 与跨设备事件同步。可靠性为 **A**。citeturn33search0turn33search1turn33search2

**HeteroLLM / HeteroInfer**。前者是 2025 arXiv 预印本，后者是 SOSP 2025 正式论文，机构来自 SJTU / Tsinghua / SenseTime 等团队。两者共同研究 **mobile SoC 上 GPU+NPU+unified memory 的异构推理**。HeteroLLM 公开报告相对 MLC 和 MNN 分别达到 **9.99×** 与 **4.36×** 的性能提升；HeteroInfer 的公开材料则强调它在移动 SoC 上已经能做到 **1000+ tok/s prefill** 和 **50 tok/s decode** 量级，并且在游戏共运行时能把性能干扰控制在较低范围。它们最重要的科学价值不是移动端本身，而是明确了一件事：**统一内存或近似统一内存的异构设备上，阶段拆分与 tensor partition 的形态会和 PCIe 离散 GPU 场景显著不同**。这对于未来 Ascend 超节点/统一地址空间类平台很有启发。可靠性分别为 **C** 与 **B**。citeturn32search3turn32search0turn32search6turn32search21

这一方向的方法论已经出现共识。共识是：**CPU 进入计算路径必须“选择性、阶段化、异构友好”**。分歧则在于选择的粒度：NEO 偏 attention/KV 子路径，llm.npu 偏 outlier 与 block affinity，LIA/FlexInfer 偏 AMX/SIMD 条件下更一般的 CPU computations，HeteroInfer 偏统一内存 SoC 下的 tensor partition。对小算力机器的核心启发是：**不要把 CPU 设计成第二个 GPU；要把 CPU 设计成 irregular path / metadata / fallback / prefetch 的经济执行器**。citeturn14search3turn33search1turn34search1turn32search3

### KV / Prefix / Context 状态对象化与分层回流

这一方向是 2025–2026 年最强的技术主线。它的研究问题已经很明确：**如何把本该随一次推理结束而销毁的状态，变成能跨请求、跨实例、跨阶段、跨存储层级持续发挥价值的系统资源**。citeturn15search2turn37search0turn20search17turn22search1

**Mooncake: A KVCache-centric Architecture for Serving LLM Chatbot**。Moonshot AI，FAST 2025，正式发表。Mooncake 的关键不是简单的 prefix cache，而是提出 **KVCache-centric disaggregated architecture**：把 prefill 与 decode 分离，同时利用 GPU 集群中被低估的 **CPU、DRAM、SSD、NIC** 资源建立 **disaggregated KVCache**。这意味着 CPU 的角色主要不是算主干 Transformer，而是承担 **状态平面、I/O 平面、对象转移平面**。Mooncake 生产 slide 显示，其在 Kimi 上让 A800 与 H800 集群分别承载 **115%** 与 **107%** 更多请求；论文页则明确其系统设计目标就是在长上下文场景下以“更多存储换更少计算”。对你关心的“小算力一体机”而言，Mooncake 最值得吸收的一点是：**即便只有 1–4 卡，KV 外部化仍然有意义，因为它重构的是状态生命周期，而不是只服务于大集群**。对 Ascend + Kunpeng 的迁移性为 **高**：原因是其对象化与分层思想和硬件无关，而 Mooncake 官方与 vLLM-Ascend 文档也已出现集成支点。可靠性为 **A/D**。citeturn15search2turn15search7turn15search12turn22search13turn22search16

**LMCache: An Efficient KV Cache Layer for Enterprise-Scale LLM Serving**。2025 技术报告 + 开源系统。LMCache 在概念上比 Mooncake 更直接：官方文档明确写道，它把 KV cache 从 temporary state 变成 **reusable AI-native knowledge**，可持久化、可跨多个 serving engines 复用、可带 observability stack。官方仓库还明确支持 **tiered storage hierarchy: CPU memory, local storage, remote backends**；vLLM 官方 examples 则已经把 LMCache 用于 **KV offloading、PD disaggregation、KV sharing**。LMCache 的研究价值在于，它已经非常接近一个“统一 state object runtime”的雏形，只是目前对象类型仍然主要是 KV。对 Ascend + Kunpeng 的迁移性为 **高**：因为其抽象层更靠近 connector / storage backend，而不是特定 CUDA kernel。可靠性为 **C/D**。citeturn37search0turn37search4turn37search8turn37search11

**Jenga: Effective Memory Management for Serving LLM with Heterogeneity**。Tsinghua/UC Berkeley 等，SOSP 2025，正式发表。Jenga 乍看像 allocator 论文，但实质上是把“状态对象化”的问题推进到 **memory allocator + layer-specific caching logic** 层。其核心观察是，现代模型中 embeddings dimension、attention、access pattern 越来越 heterogeneous，传统 PagedAttention 式统一页管理不够。Jenga 因而给出了 two-level allocator 与 layer-specific caching API，并报告 **GPU memory utilization 最高提升 79.6%**、**吞吐最高提升 4.92×**、平均 **1.80×**。这篇论文的重要性在于它说明：**状态对象化之后，下一步不是只做 store，而是要做“对象敏感 allocator”**。对 Ascend + Kunpeng 的迁移性为 **中到高**，取决于 runtime 是否允许替换 KV pool / allocation policy。可靠性 **A**。citeturn18search0turn18search3turn18search6

**KVCache Cache in the Wild**。SJTU / Alibaba / 上海交大，USENIX ATC 2025，正式发表。它不是新框架，而是**第一个强 operational evidence**：通过大型云供应商的真实 traces 证明 KV reuse 呈现明显偏斜，单轮请求与多轮请求都重要，reuse time 在全局看多样，但在细分类别里是可预测的，而且达到高 hit ratio 所需总 cache size 并不必然无限膨胀。基于此，作者提出 workload-aware eviction policy。它的最大贡献是把很多“工程直觉”变成了数据：**状态对象化必须和 workload characterization 连在一起，否则 eviction/prefetch 策略很容易错配**。可靠性 **A**。citeturn16search0turn16search1turn16search2

**Beluga** 与 **ITME** 代表了 CXL 路线。Beluga 已有 2026 年正式发表版本与 2025 预印本，提出 GPU 和 CPU 通过 **CXL switch** 访问 shared memory pool 做 KVCache 管理，相比 RDMA-based 方案实现 **TTFT 降低 89.6%**、**吞吐提升 7.35×**。ITME 则面向 agentic / long-context shared context infrastructure，利用 **CXL-hybrid memory** 呈现 TB-scale byte-addressable remote expansion，并通过大块 staging/prefetch 将传统 CPU-offloading 再推进一层，报告 **最多 35.7% 吞吐提升**。两者都指向同一设计判断：**CXL 更像低软件复杂度的大容量温层，而不是完全替代 HBM 的热层**。可靠性分别为 **B** 与 **C**。citeturn8search7turn8search3turn8search8

**Tutti** 代表 SSD-backed KV 的另一条路线。它不是在 CPU DRAM 上做更聪明的 offload，而是直接提出 **GPU-centric, two-tier HBM-SSD KV cache object store**，目标是消除 HBM 与 SSD 之间关键 I/O 与控制路径上的 CPU 干预。其摘要特别强调：即使已有 GPU Direct Storage，如果 I/O 仍碎片化、仍需 CPU 发起控制，CPU 会成为严重瓶颈。这个诊断对本地工作站尤其关键，因为很多人会高估 SSD 顺序带宽，而低估 tiny I/O 和 metadata overhead。Tutti 的可迁移性对 Ascend + Kunpeng 我评 **中**：核心问题完全成立，但需要 NPU-SSD direct path、page/object aware layout、异步 DMA API 这类当前生态不一定完善的低层接口。可靠性 **C**。citeturn28search1turn28search6

这个方向当前已经有若干工程共识。第一，**KV reuse 不是临时 patch，而是系统一等公民**。第二，**外部 KV 必须对象化，否则无法共享、观测、迁移和调度**。第三，**层级设计里最重要的是对象布局和恢复策略，而不是介质名字**。第四，**prefix cache、PD transfer、external KV store、tier-aware routing 已经在工业框架中开始收敛**。这对 Ascend + Kunpeng 的现实意义很大，因为目前公开生态文档都已经在沿着这条路建设。citeturn37search0turn21search18turn20search17turn22search1turn22search17

### MoE Expert 对象化、offload、prefetch 与 CPU fallback

MoE 方向的研究问题已经非常清楚：**当 experts 总量远超 HBM 预算时，系统如何在“常驻、分页、预取、压缩、CPU fallback、router-aware placement”之间找到平衡**。这不是传统 dense 模型里 KV offload 的简单复制，因为 expert 的访问模式由 router 决定，miss penalty 也与 token 路由高度相关。citeturn8search1turn8search9turn24search1

**KTransformers**。SOSP 2025，正式发表。它是这一组里最强的代表作，因为它不只是把 experts 搬去 CPU，而是提供 **AMX-specialized CPU kernels + asynchronous CPU-GPU task scheduling**，并以 heterogeneous expert placement 为核心对象，面向 DeepSeek-V3/R1 这类超大 MoE。公开材料显示其对现有方案带来 **4.62–19.74×** 的性能提升。KTransformers 最重要的启发是：**专家对象化不仅需要 cache manager，还需要 CPU 侧真正可用的 expert kernels；否则所谓 CPU fallback 只是纸面设计**。这对 Kunpeng 的意义尤其大，因为如果没有足够的 SIMD/SVE/AMX 级别矩阵能力，CPU expert fallback 很容易只剩容错价值而无性能价值。可靠性 **B**。citeturn8search1turn8search5

**HybriMoE**。2025 预印本，后续已有 DAC 版本引用证据。它的核心机制是三件事：**dynamic intra-layer scheduling** 做 CPU/GPU 负载平衡，**impact-driven inter-layer prefetching** 做专家预取，**score-based caching** 抵御 expert activation instability。公开摘要报告，相对已有 hybrid MoE inference baseline，在 **prefill 平均 1.33×**、**decode 平均 1.70×** 提升。对你的研究，这篇论文最重要的不是 speedup，而是它把 **热度预测 + 预取深度 + CPU/GPU 位置选择** 合并为一套 expert-object management 逻辑。可靠性 **C/B**。citeturn8search9turn15search14

**MoE-Lightning**。ASPLOS 2025，正式发表。它聚焦 memory-constrained GPU 上的高吞吐 MoE inference。虽然公开摘要没有暴露完整的机制细节与 headline 指标，但它之所以重要，是因为它把问题明确放在“memory-constrained GPUs”上，从而与本地 1–4 卡场景高度同构。它提示的路线是：**即便不引入 CPU 计算，也必须把 expert residency 当成动态资源管理问题**。可靠性 **B**。citeturn7search15

**CommitMoE**。AAAI 2026。它不是传统系统论文，但其 **fallback-free expert selection** 与 offloading strategy 很值得纳入，因为它试图利用 router certainty 减少不必要的专家加载，实质上是在降低 object miss。对本地场景，这类 work 可以作为 expert-object management 的策略参考，而不是完整 serving system。可靠性 **B**。citeturn24search1

这一方向的分歧主要在“CPU 是不是应该真的算专家”。KTransformers 和 HybriMoE 给出的答案是“在特定条件下应该”；而系统经验则提醒，只有满足 **足够强的 CPU SIMD/AMX/SVE、足够宽的 DDR 带宽、批量化的 token-expert mapping，以及可隐藏的同步开销** 时，CPU expert fallback 才可能为正收益。否则更现实的路线往往是：CPU 做 prefetch / metadata / low-frequency expert 的兜底，而不承担热路径专家计算。citeturn8search1turn8search9turn24search1

### Prefill / Decode / Encode-Prefill-Decode 阶段拆分

P/D disaggregation 到 2025–2026 年已经不再是研究原型，而是工业主路径之一。真正的研究问题也由“要不要拆”变成了 **“拆开后状态怎么传、路由怎么做、异构硬件怎么放、低并发时是否还赚钱”**。citeturn9search0turn21search18turn37search5

**DistServe** 虽然发表于 2024，但它仍然是这一方向的基石。其核心洞见是 prefill 和 decode 的资源画像不同：前者 compute-intensive，后者 memory-intensive，把两者分离可以同时改善延迟与 goodput，并允许独立资源分配。2025–2026 年几乎所有正式工程化实现都承接了这一路线。citeturn9search0turn9search9

**Cronus**。2025 预印本、ICLR 2026 submission。它把 P/D 思想进一步改成 **partially disaggregated prefill**，面向 heterogeneous GPU clusters：在低端 GPU 上执行 prefill 初段，再把余下 prefill 与早先请求的 decode 和高端 GPU 重叠。它的重要性不是 headline，而是提出一种**不必完全二分 prefill/decode 的中间形态**。这对小型异构机器很重要，因为单机或小集群里完全拆分常常过重，而“部分拆分”更可能赚钱。可靠性 **C**。citeturn31search0turn31search11

**TensorRT-LLM、vLLM NixlConnector、Dynamo**。这三者共同组成了工业工程实践的主链。TensorRT-LLM 官方文档把 **Disaggregated Serving**、**KV Cache Exchange**、**KV cache reuse** 写成正式功能；vLLM 官方则把 **disaggregated prefilling** 与 **NixlConnector** 明确为 feature；Dynamo 官方说明其依靠 vLLM 的 native KV cache events 与 NIXL 机制实现 **KV-aware routing + P/D disaggregation**。这说明阶段拆分已从论文概念变成可部署组件。对你的主题而言，这些文档比单篇论文更重要，因为它们定义了 today’s engineering substrate。可靠性 **D**。citeturn37search1turn37search5turn37search12turn9search8turn21search18turn21search4

**ModServe、EPDServe、HydraInfer**。这组三篇说明多模态场景已经把 P/D 扩展为 **E/P/D**。ModServe 是 SoCC 2025 正式论文，核心是 modality- and stage-aware disaggregation；EPDServe 在 OpenReview 与开源代码中明确把 pipeline 划分为 **Encoding / Context(Prefill) / Decoding**；HydraInfer 则进一步使用 **Hybrid EPD Disaggregation**，宣称在单节点 8×H800、满足 P90 SLO 的前提下，相对 vLLM 达到 **最高 4× throughput**。它们共同证明：阶段拆分在多模态里不是锦上添花，而是因为 encode、language prefill、decode 三段的结构差异过大，合在一起排程会天然低效。可靠性分别为 **B、C、C**。citeturn26search6turn26search0turn11search11turn26search2

这一方向的工程共识正在形成两条。第一条是：**状态连接器比拆分本身更关键**，没有子系统间的 KV transfer、layout transform、orchestrator、connector，拆分只是概念。第二条是：**低并发、短上下文、单机同构环境下，P/D 或 E/P/D 往往不一定赚钱**，因为状态传输和 orchestration overhead 可能超过拆分收益。工业实现之所以能赚钱，通常依赖高并发、明显的阶段异构、以及 connector-level overlap。citeturn9search8turn21search18turn37search5

### Agent / workflow-aware KV 生命周期管理

2025–2026 年 agent serving 的一个关键变化是：**KV 生命周期开始从“按请求看”转变为“按 workflow/program 看”**。这不是小修小补，而是系统目标函数的变化。citeturn10search0turn10search13turn10search7turn10search1

**KVFlow**。NeurIPS 2025，正式发表。它把 agent execution schedule 抽象为 **Agent Step Graph**，再为每个 agent 分配 steps-to-execution 值，用于指导 KV node-level eviction，并对下一步 agent 做 background prefetch。论文报告相对 SGLang hierarchical radix cache，在单 workflow 大 prompt 场景 **最高 1.83×**，多 workflow 并发场景 **最高 2.19×**。这里最值得你吸收的点是：**workflow-aware cache management 的基本对象不是“token page”，而是“未来将在哪一步重新激活的状态子树”**。可靠性 **A**。citeturn10search0turn14search2

**Continuum**。2025 预印本 / 2026 OpenReview。它提出 **tool-aware KV cache timeout / TTL + program-level scheduling**，直接面向 multi-turn agent workloads。其核心是通过预测 tool call duration 来决定是否将 KV pin 在 GPU memory 中，并按程序连续性避免 turn 间 scheduling bubbles。虽然公开摘要未给出统一 headline 百分比，但它清楚地把目标函数切到 **job completion time**，而不是只看 TTFT。可靠性 **C**。citeturn10search13turn10search3

**PBKV**。2026 arXiv。它针对 dynamic agent workflows，把未来 agent invocation prediction 转成 reuse value estimation，同时驱动 eviction 与 prefetch。论文报告在动态 workflow 上相对 LRU **最高 1.85×**，在静态 workflow 上相对 KVFlow **最高 1.26×**。它表明 agent serving 的前沿已经从“静态 DAG-aware”进一步走向“prediction-aware”。可靠性 **C**。citeturn10search7

**Tokencake**。2025 arXiv。它自称 **KV-Cache-centric serving framework for LLM-based multi-agent applications**，核心切入点在于多 agent + external tool 造成的双重问题：关键 cache 会因为空间竞争被驱逐，而正在等待长 tool call 的 agent 又会把 idle KV 卡在 GPU 上。Tokencake 因而从前端 graph API 到两个 specialized schedulers，完整地把 application graph 引入 cache 生命周期。公开摘要没有给出统一 headline 数字，但研究问题本身非常扎实。可靠性 **C**。citeturn10search1turn10search11

这一方向的共同点，是都在把 KV 生命周期从 LRU 提升到 **TTL / graph distance / predictive reuse / program continuity**。分歧则在于：KVFlow 偏静态 step graph，Continuum 偏 tool-aware TTL 与 multi-turn continuity，PBKV 偏 prediction robustness，Tokencake 偏应用图与系统协同。对本地一体机的意义很大，因为本地 agent workload 的并发通常不高，但 session continuity 很强；这使得“少量 GPU HBM + 更聪明的 pin/offload/prefetch”往往比盲目扩大模型更有效。citeturn10search0turn10search13turn10search7turn10search1

### 多模态生成 / 视频生成 / latent / Noise Cache / rolling KV

这一方向在 2025–2026 年已经很活跃，但也最容易把“算法 cache”与“系统 state object”混为一谈。需要明确区分。citeturn11search0turn11search1turn26search3turn11search17turn11search9

**Understanding Diffusion Model Serving in Production**。SoCC 2025，正式论文，来自 Alibaba AIOS 等。它是一篇非常重要的“问题刻画论文”，因为它不是先上某个 trick，而是从生产 workload、调度、资源效率出发，分析 diffusion serving 独特的多阶段 pipeline、资源瓶颈与 memory hierarchy，并提出 **intelligent cache placement、heterogeneous memory optimization、cost-aware scheduling** 三类协同优化。它的重要性在于把 diffusion serving 正式带入“系统”议程，而不再只是算子或模型层优化。可靠性 **B**。citeturn11search0turn11search5turn27search19

**GenServe**。2026 arXiv。它面向同时服务 T2I 与 T2V 的 heterogeneous diffusion workloads，机制包括 **video preemption、elastic sequence parallelism with dynamic batching、SLO-aware scheduler**，并报告相对 strongest baseline **SLO attainment 最高提升 44%**。它说明 diffusion serving 的问题已经转向 **heterogeneous workload co-serving**。可靠性 **C**。citeturn11search1turn11search6

**DisagFusion**。2026 arXiv。它更进一步，把 diffusion serving 做成 **disaggregated serving**，用 **asynchronous pipeline parallelism** 和 **hybrid instance scheduling** 处理 stage handoff 和 workload shift，报告相对 monolithic baseline **throughput 提升 3.4×–20.5×**、**端到端 latency 降低最高 18.5×**。这篇论文证明：视频/扩散这一侧已经在重走 LLM serving 的“阶段拆分 + 状态交换 + 弹性调度”路线。可靠性 **C**。citeturn26search3

**EPDServe / ModServe / HydraInfer** 说明在多模态 LMM 里，encode/prefill/decode 三段已经足够异构，值得拆开部署；**StreamDiffusionV2** 则进一步把视频生成推向实时 streaming 系统，但当前公开摘要强调更多是 SLO、streaming pipeline 与多 GPU 扩展，而不是 state tiering。citeturn26search0turn26search6turn26search2turn11search3turn11search16

与之相对，**TeaCache、FasterCache、FlowCache** 解决的是另一类问题：如何在 diffusion/AR-video 里重用 noise feature、intermediate feature 或 flow chunk，从而减少重复 denoising / video generation 开销。TeaCache 是 CVPR 2025，FasterCache 在 OpenReview 上有较高影响力，FlowCache 是 2026 arXiv。但这些方法多数仍属于 **model/runtime reuse policy**，并没有形成像 Mooncake/LMCache 那样完整的“外部状态对象层 + 分层回流系统”。因此，关于你特别关心的“**视频生成 serving + Noise Cache/rolling KV/latent state 对象化 + 分层回流**”，我目前的结论是：**未找到 2025–2026 年已经完整闭环的系统论文**。现有公开工作要么偏 serving pipeline，要么偏 training-free cache reuse；二者尚未完全合流。citeturn11search17turn11search9turn27search10turn11search0turn26search3

这恰恰是一个很扎实的研究空白：**能否把 latent / noise / rolling state 统一纳入 state object runtime，并做 tier-aware placement、restore、prefetch、compression 与 observability**。从公开文献看，这个问题已经被“需要”，但尚未被“系统化解决”。citeturn11search17turn11search9turn27search10turn37search0

### Trace / Profiler / Simulator / Benchmark / Energy Model

这一方向对你的课题尤其重要，因为它决定第三条技术路线——**收益边界与规格反推**——是否能从“经验主义”变成“方法论”。citeturn13search16turn12search2turn12search0turn30search0

**ServeGen**。NSDI 2026，正式发表。它的重要性在于提供了来自 production clusters、跨 language/multimodal/reasoning 的 LLM serving workload characterization，并给出按 client decomposition 生成 realistic workloads 的方法。论文页与 PDF 都说明其数据来自四个月、数十亿请求的生产集群。对你来说，它最大的价值不是某个优化数字，而是告诉你：**评估异构协同时，synthetic trace 很容易误导，必须考虑 burstiness、conversation structure、reasoning workload 与 multimodal mix**。可靠性 **A**。citeturn13search16turn15search6

**ProfInfer**。2026 arXiv。它是面向现代 LLM inference engines 的 **eBPF-based fine-grained profiler**，可在不修改源码的情况下，把 forward pass、operator、timeline 与 hardware counters 采出来，且论文报告 runtime overhead **低于 4%**。这类工具非常适合回答你反复强调的问题：CPU 参与到底是在算、在等、还是在 sync。可靠性 **C**。citeturn12search2turn12search7

**KernelSight-LM**。2026 arXiv。它提供 token-level execution、kernel-level latency breakdown、roofline kernel model、communication model、host-overhead model，并通过 discrete-event scheduler 把 prefix caching、continuous batching 等机制拼起来。它最有价值的地方是**把 host overhead 也建模进去**，这对判断 CPU/NPU/GPU 协同是否被 control overhead 反噬非常关键。可靠性 **C**。citeturn12search0

**Kareto**。2026 arXiv，论文标题为 *Adaptive Multi-Objective Tiered Storage Configuration for KV Cache in LLM Service*。它用 high-fidelity end-to-end simulator 做 tiered KV 的 Pareto frontier 搜索，并报告相对固定配置，**吞吐可提升 9.3%**、或**延迟降低 58.3%**、或**成本下降 20.2%**。这条路线直接对应你的第三个问题：**不是先拍脑袋定 DRAM/SSD/CXL 规格，而是先建 workload-aware what-if model 再反推规格**。可靠性 **C**。citeturn30search0

**TokenPowerBench** 与 **Chakra** 则补齐了另外两块拼图。前者把 prefill/decode 分阶段对齐到能耗测量，提供 Joules/token 等指标；后者提供开放 trace graph 生态，用于 observation / reproduction / co-design。二者合在一起，意味着 2026 年已经可以开始认真回答“增加 CPU 核数值不值”“多一层 CXL memory 是否划算”“不同路由/拆分策略的能耗代价是多少”这类问题，而不再停留在粗糙吞吐测试。citeturn13search13turn13search9turn13search19

这一方向当前的不足也很明确：现有 profiler/simulator 多数仍对 **单机小算力、Ascend+Kunpeng、video latent state、CPU fallback expert** 的建模不足。因此你若要做原创，完全可以把“**小算力异构 serving 的收益判定模型**”作为独立研究目标。citeturn12search0turn30search0turn22search11

### 工业框架与工程实践

工业与开源框架的证据，非常重要，因为它们体现了“哪些机制已经走出论文”。citeturn37search1turn37search0turn20search17turn22search11

**vLLM** 已经原生支持 **Automatic Prefix Caching**、**disaggregated prefilling** 与 **NixlConnector**。这意味着在 vLLM 体系里，prefix cache、KV event、P/D 拆分、connector 化传输已经是主流能力，而不是实验分支。citeturn19search6turn9search8turn21search18

**NVIDIA Dynamo / NIXL / TensorRT-LLM** 共同说明，工业界正在把 KV transfer、KV-aware routing、disaggregated serving 做成正式产品能力。NIXL 官方仓库明确写到它提供对 **CPU/GPU memory 与 file/block/object store** 的抽象；TensorRT-LLM 官方文档同时提供 **KV cache reuse** 与 **Disaggregated Serving / KV Cache Exchange**。这表明“状态对象 + 连接器 + 路由器”已是工业共识。citeturn21search5turn21search4turn37search1turn37search5turn37search12

**SGLang HiCache** 则把层级缓存在开源方向做得非常明确。官方文档写明其为 three-tier hierarchical KV caching，可跨 GPU memory、host memory 与 external storage backend；同时 Dynamo 文档已经支持 HiCache 的 tier-aware worker selection；Mooncake 也作为 HiCache backend 出现。citeturn20search17turn20search5turn20search8turn20search11turn20search12

**LMCache** 在开源层更进一步地强化了“持久层”与“跨 engine 复用”这一抽象，而 **llm-d** 与相关博客则在分布式/文件系统场景里强调原生 KV offloading 与 KV-aware scheduling。citeturn37search0turn37search4turn37search14turn22search6

**Ascend 生态** 目前公开证据更多来自文档，而非论文。MindIE 官方写明其支持服务化部署、session management、request scheduling，并兼容 Triton/OpenAI/TGI/vLLM 等接口；vLLM-Ascend 官方把自己描述为遵循 hardware-pluggable 原则的 Ascend backend；UCM 提供 external KV-cache storage layer，用于 prefix caching 场景，并采用 node-local DRAM + shared storage 的 tiered design；vLLM-Ascend 还公开了 **PD-colocated with Mooncake** 教程与 **KV Cache Pool** 文档。换言之，**Ascend 生态在“状态对象化与分层回流”上已经有工程支点，只是缺乏学术论文把它系统化讲清楚**。citeturn22search0turn22search11turn22search1turn22search13turn22search2turn22search17

## 反例与收益边界

CPU 参与并不天然正确。最典型的反例，是算子本身虽然小，但需要高频跨设备同步、layout transform 或 tiny tensor copy。此时 CPU 的标量/向量计算成本不高，真正昂贵的是 **PCIe/UB/NVLink/CXL 往返 + host runtime bookkeeping + kernel launch / event synchronization**。NEO 之所以只 offload decode attention 的部分子路径，就是为了避免整层 swap；llm.npu 之所以显式抽出 outlier、固定块和顺序重构，也是因为 NPU/GPU/CPU 的优势区间不同。CPU-vs-GPU 的 on-device 研究更进一步提醒：有时 CPU 甚至能战胜 GPU，不是因为 CPU 更快，而是因为 GPU 的内存搬运与调度代价更高。citeturn14search3turn33search1turn34search0

KV offload 也不是越细越好。Tutti 直接指出，如果 KV page/object 布局碎片化，系统会产生大量 **tiny random I/O** 和巨大的 metadata/control overhead；即便理论上有 direct storage，若每个 I/O 仍需 CPU 发起，也一样会被 control plane 反噬。SGLANG-LSM 之所以转向 LSM-tree / key-value separation，也正是为了修补 file-per-object 布局在大规模 external KV 上的元数据与 locality 问题。citeturn28search1turn28search0

P/D 或 E/P/D 拆分在**单机、低并发、短上下文**下常常不赚钱。因为这时 prefill 与 decode 的干扰尚不严重，反而状态传输、orchestrator、connector 初始化、layout transform 这些额外步骤会成为纯开销。TensorRT-LLM 和 vLLM 的官方文档都很强调 KV cache exchange / connector / overlap，是因为没有这些机制时，拆分本身会失去收益。Cronus 之所以提出“partially disaggregated prefill”，某种意义上也是在承认“完全拆分”并非总是最佳。citeturn37search5turn9search8turn31search0

CXL memory 更适合作为**温层或容量扩展层**，不一定适合作为热路径。Beluga 与 ITME 的成功建立在 shared pool / byte-addressable extension / lower software overhead 上，但它们并没有宣称 CXL 可以取代 HBM 成为最热状态层；Kareto 也显示 tier choice 必须结合 workload 的多目标优化来选。换句话说，**CXL 的优势首先是扩容、共享与编程模型，而不是绝对时延**。citeturn8search3turn8search8turn30search0

CPU fallback expert 只有在满足明确条件时才值得做。KTransformers 和 LIA 给出的隐含前提是：CPU 需要有足够强的 **AMX / SIMD / SVE 类矩阵能力**、足够高的 **DDR 带宽**、足够好的 **batching / prefetch / overlap**，并且 expert miss 不是太频繁。否则 CPU 只会把 expert miss penalty 从 “load to HBM” 换成 “slow host compute + sync”。因此，对塔式服务器或小一体机而言，**没有强 SIMD/AMX/SVE 的 CPU，更适合做 expert prefetch 与 metadata，而不是做热路径 experts**。citeturn8search1turn34search1turn8search9

GPU/NPU-SSD direct path 如果缺少 **object-aware layout、batch I/O、页级组织与异步 DMA API**，也不一定有意义。Tutti 的贡献恰恰是在说明：只有顺序带宽数字是不够的；若系统不能把 KV/expert/latent 组织成对 SSD 友好的对象，不能避免 CPU bounce buffer，不能把 I/O 与恢复并行，所谓 “direct storage” 很容易沦为营销名词。citeturn28search1turn28search6

多模态 pipeline 也有自己的反例。ModServe、HydraInfer、DisagFusion 说明分阶段部署很有吸引力，但 production diffusion serving 的分析进一步显示：一旦 text/vision encode、DiT/U-Net 主干、VAE decode、codec/post-processing 被拆开，**CPU codec/VAE/postprocess 很容易变成新的瓶颈**。也就是说，阶段拆分只会把瓶颈移动，而不会自动消灭瓶颈。citeturn26search6turn26search2turn26search3turn11search5

## Ascend NPU + Kunpeng CPU 迁移表

从公开证据看，**未找到 2025–2026 年直接以 Ascend + Kunpeng 为对象的同等级系统论文组合**；但从 MindIE、vLLM-Ascend、UCM、Mooncake on Ascend 等官方资料来看，迁移路径已经具备较强工程可行性。citeturn22search0turn22search11turn22search1turn22search13turn22search16

| 机制 | 代表论文/系统 | CUDA/GPU 生态做法 | Ascend 生态可用支点 | Kunpeng CPU 角色 | 纯软件可做 | 需要推理引擎 hook | 需要 runtime / DMA / memory API | 需要下一代硬件接口 | 优先级 | 最大风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| Selective CPU attention / short-path compute | NEO, FlexInfer, LIA | CUDA kernel + host-side overlap + AMX/CXL | MindIE / vLLM-Ascend 的可插拔 backend，CANN 图外算子调度 | attention fallback、metadata、prefetch | 可以先做 host-side 子路径挑选 | 需要 attention/KV 分块与跨设备事件接口 | 需要低开销 async copy/event | 更强 host-side matrix ISA | P1 | NPU runtime 不易暴露细粒度切分点 |
| NPU 主 prefill + CPU/GPU 处理 outlier | llm.npu | NPU for fixed-shape bulk, CPU/GPU for outliers | CANN + MindIE + Ascend kernel registry | outlier block、异常 shape、控制面 | 可先在前端做 prompt/block 重排 | 需要 block affinity / OOO block scheduling | 需要跨 NPU/CPU 的异步同步 | 更细粒度 NPU subgraph fallback | P0 | NPU 编译与动态图支持不足 |
| MoE CPU fallback / expert prefetch | KTransformers, HybriMoE | CPU AMX kernels + async scheduler + expert cache | vLLM-Ascend 对 MoE 支持、CANN、HCCL | 冷专家 fallback、预取、打分 | 可做 expert heat 预测与 host cache | 需要 expert manager 与 router hook | 需要高吞吐 host↔NPU 数据面 | 更强 Kunpeng SIMD/SVE / host BW | P1 | CPU 算力不足导致 fallback 变负收益 |
| Prefix cache / external KV | Mooncake, LMCache, UCM | vLLM/SGLang/Dynamo connectors | UCM、vLLM-Ascend、MindIE Prefix Cache、Mooncake | DRAM warm tier 与 local cache | 可立即做 | 需要 cache key、restore、evict hook | 需要可控 KV import/export API | 更高效 NPU-state serialization | P0 | 状态格式与兼容性 |
| Hierarchical KV caching | HiCache, LMCache, UCM | GPU/HBM + host RAM + external store | UCM，Mooncake on Ascend，3FS/NFS backend | DRAM 层与 I/O 聚合层 | 可立即做 | 需要 tier-aware cache manager | 需要 async I/O / background prefetch | 更低开销 direct path | P0 | DRAM/SSD 层数据路径抖动 |
| PD disaggregation | DistServe, TensorRT-LLM, Dynamo, vLLM PD | KV connector + routing + exchange | vLLM-Ascend + UCM + Mooncake 文档已支持 PD 相关路径 | orchestration、KV relay、调度 | 可先做 PD-colocated 与双实例 | 需要 prefill/decode 连接器 | 需要 NPU 间 KV transfer API | 更高效跨节点 KV DMA | P0 | KV transfer 成本过高 |
| E/P/D disaggregation for multimodal | EPDServe, ModServe, HydraInfer | separate encode/prefill/decode workers | MindIE + vLLM-Ascend 多实例部署 | image/codec/postprocess、调度 | 可以先做多进程原型 | 需要 stage DAG / router / layout transform | 需要跨 stage tensor/latent transfer | 更好的多 stage direct path | P1 | 视觉编码与语言状态格式转换开销 |
| CXL / warm expansion | Beluga, ITME | GPU/CPU shared pool / hybrid memory | 目前公开 Ascend 论文证据弱，更多依赖 OS/memory stack | host warm pool manager | 可先做软件模拟与 what-if | 需要 tier-aware allocator | 需要统一内存映射与 direct access | 更成熟 CXL fabric / NPU load-store semantic | P2 | 生态支持不足 |
| SSD-backed KV / state object | Tutti, LMCache, SGLANG-LSM | GPU-centric SSD object I/O + KV store | openEuler/存储栈、UCM backend、Mooncake store | object aggregation、metadata、fallback restore | 可先做 CPU-bounce 版 | 需要 object API 与 restore scheduler | 需要 direct storage / async DMA | NPU-SSD direct path、对象页布局支持 | P2 | tiny I/O 与控制开销 |
| Workflow-aware KV lifecycle | KVFlow, Continuum, PBKV, Tokencake | agent graph aware cache/scheduler | MindIE session manager、vLLM-Ascend runtime | tool TTL、workflow cache policy | 可立即做 | 需要 session/workflow metadata hook | 需要低成本 pin/unpin/restore | 更原生 session-aware runtime | P0 | 真实 agent trace 获取困难 |
| Observability / what-if model | ProfInfer, KernelSight-LM, Kareto | eBPF/timeline/simulator/Pareto optimizer | MindIE 指标、CANN profiling、openEuler perf 工具 | host-side trace aggregation | 可先做 trace/energy pipeline | 需要 runtime events 暴露 | 需要 counters / memory / DMA telemetry | 更丰富硬件性能计数器 | P0 | NPU runtime 可观测性不足 |

综合来看，**P0** 最值得优先做的是三件事：其一，**外部 KV + 分层 cache + prefix cache 的统一原型**；其二，**PD/PD-colocated 的状态连接器与小规模多实例调度**；其三，**agent/workflow-aware KV 生命周期管理**。这三件事依赖的软件支点今天已经存在，而且最能转化为对小算力一体机的差异化能力。citeturn22search1turn22search13turn22search17turn37search0turn20search17

## 研究空白、精读优先级、参考文献与关键词

### 研究空白与创新机会

第一个空白，是 **NPU-SSD direct storage for KV / state object**。Tutti 在 GPU 侧已经清晰说明“光有 GDS 不够，还要 object/layout/control-path 设计”，但面向 NPU 的公开系统论文基本仍是空白。Ascend + Kunpeng 如果能在这一点形成公开、可核验的系统工作，学术价值和工程价值都很高。citeturn28search1turn22search11

第二个空白，是 **统一 state object runtime**。今天有 KV object runtime 的雏形，如 LMCache、Mooncake、HiCache、UCM；也有 expert-object 的初级形态，如 KTransformers / HybriMoE；还有 latent/noise/flow 的复用方法，如 TeaCache、FasterCache、FlowCache。但公开论文里还没有把 **KV / Expert / Adapter / Embedding / Latent / Noise Cache / Tool Result** 放进同一抽象下做统一“命名—驻留—迁移—压缩—恢复—观测”的系统。citeturn37search0turn15search2turn20search17turn22search1turn8search1turn8search9turn11search17turn11search9turn27search10

第三个空白，是 **面向小算力单机 / 小集群的收益判定模型**。现有很多论文默认云集群或高端 GPU，或者至少在多 GPU 高并发场景下评估；而你关心的是 Mini 工作站、塔式服务器、1–4 卡小机、2–8 节点小集群，这要求一个不同的 cost model：把 CPU 核数、DDR 带宽、HBM 容量、SSD IOPS、互联时延、功耗都纳入 what-if。KernelSight-LM、Kareto、ServeGen 是可利用的起点，但还不够贴合这一场景。citeturn12search0turn30search0turn13search16

第四个空白，是 **Ascend + Kunpeng 上的公开系统论文缺口**。公开生态已经有 MindIE、vLLM-Ascend、UCM、Mooncake 集成，但学术界尚未给出足够强的、系统化的正式论文来把这些能力串起来。因此，如果你的团队能把“外部 KV、PD、workflow-aware cache、Kunpeng fallback 路线”在 Ascend 上做出论文级证据，这个方向会非常有辨识度。citeturn22search0turn22search11turn22search1turn22search13

第五个空白，是 **视频生成 serving 中 rolling KV / Noise Cache / latent state 的系统级分层回流**。目前公开工作要么是 serving pipeline，要么是 training-free cache reuse；还没有一个像 Mooncake/LMCache 那样成熟的“视频状态层”。这是非常值得切入的空白。citeturn11search0turn26search3turn11search17turn11search9turn27search10

第六个空白，是 **CPU fallback expert 的硬件规格边界**。大家都在说 CPU 可做 fallback，但“需要多少 SIMD/AMX/SVE、多少 DDR BW、什么 batch/concurrency 才为正收益”仍缺少统一判定模型。KTransformers、LIA、HybriMoE 提供了方向，但没有给出普适的规格反推框架。citeturn8search1turn34search1turn8search9

### 最值得精读论文清单

**P0 必须读**

- **NEO**：如果你要理解“CPU 为什么能正收益介入 attention/KV 子路径”，这是最直接的正式论文。citeturn14search3turn36search3
- **Mooncake**：如果你要理解“KVCache-centric architecture”到底长什么样，这是必读。citeturn15search2turn15search7
- **KTransformers**：如果你要判断 CPU fallback expert 是否值得做，这是当前最强的正式系统证据。citeturn8search1turn15search23
- **Jenga**：如果你要理解状态对象化为什么最终会推到 allocator / memory manager 层，这是必读。citeturn18search3turn18search6
- **KVCache Cache in the Wild**：如果你要避免拿 synthetic trace 做错系统决策，这是必读。citeturn16search0turn16search2
- **KVFlow**：如果你要把 workflow-aware cache 讲清楚，这篇最扎实。citeturn10search0turn14search2
- **ServeGen**：如果你要做 benchmark、simulation、what-if analysis，这篇是 workload 入口。citeturn13search16turn15search6
- **Beluga / ITME / Tutti**：三篇一起读，能把 CXL、remote memory、SSD-backed KV 的边界看清楚。citeturn8search3turn8search8turn28search1

**P1 应读**

- **FlexInfer**：帮助你把 CPU 从“容量扩展器”理解为“可调算力池”。citeturn35search0turn35search15
- **LIA**：帮助你把 AMX/CXL 条件纳入规格反推。citeturn34search1
- **llm.npu / HeteroLLM / HeteroInfer**：帮助你理解 NPU 主路径 + CPU/GPU irregular path 的端侧形态。citeturn33search1turn32search3turn32search21
- **HybriMoE**：帮助你理解 expert prefetch / score-based cache。citeturn8search9
- **ModServe / EPDServe / HydraInfer**：帮助你把 P/D 思想扩展到 multimodal E/P/D。citeturn26search6turn26search0turn26search2
- **ProfInfer / KernelSight-LM / Kareto**：帮助你建立第三条路线的方法论。citeturn12search2turn12search0turn30search0

**P2 背景参考**

- **Continuum / PBKV / Tokencake**：理解 agentic workload 下 KV 生命周期如何变化。citeturn10search13turn10search7turn10search1
- **Understanding Diffusion Model Serving / GenServe / DisagFusion**：建立 multimodal/video serving 的系统视角。citeturn11search0turn11search1turn26search3
- **TeaCache / FasterCache / FlowCache**：理解 latent/noise/video cache 的方法学现状与局限。citeturn11search17turn11search9turn27search10
- **TokenPowerBench / Chakra**：做能耗与 co-design 的补充工具。citeturn13search13turn13search9

### 参考文献与链接清单

本报告优先使用了以下 **primary sources**：  
MLSys 2025 proceedings 与 OpenReview（NEO, FlexInfer, Marconi）；USENIX FAST/ATC/NSDI 官方论文页与 PDF（Mooncake, KVCache Cache in the Wild, Weaver, ServeGen）；ACM SOSP/ISCA/ASPLOS 正式页面（KTransformers, HeteroInfer, Jenga, LIA, llm.npu, MoE-Lightning）；arXiv 原文与官方项目页（HeteroLLM, HybriMoE, Beluga, ITME, Tutti, Cronus, HydraInfer, PBKV, Tokencake, GenServe, DisagFusion, KernelSight-LM, Kareto）；以及 vLLM、TensorRT-LLM、NVIDIA Dynamo/NIXL、SGLang、LMCache、MindIE、vLLM-Ascend、UCM、Mooncake 官方文档。citeturn36search3turn15search2turn16search0turn13search16turn15search23turn34search1turn33search0turn32search21turn18search3turn37search0turn37search1turn21search5turn20search17turn22search0turn22search1turn22search11turn22search16

### 搜索关键词清单

本轮实际使用并交叉扩展的关键词包括：  
CPU GPU collaborative LLM inference；CPU assisted attention LLM；CPU offloading online LLM inference；CPU fallback expert MoE；heterogeneous LLM inference CPU GPU；NPU LLM inference CPU；on-device LLM inference NPU CPU GPU；KV cache offload CPU memory SSD；external KV cache LLM serving；KV cache tiering DRAM SSD CXL；KV cache object store GPU SSD；GPU direct storage KV cache；CXL memory LLM inference；MoE expert offloading CPU GPU；MoE expert prefetch LLM serving；prefill decode disaggregation；encode prefill decode multimodal serving；agent workflow KV cache；tool-aware KV cache TTL；diffusion model serving heterogeneous pipeline；video generation serving latent cache；Noise Cache video generation；rolling KV video generation；LLM serving simulator cost model；LLM serving profiler eBPF；LLM serving energy benchmark；hardware-aware LLM serving。上述搜索再结合已知论文做 citation-chain 扩展，得到本报告中的核心条目与会议查缺补漏结论。citeturn36search2turn19search11turn25search0turn25search1turn25search2