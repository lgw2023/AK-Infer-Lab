# A+K 协同单页高密度 PPT｜文字内容草案

> 用途：先梳理一页 PPT 中应放的具体文字，不生成 PPT。  
> 页面逻辑：顶部给一句话结论；中部用 4 个技术方向卡片承载“问题—技术及趋势—未来趋势”；底部用一条压缩横条给硬件诉求摘要。  
> 表述原则：关键技术点采用“短句：长句”样式；“技术及趋势”不写硬件诉求；“未来趋势”去掉年份，写成连续判断句；硬件诉求只放页面底部。

---

## 0. 页面标题与主结论

### 标题
**A+K 协同：让 Kunpeng CPU 从 Host 变成计算、状态、调度与观测的一等系统资源**

### 副标题
面向 AI Coding Agent、办公助手 Agent、多模态生成的一体机小算力增强路径

### 顶部一句话结论
**A+K 协同不是“让 CPU 多算一点”，而是让 Ascend NPU、Kunpeng CPU、DDR/SSD 与 Runtime 围绕同一条 Agent critical path，形成计算协同、状态分层、语义调度和 Trace 仿真闭环。**

### 顶部场景牵引短句
- **AI Coding Agent：**744B GLM、M 级长上下文、工具/编译/测试循环，核心矛盾是长前缀、KV 驻留、冷专家回取和 CPU 工具链等待。
- **办公助手 Agent：**30B/70B/120B、本地知识库与文档工具，核心矛盾是多轮上下文复用、检索/Rerank、结构化输出和低尾延迟交互。
- **多模态生成：**Helios-14B、Wan-27B、AR+DiT/DiT/VAE/Codec 流水，核心矛盾是生成主干、滚动缓存、视频编解码、后处理和临时 I/O 的端到端协同。
- **系统目标：**放得下、跑得快、恢复得回、功耗可控。

---

## 1. 数据面协同计算：CPU 直接参与端到端计算链路

### 问题
- **NPU 主路径与长尾计算错配：**NPU 适合规则化大矩阵，但动态长度、outlier、小算子、短序列矩阵、tokenizer、schema/mask 和数据依赖容易把端到端链路拖慢。
- **细粒度卸载容易被搬运成本反噬：**CPU/NPU 分工如果切得过细，UB/PCIe、DDR、同步和 runtime 管理开销会吞掉计算收益。
- **工具与多模态外部计算被低估：**Coding 编译测试、文件 I/O、浏览器、检索、视频编解码和后处理常处在任务关键路径上，传统 tokens/s 指标看不到。

### 技术及趋势
- **阶段感知混合执行：构建以 Prefill、Decode、工具调用、检索和多模态流水为边界的 A+K 执行矩阵，按算子规则性、状态热度和搬运成本选择 NPU 主算、CPU 辅算、重算或卸载，避免细粒度 offload 被 UB/PCIe 同步开销反噬。**
- **近数据短算子加速：围绕 KV 相似度、Prefix 匹配、短序列矩阵、向量检索和离散 I/O 聚合构建 Kunpeng 侧近数据算子库，通过 SVE/OMP、批量化排布和异步搬运压低小并发交互负载的长尾时延。**
- **稀疏专家协同计算：面向 MoE 冷/温专家建立 CPU 侧专家索引、fallback expert 和 expert prediction 能力，让 Ascend NPU 保持热专家与密集层连续执行，降低专家 miss 对 TPOT 和任务尾延迟的冲击。**
- **工具与媒体链路并行：将 shell、编译测试、文档解析、视频编解码、后处理和封装纳入 CPU 数据面，通过工具空窗与生成流水并行掩盖 CPU 时间，保障 NPU 主推理不被模型外负载拖停。**

### 未来趋势
A+K 数据面会从静态 CPU/NPU 分工演进为 profile 与 cost model 驱动的自动混合执行计划，Runtime 能按阶段、算子形态、状态热度和工具空窗动态决定 NPU 主算、CPU 辅算、重算或卸载。

---

## 2. 状态与内存协同：CPU/DDR/SLC/SSD 承接模型状态

### 问题
- **权重、KV 与专家共同挤压近端内存：**百 B 办公模型、744B Coding MoE、M 级上下文和多 Agent 会同时消耗热权重、热 KV、workspace、专家权重和索引状态。
- **放得下不等于恢复得回：**KV/Prefix/Expert 下沉到 DDR/SSD 后，如果恢复路径慢、预取不准或 SSD I/O 抖动，就会直接放大 TTFT、TPOT 和 JCT 尾延迟。
- **Exact prefix cache 不足以覆盖 Agent 复用：**Coding repo、工具描述、长期记忆和企业文档常是相对稳定但位置漂移的上下文块，仅靠完全相同前缀命中会浪费大量可复用状态。
- **MoE 专家热度随任务阶段变化：**专家访问不是静态热点，session、输入类型、层级和阶段都会改变专家热度，简单常驻/简单 LRU 都不够。

### 技术及趋势
- **统一状态对象层：将 KV、Prefix、Context 与 Expert 从引擎私有缓存抽象为可命名、可迁移、可恢复的状态对象，统一维护 owner、version、tier、hotness、TTL 与 resume hint，支撑 Bailu、DDR 和 SSD 之间的定位、保留、迁移与治理。**
- **热温冷生命周期策略：以 next-use、工具阶段、session 关键性和恢复成本决定 pin、offload、discard 或 recompute，让热 KV/热专家留在近端、温状态提前回温、冷状态可落盘且可按需恢复。**
- **跨层直通恢复流水：将 NPU-SSD 直通、CPU 预取聚合、异步 load/store 和 I/O round-robin 组织成统一恢复面，把冷 KV/冷专家的随机小 I/O 改造成可批量、可预测、可掩盖的数据回流。**
- **专家状态分级治理：建立热专家高精常驻、温专家语义预取、冷专家低精应急和失效重算策略，用 expert hit rate、miss penalty 与质量损失共同管理 MoE 容量、时延和精度。**

### 未来趋势
状态与内存协同会从“引擎内部缓存优化”演进为“推理数据基础设施”，KV、Prefix、Context 和 Expert 将像数据库对象一样被命名、观测、迁移、恢复和治理。

---

## 3. 控制面调度管理：CPU 作为异构系统的大脑

### 问题
- **Request-level 调度丢失 Agent 语义：**Agent 任务由多轮 LLM、工具调用、检索、失败重试和状态恢复组成，单次请求的 TTFT/TPOT 不能代表完整任务体验。
- **工具资源与 NPU 资源强耦合：**CPU 沙箱、编译测试、浏览器、文档解析、向量库和文件系统队列会影响下一轮模型恢复，但传统推理调度只看 NPU 队列。
- **工具等待改变 KV 生命周期：**短工具适合 KV pin，中工具适合 offload + prefetch，长工具可能应 discard/recompute；没有工具阶段信息就无法正确保温。
- **小并发交互不适合固定 batch 策略：**Mini/塔式工作站常是少量用户、高突发、前后台混部，长 prefill 很容易阻塞即将完成的短任务分支。

### 技术及趋势
- **语义元数据下沉：构建 workflow、session、stage、tool、cache intent 与 expected resume time 的最小元数据协议，让 Agent 的任务边界、工具空窗和恢复路径进入 A+K 调度链路。**
- **轻量策略运行时：在 Agent 框架与推理引擎之间构建 observe–score–predict–act 策略层，统一评估会话进度、KV 价值、专家热度、工具队列和 NPU 队列，形成不重写引擎也可插拔的控制面。**
- **任务级优先级与准入：形成 resume-first、completion-aware、prefill-budget 和 CPU/NPU 联合 admission 策略，优先保护接近完成、可复用状态价值高、或前台交互敏感的任务，压低 JCT 尾部。**
- **工具感知状态调度：根据工具类型和预计时长自动选择 KV pin、DDR offload + prefetch、discard/recompute 或专家预热，把工具等待从黑盒暂停变成可利用的状态管理窗口。**

### 未来趋势
控制面会从“请求队列调度器”演进为“Agent Runtime 操作系统”，系统将以 session、program、workflow 为基本对象，围绕任务完成时间、SLO goodput、恢复优先级和状态价值做全局调度。

---

## 4. Trace 与仿真闭环：性能预测、能效建模与硬件参数反推

### 问题
- **没有真实 Trace 就无法判断 A+K 是否收益为正：**CPU offload、KV 分层、专家预取和 NPU-SSD 直通都可能被搬运、同步、恢复和管理开销抵消。
- **Tokens/s 无法解释任务为什么慢：**Agent 任务的慢点可能在工具、检索、KV 恢复、SSD I/O、CPU 队列、前后台干扰或失败重试，而不一定在模型主算。
- **硬件诉求需要因果证据支撑：**只看资源利用率不能反推规格，必须通过限算力、限容量、限带宽、限 CPU、限 DRAM、限 SSD、限功耗等扰动实验建立瓶颈因果关系。

### 技术及趋势
- **任务语义 Trace：构建覆盖 Task、Turn、Request、Tool、Memory、KV、Resource 和 Power 的统一事件链，把 append token、prefix hit、KV restore、tool wait、CPU Core·s 与 NVMe bytes 对齐到同一条 Agent 任务路径。**
- **协同边界 Profiler：构建低侵入 A+K profiler，按阶段归因 NPU 算力、Bailu/HBM、DDR、UB/PCIe、SSD、CPU 工具池和 Runtime 开销，识别瓶颈究竟来自模型主算还是协同链路。**
- **收益判定 Cost Model：把 CPU/NPU placement、KV/Expert 迁移、重算、预取、直通和功耗上限纳入同一代价模型，输出 offload、保留、回温、丢弃和重算的收益边界。**
- **规格反推仿真器：基于单资源扰动和 what-if 扫描形成硬件参数反推链，量化 CPU 核数、DDR 带宽、SSD IOPS、UB 带宽和 Bailu 容量对 JCT、P95/P99 与 Tasks/J 的敏感度。**

### 未来趋势
Trace 与仿真会从“事后性能分析”演进为“软硬件协同设计输入”，每个关键技术和硬件规格都需要绑定 trace、扰动实验、cost model 和 what-if 结果，形成可审计的参数反推链路。

---

## 5. 底部硬件诉求摘要（只放一条横向压缩信息）

**硬件诉求摘要：**Mini / DV100 Lite 作为 A+K 原型验证平台，重点验证阶段级分工、SVE/OMP 短算子、KV/Prefix 分层、工具感知 TTL 和多模态 media pipeline；塔式 / n+1 分级内存系统需要把 84GB Bailu、384GB DDR5、SSD 冷层、UB 200GB/s、NPU-SSD 直通和 CPU 沙箱池做成可编排 tier；n+2 PIM+HMM 异构 SoC 需要用 HMM 承载大容量权重/状态，用 PIM 承接高带宽 KV/激活近存访问，并同步暴露 telemetry、QoS、统一编址和仿真模型。

---

## 6. 页面压缩版，可直接贴入一页 PPT

### 主标题
**A+K 协同：Kunpeng 从 Host 变成计算、状态、调度与观测的一等系统资源**

### 主结论
**不是 CPU 多算一点，而是让 Ascend NPU、Kunpeng CPU、DDR/SSD 与 Runtime 围绕 Agent critical path 形成计算协同、状态分层、语义调度和 Trace 仿真闭环。**

### 四个技术方向卡片

#### 1）数据面协同计算
**问题：**NPU 主路径与动态长度、小算子、outlier、工具 I/O、视频 codec 错配；细粒度 offload 容易被 UB/PCIe 与同步开销反噬。  
**关键技术：**阶段感知混合执行：按 Prefill、Decode、工具、检索和多模态阶段建立 A+K 执行矩阵，用算子规则性、状态热度和搬运成本决定 NPU 主算、CPU 辅算、重算或卸载。  
**关键技术：**近数据短算子加速：围绕 KV 相似度、Prefix 匹配、短序列矩阵和离散 I/O 聚合建设 Kunpeng 近数据算子库，降低小并发交互长尾。  
**关键技术：**稀疏专家协同计算：建立 CPU 侧专家索引、fallback expert 和 expert prediction 能力，让 NPU 保持热专家与密集层连续执行。  
**未来趋势：**A+K 数据面会走向 profile 与 cost model 驱动的自动混合执行计划，按阶段、算子形态、状态热度和工具空窗动态选择 NPU 主算、CPU 辅算、重算或卸载。

#### 2）状态与内存协同
**问题：**权重、KV、Prefix、Context、Expert 同时挤压近端内存；状态下沉后如果恢复慢，TTFT/TPOT/JCT 尾延迟会被放大。  
**关键技术：**统一状态对象层：把 KV、Prefix、Context 和 Expert 抽象成可命名、可迁移、可恢复对象，支撑 Bailu、DDR、SSD 之间的定位、迁移和治理。  
**关键技术：**热温冷生命周期策略：以 next-use、工具阶段和恢复成本决定 pin、offload、discard 或 recompute，实现“放得下、恢复得回”。  
**关键技术：**跨层直通恢复流水：把 NPU-SSD 直通、CPU 预取聚合和异步 load/store 组织成恢复面，将冷状态随机 I/O 改造成可掩盖的数据回流。  
**未来趋势：**状态与内存协同会从引擎内部缓存优化演进为推理数据基础设施，KV、Prefix、Context 和 Expert 将被命名、观测、迁移、恢复和治理。

#### 3）控制面调度管理
**问题：**Request-level 调度看不到 Agent 的 session、workflow、工具阶段和未来恢复路径；CPU 工具队列与 NPU 推理队列会互相放大尾延迟。  
**关键技术：**语义元数据下沉：把 workflow、session、stage、tool、cache intent 和 expected resume time 下沉到 Runtime，让调度对象从 request 转为任务关键路径。  
**关键技术：**轻量策略运行时：构建 observe–score–predict–act 策略层，统一评估会话进度、KV 价值、专家热度、工具队列和 NPU 队列。  
**关键技术：**任务级优先级与准入：形成 resume-first、completion-aware、prefill-budget 与 CPU/NPU 联合 admission，优先保护高价值恢复任务。  
**未来趋势：**控制面会从请求队列调度器演进为 Agent Runtime 操作系统，以 session、program、workflow 为基本对象优化任务完成时间、SLO goodput、恢复优先级和状态价值。

#### 4）Trace 与仿真闭环
**问题：**没有真实 Trace 与扰动实验，就无法判断 CPU offload、KV 分层、专家预取和 NPU-SSD 直通是否真的收益为正。  
**关键技术：**任务语义 Trace：构建覆盖 Task、Turn、Request、Tool、Memory、KV、Resource 和 Power 的统一事件链，把状态驻留和资源消耗对齐到任务路径。  
**关键技术：**收益判定 Cost Model：把 placement、迁移、重算、预取、直通和功耗上限纳入统一代价模型，输出 A+K 协同是否收益为正的边界。  
**关键技术：**规格反推仿真器：用单资源扰动和 what-if 扫描量化 CPU、DDR、SSD、UB、Bailu 对 JCT、P95/P99 和 Tasks/J 的敏感度。  
**未来趋势：**Trace 与仿真会从事后分析演进为软硬件协同设计输入，每个关键技术和硬件规格都应绑定 trace、扰动实验、cost model 和 what-if 结果。

### 底部硬件诉求横条
**硬件诉求：**Mini/DV100 Lite 用于验证阶段级 A+K 分工、SVE/OMP 短算子、KV/Prefix 分层和工具隔离；塔式/n+1 需把 Bailu、DDR5、SSD、UB、NPU-SSD 直通和 CPU 沙箱池做成可编排 tier；n+2 PIM+HMM 需用 HMM 承载大容量状态，用 PIM 承接 KV/激活近存高带宽访问，并提供 telemetry、QoS、统一编址与仿真模型。
