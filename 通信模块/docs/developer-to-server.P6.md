# 开发机 → Ascend 服务器：P6.3C-R2-F4-A1 自适应证据接收与零 NPU 再归档

更新日期：2026-08-01

## 1. 本轮真正要完成的事

本轮不重跑八卡实验，也不再围绕 RED/GREEN 标签消耗 NPU。目标是使用服务器已经成功完成的 F4 原始证据，把服务器现场修复正式接入仓库，并用修正后的能力判断重新生成一份可交付的小结果包。

源结果：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
```

新派生结果：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_a1_adaptive_acceptance_2026_0801
```

F4 已经形成的实质性事实如下：

- 6/6 lifecycle 完成，90/90 请求、48/48 batch 成功；
- 42/42 measured pair 原子释放，机制首轮合同 6/6；
- request-ID normalization、co-arrival、mechanism gate 全部为 true；
- Off 三个 cell 都没有 partial prefill；On 的 10K+6K 与 8K+8K 压力 cell 都有 partial prefill；
- 4K+4K 无压力 cell 两侧都没有 partial prefill；
- 0–7 keep-alive 精确恢复，端口、vLLM 残留和共享工作树恢复干净。

因此本项目接收的科学结论是：

> 在 `12288/12288/2`、Prefix Cache off、受控原子共同到达的三组双请求环境中，Chunked Prefill 确实改变了超预算时的 scheduler token 分配；本轮固定样本没有显示短请求 TTFT 或 batch throughput 收益。

这是一项有效的机制结果，不是普遍性能优化结论，也不是 Chunked Prefill 的普遍负面结论。

## 2. 为什么服务器现场修复被正式接受

服务器发现 warmup 只有一个请求，但其实际 ID：

```text
cmpl-p6_3c_r2_f4_<track>_warmup-0-<8hex>
```

会命中 measured pair parser。旧 controller 因而等待不存在的 member 1。服务器加入的两行逻辑是：

```python
if normalized.pair_key.endswith("_warmup"):
    return self._original_add(engine_core, request, request_wave)
```

它只让 singleton warmup 走原始 `EngineCore.add_request`，没有改变 42 个 measured pair 的原子准入，也没有改变 Off/On、请求体、cell 或指标。成功执行使用的 controller SHA-256 为：

```text
a396ba49f94922592854192de139e497232e8952f718cc791d36e372a7a42f4b
```

该实现现已按相同字节进入远端 `main`。服务器当时先修复、验证、再恢复共享工作树的做法是合理的现场自适应，不再视为实验无效条件。

旧 grade 仍作为原始输出保留。错误来自共享 finalizer 只在 task ID 含 `_r2_f3_` 时才期待 atomic admission；F4 明明在环境、overlay manifest 和六个 resolved config 中启用了该能力，却被误判为 runtime gate incomplete，随后又被映射成 mechanism RED。新代码读取实际的：

```text
P6_3C_ATOMIC_PAIR_ADMISSION=1
```

并用完整执行、runtime/transport、co-arrival 和 mechanism 结构化证据直接生成结果。

## 3. 新协作规则

先完整阅读：

```text
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
```

服务器 AI 已获授权在任务范围内实时修复 task-local 代码、overlay、路径、代理、环境、warmup、健康检查、诊断和清理逻辑，并在新的尝试能够增加证据时继续或重试。不要因为历史文档写有 `server_side_code_edit_allowed: false`、`retry_allowed: false` 或某项 SHA 不一致而机械停止。

同时遵守以下边界：

1. 优先在本任务独立 Git worktree、结果目录或 task-local overlay 中修改，避免碰共享 checkout 和其他会话。
2. 每项适配保存原因、命令、diff/patch、修改前后 SHA、attempt 序号、结果和资源恢复。
3. 控制面修复可以沿用任务；若改变 A/B 差异、measured 请求、cell、参数或指标，建立新 variant ID 并写清完整差异。
4. 自动 grade 是辅助字段。若它与请求、机制和恢复证据矛盾，保留原字段，同时给出证据结论。
5. 服务器不直接向远端 `main` 推送；代码补丁交回开发机审核发布。

## 4. 与其他服务器会话隔离

本任务是零 NPU、只读消费既有 raw result 的离线再归档，可以与 NPU 实验并行，但不得改写其他会话的仓库、结果目录或进程。

- 不停止任何卡的 keep-alive。
- 不启动 vLLM，不监听 7000，不发送模型请求。
- 不改写源结果目录。
- 不在共享 checkout 中 `git pull`、`checkout`、`update-index --skip-worktree` 或编辑 tracked 文件。
- 使用独立 worktree。若 Git 正被其他会话持锁，等待锁释放，不删除别人的 lock 文件。

本任务不使用下列 stop 命令；列出它只是为了明确禁止误操作：

```bash
# 本轮不要执行：
# bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
```

keep-alive 必须保持原状。若服务器 AI 发现进入任务前 keep-alive 已由其他会话停止，不要替其他会话恢复；只报告观察到的状态。

## 5. 同步远端 main 并建立独立 worktree

建议执行：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r2_f4_a1_2026_0801

cd "${SHARED_REPO}"
git fetch origin main
git rev-parse origin/main

mkdir -p /data/node0_disk1/liguowei/server_worktrees
git worktree add --detach "${TASK_WORKTREE}" origin/main

cd "${TASK_WORKTREE}"
git status --short --branch
git rev-parse HEAD
```

若 `TASK_WORKTREE` 已存在，不要直接删除。先确认它只属于本任务；可以在其上继续，也可以换一个带时间后缀的新目录。报告实际使用的 worktree、HEAD 和 `origin/main`。

必须看到以下文件：

```text
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f4_a1_adaptive_acceptance.yaml
tools/inference_contracts/review_deepseek_p6_3c_r2_f4_adaptive_run.py
tools/inference_contracts/run_deepseek_p6_3c_r2_f4_a1_server_task.sh
tools/inference_contracts/p6_3c_r2_f4_atomic_pair_admission.py
```

核对已发布 controller 与成功执行源码相同：

```bash
sha256sum tools/inference_contracts/p6_3c_r2_f4_atomic_pair_admission.py
```

预期：

```text
a396ba49f94922592854192de139e497232e8952f718cc791d36e372a7a42f4b
```

## 6. 先做零 NPU 源证据核验

```bash
cd "${TASK_WORKTREE}"
python3 tools/inference_contracts/review_deepseek_p6_3c_r2_f4_adaptive_run.py \
  --source-result-dir \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01 \
  --validate-only
```

它必须核对：源 task ID、成功执行 controller/runner/workload SHA、6/6 lifecycle、90/90 request、48/48 batch、42/42 pair、request ID、co-arrival、mechanism 和资源恢复。

若核验发现路径或字段在真实服务器 raw result 中与脚本假设不同，服务器 AI 可以在独立 worktree 修复 reviewer 后继续；保存 patch 和 attempt 记录。不要修改源 raw result 来迎合脚本。

## 7. 执行 A1 零 NPU 再归档

确认派生目录不存在后执行：

```bash
cd "${TASK_WORKTREE}"
bash tools/inference_contracts/run_deepseek_p6_3c_r2_f4_a1_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01 \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_a1_adaptive_acceptance_2026_0801
```

脚本会：

1. 只读核验源结果；
2. 建立临时派生视图，复用服务器保留的 `lifecycles/` raw evidence；
3. 用当前 finalizer 重新生成顶层小结果；
4. 证明当前仓库 controller 与成功服务器适配源码 SHA 相同；
5. 写 `adaptive_execution_review.json`；
6. 生成不超过 70KB 的候选清单；
7. 不触碰 NPU、vLLM、端口、源结果或共享 checkout。

期望语义结果：

```text
corrected_evidence_outcome=accepted_chunked_prefill_scheduler_mechanism_observed
f4_runtime_and_transport_gates_complete=true
request_id_normalization_gate_complete=true
coarrival_gate_complete=true
mechanism_gate_complete=true
executed_source_matches_published_source=true
```

`candidate_green...` 可以作为修正后的机器标签，但报告必须把重点放在上述结构化事实和描述性性能结论上。

## 8. 现场适配与重试的记录方式

若无需适配，报告 `adaptive_attempts_for_A1=0`。

若需要适配，在派生结果目录旁建立：

```text
server_local/adaptations/attempt_01/
server_local/adaptations/attempt_02/
...
```

每个 attempt 至少保存：

```text
reason.md
command.sh
stdout_stderr.tail.txt
exit_code.txt
change.patch
before_after_sha256.tsv
scientific_impact.json
```

可以继续到证据闭合，不设机械的一次执行上限。以下情况才停止：

- 同一阻塞重复且没有新增信息；
- 会碰撞其他会话或共享资源；
- 需要改变研究问题但尚未建立新 variant；
- 发现源 raw evidence 实际不完整；
- 出现资源或数据安全风险。

## 9. 结果清单与传输

完成后读取：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_a1_adaptive_acceptance_2026_0801/candidate_manifest.server_local.json
```

`result_transfer_authorized: true` 表示该有界包可以候选传输，不代表自动发送。先报告：

- result summary 路径；
- 完整文件名、字节数、SHA-256 和敏感性；
- 总文件数、总字节数、是否 ≤70KB；
- 可选 `email` / `upload-api` / `server-local`；
- 推荐渠道与理由。

等待用户明确选择一个渠道后，再一次性传输完整清单。不要先发状态邮件，不要自动沿用上次渠道，不要在渠道失败后自行切换。

## 10. 必须回报的内容

请按以下结构回报，中文即可：

```text
P6_3C_R2_F4_A1_SERVER_REPORT_BEGIN
task_id=p6_3c_r2_f4_a1_adaptive_acceptance_2026_0801
worktree=<实际独立 worktree>
head=<HEAD>
origin_main=<origin/main>
npu_used=false
keep_alive_action=left_unchanged
source_result_dir=<路径>
source_result_mutated=false
derived_result_dir=<路径>
source_server_grade_preserved=<原始 grade>
corrected_evidence_outcome=<证据结论>
corrected_server_grade=<修正标签>
published_controller_sha256=<SHA>
executed_source_matches_published_source=<true/false>
lifecycles=<x/6>
requests=<x/90>
batches=<x/48>
atomic_pairs=<x/42>
mechanism_first_step_contracts=<x/6>
request_id_normalization_gate=<true/false>
coarrival_gate=<true/false>
mechanism_gate=<true/false>
runtime_and_transport_gate=<true/false>
adaptive_attempts_for_A1=<数量>
adaptive_patch_paths=<无则 none>
scientific_contract_changed=<true/false；若 true 给出新 variant>
candidate_manifest=<路径>
candidate_file_count=<数量>
candidate_total_bytes=<字节>
transfer_method_selected=false
available_methods=email,upload-api,server-local
recommended_method=<方法及理由>
P6_3C_R2_F4_A1_SERVER_REPORT_END
```

最后用一段自然语言说明：Chunked Prefill 在哪种压力下改变了调度、固定性能样本显示了什么、没有证明什么，以及服务器现场自适应为何没有改变 measured A/B 含义。
