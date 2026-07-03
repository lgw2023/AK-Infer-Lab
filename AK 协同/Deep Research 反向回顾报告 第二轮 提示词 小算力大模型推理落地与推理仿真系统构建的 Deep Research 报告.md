请进行一次面向“小算力大模型推理落地与推理仿真系统构建”的系统性 Deep Research。不要再泛化综述所有 Agent Serving、所有多模态、所有异构系统论文；本轮任务要围绕非常具体的工程矛盾展开：

核心目标：
1. 如何在小算力一体机 / Mini 工作站 / 塔式服务器 / 1–4 卡小服务器 / 2–8 节点小集群上实现大模型推理；
2. 如何利用 CPU、HBM/GDDR/Bailu、DRAM/DDR/CXL、SSD/NVMe、GPU/NPU/加速卡之间的协同，实现模型“放得下、跑得快、并发上得去”；
3. 如何构建模型推理算力仿真系统，基于硬件实测数据、模型结构和场景 workload，预测不同部署策略的 TTFT、TPOT、吞吐、并发、显存占用、DDR/SSD 流量、能耗与瓶颈。

请重点搜索 2025～2026 年发表或公开的学术论文、预印本、OpenReview、arXiv、官方技术博客、工程框架文档和 artifact。会议范围包括 ICLR, AAAI, ICML, NeurIPS/NIPS, MLSys, OSDI, SOSP, NSDI, USENIX ATC, FAST, EuroSys, SoCC, Middleware, ASPLOS, ISCA, MICRO, HPCA, SC，以及相关 SIGMOD/VLDB/CIDR、MobiSys/SenSys/SEC/IoTDI、工业博客与主流开源框架。

一、研究主题收敛范围

本轮只关注以下五大方向。

方向 A：CPU 可卸载计算与模型内协同计算
请重点找：
- CPU 参与 attention、decode、gating、FFN、MoE expert、短矩阵、小 batch matmul、outlier block、sparse block、rerank、embedding、token selection、KV selection 的论文；
- CPU 与 GPU/NPU 的 hybrid execution、cooperative computation、asymmetric pipeline、load-aware scheduling、profiling-informed scheduling；
- CPU gating / FFN 加速、CPU-side router/gate、CPU fallback expert、CPU-side low-frequency expert compute；
- CPU 参与时的收益边界：什么时候计算收益大于 PCIe/UB/NVLink/CXL 传输、DDR 访问、格式转换、同步与 host runtime overhead。

重点论文线索包括但不限于：
NEO, FlexInfer, LIA, APEX, HybridGen, llm.npu, HeteroInfer / HeteroLLM, KTransformers, Fiddler, HybriMoE, DAOP, CoX-MoE, DALI, Challenging GPU Dominance, PowerInfer-2, Q-Infer, SuperInfer。

方向 B：MoE 专家权重卸载、预取、缓存与冷热判断
请重点找：
- MoE expert offloading、expert paging、expert cache、expert prefetch、expert hotness prediction、routing-aware cache；
- 热专家常驻 HBM，温专家在 DRAM/CXL，冷专家在 SSD/NVMe 或 remote store 的系统；
- expert hit rate、expert miss penalty、prefetch accuracy、prefetch lead time、expert cache replacement；
- CPU 侧 fallback expert、CPU pre-calculation、CPU expert execution；
- Prefill 与 Decode 阶段 expert 策略是否不同；
- 如何准确预测 / 计算冷热专家权重或其他参数块；
- 专家权重加载和 KV/激活/计算之间如何流水重叠。

重点论文线索包括但不限于：
KTransformers, Fiddler, HybriMoE, MoE-Lightning, FineMoE, FluxMoE, FloE, DAOP, DALI, DuoServe-MoE, CommitMoE, MoE-Infinity, ProMoE, Mixtral-Offloading, CoX-MoE。

方向 C：KV Cache 容量管理、卸载、预取、恢复与分层内存
请重点找：
- KV / Prefix / Context cache 管理；
- PagedAttention、Automatic Prefix Caching、RadixAttention、HiCache、LMCache、Mooncake、UCM、vLLM KV Connector、NIXL、TensorRT-LLM KV reuse；
- HBM/GDDR/Bailu、CPU DRAM/DDR、CXL memory、SSD/NVMe、remote KV store 的分层；
- KV offload、prefetch、restore、recompute、compression、eviction、pinning、TTL、prefix reuse；
- KV 热/冷判断、reuse distance、reuse probability、cache hit/miss prediction；
- SSD-backed KV、CXL-backed KV、GPU/NPU-direct storage、object layout、batch I/O、CPU bounce buffer；
- KV 容量扩展如何帮助增加并发，如何影响 TTFT / TPOT / P95/P99。

重点论文线索包括但不限于：
Mooncake, LMCache, SGLang HiCache, vLLM APC / KV Connector / NixlConnector, TensorRT-LLM KV reuse / disaggregated serving, UCM for vLLM-Ascend, Beluga, ITME, Tutti, SolidAttention, ECHO, IMPRESS, KVCache Cache in the Wild, InfiniGen, KVPR, CacheBlend, CacheSlide, HCache, Jenga, Symphony, SGLANG-LSM。

方向 D：硬件流水线、互联带宽、并发提升与部署策略
请重点找：
- Prefill / Decode / Encode-Prefill-Decode 分离；
- 单机、多卡、小集群上的 pipeline parallelism、asynchronous pipeline、compute-transfer overlap；
- GPU/NPU ↔ CPU、GPU/NPU ↔ SSD、CPU ↔ SSD、GPU/NPU ↔ CXL、GPU/NPU ↔ remote KV store 的数据路径；
- PCIe / NVLink / CXL / RoCE / HCCS / HCCL / UB / DMA / GDS / NIXL 等互联或数据搬运抽象；
- 如何通过 batch、continuous batching、request routing、phase-aware scheduling、KV-aware routing、expert-aware scheduling 提高并发；
- 小算力条件下增加并发的瓶颈：HBM 容量、DRAM 带宽、SSD IOPS、CPU core、interconnect、scheduler overhead、KV restore stall；
- P/D 或 E/P/D 在什么并发、上下文、模型规模下收益为正，什么时候不赚钱。

重点论文线索包括但不限于：
DistServe, Splitwise if valid, Mooncake, vLLM PD, TensorRT-LLM Disaggregated Serving, NVIDIA Dynamo/NIXL, SGLang EPD, Cronus, ModServe, EPDServe, HydraInfer, TriInfer, SuperInfer, JITServe, Symphony, ServeGen, DroidSpeak, Marconi, BatchLLM, BOute。

方向 E：推理算力仿真系统、性能建模与硬件实测方法
这是本轮最重要方向之一。请重点找：
- LLM serving simulator、discrete-event simulator、operator-level simulator、kernel-level simulator、hardware-aware simulator；
- Roofline model、memory-bandwidth model、communication model、host overhead model、queueing model、phase-aware model；
- Profiler / trace / eBPF / operator timeline / GPU/NPU counter / CPU counter / SSD I/O counter / power telemetry；
- 基于实测 microbenchmark 反推模型推理效率的方法；
- 如何把模型结构参数、算子 shape、精度、batch、context length、MoE expert 路由、KV 长度映射成硬件资源需求；
- 如何仿真 CPU offload、KV offload、expert prefetch、PD/EPD、SSD/CXL tiering、并发调度；
- 如何用仿真预测 TTFT、TPOT、throughput、goodput、P95/P99、HBM 占用、DRAM 流量、SSD IOPS、interconnect bandwidth、energy、Tasks/J；
- 如何校验仿真准确性：与实机 profile 对齐、误差范围、benchmark workload、trace replay。

重点论文线索包括但不限于：
KernelSight-LM, Kareto, ProfInfer, ServeGen, BurstGPT, CCL-Bench, MLCommons Chakra, TokenPowerBench, Characterizing LLM Inference Energy-Performance Tradeoffs, Frontier simulator, LLMServingSim, OServe, MorphServe, Benchmark/Trace/Performance Modeling 相关论文。

二、检索方式要求

请使用三种方式交叉检索。

方式 1：按会议逐项搜索
对以下会议逐个检索官方 accepted papers / proceedings / technical program / OpenReview：
- ICLR 2025 / 2026
- AAAI 2025 / 2026
- ICML 2025 / 2026
- NeurIPS 2025 / 2026
- MLSys 2025 / 2026
- OSDI 2025 / 2026
- SOSP 2025
- NSDI 2025 / 2026
- USENIX ATC 2025 / 2026
- FAST 2025 / 2026
- EuroSys 2025 / 2026
- SoCC 2025 / 2026
- Middleware 2025 / 2026
- ASPLOS 2025 / 2026
- ISCA 2025 / 2026
- MICRO 2025 / 2026
- HPCA 2025 / 2026
- SC 2025 / 2026
- SIGMOD / VLDB / CIDR 2025 / 2026
- MobiSys / SenSys / SEC / IoTDI 2025 / 2026

每个会议给一个小表：
1. 会议名称；
2. 强相关论文；
3. 中相关论文；
4. 未发现强相关时明确写“未发现直接相关论文”；
5. 是否需要人工复核；
6. 官方来源链接。

方式 2：按机制关键词搜索
必须使用以下关键词组合，并可自行扩展：

CPU 计算与 FFN / gating：
- CPU GPU collaborative LLM inference
- CPU assisted attention LLM
- CPU offloading online LLM inference
- CPU fallback expert MoE
- CPU FFN acceleration LLM inference
- CPU gating MoE inference
- CPU side router MoE
- CPU GPU hybrid inference MoE
- short matrix CPU GPU LLM inference
- outlier block CPU GPU LLM
- sparse block CPU GPU inference
- FFN offload CPU LLM
- selective CPU compute LLM serving

MoE 专家：
- MoE expert offloading CPU GPU
- MoE expert prefetch LLM serving
- expert paging MoE inference
- expert cache replacement MoE
- expert hotness prediction MoE
- routed expert CPU fallback
- MoE expert weight tiering DRAM SSD
- MoE expert miss penalty
- MoE inference memory constrained GPU
- local PC MoE inference offloading

KV 与分层内存：
- KV cache offload CPU memory SSD
- external KV cache LLM serving
- KV cache tiering DRAM SSD CXL
- GPU direct storage KV cache
- NPU SSD direct storage KV cache
- SSD-backed KV cache LLM
- CXL memory LLM inference
- prefix cache offload LLM
- KV cache restore latency
- KV prefetch prediction LLM
- KV recomputation vs offload
- KV cache hit rate workload characterization

硬件流水与并发：
- prefill decode disaggregation
- encode prefill decode multimodal serving
- KV transfer connector LLM serving
- compute communication overlap LLM inference
- PCIe bottleneck LLM offloading
- NVLink CXL LLM serving
- continuous batching KV cache offload
- throughput goodput LLM serving hardware aware
- phase-aware scheduling LLM serving
- memory-aware routing LLM serving

仿真与评测：
- LLM serving simulator
- hardware-aware LLM serving simulator
- LLM inference performance model
- LLM inference cost model
- LLM serving profiler eBPF
- LLM serving trace replay
- model inference hardware simulation
- roofline model LLM inference
- discrete event simulator LLM serving
- KV cache tiering simulator
- energy model LLM inference
- power benchmark LLM serving
- hardware parameter back-solving LLM inference

方式 3：按已知论文做引用扩展
请从以下论文 / 系统出发，查引用链和同 session 论文：
NEO, FlexInfer, LIA, APEX, HybridGen, llm.npu, HeteroInfer/HeteroLLM, KTransformers, Fiddler, HybriMoE, MoE-Lightning, FineMoE, FluxMoE, DALI, DAOP, FloE, DuoServe-MoE, Mooncake, LMCache, SGLang HiCache, vLLM KV Connector/NIXL, TensorRT-LLM, UCM, Tutti, Beluga, ITME, SolidAttention, ECHO, DistServe, Cronus, HydraInfer, EPDServe, ModServe, KernelSight-LM, Kareto, ProfInfer, ServeGen, BurstGPT, CCL-Bench, Chakra, TokenPowerBench, Frontier simulator。

三、纳入与排除标准

强相关：
- 直接涉及 CPU 参与模型计算、gating、FFN、attention、MoE expert、fallback compute；
- 直接涉及 MoE 专家权重卸载、预取、分页、热度预测、CPU fallback、expert cache；
- 直接涉及 KV cache 容量管理、offload、restore、prefetch、prefix reuse、CXL/SSD tiering；
- 直接涉及模型参数、expert、KV、activation、latent 等状态在 HBM/DRAM/CXL/SSD 之间移动；
- 直接涉及硬件流水线、互联带宽、PD/EPD、transfer overlap、concurrency scaling；
- 直接涉及推理仿真、性能模型、trace/profiler、hardware-aware cost model、energy model。

中相关：
- 主要是 Agent / workflow-aware serving，但能影响 KV 生命周期、工具等待期间 KV pin/offload；
- 主要是多模态/视频，但涉及 stage disaggregation、latent/cache、codec bottleneck；
- 主要是量化/稀疏/推测解码，但明确改变 CPU/GPU/NPU 分工或内存状态路径。

弱相关 / 排除：
- 纯算法，没有系统实现或硬件路径；
- 纯 kernel，不涉及 offload、状态、并发或建模；
- 纯 Agent 应用框架，不涉及模型推理资源；
- 纯产品宣传，没有论文、代码、文档或可核验数据。

四、每篇强相关论文的输出字段

对每篇强相关论文，请输出如下字段：

1. 论文名称；
2. 作者机构；
3. 会议 / 来源；
4. 发表时间；
5. 状态：正式发表 / 预印本 / OpenReview submission / workshop / 官方文档 / 工业博客 / 开源系统；
6. 官方链接；
7. 研究背景需求；
8. 要解决什么核心问题；
9. 归属方向：
   - CPU 可卸载计算；
   - MoE 专家权重管理；
   - KV Cache 容量管理；
   - 硬件流水与并发；
   - 推理仿真与性能建模；
10. 核心贡献；
11. 核心策略与方法；
12. 改动系统层级：
   - Model graph；
   - Runtime；
   - Scheduler；
   - KV manager；
   - Expert manager；
   - Storage/data plane；
   - Kernel；
   - Interconnect / DMA；
   - Simulator / Profiler；
13. CPU 角色：
   - host；
   - scheduler；
   - state manager；
   - memory tier；
   - I/O aggregator；
   - gating / router compute；
   - FFN compute；
   - attention compute；
   - expert compute；
   - fallback compute；
   - codec / postprocess；
14. 被管理的对象：
   - model weight；
   - FFN；
   - gate/router；
   - MoE expert；
   - KV cache；
   - prefix；
   - activation；
   - embedding；
   - latent/noise；
   - adapter；
   - checkpoint；
15. 数据驻留层级：
   - HBM/GDDR/Bailu；
   - CPU DRAM/DDR；
   - CXL memory；
   - SSD/NVMe；
   - remote memory/store；
16. 数据搬运路径：
   - GPU/NPU ↔ CPU；
   - GPU/NPU ↔ SSD；
   - CPU ↔ SSD；
   - GPU/NPU ↔ CXL；
   - GPU/NPU ↔ remote store；
   - 是否经过 CPU bounce buffer；
   - 是否支持 direct path；
17. 硬件平台：
   - GPU/NPU 型号；
   - CPU 型号；
   - CPU ISA / AMX / AVX-512 / SVE / SIMD；
   - HBM/显存容量；
   - DRAM 容量/带宽；
   - SSD/NVMe；
   - PCIe/NVLink/CXL/RoCE/UB/HCCL/HCCS；
18. 模型与 workload：
   - 模型名称；
   - 参数规模；
   - Dense / MoE / VLM / Diffusion；
   - context length；
   - batch；
   - concurrency；
   - online/offline；
   - coding/agent/RAG/video；
19. baseline；
20. 指标：
   - TTFT；
   - TPOT / ITL / TBT；
   - throughput / goodput；
   - concurrency；
   - P95/P99；
   - memory saving；
   - KV hit rate；
   - expert hit rate；
   - prefetch accuracy；
   - restore latency；
   - PCIe/DRAM/SSD bytes；
   - SSD IOPS；
   - energy / tokens/J / Tasks/J；
   - simulation error；
21. 结果收益与评估方式；
22. 正收益原因；
23. 反噬风险；
24. 对“小算力大模型推理”的启发；
25. 对“推理算力仿真系统”的启发；
26. 是否适合迁移到 Ascend NPU + Kunpeng CPU：高 / 中 / 低；
27. 可靠性等级：
   - A：正式论文 + artifact / 官方实现；
   - B：正式论文但 artifact 不明确；
   - C：arXiv / OpenReview / workshop；
   - D：工业博客 / 官方文档；
   - E：二手资料，需人工复核；
28. 一句话总结。

五、输出报告结构

请按以下结构输出：

1. 执行摘要
- 10 条以内；
- 必须围绕“大模型小算力推理”和“推理仿真系统”；
- 不要泛泛讲 agent serving。

2. 研究问题地图
用表格列出：
- 方向；
- 核心瓶颈；
- 代表论文；
- 主要方法；
- 涉及硬件组件；
- 解决的是“放得下 / 跑得快 / 并发上得去 / 能仿真预测”中的哪一类问题。

3. 逐会议查缺补漏表
每个会议都要写：
- 强相关论文；
- 中相关论文；
- 未发现；
- 需人工复核；
- 来源链接。

4. 论文总表
按“方向 + 会议”组织，而不是简单按时间排序。

5. 分方向详细分析
必须包含：
A. CPU 可卸载计算与模型内协同计算；
B. MoE 专家权重卸载、预取、缓存与冷热判断；
C. KV Cache 容量管理、卸载、恢复、预取与分层内存；
D. 硬件流水线、互联带宽、并发提升与部署策略；
E. 推理算力仿真系统、性能建模与硬件实测方法。

每个方向都回答：
- 业内关注的问题是什么；
- 为什么 2025–2026 年变重要；
- 代表论文分别怎么解决；
- 哪些路线已经形成共识；
- 哪些路线仍有争议；
- 对小算力一体机的启发；
- 对 Ascend + Kunpeng 的迁移难点；
- 对仿真系统输入参数、输出指标、校验方法的启发。

6. 专门章节：推理仿真系统设计参考
请基于论文总结出一个可落地的仿真系统设计。

必须包括：
- 输入 1：模型结构参数
  - layers；
  - hidden size；
  - FFN size；
  - attention heads；
  - KV size per token；
  - MoE experts；
  - top-k；
  - expert size；
  - precision；
  - activation / workspace；
- 输入 2：硬件实测参数
  - NPU/GPU matmul throughput by shape/precision；
  - CPU matmul/FFN/expert throughput；
  - CPU SIMD/SVE/AMX microbenchmark；
  - HBM bandwidth；
  - DRAM bandwidth；
  - SSD sequential/random bandwidth and IOPS；
  - PCIe/UB/NVLink/CXL bandwidth/latency；
  - DMA overhead；
  - host runtime overhead；
  - power data；
- 输入 3：workload 参数
  - prompt length；
  - output length；
  - batch；
  - concurrency；
  - session reuse；
  - KV reuse probability；
  - expert hotness distribution；
  - request arrival distribution；
  - agent/tool idle time；
- 建模模块：
  - prefill model；
  - decode model；
  - KV cache memory model；
  - MoE expert placement model；
  - CPU offload model；
  - SSD/CXL tiering model；
  - interconnect transfer model；
  - scheduler / queueing model；
  - energy model；
- 输出：
  - TTFT；
  - TPOT；
  - throughput；
  - max concurrency；
  - HBM occupancy；
  - DRAM traffic；
  - SSD IOPS；
  - transfer bottleneck；
  - pipeline bubbles；
  - expert miss penalty；
  - KV restore stall；
  - energy per token / per task；
  - bottleneck attribution；
- 校验方法：
  - microbenchmark calibration；
  - operator trace alignment；
  - end-to-end replay；
  - per-stage error；
  - sensitivity analysis；
  - what-if validation。

7. 专门章节：收益边界与反例
必须回答：
- CPU gating / FFN / expert compute 什么时候不值得做；
- expert offload 什么时候不值得做；
- KV offload 什么时候不值得做；
- CXL 什么时候不适合做热层；
- SSD direct path 什么时候会被 tiny I/O 反噬；
- P/D 拆分什么时候不赚钱；
- 增加并发什么时候会从算力瓶颈变成容量/带宽瓶颈。

8. 专门章节：Ascend NPU + Kunpeng CPU 可迁移路线
不要只说“可迁移”，要拆成：
- 纯软件可做；
- 需要 MindIE / vLLM-Ascend / CANN / UCM / Mooncake hook；
- 需要 Kunpeng CPU SIMD/SVE 能力；
- 需要 NPU↔CPU 低开销传输；
- 需要 NPU↔SSD direct path；
- 需要下一代硬件规格支持；
- 推荐原型优先级 P0/P1/P2。

9. 研究空白与创新机会
重点找：
- CPU gating / FFN offload 的系统论文是否不足；
- 专家冷热预测与硬件调度结合是否不足；
- Ascend + Kunpeng 的公开系统论文缺口；
- NPU-SSD direct storage 缺口；
- 小算力推理仿真系统缺口；
- KV / Expert / Weight / Latent 统一对象层缺口；
- 多模态 Noise Cache / rolling KV 分层回流缺口。

10. 精读清单
按 P0 / P1 / P2 列出最值得读的论文，每篇说明为什么。

11. 参考文献
必须给 primary source，标注状态，不要只给二手博客。

六、报告风格要求

- 中文输出，保留英文论文题名和术语；
- 结果数字必须带 baseline、模型、硬件、workload；
- 论文状态必须严格区分正式发表、预印本、OpenReview submission、官方文档、工业博客；
- 不要把 weakly related paper 塞进强相关；
- 不要再以 PPT 为目标；
- 输出要帮助我真正理解：业内具体在研究什么问题、怎么做、有什么结果、对小算力大模型推理和仿真系统有什么可迁移方法。