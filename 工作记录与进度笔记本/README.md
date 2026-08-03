# 工作记录与进度笔记本

本目录是 AK-Infer-Lab 的任务事实账本。稳定项目说明放在仓库根 `README.md` 和 `docs/` 下；本目录只记录每轮任务、实验、结果、问题、边界和下一步行动。

## 当前主线

当前主线已从“静态提示词推理负载可观测性”升级为：

```text
DeepSeek-V4-Flash on Ascend
  → P5 官方 mixed FP8+FP4 checkpoint runtime gate 与八卡 128K smoke
  → P6 单机八卡 controlled baseline
  → 单卡/双卡极限硬件边界
  → P8 KV/Prefix + MoE Expert + StateObject 分层工程原型
  → CPU/NPU 阶段级协同
  → P9 trace-driven simulator 与下一代硬件规格反推
```

当前 P6.1C-R1 official context、P6.1 unprofiled performance、P6.2 profiled evidence、
P6.3A matched MTP on/off 与 P6.3B-R4-R1 explicit Prefix Cache control 五层 evidence 已关闭。
P6.3B green 限于 primary 9/9 positive-hit 机制证据；15 条 boundary 仍零命中，不形成普遍性能收益。
当前性能总览以 P6.3A/P6.3B 并列双主表呈现，P6.3B 八组 matched hit/TTFT 数据不再压缩为摘要卡。
原 P6.3C 已因 `4096 < 135168` 的 frozen validation 约束收口为
`blocked_p6_3c_not_strict_single_variable`，未创建原配置 executable workload；该范围只关闭原
135168/4096/1 参考的直接 A/B。独立 P6.3C-R1 的 69632/69632/2 共同环境已在首个 lifecycle 的
KV-cache 初始化阶段失败，0 request、0 scheduler step，只形成启动 RED，不形成 Chunked Prefill
机制或性能结论。P6.3C-R2-F4 已在共同 `12288/12288/2`、Prefix Cache off、受控 atomic
co-arrival 环境中完成 6/6 lifecycle、90/90 request、48/48 batch 和 42/42 pair release：Off
三组无 partial prefill，On 在 10K+6K、8K+8K 两个压力 cell 出现 partial prefill；机制已接收，
固定样本未显示短请求 TTFT 或 batch throughput 收益。F4-A1 已用零 NPU 只读再归档关闭来源与
分类链。P6.3C-R3A 收益验证执行包已完成：服务器先运行 `R3-S0` 容量/调度语义 scout，只有
八 resident、12000 fit control、12281 Off wait/On partial mixed 和零 preemption 的机制门通过，
才继续 `R3A` Decode-resident admission-cliff matched A/B；任务已授权在全局八卡无冲突时通过
P6 专用独立 worktree 交接执行。P8.1-R1 与 P8.2-K0
已 green，K1A-R2 accepted capacity 已 ready。R3-R2-R2-R1-R1-R1 已完成同容量唯一 lifecycle：
6/6 transport 成功、D2H store 闭合、CPU hit/load/H2D 为零。原 red 保留，开发机只接受 store-only yellow。
R4-R1 offline store-only closeout 已 green，R5-F0 ready，R5-L1/R1 red 保留。F1-R1 calibration
得到 36800 candidate，但 fixed L2 3/3 请求和 D2H 8/8 后 endpoint 为 `CPU=54/GPU=0`，保留
target-lost red、未发送 restore。F1-R4 外层 128 被通用 mode 覆盖为 64，保留为无效运行合同证据，不否定 accepted capacity。K1A-F1 已由 R17 闭合。K2-R0 run02 已完成 UCM dependency/import，但 8 GiB buffer 的 1296 shards 低于源码门 2048，零请求；四节点 NFS `no_root_squash` 已由用户修复。run03 随后通过 NFS、CMake Python、16 GiB CacheStore 与主机容量门，但在 `UCMFAWAConnector` 初始化期间因默认 4096 目录分片下 FA Posix GC 回收数被整数截断为 0 而停止，0/3 请求。零 NPU attribution 已恢复精确异常和 FA/WA worker block=`3186688/6627328`。当前唯一 driver 为
`run_deepseek_p8_2_k2_r0_server_task.sh`：停卡前验证 attribution/all-payload、FA/WA Cache 与 Posix GC 几何和主机/存储容量；固定总 POSIX 64 GiB、`data_dir_shard_bytes=2`，分流后 32/32 GiB；随后只执行一个 TP8 lifecycle 和 warmup→prime→follower 三请求，退出时恢复 0–7 keep-alive。P6.3C-R2-F4/A1 已完成，当前没有需要重跑的 P6 八卡任务；未来若建立新的 P6 variant，仍须使用独立 P6 交接并通过全局 NPU 互斥门。K2-R1、P8.3-I1 和 P9 不自动进入。

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
| `02_阶段计划.md` | 记录 P0-P9 阶段、目标、交付物和验证标准。 |
| `03_阶段性进展.md` | 每轮推进后的实际进展和证据。 |
| `04_结果与问题点.md` | 已得到结果、问题、风险、决策点和边界。 |
| `05_下一步行动指导.md` | 只写下一步可执行动作。 |
| `06_提示词推理负载设计.md` | 静态 prompt workload 设计。 |
| `07_可观测能力体检执行说明.md` | 服务器可观测能力体检框架说明。 |
| `08_服务器体检结果分析与下一步计划.md` | Atlas 服务器体检结果和后续修正。 |
| `09_DeepSeek_V4_Flash_专项计划.md` | DeepSeek-V4-Flash P5-P9 八卡、极限硬件、P8 原型与规格反推专项状态。 |
| `10_P0_P4_阶段收尾评估.md` | P0-P4 当前阶段三类目标的完成判定和边界。 |
| `11_P0_P4_阶段收尾报告.md` | P0-P4 当前阶段收尾报告和后续建议。 |
| `12_P5_P9_后续阶段重排计划.md` | P5-P9 当前路线、阶段门、P8 分层工程原型和硬件联合分析。 |
| `13_P0_P4_数据资产成果包索引.md` | P0-P4 硬件性能与推理观测数据资产成果包入口，串联审计计划、审计结果正文、静态仪表盘和副本关系。 |
| `14_Qwen3_5_4B_vLLM_AISBench_性能指标记录.md` | P1.28-P1.30 Qwen3.5-4B / vLLM AISBench 风格性能指标、phase memory matrix、server stats 和边界记录。 |
| `16_P6_阶段复盘与P6_3进入评估.md` | P6.0-P6.3B evidence chain、结果包索引、声明边界和 P6.3C/P7-P9 路线复审入口。 |
| `17_P6_3C_R2_F4_Chunked_Prefill_受控调度实验手稿.md` | P6.3C-R2-F4/A1 的论文手稿式完整记录：研究问题、实验设置、原子共到达方法、执行 lineage、机制与性能结果、来源证明和有效性边界。 |
| `18_P6_3C_R3_Chunked_Prefill_收益验证实验设计.md` | P6.3C-R3 的收益验证方案与实现记录：校正 vLLM 0.22 RUNNING-first 调度语义，以 Decode-resident admission cliff 验证长 Prefill 准入收益与 Decode 代价；R3-S0/R3A 执行包已开发，R3B/R3C 仍待前序证据。 |
| `P6_阶段证据链仪表盘_2026_0715.html` | 八页 16:9 P6 closeout 领导汇报：冻结配置、P6.1C-R1/P6.1/P6.2/P6.3A/P6.3B-R4-R1 green、P6.3C strict-single-variable blocked、P6.3B lineage、结果包与 P7-P9 边界。 |
| `DeepSeek_V4_Flash_W8A8_8NPU_性能总览_修订版.html` | 五页 16:9 P6 全阶段实测领导汇报：18-cell unprofiled baseline、MTP Off/On 绝对值与 paired delta、Prefix Cache 八组命中/TTFT、profiled evidence、Chunked Prefill feasibility 与 artifact closeout。 |
| `P8_阶段主要结果与证据链仪表盘_2026_0728.html` | P8 分层工程原型静态证据控制台：P8.0/P8.1/K0、K1/K1A 历史 lineage、R17 restore/H2D 机制闭环、claim boundary、当前 K2-R0 与 Expert/TP4 开放门。 |
| `ak_infer_lab_p0_p4_data_asset_audit_2026_0708.txt` | P0-P4 数据资产全量审计结果正文，作为成果包主读文本版本。 |
| `P0_P4_硬件性能与推理观测数据资产仪表盘_2026_0708.html` | P0-P4 数据资产全量审计的静态可视化仪表盘，作为成果包主展示版本。 |
| `p1_inference_contracts/` | workload、schema、handoff、fixture、prompt。 |
| `runtime_trace_smokes/` | smoke、prefix A/B、msprof 和 request-device 聚合归档。 |
| `observability_profiles/` | 服务器体检 run 归档。 |
| `hardware_ceiling_runs/` | P0/P3 hardware ceiling sweep 归档。 |

## 维护规则

1. 新实验必须先写实验卡片，再跑命令。
2. 新进展写入 `03_阶段性进展.md`，不要覆盖历史。
3. 新结果写入 `04_结果与问题点.md`，必须注明 run id、commit、服务器路径和边界。
4. 下一步只写可执行动作，避免泛泛讨论。
5. 服务器任务必须通过 `通信模块/docs/developer-to-server.md` 交接，且每次只保留当前任务。
6. 服务器邮件正文和每个附件受 70KB 限制；小结果在用户选择后用 `email + 附件` 或 `upload-api + 文本总结/文件` 交付，大 artifact 留在服务器就地分析。
7. 本地 dry-run 不能作为 Atlas 服务器证据。
8. 所有性能结论必须经过 controlled replay；smoke、stats、profile collected、request-device join 分别有不同证明力。
