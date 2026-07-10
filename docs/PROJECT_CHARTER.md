# AK-Infer-Lab 项目 Charter

## 1. 项目定位

AK-Infer-Lab 是一个面向 Ascend NPU + Kunpeng CPU 小算力系统的大模型推理实验与硬件规格反推项目。项目以 DeepSeek-V4-Flash 为核心牵引模型，同时保留 Qwen、GLM、DeepSeek-Distill 和中型 MoE 作为可控分阶段模型。项目关注模型推理链路本身：prefill、decode、attention、MLP/MoE、KV Cache、Prefix Cache、expert dispatch、copy-compute overlap、runtime queue 和硬件链路。

本页标准术语以 `AK 协同/` 为来源库：Prefill/Decode 与 TTFT/ITL 对齐 vLLM 官方文档快照，KV Cache CPU Offload/UCM 对齐 vLLM-Ascend 官方文档，External KV Cache 与分层存储对齐 LMCache/Mooncake，MoE Expert Offload / Expert Cache 对齐 KTransformers、FineMoE、DALI、FluxMoE 等论文，HCCL collective 对齐 vLLM-Ascend 官方资料和 CCL-Bench。来源只用于命名和机制对齐，不代表这些机制已在本机验证或收益为正。

## 2. 目标

项目目标分为三层。

第一层是**可信基准**：在 Atlas 800 A2 / Atlas 800T A2 单机 8×64GB Ascend NPU 上，建立 DeepSeek-V4-Flash 官方 mixed FP8+FP4 checkpoint 的可复现实验基线。当前必须先关闭四卡新栈 runtime gate，再单独授权八卡；输出包括命令、环境、模型版本、并行策略、采样参数、请求计划、trace、server stats、msprof 结果和 request-device 聚合。

第二层是**极限边界**：在单卡或双卡硬件条件下，研究哪些低比特、低上下文、低并发、KV Cache CPU Offload / External KV Cache、MoE Expert Offload / Expert Cache 和 CPU/NPU 协同机制能够让 DeepSeek-V4-Flash 的局部或压缩形态进入可运行边界。该层不承诺生产服务；瓶颈归因只能在 request-token-operator-stall 证据闭合后输出。

第三层是**规格反推**：通过 controlled replay、microbench、state object trace 和 simulator what-if，反推下一代硬件应优先处理哪些参数：近端内存容量、近端内存带宽、主存带宽、NPU-CPU 互联、SSD I/O、NPU-SSD 直通、HCCS/HCCL、CPU 核数、PIM/HMM、计数器与运行时可观测接口。

## 3. 非目标

本项目不把真实 Coding Agent、工具执行、浏览器自动化、仓库读写代理、多 Agent 编排、代码质量评测作为第一阶段目标。静态 prompt workload 只用于近似 Agent 风格推理负载，不代表真实 Agent 端到端系统。

本项目不把 CPU 作为通用主算设备。Kunpeng 的优先角色是 External KV Cache / state-object management（项目内概括为“状态底座”）、metadata manager、prefetch planner、I/O aggregator、profiler/simulator host、少量可重叠冷路径和可证明收益为正的小算子。

本项目不把 SSD cold tier、NPU-SSD 直通或完整物理 P/D 分离作为 P0/P1 前置条件。SSD 和远端存储首先是容量层，只有在 chunk/object I/O、异步、预取和 tail-latency 控制成立后才能进入更靠近热路径的设计。

## 4. 目标硬件

当前主服务器口径：

```text
OS: Ubuntu 22.04 / aarch64
CPU: Kunpeng-920, 4 socket × 48 cores, 192 logical cores
NPU: Ascend 910B1 × 8
HBM: 64GB per NPU, 512GB aggregate but not a single shared memory pool
Memory: ~1.5TiB DRAM
Storage: multiple 7TB NVMe disks
CANN: 9.0.0 as validated baseline
vLLM-Ascend: validated import and API smoke path
```

八卡场景使用 8 张 64GB NPU 作为 TP/EP/DP/CP 可组合的分布式近端容量池。单卡/双卡场景必须按照 64GB 或 128GB 近端容量单独建模，不得把整机 512GB 当成单卡统一显存。

事实边界：
- vLLM-Ascend 官方 DeepSeek-V4-Flash 教程的明确单机口径是 Atlas 800 A2 64GB×8 或 Atlas 800 A3 128GB×8。
- 本项目目标服务器记录为 Atlas 800T A2 / 8×910B1 / 64GB HBM per card。它与官方 A2 口径的兼容性必须由服务器侧容器、驱动、CANN、torch-npu、vLLM-Ascend 和模型权重 smoke 逐项确认。
- 当前本地机器是外部开发机，本地容器或文档核查不能替代真实 Ascend 服务器验收。

## 5. 阶段划分

| 阶段 | 名称 | 核心问题 | 交付物 | 不输出 |
| --- | --- | --- | --- | --- |
| P0-P4 | 基础数据资产与观测闭环 | 服务器能测什么，请求/runtime/device 能否对齐 | observability profile、hardware microbench、Qwen/vLLM trace 与 readout | DeepSeek 八卡性能和优化结论 |
| P5 | DeepSeek runtime gate、八卡启动与 128K smoke | 官方 mixed checkpoint 能否先在固定新栈拉起，再达到最高哪档上下文 | readiness、完整启动命令、context ladder、green/yellow/red 状态 | controlled benchmark、瓶颈归因 |
| P6 | 单机八卡 controlled baseline | 可否建立可复现 reference point | unprofiled 性能、profiled evidence、单变量 A/B | 单卡部署承诺、无证据因果结论 |
| P7 | 单卡/双卡极致硬件边界 | 64GB/128GB 下容量、格式、kernel、通信和恢复边界在哪里 | boundary report、compatibility matrix、simulator calibration | full model official deployment 承诺 |
| P8 | 分层工程原型 | KV/Prefix 与 Expert 状态能否被观测、统一建模并分阶段迁移 | capability matrix、StateObject trace、KV real path、expert trace/static placement/tier simulation | 一步到位的生产框架、SSD 逐 token 热路径 |
| P9 | 规格反推 | 下一代硬件优先改什么 | sensitivity report、validated simulator、hardware ask matrix | 无 trace/microbench 支撑的泛泛趋势判断 |

## 6. 里程碑验收

每个里程碑必须有三类证据：

1. **可复现命令**：完整环境变量、模型路径、并行参数、采样参数、workload manifest。
2. **机器可读结果**：JSON/JSONL/TSV/YAML，能被后续脚本读取，不只保留截图和文字。
3. **边界说明**：明确该实验不能证明什么，尤其是 smoke、benchmark、profile、归因和优化结论之间的边界。

## 7. 设计原则

- 先 profile，再优化。
- 先八卡官方基准，再单卡极限探索。
- 先锁定来源和版本，再写服务器命令。
- 先 KV/Prefix DRAM warm tier，再 SSD cold tier。
- 先 expert trace，再 expert offload。
- 先逻辑 P/D 与队列隔离，再物理 P/D。
- 先 request-device 时间对齐，再做瓶颈归因。
- 所有 A+K 协同机制必须说明对象、链路、重叠窗口、收益边界和失败条件。
- 所有项目内中文概括首次出现时都要同时给出 `AK 协同/` 中可检索的标准术语、来源类型和适用边界；项目内概括不作为新的外部技术名词。
- 任何指标卡或阶段结论都必须标注 Scope 与 Not Claim；当前 P0-P4 不得输出 compute-bound、memory-bound、queue-bound、scheduler-bound 或 AI Core / AIV / MTE bottleneck 归因。
