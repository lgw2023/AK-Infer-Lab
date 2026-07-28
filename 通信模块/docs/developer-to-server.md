# 开发机 → Ascend 服务器：当前唯一任务

## 当前唯一服务器动作：P6.3C-R1 Chunked Prefill scheduler-pressure matched A/B

```yaml
task_id: p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01
stage: P6.3C-R1
execution_mode: authorized_six_fresh_lifecycle_mechanism_and_balanced_performance_tracks
npu_execution_authorized: true
npu_card_ids: [0, 1, 2, 3, 4, 5, 6, 7]
formal_model_lifecycle_count_exact: 6
engine_request_count_exact: 90
batched_http_call_count_exact: 48
request_retry_count_exact: 0
profiler_authorized: false
runtime_or_dependency_mutation_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
next_task_authorized: false
```

服务器先完整同步远程 `main`，再只运行本文件给出的 run01。不要执行此前的 P8 K2-R0
交接，不要补代码、安装/修改依赖、调整参数或请求体，也不要自行创建 run02。

## 1. 为什么需要这个独立实验

原 P6.3C 的审计结果必须保留：

```text
blocked_p6_3c_not_strict_single_variable
```

它只证明：在原 P6 参考配置
`max_model_len=135168`、`max_num_batched_tokens=4096`、
`max_num_seqs=1` 完全不变时，Chunked Prefill Off 侧无法启动，因此不能直接接在
P6.1 后形成 131K+c1 严格单变量 A/B。

它不等于“Chunked Prefill 无法研究”。但也不能只把单请求的 token budget 提高到
135168 后重跑，因为 Off 可启动要求 `B >= L`，单请求满足 `P <= L`，所以必有
`B >= P`；整段输入能进入一个调度批次，On 侧未必真正发生分块，机制辨识力不足。

本任务另起 P6.3C-R1 结果链，在 Off/On 两侧共同建立新的双请求调度压力环境。原
P6.3C YAML、grade 和审计资产不得删除、覆盖或改名。

## 2. 冻结实验合同

两侧共同固定：

- 模型：`/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp`
- served model：`deepseek-v4-flash-w8a8-mtp`
- vLLM：`0.22.1+empty@0decac0d96c42b49572498019f0a0e3600f50398`
- vLLM-Ascend：`0.22.1rc1@5f6faa0cb8830f667266f3b8121cd1383606f2a1`
- `--quantization ascend`
- TP8 + EP，使用卡 `0,1,2,3,4,5,6,7`
- MTP：`method=mtp`、`num_speculative_tokens=1`
- graph：`FULL_DECODE_ONLY`
- `--max-model-len 69632`
- `--max-num-batched-tokens 69632`
- `--max-num-seqs 2`
- `--block-size 128`
- `--gpu-memory-utilization 0.92`
- async scheduling 开启
- Prefix Cache 两侧都显式 `--no-enable-prefix-caching`
- observer 仅在 mechanism 轨道启用，performance 轨道必须禁用
- profiler 与 HBM sampler 全轨道禁用
- 请求 body 只准备一次，并在所有 mode/lifecycle 中按字节复用

唯一 A/B 差异：

```text
Off: --no-enable-chunked-prefill
On:  --enable-chunked-prefill
```

三组 batched completion 均通过一个 `/v1/completions` HTTP 请求携带两个 prompt token
数组，使 vLLM 在同一次 API 调用中创建两个 engine input：

| cell | 同批两个输入 | 总 Prefill tokens | 研究作用 |
|---|---:|---:|---|
| `no_pressure_32k_32k` | 32K + 32K | 65,536 | 低于预算；验证无分块压力时两侧接近 |
| `asymmetric_pressure_64k_32k` | 64K + 32K | 98,304 | 观察长 Prefill 分块与短请求 TTFT |
| `symmetric_pressure_48k_48k` | 48K + 48K | 98,304 | 观察调度公平性、批吞吐与完成时间差 |

每个 engine request 固定输出 64 token、streaming、temperature=0、ignore_eos、
min_tokens=max_tokens。不得保留生成文本或生成 token ID。

## 3. 两条证据轨道与固定顺序

机制轨道使用只读 scheduler observer；它只能记录，不得改变任何调度决定：

1. `mechanism_01`: Chunked Prefill Off
2. `mechanism_02`: Chunked Prefill On

必须记录每轮 scheduler step、request ID/顺序、prompt/computed/remaining/scheduled
token、`prefill_partial`、waiting/running 队列前后状态。预期机制门：

- Off 三组均不得出现 partial prefill；
- On 的 64K+32K 与 48K+48K 两个压力组必须出现 partial prefill；
- 32K+32K 无压力组两侧均不得出现 partial prefill。

性能轨道必须关闭 observer 与 profiler，使用四个 fresh lifecycle 的顺序平衡设计：

1. `performance_01`: Off，pair_01 first
2. `performance_02`: On，pair_01 second
3. `performance_03`: On，pair_02 first
4. `performance_04`: Off，pair_02 second

测量每个请求的 TTFT、E2EL、TPOT、ITL p50/p95/p99，以及 batch output
throughput 和两个请求的完成时间差。结果只作冻结 cell 内的描述性比较，不声明统计显著性、
普遍性能收益或生产吞吐。

精确总量：

- 6 个 fresh model lifecycle；
- 6 个 warmup engine request；
- 12 个 mechanism measured engine request；
- 72 个 performance measured engine request；
- 共 90 个 engine request；
- 共 48 个 batched HTTP call；
- retry 必须为 0。

任一 lifecycle 失败后立即停止后续 lifecycle，不调参、不改 body、不重试。

## 4. NPU keep-alive 操作规则

本任务使用全部八张卡，所以只能停止卡 `0 1 2 3 4 5 6 7` 上的低优先级
keep-alive。末尾数字是卡号，不得扩大或改变卡集。

server-task driver 会在正式实验前执行：

```bash
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
```

无论成功、失败、中断或提前退出，都必须对完全相同的卡集执行：

```bash
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

最终回报必须写明实际停卡卡号、实际恢复卡号与恢复状态，并确认：

- 16 个 keep-alive 进程标记恢复；
- 卡号覆盖恰好为 `0,1,2,3,4,5,6,7`；
- 端口 7000 无残留监听；
- 无 DeepSeek vLLM 残留进程；
- tracked worktree clean。

如果 stop 或 restore 失败，仍要保存已有证据并明确报告，不能把资源恢复不完整写成实验 green。

## 5. 同步与只读预检

仓库路径：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab
```

若仓库有未提交修改、当前分支不是 `main`、不能 fast-forward，或同步后
`HEAD != origin/main`，立即停止并回报，不要覆盖服务器本地修改。

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git status --short --branch
git fetch origin main
git switch main
git pull --ff-only origin main
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --short --branch
```

同步后先运行不使用 NPU 的合同审计：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
P6_3C_R1_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01
```

审计输出必须确认：

- expected result basename 正确；
- 卡集为 `0,1,2,3,4,5,6,7`；
- lifecycle=6、engine request=90、retry=0；
- mechanism observer=read_only；
- performance observer=disabled；
- profiler 全程 disabled；
- performance 顺序为 Off→On→On→Off；
- 每个 track 内 canonical argv 只差 Chunked Prefill flag。

若审计失败，停止，不运行 NPU，不修改代码。

## 6. 正式执行

结果目录必须预先不存在。正式任务只运行一次：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
bash tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01
```

driver 已包含预检、停卡、六生命周期、首错停止、进程清理、同卡恢复、finalize、bounded
package 和最终标准输出报告。不要绕过 driver 单独运行 mode runner。

禁止事项：

- 不改 `69632 / 69632 / 2`；
- 不改 Prefix Cache、MTP、graph、block size、模型、量化或请求 body；
- 不把单请求 131K 当替代实验；
- 不增加并发组合、重复数、sweep 或 lifecycle；
- 不使用 profiler；
- 不 retry；
- 不运行 P8 K2-R0、P8.3-I1、P9 或其他任务；
- 不在服务器仓库提交或推送代码；
- 不自动邮件、上传或切换传输渠道。

## 7. 结果判定

候选 green：

```text
candidate_green_p6_3c_r1_chunked_prefill_scheduler_pressure_matched_ab
```

它要求：

- 6/6 fresh lifecycle 清洁结束；
- 90/90 engine request 成功；
- 48/48 batched HTTP call 完整；
- Off→On→On→Off 性能顺序准确；
- 请求 body hash 跨 mode/lifecycle 一致；
- 每个 track 内启动参数只有 Chunked Prefill 一个 flag 差异；
- 六个 lifecycle 中 Prefix Cache resolved=false；
- observer 只在 mechanism 轨道存在；
- observer 给出前述 Off/On partial-prefill 机制证据；
- health、queue、MTP 计数和资源恢复完整；
- 无 profiler、无 retry。

candidate green 表示证据链完整，不表示 Chunked Prefill 在所有 workload 上都有收益。
服务器只报告 formal grade；最终是否接受仍由开发机复核决定。

## 8. 服务器本地结果与回报

大文件、原始日志、请求 body、scheduler trace、指标明细和生成内容全部留服务器。候选有界结果：

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

每个外发候选文件以及邮件正文都不得超过 70KB。正式执行结束后，先在当前控制台完整贴回
driver 的 `P6_3C_R1_SERVER_REPORT_BEGIN` 到 `P6_3C_R1_SERVER_REPORT_END`，其中必须包括：

- server HEAD、origin/main、ahead/behind；
- experiment/finalize/package exit code；
- formal grade 和未通过的 gate；
- 三组 mechanism chunk 摘要；
- 三组 performance 绝对值与顺序平衡 pair 摘要；
- 实际停卡/恢复卡集与恢复状态；
- cleanup 状态；
- result summary 正文；
- `candidate_manifest.server_local.json` 全文、bytes 和 SHA-256。

`result_transfer_authorized: true` 表示有界结果包具备转移资格，不代表已经选择渠道。任何结果离开
服务器前，必须先给出精确 summary 路径、完整附件清单、每个文件 bytes、SHA-256、敏感性、
可用方法 `email` / `upload-api` / `server-local`，以及一个推荐方法和理由，然后等待用户对这份
完整范围明确选择一个方法。

推荐 `upload-api`，因为候选文件较多，可作为一个命名的多文件 session 保持清单与哈希关联；
但在用户选择前不得上传。不要先发状态邮件；遇到 401、409、413、代理/重定向、超时、服务或
哈希校验失败时不得自动换渠道，必须重新请求用户选择。

本任务结束即停止，`next_task_authorized: false`。
