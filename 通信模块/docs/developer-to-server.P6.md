# P6.3C-R3E 服务器任务：Mixed Prefill/Decode step latency-floor attribution

这是一条新的 P6 研究任务，不是 R3D 重跑，也不是颜色评分修复。服务器 AI 的首要目标是获得
可解释的执行路径证据：在 R3D 已确认的约 420 ms mixed Prefill/Decode step floor 中，host
scheduler/update 与更宽的 EngineCore execution pipeline 分别贡献多少；两个代表策略的 msprof request
window 又对应哪些 device task / operator category。

服务器 AI 可以根据真实 Ascend 环境修复路径、overlay、导入顺序、msprof 参数、SQLite 布局、
health check、warmup、cleanup 和结果聚合。不要为了遵守过期的一次性脚本细节而放弃科学任务。
但凡改变请求、policy、target、cell、到达条件或指标定义，都必须建立新 variant，并明确报告
delta；不能把它伪装成原 R3E。

## 1. 任务身份与成功条件

- task ID：`p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01`
- source task：`p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01`
- source outcome：`persistent_prefill_tradeoff_no_candidate_within_bounds`
- workload：
  `benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_mixed_step_latency_floor_attribution.yaml`
- 正式入口：
  `tools/inference_contracts/run_deepseek_p6_3c_r3e_server_task.sh`
- expected：5 个 fresh-model lifecycle、50 条 EngineCore request、15 个本地 HTTP request、0 retry。

R3E 完整成功需要同时得到：

1. 三个 profiler-off host lifecycle 全部完成，并保留完整 Prefill chunk sequence、零 preemption；
2. 每个 measured scheduler step 的 `schedule → execute submit/Future → update` 事件可关联；
3. admission T4096、persistent T1024、persistent T128 都有 mixed Prefill/Decode timing rows；
4. 两个 diagnostic-msprof lifecycle 完成，并能对 request window 聚合 device task；
5. 结果明确区分 scheduler/update CPU、`execute_model` Future 子分量、广义 EngineCore pipeline 与 msprof device evidence；
6. 0–7 keep-alive 精确恢复，7000 端口与 vLLM 进程清理干净；
7. 生成不超过 70KB 的候选小包 manifest，但未经用户选择不得传输。

自动 grade 只是一种结构化汇总。若 finalizer 对现场 msprof schema 的假设有误，但 raw evidence
完整，服务器应修复聚合器、保存修复 provenance 并重新聚合；不要因 grade 非 green 重跑模型。

## 2. 科学合同：哪些不变，哪些是新测量

五个 lifecycle 共同固定：

- DeepSeek-V4-Flash W8A8+MTP，TP8+EP；
- `max_model_len=12288`；
- `max_num_batched_tokens=12288`；
- `max_num_seqs=9`；
- Prefix Cache 显式关闭；
- `FULL_DECODE_ONLY`、block size 128、async scheduling；
- 八个 resident request：每个 256-token Prompt、128-token 输出；
- 八者都输出至少 16 token 后，注入 12281-token Prompt、4-token 输出；
- Decode quantum=2；零 request retry。

三个 profiler-off host timing lifecycle：

| lifecycle | policy | pressure scope | target | profiler |
| --- | --- | --- | ---: | --- |
| `host_01` | `admission_on_t4096` | waiting-only | 4096 | off |
| `host_02` | `persistent_on_t1024` | waiting + running unfinished | 1024 | off |
| `host_03` | `persistent_on_t128` | waiting + running unfinished | 128 | off |

host gate 通过后才运行两个诊断 lifecycle：

| lifecycle | policy | profiler | 用途 |
| --- | --- | --- | --- |
| `profile_01` | `admission_on_t4096` | msprof on | 低迭代数 anchor |
| `profile_02` | `persistent_on_t128` | msprof on | 高迭代数端点 |

诊断 profiler 数据不参与 R3D 性能比较，也不得用于宣称 profiler-off absolute performance。
host observer 同时记录 `execute_model` Future 子分量，以及从 scheduler 返回到 update 开始的
EngineCore pipeline。后者还包含 async `sample_tokens` Future、batch queue、host RPC、worker、
device execution 和 synchronization；只有结合 msprof，才能进一步讨论 device task。

项目内诊断规则：若三个 policy 的 mixed-step EngineCore pipeline fraction 都至少为 0.80，且
persistent T128/T1024 的 mixed pipeline median 比值处于 `[0.75, 1.25]`，记录
`mixed_step_floor_executor_path_supported`。这不是外部标准，也不等于 NPU kernel 已被唯一归因。

## 3. 并发与 worktree：不要碰其他会话

先确认没有别的 P6/P8/vLLM/msprof 任务占用 0–7 号卡或 7000 端口。若其他会话正在运行，保持
其进程和 keep-alive 状态不变，本任务等待；不得 kill、复用其 worktree 或修改共享 checkout。

在共享仓库只做 fetch，然后从 `origin/main` 建独立 detached worktree：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3e_2026_0808

git -C "${SHARED_REPO}" fetch origin main
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" origin/main
git -C "${WORKTREE}" status --short --branch
git -C "${WORKTREE}" rev-parse HEAD
git -C "${WORKTREE}" rev-parse origin/main
git -C "${WORKTREE}" rev-list --left-right --count HEAD...origin/main
```

如果指定 worktree 已存在，不要删除；先判断它是否属于同一 task。需要新尝试时使用
`p6_3c_r3e_2026_0808_attempt_02` 之类的新目录。服务器不得 push remote `main`。

冲突检查至少包括：

```bash
npu-smi info
ss -ltnp | grep ':7000' || true
pgrep -af 'vllm|msprof|p6_3c|p8_' || true
```

## 4. 发布资产核验

以下 SHA 是同步/来源事实，不是禁止现场修复的冻结法律。若 tracked 文件 SHA 不同，先确认
worktree 是否已同步到最新 `origin/main`；不要在旧提交上运行。若服务器必须修改其中某文件，
在 task-local worktree/overlay 中保存 before/after SHA、diff、原因和 scientific impact。

| 文件 | SHA-256 |
| --- | --- |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_server_task.sh` | `34411fcac583b018281686940614eda12b3ccb9c4556a4fd8f3cd3850cd26551` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_experiment.sh` | `60afc301b3eea4aebaf43f3a4857a53146ed52f88ee4d3153ea372c1a8f6e4f4` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_mode.sh` | `9b8dd4f40a4e09ae159981ce803a087bdac3d0ab8300f209b4a9ef992d01cfe0` |
| `tools/inference_contracts/run_deepseek_p6_3c_r3e_latency_floor.py` | `f823cdec6b5105d8923f29ba325b1d6ab562213fedfde38db13b2c9f5b8bd886` |
| `tools/inference_contracts/p6_3c_r3_decode_resident_observer.py` | `d9eef094da2cd1d40a571ec6fd2d6a479f766e5f310ab26df1ab24f85e02b72c` |
| `tools/inference_contracts/p6_3c_r3d_persistent_scheduler.py` | `de40ae8329025159759f3ba1c2f11e5dee1f261765c160d3d0d23c0715b63107` |
| `tools/inference_contracts/p6_3c_r3d_sitecustomize.py` | `a2100f168fd3a158ec709e45f4b10bacb60b3171051cc359ebe225c81a4ab370` |
| `tools/inference_contracts/p6_3c_r3d_hybrid_kv_runtime_patch.py` | `8a040d89d3e004038137f8da882b4873dad77eabc23552b290b0920f2d64b83c` |
| `tools/inference_contracts/smoke_p6_3c_runtime_overlay.py` | `e00b8dcb8253636064c9cf16d8ae526ed700f471b1292e4f2545447bf30f71a6` |
| `tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh` | `44f0aa20c52e2c9da3f8b06f175f04962e743609567c92de03438b8a7b749133` |
| `tools/inference_contracts/analyze_msprof_request_device_aggregate.py` | `9285131bdb1c462845d059a812b6b838ca78a6a401dff81f61a35037d498ee21` |
| `tools/inference_contracts/analyze_msprof_sqlite_windows.py` | `1b1c11a4c86ad0382a9a7b5cb2859aefbeb29389f7081bd5266ad5a2b1e7781f` |
| `tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh` | `86bd3567b4e3315c69b67276e88609fef0794a3adb387168323511dcf8d1966b` |
| `tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh` | `a0b4e3fe55c962b954b61cf56b03d8a86d0ee25476c0fbefacf62c541b0616e8` |
| `tools/inference_contracts/prepare_p6_3c_runtime_overlay.py` | `5b8a95fbe2fc8ec81ea4a2243afea5d1093ee90fc6d8571691655b68de9162b0` |
| `tools/inference_contracts/resolve_p6_3c_runtime_layout.py` | `a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897` |
| `benchmarks/deepseek_v4_flash/workloads/p6_3c_r3e_mixed_step_latency_floor_attribution.yaml` | `c064659a991c210a936879cf5d79d59db7f53aec77f1d4e792c567a7192e0756` |
| `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch` | `2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f` |
| `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_acl_graph_update_params_compat.patch` | `777f6d87fa741c6c900ee251ddef79071b66017f17b192069468bfe349ed50d8` |
| `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch` | `75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1` |

请求源仍须为 19487 bytes，SHA-256：
`48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1`。

## 5. 零 NPU audit 与 profiler 预检

先完整阅读：

```bash
cd "${WORKTREE}"
sed -n '1,260p' docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
sed -n '1,360p' 通信模块/docs/developer-to-server.P6.md
```

零 NPU audit：

```bash
TASK_ID=p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r3e_server_task.sh \
  "/audit/${TASK_ID}"
```

audit 必须报告 5 lifecycle、50 EngineCore request、15 HTTP、0 retry，以及三条 host timing 和
两条 diagnostic msprof 的准确 schedule。audit 不得停 keep-alive、不得启动 vLLM。

在停卡前确认 `msprof` 可执行、结果盘空间足以容纳两个各上限 4096 MB 的 raw profile，并执行
runtime overlay import smoke。仓库已正式修复 smoke 的 callable 解析：检查
`acl_graph.update_full_graph_params` 中的 guard，而不是不存在的模块级 `update_graph_params`。

若 msprof 的参数名、输出目录或 SQLite 文件名与发布假设不同，允许先用不启动模型的
`msprof --help`、已有 server-local profile 或最小无 NPU解析做兼容修复。不得因 profiler 布局问题
修改 scientific request 或跳过三条 host timing。

## 6. 正式执行与 keep-alive

为保留 attempt lineage，使用外层 attempt 目录；传给入口的 RESULT_DIR basename 必须等于 task ID：

```bash
TASK_ID=p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01
ATTEMPT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_2026_0808_attempt_01
RESULT_DIR="${ATTEMPT_ROOT}/${TASK_ID}"

test ! -e "${RESULT_DIR}"
mkdir -p "${ATTEMPT_ROOT}"
cd "${WORKTREE}"
bash tools/inference_contracts/run_deepseek_p6_3c_r3e_server_task.sh "${RESULT_DIR}"
```

本任务需要 NPU 0–7。正式入口会执行以下规则；服务器 AI 仍须在报告中明确列出 stopped/restored
card IDs。只能停止本任务使用的 0–7，不得影响其他会话：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

无论成功、失败、中断还是 early exit，都必须恢复同一组 0–7，并核验 marker、7000 listener、
vLLM/msprof residual process 和 tracked worktree。若 host gate 失败，保留证据并停止，不进入
diagnostic profiler；如果失败来自 observer correlation 的真实代码问题，可以 task-local 修复并在
新 attempt 中重跑。若三条 host lifecycle 已完整，只有 profiler 聚合失败，优先原地只读重新聚合，
不要重跑模型。

## 7. 自适应执行权限与 provenance

允许：

- 修复 runtime path、editable-install 布局、overlay import、ACL graph guard、Ascend manager alias；
- 修复 msprof CLI、输出定位、SQLite table/column 名、request-window 对齐和 aggregation；
- 修复 proxy/no_proxy、health probe、warmup singleton、cleanup、finalizer 与 bounded packaging；
- 在独立 worktree 或 task-local overlay 内保存补丁并重试，只要新 attempt 能增加证据；
- 对已完成 raw evidence 做零 NPU 重新聚合。

每个 adaptation 必须保存：before/after 文件、SHA-256、最小 diff、失败摘录、attempt 顺序、
`scientific_impact`。服务器不得改 conda site-packages 或共享 checkout；确有必要时用物化 overlay，
并把补丁交回开发机审核。不得 push remote `main`。

以下变化必须建立新 variant：resident 数/长度、16-token injection gate、12281-token injected
Prompt、T4096/T1024/T128、pressure scope、Prefix Cache、MTP/graph、capacity contract、timing span
定义、request window 或 metric definition。

## 8. 结果解释：请直接回答科学问题

完成后请给出下列事实，而不是只报 grade：

1. 三个 policy 的 mixed-step 数、scheduler median、`execute_model` Future median、EngineCore
   pipeline median/P95、update median、full-step median和 pipeline fraction；
2. persistent T128/T1024 的 mixed pipeline median 比值，是否落入项目诊断区间；
3. scheduler/update 是否可能解释约 420 ms floor，还是成本主要落在广义 EngineCore pipeline；
4. 两个 profiler window 的 task row、summed duration、stream/task count 与 top operator category；
5. collective、matmul/MoE、attention、transfer/sync 的描述性占比/排序，以及 stream-overlap caveat；
6. R3D 的“persistent policy 无部署候选”结论是否保持；
7. 下一步应针对 host bookkeeping、RPC/sync、collective/graph，还是需要更细 worker marker。

若 msprof 无法把广义 EngineCore pipeline 进一步分解，应明确记录
`latency_floor_attribution_incomplete`，并指出缺少什么；不要把 host pipeline time 直接写成 NPU time。

## 9. 小包、传输与报告格式

raw scheduler trace、token timestamps、msprof（每条最多 4096 MB）、server log、request bodies 和
完整结果树全部留在服务器。候选小包上限 71680 bytes，只应包含 finalizer 生成的摘要、timing
aggregate、profiler aggregate、环境/资源与 manifest；不得包含 token ID、生成文本或 raw profile。

`result_transfer_authorized: true` 表示完整 bounded scope 可以进入选择，不等于已选择传输方式。
正式运行结束后，先报告：

- result summary 绝对路径；
- candidate manifest 绝对路径；
- 每个候选文件的 path / bytes / SHA-256 / sensitivity；
- 总文件数与总 bytes；
- available methods：`email`、`upload-api`、`server-local`；
- 推荐方法及原因。

然后等待用户对整个 scope 明确选择一种方法。不要先发 status-only 邮件，不要自行沿用上次
upload-api 选择。遇到 401/409/413、proxy、redirect、timeout、service 或 hash mismatch 后停止，
重新请用户选择。

请用以下骨架回报：

```text
P6_3C_R3E_SERVER_REPORT_BEGIN
task_id=
attempt_id=
worktree=
head=
origin_main=
ahead_behind=
asset_sha_gate=
zero_npu_audit_exit=
runtime_overlay_import_smoke_complete=
formal_experiment_started=
lifecycles=/5
engine_requests=/50
http_requests=/15
request_retries=
host_gate_complete=
host_mixed_step_summary=
persistent_t128_to_t1024_pipeline_median_ratio=
engine_pipeline_floor_supported=
profiler_lifecycles=/2
profiler_request_windows_complete=
profiler_operator_category_summary=
scientific_outcome=
scientific_contract_changed=
adaptive_attempt_count=
adaptive_patch_paths=
cleanup_status=
stopped_card_ids=
restored_card_ids=
keep_alive_restored_exact=
port_7000_listener_count=
vllm_residual_process_count=
msprof_residual_process_count=
tracked_worktree_clean=
result_dir=
candidate_manifest=
candidate_total_bytes=
transfer_method_selected=false
P6_3C_R3E_SERVER_REPORT_END
```

最后用自然语言回答 §8 的七个问题。不要自动进入下一任务。
