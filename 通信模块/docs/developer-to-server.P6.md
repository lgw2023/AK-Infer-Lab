# 开发机 → Ascend 服务器：P6.3C-R3D 持续 Prefill 压力调度实验

更新日期：2026-08-07

任务 ID：`p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01`

任务性质：`NPU / new scientific variant / persistent runtime scheduler policy`

`result_transfer_authorized: true`

本文件是当前 P6 工作流的唯一活跃交接。它替换已完成的 R3C 交接，但不删除、覆盖或重命名 R3C、R3B、R3A、F4 与原始 P6.3C blocked 审计的任何结果目录。

## 1. 你要回答的科学问题

R3C 已证明，在不改变命令行 `max_num_batched_tokens=12288` 与 KV-cache 容量的前提下，真实 EngineCore 可以在 Decode resident 与长 Prefill 冲突时临时收紧当前 scheduler iteration 的 token budget。R3C 将 injected TTFT 相对 Off 降低约 79%–81%，并将 TPS 损失收窄到 1.5%–4.1%，但 resident P99 TBT 仍增加 340%–482%，没有配置进入联合部署边界。

R3C 的机制 trace 还显示，它实际只限制了首个 Prefill chunk。原因是控制器只看 `waiting_prefill_count`：首 chunk 将长请求移入 running 后，waiting 归零，下一轮恢复 full budget。R3C T2048/T4096/T8192 的完整 sequence 分别是 `2048+10233`、`4096+8185`、`8192+4089`。

R3D 不重跑 R3C。它建立新状态机：

```text
configured_budget = max_num_batched_tokens = 12288
D = decode_resident_count × decode_quantum_tokens
active_prefill = waiting_prefill_count + running_unfinished_prefill_count

if decode_resident_count > 0 and active_prefill > 0:
    effective_budget = min(12288, D + active_chunk_target_tokens)
else:
    effective_budget = 12288
```

本轮要回答：

1. 长 Prompt 从 waiting 转入 running 后，persistent policy 是否真的持续限制后续 chunk；
2. 128/256/512/1024 token 四档更细粒度是否能将 resident P99 TBT 从 R3C 的 400–530 ms 拉近 Off 约 91 ms；
3. 尾延迟改善会付出多大 injected TTFT 与 aggregate TPS 代价；
4. 是否有策略同时满足 TTFT 至少下降 20%、resident P99 TBT 增加不超过 10%、TPS 下降不超过 5%。

这三条边界是项目内部决策线，不是外部标准。

## 2. 谱系与不可覆盖的事实

- 原 P6.3C `135168/4096/1`：`blocked_p6_3c_not_strict_single_variable`。
- R2-F4/A1：`accepted_chunked_prefill_scheduler_mechanism_observed`，范围为受控双 Prefill 原子共到达。
- R3A：`mechanism_confirmed_tradeoff_only`，范围为 Decode-resident admission cliff matched A/B。
- R3B-A1：`pareto_frontier_observed_no_candidate_within_bounds`，范围为静态 On budget policy calibration。
- R3C：`p6_3c_r3c_adaptive_budget_2026_0805_run01` / `adaptive_policy_tradeoff_no_candidate_within_bounds`，范围为 waiting-only one-shot admission cap。
- R3D 是 persistent Prefill-pressure policy 新 variant，不是 strict boolean-only A/B，不改写上述任何 outcome。

## 3. 共同冻结的平台、请求和指标

```text
model=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
served_model_name=deepseek-v4-flash-w8a8-mtp
vllm=0.22.1+empty
vllm_ascend=0.22.1rc1
quantization=ascend_w8a8
TP=8; EP=true; MTP speculative tokens=1
graph=FULL_DECODE_ONLY; block_size=128; async_scheduling=true
prefix_cache=false
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=9
profiler=disabled
request_retry_count=0
```

每个 trial 沿用已审计 staged arrival：一个 batched streaming HTTP request 携带 8 个 resident choice，每个 256-token Prompt + 128-token 强制输出；8 个 choice 都流出至少 16 token 后，立即通过第二个 independent streaming request 注入 12281-token Prompt + 4-token 输出。cell 为 `resident_only` 与 `admission_cliff_12281`。不落盘生成文本和 token ID。

指标定义完全沿用 R3B-A1/R3C：

- injected request TTFT；
- resident interference-window P99 TBT；
- resident interference-window maximum adjacent-token stall；
- aggregate output tokens/s；
- resident TBT SLO attainment，其 threshold 为 `2× Off resident-only pooled median TBT`。

## 4. 六个策略与实验解释

| config | Chunked Prefill | CLI budget | scope | target | 作用 |
| --- | --- | ---: | --- | ---: | --- |
| `off_b12288` | Off | 12288 | none | — | contemporaneous legal Off |
| `admission_on_t4096` | On | 12288 | waiting only | 4096 | contemporaneous R3C semantics anchor |
| `persistent_on_t128` | On | 12288 | waiting + running unfinished | 128 | block-size-scale fine chunk |
| `persistent_on_t256` | On | 12288 | waiting + running unfinished | 256 | 2× block size |
| `persistent_on_t512` | On | 12288 | waiting + running unfinished | 512 | mid-fine chunk |
| `persistent_on_t1024` | On | 12288 | waiting + running unfinished | 1024 | coarse persistent chunk |

`admission_on_t4096` 必须与 persistent 策略同轮执行，不能只从 R3C 历史包复制点估计。它的作用是将“状态机变化”与“服务器时期/模型生命周期变化”分开。

## 5. 机制轨道：必须证明完整 chunk sequence

机制 lifecycle 共 5 个：

```text
mechanism_01 admission_on_t4096
mechanism_02 persistent_on_t128
mechanism_03 persistent_on_t256
mechanism_04 persistent_on_t512
mechanism_05 persistent_on_t1024
```

只读 scheduler observer 开启，profiler 关闭。机制门不再只看 first chunk，必须同时成立：

1. 首个 injected step 有且只有 8 个 resident running，`resident_decode_tokens>0`；
2. 首 chunk 等于该 policy target，是 partial Prefill，并与 resident Decode mixed；
3. 每个 pressure step 的 selected budget 等于 `min(12288, decode_count×2+target)`；
4. 每个 pressure step 的 Prefill chunk 精确消耗 selected budget 在实际 resident Decode token 之后的剩余部分，不硬编 `D=16`；
5. persistent policy 在 `waiting_prefill_count=0` 且 `running_unfinished_prefill_count>0` 时仍有 `pressure_capped`；
6. admission-only anchor 在同一状态有 `full_budget`，用于直接复现 R3C 局限；
7. 所有 injected Prefill chunk 之和精确为 12281；
8. 零 preemption，且 adaptive policy 的 configured `max_num_batched_tokens` 始终为 12288。

名义 `D=16` 时：

- admission T4096 预期首 chunk=4096；因为它只看 waiting，后续通常是 full-budget 8185。
- persistent T256 在 resident 持续存在时预期 `256×47+249=12281`。
- persistent T512 预期 `512×23+505=12281`。
- persistent T1024 预期 `1024×11+1017=12281`。
- persistent T128 完成整段 Prompt 需要的 iteration 可能多于 resident 剩余 Decode 寿命。如果 trace 显示 `decode_resident_count=0`，后续恢复 full budget 是正确行为，不得为追求 96 个固定 chunk 而修改 resident 输出长度。

机制门不完整时停在机制轨道，不进入 performance。先根据 trace 判断是 runtime 问题、observer 问题还是策略本身未实现。前两者可 task-local 修复；策略语义变更要建新 variant。

## 6. 性能轨道与样本结构

只有机制门通过才执行 12 个 performance lifecycle。observer 和 profiler 都关闭；controller trace 保留为策略生效证据，不当作性能指标。

```text
round_1:
  off_b12288
  admission_on_t4096
  persistent_on_t128
  persistent_on_t256
  persistent_on_t512
  persistent_on_t1024

round_2:
  persistent_on_t1024
  persistent_on_t512
  persistent_on_t256
  persistent_on_t128
  admission_on_t4096
  off_b12288
```

每个 lifecycle 的 12 个 measured cell sequence 为：

```text
resident_only, cliff, cliff, resident_only,
resident_only, cliff, cliff, resident_only,
resident_only, cliff, cliff, resident_only
```

每个 config-cell 有 12 个 measured trial。每个 On 策略与同 mirror round 的 Off 按 repeat index 配对。bootstrap 为固定 seed 633、10000 次 paired median difference，95% interval。`n=12` 是两个 fresh-model lifecycle 内的 trial pair，不是 12 个独立模型重复，区间只作 descriptive evidence。

预期总数：

```text
17 fresh-model lifecycle
5 mechanism lifecycle
12 performance lifecycle
1286 EngineCore request including warmup
243 local HTTP request including warmup
0 retry in the scientific request driver
```

## 7. 已发布资产与 SHA-256 门

在任何 NPU 操作前，对以下资产做逐字节 SHA-256 核验。任何一项不一致都先停止，不触卡；将实际 SHA、预期 SHA、Git HEAD 和 diff 报回。

```text
benchmarks/deepseek_v4_flash/workloads/p6_3c_r3d_persistent_prefill_pressure.yaml=0da3d7f4bbad14df6c5c90a3d813151286d9efc0aa1778fae49c8b29e6dd961c
tools/inference_contracts/p6_3c_r3d_persistent_scheduler.py=de40ae8329025159759f3ba1c2f11e5dee1f261765c160d3d0d23c0715b63107
tools/inference_contracts/p6_3c_r3d_sitecustomize.py=a2100f168fd3a158ec709e45f4b10bacb60b3171051cc359ebe225c81a4ab370
tools/inference_contracts/run_deepseek_p6_3c_r3d_persistent_prefill.py=5b3e18106a554316680117214d4f995004e04a3b445d6a4e0e27182911d9031f
tools/inference_contracts/run_deepseek_p6_3c_r3c_adaptive_budget.py=60573401b9fa8dcbd9734b3214ed96da3108eafb8f71664a511bf1d2a99bb08b
tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py=fb2432a25aaeffde3d295c6d1849400a24f101058ea4e7a1faba1efeeff918ac
tools/inference_contracts/run_deepseek_p6_3c_r3a_decode_resident.py=215315da2414a52004d84214a9a692eb4689f56a806e7257beee78e2d0bdf10b
tools/inference_contracts/analyze_deepseek_p6_3c_r3a_costs.py=3292defe09d124a4bf9e962292791a6b383e3fe49b91f52c94b05f84ae6d58b8
tools/inference_contracts/run_deepseek_p6_3c_r3d_mode.sh=bea16cd5b59a645966c5c65bb078897f591073e84be5572df3639a2888bb2b87
tools/inference_contracts/run_deepseek_p6_3c_r3d_experiment.sh=3d564f8ebace3e5fa8adb048cb0b62565291fb46a10447b2481213ea76b46ebf
tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh=e8ab0bc8bfbe76b4a26e6d0c49b932dcda3b764ba8b2c48412f1a054ec6fc0c1
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh=9df98c9dfefdfed63364b7041487c8528dfce81f76e103e2fae6be994abbab29
tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh=38f6a4a44feb606ae2a8d4d2d64ab838a09ebc9691a2bda2699a3d92dab2baae
tools/inference_contracts/p6_3c_r3_decode_resident_observer.py=9c2147a7eb1e703da100bcff6cc31481f9c0ba7fe17bdf2375b9383ad71e9a15
tests/inference_contracts/test_deepseek_p6_3c_r3d_persistent_prefill.py=f29d4fcd10a22b5132991852394246968ff6308f0da046d906a627429972f8a2
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md=7dff584b742bfba91df332a8671c7430675d7dfacb9c3a15144dae1b3034fe0e
```

快速核验命令：

```bash
cd "${WORKTREE}"
while IFS='=' read -r path expected; do
  test -f "${path}" || { echo "missing:${path}"; exit 2; }
  actual=$(sha256sum "${path}" | awk '{print $1}')
  test "${actual}" = "${expected}" || {
    echo "sha_mismatch:${path}:expected=${expected}:actual=${actual}"
    exit 2
  }
done <<'EOF'
benchmarks/deepseek_v4_flash/workloads/p6_3c_r3d_persistent_prefill_pressure.yaml=0da3d7f4bbad14df6c5c90a3d813151286d9efc0aa1778fae49c8b29e6dd961c
tools/inference_contracts/p6_3c_r3d_persistent_scheduler.py=de40ae8329025159759f3ba1c2f11e5dee1f261765c160d3d0d23c0715b63107
tools/inference_contracts/p6_3c_r3d_sitecustomize.py=a2100f168fd3a158ec709e45f4b10bacb60b3171051cc359ebe225c81a4ab370
tools/inference_contracts/run_deepseek_p6_3c_r3d_persistent_prefill.py=5b3e18106a554316680117214d4f995004e04a3b445d6a4e0e27182911d9031f
tools/inference_contracts/run_deepseek_p6_3c_r3c_adaptive_budget.py=60573401b9fa8dcbd9734b3214ed96da3108eafb8f71664a511bf1d2a99bb08b
tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py=fb2432a25aaeffde3d295c6d1849400a24f101058ea4e7a1faba1efeeff918ac
tools/inference_contracts/run_deepseek_p6_3c_r3a_decode_resident.py=215315da2414a52004d84214a9a692eb4689f56a806e7257beee78e2d0bdf10b
tools/inference_contracts/analyze_deepseek_p6_3c_r3a_costs.py=3292defe09d124a4bf9e962292791a6b383e3fe49b91f52c94b05f84ae6d58b8
tools/inference_contracts/run_deepseek_p6_3c_r3d_mode.sh=bea16cd5b59a645966c5c65bb078897f591073e84be5572df3639a2888bb2b87
tools/inference_contracts/run_deepseek_p6_3c_r3d_experiment.sh=3d564f8ebace3e5fa8adb048cb0b62565291fb46a10447b2481213ea76b46ebf
tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh=e8ab0bc8bfbe76b4a26e6d0c49b932dcda3b764ba8b2c48412f1a054ec6fc0c1
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh=9df98c9dfefdfed63364b7041487c8528dfce81f76e103e2fae6be994abbab29
tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh=38f6a4a44feb606ae2a8d4d2d64ab838a09ebc9691a2bda2699a3d92dab2baae
tools/inference_contracts/p6_3c_r3_decode_resident_observer.py=9c2147a7eb1e703da100bcff6cc31481f9c0ba7fe17bdf2375b9383ad71e9a15
tests/inference_contracts/test_deepseek_p6_3c_r3d_persistent_prefill.py=f29d4fcd10a22b5132991852394246968ff6308f0da046d906a627429972f8a2
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md=7dff584b742bfba91df332a8671c7430675d7dfacb9c3a15144dae1b3034fe0e
EOF
```

## 8. 与其他服务器会话的隔离

不要在共享 checkout 中修改文件、checkout branch、stash、reset 或清理其他会话的文件。先同步远程，再建立本任务独立 detached worktree：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3d_2026_0807
ATTEMPT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3d_2026_0807_attempt_01
RESULT_DIR=${ATTEMPT_ROOT}/p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01

git -C "${SHARED_REPO}" fetch origin main
git -C "${SHARED_REPO}" status --short --branch
git -C "${SHARED_REPO}" rev-parse origin/main
test ! -e "${WORKTREE}"
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" origin/main
git -C "${WORKTREE}" status --short --branch
git -C "${WORKTREE}" rev-list --left-right --count HEAD...origin/main
test ! -e "${RESULT_DIR}"
```

如果 worktree 或 attempt 目录已存在，不覆盖，不删除。先判断它是本任务的已完成尝试、失败尝试，还是其他会话所有。需要新尝试时，使用新的 `p6_3c_r3d_2026_0807_attempt_02/` 外层目录，其内层 result basename 仍保持精确 task ID，不覆盖 attempt_01。

正式触卡前必须再做全局互斥检查：

- NPU 0–7 全部 Health=OK；
- AICore 为空闲，无其他用户/会话的进程；
- 无其他 P6/P8/vLLM/profiler/server-task lifecycle 在运行；
- port 7000 无监听；
- 不存在本任务之外的 DeepSeek-V4-Flash vLLM 进程。

发现冲突时不停止别人的任务，不抢卡，不启动本任务。报告冲突 PID、用户、卡、端口和可见任务名，等待资源空闲后再继续。

## 9. 零 NPU audit

在 worktree 内先执行：

```bash
cd "${WORKTREE}"
REPO_ROOT="${WORKTREE}" \
P6_3C_SHARED_REPO_ROOT="${SHARED_REPO}" \
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
bash tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh \
  /audit/p6_3c_r3d
```

audit 必须显示：

```text
17 lifecycle
1286 EngineCore request
243 HTTP request
0 retry
all CLI max_num_batched_tokens=12288
off + admission-only T4096 + persistent T128/T256/T512/T1024
complete_prefill_chunk_sequence mechanism gate
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
```

audit 只解析合同，不停 keep-alive，不启 vLLM，不触 NPU。如果 audit 不通过，先在独立 worktree 内修复代码/路径问题，保留前后 diff 与 SHA，不要为了通过 audit 改变科学变量。

## 10. R3C 已知现场兼容点与自适应权限

服务器 AI 有权并有责任处理真实运行环境。不要因历史文件中的“禁止改码/禁止重试”停止有科学价值的任务。遵循 `docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md`：将运行时路径、overlay、import、版本布局、loopback/proxy、warmup、trace、cleanup 与诊断修复限定在本任务 worktree/overlay，并可证据驱动重试。

R3C 成功尝试遇到过两个已知兼容点：

1. 现场 `AscendDSACPImpl` 不一定实现 `update_graph_params`，需要 `hasattr`/兼容 guard；
2. vLLM cache-manager alias/mapping 可能仍指向过时 key，需要对齐实际 Ascend subclass key。

请先在服务器保留的 R3C 成功 worktree/result/attempt history 中寻找确切 patch，审查后将同等修复应用到当前 R3D task-local overlay 生成路径，不要直接修改 conda/site-packages 或共享 checkout。如果无法找到旧 patch，可根据当前源码实现最小等价修复。

每个 adaptation 必须保留：

```text
attempt_id
failure_before
changed_paths
before_sha256
after_sha256
unified_diff
why_needed_on_this_server
scientific_impact=none | changed
validation_after
cleanup_and_resource_recovery
```

可在原 task ID 内修复：运行时路径、editable/site-packages layout、overlay copy/patch、Python import、sitecustomize 时序、上述两项 R3C 兼容问题、loopback `NO_PROXY/no_proxy`、health check、warmup 特例、trace 写入、分析器字段聚合和 cleanup。

必须建立新 variant：修改 target grid、pressure scope 语义、decode quantum、CLI budget、`max_model_len`、`max_num_seqs`、请求长度/数量/到达 gate、cell、trial 数、指标、SLO threshold、配对方式、Pareto 目标或声明边界。如果这样的变更能产生更好的新实验，允许继续，但必须使用新 task ID 和独立 result 目录，不得表述为原 R3D 不变。

服务器不得 push 远程 `main`。请返回 patch 与证据，由开发机审查和发布。

## 11. NPU keep-alive 与正式入口

本任务使用 0–7 号卡。只有 Git/SHA/audit/runtime preflight/全局互斥全部通过后，才允许开始 NPU 阶段。基础 server-task 将执行下列 stop/restore；你必须确认它没有停别的卡。

```bash
# 停止本任务使用的低优先级 keep-alive。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 无论成功、失败、中断、早停或 Ctrl-C，都恢复完全相同的卡集合。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

正式入口：

```bash
cd "${WORKTREE}"
mkdir -p "${ATTEMPT_ROOT}"
REPO_ROOT="${WORKTREE}" \
P6_3C_SHARED_REPO_ROOT="${SHARED_REPO}" \
bash tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh \
  "${RESULT_DIR}"
```

基础 runner 已用 `trap` 处理 success/failure/INT/TERM 的恢复。但任务结束后还必须独立核对：

```text
stopped_card_ids=0,1,2,3,4,5,6,7
restored_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_count=16
keep_alive_restored_exact=true
port_7000_listener_count=0
vllm_residual_process_count=0
tracked_worktree_clean=true
```

任务内所有 loopback HTTP 必须直连 `127.0.0.1:7000`，使用 `curl --noproxy '*' --proxy ''`，并将 `127.0.0.1,localhost,::1` 同时写入 `NO_PROXY` 与 `no_proxy`。不得让华为代理介入健康检查或请求。

## 12. 结果判读

不要用红/绿标签代替科学解释。优先报告 absolute metrics、relative effect、mirror-round 一致性和完整 chunk sequence。

对每个 persistent target，必须给出：

- chunk count 和完整 chunk size sequence；
- 首 chunk 与 waiting→running 后的第二/后续 chunk；
- pressure-capped step 数、running-unfinished pressure step 数、resident 结束后 full-budget step 数；
- Prefill token sum，应为 12281；
- preemption count；
- TTFT、P99 TBT、max stall、TPS、SLO attainment 的 absolute median；
- 相对 contemporaneous Off 的 median effect 和 95% descriptive paired-bootstrap interval；
- 相对 contemporaneous admission-only T4096 anchor 的相对变化；
- 两个 mirror round 的方向与量级。

如果有配置进入三条联合边界，outcome 为 `persistent_prefill_policy_candidate_found_within_bounds`，但仍不自动进入部署。如果无配置进入，但机制和性能证据完整，outcome 为 `persistent_prefill_tradeoff_no_candidate_within_bounds`；这是有效科学结果，不要为追求绿色而改阈值。

## 13. 服务器保留与小包交付

raw scheduler trace、token timestamps、request bodies、server log、完整结果树和大 manifest 留在服务器。不要传输全量 manifest；不要重复 R3C 将 1.2 MB gzip manifest 作为小包发出的问题。本项目每封邮件 body 和每个 attachment 均不得超过 70KB；候选包整体也必须由 finalizer 确认不超过 71680 bytes。

候选文件为：

```text
result_summary.md
environment_and_hashes.json
payload_identity_summary.json
lifecycle_summary.tsv
r3d_mechanism_sequence_summary.json
r3d_mechanism_sequence_cells.tsv
r3d_policy_summary.tsv
r3d_policy_paired_effects.tsv
r3d_policy_uncertainty.json
r3d_pareto_frontier.json
r3d_controller_summary.json
scientific_outcome.json
grading_inputs.json
startup_resource_summary.tsv
resource_recovery_summary.json
cleanup_status.txt
first_failure_excerpt.txt
```

如果发生 adaptation，还要在服务器保留完整 `adaptive_execution_review.json`/同等证据。若该文件加入候选包会超过 70KB，不截断原文；改为在 `result_summary.md` 中列出其服务器路径、bytes、SHA-256 与一段不超过 2KB 的摄要，原文留服务器。

`result_transfer_authorized: true` 表示有界包具备被选择传输的资格，不代表已选择渠道。在任何文件离开服务器前，先报告：

```text
result_summary_path
candidate_manifest_path
candidate_file_count
candidate_total_bytes
each path / bytes / sha256 / sensitivity
available_methods=email,upload-api,server-local
recommended_method and reason
transfer_method_selected=false
```

然后等待用户对这一完整 scope 明确选择 `email` / `upload-api` / `server-local` 之一。不先发 status-only 邮件，不自动上传，不沿用上一任务的渠道授权。如果后续选择 upload-api，必须一次提交整个已批准小包并核验 local/remote SHA；401/409/413/proxy/redirect/timeout/service/hash 失败后不自动换渠道，要求新选择。

## 14. 固定回报格式

```text
P6_3C_R3D_SERVER_REPORT_BEGIN
task_id=
worktree=
head=
origin_main=
ahead_behind=
shared_checkout_modified=
audit_only_exit=
formal_experiment_started=
attempt_count=
adaptive_patch_paths=
scientific_contract_changed=
experiment_exit=
finalize_exit=
package_exit=
mechanism_lifecycles=
performance_lifecycles=
engine_requests=
http_requests=
retries=
controller_installed_lifecycles=
configured_budget_preserved_for_all_on=
full_prefill_sequence_gate_complete=
persistent_running_prefill_pressure_observed=
admission_only_reversion_observed=
preemption_count=
performance_complete=
pareto_config_ids=
deployment_bound_config_ids=
scientific_outcome=
server_grade=
stopped_card_ids=
restored_card_ids=
keep_alive_marker_count=
keep_alive_restored_exact=
port_7000_listener_count=
vllm_residual_process_count=
tracked_worktree_clean=
cleanup_status=
candidate_manifest=
candidate_file_count=
candidate_total_bytes=
transfer_method_selected=false
available_methods=email,upload-api,server-local
recommended_method=
next_task_authorized=false
P6_3C_R3D_SERVER_REPORT_END
```

随后用自然语言回答：

1. admission-only T4096 是否复现 waiting→running 后回到 full budget；
2. 四档 persistent target 的完整 chunk sequence 与状态转换是什么；
3. 每档相对 Off 与 admission-only anchor 的 TTFT、P99 TBT、max stall、TPS、SLO 改变；
4. mirror round 是否同向，哪些指标对 lifecycle order 敏感；
5. 是否有配置进入联合边界，最接近每条边界的配置和差距是什么；
6. 服务器做了哪些 adaptation，为什么不改变/改变了科学合同。

本任务完成后不自动进入 R3E/P7/P8/P9，不执行下一任务。
