# 开发机 → Ascend 服务器：P6.3C-R3A Decode-resident admission-cliff matched A/B

更新日期：2026-08-03

任务 ID：`p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01`

状态：已授权服务器在确认全局无冲突后执行 R3-S0；只有 S0 机制门通过，正式 R3A 性能轨道才自动继续。

## 1. 本轮真正要回答的问题

F4 已经证明：两个 Prefill 在同一个 scheduler step 前共同可见、总 Prefill 超过 token budget
时，Chunked Prefill On 会发生 partial prefill，Off 不会。但 F4 没有稳定在途 Decode，因此
不能回答 Chunked Prefill 的实际收益。

R3A 改为制造下面这类竞争：

1. 八个请求已经完成 Prefill 并持续 Decode；
2. 客户端确认每个 resident 都已输出至少 16 token；
3. 此时注入一个接近长度上限的长 Prefill；
4. 比较 Off 是否因无法整段装入剩余 budget 而等待，On 是否用剩余 budget 立即 partial admit；
5. 同时量化长请求 TTFT 收益与 resident Decode 尾 TBT/吞吐代价。

对 vLLM 0.22 V1 scheduler 的源码复核表明，两侧都先调度 RUNNING request。设 batch budget
为 `B`、resident Decode 本轮已占用 token 为 `D`、新 Prefill 长度为 `P`，则剩余预算是：

```text
R = B - D
```

Off 只有 `P <= R` 才能准入整个 Prefill；On 可以调度 `min(P, R)`。因此本任务检验的是
“长 Prefill 准入饥饿是否被消除”，不是预设“On 一定保护 Decode”。resident TBT 可能改善，
也可能变差，必须作为独立代价报告。

## 2. 结论 lineage 与禁止覆盖的历史

以下记录必须保留，不能被本任务覆盖：

- 原 `135168/4096/1` 参考配置：`blocked_p6_3c_not_strict_single_variable`；
- F4 受控原子共到达机制结论：`accepted_chunked_prefill_scheduler_mechanism_observed`；
- F4 固定样本未显示短请求 TTFT 或 batch throughput 收益；
- R1–F3 的启动、路径、代理、共到达和 request-ID 失败均保留为 provenance。

R3A 是独立的新研究链。完成后只能声明受控 decode-resident staged arrival 下的机制、TTFT、
resident TBT 与 aggregate throughput；不能声明自然 API 流量、生产 SLO 或普遍收益。

## 3. 已由开发机完成的实现

服务器必须包含以下代码提交：

```text
6175ac9f13b9e881bbf09d57c90f3299ae88abb8
feat(p6): add decode-resident chunked-prefill experiment
```

该提交包括：

```text
benchmarks/deepseek_v4_flash/workloads/p6_3c_r3a_decode_resident_admission_cliff_matched_ab.yaml
tools/inference_contracts/p6_3c_r3_decode_resident_observer.py
tools/inference_contracts/run_deepseek_p6_3c_r3a_decode_resident.py
tools/inference_contracts/run_deepseek_p6_3c_r3a_mode.sh
tools/inference_contracts/run_deepseek_p6_3c_r3a_experiment.sh
tools/inference_contracts/run_deepseek_p6_3c_r3a_server_task.sh
```

核心资产 SHA-256：

```text
4a27659a1aeceb922daee08f28cfec22bd94e5bdb1f14aeda2e55845bbdba509  benchmarks/deepseek_v4_flash/workloads/p6_3c_r3a_decode_resident_admission_cliff_matched_ab.yaml
3cc372c28681b786ceb65b62830375f584386d51486ec4425147b12f5bab6e0e  tools/inference_contracts/p6_3c_r3_decode_resident_observer.py
2bbc6e6e60575af8c1502198571ac2081a9dbb1ff77aaa9ffed5df1ed04b06ba  tools/inference_contracts/run_deepseek_p6_3c_r3a_decode_resident.py
0c299c1f6bd04af944c5732f9b879b4175cd3a134722ff739f6bbfa055eb43f7  tools/inference_contracts/run_deepseek_p6_3c_r3a_experiment.sh
27434047efd723ddea031d7a528b3eebd70aff93f10094a001a6a951ee6c4190  tools/inference_contracts/run_deepseek_p6_3c_r3a_mode.sh
9f0f31b93f261dbf9ffa16b64c801ac0b5b17ff07724fe3af7051f3e016a4a0c  tools/inference_contracts/run_deepseek_p6_3c_r3a_server_task.sh
```

这些 SHA 用于确认同步是否完整。若仓库 HEAD 已包含后续开发机提交，但上述代码提交仍是祖先，
且核心资产 SHA 相同，可以继续。服务器现场的 task-local 修复允许改变文件 SHA；这时按第 9 节
保存 before/after 和科学影响，不要为了旧 SHA 机械停止。

## 4. 实验设置

两侧共同冻结：

```text
model=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
served_model_name=deepseek-v4-flash-w8a8-mtp
vLLM=0.22.1+empty
vLLM-Ascend=0.22.1rc1
quantization=ascend
TP=8
EP=true
MTP num_speculative_tokens=1
cudagraph_mode=FULL_DECODE_ONLY
block_size=128
async_scheduling=true
Prefix Cache=false
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=9
profiler=disabled
retry=0
```

唯一 A/B 差异：

```text
--no-enable-chunked-prefill
--enable-chunked-prefill
```

每个 measured trial 的 resident cohort：

```text
8 requests × (256 input tokens + 128 forced output tokens)
temperature=0
ignore_eos=true
```

只有八个 choice 都返回至少 16 output token 后，客户端才通过第二个独立 streaming HTTP
request 注入 Prefill。每个 choice 保存 token arrival `monotonic_ns`；不保存生成文本或 token ID。

三个 cell：

| cell | 注入请求 | 作用 |
| --- | ---: | --- |
| `resident_only` | 无 | resident Decode 基线 |
| `fit_control_12000` | `12000 in + 4 out` | 预期两侧均可完整准入 |
| `admission_cliff_12281` | `12281 in + 4 out` | `D≥8` 时 Off 等待、On partial admit |

## 5. R3-S0 与 R3A 的执行关系

任务固定六个 fresh-model lifecycle：

```text
mechanism_01   Off   observer on
mechanism_02   On    observer on
performance_01 Off   observer off
performance_02 On    observer off
performance_03 On    observer off
performance_04 Off   observer off
```

前两个 lifecycle 是 R3-S0。每侧每 cell 只跑一个有效 trial，直接观察：

- 注入前是否确有八个 resident RUNNING；
- resident Decode 本轮实际 scheduled token 总量 `D`；
- 12000-token fit control 是否两侧都在首个相关 step 完整准入；
- 12281-token cliff 是否 Off 首步 waiting 且 scheduled Prefill=0；
- 同一 cliff 是否 On 首步 partial prefill 且与 resident Decode mixed；
- 是否发生 preemption；
- observer 是否原样返回 SchedulerOutput。

只有 `r3_s0_gate_complete=true`，experiment script 才继续四个 performance lifecycle。

性能轨道每个 lifecycle 对三个 cell 各执行六个有效 trial，共 18 measured trial；同 mode 的两个
lifecycle 合计每 cell 12 个样本。observer 和 profiler 都关闭。全任务包括 warmup 的预期总量：

```text
model lifecycles=6
engine requests=682
local HTTP requests=136
retries=0
```

## 6. 服务器同步与多会话隔离

本任务使用全部 NPU 0–7，必须全局独占这些卡。若任何其他会话正在运行 NPU/vLLM、占用
7000 端口、准备停止同一组 keep-alive，或声明即将执行八卡任务，本任务等待，不抢占、不终止
别人的进程。

共享仓库只用于 fetch 和环境/请求源定位；正式代码从独立 detached worktree 运行：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3a_2026_0803

cd "${SHARED_REPO}"
git fetch origin main
git rev-parse origin/main
git merge-base --is-ancestor 6175ac9f13b9e881bbf09d57c90f3299ae88abb8 origin/main

mkdir -p /data/node0_disk1/liguowei/server_worktrees
git worktree add --detach "${TASK_WORKTREE}" origin/main
cd "${TASK_WORKTREE}"
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

若该 worktree 已存在，不要删除；确认归本任务后继续，或换一个带时间后缀的新目录。不要在共享
checkout 中 `git pull`、`checkout`、`update-index --skip-worktree` 或编辑 tracked 文件。不要删除
其他会话的 Git lock。

确认核心资产：

```bash
cd "${TASK_WORKTREE}"
sha256sum \
  benchmarks/deepseek_v4_flash/workloads/p6_3c_r3a_decode_resident_admission_cliff_matched_ab.yaml \
  tools/inference_contracts/p6_3c_r3_decode_resident_observer.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3a_decode_resident.py \
  tools/inference_contracts/run_deepseek_p6_3c_r3a_experiment.sh \
  tools/inference_contracts/run_deepseek_p6_3c_r3a_mode.sh \
  tools/inference_contracts/run_deepseek_p6_3c_r3a_server_task.sh
```

## 7. 零 NPU 审计

在停 keep-alive 前先执行：

```bash
cd "${TASK_WORKTREE}"
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
PYTHON_BIN=/usr/bin/python3 \
REPO_ROOT="${TASK_WORKTREE}" \
bash tools/inference_contracts/run_deepseek_p6_3c_r3a_server_task.sh \
  /audit/p6_3c_r3a
```

审计应显示：

```text
formal_model_lifecycle_count_exact=6
engine_request_count_exact=682
http_request_count_exact=136
capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_9
mechanism_scout_required_before_performance=true
performance_order=off,on,on,off
observer=enabled only for mechanism
profiler=disabled
result_transfer_authorized=true
```

Off canonical server argv SHA 应为：

```text
cb4da1551e44da5faeb508b899254ff019c33ca5cad81146f2302a4bbe35d184
```

On canonical server argv SHA 应为：

```text
7a7703de70025eeeb4acbdbd7044aee2b74038846a07a2158b821143db7f9259
```

若审计中的路径、Python 或安装布局与现场不符，可以按第 9 节在 worktree 内修复。审计本身不得
触发 NPU、停止 keep-alive、启动 vLLM 或创建正式结果目录。

## 8. 正式运行与 keep-alive 规则

正式结果目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01
```

确认目录不存在、全局八卡无冲突后，唯一正式入口是：

```bash
cd "${TASK_WORKTREE}"
REPO_ROOT="${TASK_WORKTREE}" \
bash tools/inference_contracts/run_deepseek_p6_3c_r3a_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01
```

脚本会解析 shared environment 中的 editable vLLM 与 site-packages vLLM-Ascend，物化 task-local
overlay，复用 F4 已验证的 loopback proxy-safe、MTP 和 hybrid-KV repair，再启动六个独立
lifecycle。不要手工先启动 vLLM。

本任务需要 NPU 0–7，因此必须只停止并最终恢复完全相同的卡集：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

正式脚本已经在 success、failure、interrupt 和 early exit 路径中恢复卡。若服务器 AI 改写入口，
也必须保持这一语义。最终报告必须给出 `stopped_card_ids`、`restored_card_ids`、16 markers、端口
7000 listener、vLLM residual process 和 worktree 恢复状态。

## 9. 服务器 AI 的现场自适应权限

先读：

```text
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
```

服务器 AI 可以在独立 worktree、结果目录或 task-local overlay 中实时修复：

- vLLM/vLLM-Ascend 安装布局和路径解析；
- Python/Bash 兼容、代理、loopback health、超时与权限；
- warmup、stream parser、request-ID 匹配和 observer 字段提取；
- overlay patch、启动诊断、清理和结果归档；
- 不改变科学合同的控制面错误，并在新尝试可增加证据时重试。

不要为遵守历史的“禁止服务器改码、零重试、逐 SHA 失败即停”而放弃实质任务。自动 grade 只作
材料完整性提示；请求、调度 token、effect size 与资源恢复才是主要证据。

每次 adaptation 保存：

```text
server_local/adaptations/attempt_XX/reason.md
server_local/adaptations/attempt_XX/command.sh
server_local/adaptations/attempt_XX/stdout_stderr.tail.txt
server_local/adaptations/attempt_XX/exit_code.txt
server_local/adaptations/attempt_XX/change.patch
server_local/adaptations/attempt_XX/before_after_sha256.tsv
server_local/adaptations/attempt_XX/scientific_impact.json
```

以下变化必须建立新的 variant/task ID，不能在本 run01 内静默修改：

- `12288/12288/9`；
- resident 数量、输入/输出长度；
- 16-token injection gate；
- 12000 或 12281 injected Prompt；
- Off/On 唯一开关差异；
- measured cell、样本数或指标定义。

若 S0 因真实 `D` 使 12000 不再是 fit 或 12281 不再是 cliff，停止正式 performance，保留 S0
trace，并提出 `P6.3C-R3A-V2`：给出实际 `D`、新 Prompt 长度、两侧共同变化、信息增益、预计
资源成本和新 task ID。不要在 run01 performance 中临时换长度。

服务器不得推送远端 `main`。若现场修复有效，返回 patch 和证据，由开发机审核发布。

## 10. 主要指标与解释规则

机制轨道必须直接给出每个 mode-cell 的：

- first relevant scheduler step；
- resident running count；
- resident Decode scheduled tokens `D`；
- injected waiting/scheduled/partial；
- mixed Decode/Prefill；
- preemption。

性能轨道主要收益：

- injected TTFT；
- injected E2EL；
- trial makespan。

主要代价：

- resident Prefill 干扰窗口 P99 TBT；
- maximum resident token stall；
- aggregate output tokens/s。

预注册项目决策阈值：

```text
practical benefit: admission-cliff median injected TTFT 至少下降 20%
resident cost bound: P99 TBT 增幅不超过 10%
throughput cost bound: aggregate output TPS 降幅不超过 5%
uncertainty: 12 对 mode-cell 样本的 paired bootstrap median difference
bootstrap samples=10000, seed=633, 95% CI
```

必须区分：

```text
mechanism_confirmed_user_benefit_observed
mechanism_confirmed_tradeoff_only
mechanism_confirmed_no_material_benefit
mechanism_not_identified
```

即使材料完整，也可能得到 trade-off 或 no-material-benefit；这不是工程失败。反之，仅有请求成功
但没有 S0 机制证据，不能解释性能差异。

## 11. 停止条件与后续动作

以下情况停止并回报，不自动进入性能或下一个研究任务：

- S0 gate false；
- 八个 resident 未共同达到 16-token gate；
- fit/cliff 的实际 scheduler 语义不符合预期；
- preemption 破坏比较；
- 同一控制面阻塞重复且不再增加信息；
- 其他会话开始占用八卡或共享资源；
- 资源恢复、数据安全或结果来源无法保证。

若 S0 和 R3A 完整完成，也不要自动进入 R3B、R3C、P7、P8 或 P9。只提交结果、等待开发机审查。

## 12. 结果清单与传输

原始 token timestamp、scheduler trace、server log、metrics 和 body 留在服务器。finalizer 生成
≤70KB 候选包与：

```text
candidate_manifest.server_local.json
```

`result_transfer_authorized: true` 表示候选包可以传输，不表示自动选择渠道。完成后先报告：

- result summary 的完整路径；
- 候选文件名、bytes、SHA-256、敏感性；
- 文件总数和总 bytes；
- `email` / `upload-api` / `server-local` 三个可选渠道；
- 推荐渠道与理由。

等待用户明确选择后，再一次性传输完整清单。不要先发状态邮件；不要沿用上次的 upload-api
选择；401/409/413、代理、重定向、超时、服务或 hash 失败后也不得自动切换渠道。

## 13. 必须回报的格式

```text
P6_3C_R3A_SERVER_REPORT_BEGIN
task_id=p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01
worktree=<实际路径>
head=<HEAD>
origin_main=<origin/main>
code_commit_is_ancestor=<true/false>
shared_checkout_modified=<true/false>
npu_conflict_check=<通过或等待说明>
audit_only_exit=<exit>
formal_experiment_started=<true/false>
stopped_card_ids=<实际>
restored_card_ids=<实际>
keep_alive_restored_exact=<true/false>
lifecycles=<x/6>
engine_requests=<x/682>
http_requests=<x/136>
retries=<数量>
r3_s0_gate_complete=<true/false>
eight_residents_running=<true/false + 实测>
resident_decode_tokens_D=<Off/On、fit/cliff 实测>
fit_control_whole_admission_both_modes=<true/false>
off_cliff_wait_zero_prefill=<true/false>
on_cliff_partial_mixed_admission=<true/false>
preemption_count=<数量>
performance_lifecycles_complete=<true/false>
admission_cliff_ttft_off_median_ms=<值>
admission_cliff_ttft_on_median_ms=<值>
admission_cliff_ttft_relative_change=<值>
paired_bootstrap_ttft_ci95=<low,high>
resident_p99_tbt_relative_change=<值>
aggregate_output_tps_relative_change=<值>
scientific_outcome=<四类之一>
scientific_contract_changed=<true/false；true 时必须是新 variant>
adaptive_attempt_count=<数量>
adaptive_patch_paths=<none 或路径>
evidence_status=<complete/incomplete>
cleanup_status=<clean/incomplete>
port_7000_listener_count=<数量>
vllm_residual_process_count=<数量>
candidate_manifest=<完整路径>
candidate_file_count=<数量>
candidate_total_bytes=<字节>
transfer_method_selected=false
available_methods=email,upload-api,server-local
recommended_method=<方法及理由>
next_task_authorized=false
P6_3C_R3A_SERVER_REPORT_END
```

最后用自然语言回答三个问题：

1. Chunked Prefill 是否在 resident Decode 存在时改变长 Prefill 的准入？
2. injected TTFT 得到了多大收益，resident TBT 和总吞吐付出了什么代价？
3. 这一结论可以外推到哪里，不能外推到哪里？
