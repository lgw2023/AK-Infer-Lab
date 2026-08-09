# P6.3C-R3E：从稳态延迟地板到 request-scoped 执行路径证据

## 摘要

P6.3C-R3D 已经给出一个稳定而反直觉的结果：把持续 Prefill target 从 1024 token 逐级缩小到
128 token，并没有继续降低八条 resident Decode 的 P99 TBT；四档 persistent policy 的 P99 TBT
都停留在约 420 ms，而更细的 chunk 只增加了长请求 TTFT 和吞吐代价。R3E 因而不再把
Chunked Prefill 当作一个有待继续扫参的黑盒开关，而是把问题改写为：这个对 chunk target
不敏感的延迟地板，究竟发生在 Python scheduler bookkeeping、EngineCore 请求管线，还是设备执行
路径内部？

R3E attempt03 首先以三条 profiler-off lifecycle 对 scheduler step 做主机侧分段计时。在 79 个
完整 timing context 中，mixed Prefill/Decode step 的 99.6% 以上时间位于从 scheduler return
到 update start 的广义 EngineCore pipeline；scheduler 与 update 本身只有约 2–3 ms 和 0.2 ms。
persistent T128 与 T1024 的 pipeline 中位数之比为 1.018，说明约 420 ms 的 resident TBT floor
不是由更小 target 引起的 Python 调度开销线性增长。结合 vLLM V1 的 two-batch asynchronous
pipeline，EngineCore pipeline latency 的一半与三种策略的稳态 TBT 接近，这构成了一个强的
cadence 解释，但尚未定位到某个 NPU kernel。

R3E-F1 随后只补跑 admission T4096 与 persistent T128 两个诊断端点，并把 profiler 窗口严格
限制在 warmup 之后的 measured staged-arrival request 内。两条 lifecycle、20 个 EngineCore
request 和 6 个本地 HTTP request 全部成功，模型加载不在采集窗口。该实验第一次获得了本项目
Ascend + vLLM 路径上的 request-scoped profiler trace，同时完整复现了 T4096 的
`4096,8185` 两块序列与 T128 的 56 块持续压力序列。

但是，F1 的现场聚合只解析了 rank 0，并用 operator 名称 token 将多种事件统称为 device event；
其 top events 同时包含 HCCL dequeue、`npu_fx_compiler inference`、`vllm::`、`c10d::`、
`aten::` 和 `aclnn*`。因此本轮结果已经足以证明“请求窗口内存在这些执行路径”，却还不足以把
duration sum 解释为设备 wall-clock，更不足以选择 collective、compiler、MoE 或 attention 作为
下一优化目标。为关闭这一证据缺口，本手稿最后定义 R3E-F1-A1：不重跑模型、不触 NPU，直接对
服务器保留的全部 rank raw trace 做可复现的分域重聚合。

## 1. 研究问题的递进

R3A 至 R3E 不是相互覆盖的独立 benchmark，而是一条逐层收缩解释空间的证据链：

1. R3A 证明 Chunked Prefill 能消除 decode-resident admission cliff，但会放大 resident tail；
2. R3B 证明单纯扫描共同 `max_num_batched_tokens` 找不到同时满足 TTFT、P99 TBT 与 TPS 边界的点；
3. R3C 证明 waiting-only dynamic budget 能恢复大部分吞吐，却不能消除 resident tail；
4. R3D 证明把小 target 持续施加到 running unfinished Prefill，不会按 target 比例降低 P99 TBT，
   反而通过增加迭代数显著损害 TTFT 和 TPS；
5. R3E 因而研究延迟地板的执行路径来源，而不是继续寻找更小的 chunk。

本阶段的核心假设可写成：

\[
T_{\mathrm{step}}
=T_{\mathrm{scheduler}}
+T_{\mathrm{engine\ pipeline}}
+T_{\mathrm{update}},
\]

其中 R3D 已经显示 (T_{\mathrm{TBT}}) 对 target 不敏感。若
(T_{\mathrm{scheduler}}+T_{\mathrm{update}}) 很小，而
(T_{\mathrm{engine\ pipeline}}) 占据绝大多数 step，则继续优化 Python admission policy
不太可能消除该地板；后续应进入 executor/device-path 归因。这里的“广义 EngineCore pipeline”
包括 execute Future、sample、async queue、RPC、worker、device execution 与同步，不能直接等同于
纯 NPU kernel time。

## 2. R3E attempt03：主机侧阶段分解

R3E 保留 R3D 的 staged-arrival 科学合同：DeepSeek-V4-Flash W8A8+MTP，TP8+EP，
`max_model_len=max_num_batched_tokens=12288`，`max_num_seqs=9`，Prefix Cache off，八条
resident request 先进入 Decode，随后注入 12281-token 长 Prefill。三条 host lifecycle 分别为
admission-only T4096、persistent T1024 与 persistent T128。profiler 在这三条 lifecycle 中关闭，
避免 profiler overhead 污染主机阶段计时。

表 1 报告 mixed Prefill/Decode step 的中位数。pipeline fraction 定义为广义 EngineCore pipeline
在完整 step 中的比例；它是路径归因量，不是设备利用率。

| policy | mixed rows | scheduler (ms) | execute Future (ms) | EngineCore pipeline (ms) | pipeline P95 (ms) | update (ms) | full step (ms) | pipeline fraction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| admission T4096 | 2 | 2.854 | 721.392 | 828.738 | 1070.192 | 0.220 | 831.812 | 0.9961 |
| persistent T1024 | 12 | 2.233 | 805.464 | 858.228 | 953.814 | 0.198 | 860.915 | 0.9970 |
| persistent T128 | 55 | 2.004 | 805.366 | 874.032 | 905.231 | 0.198 | 876.266 | 0.9975 |

T128/T1024 的 mixed pipeline median ratio 为 1.018415。该结果排除了“target 越小导致 Python
scheduler 逐步变慢”作为主要解释。与此同时，vLLM V1 的 async queue 允许两个 batch in flight；
在这种 cadence 下，单个 resident stream 观测到的 token interval 可能接近完整 pipeline latency
的二分之一。该二分之一与 R3D 三个端点的 P99 TBT 相差约 2.1%、2.1% 和 4.2%。由于这里没有
显式 device dependency trace，这一对应关系被记录为强机制线索，而非唯一因果证明。

## 3. 为什么 process-wide profiler 没有形成证据

R3E attempt03 原计划另启两条 profiler lifecycle，但 process-wide `msprof vllm serve` 在模型加载
期间就消耗了采集预算：第一条 profile lifecycle exit 143，第二条未运行。这个失败不是 Chunked
Prefill 机制失败，而是采集窗口与研究对象错位。模型加载 trace 不能回答 measured mixed step
里发生了什么，也不能与 profiler-off 的 R3D 性能值直接比较。

因此 F1 的方法学修正不是增加 profiler 时长，而是改变控制点：vLLM server 正常启动、完成
readiness 与 warmup，随后由 driver 调用 `/start_profile`；单次 measured staged-arrival trial
完成后立即调用 `/stop_profile`。该窗口使“请求执行路径”成为 profiler 的主体，并避免把模型
加载当作在线推理证据。

## 4. R3E-F1 实验设置与执行 lineage

F1 task ID 为
`p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01`，执行提交为
`90c027e7b97cb8a1ca152b76ca29105ebe74128c`。服务器在独立 detached worktree 中完成 21/21
发布资产核验和源 R3E 证据核验。两条 lifecycle 共完成 20/20 EngineCore request、6/6 HTTP
request、0 retry；四次 profiler API 调用均返回 HTTP 200。两条路径共同冻结模型、容量、resident
集合、注入请求与到达过程，只改变已经在 R3D 中定义的 policy endpoint：

| lifecycle | policy | pressure scope | target | Prefill sequence | relevant scheduler steps |
| --- | --- | --- | ---: | --- | ---: |
| profile_f1_01 | admission T4096 | waiting-only | 4096 | `4096,8185` | 5 |
| profile_f1_02 | persistent T128 | waiting + running unfinished | 128 | 56 chunks，总和 12281 | 59 |

T4096 首次压力步只准入 4096 token；请求进入 running、waiting 归零后，下一步恢复 full budget，
一次处理余下 8185 token。T128 则产生 55 个 pressure chunk，并在 54 个 waiting 已归零的 step
中继续限制 running unfinished Prefill。两条路径均无 preemption。换言之，profiler 开启没有破坏
R3D 所研究的状态机差异。

任务退出后，0–7 卡的 keep-alive 恢复为 16 markers，端口 7000 无监听，无 vLLM 残留，
tracked worktree clean。收到的小包位于：
`/Volumes/SSD1/Inbox/2026-08-08/p6_3c_r3e_f1_attempt01_20260808_run01`。服务器上的 raw trace
保留在：
`/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_2026_0808_attempt_01/p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01`。

## 5. F1 的 rank-0 描述性结果

服务器现场为 16 份 rank profiler data 运行 Ascend trace conversion，但当时的 task-local analyzer
设置了 `max_ranks=1`，最终小包只聚合 rank 0。admission T4096 的 rank-0 `trace_view.json`
为 871,640,034 bytes，记录 3,788,657 个事件；persistent T128 为 2,928,549,101 bytes，现场
报告 5,000,001 个事件。后一个恰好落在 5,000,001 的计数需要在 A1 中确认：它可能是真实数组
长度，也可能来自现场 parser cap；在读到 JSON 数组结尾之前，不能把它写成完整性事实。

现场名称匹配聚合得到以下 duration-sum 构成：

| endpoint | collective | matmul/MoE | memory/sync | other |
| --- | ---: | ---: | ---: | ---: |
| admission T4096 | 31.27% | 22.44% | 25.88% | 20.41% |
| persistent T128 | 40.44% | 20.89% | 2.37% | 36.30% |

这些数值只能回答“被现场规则捕获的 timed range 以何种名称出现”。其 top events 混合了：

- `Dequeue@HcclAllGather`、`Dequeue@HcclReduceScatter`、
  `Dequeue@acl_memcpy_host_to_device` 等 runtime/queue 范围；
- `npu_fx_compiler inference`、`vllm::moe_forward_shared`、
  `vllm::matmul_and_reduce` 等高层 host annotation；
- `c10d::_allgather_base_`、`aten::matmul`、`npu::npu_quant_matmul` 等框架范围；
- `aclnnGroupedMatmul*`、`aclnnQuantMatmul*` 等 operator candidate；
- `_C_ascend::npu_sparse_attn_sharedkv`，它在旧 classifier 中落入 `other`。

因此不能从 40.44% 的 collective 名称占比直接推导 HCCL 位于因果 critical path，也不能因为旧表
没有 attention 行而说 attention 成本可忽略。多 stream 的 event duration 会重叠，高层 range 与
内部 kernel 还会嵌套；简单求和既可能双计数，也不等于 wall-clock。T4096 只有 2 个 Prefill chunk，
T128 有 56 个，两个窗口的 step 数与事件数也不同，raw duration sum 不能直接作为策略间性能比较。

## 6. 当前可以接受的结论

R3E 与 F1 联合支持三条结论。第一，R3D 的约 420 ms resident TBT floor 位于广义
EngineCore/executor path，而不是 Python scheduler/update bookkeeping。第二，request-scoped
profiler 在本项目 Ascend + vLLM 栈上可用，能够排除模型加载并捕获 measured staged-arrival
窗口。第三，在该窗口内确实出现 collective、MoE/matmul、attention candidate、runtime queue、
compiler 与 framework range；它们为下一层归因提供了搜索空间。

当前不能接受的结论是“下一步已经证明应优化 collective/compiler，而不是 matmul/attention”。
这个选择仍缺少三个条件：完整 rank 覆盖、可靠的事件来源分域，以及从事件到 scheduler mixed step
和 dependency-aware critical path 的连接。F1 的正式 outcome
`executor_path_supported_with_request_scoped_device_categories` 因而保留，但被解释为描述性执行路径
证据，而非唯一瓶颈结论。

## 7. R3E-F1-A1：零 NPU 全 rank 重聚合

A1 task ID 定义为
`p6_3c_r3e_f1_a1_cross_rank_trace_reaggregation_2026_0808`。它不启动 vLLM，不停止 keep-alive，
不重新执行请求，也不改变任何科学变量。输入是 F1 已保留的 raw/converted trace 和结构化 scheduler
mechanism evidence；输出是一个独立派生目录，源结果不可覆盖。

发布版实现包含两个组成部分：

1. `analyze_torch_profiler_traces.py`：支持 `.pt.trace.json(.gz)` 与 Ascend
   `trace_view.json(.gz)`，包括顶层 `traceEvents` object 和裸 event array；默认无 event cap，只有
   真正读到数组闭括号才记为 `parse_complete=true`；默认发现全部 rank；
2. `run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.py`：验证 F1 来源、聚合 8 rank × 2 lifecycle，
   以 mechanism evidence 中的 relevant step、Prefill chunk 与 pressure chunk 做归一化，并生成
   bounded result package。

事件分类被拆成两个正交维度。`evidence_domain` 记录事件来源证明力：

- `device_kernel`：由 device process metadata、trace category 或 event args 明确支持；
- `runtime_or_queue_wait`：dequeue/enqueue、ACL runtime、stream/event synchronization；
- `host_framework_range`：`aten::`、`vllm::`、`c10d::`、`_C_ascend::`、`npu::` 或 compiler range；
- `name_inferred_device_candidate`：只有 operator 名称像设备算子，没有 schema-level device provenance；
- `unclassified_timed_range`：其余 timed range。

`op_category` 则记录语义族：collective、attention、matmul/MoE、compiler/graph、memory transfer、
sampling、normalization/elementwise 与 other。Ascend sparse attention、flash attention、MLA 与
lightning indexer 被显式路由到 attention，避免“分类器未识别”被误写成“机制不重要”。

A1 对每个 trace 报告 rank、bytes、top-level schema、事件数、是否读到数组末尾、是否触发 event
limit、parse error 和各 evidence domain 计数；对每个 rank 报告 domain/category 聚合；对每条
lifecycle 报告跨 rank 的 median/min/max。若 timestamp 单调，分析器计算重叠区间并集
`active_time_union_us`，但仍明确标记为 activity 而不是 causal critical path。`npu_fx_compiler`
事件数将按 rank 与 Prefill chunk 归一化，用来检验“是否与小 chunk 重复共变”；HCCL queue range
只作为等待候选，除非 trace 存在足够 dependency-flow 证据，否则
`critical_path_identifiable=false`。

## 8. A1 的判定原则与后续决策

A1 完成需要两条 lifecycle 各有 8 个唯一 rank、所有 trace 无 event cap 且完整读到 JSON 末尾、
源 F1 小文件 SHA 与 trace size/mtime 在重聚合前后不变。完成时的科学 outcome 预定义为
`descriptive_cross_rank_execution_path_complete_causal_bottleneck_unresolved`。这个命名是有意的：
全 rank 重聚合能够修正 rank0 偏差和分类混淆，却不会凭空产生 kernel dependency graph。

后续只有在 A1 返回后才选择优化分支：

- 若 `npu_fx_compiler inference` 在各 rank 上按 chunk 近似重复，并有 cache/graph diagnostics
  证明发生实际 recompilation，则进入 shape/graph stability；
- 若 HCCL runtime wait 在多个 rank 的 mixed-step 窗口中暴露，且能与 device collective 依赖链对齐，
  则进入 communication/MoE overlap；
- 若 attention 或 matmul device kernels 支配 overlap-resolved active interval，则进入对应 kernel/shape
  分析；
- 若仍只有嵌套 host range 与 queue event 而无 dependency proof，则下一步应增加时间戳/flow 对齐，
  而不是提前选定优化对象。

这一策略延续本项目的核心原则：自动 grade 只是证据整理工具，科学推进来自研究问题、可辨识实验和
可复现证据。R3E-F1 已经成功关闭 request-scoped profiler capture；A1 的任务不是把结果改成另一种
颜色，而是把一次真实但现场化的成功运行转化为可以支持下一项系统优化决策的证据。

## 9. A1 全 rank 结果：完整性问题关闭，因果问题仍然开放

A1 在 `main@cdab34ed41c21cb1b9049eff12cb5d19144433cc` 上以零 NPU 方式完成。两条
lifecycle 的 rank 0–7 均被发现，16 个裸 JSON event array 全部读到闭括号，未设置 event cap。
admission T4096 的八个 rank 分别包含约 3.789M 个事件，总计 30,310,171；persistent T128
的每个 rank 包含约 12.473M 个事件，总计 99,784,353。因此 F1 现场报告的 5,000,001 并不是
T128 trace 的真实长度，而是旧 parser 的 `max_events=5,000,000` 截止标记。源 F1 目录在分析
前后保持不变，A1 没有启动 vLLM、停止 keep-alive 或重新生成请求。

跨 rank event count 呈高度对称结构。T4096 的 host-framework range 在每个 rank 上均为
270,091，T128 则均为 1,205,933；runtime/queue、name-inferred candidate 和 device-labelled
process range 的计数也在 rank 间接近。这个结果排除了“F1 的 rank 0 恰好走了一条特殊执行路径”
这一解释，却不能排除 rank 间等待时间差：按 A1 的 duration sum，T4096 八个 rank 的总量约为
74.2–87.3 s，T128 约为 337.7–414.6 s。由于 range 嵌套和 stream 并发，这些差异不能直接
解释为 wall-clock straggler，但足以把 rank skew 保留为下一层待验证假设。

A1 对三个最直接的候选解释给出了否定或限定性证据。第一，`npu_fx_compiler inference` 在
T4096 中共有 96 个事件，相当于每 rank 每 Prefill chunk 6.0 个；T128 中共有 1,136 个事件，
相当于 2.54 个。事件密度没有随 chunk 变小而增加，且这些 range 可能是嵌套的 compiler
annotation，不能证明每 chunk 发生重编译或 cache miss。第二，collective runtime/queue range
在 T128 中随 59 个 relevant step 大量出现，但按 step 归一化后的中位 duration 与 T4096 接近，
且现有表没有 enqueue→kernel→completion 的 flow 关系，因而不能把 HCCL duration sum 写成
exposed critical-path wait。第三，attention 在 host framework domain 中清晰可见：T4096 每
rank 735 个事件、约 94.6 ms 中位总量；T128 每 rank 5,030 个事件、约 449 ms。旧版 `other`
并非简单由遗漏 attention 导致，其中大量是 `EVENT_WAIT`、`NOTIFY_WAIT`、`Node@launch` 等
尚未获得设备语义证明的 timed range。

A1 的正式 outcome 因而是
`descriptive_cross_rank_execution_path_complete_causal_bottleneck_unresolved`。这里的
“complete”只指 16 份 trace 的覆盖和解析完整，不指 causal graph 已经完整。固定样本的性能事实
仍来自 R3D；A1 既没有形成新的性能样本，也没有选择 compiler、collective、MoE 或 attention
中的任何一个作为优化 target。

## 10. A1 后验审计揭示的两个方法学修正

收到 A1 小包后，开发机对 manifest 和 top events 做了逐文件复核。第一，A1 把 device-labelled
process 中的所有 timed range 统称为 `device_kernel`，但 duration 排名前列包含 `Free`、
`Computing`、`Communication`、`Communication(Not Overlapped)` 与 `Notify_Wait`。这些是
Ascend profiler 的派生分析时间线，而不是逐个真实 operator kernel。若把它们与 `aclnn*`/
HCCL kernel 放在同一 evidence domain，会把分析器生成的状态轨道误写成执行实体。发布版分类器
因此升级为三层：只有 trace category 或 event args 明确标记 kernel 的事件才进入
`actual_device_kernel`；上述五类进入 `device_analysis_timeline`；仅由 device process metadata
支持的其余 range 进入 `device_process_timed_range`。名称像设备算子但缺 schema provenance 的
事件仍为 `name_inferred_device_candidate`。

第二，A1 报告中的 candidate manifest 记录
`adaptive_execution_review.json=355 bytes, SHA prefix 0e5a...`，而实际收到的终态文件为
1,013 bytes，SHA-256=`8e9abfb01a0ee424558d48b7e0b088435ccc7200b07f7180f6f6700a0be35407`。
其余 11 个文件与报告相符，科学结果不受影响；差异说明服务器在 manifest 生成后补写了 adaptive
provenance。A1/A2 的 packaging 现被改为显式终态步骤：任何 task-local adaptation 更新
`adaptive_execution_review.json` 后必须重新运行 `package`，manifest 自身不列入候选集合，且
最后一次 package 是传输审查前的最后写操作。

## 11. R3E-F1-A2：从整窗描述转向 step 与依赖标识连接

A2 的 task ID 为
`p6_3c_r3e_f1_a2_step_flow_causal_linkage_2026_0809`。它继续复用 F1 的两个 profiler
lifecycle 和 A1 的完整性结论，不触 NPU、不重跑模型。与 A1 按整个 request-scoped window
聚合不同，A2 直接读取 F1 中同 lifecycle 保留的只读 scheduler observer JSONL，把每个
`timing_context_id` 的四个事件连接起来：`scheduler_step`、`executor_execute_submit`、
`executor_execute_complete` 与 `scheduler_update_complete`。每个执行窗定义为 execute submit
开始至 Future completion/update start 的单调时钟区间，并保留 step index、resident Decode token、
injected Prefill token 和 mixed/Decode-only/Prefill-only 类型。

Profiler timestamp 与 scheduler monotonic timestamp 的连接不通过手写固定 offset 完成。A2 对每个
rank 分别评估 microsecond/nanosecond/millisecond 三种时间单位，以及 monotonic/wall 两种 clock
origin；wall 与 monotonic 的 offset 由同一 observer row 中的 `timestamp_ns−monotonic_ns` 推导。
只有样本事件与 scheduler window 形成非偶然覆盖时才记为 `clock_alignment_reliable=true`。
随后所有 timed range 按实际区间与 step window 的交集做时间归属；async two-batch 可能让一个
event 同时落入多个 window，因此 A2 单列 multi-window count，并把 clipped duration sum 标记为
非 interval union、非 critical path。

依赖标识轨道独立于时间归属轨道。A2 完整扫描 Chrome `s/t/f` flow phase，并从 event/args 中提取
`correlation_id`、`external_id`、`record_function_id`、`sequence_number`、`flow_id`、
`connection_id` 与 `task_id`。原始标识不进入小包，只保留带 kind 的 SHA-256 前缀、事件数、
domain 集合和语义类别。一个 link value 只有同时出现在 host framework、runtime/queue 和设备
执行候选域时，才计入 host→runtime→device cross-domain link；时间上落入同一 step 但没有共同
标识的事件只构成 temporal containment，不构成 dependency proof。

A2 输出两类互补的 rank 证据。`step_rank_path_full.server_local.tsv` 保留每个
step×rank×execution-role 的完整归属，bounded package 只返回每条 lifecycle/rank 的主要 role；
`step_cross_rank_summary.tsv` 则报告每步 rank 覆盖、最晚活动 rank 和活动结束 skew。重点 role
显式区分 runtime collective queue、actual device collective kernel 和
`analysis_communication_not_overlapped`，从而可以判断先前的 HCCL 假设究竟获得了执行链支持，
还是只获得 profiler 派生时间线支持。

## 12. A2 的决策边界

A2 不预设一定能从既有 trace 中恢复 causal graph。若 clock alignment、8-rank step coverage 与
host→runtime→device 标识链同时存在，它可以把候选瓶颈收缩到具体 pressure step 和 rank；但即便
如此，只有同一类 dependency-linked final edge 在多数 pressure step 中反复出现，才足以选择优化
target。当前发布实现保守地保持 `causal_bottleneck_resolved=false`，把结构化链和时间窗交给
服务器真实 trace 决定后续证据是否充分，不会根据 automatic grade 自动宣布 collective 或 kernel
瓶颈。

若既有 trace 缺少可连接的 flow/correlation 字段，A2 的有效结果不是重复 R3D/R3E，而是精确报告
缺失的 clock、field、domain 或 rank 环节，并据此设计一个新的 R3E-F2：在 request-scoped 窗口内
增加显式 step 与 worker-rank correlation marker。F2 必须是独立 task ID 和独立 artifact chain，
且只补采能够关闭缺口的两个端点；不能把 instrumentation 变化冒充原 F1 的不变重聚合，也不能
重新回到没有机制辨识力的 budget 扫描。
