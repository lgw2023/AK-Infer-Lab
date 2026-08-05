# 开发机 → Ascend 服务器：P6.3C-R3C Decode-SLO-aware adaptive budget

更新时间：2026-08-05

任务 ID：`p6_3c_r3c_adaptive_budget_2026_0805_run01`

任务性质：`NPU / new scientific variant / adaptive scheduler policy`

本文件是当前 P6.3C 活跃任务的唯一交接合同。它替换已完成的 R3B-A1 零 NPU 再聚合交接，但不覆盖 R3B、R3A、F4 或原始 blocked 审计的结果目录和结论。

## 1. 本轮实质目标

R3B 已完成五档静态 On budget 的性能再聚合：所有 On 点都显著降低 admission-cliff 注入 TTFT，但 resident Decode 的 P99 TBT 增加 345.6%–681.6%，TPS 下降 6.8%–20.4%，没有静态点同时满足项目内部署边界。本轮不再继续寻找另一个固定最优 budget，而是验证动态策略能否把“无竞争”和“Decode 驻留 + 等待 Prefill”两种状态分开处理。

控制律：

```text
configured_budget = max_num_batched_tokens = 12288
D = decode_resident_count × decode_quantum_tokens
if decode_resident_count > 0 and waiting_prefill_count > 0:
    effective_budget = min(12288, D + active_chunk_target_tokens)
else:
    effective_budget = 12288
```

控制器只临时改变 `Scheduler.max_num_scheduled_tokens`，不改变 `SchedulerConfig.max_num_batched_tokens`、`max_model_len`、KV cache 容量或请求集合。R3C 的 `decode_quantum_tokens=2`，目标网格是 2048、4096、8192。

## 2. 谱系和比较语义

- 原 P6.3C `135168/4096/1`：`blocked_p6_3c_not_strict_single_variable`，保留审计事实。
- R2-F4：`accepted_chunked_prefill_scheduler_mechanism_observed`，保留受控共到达机制结果。
- R3A：`mechanism_confirmed_tradeoff_only`，保留 Decode-resident admission cliff 结果。
- R3B-A1：`pareto_frontier_observed_no_candidate_within_bounds`，保留静态 budget Pareto 结果。
- R3C 是新 policy variant，不是 R3B 重跑，不是 strict boolean-only A/B，不覆盖旧结果。

## 3. 固定平台和请求合同

```text
model=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
served_model_name=deepseek-v4-flash-w8a8-mtp
vllm=0.22.1+empty; vllm_ascend=0.22.1rc1
TP=8; EP=true; MTP speculative tokens=1
graph=FULL_DECODE_ONLY; block_size=128; async_scheduling=true
prefix_cache=false; max_model_len=12288; max_num_seqs=9
profiler=disabled; retry=0
```

每个 lifecycle 沿用已审计 staged-arrival workload：一个 batched streaming request 携带 8 个 resident choice，每个 256 prompt + 128 output；8 个 resident 都流出 16 token 后，发送独立 injected streaming request（12281 prompt + 4 output）；cell 为 `resident_only` 和 `admission_cliff_12281`；不保存生成文本和 token ID；Prefix Cache 两侧显式关闭。

## 4. 五个 policy

| policy | chunked flag | CLI `max_num_batched_tokens` | 运行时行为 |
|---|---|---:|---|
| `off_b12288` | Off | 12288 | 合法 Off 基线 |
| `static_on_b8192` | On | 8192 | R3B 静态 anchor |
| `adaptive_on_t2048` | On | 12288 | pressure 时 `D+2048`，否则 12288 |
| `adaptive_on_t4096` | On | 12288 | pressure 时 `D+4096`，否则 12288 |
| `adaptive_on_t8192` | On | 12288 | pressure 时 `D+8192`，否则 12288 |

adaptive policy 的关键审计点：CLI 和 `SchedulerConfig.max_num_batched_tokens` 始终为 12288，变化只能出现在 `schedule()` 调用期间的 `max_num_scheduled_tokens`。若现场发现控制器修改了配置 budget、KV cache 初始化参数、请求、cell、阈值或指标定义，必须停止并报告。

## 5. 生命周期和执行顺序

总计 14 个 fresh-model lifecycle：4 个机制 lifecycle + 10 个性能 lifecycle。

机制轨道（observer 开启，profiler 关闭）：

```text
mechanism_01 static_on_b8192
mechanism_02 adaptive_on_t2048
mechanism_03 adaptive_on_t4096
mechanism_04 adaptive_on_t8192
```

性能轨道（observer 和 profiler 均关闭）：

```text
round_1: off_b12288, static_on_b8192, adaptive_on_t2048, adaptive_on_t4096, adaptive_on_t8192
round_2: adaptive_on_t8192, adaptive_on_t4096, adaptive_on_t2048, static_on_b8192, off_b12288
```

每个 lifecycle 使用既有顺序平衡的 12 个 measured trial：`resident_only, cliff, cliff, resident_only` 重复三次。每个 policy-cell 目标为 12 个有效 trial，每个 On policy 与同一 mirror round 的 Off cliff trial 配对。resident TBT SLO 继续定义为 `2× Off resident-only pooled median TBT`，它是项目分析阈值，不是外部标准。

预期计数：`14 lifecycle / 1070 engine requests / 202 HTTP requests / 0 retry`。

## 6. 发布资产、worktree 和入口

服务器在独立 detached worktree 中执行，不改共享 checkout，不要求服务器 push `main`。核验：

```text
benchmarks/deepseek_v4_flash/workloads/p6_3c_r3c_adaptive_budget.yaml
tools/inference_contracts/p6_3c_r3c_adaptive_scheduler.py
tools/inference_contracts/p6_3c_r3c_sitecustomize.py
tools/inference_contracts/run_deepseek_p6_3c_r3c_adaptive_budget.py
tools/inference_contracts/run_deepseek_p6_3c_r3c_mode.sh
tools/inference_contracts/run_deepseek_p6_3c_r3c_experiment.sh
tools/inference_contracts/run_deepseek_p6_3c_r3c_server_task.sh
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh
tools/inference_contracts/p6_3c_r3_decode_resident_observer.py
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
```

发布资产 SHA-256（服务器先核对字节级一致；本段随代码提交更新）：

```text
benchmarks/deepseek_v4_flash/workloads/p6_3c_r3c_adaptive_budget.yaml=deea24994e1e7cea9f972df03ca84855a32fa69fc3c1ccef431071264a784583
tools/inference_contracts/p6_3c_r3c_adaptive_scheduler.py=de36f72244e4c8e86d98c9b8b36c1b58b7f697f1edb72a1e41cb6df0b8d66fe4
tools/inference_contracts/p6_3c_r3c_sitecustomize.py=3341cc272fc49dd55dda4259aa46f428701d833010bf61761b80ad47390469c9
tools/inference_contracts/run_deepseek_p6_3c_r3c_adaptive_budget.py=7c7fb367630d5206848b082e1ae60cc1e6f5a9738a8b55a3733e66df24539bc5
tools/inference_contracts/run_deepseek_p6_3c_r3c_mode.sh=dde477fadae81c35bfdc1adb64b920440d54a4a538b1b4703891bb8f75c66f27
tools/inference_contracts/run_deepseek_p6_3c_r3c_experiment.sh=d2fddbbfea496272cf472cc8af98c959ebc4553e4c00567ffd47814da97bd38f
tools/inference_contracts/run_deepseek_p6_3c_r3c_server_task.sh=0a2532bc477f65f240dff8aa0676738e0c8975bff70ba3528711f5248d95be67
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh=47638a8a43fa5bc8add41f67673f6beb4a75dfec01c3bf1c9f9270f8e5a1ff08
tools/inference_contracts/p6_3c_r3_decode_resident_observer.py=9c2147a7eb1e703da100bcff6cc31481f9c0ba7fe17bdf2375b9383ad71e9a15
tests/inference_contracts/test_deepseek_p6_3c_r3c_adaptive_budget.py=88672e12abdb5ebfd983e9201773165f2327a46a8148a4dbe13ce4db1e74721c
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md=7dff584b742bfba91df332a8671c7430675d7dfacb9c3a15144dae1b3034fe0e
```

其中 `run_deepseek_p6_3c_r1_mode.sh` 是 R3C 复用并修改过的既有生命周期入口；其 SHA 必须核对。

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git fetch origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git worktree add --detach   /data/node0_disk1/liguowei/server_worktrees/p6_3c_r3c_2026_0805   origin/main
```

在 worktree 中核对上述文件存在、Python 可导入、shell 可解析，并记录逐文件 SHA-256。若发生 task-local repair，保留独立 worktree、attempt 编号、前后 diff、SHA 和 scientific-impact statement；服务器不得 push 远端 `main`。

零 NPU audit：

```bash
P6_3C_SERVER_TASK_AUDIT_ONLY=1   bash tools/inference_contracts/run_deepseek_p6_3c_r3c_server_task.sh   /audit/p6_3c_r3c_adaptive_budget
```

正式入口：

```bash
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3c_adaptive_budget_2026_0805_run01
bash tools/inference_contracts/run_deepseek_p6_3c_r3c_server_task.sh "${RESULT_DIR}"
```

正式运行前必须完成 audit、Git、路径、payload SHA、runtime layout、overlay preflight 和并发冲突检查。健康检查必须直连 loopback，不得经华为代理访问 `127.0.0.1:7000`。

## 7. 控制器运行时证据

`run_deepseek_p6_3c_r1_mode.sh` 在 task-local overlay 中复制 controller 和 `sitecustomize.py`。vLLM 子进程只在 `P6_3C_R3C_ADAPTIVE_ENABLED=1` 时安装 wrapper。安装成功必须生成：

```text
lifecycles/<id>/runtime/adaptive_controller_installed.json
lifecycles/<id>/runtime/adaptive_controller_identity.tsv
lifecycles/<id>/runtime/adaptive_controller_self_test.txt
lifecycles/<id>/runtime/adaptive_scheduler_trace/schedule_decisions.jsonl
```

trace 每条记录至少含 `timestamp_ns`、`pid`、`configured_budget`、`decode_resident_count`、`waiting_prefill_count`、`decode_reserve_tokens`、`active_chunk_target_tokens`、`selected_budget`、`decision` 和 `previous_budget`。机制 observer trace 还必须含 `effective_token_budget` 与 `controller_decision`；前者是本轮实际使用的 per-iteration budget，不能用 wrapper 恢复后的 `token_budget` 替代。性能 lifecycle 不安装 scheduler observer，但 controller trace 仍是策略生效的控制证据，不是额外性能指标。

机制首步在 D=16 时应出现：

```text
target 2048 -> selected budget 2064
target 4096 -> selected budget 4112
target 8192 -> selected budget 8208
```

如果实际 D 不为 16，按现场 trace 计算 `D+target` 并报告，不硬改预期值。resident-only 必须能看到 `full_budget=12288`，否则控制器状态条件没有被证明。

## 8. 自适应权限和停止条件

遵循 `docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md`：允许在独立 worktree 内修复运行时路径、editable/site-package 布局、Python import、overlay、sitecustomize 初始化时序、loopback 健康检查、warmup、trace 写入和 cleanup。每次修复保留 before/after diff、SHA、attempt 和影响说明。

改变 policy target、CLI budget、`max_model_len`、`max_num_seqs`、请求、gate、cell、trial 数、指标、SLO threshold、配对方式、Pareto 定义或“configured budget 保持 12288”的语义，必须新建 variant，不得继续使用本 task ID。

以下情况立即停止相应阶段：

1. 前置 SHA、payload、Git ancestor 或并发门失败：不触 NPU；
2. controller 无法安装、无 trace、pressure/full-budget 决策不完整：停止在机制门；
3. 机制门未全部通过：不跑性能轨道；
4. 请求/lifecycle/资源恢复不完整：保留首错证据，不伪造绿色；
5. 发生科学变量变化：停止当前任务并按新 variant 回报。

## 9. NPU keep-alive 和资源恢复

本轮使用 0–7 号卡。开始前确认无其他 NPU 作业，只停止实际使用的卡：

```bash
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
```

无论成功、失败、超时、Ctrl-C、overlay 失败还是健康检查失败，都必须恢复同一集合：

```bash
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

报告必须给出 `stopped_card_ids=0,1,2,3,4,5,6,7`、`restored_card_ids=0,1,2,3,4,5,6,7`、`keep_alive_restored_exact=true`，并核对 16 markers、port 7000 无监听、无 vLLM residual process、tracked worktree clean。若未触卡，明确 stopped/restored 为 none，并说明 keep-alive left running。

## 10. 结果包、传输和固定回报

原始 scheduler trace、token timestamps、server log 和大目录留在服务器。候选小包上限 70KB，建议包含以下 bounded files（最终以 `candidate_manifest.server_local.json` 为准）：

```text
result_summary.md; environment_and_hashes.json; payload_identity_summary.json; lifecycle_summary.tsv
r3c_mechanism_budget_summary.json; r3c_mechanism_budget_cells.tsv
r3c_policy_summary.tsv; r3c_policy_paired_effects.tsv; r3c_policy_uncertainty.json
r3c_pareto_frontier.json; r3c_adaptive_controller_summary.json
scientific_outcome.json; grading_inputs.json; startup_resource_summary.tsv
resource_recovery_summary.json; cleanup_status.txt; first_failure_excerpt.txt
```

`result_transfer_authorized: true` 只表示有界包具备传输资格，不选择渠道。回传前报告精确路径、文件数、总字节、逐文件 SHA-256、敏感性、可用 `email/upload-api/server-local` 方法和推荐方法；未得到开发机对完整 scope 的明确选择，不发送候选文件。

固定报告格式：

```text
P6_3C_R3C_SERVER_REPORT_BEGIN
task_id=
head=
origin_main=
ahead_behind=
audit_only_exit=
experiment_exit=
finalize_exit=
package_exit=
attempt_count=
scientific_contract_changed=
mechanism_lifecycles=
performance_lifecycles=
engine_requests=
http_requests=
retries=
controller_installed_lifecycles=
controller_pressure_capped_steps=
controller_full_budget_steps=
configured_budget_preserved_for_adaptive=
mechanism_gate_complete=
performance_complete=
scientific_outcome=
server_grade=
keep_alive_action=
stopped_card_ids=
restored_card_ids=
keep_alive_restored_exact=
cleanup_status=
candidate_manifest=
next_task_authorized=false
P6_3C_R3C_SERVER_REPORT_END
```

自然语言必须回答：controller 是否在真实 vLLM 子进程安装且只改变 per-iteration budget；三个 target 的首步 effective budget/chunk 和 resident-only full-budget 控制是否成立；adaptive 相对 Off、static B8192 的 TTFT、resident P99 TBT、max stall、TPS、SLO 和 mirror-round 方向；是否有配置进入预注册 bounds。没有候选时，报告有效 trade-off，不通过 grade 改写制造候选。
