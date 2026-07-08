# AK-Infer-Lab

AK-Infer-Lab 是面向 Ascend NPU + Kunpeng CPU 的大模型推理实验栈。当前项目的主线不是构建一个通用 Agent 框架，而是围绕 DeepSeek-V4-Flash 在昇腾服务器上的可运行边界、性能瓶颈和硬件规格反推，建立一套可复现实验、可观测 trace、状态分层运行时原型和 what-if 仿真工具。

## 一句话目标

在项目目标服务器 Atlas 800T A2 8×64GB Ascend NPU 上，先对齐 vLLM-Ascend 官方 DeepSeek-V4-Flash W8A8-MTP 八卡部署口径，再以单卡/双卡极限场景为压力测试边界，系统评估 KV Cache 分层、Prefix 复用、MoE 专家热温冷分层、CPU/NPU 阶段级协同和硬件链路参数对 TTFT、TPOT、P95/P99、容量上限与能效的影响，最终形成下一代硬件规格建议。

## 核心判断

DeepSeek-V4-Flash 是 284B 总参数、13B 激活参数、1M context 的 MoE 模型。vLLM-Ascend 官方教程给出的 Ascend 路线是 `DeepSeek-V4-Flash-w8a8-mtp`，单机部署口径是 Atlas 800 A2 64GB×8 或 Atlas 800 A3 128GB×8。项目目标服务器是 Atlas 800T A2，需要在服务器上验证设备、镜像、驱动、CANN、torch-npu、vLLM-Ascend 和权重版本与官方口径的实际兼容关系。单张 64GB NPU 不能作为官方模型生产部署目标；单卡/双卡应定位为极限硬件实验，用于研究低比特、低上下文、低并发、KV/Prefix 下沉、专家分层和仿真反推。

外部事实按 2026-07-08 校验，稳定记录放在 `docs/SOURCES_AND_BOUNDARIES.md`。后续如果 vLLM-Ascend、DeepSeek 权重或 Ascend 镜像版本变化，先刷新来源边界，再改实验命令。

当前后续实验登记两个 DeepSeek-V4-Flash 对象：ModelScope `DeepSeek-V4-Flash-w8a8-mtp` 已在本地 `/Volumes/Elements/DeepSeek-V4-Flash-w8a8-mtp` 下载完成，作为 P6 八卡 baseline 首选；官方 `deepseek-ai/DeepSeek-V4-Flash` 正在 `/Volumes/Elements/DeepSeek-V4-Flash` 下载，作为来源 checkpoint、转换/兼容性和单/双卡边界研究对象。用户会自行把模型目录拷贝到 Ascend 服务器；本地外置盘路径不等同于服务器路径。

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
  benchmarks/
    deepseek_v4_flash/                # P5 模型对象登记、readiness card 和 workload 模板
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
    TECHNICAL_ARCHITECTURE.md
    EXPERIMENT_PLAN.md
    METRICS_AND_TRACE_SCHEMA.md
    HARDWARE_FEEDBACK.md
    SOURCES_AND_BOUNDARIES.md
```

## 当前状态摘要

P0-P4 已按三类目标收尾：服务器环境与硬件天花板基线已完成，小模型推理链路已跑通，小 prompt 推理链路观测已闭环。关键证据包括 P0/P3 `hardware_ceiling_sweep_2026_0708_p0_007` 成功，以及 P1.28 `runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028` 的 `continuous32_mixed` on/off 两轮 32/32 成功、固定生成 64 tokens、request-device 聚合和 readout 成功。

边界必须保留：P0/P3 是合成硬件 microbench ceiling，不是模型推理 benchmark；P1.28 是 raw counter readout，不是吞吐、scheduler 效率、prefix cache 命中率验收、瓶颈归因或优化建议。当前 `通信模块/docs/developer-to-server.md` 保持 `no_active_server_task_after_p0_p4_closeout_2026_0708`，没有新的服务器任务。

## 不做什么

本项目不在第一阶段运行真实 Coding Agent，不评估工具调用质量、仓库修改质量或多 Agent 规划能力；不把单卡 64GB 写成 DeepSeek-V4-Flash 官方模型可生产部署；不把冷存储随机小块读取放入逐 token 热路径；不在缺少 microbench 和 trace 证据时宣称 CPU/NPU 协同收益。

## 最小开工路径

1. P5：完成 `benchmarks/deepseek_v4_flash/` 的模型对象登记、P5 readiness card、来源版本和服务器路径占位，不下发服务器任务。
2. P6：在用户完成服务器拷贝并提供真实模型路径后，用 `DeepSeek-V4-Flash-w8a8-mtp` 设计单机八卡 official/degraded baseline。
3. P7：单卡/双卡只做极限边界，覆盖小模型、中型 MoE、DeepSeek 子图、低比特/裁剪变体、模拟 expert pool 和 simulator-only full model。
4. P8：优先做 KV/Prefix 管理，再做 expert trace 与热温冷分层；SSD 只做 cold tier，不进入逐 token 热路径。
5. P9：把 P0/P3 microbench 与 P6/P7/P8 trace 合并，输出下一代硬件优先级。
