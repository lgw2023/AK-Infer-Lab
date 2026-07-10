# AK-Infer-Lab Documentation Index

本目录放稳定项目文档；每轮实验事实和临时决策继续写入 `工作记录与进度笔记本/`。DeepSeek-V4-Flash、vLLM-Ascend 和 KV/offload 相关外部事实按 `SOURCES_AND_BOUNDARIES.md` 统一维护。

- `PROJECT_CHARTER.md`: 项目定位、目标、非目标、阶段划分和验收规则。
- `DEEPSEEK_V4_FLASH_ASCEND_PLAN.md`: DeepSeek-V4-Flash P5-P9 八卡基准、单/双卡边界与规格反推专项计划。
- `P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`: P8 分层工程原型的 runtime adapter、StateObject、KV/Prefix、MoE expert 与 simulator 交接详案。
- `TECHNICAL_ARCHITECTURE.md`: AK 状态分层推理实验栈架构。
- `EXPERIMENT_PLAN.md`: 当前 P5-P9 阶段依赖、实验矩阵、证据门与验收口径。
- `METRICS_AND_TRACE_SCHEMA.md`: 请求、device、transfer、KV、Expert、storage trace schema。
- `HARDWARE_FEEDBACK.md`: 从 trace 和 simulator 反推下一代硬件规格的方法。
- `SOURCES_AND_BOUNDARIES.md`: 外部来源、内部资料和不确定性边界。
