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
