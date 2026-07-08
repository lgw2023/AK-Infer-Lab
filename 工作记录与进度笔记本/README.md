# 工作记录与进度笔记本

本目录是 AK-Infer-Lab 的任务事实账本。稳定项目说明放在仓库根 `README.md` 和 `docs/` 下；本目录只记录每轮任务、实验、结果、问题、边界和下一步行动。

## 当前主线

当前主线已从“静态提示词推理负载可观测性”升级为：

```text
DeepSeek-V4-Flash on Ascend
  → 单机八卡官方 W8A8-MTP 基准
  → 单卡/双卡极限硬件边界
  → KV/Prefix 状态分层
  → MoE Expert 热温冷分层
  → CPU/NPU 阶段级协同
  → trace-driven simulator 与下一代硬件规格反推
```

## 当前范围

范围内：

- DeepSeek-V4-Flash 八卡官方 Ascend 基准。
- 单卡/双卡极限硬件实验边界。
- Qwen/GLM/DeepSeek 小模型和中型 MoE 作为前置验证模型。
- vLLM-Ascend、MindIE、KV Cache CPU Offload、UCM、Mooncake、prefix cache、msprof、CANN/NPU trace。
- KV、Prefix、Context、Expert、Weight、Activation、Workspace 状态对象的生命周期、迁移、命中、恢复、重算和驱逐。
- MoE router top-k、expert hotset、expert miss、prefetch、warm/cold tier。
- 硬件 microbench、request-device 聚合、bottleneck report、what-if simulator。

范围外：

- 真实 Coding Agent 运行和工具调用质量评测。
- 多 Agent 编排、浏览器自动化、代码补丁质量评估。
- 单卡 64GB 官方 DeepSeek-V4-Flash 生产部署承诺。
- 缺少 trace 证据时宣称 CPU/NPU 协同加速。
- 第一阶段把 SSD cold tier 或 NPU-SSD 直通放入逐 token 热路径。

## 文件结构

| 路径 | 用途 |
| --- | --- |
| `01_工作记录.md` | 记录当前工作条目、目标、价值、输入、输出和验收边界。 |
| `02_阶段计划.md` | 记录 P0-P6 阶段、目标、交付物和验证标准。 |
| `03_阶段性进展.md` | 每轮推进后的实际进展和证据。 |
| `04_结果与问题点.md` | 已得到结果、问题、风险、决策点和边界。 |
| `05_下一步行动指导.md` | 只写下一步可执行动作。 |
| `06_提示词推理负载设计.md` | 静态 prompt workload 设计。 |
| `07_可观测能力体检执行说明.md` | 服务器可观测能力体检框架说明。 |
| `08_服务器体检结果分析与下一步计划.md` | Atlas 服务器体检结果和后续修正。 |
| `09_DeepSeek_V4_Flash_专项计划.md` | 建议新增：DeepSeek-V4-Flash 八卡与极限硬件专项计划。 |
| `p1_inference_contracts/` | workload、schema、handoff、fixture、prompt。 |
| `runtime_trace_smokes/` | smoke、prefix A/B、msprof 和 request-device 聚合归档。 |
| `observability_profiles/` | 服务器体检 run 归档。 |

## 维护规则

1. 新实验必须先写实验卡片，再跑命令。
2. 新进展写入 `03_阶段性进展.md`，不要覆盖历史。
3. 新结果写入 `04_结果与问题点.md`，必须注明 run id、commit、服务器路径和边界。
4. 下一步只写可执行动作，避免泛泛讨论。
5. 服务器任务必须通过 `通信模块/docs/developer-to-server.md` 交接，且每次只保留当前任务。
6. 服务器邮件和附件受 70KB 限制，大 artifact 留在服务器，只回传摘要、路径和小表。
7. 本地 dry-run 不能作为 Atlas 服务器证据。
8. 所有性能结论必须经过 controlled replay；smoke、stats、profile collected、request-device join 分别有不同证明力。
