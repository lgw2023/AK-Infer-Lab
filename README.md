# AK-Infer-Lab

AK-Infer-Lab 是面向 Ascend NPU + Kunpeng CPU 的大模型推理实验栈。当前项目的主线不是构建一个通用 Agent 框架，而是围绕 DeepSeek-V4-Flash 在昇腾服务器上的可运行边界、待验证的性能瓶颈假设和硬件规格反推，建立一套可复现实验、可观测 trace、KV/Prefix/Expert memory tiering 原型和 what-if 仿真工具。

术语来源以 `AK 协同/` 资料库为准：`references/bibliography_inference_sim.md` 负责路由论文与官方资料，`references/web/` 保存 vLLM、vLLM-Ascend、MindIE、LMCache、Mooncake 等文档快照，`references/papers/` 保存系统论文。标准术语首次出现时必须同时说明来源类型和适用边界；项目内中文解释只作为阅读辅助，不作为新的外部技术名词。详细映射见 `docs/SOURCES_AND_BOUNDARIES.md`。

## 一句话目标

在项目目标服务器 Atlas 800T A2 8×64GB Ascend NPU 上，以官方文档面向 A2/A3 的 DeepSeek-V4-Flash W8A8-MTP checkpoint 建立可复现运行基线，再以单卡/双卡极限场景为压力测试边界，系统评估 KV Cache CPU Offload / External KV Cache、Prefix Cache、MoE Expert Offload / Expert Cache、CPU/NPU 阶段级协同和硬件链路参数对 TTFT、TPOT、ITL、E2EL、P95/P99、容量上限与能效的影响，最终形成下一代硬件规格建议。

## 核心判断

DeepSeek-V4-Flash 是 284B 总参数、13B 激活参数、1M context 的 MoE 模型。官方原始 checkpoint 的非 expert 权重为 FP8、expert 权重为 FP4；但 vLLM-Ascend 当前把 MXFP4/MXFP8 MoE 路径限定在 Ascend 950，A2/A3 教程使用 `DeepSeek-V4-Flash-w8a8-mtp`。本项目据此停止 mixed checkpoint 的适配与执行探索，后续 P5/P6 只以 W8A8-MTP 为主对象。单张 64GB NPU 不能作为完整模型生产部署目标；单卡/双卡仍定位为极限硬件实验。

DeepSeek 模型与 v0.18.0、v0.20.2rc1 的失败保留为历史证据。独立 `vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1` 环境已依次关闭核心版本、插件路由、allocator 和 ACL 路径问题，四卡运行加载了 mixed checkpoint 的全部 46 个分片，随后在 `process_weights_after_loading` 命中 `customize_dtype is not supported by the current soc version`。该结果证明当前 910B1 路线不适合继续执行 MXFP4；W8A8-MTP 则已在后续八卡任务中建立 official context、unprofiled performance 与 profiled evidence 三层 reference。

当前主对象是服务器上的 `DeepSeek-V4-Flash-w8a8-mtp`：70 个连续分片、约 `279.41 GiB`。该体量超过四卡约 256 GiB 聚合 HBM；P6.1C-R1 已在 NPU 0-7 上把固定 64 输出的 official context 推到 131072，P6.1 与 P6.2 随后分别关闭 unprofiled 和 profiled reference。mixed checkpoint 的 46 分片 / `148.66 GiB` inventory 仅保留为历史诊断和来源记录，不做适配、转换或 fallback。

## 两类实验场景

### 场景 A：单机八卡官方基准

目标是形成 DeepSeek-V4-Flash W8A8-MTP 在 Ascend 上的可信八卡基线。模型使用 vLLM-Ascend A2/A3 参考路径和 `--quantization ascend`；当前 official context、unprofiled performance、profiled evidence、P6.3A matched MTP on/off 与 P6.3B-R4-R1 explicit Prefix Cache control 已建立。P6.3B 完整保留 query-positive/hit-zero、import-order red、repair green、invalid on-vs-on、root-squash blocked 与最终 explicit-control green lineage；最终机制结论限于 primary 9/9 positive hit，不从固定顺序或 boundary zero-hit 外推普遍性能收益。P6.3C 已因 frozen `4096 < 135168` 组合无法保持 Chunked Prefill off 的严格单变量而收口为 `blocked_p6_3c_not_strict_single_variable`。

### 场景 B：单卡/双卡极限硬件实验

目标不是宣称“单卡跑满 DeepSeek-V4-Flash”，而是回答为什么跑不下、哪些分层技术能推迟失效、哪些硬件参数最敏感。该场景可以从小模型和中型 MoE 开始，逐步进入 DeepSeek-V4-Flash 的切片、低比特、模拟专家池或真实低比特变体。成功标准是低上下文 smoke、少量 token 生成、专家/KV/传输 trace 完整、瓶颈可归因，而不是 1M context 或稳定生产 serving。

## 技术主线

1. **KV Cache CPU Offload / External KV Cache / Prefix Cache。** 先验证 vLLM-Ascend KV Cache CPU Offload 和 Prefix Cache，再评估 UCM、Mooncake 与 LMCache 等 External KV Cache / KV Cache Layer 机制。项目内可将其解释为“KV/Prefix 状态外部化与分层管理”，但对外保留标准术语。
2. **MoE Expert Offload / Expert Cache。** 先做 expert routing trace，再评估 hot expert HBM residency、warm expert DRAM tier 与 cold expert SSD/NVMe tier。所有策略都必须用 expert hit rate、miss penalty、prefetch lead time 和 wrong prefetch bytes 约束。
3. **CPU/NPU 阶段级协同。** NPU 承担密集主路径；Kunpeng 负责 tokenizer、sampling、runtime metadata、KV/prefix lookup、expert hotness prediction、prefetch planner、I/O aggregation 和少量可重叠冷路径。CPU 不默认承接主干 attention/FFN。
4. **可观测、仿真和硬件规格反推。** 所有实验都要落到统一 trace schema、experiment card、microbench profile 和 simulator what-if 表。项目最终交付不是单一优化技巧，而是能说明下一代硬件应该优先增加哪类容量、带宽、互联或直通能力的证据链。

## 当前仓库结构

```text
AK-Infer-Lab/
  README.md                         # 本项目总入口
  AGENTS.md                         # 开发和服务器交接规则
  tools/
    observability_profile/           # P0.5 服务器可观测能力体检
    inference_contracts/             # P1 请求/trace/workload/分析脚本
  benchmarks/
    deepseek_v4_flash/                # P5 卡片与后续 P6-P8 实验契约入口
  工作记录与进度笔记本/
    README.md                        # 工作笔记本入口
    01_工作记录.md
    02_阶段计划.md
    03_阶段性进展.md
    04_结果与问题点.md
    05_下一步行动指导.md
    10_P0_P4_阶段收尾评估.md
    11_P0_P4_阶段收尾报告.md
    12_P5_P9_后续阶段重排计划.md
    16_P6_阶段复盘与P6_3进入评估.md
    P6_阶段证据链仪表盘_2026_0715.html
    p1_inference_contracts/          # prompt、schema、handoff、fixture
    runtime_trace_smokes/            # smoke 与 profiler run 归档
    hardware_ceiling_runs/            # P0/P3 hardware ceiling sweep 归档
  docs/
    PROJECT_CHARTER.md
    DEEPSEEK_V4_FLASH_ASCEND_PLAN.md
    P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md
    TECHNICAL_ARCHITECTURE.md
    EXPERIMENT_PLAN.md
    METRICS_AND_TRACE_SCHEMA.md
    HARDWARE_FEEDBACK.md
    SOURCES_AND_BOUNDARIES.md
```

## 当前状态摘要

P0-P4 已建立硬件 microbench 与 Qwen3.5-4B / vLLM 推理观测数据资产。P5 mixed-checkpoint 四卡诊断已收敛到 910B1 SoC 不支持其 MXFP4 format-cast 路径；W8A8-MTP 已在八卡上完成 P6.1C-R1 official 131072 context、P6.1 unprofiled 18-cell performance reference、P6.2 三个代表性 profiled evidence cell、P6.3A matched MTP on/off 和 P6.3B-R4-R1 explicit Prefix Cache control。P8.1-R1 已由开发机接受 `green_p8_1_r1_official_mtp_observe_only_matrix`。P8.2-K0-R1 使用不变的 29-file raw evidence 离线修正 finalizer 后，15 项逐请求 predicate 均为 20/20，开发机已接受 `green_p8_2_k0_order_balanced_prefix_cache_baseline`；该结果仍不是 performance reference 或 offload evidence。K1 `OffloadingConnector + NPUOffloadingSpec` 冻结源路径保持 `blocked_p8_2_k1_frozen_stack_import_incompatible`。K1A 的 source/import/registration 门已过，但冻结 32 GiB/rank 在服务就绪前以 `aclrtMallocHostWithCfg / 207001` 失败，0/6 请求，开发机只接受为该容量点的 `red_p8_2_k1a_simple_cpu_offload_no_success`，不宣判普通 DRAM 不足、唯一 pinned-pool 根因或整个 connector 不支持。P6.3C 继续保持 strict-single-variable blocked。

P8 现显式分成两条并行依赖。P8.3-I0-R1 已在 bounded taxonomy 边界接受为
`green_p8_3_i0_r1_unclassified_taxonomy`，但 `1135` tensor / `12319364956 bytes` 的分类结果不能自动
补全 TP4 budget 或授权 I1。K1A-R1 probe-invalid red 保留；K1A-R2 的 same-run 8-rank geometry、
`32/64/96/128`-block pinned envelope 与离线 provenance replay 已由开发机接受为
`ready_p8_2_k1a_r2_allocator_capacity`。P8.2-K1A-R3 因 handoff 混淆 geometry summary 与 rendezvous
marker schema，在零 NPU/零请求处保留 provenance blocked。P8.2-K1A-R3-R1 随后通过 repaired
provenance，但其 mode runner 用 Bash `printf %q` 文本做命令身份，因开发机 Bash 3.2 与服务器 Bash 5.1
转义不同而在 vLLM 启动前停止，0/6 request；该结果只接受为 repository portability contract red，
不撤销 R2 capacity ready。P8.2-K1A-R3-R2 已证明 exact argv canonical JSON 与 R2 provenance
均通过，但 handoff 新增了服务器不存在的 vLLM-Ascend checkout 路径，故在零 NPU/零请求处保留
source-contract blocked。P8.2-K1A-R3-R2-R1 已进入真实 runtime：4K warmup 成功，32K prime 失败后首错停止，
8 worker 提交 `403691520` D2H bytes 但零 completion，H2D 未启动，cleanup/keep-alive restore clean。开发机只接受
`yellow_p8_2_k1a_r3_r2_r1_partial`，不接受 store/restore green。R3-R2-R2-R1 又在零 NPU 处因
`copy_blocks` 是 `ImportFrom` 而被旧 AST auditor 假阴性阻断；其回包同时声称没有直接异常和存在被捕获的
worker TypeError，故正式保留 `blocked_p8_2_k1a_r3_r2_r2_r1_source_or_observer_gate`，不直接重跑。
当前唯一服务器任务为 R3-R2-R2-R1-R1：先证明六文件 source binding/definition、runtime object identity 和
parent raw log 的结构化异常指纹；只有无直接异常或异常全部精确匹配已退役 observer 的 `wait_event` 缺陷时，
才在同一 `430604288 bytes/rank / 3444834304 bytes total` 上执行最多一次六请求 replay，零 retry；容量搜索、
行为 patch、第二 lifecycle、K2 与 P8.3-I1 均未授权。

边界必须保留：P0/P3 是合成硬件 microbench observed ceiling，不是模型推理 benchmark；P1.29/P1.31 是 vLLM OpenAI streaming client 口径下的 scoped facts，不是 MindIE native event；P1.30 是 whole-device HBM occupancy 和 process-group RSS/PSS readout，不是 per-request KV object bytes 或 HBM traffic。当前结果仍不支持 compute-bound、memory-bound、queue-bound、scheduler-bound、AI Core / AIV / MTE bottleneck 归因。

## 指标与声明边界

- 术语优先级为：`AK 协同/` 内的官方文档 / 框架资料 / benchmark 输出字段，其次是本地系统论文，最后才是项目内中文解释。项目内解释不替代 H2D/D2H、TTFT、TPOT、ITL、E2EL、KV Cache CPU Offload、External KV Cache、MoE Expert Offload 和 HCCL collective 等现有术语。
- 本页术语来源类型与边界：TTFT/ITL 和 Prefill/Decode disaggregation 对齐 vLLM 官方文档快照；KV Cache CPU Offload/UCM 对齐 vLLM-Ascend 官方文档快照；External KV Cache 与 memory tiering 对齐 LMCache/Mooncake 资料；MoE Expert Offload / Expert Cache 对齐 KTransformers、FineMoE、DALI、FluxMoE 等论文；HCCL collective 对齐 vLLM-Ascend release-note/KV Pool 快照。上述来源只证明术语和机制存在，不证明本机收益或带宽。
- 每个性能数字必须同时给出 `Scope`（模型、workload、size/tokens、pinned/sync、N 与 unit）和 `Not Claim`（当前证据不能支持的外推）。
- H2D/D2H 只表示 Host↔Device 拷贝方向；当前 `24.313915 / 26.480714 GB/s` 是 `size=1G, pinned=1, non_blocking=0` 且每次拷贝后 synchronize 的端到端 observed copy ceiling，不是 PCIe/UB 理论峰值、NPU-NPU 通信带宽或 copy-compute overlap 证据。
- ITL 在 P1.29/P1.31 中是 host streaming inter-chunk median per request；TPOT 为 `(response_end - first_token) / (generated_tokens - 1)`。二者都不是 NPU runtime native decode event。
- NumPy read/copy `5.332057 / 2.963189 GB/s` 是 Python/NumPy 软件路径下的 observed CPU memory path ceiling，不是 server DRAM hardware peak。
- 当前尚无 Atlas 800T A2 单机八卡 NPU-NPU interconnect 带宽实测；不得用 H2D/D2H 代替 pairwise P2P 或 HCCL all-reduce / all-gather / reduce-scatter / all-to-all 的 algbw / busbw。

## 不做什么

本项目不在第一阶段运行真实 Coding Agent，不评估工具调用质量、仓库修改质量或多 Agent 规划能力；不把单卡 64GB 写成 DeepSeek-V4-Flash 官方模型可生产部署；不把冷存储随机小块读取放入逐 token 热路径；不在缺少 microbench 和 trace 证据时宣称 CPU/NPU 协同收益。

## 最小开工路径

1. P5/P6 runtime、official context、unprofiled/profiled reference 与 matched controls 已关闭；mixed checkpoint 不再参与，P6.3C 保留严格单变量 blocked。
2. P8 KV/Prefix 线：P8.1-R1 与 K0 已 green，旧 K1 blocked，K1A 32 GiB/rank red，K1A-R1 probe-invalid red，K1A-R2 capacity ready，K1A-R3 provenance blocked，K1A-R3-R1 portable-argv contract red，K1A-R3-R2 source-contract blocked，K1A-R3-R2-R1 runtime partial yellow，R3-R2-R2 与 R3-R2-R2-R1 blocked provenance 保留；当前执行 R3-R2-R2-R1-R1 source binding + exception provenance + conditional same-capacity replay，K2 不授权。
3. P8 Expert/TP4 线：P8.3-I0 inventory 与 I0-R1 bounded taxonomy 已在各自窄边界 green；TP4 budget 仍 incomplete，P8.3-I1 hotness/runtime trace 未授权。
4. P7：并行准备单卡/双卡边界校准，覆盖小模型、中型 MoE、DeepSeek 子图/partial shard、模拟 expert pool 和 simulator-only full model。
5. P9：待 P7/P8 的真实 trace、inventory、simulation 与 TP4 closure 证据齐备后，合并 P0/P3 microbench，输出带置信度和软件前提的下一代硬件优先级。

P5-P9 稳定阶段契约见 `docs/EXPERIMENT_PLAN.md`，P8 详案见 `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`。
