# P6.3C-R3E-F1 服务器任务：请求窗口内的 device-category attribution

这是 R3E 的诊断补全任务，不是 R3E 性能实验重跑，也不是为了修改颜色评分。
R3E attempt03 已经用三个 profiler-off lifecycle 完成 host timing 归因，而且这些结果
必须保留。本轮只执行两个尚未完成的诊断 endpoint，用 vLLM 的 request-scoped
torch profiler API 在 warmup 之后开始采集，从而回答一个实质问题：已被定位到广义
EngineCore execution pipeline 的 mixed Prefill/Decode step 中，主要出现了哪些 NPU
operator category，以及 admission T4096 与 persistent T128 两个端点的设备路径有何差异。

服务器 AI 有权根据真实 Ascend 环境修复 task-local 路径、overlay、profiler config/API、
trace 布局、解析器、health check、warmup 和 cleanup，并在新 attempt 中继续取证。不要
因为历史脚本或自动 grade 的假阴性而放弃科学任务。但如果改变请求、policy、
target、cell、到达过程或 metric definition，必须建立新 variant/task ID，不得冒充 R3E-F1。

## 1. 已闭环的事实：不要重跑

源任务：

- task ID：`p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01`
- R3D 父任务：`p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01`；其
  `persistent_prefill_tradeoff_no_candidate_within_bounds` 性能结论不被本轮改写。
- 服务器源结果：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_2026_0808_attempt_03/p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01`
- 已完成 lifecycle：`host_01` / `host_02` / `host_03`
- host timing context：79 个；三个 host lifecycle 的请求、机制序列与 cleanup 已完成。

已确认的 mixed Prefill/Decode step 中位数：

| policy | mixed rows | scheduler (ms) | execute Future (ms) | EngineCore pipeline (ms) | pipeline P95 (ms) | update (ms) | full step (ms) | pipeline fraction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| admission T4096 | 2 | 2.854 | 721.392 | 828.738 | 1070.192 | 0.220 | 831.812 | 0.9961 |
| persistent T1024 | 12 | 2.233 | 805.464 | 858.228 | 953.814 | 0.198 | 860.915 | 0.9970 |
| persistent T128 | 55 | 2.004 | 805.366 | 874.032 | 905.231 | 0.198 | 876.266 | 0.9975 |

T128/T1024 的 mixed pipeline median ratio 为 `1.018415`。三个 policy 均有超过 99.6%
的 measured step 时间落在广义 EngineCore pipeline，Python scheduler/update bookkeeping 不能
解释约 420 ms 的 resident P99 TBT floor。结合 vLLM V1 的 2-batch async queue，
pipeline/2 与 R3D P99 TBT 在三个端点上仅相差约 2.1% / 2.1% / 4.2%；这是对
“两个 in-flight batch cadence 传导为稳态 TBT floor”的强支持，但还不是对某个 NPU
kernel 的唯一因果定位。

attempt03 的 process-wide `msprof vllm serve` 在模型加载期间就消耗了采集预算，
`profile_01` exit 143，`profile_02` 未运行，未获得 request-window device operator。因此本轮
不得再用整进程 msprof 包裹模型加载，也不得重跑三个 host lifecycle。

## 2. 本轮任务身份与成功条件

- task ID：`p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01`
- workload：
  `benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_f1_request_scoped_profile_completion.yaml`
- 正式入口：
  `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_server_task.sh`
- 新模型 lifecycle：2
- 新 EngineCore request（含 warmup）：20
- 新本地 HTTP request（含 warmup）：6
- retry：0

两个新 lifecycle：

| lifecycle | policy | pressure scope | target | profiler window |
| --- | --- | --- | ---: | --- |
| `profile_f1_01` | `admission_on_t4096` | waiting-only | 4096 | warmup 后、measured trial 前 start，trial 后 stop |
| `profile_f1_02` | `persistent_on_t128` | waiting + running unfinished | 128 | warmup 后、measured trial 前 start，trial 后 stop |

两条共同固定：

- DeepSeek-V4-Flash W8A8+MTP，TP8+EP；
- `max_model_len=12288`，`max_num_batched_tokens=12288`，`max_num_seqs=9`；
- Prefix Cache 显式关闭，`FULL_DECODE_ONLY`，block size 128，async scheduling；
- 8 个 resident：256-token Prompt + 128-token output；
- 8 个 resident 均生成至少 16 token 后，注入 12281-token Prompt + 4-token output；
- Decode quantum=2，0 retry；
- vLLM server 启动时加载 torch profiler config，但不自动开始采集；
- warmup 完成后，driver 才 `POST /start_profile`，measured staged-arrival trial 完成后
  `POST /stop_profile`；
- 模型加载、server readiness 和 warmup 不进入 trace。

完整成功需要：

1. 源 R3E host 证据的 5 个文件验证通过，证明源目录未被覆盖；
2. 2/2 lifecycle exit 0、20/20 EngineCore request、6/6 HTTP request、0 retry；
3. 两条 lifecycle 的 `/start_profile` 与 `/stop_profile` 均成功，并保存调用时序/状态；
4. 两个 profiler 目录均有可解析的 Chrome trace，且有 device event；
5. 两个 policy 的完整 Prefill chunk sequence 与零 preemption 机制证据保留；
6. 输出按 lifecycle 的 trace/rank inventory、device category duration/event count 与 top operator；
7. 资源恢复干净：仅恢复本任务停止的卡，7000 端口无监听，无本任务 vLLM 残留；
8. 生成不超过 70KB 的候选小包 manifest，但不自动传输。

profiler-on 数据不用于 absolute performance 或 On/Off 性能声明。并行 stream 可重叠，
event duration 之和只是诊断计数，不是 wall-clock decomposition。

## 3. 并发互斥与独立 worktree

上一轮已经遇到另一个 Qwen3.6-27B vLLM 任务占用 0–7 卡。本轮必须先做
外部作业互斥检查。如果任何非本任务 vLLM、训练或 NPU 进程正在使用目标卡：

- 不要 kill 它；
- 不要停止它的 keep-alive 或重置卡；
- 不要启动 R3E-F1；
- 保留冲突证据，等待资源空闲后再执行。

从最新 `origin/main` 建立独立 detached worktree：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3e_f1_2026_0808

git -C "${SHARED_REPO}" fetch origin main
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" origin/main
git -C "${WORKTREE}" status --short --branch
git -C "${WORKTREE}" rev-parse HEAD
git -C "${WORKTREE}" rev-parse origin/main
git -C "${WORKTREE}" rev-list --left-right --count HEAD...origin/main
```

指定 worktree 已存在时不要删除；判断是否属于同一任务，新尝试使用
`p6_3c_r3e_f1_2026_0808_attempt_02` 等新目录。不要修改共享 checkout，服务器不得 push
remote `main`。

开始前至少执行：

```bash
npu-smi info
ss -ltnp | grep ':7000' || true
pgrep -af 'vllm|torchrun|deepspeed|msprof|p6_3c|p8_' || true
```

正式入口还会在停卡前检查活跃 `vllm.*serve`；发现外部 serving process 时必须结束
当次尝试，不得绕过此保护。

## 4. 发布资产与 SHA 核验

以下 SHA 是开发机发布事实和同步门，不是禁止现场修复的旧式冻结合同。
若 tracked 文件不同，先确认 worktree 是最新 `origin/main`。如果必须现场修改，在独立
worktree/task-local overlay 保存 before/after SHA、diff、原因、attempt 顺序和
`scientific_impact`，并交回开发机审核。

| # | 文件 | SHA-256 |
| ---: | --- | --- |
| 1 | `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_server_task.sh` | `33d583844b4b8534c3927b7a3f1e6803fb0b10949f0b0e5359b78b999225db9f` |
| 2 | `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_experiment.sh` | `18f7b70a3bce6899bd0b1c7883f67133ad47d41dce97c0f7c9535c3920ef106c` |
| 3 | `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_mode.sh` | `db954e8510d8ec0fd4eb39ccfd359e2359ca20b43a34ad32dee3c9322095cda7` |
| 4 | `tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_profile_completion.py` | `35cdfc645690ae52354508dc35d736439dde790bbf51bc0f99187f300521c643` |
| 5 | `tools/inference_contracts/analyze_torch_profiler_traces.py` | `b4af82c54cfe4434a7de9223f95f92d0f3376ec5da7e9d7292176b231ad1defa` |
| 6 | `tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh` | `d968640f1ce3736dbeabcd5d101c82b0970129fab2d203b5ecee16bf0f7e1974` |
| 7 | `tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py` | `ebd39bba812da6b63ede782df35d930da1270fdb60c436f1f8de906031577f3c` |
| 8 | `tools/inference_contracts/run_deepseek_p6_3c_r3e_latency_floor.py` | `1154059c8a61049f7fffd69d3a91ab7de2a1c154b37e3fdc462e2f6758d97cbc` |
| 9 | `tools/inference_contracts/p6_3c_r3_decode_resident_observer.py` | `d9eef094da2cd1d40a571ec6fd2d6a479f766e5f310ab26df1ab24f85e02b72c` |
| 10 | `tools/inference_contracts/p6_3c_r3d_persistent_scheduler.py` | `de40ae8329025159759f3ba1c2f11e5dee1f261765c160d3d0d23c0715b63107` |
| 11 | `tools/inference_contracts/p6_3c_r3d_sitecustomize.py` | `a2100f168fd3a158ec709e45f4b10bacb60b3171051cc359ebe225c81a4ab370` |
| 12 | `tools/inference_contracts/p6_3c_r3d_hybrid_kv_runtime_patch.py` | `8a040d89d3e004038137f8da882b4873dad77eabc23552b290b0920f2d64b83c` |
| 13 | `tools/inference_contracts/smoke_p6_3c_runtime_overlay.py` | `e00b8dcb8253636064c9cf16d8ae526ed700f471b1292e4f2545447bf30f71a6` |
| 14 | `tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh` | `86bd3567b4e3315c69b67276e88609fef0794a3adb387168323511dcf8d1966b` |
| 15 | `tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh` | `a0b4e3fe55c962b954b61cf56b03d8a86d0ee25476c0fbefacf62c541b0616e8` |
| 16 | `tools/inference_contracts/prepare_p6_3c_runtime_overlay.py` | `5b8a95fbe2fc8ec81ea4a2243afea5d1093ee90fc6d8571691655b68de9162b0` |
| 17 | `tools/inference_contracts/resolve_p6_3c_runtime_layout.py` | `a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897` |
| 18 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_f1_request_scoped_profile_completion.yaml` | `2090bcdb010b81b6a60fd0d624c3a5ad2f3d905b8808f2fc6e12e3295dcd84e1` |
| 19 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch` | `2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f` |
| 20 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_acl_graph_update_params_compat.patch` | `777f6d87fa741c6c900ee251ddef79071b66017f17b192069468bfe349ed50d8` |
| 21 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch` | `75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1` |

请求 payload 仍必须为 19487 bytes，SHA-256：
`48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1`。

## 5. 源 R3E 证据身份

在任何 NPU 操作之前，验证源目录存在且未被修改。必需文件的开发机收到版
SHA-256 如下；服务器源文件应与之一致：

| 文件 | SHA-256 |
| --- | --- |
| `r3e_host_attribution.json` | `1a381cece67defcbffefb0b3e48a80e88a2e4b4535ce505c8ac79a57257ef5b3` |
| `r3e_host_phase_summary.tsv` | `eb3dd92ee3c1339777ac76d2df58a04c57c6d5da69b12f451c0b5bf49ea4d705` |
| `r3e_mechanism_cells.tsv` | `d7dd71ff2d8add1671f69b0f9bdc3d4d53c6e8625711c5b58dd0f4703cf484d9` |
| `lifecycle_summary.tsv` | `2cf1b9b3021ea7a3800d662b7d88eaa1ae766a6b2b888cd188d0be06b1c49cc5` |
| `environment_and_hashes.json` | `52720e986a54b2c18437cfd798dabacbed6144f53ac9a6f899eba9a4397c54e8` |

使用发布 runner 进行结构化验证：

```bash
cd "${WORKTREE}"
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
SOURCE_R3E=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_2026_0808_attempt_03/p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01

sha256sum \
  "${SOURCE_R3E}/r3e_host_attribution.json" \
  "${SOURCE_R3E}/r3e_host_phase_summary.tsv" \
  "${SOURCE_R3E}/r3e_mechanism_cells.tsv" \
  "${SOURCE_R3E}/lifecycle_summary.tsv" \
  "${SOURCE_R3E}/environment_and_hashes.json"

"${ENV_PREFIX}/bin/python" \
  tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_profile_completion.py \
  validate-source --source-r3e-result "${SOURCE_R3E}"
```

该命令必须返回 `source_host_evidence_complete=true`。新结果中只记录这 5 个文件的
bytes/SHA 和结构化事实，不覆盖、搬移或重写源结果目录。

## 6. 零 NPU audit 与 profiler capability preflight

先完整阅读：

```bash
cd "${WORKTREE}"
sed -n '1,320p' docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
sed -n '1,520p' 通信模块/docs/developer-to-server.P6.md
```

零 NPU audit：

```bash
TASK_ID=p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_server_task.sh \
  "/audit/${TASK_ID}"
```

audit 必须报告：2 lifecycle、20 EngineCore request、6 HTTP、0 retry、`max_model_len=12288`、
`max_num_batched_tokens=12288`、`max_num_seqs=9`、profiler backend 为
`vllm_torch_profile_api`、model loading 不被 profile。audit 不得停 keep-alive、启动 vLLM 或
访问 NPU。

在停卡前，还要用已解析的 vLLM runtime 做无 NPU capability 检查：

1. `vllm serve --help` 或对应 parser 包含 `--profiler-config`；
2. 实际版本的 API server 注册 `POST /start_profile` 和 `POST /stop_profile`；
3. `ProfilerConfig` 支持 torch profiler 以及 server-local output directory；
4. runtime overlay import smoke 四项 Ascend manager resolution 与 ACL graph guard 全部通过；
5. 结果盘空间足够，raw trace 仅保留在服务器。

如果实际 vLLM 的 profiler JSON key、API response、trace 后缀、rank/pid 布局或 gzip 行为与
发布假设不同，这属于允许的 runtime compatibility repair；请在 task-local worktree 修复并
保留 provenance，不要改科学请求。

## 7. 正式执行与 keep-alive

在“没有其他 NPU/vLLM 作业、资产核验通过、源证据验证通过、audit 通过”之后，
使用新 attempt 目录运行：

```bash
TASK_ID=p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01
ATTEMPT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f1_2026_0808_attempt_01
RESULT_DIR="${ATTEMPT_ROOT}/${TASK_ID}"
SOURCE_R3E=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_2026_0808_attempt_03/p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01

test ! -e "${RESULT_DIR}"
mkdir -p "${ATTEMPT_ROOT}"
cd "${WORKTREE}"
P6_3C_R3E_SOURCE_RESULT="${SOURCE_R3E}" \
  bash tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_server_task.sh \
  "${RESULT_DIR}"
```

本任务需要 NPU 0–7。仅在确认无其他作业后，才可停止本任务需要的低优先级
keep-alive：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

无论 success、failure、interrupt 还是 early exit，都必须在 finally 路径恢复同一组卡。报告
`stopped_card_ids`、`restored_card_ids`、marker 计数、`keep_alive_restored_exact`、7000 listener、
本任务 vLLM residual 和 tracked worktree 状态。如果 keep-alive 初始状态因其他作业不是
16 markers，不得伪造 exact restoration；应优先判定外部作业并且不执行本任务。

## 8. 现场修复、重试与停止分支

允许直接修复并在新 attempt 中继续：

- runtime path、editable-install 布局、overlay import、ACL graph guard、Ascend manager alias；
- `--profiler-config` 实际 schema、torch profiler output path、gzip/Chrome trace 后缀、rank/pid 布局；
- `/start_profile` / `/stop_profile` 控制调用、timeout、API response 解析；
- 流式 parser 的现场 trace schema 兼容、operator 名称分类和 bounded aggregation；
- loopback proxy、health probe、warmup singleton、cleanup、finalizer、manifest 和 packaging；
- 对已完成 raw trace 进行零 NPU 重新解析，不重跑模型。

每个 adaptation 必须保存：before/after 文件及 SHA、最小 diff、first failure excerpt、
attempt 顺序、`scientific_impact`。不要直接改 conda site-packages；使用物化 runtime overlay
或独立 worktree。不得 push remote `main`。

明确不允许的降级：

- 不要再用 process-wide msprof 包裹 `vllm serve`；
- 不要把模型加载 trace 当成 request device evidence；
- 不要为了让 grade 变绿而修改请求、target、pressure scope 或 metric；
- 不要从 profiler-on lifecycle 推断 absolute performance、TTFT/TBT 收益或回归；
- 不要把各 stream 的 duration sum 直接当作 wall-clock 占比。

如 vLLM request-scoped torch profiler 在 Ascend worker 上没有产生任何 device event，服务器 AI 先检查
profiler 是否在 worker 启用、环境变量是否传递、输出目录是否按 rank 分散。必要时，允许在
task-local runtime overlay 中对实际 worker profiler hook 做最小修复，但必须仍由同一对
`start_profile/stop_profile` 将采集限定在 measured request window。这属于可记录的实现修复；
如果需要改变采集窗口或请求过程，则必须新建 variant。

停止条件：

- 源 host 证据不完整且无法从保留的 R3E 源目录恢复；
- 外部 NPU/vLLM 作业持续占用目标卡；
- 修复必须改变科学合同，但未创建新 variant；
- 资源无法安全恢复。

如果两条 measured trial 与 trace 均完整，仅 finalizer/parser 失败，必须优先零 NPU
修复和重聚合，不得重跑模型。

## 9. 科学证据与解释要求

流式解析器会扫描 `.pt.trace.json` / `.pt.trace.json.gz`，避免把大型 Chrome trace 整体
载入内存。默认类别是：

- `collective_communication`；
- `matmul_or_moe`；
- `attention`；
- `memory_transfer_or_sync`；
- `sampling_or_selection`；
- `other`。

请不要只报 grade，而要直接回答：

1. 源 R3E 的 5 个证据文件是否与上述 SHA 完全相等，结构化 host gate 是否通过；
2. 两条 profiler lifecycle 的 start/stop 时间、HTTP status、trace 数量、rank/pid 与 device event 数；
3. admission T4096 与 persistent T128 的完整 Prefill chunk 序列、mixed step 数、preemption 数；
4. 每个 lifecycle 各 operator category 的 event count、summed duration、描述性 fraction 和排名；
5. 每个 lifecycle 的 top device operator，并指出 collective、matmul/MoE、attention、
   transfer/sync 中哪些在两端点有系统差异；
6. 证据是否支持将下一轮优化定位到 collective/graph、matmul/MoE、attention，还是仍需要
   worker marker 或同步边界；
7. R3D 的 `persistent_prefill_tradeoff_no_candidate_within_bounds` 结论是否完整保持。

如果只获得 host trace 而没有 NPU device event，结论必须是
`latency_floor_device_category_attribution_incomplete`，并明确缺少的 hook/边界；不要把
EngineCore pipeline time 直接写成 NPU kernel time。

## 10. 结果小包、传输选择与回报格式

raw Chrome trace、scheduler trace、token timestamps、server log、request bodies 和完整结果树都留在
服务器。候选小包不超过 71680 bytes，只包含 19 个 bounded summary/inventory 候选文件；
不得包含 raw trace、token ID 或生成文本。

`result_transfer_authorized: true` 表示该完整 bounded scope 可以进入传输选择，不等于已选
传输方式。任务完成后先报告：

- result summary 绝对路径；
- candidate manifest 绝对路径；
- 完整候选文件清单，每个文件的 path / bytes / SHA-256 / sensitivity；
- 总文件数与总 bytes；
- available methods：`email`、`upload-api`、`server-local`；
- 推荐方法及理由。

然后等待用户对整个 scope 明确选择一种方法。不要先发 status-only 邮件，不要沿用
上一轮 upload-api 选择。遇到 401/409/413、proxy、redirect、timeout、service 或 hash
mismatch 时停止，重新请用户选择。

请按以下骨架回报：

```text
P6_3C_R3E_F1_SERVER_REPORT_BEGIN
task_id=
attempt_id=
worktree=
head=
origin_main=
ahead_behind=
tracked_clean=
shared_checkout_modified=
asset_sha_gate=
source_r3e_result=
source_r3e_hashes_exact=
source_host_evidence_complete=
zero_npu_audit_exit=
runtime_profile_capability_preflight=
external_npu_or_vllm_conflict=
formal_experiment_started=
lifecycles=
engine_requests=
http_requests=
retries=
profile_api_control_complete=
profile_f1_01_start_stop_status=
profile_f1_02_start_stop_status=
trace_inventory_complete=
device_event_count_by_lifecycle=
mechanism_complete=
preemption_count=
scientific_outcome=
parent_r3e_host_outcome_preserved=
parent_r3d_outcome_preserved=
scientific_contract_changed=
adaptive_attempt_count=
adaptive_patch_paths=
cleanup_status=
stopped_card_ids=
restored_card_ids=
keep_alive_marker_count=
keep_alive_restored_exact=
port_7000_listener_count=
vllm_residual_process_count=
result_summary=
candidate_manifest=
candidate_file_count=
candidate_total_bytes=
transfer_method_selected=false
available_methods=email,upload-api,server-local
recommended_method=
next_task_authorized=false
P6_3C_R3E_F1_SERVER_REPORT_END
```

随后用自然语言单独回答上一节的 7 个科学问题。如果任务因外部作业冲突而未开始，
仍须报告冲突进程与未触发 keep-alive/NPU 的事实，不得继续执行或杀死其他会话。
