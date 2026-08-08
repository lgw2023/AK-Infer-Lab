# P6.3C-R3C 动态预算结果与 R3D 持续 Prefill 压力实验设计

## 摘要

R3A 证明，当八个请求已进入 Decode 而新长 Prompt 到达时，Chunked
Prefill 可以消除 Off 侧由整段准入条件引起的 starvation，但接近容量上限的
12272-token 首 chunk 会以严重的 resident Decode 尾延迟和吞吐损失为代价。R3B 进一步
表明，五档静态 budget 形成清晰的经验 Pareto frontier，但没有配置同时满足项目内
TTFT、resident P99 TBT 和 TPS 边界。基于此，R3C 把固定命令行 budget 改写为运行时
调度决策：配置容量保持 12288，只在 Decode resident 与 waiting Prefill 共存时临时限制
当前 scheduler iteration。

R3C 在真实 Ascend/vLLM 环境完成 14 个 fresh-model lifecycle、1070 个 EngineCore
request 和 202 个本地 HTTP request，零重试，所有资源恢复闭合。三档动态策略相对 Off
均将 injected TTFT 降低约 79%–81%，并把吞吐损失缩小至 1.5%–4.1%。其中
T4096 展现出最平衡的点估计：TTFT 下降 80.6%，TPS 下降 1.9%。然而，它的
resident P99 TBT 仍比 Off 高 340.1%，说明吞吐恢复并没有转化为交互式 Decode 尾延迟
恢复。

进一步的代码—trace 对照表明，R3C 的压力条件只观测 waiting queue。长 Prompt 首次
partial admit 后转入 running，waiting 计数归零，后续迭代立即恢复 12288 的 full budget。
因此 R3C 严格证明的是 admission-triggered one-shot cap，而不是贯穿整个 Prefill 的持续
chunk control。R3D 于此基础上建立新 variant：将 running 中尚未完成 Prompt 计算的请求也纳入
压力状态，并以 128、256、512 和 1024 token 四档更细粒度目标直接检验 resident tail
与 TTFT/TPS 的可达边界。

## 1. 研究背景与问题转换

R3B 的静态预算扫描展示了一个稳定但不理想的冲突：更大的 Prefill chunk 能更快地将
新请求推过 admission cliff，却使已经在 Decode 的请求经历更长的相邻 token gap；更小的
chunk 会减小单次 stall，但可能因 iteration 数增多而牺牲长请求 TTFT 与整体效率。因此，
研究问题不再是“Chunked Prefill 开关是否有效”，而是“调度器在什么状态下应保持多大的
Prefill quantum”。

R3C 的直观出发点是把容量配置与瞬时决策分离。它保留了足以启动 Off 基线的
`max_num_batched_tokens=12288`，不通过修改 KV-cache 初始化容量制造策略差异；只在
`Scheduler.schedule()` 调用内临时将 `max_num_scheduled_tokens` 改为

\[
B_t=\min(12288, D_t+T),
\]

其中 \(D_t\) 是本轮为 Decode resident 预留的 token，\(T\) 是 Prefill target。此设计已经成功
把 static B8192 的吞吐下降从 6.1% 缩小至 1.5%–4.1%，但没有解决 resident tail。这一
反差促使我们从状态机而非 target 数值本身寻找原因。

## 2. R3C 实验设置

R3C 共享 R3A/R3B 的 decode-resident staged-arrival 环境。平台固定为 DeepSeek-V4-Flash
W8A8+MTP，TP8+EP，`FULL_DECODE_ONLY`，block size 128，Prefix Cache off，
`max_model_len=12288`，`max_num_seqs=9`。八个 resident request 各含 256-token Prompt
和 128-token 强制输出；当八者都已流出至少 16 token 后，发送 12281-token Prompt 和
4-token 输出的独立 injected request。

五个策略为 Off B12288、static On B8192，以及配置 budget 保持 12288 的 adaptive
T2048/T4096/T8192。四个 mechanism lifecycle 打开只读 scheduler observer，直接记录
effective budget、scheduled Prefill token、resident Decode token、partial/mixed 与 preemption。十个
performance lifecycle 关闭 observer 和 profiler，使用升序—降序镜像顺序，每个 policy-cell
得到 12 个 measured trial。主指标是 injected TTFT、resident interference-window P99 TBT、
maximum adjacent-token stall、aggregate output TPS 和 resident TBT SLO attainment。

## 3. 服务器执行过程

服务器以 `main@c536d6958c4e68990283f2b273be5adc15925265` 的 detached worktree 为基线。零 NPU
audit 通过后，在不修改共享 checkout 的前提下做了两项 task-local runtime adaptation：

1. 当现场 `AscendDSACPImpl` 没有 `update_graph_params` 时增加兼容 guard；
2. 将过时的 vLLM cache-manager alias/mapping 同步到实际 Ascend subclass key。

两项修复都是对现场运行时布局的兼容，未改变请求、cell、target、指标或策略状态机。最终
14/14 lifecycle 完成，1070/1070 EngineCore request 和 202/202 HTTP request 成功，零 retry。
controller 在真实 EngineCore PID 中安装，共记录 5451 次决策，其中 106 次为
pressure-capped、5345 次为 full-budget。八卡 keep-alive 按 0–7 精确恢复，16/16 marker 齐全，
port 7000 无监听，vLLM 无残留进程。

## 4. R3C 机制结果

首次注入时，八个 resident 每轮共占用 \(D=16\) token。三档 adaptive target 的第一个
Prefill chunk 精确等于 target：

| policy | effective budget | 观测 chunk sequence |
| --- | ---: | --- |
| adaptive T2048 | 2064 | 2048 + 10233 |
| adaptive T4096 | 4112 | 4096 + 8185 |
| adaptive T8192 | 8208 | 8192 + 4089 |
| static B8192 | 8192 | 8176 + 4105 |

首 chunk 的精确性证明 controller 已在真实 scheduler 内改变了瞬时 token budget。但三个 adaptive
策略都只产生两个 chunk：首 chunk 为 target，第二 chunk 一次吸收全部 remainder。这与源码的
`waiting_prefill_count>0` 条件完全一致，因而将 R3C 的科学语义限定为“准入触发的单次限额”。

## 5. R3C 性能结果

| policy | injected TTFT (ms) | resident P99 TBT (ms) | TPS | SLO attainment |
| --- | ---: | ---: | ---: | ---: |
| Off B12288 | 5756.7 | 91.4 | 130.57 | 100.0% |
| static On B8192 | 1132.2 | 549.7 | 122.57 | 83.0% |
| adaptive T2048 | 1183.7 | 410.1 | 125.16 | 83.2% |
| adaptive T4096 | 1115.6 | 402.1 | 128.04 | 83.0% |
| adaptive T8192 | 1113.3 | 531.7 | 128.63 | 83.0% |

adaptive T4096 相对 Off 将 TTFT 降低 80.6%，TPS 只下降 1.9%；相对 static B8192，
TTFT 还下降 1.5%，resident P99 TBT 下降 26.9%，TPS 提高 4.5%。这说明将容量与
瞬时 admission budget 分离是有效的，而且比直接把静态 B 下调到 8192 更好。但相对 Off，
T4096 的 resident P99 仍增加 340.1%，远超 +10% 边界。因此 R3C 的 outcome 应保留为
`adaptive_policy_tradeoff_no_candidate_within_bounds`，不能写成部署候选已成立。

## 6. R3D 假设与改进的状态机

R3D 对压力状态做如下重定义：

\[
\text{pressure}_t =
(N^{decode}_t>0)\land
(N^{waiting\_prefill}_t+N^{running\_unfinished\_prefill}_t>0).
\]

这一定义保持了两个必要边界。第一，只要 Decode resident 仍存在，部分已准入但尚未完成
Prompt 的长请求就不能让控制器误判压力消失。第二，如果 resident Decode 已经全部完成，
恢复 full budget 是正确行为，因为此时已无交互式前台需要保护。

R3D 预注册三个主要假设：

- H1：persistent policy 会在 waiting 变为 0 后继续产生 pressure-capped 决策，而 admission-only
  anchor 会在同一状态恢复 full budget。
- H2：更小的持续 target 会系统性降低 resident interference P99 TBT 与 maximum stall。
- H3：过小 target 会通过增加 scheduler iteration 和 Prefill 完成轮数损害 injected TTFT 或 TPS，
  因而依然存在粒度—效率 Pareto 权衡。

## 7. R3D 实验设置

R3D 保持 R3C 的模型、TP/EP/MTP、graph、block size、Prefix Cache、`12288/12288/9`、
staged arrival、请求长度、cell、输出长度、采样次数和指标定义。新的六个策略为：

1. contemporaneous Off B12288；
2. waiting-only `admission_on_t4096`，完整复现 R3C 状态机；
3. persistent T128/T256/T512/T1024。

选择更小的 128–1024 target，是因为 R3B static B2048 的 resident P99 TBT 仍约 426 ms，
R3C one-shot T2048 也约 410 ms。如果目标是接近 Off 的 91 ms，继续在 2K–8K 范围扫描
缺乏辨识力。T128 与当前 block size 同尺度，T256/T512/T1024 则提供成倍剂量阶梯。

五个 mechanism lifecycle 要求完整重建 12281-token Prefill 的 chunk sequence。机制通过不再只
依赖 first chunk，而需要每一个 pressure step 都满足实际 effective budget 合同，且 persistent
策略必须在 `waiting=0` 与 `running_unfinished_prefill>0` 时继续限额。如果 resident 在长
Prompt 完成前结束，后续 full-budget step 允许存在，但 trace 必须同时证明
`decode_resident_count=0`。

性能轨道使用六策略升序—降序的 12 个 fresh-model lifecycle，每个 config-cell 保留 12 个
measured trial。全任务预计为 17 lifecycle、1286 EngineCore request、243 HTTP request 和零 retry。
配对与 descriptive bootstrap 沿用 R3B-A1 已修正的分析实现。

## 8. 决策与声明边界

部署候选仍须同时满足：injected TTFT 相对 Off 下降至少 20%，resident P99 TBT 增加
不超过 10%，aggregate TPS 下降不超过 5%。这些是项目内部决策边界，不是外部标准。
即使 R3D 有一个点进入边界，结论也只支持受控 decode-resident admission-cliff 环境下的候选，
不支持自然 API 流量、生产 SLO 容量或普遍收益声明。

R3D 不覆盖 R3C。R3C 是“one-shot admission cap 可实现且能恢复吞吐，但仍无部署候选”的
完整证据；R3D 只回答更新的状态机问题。服务器可依据
`docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md` 处理真实环境的路径、overlay、版本布局和兼容性；
任何改变 target、请求、cell、指标或 policy semantics 的修复都必须建立新 variant。

## 9. 数据与实现索引

- R3C 开发机控制器：`tools/inference_contracts/p6_3c_r3c_adaptive_scheduler.py`
- R3C 服务器返回摘要：`/Volumes/SSD1/Inbox/2026-08-07/p6-3c-r3c-20260807T102129-c536d695/result_summary.md`
- R3C 全量服务器 manifest：同目录 `p6_3c_r3c_complete_file_manifest.tsv.gz`
- R3D workload：`benchmarks/deepseek_v4_flash/workloads/p6_3c_r3d_persistent_prefill_pressure.yaml`
- R3D controller：`tools/inference_contracts/p6_3c_r3d_persistent_scheduler.py`
- R3D driver：`tools/inference_contracts/run_deepseek_p6_3c_r3d_persistent_prefill.py`
- R3D 服务器交接：`通信模块/docs/developer-to-server.P6.md`

R3C 的 raw scheduler trace、token timestamps 和 server log 保留在 Ascend 服务器。本地接收包仅含
结果摘要与全量 manifest，因而本文中的点估计与过程计数以服务器摘要为主；未在开发机
重算未传输的 per-trial 配对统计。

## 10. R3D 首次执行：运行时阻断与证据边界

R3D 的第一次正式尝试基于 `main@5e6eee6bb044359b4449568df4792fdba0cb88c6`。服务器完成了
Git 同步、16 项发布资产核验和零 NPU 合同审计，并成功生成 22 条请求体记录；请求体 manifest
逐项验证通过，所有 policy lifecycle 复用完全相同的请求字节。因此，本次失败并非请求生成、
任务目录或科学合同缺失。正式入口随后建立了 `mechanism_01` lifecycle，但在模型 ready、
HTTP 请求和 scheduler 观测之前终止：EngineCore request 与 HTTP request 均为 0，后续 16 个
lifecycle 未开始。

失败来自 R3C 成功运行时已经暴露、但尚未被正式发布到仓库的运行时兼容差异。vLLM 的
`single_type_kv_cache_manager` 在模块导入时按精确类型构造 `spec_manager_map`；当前服务器上的
vLLM-Ascend 随后将公共 MLA spec 替换成 `AscendMLAAttentionSpec` 与
`AscendSlidingWindowMLASpec`。当 manager 模块先被导入时，映射与模块别名仍停留在原始基类，
因此 task-local deferred loader 对四项解析条件的检查全部失败。这个错误发生在任何长 Prefill
进入 waiting/running 队列之前，故不能被解释为 persistent policy 的反例，也不能与机制门失败
混为一谈。

服务器最终资源证据显示，0–7 号卡对应的 keep-alive 已恢复为 16/16 marker，port 7000 无
监听，vLLM 残留进程为 0，detached worktree 保持 clean。早期自然语言状态中出现的“2 个
marker”是恢复过程中的中间观测，不是最终资源状态。由此，本次尝试应记录为
`runtime_blocked_before_scheduler_evidence`：它保留为可审计的失败尝试，但不更新 R3D 的科学
outcome。

## 11. R3D 第二次尝试：将现场经验转化为可复现实验基础设施

第二次尝试不建立新科学 variant。策略集合、128/256/512/1024 target、Decode quantum、
`12288/12288/9` 容量、staged arrival、请求体、cell、样本数、指标、配对和决策边界全部保持
不变；唯一变化是把 R3C 已验证的两项 task-local 兼容修复正式纳入运行时 overlay。

第一项修复在 Ascend spec 完成替换后，对 frozen vLLM manager 做显式解析对齐。原始基类键
继续保留，以避免破坏既有调用；两个 Ascend subclass 精确键复用原 manager class，并同步
`MLAAttentionSpec` 与 `SlidingWindowMLASpec` 模块别名。修复后的自检要求四项条件同时成立：
两个 Ascend 精确键存在，且两个 manager alias 均指向对应 Ascend 类。这样既修复了当前失败，
也保留了 exact-type dispatch 的可解释性。

第二项修复作用于 vLLM-Ascend 0.22.1rc1 的 ACL graph helper。现场
`AscendDSACPImpl` 不提供 `update_graph_params`，而公共 helper 原先无条件调用该方法。新的
overlay 仅在 backend class 实际实现此方法时调用；它不改变 graph mode、capture sizes、请求
或 scheduler 决策。两项修改都只发生在每个 lifecycle 的物化 overlay，既不改 conda
site-packages，也不改共享 checkout。

更重要的是，第二次尝试把真实导入顺序的烟测前移到停用 keep-alive 之前。预检在正式
`PYTHONPATH`、CANN/ATB 环境和插件集合下导入 Ascend KV interface、执行 deferred loader、
核验 exact manager resolution，并导入已修正的 ACL graph module。只有这组无模型、无请求、
不占用 NPU 的检查完整通过，任务才允许进入八卡生命周期。相比把错误留到模型启动阶段，
这项改变直接减少无效停卡和重复加载，同时不把科学任务降格为追逐自动评分。

R3D attempt02 因而仍检验同一个核心假设：当长 Prefill 已从 waiting 转为 running 但尚未完成时，
持续限制 Prefill quantum 是否能够显著降低 resident Decode 的尾部干扰，并在 TTFT 与 TPS 上
形成可接受的权衡。只有新的 scheduler trace 和 12-lifecycle performance 结果才能回答该问题；
运行时兼容烟测本身不构成 Chunked Prefill 的正向或负向证据。

## 12. R3D attempt02：完整执行与机制识别

R3D attempt02 在 `main@2c0a87a38bf058a3b55aacab23426129ca946a4e` 上完成了原定科学
合同。服务器使用独立 detached worktree，18/18 发布资产核验与零 NPU audit 均通过；正式实验
共完成 17/17 个 fresh-model lifecycle、1286/1286 条 EngineCore request、243/243 个本地 HTTP
request，零 retry。性能轨道保留 144/144 个 measured trial 与 60/60 个有效配对。实验结束后，
0–7 号卡的 keep-alive 精确恢复，port 7000 无监听，vLLM 无残留进程，worktree 保持 clean。

attempt02 的唯一现场适配发生在停卡前的 runtime-overlay smoke。已发布 smoke 试图从模块级
`acl_graph.update_graph_params` 读取源码，但现场 guard 实际位于 `update_full_graph_params`。
服务器将检查对象改为后者，并通过 task-local 固定副本注入；ACL graph overlay 的输出 SHA 与
预期值精确一致，四项 Ascend manager resolution 也全部成立。这个改变只修复“如何检查已经发布
的兼容 guard”，没有修改 guard 本身、模型启动参数、scheduler policy、请求、cell 或指标。开发机
在本轮将该现场修复正式纳入仓库，避免后续任务重复发现同一布局差异。

完整 scheduler trace 证明 persistent 状态机按预期运行。八个 resident 每轮共消耗 16 个 Decode
token，因此 target 为 (T) 时，pressure budget 为 (16+T)，留给 injected Prefill 的首块恰好为
(T)。四档策略的完整 chunk sequence 为：

| policy | 完整 Prefill chunk sequence | chunk 数 | waiting 归零后仍限额的步数 |
| --- | --- | ---: | ---: |
| persistent T128 | 以约 128-token 小块持续推进，末块 5229 | 56 | 54 |
| persistent T256 | (256\times47+249) | 48 | 47 |
| persistent T512 | (512\times23+505) | 24 | 23 |
| persistent T1024 | (1024\times11+1017) | 12 | 11 |

每条 sequence 的 Prefill token 总和均为 12281，且所有 pressure step 都满足
`selected_budget = scheduled resident Decode + target`；全程没有 preemption。作为同时运行的语义
对照，admission-only T4096 在首次准入 4096 token 后，长请求进入 running、waiting 归零，下一步
恢复 full budget 并一次处理剩余 8185 token。由此 H1 得到直接支持：R3D 不只是改变首块大小，
而是实际改变了 waiting→running 之后的调度状态机。

## 13. R3D 性能结果：持续小块没有换来更低的 Decode 尾延迟

下表报告 admission-cliff cell 的 pooled sample median。它们来自两轮镜像 lifecycle 中的固定样本，
用于描述本项目平台上的策略结果，不被解释为独立重复的总体推断。

| policy | injected TTFT (ms) | resident P99 TBT (ms) | aggregate TPS |
| --- | ---: | ---: | ---: |
| Off B12288 | 5817 | 93.2 | 129.1 |
| admission-only T4096 | 1120 | 405.9 | 126.7 |
| persistent T128 | 23084 | 419.5 | 34.4 |
| persistent T256 | 19818 | 425.6 | 42.4 |
| persistent T512 | 10030 | 422.0 | 65.8 |
| persistent T1024 | 5072 | 420.3 | 92.2 |

结果拒绝了 R3D 最关键的 H2。将持续 target 从 1024 缩小到 128，resident P99 TBT 并没有沿着
chunk size 下降，而是稳定在 419.5–425.6 ms 的狭窄区间，仍约为 Off 的 4.5 倍。与此同时，
更小 target 通过增加 Prefill iteration 数显著恶化 injected TTFT 和吞吐：T128 需要 56 个 chunk，
TTFT 上升到 23.1 s，TPS 降至 34.4；T1024 虽把 TTFT 恢复到 5.1 s，TPS 仍只有 92.2。H3
因此得到支持，但其形式比原假设更强：小块策略付出了近似线性的迭代成本，却没有得到预期的
单步 stall 缩短。

五目标 Pareto 分析只保留 Off B12288 与 admission-only T4096；四个 persistent policy 全部被
支配，没有任何配置同时满足 TTFT 下降至少 20%、resident P99 TBT 增幅不超过 10%、TPS 下降
不超过 5% 的项目内联合边界。R3D 的正式 outcome 为
`persistent_prefill_tradeoff_no_candidate_within_bounds`。这是一个有效阴性结果：persistent
controller 已被机制证据确认，阴性来自策略本身的性能行为，而不是控制器没有生效。

## 14. 从策略搜索转向执行路径归因

R3D 最有信息量的观察不是“更小 target 更慢”，而是四档 persistent policy 的 resident P99
几乎停在同一个约 420 ms 平台。若 stall 主要由 Prefill token 数量决定，那么 target 从 1024
缩小八倍理应显著缩短单个 mixed Prefill/Decode step；数据并不支持这一关系。相反，它更像每个
mixed iteration 都支付了一个近似固定的执行成本，而更小 target 只是重复支付该成本更多次。

这一现象可能来自多个层面：Python scheduler/update 的 CPU 开销、EngineCore 到 TP8 worker 的
RPC 与结果同步、图执行边界、MTP/采样路径、collective communication，或固定形态的 device
kernel sequence。仅凭 token timestamp 无法区分这些解释。继续增加 T64/T32 只会在同一机制上
制造更多高代价 iteration，既不接近部署边界，也不能回答成本来自哪里。因此下一轮不再扩展
policy grid，而建立新的 R3E attribution variant。

## 15. R3E 研究问题与分层测量设计

R3E 的核心问题是：在相同的八 resident staged-arrival admission cliff 下，约 420 ms 的 mixed
step floor 主要位于 host scheduler/update，还是位于从 scheduler 返回到 update 开始的更宽
EngineCore execution pipeline？在 async scheduling 下，`execute_model` 与 `sample_tokens` 使用不同
Future，广义 pipeline 还包含 batch queue、host RPC、worker、device execution 与 synchronization，
不能仅凭 host timer 称为“NPU 时间”。为避免这种过度归因，R3E 将证据拆成两个层次。

第一层是三条 profiler-off host-timing lifecycle，分别运行 admission-only T4096、persistent
T1024 和 persistent T128。只读 observer 在 pinned vLLM EngineCore 路径上关联四个事件：
`Scheduler.schedule`、`MultiprocExecutor.execute_model` 提交、execute Future 完成，以及
`Scheduler.update_from_output` 开始/完成。主归因量是 scheduler 返回到 update 开始的 pipeline
span，execute-model Future 则作为可解释的子分量。每个 timing context 保留 step index、scheduled Decode/Prefill
token、effective budget 与 request ordering，因此可以把时长按 `mixed_prefill_decode`、
`resident_decode_only` 和 `injected_prefill_only` 分类。observer 始终返回原始 scheduler output、
Future 和 update output，不修改调度或执行语义。

第二层是两条 fresh diagnostic-msprof lifecycle，只覆盖 admission-only T4096 与 persistent T128
两个代表端点。它们使用完全相同的请求和 policy，但不参与性能比较。分析仅对“injected request
start→first token”和“injection dispatch→first token”两个窗口聚合 device task 与 top op type，
再将 op type 描述性归为 collective communication、matmul/MoE、attention、transfer/sync 和
other。由于不同 stream 可以重叠，task duration 求和只是诊断计数，不是 wall-clock 分解；raw
profiler 数据继续保留在服务器。

## 16. R3E 可证伪假设与判定边界

R3E 预注册三种相互可区分的解释。若三个策略的 mixed-step EngineCore pipeline span 都占完整
step 的至少 80%，且 persistent T128/T1024 的 pipeline median 比值落在 0.75–1.25，则记录
`mixed_step_floor_executor_path_supported`。这里的阈值只是项目诊断规则，不是外部标准；它只把
主要定位从 Python scheduler/update 缩小到 RPC—worker—device—sync 的复合路径，仍须结合
msprof operator evidence 才能进一步讨论 device 侧。

若 scheduler 与 update 的合计时长占主导，则记录 `host_scheduler_overhead_dominant`；若 pipeline
成本随 target 明显变化，或多个层面共同贡献，则记录
`target_sensitive_or_multifactor_execution_cost`。任何 lifecycle、timing context 或 profiler window
不完整，都必须保留为 `latency_floor_attribution_incomplete`，不能用 R3D 的约 420 ms 先验补齐。

R3E 共需要五个 fresh-model lifecycle：三条 host timing、两条 diagnostic msprof；每条仍只有一个
512-token warmup 和一组 8-resident+1-injected measured trial，因此总合同为 50 条 EngineCore
request、15 个本地 HTTP request、零 retry。三条 host lifecycle 完成完整 chunk sequence 与 timing
correlation gate 后，才进入两条 profiler 诊断。R3E 不重新估计 R3D 的 pooled performance，不搜索
部署 target，也不把 profiler-on 时延与 profiler-off 数据比较。

## 17. 有效性与后续研究边界

R3E 的内部有效性来自三点：请求体与 R3D staged-arrival 语义完全复用；host timing 与 profiler
轨道分离；每个 timing row 与具体 scheduler output 通过 context id 关联，而不是用相邻时间戳猜测。
主要威胁则包括 observer 本身的微小 host 开销、异步 batch queue 对 pipeline span 的影响、msprof
不同 stream 的重叠，以及仅选两个 profiler 端点造成的覆盖限制。因此，完整结果最多支持“受控
decode-resident mixed-step floor 的路径归因”，不支持生产瓶颈、自然到达流量或普遍优化建议。

只有当 R3E 把主要成本定位到可操作层面，下一轮才应设计针对性 intervention。例如，若 device
trace 显示固定 collective/graph 序列主导，可以研究 mixed batch shape 或 graph policy；若 host
更新主导，则研究 scheduler bookkeeping；若 EngineCore 复合路径仍无法分解，下一步应增加 worker
侧 NVTX/msproftx 标记，而不是继续扫 chunk size。原 P6.3C blocked、F4、R3A、R3B、R3C 与 R3D
结果链均保留，R3E 只新增 attribution evidence。

## 18. R3E 实现与交付索引

- workload：`benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_mixed_step_latency_floor_attribution.yaml`
- host timing observer：`tools/inference_contracts/p6_3c_r3_decode_resident_observer.py`
- driver/finalizer：`tools/inference_contracts/run_deepseek_p6_3c_r3e_latency_floor.py`
- lifecycle wrapper：`tools/inference_contracts/run_deepseek_p6_3c_r3e_mode.sh`
- experiment entry：`tools/inference_contracts/run_deepseek_p6_3c_r3e_experiment.sh`
- server entry：`tools/inference_contracts/run_deepseek_p6_3c_r3e_server_task.sh`
- server handoff：`通信模块/docs/developer-to-server.P6.md`
- R3D attempt02 本地小包：`/Volumes/SSD1/Inbox/2026-08-08/p6_3c_r3d_attempt02_20260808_run01`

R3D raw scheduler trace、token timestamp、msprof output 与完整日志继续保留在 Ascend 服务器。本节
的 R3D 数值来自服务器完成报告与有界结果包；R3E 尚无 NPU 结果，本文记录的是下一轮已发布的
可执行研究合同，而不是预先宣告结论。
