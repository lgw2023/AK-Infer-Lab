# AK-Infer-Lab

AK-Infer-Lab 是面向 Ascend NPU + Kunpeng CPU 的大模型推理实验栈。当前项目的主线不是构建一个通用 Agent 框架，而是围绕 DeepSeek-V4-Flash 在昇腾服务器上的可运行边界、性能瓶颈和硬件规格反推，建立一套可复现实验、可观测 trace、状态分层运行时原型和 what-if 仿真工具。

## 一句话目标

在项目目标服务器 Atlas 800T A2 8×64GB Ascend NPU 上，先对齐 vLLM-Ascend 官方 DeepSeek-V4-Flash W8A8-MTP 八卡部署口径，再以单卡/双卡极限场景为压力测试边界，系统评估 KV Cache 分层、Prefix 复用、MoE 专家热温冷分层、CPU/NPU 阶段级协同和硬件链路参数对 TTFT、TPOT、P95/P99、容量上限与能效的影响，最终形成下一代硬件规格建议。

## 核心判断

DeepSeek-V4-Flash 是 284B 总参数、13B 激活参数、1M context 的 MoE 模型。vLLM-Ascend 官方教程给出的 Ascend 路线是 `DeepSeek-V4-Flash-w8a8-mtp`，单机部署口径是 Atlas 800 A2 64GB×8 或 Atlas 800 A3 128GB×8。项目目标服务器是 Atlas 800T A2，需要在服务器上验证设备、镜像、驱动、CANN、torch-npu、vLLM-Ascend 和权重版本与官方口径的实际兼容关系。单张 64GB NPU 不能作为官方模型生产部署目标；单卡/双卡应定位为极限硬件实验，用于研究低比特、低上下文、低并发、KV/Prefix 下沉、专家分层和仿真反推。

外部事实按 2026-07-08 校验，稳定记录放在 `docs/SOURCES_AND_BOUNDARIES.md`。后续如果 vLLM-Ascend、DeepSeek 权重或 Ascend 镜像版本变化，先刷新来源边界，再改实验命令。

## 两类实验场景

### 场景 A：单机八卡官方基准

目标是形成 DeepSeek-V4-Flash 在 Ascend 上的可信基线。该场景采用官方 W8A8-MTP 权重、`--tensor-parallel-size 8`、`--enable-expert-parallel`、`--quantization ascend`、prefix caching、chunked prefill、MTP speculative decode 等官方部署要素。输出不是单次 tokens/s，而是完整的性能和硬件画像：请求级延迟、vLLM server stats、NPU device timeline、AI Core task、HBM/KV 占用、H2D/D2H、HCCL/HCCS、CPU/DRAM/SSD 和 prefix/KV/MoE 状态指标。

### 场景 B：单卡/双卡极限硬件实验

目标不是宣称“单卡跑满 DeepSeek-V4-Flash”，而是回答为什么跑不下、哪些分层技术能推迟失效、哪些硬件参数最敏感。该场景可以从小模型和中型 MoE 开始，逐步进入 DeepSeek-V4-Flash 的切片、低比特、模拟专家池或真实低比特变体。成功标准是低上下文 smoke、少量 token 生成、专家/KV/传输 trace 完整、瓶颈可归因，而不是 1M context 或稳定生产 serving。

## 技术主线

1. **KV / Prefix / Context 分层管理。** 先验证 vLLM-Ascend KV Cache CPU Offload 和 prefix cache，再接 UCM / Mooncake / LMCache 思路，把 KV、Prefix、Context 从引擎内部缓存升级为可迁移、可恢复、可观测的状态对象。
2. **MoE 专家热温冷分层。** 先做 expert routing trace，再实现 hot expert HBM 常驻、warm expert DRAM/DUMA 回温、cold expert SSD 恢复。所有策略都必须用 expert hit rate、miss penalty、prefetch lead time 和 wrong prefetch bytes 约束。
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
  工作记录与进度笔记本/
    README.md                        # 工作笔记本入口
    01_工作记录.md
    02_阶段计划.md
    03_阶段性进展.md
    04_结果与问题点.md
    05_下一步行动指导.md
    p1_inference_contracts/          # prompt、schema、handoff、fixture
    runtime_trace_smokes/            # smoke 与 profiler run 归档
  docs/
    PROJECT_CHARTER.md
    DEEPSEEK_V4_FLASH_ASCEND_PLAN.md
    TECHNICAL_ARCHITECTURE.md
    EXPERIMENT_PLAN.md
    METRICS_AND_TRACE_SCHEMA.md
    HARDWARE_FEEDBACK.md
    SOURCES_AND_BOUNDARIES.md
```

## 当前状态摘要

项目已经完成从服务器可观测能力体检到小模型 vLLM API/msprof 受控 trace 的早期闭环：Qwen3.5-4B 在单卡上完成 transformers 与 vLLM smoke；长 prompt 4K/8K/12K/16K envelope 已打通；vLLM OpenAI API server 的 burst/continuous 请求入口已跑通；prefix-cache on/off 对照、msprof 采集、request window 与 device SQLite 时间字段直接 overlap、request-device 聚合加速和固定 64 tokens 受控复现已完成。下一阶段应从“能采集”进入“能判读”，再进入 DeepSeek-V4-Flash 八卡基准和 MoE/KV 状态分层实验。

## 不做什么

本项目不在第一阶段运行真实 Coding Agent，不评估工具调用质量、仓库修改质量或多 Agent 规划能力；不把单卡 64GB 写成 DeepSeek-V4-Flash 官方模型可生产部署；不把冷存储随机小块读取放入逐 token 热路径；不在缺少 microbench 和 trace 证据时宣称 CPU/NPU 协同收益。

## 最小开工路径

1. 以当前 P1.27 受控 readout 为收束点，确认 prefix-cache on/off 的 request-device raw delta 可读。
2. 形成 `benchmarks/deepseek_v4_flash/a2_8card_w8a8_mtp_baseline.md`，只定义八卡实验，不先跑单卡幻想实验。
3. 新增 DeepSeek-V4-Flash 专项 workload：384K/128K/32K/8K 分级，不直接上 1M。
4. 在中型 MoE 上补齐 expert routing trace，再把专家分层策略迁到 DeepSeek-V4-Flash。
5. 将 KV CPU Offload、UCM、Mooncake SSD offload 分别作为 P1、P2、P3 能力，而不是一次性混入同一个实验。
