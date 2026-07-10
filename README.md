# AK-Infer-Lab

AK-Infer-Lab 是面向 Ascend NPU + Kunpeng CPU 的大模型推理实验栈。当前项目的主线不是构建一个通用 Agent 框架，而是围绕 DeepSeek-V4-Flash 在昇腾服务器上的可运行边界、待验证的性能瓶颈假设和硬件规格反推，建立一套可复现实验、可观测 trace、KV/Prefix/Expert memory tiering 原型和 what-if 仿真工具。

术语来源以 `AK 协同/` 资料库为准：`references/bibliography_inference_sim.md` 负责路由论文与官方资料，`references/web/` 保存 vLLM、vLLM-Ascend、MindIE、LMCache、Mooncake 等文档快照，`references/papers/` 保存系统论文。标准术语首次出现时必须同时说明来源类型和适用边界；项目内中文解释只作为阅读辅助，不作为新的外部技术名词。详细映射见 `docs/SOURCES_AND_BOUNDARIES.md`。

## 一句话目标

在项目目标服务器 Atlas 800T A2 8×64GB Ascend NPU 上，以 DeepSeek 官方 FP8 + FP4 experts 混合 checkpoint 建立可复现运行基线，再以单卡/双卡极限场景为压力测试边界，系统评估 KV Cache CPU Offload / External KV Cache、Prefix Cache、MoE Expert Offload / Expert Cache、CPU/NPU 阶段级协同和硬件链路参数对 TTFT、TPOT、ITL、E2EL、P95/P99、容量上限与能效的影响，最终形成下一代硬件规格建议。

## 核心判断

DeepSeek-V4-Flash 是 284B 总参数、13B 激活参数、1M context 的 MoE 模型。官方 checkpoint 的非 expert 权重为 FP8、expert 权重为 FP4。vLLM-Ascend 官方教程当前仍以 `DeepSeek-V4-Flash-w8a8-mtp` 展示 A2/A3 部署，但本项目已停止使用该 W8A8 对象；项目主线改为验证 vLLM-Ascend 新发布栈对官方 mixed checkpoint 的真实兼容性。单张 64GB NPU 不能作为完整模型生产部署目标；单卡/双卡仍定位为极限硬件实验。

DeepSeek 模型与 v0.18.0 首轮失败保留为历史证据；服务器的独立 `vLLM 0.20.2 / vLLM-Ascend 0.20.2rc1` 环境通过了 Qwen2.5 纯注意力 smoke，但官方 mixed checkpoint 在 `ModelConfig` 量化平台门被明确拒绝，早于权重加载、HBM 和 MTP。当前交接改为新建独立 `vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1` 环境，因为该发布 tag 已注册 `deepseek_v4_fp8` 及对应 Ascend FP8/FP4 scheme；服务器结果回来前仍不能写成 runtime ready。

当前主对象是服务器上的官方 `deepseek-ai/DeepSeek-V4-Flash`：46 个连续分片、约 `148.66 GiB`。ModelScope W8A8 目录的 70 分片 / `279.41 GiB` inventory 继续保留，但项目禁止启动、转换或作为 P5/P6 fallback。当前只授权 NPU 4-7 做新栈 TP4/EP runtime gate；四卡成功后，八卡 context ladder 仍需单独授权。

## 两类实验场景

### 场景 A：单机八卡官方基准

目标是形成 DeepSeek-V4-Flash 官方 mixed checkpoint 在 Ascend 上的可信八卡基线。模型量化由 checkpoint config 自动识别为 `deepseek_v4_fp8`，不得显式改写为 `--quantization ascend`；TP8、EP、prefix caching、chunked prefill 和 MTP 只有在四卡 runtime gate 通过并获得八卡授权后才逐项恢复。输出不是单次 tokens/s，而是完整的性能和硬件画像。

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

P0-P4 已建立硬件 microbench 与 Qwen3.5-4B / vLLM 推理观测数据资产。当前服务器交接为 `p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1_2026_0710`：完整同步 `main` 后，新建隔离 `0.22.1/0.22.1rc1` 栈，只用 NPU 4-7 先跑 `base_no_mtp`，成功后再跑 `mtp_on`，每个 profile 最多一个 `4096+64` 请求。W8A8 已退出项目执行；八卡 P5 与 P6 benchmark 仍未解锁。

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

1. P5 runtime gate：在独立 `vLLM 0.22.1+empty / vLLM-Ascend 0.22.1rc1` 栈上执行已授权 NPU 4-7 的官方 FP8/FP4 checkpoint TP4 最小拉起；任何失败按第一失败点停止，W8A8 不参与。四卡成功后仍等待独立八卡授权。
2. P6：从 P5 最终成功 command 冻结八卡 baseline，分开执行 unprofiled 性能、profiled evidence 和单变量 A/B。
3. P7：并行准备单卡/双卡边界校准，覆盖小模型、中型 MoE、DeepSeek 子图/partial shard、模拟 expert pool 和 simulator-only full model。
4. P8：先做 capability matrix 与 observe-only StateObject trace，再依次做 KV/Prefix 真实 DRAM warm tier、expert hotness/static placement、Expert Tier V0 simulation；MindIE 为 availability-gated 对照路。
5. P9：把 P0/P3 microbench 与 P6/P7/P8 trace bundle 合并，输出带置信度和软件前提的下一代硬件优先级。

P5-P9 稳定阶段契约见 `docs/EXPERIMENT_PLAN.md`，P8 详案见 `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`。
