# 开发机 → Ascend 服务器：P6 专用执行交接

## P6.3C-R1 Chunked Prefill scheduler-pressure matched A/B

这是一份独立、稳定的 P6 专用交接。它不会随通用
`通信模块/docs/developer-to-server.md` 的其他阶段任务切换而被覆盖。

只有当用户或服务器任务提示词**明确点名本文件**时，本交接才激活。激活后，只执行
本文件定义的 P6.3C-R1 run01；不要同时执行通用交接中的 K2、K3、P8.3、P9 或其他
任务。如果已有服务器任务或 NPU 作业正在运行，不要中断或并跑，先回报冲突并等待。

```yaml
handoff_file: 通信模块/docs/developer-to-server.P6.md
dispatch_revision: p6_3c_r1_sha_gate_reissue_2026_0729_r1
task_id: p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01
stage: P6.3C-R1
status: redispatched_after_pre_npu_sha_gate_stop_awaiting_server_run01
activation_rule: explicit_instruction_naming_this_file
execution_mode: authorized_six_fresh_lifecycle_mechanism_and_balanced_performance_tracks
server_execution_authorized: true
npu_execution_authorized: true
npu_card_ids: [0, 1, 2, 3, 4, 5, 6, 7]
formal_model_lifecycle_count_exact: 6
engine_request_count_exact: 90
batched_http_call_count_exact: 48
request_retry_count_exact: 0
profiler_authorized: false
runtime_or_dependency_mutation_authorized: false
server_side_code_edit_authorized: false
concurrent_task_authorized: false
server_task_queue_exclusive: true
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
next_task_authorized: false
```

## 0. 本次重派发说明

上一轮服务器尝试在九项仓库 SHA 门的第 9 项停止，未运行 audit-only、正式 driver 或
NPU 实验。服务器回报的实际文件 SHA 为：

```text
75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
```

这个值是正确值。开发机随后对工作树、提交
`b064e0b0aeabd0859e63b3766cc61648a8ef1d6d` 的 Git blob 和实时远程 `main` 三处
交叉核对，三者的本交接第 9 项实际都已经是 `...f261a3...`，无法从该提交复现服务器
看到的 `...f262a3...`。因此本次不修改正确的 patch 文件，也不允许服务器临场改 hash；
安全处置是发布一个新的交接修订，并废止此前聊天中粘贴、缓存或另存的 P6 执行文本。

本次仍使用 `run01`，因为上一轮没有创建正式结果目录、没有通过 audit-only、没有进入
driver，也没有触发 NPU。服务器必须只以重新同步后的 Git tracked 文件
`通信模块/docs/developer-to-server.P6.md` 为执行真值，不能从旧消息复制命令或 SHA。

本任务是服务器全局串行任务，不是与通用 handoff 并行的第二任务。只有在任务协调通道
明确确认其他服务器任务已经完成、停止或尚未开始，且没有其他 NPU/vLLM 作业时，才能
进入本交接。若通用 `developer-to-server.md` 所指任务或任何其他会话已在执行，本 P6
任务保持排队，不能抢占、停止或并跑。P6 driver 一旦开始，到 0–7 keep-alive 完整恢复
并贴回报告前，也不得启动任何其他服务器任务。

## 1. 任务目标与结论边界

原 P6.3C 审计必须原样保留：

```text
blocked_p6_3c_not_strict_single_variable
```

它只证明：原 P6.1 参考配置
`max_model_len=135168`、`max_num_batched_tokens=4096`、
`max_num_seqs=1` 完全不变时，Chunked Prefill Off 侧无法启动，因此不能直接形成
131K+c1 严格单变量 A/B。

这不是“Chunked Prefill 无法实验”。但也不能只把单请求 token budget 提高到
135168 后重跑：Off 可启动要求 `B >= L`，单请求满足 `P <= L`，因此必有
`B >= P`；完整输入可能一次进入调度批次，On 侧即使启用也未必发生真实分块。

本任务另起 P6.3C-R1 结果链，在 Off/On 两侧共同冻结新的双请求调度压力环境，用两条
证据轨道回答：

1. 当同批 Prefill token 总量超过预算时，Chunked Prefill 是否实际改变调度过程；
2. 它是否降低短请求被长 Prefill 阻塞的程度；
3. 这种调度变化对批吞吐、各请求时延和完成时间差有什么描述性影响。

原 P6.3C YAML、grade 和审计资产不得删除、覆盖、改名或重新判级。P6.3C-R1 未得到
服务器结果并经开发机复核前，不得写成 Chunked Prefill 已完成的正向成果。

## 2. 冻结实验合同

Off/On 两侧共同固定：

- 模型：
  `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp`
- served model：
  `deepseek-v4-flash-w8a8-mtp`
- Conda：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1`
- vLLM：
  `0.22.1+empty@0decac0d96c42b49572498019f0a0e3600f50398`
- vLLM-Ascend：
  `0.22.1rc1@5f6faa0cb8830f667266f3b8121cd1383606f2a1`
- `--quantization ascend`
- TP8 + EP，卡集严格为 `0,1,2,3,4,5,6,7`
- MTP：`method=mtp`、`num_speculative_tokens=1`
- graph：`FULL_DECODE_ONLY`
- `--max-model-len 69632`
- `--max-num-batched-tokens 69632`
- `--max-num-seqs 2`
- `--block-size 128`
- `--gpu-memory-utilization 0.92`
- async scheduling 开启
- Prefix Cache 两侧显式 `--no-enable-prefix-caching`
- observer 只在 mechanism 轨道启用
- observer 和 profiler 在 performance 轨道都必须关闭
- profiler 与 HBM sampler 全轨道禁用
- 请求 body 只生成一次，并在所有 mode/lifecycle 中按字节复用

唯一 A/B 差异：

```text
Off: --no-enable-chunked-prefill
On:  --enable-chunked-prefill
```

每个测量单元都用**一个** `/v1/completions` HTTP 请求携带两个 prompt token 数组，
让两个 engine input 在同一次 API 调用中创建：

| cell | 同批两个输入 | 总 Prefill tokens | 作用 |
|---|---:|---:|---|
| `no_pressure_32k_32k` | 32K + 32K | 65,536 | 低于预算，验证无分块压力时两侧接近 |
| `asymmetric_pressure_64k_32k` | 64K + 32K | 98,304 | 观察长 Prefill 分块和短请求 TTFT |
| `symmetric_pressure_48k_48k` | 48K + 48K | 98,304 | 观察调度公平性、批吞吐和完成差 |

每个 engine request 固定输出 64 token，streaming、temperature=0、ignore_eos，
`min_tokens=max_tokens`。不得保留生成文本或生成 token ID。

## 3. 两条证据轨道与固定顺序

### 3.1 机制轨道

机制轨道使用只读 scheduler observer。observer 只能包装 `Scheduler.schedule`，读取原
`SchedulerOutput` 并记录，不能修改调度输出、请求状态、队列或 token 数。

固定 lifecycle：

1. `mechanism_01`：Chunked Prefill Off
2. `mechanism_02`：Chunked Prefill On

记录字段至少包括：

- scheduler step index；
- request ID 与请求次序；
- prompt/computed/remaining/scheduled token；
- `prefill_partial`；
- waiting/running 队列前后状态。

机制门：

- Off 三组都不得出现 partial prefill；
- On 的 64K+32K 与 48K+48K 两个压力组必须出现 partial prefill；
- 32K+32K 无压力组两侧都不得出现 partial prefill。

### 3.2 性能轨道

性能轨道必须关闭 observer、profiler 和 HBM sampler，使用四个 fresh lifecycle：

1. `performance_01`：Off，pair_01 first
2. `performance_02`：On，pair_01 second
3. `performance_03`：On，pair_02 first
4. `performance_04`：Off，pair_02 second

固定顺序为：

```text
Off → On → On → Off
```

测量每个请求的 TTFT、E2EL、TPOT、ITL p50/p95/p99，以及 batch output throughput
和两个请求的完成时间差。结果只能解释为冻结 cell 内、顺序平衡后的描述性比较；不声明
统计显著性、普遍性能收益或生产吞吐。

精确执行总量：

- fresh model lifecycle：6；
- warmup engine request：6；
- mechanism measured engine request：12；
- performance measured engine request：72；
- total engine request：90；
- batched HTTP call：48；
- retry：0。

任一 lifecycle 失败后立即停止后续 lifecycle，不调参、不改 body、不重试。

## 4. 固定代码、合同与服务器前提

仓库路径：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab
```

P6.3C-R1 首次发布提交：

```text
faacb936de6079278d0097e78f4d7288908b0e2e
```

服务器必须同步最新远程 `main`，并确认上述提交仍是当前 HEAD 的祖先。不要退回旧提交，
也不要把服务器仓库 reset 到该提交。

同步后先确认本次重派发文件来自当前 Git HEAD，而不是旧聊天文本、缓存或手工副本：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

P6_HANDOFF='通信模块/docs/developer-to-server.P6.md'
CORRECT_SHA_LINE='75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch'
STALE_SHA='75156e56ce06554cfca79aef92167ec78521a28902f90389f8f26''2a3d509ebc1'

git diff --exit-code HEAD -- "${P6_HANDOFF}"
test "$(git show "HEAD:${P6_HANDOFF}" | grep -Fxc "${CORRECT_SHA_LINE}")" = 1
test "$(grep -Fxc "${CORRECT_SHA_LINE}" "${P6_HANDOFF}")" = 1
! grep -Fq "${STALE_SHA}" "${P6_HANDOFF}"
grep -F 'dispatch_revision: p6_3c_r1_sha_gate_reissue_2026_0729_r1' \
  "${P6_HANDOFF}"
```

任一检查失败都按
`blocked_p6_3c_r1_source_or_resource_gate(handoff_revision_or_sha_text_mismatch)`
停止，不运行 audit-only，不触 NPU。不要手工修复服务器文件；回报 HEAD、本文件
`git hash-object`、正确行计数、陈旧 SHA 行计数和 tracked 状态。

以上通过后，再核对以下仓库输入：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

git merge-base --is-ancestor \
  faacb936de6079278d0097e78f4d7288908b0e2e HEAD

sha256sum -c <<'EOF'
79929e198f5062114c51813ed2233676e9f15a8b1bf37de25e37e371da94340c  tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh
34cff873bb01e240cb923d3692acd38bd2b1d4c82f16257092841e542c54f113  tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.sh
84dd361f92bb61d07336da8f2c1fbc320449cc4f80a6286dbe5b07935b0044d9  tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh
b60c859c44d0a0c89eb0ac04cb6e11bdf843c845a759c8bce65c558cf6911414  tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py
c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4  tools/inference_contracts/p6_3c_r1_scheduler_observer.py
c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d  tools/inference_contracts/canonicalize_server_argv.py
2e8af028e794cba487d9d140c18b4341df7edf09fa23847013e982c172fc68e5  benchmarks/deepseek_v4_flash/workloads/p6_3c_r1_chunked_prefill_scheduler_pressure_matched_ab.yaml
2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch
75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
EOF
```

九项必须全部 `OK`。任何一项不一致都停止，不在服务器补代码或改 hash。

正式 driver 还会校验服务器已有 prompt source：

```text
path=/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
bytes=19487
sha256=48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
```

它还会校验安装态/冻结 source：

```text
vllm_ascend/spec_decode/llm_base_proposer.py
sha256=0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

vllm_ascend/distributed/kv_transfer/__init__.py
sha256=dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1

/data/node0_disk1/vllm-0.22.1/vllm/v1/core/sched/scheduler.py
sha256=41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983
```

如果 prompt source、环境、模型、冻结 source 或工具缺失，只回报精确路径和失败检查；
不要复制旧结果伪造输入、安装依赖、切版本、改 runtime 或创建新环境。

## 5. NPU keep-alive 与资源互斥

本任务使用全部八张卡。开始前必须确认没有其他服务器任务占用端口 7000、DeepSeek
vLLM 或卡 `0–7`，并在任务协调通道确认没有其他会话处于“即将执行/已授权执行但尚未
收口”的重叠窗口。不得只凭端口 7000 空闲推断全局无任务。不得杀死不属于本任务的
进程；发现冲突就停止并回报。

在 audit-only 前和正式 driver 前各检查一次：

```bash
if pgrep -af \
  '[r]un_deepseek_.*server_task|[r]un_.*server_task|[v]llm.*serve' \
  > /tmp/p6_3c_r1_conflicting_tasks.txt; then
  cat /tmp/p6_3c_r1_conflicting_tasks.txt
  exit 2
fi
```

该进程检查只是机器侧辅助门；任务协调通道中的显式无冲突确认仍是必要条件。发现其他
会话的任务处于运行、清理或结果收口阶段时，不执行 P6，也不调用 `npu_stop.sh`。

正式 server-task driver 会在实验前只对卡 `0 1 2 3 4 5 6 7` 执行：

```bash
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
```

无论成功、失败、中断或提前退出，都必须对完全相同卡集执行：

```bash
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

不要在 driver 外手工提前 stop。driver 的 EXIT/INT/TERM finalizer 负责清理实验进程、
同卡恢复、结果终结和有界打包。

最终必须确认：

- 实际停卡卡集恰好为 `0,1,2,3,4,5,6,7`；
- 实际恢复卡集恰好相同；
- 16 个 keep-alive 进程标记恢复；
- keep-alive 卡号覆盖恰好为 `0–7`；
- 端口 7000 无残留监听；
- 无 DeepSeek-V4-Flash vLLM 残留进程；
- tracked worktree clean。

stop/restore 任一步失败时，仍要保存已有证据并回报。资源恢复不完整不能写成实验 green。

## 6. 同步远程 main

不要覆盖服务器本地 tracked 修改，不要 stash、reset、checkout 文件、rebase 或 force。

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

git status --short --branch
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain --untracked-files=no)"
git fetch origin main
git merge --ff-only origin/main

git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --porcelain --untracked-files=no
```

硬门：

```text
branch=main
HEAD=origin/main
ahead/behind=0 0
tracked-clean=true
```

`server_local/` 和 `server_results/` 的未跟踪资产允许保留。若存在 tracked 修改、分支
不是 main、不能 fast-forward 或同步后不一致，停止并回报精确状态；不要修复工作区。

拉取完成后重新打开本文件，后续不要执行通用 `developer-to-server.md` 中的其他任务。
记录同步后的 HEAD。若 audit-only 结束后远程 `main` 又推进，正式 driver 前必须停止，
重新 fast-forward、重新打开本文件并从第 4 节开始重做全部门；不能拿旧 audit 结果搭配
新 HEAD。

## 7. 零 NPU audit-only

结果路径固定为：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01
```

先确认正式结果目录不存在。存在时不要删除、改名、覆盖或自动创建 run02；只回报目录。

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

test ! -e \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01

P6_3C_R1_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01
```

audit-only 不使用 NPU，也不应停止 keep-alive。输出必须确认：

- result basename 与 task ID 正确；
- 卡集 `0,1,2,3,4,5,6,7`；
- lifecycle=6；
- engine request=90；
- batched HTTP call=48；
- retry=0；
- mechanism observer=read_only；
- performance observer=disabled；
- profiler 全轨道 disabled；
- performance 顺序为 Off→On→On→Off；
- 三个 Off lifecycle 的 canonical argv hash 均为
  `1176d6e37dd0be874eb0b3647a5317e171c26730e26f95a29cfbe5487675dc93`；
- 三个 On lifecycle 的 canonical argv hash 均为
  `114aae24f15f6338ab0446e83c1911fe27808c3050b1e7906535275c2e621f44`。

若 audit-only 失败，停止，不触 NPU，不修改代码或环境。

## 8. 唯一正式执行

audit-only、仓库输入、环境和资源互斥全部通过后，只执行下面一个命令一次：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

# 防止 audit-only 之后其他会话又推进远程 main。
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"

bash tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01
```

driver 已包含：

1. 仓库、结果目录、环境、模型输入、端口和残留进程预检；
2. 八卡 keep-alive stop；
3. 14 份 canonical batched request body 的一次性生成和 hash；
4. 两个 mechanism lifecycle；
5. 四个 performance lifecycle；
6. 任一 lifecycle 首错停止；
7. 进程组清理；
8. 0–7 同卡 keep-alive 恢复；
9. 90-request/48-batch/argv/resolved config/observer/health/queue/MTP 校验；
10. formal grade、结果摘要和小包 manifest 生成；
11. `P6_3C_R1_SERVER_REPORT_BEGIN/END` 控制台回报。

不要绕过 server-task driver 单独运行 mode runner 或 Python runner。

禁止事项：

- 不改 `69632 / 69632 / 2`；
- 不改 Prefix Cache、MTP、graph、block size、模型、量化或请求 body；
- 不把单请求 131K 当替代实验；
- 不新增请求组合、重复数、sweep 或 lifecycle；
- 不使用 profiler；
- 不 retry；
- 不删除或覆盖已有结果目录；
- 不在服务器仓库编辑、提交或推送代码；
- 不执行 K2、K3、P8.3、P9 或通用 handoff 的任务；
- 不自动发送邮件、上传文件或切换传输渠道；
- 不创建 run02 或后续任务。

## 9. 结果判定与解释

候选 green：

```text
candidate_green_p6_3c_r1_chunked_prefill_scheduler_pressure_matched_ab
```

要求同时满足：

- 6/6 fresh lifecycle 清洁结束；
- 90/90 engine request 成功；
- 48/48 batched HTTP call 完整；
- Off→On→On→Off 顺序准确；
- canonical request body hash 跨 mode/lifecycle 一致；
- 每个 track 内启动参数只有 Chunked Prefill 一个布尔差异；
- 六个 lifecycle 中 Prefix Cache resolved=false；
- observer 只在 mechanism 轨道存在；
- Off 三组无 partial prefill；
- On 两个压力组存在 partial prefill；
- On/Off 无压力组均无 partial prefill；
- health、queue、MTP 计数完整；
- 无 profiler、无 retry；
- cleanup 和 keep-alive 同卡恢复完整。

其他 formal grade 也必须如实保留：

```text
blocked_p6_3c_r1_source_or_resource_gate
red_p6_3c_r1_scheduler_pressure_no_success
yellow_p6_3c_r1_scheduler_pressure_partial
red_p6_3c_r1_scheduler_pressure_evidence_incomplete
```

candidate green 只表示这条冻结结果链证据完整，不表示 Chunked Prefill 在所有 workload
上都有收益。服务器只报告 formal grade 和原始摘要；最终接受、页面更新与研究结论由开发机
复核后决定。

## 10. 结果留存、回报与传输

原始日志、请求 body、scheduler trace、逐请求指标、生成内容和大文件全部留在服务器结果
目录，不通过邮件或附件返回。

候选有界文件：

```text
result_summary.md
environment_and_hashes.json
request_body_manifest.json
lifecycle_summary.tsv
mechanism_scheduler_summary.json
mechanism_request_chunk_summary.tsv
performance_mode_cell_summary.tsv
performance_order_balanced_pairs.tsv
grading_inputs.json
resource_recovery_summary.json
cleanup_status.txt
first_failure_excerpt.txt
```

每个候选文件、完整候选包和邮件正文都必须满足 70KB 边界。正式执行结束后，先在当前
控制台原样贴回 driver 的：

```text
P6_3C_R1_SERVER_REPORT_BEGIN
...
P6_3C_R1_SERVER_REPORT_END
```

回报必须至少包含：

1. server HEAD、origin/main、ahead/behind、tracked-clean；
2. P6 首次发布提交是 HEAD 祖先；
3. 九项仓库 SHA 校验结果；
4. audit-only 关键输出；
5. experiment/finalize/package exit code；
6. formal grade 与未通过 gate；
7. lifecycle、engine request、batched HTTP call、retry 实际总量；
8. 三组 mechanism chunk 摘要；
9. 三组 performance 绝对值与顺序平衡 pair 摘要；
10. 实际停卡/恢复卡集与 `keep_alive_restored_exact`；
11. keep-alive marker、7000 listener、vLLM residual、cleanup 状态；
12. result summary 正文；
13. `candidate_manifest.server_local.json` 全文、bytes 和 SHA-256；
14. 完整结果目录路径；
15. 是否发生任何代码、环境、参数、请求体或 retry 偏离。

`result_transfer_authorized: true` 只表示有界包具备转移资格，不表示已经选择渠道。任何结果
离开服务器前，必须先报告：

- result summary 精确路径；
- 完整候选附件清单；
- 每个文件 bytes；
- 每个文件 SHA-256；
- 每个文件敏感性；
- 可用方法：`email` / `upload-api` / `server-local`；
- 一个推荐方法及理由。

然后等待用户对这份完整范围明确选择一个方法。推荐 `upload-api`，因为候选文件较多，可用
一个命名的 multi-file session 保持清单和 hash 关联；但在用户选择前不得上传。

不要先发状态邮件。遇到 401、409、413、代理/重定向、超时、服务或 hash 校验失败时，
不得自动换渠道，必须重新请求用户选择。

本任务结束即停止：

```yaml
next_task_authorized: false
```

## 11. 服务器助手的最短执行摘要

1. 确认没有其他服务器/NPU 任务在运行；
2. fast-forward 同步最新远程 `main`；
3. 只打开本次 Git tracked 文件，验证 dispatch revision、正确 SHA 行和无陈旧 SHA；
4. 不执行通用 handoff，验证 P6 发布提交祖先关系和九项 SHA；
5. 确认固定 result dir 不存在；
6. 再次确认任务队列与机器进程都无冲突，运行一次 audit-only；
7. audit 后确认远程 HEAD 未推进、仍无其他任务，再运行一次唯一 server-task driver；
8. 无论任何退出路径都确认 0–7 keep-alive 同卡恢复；
9. 原样回报完整 server report 和 bounded manifest；
10. 大文件留服务器，等待用户选择唯一传输渠道，不进入下一任务。
