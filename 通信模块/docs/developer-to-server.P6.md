# 开发机 → Ascend 服务器：P6 独立候选任务

## P6.3C-R2 run01：容量校准后的 Chunked Prefill 调度压力匹配 A/B

```yaml
dispatch_revision: p6_3c_r2_capacity_calibrated_2026_0729_r1
task_id: p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
run_id: p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
stage: P6.3C-R2
execution_mode: authorized_capacity_calibrated_scheduler_pressure_matched_ab
npu_execution_authorized: true
npu_card_ids: [0, 1, 2, 3, 4, 5, 6, 7]
formal_model_lifecycle_count_exact: 6
engine_request_count_exact: 90
batched_http_call_count_exact: 48
request_retry_count_exact: 0
parameter_sweep_authorized: false
server_side_code_edit_authorized: false
base_conda_environment_mutation: false
prefix_cache_enabled: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
next_task_authorized: false
```

这是一份独立的 P6 候选交接，不覆盖
`通信模块/docs/developer-to-server.md` 中其他会话占用的当前任务。只有在用户明确派发本
文件，并且服务器确认没有其他任务正在使用、停止、恢复或清理 NPU 0–7 时，才可执行。
若 K2、K3、P8.3、P9、其他 P6 或任意服务器/NPU 作业仍在运行或收尾，立即停在零 NPU
前置门，报告冲突，不进入 audit-only，不停止 keep-alive，也不排队自动续跑。

服务器助手不需要补写实验代码。本轮开发机已经把容量合同、共同运行时修复、两条证据
轨道、完整请求体、生命周期、首错归类、结果聚合、清理恢复和有界打包写好。服务器只需：

1. 获得本 P6 文件的明确派发；
2. 等待并复核全局无冲突；
3. fast-forward 同步远程 `main`，重新读取本文件；
4. 完成 Git、固定输入、源码和 17 个任务资产的事实门；
5. 零 NPU 执行一次 audit-only；
6. 只运行一次正式 server-task driver；
7. 无论成功、失败、中断或早退，都确认 0–7 keep-alive 精确恢复；
8. 原样回报 `P6_3C_R2_SERVER_REPORT_BEGIN/END` 全段和有界结果包清单；
9. 暂停，等待用户选择 `email`、`upload-api` 或 `server-local`，不得自动传输。

## 1. 结论边界与本轮真正要回答的问题

### 1.1 原 P6.3C 审计必须保留

原 P6 参考配置：

```text
max_model_len=135168
max_num_batched_tokens=4096
max_num_seqs=1
```

仅证明 Chunked Prefill Off 侧无法在这组完全冻结的参数下启动，因此不能直接接在 P6.1
之后形成 131K+c1 严格单变量 A/B。它不证明 Chunked Prefill 无法研究，也不允许覆盖或
改写原 `blocked_p6_3c_not_strict_single_variable` 审计。

### 1.2 P6.3C-R1 是有效的启动 RED，不是机制结论

R1 重新冻结为 `69632/69632/2`，但在第一个 Off 机制 lifecycle 的 EngineCore KV cache
初始化阶段失败：

```text
formal_grade=red_p6_3c_r1_scheduler_pressure_no_success
available_kv_cache_gib=8.27
required_kv_cache_gib=36.66
estimated_max_model_len=15672
lifecycle_count_actual=1/6
engine_request_count_actual=0/90
batched_http_call_count_actual=0/48
scheduler_step_count_actual=0
```

因此 R1 没有观测 Chunked Prefill 调度机制，也没有性能结论。R1 结果链必须保留；本任务
不是 R1 重跑，也不得创建 R1 run02。

### 1.3 R2 的共同容量环境

R2 根据 R1 服务器给出的 `estimated_max_model_len=15672`，为两侧共同冻结一组更保守、
可承载两请求压力的容量环境：

```text
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=2
```

按 R1 的线性诊断只用于选点，12288 约需 6.469 GiB KV，相对 R1 的 8.27 GiB 可用量约留
1.801 GiB 余量。该估算不是服务器验证；正式启动结果必须由本次任务记录。禁止在服务器
侧把 12288 改成 14336、15360、15672 或其他值，禁止自动降档。

两侧还共同启用已经在 P6.3B 服务器验证过的 deferred hybrid-KV 任务内修复，以避免重新
引入已知的 MTP/hybrid KV 兼容缺口。修复只写入每个 lifecycle 的临时 overlay，不修改
base conda、site-packages 或仓库。它在 Off/On 六个 lifecycle 完全相同，不能被宣称为
R1 启动 RED 的唯一原因或唯一修复。

### 1.4 唯一 A/B 差异

在每条证据轨道内，canonical server argv 唯一差异必须是：

```text
Off: --no-enable-chunked-prefill
On:  --enable-chunked-prefill
```

Prefix Cache 两侧显式关闭。模型、量化、MTP、graph、block size、GPU memory utilization、
并行度、共同 hybrid-KV 修复和所有其他参数必须一致。

### 1.5 三个双请求单元

| 实验单元 | 同时到达的输入 | 总 Prefill tokens | 用途 |
|---|---:|---:|---|
| `no_pressure_4k_4k` | 4K + 4K | 8,192 | 低于 12,288，验证无压力时两侧接近 |
| `asymmetric_pressure_10k_6k` | 10K + 6K | 16,384 | 超过预算，观察长请求分块和短请求 TTFT |
| `symmetric_pressure_8k_8k` | 8K + 8K | 16,384 | 超过预算，观察公平性、完成时间差和批吞吐 |

本轮要回答的是：

1. 总 Prefill tokens 超过共同预算时，On 是否实际形成多轮 prefill chunk；
2. Off 是否采用整段准入或串行等待，On 是否降低短请求受长 Prefill 阻塞的程度；
3. 该调度变化对 TTFT、E2EL、TPOT、ITL、批输出吞吐和两请求完成时间差有何描述性影响。

无论结果正负，都不得把本轮外推为普遍收益、统计显著性或生产吞吐结论。

## 2. 两条证据轨道与固定工作量

### 2.1 机制轨道

```text
mechanism_01: Off
mechanism_02: On
observer: read-only scheduler wrapper
profiler: off
每 lifecycle: 1 个 warmup batch + 每 cell 3 个 measured batch
```

observer 只记录每轮 scheduled token、partial prefill/chunk、waiting/running 队列和请求次序。
它不得改调度决策。预期用事实判定：

- 无压力单元两侧均不应出现 partial prefill；
- 两个压力单元的 On 侧应出现 partial prefill；
- Off 侧不得伪报 partial prefill。

若观测不满足预期，应按证据真实分级，不得人工改 JSON、TSV 或 grade。

### 2.2 性能轨道

```text
performance_01: Off
performance_02: On
performance_03: On
performance_04: Off
observer: off
profiler: off
每 lifecycle: 1 个 warmup batch + 每 cell 3 个 measured batch
```

固定总量：

```text
fresh model lifecycles: 6
warmup engine requests: 6
measured mechanism engine requests: 12
measured performance engine requests: 72
engine requests total: 90
batched HTTP calls total: 48
request retries: 0
canonical request bodies: 14
```

一个 batched HTTP call 同时携带两个 prompt；不要拆成两个顺序 HTTP 请求。

## 3. 服务器固定路径与版本事实

```bash
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN="${ENV_PREFIX}/bin/python"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
```

固定环境：

```text
vLLM commit=0decac0d96c42b49572498019f0a0e3600f50398
vLLM-Ascend commit=5f6faa0cb8830f667266f3b8121cd1383606f2a1
tensor parallel=8
expert parallel=true
quantization=ascend
block_size=128
gpu_memory_utilization=0.92
MTP speculative tokens=1
cudagraph mode=FULL_DECODE_ONLY
async scheduling=true
```

固定请求源：

```text
path=工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
bytes=19487
sha256=48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
```

冻结的服务器源码事实：

| 文件 | bytes | SHA-256 |
|---|---:|---|
| `${ENV_PREFIX}/lib/python3.11/site-packages/vllm/v1/core/single_type_kv_cache_manager.py` | 53714 | `d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1` |
| `${ENV_PREFIX}/lib/python3.11/site-packages/vllm/v1/core/kv_cache_coordinator.py` | 25255 | `a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89` |
| `/data/node0_disk1/vllm-ascend-0.22.1rc1/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py` | 23103 | `dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20` |
| `/data/node0_disk1/vllm-ascend-0.22.1rc1/vllm_ascend/patch/platform/patch_kv_cache_interface.py` | 11819 | `a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2` |
| `/data/node0_disk1/vllm-ascend-0.22.1rc1/vllm_ascend/spec_decode/llm_base_proposer.py` | 以服务器现有文件为准 | `0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb` |
| `/data/node0_disk1/vllm-ascend-0.22.1rc1/vllm_ascend/distributed/kv_transfer/__init__.py` | 以服务器现有文件为准 | `dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1` |
| `/data/node0_disk1/vllm-0.22.1/vllm/v1/core/sched/scheduler.py` | 以服务器现有文件为准 | `41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983` |

若安装布局与路径不同，只允许用 Python import 解析同一环境中对应模块的真实文件；不得
编辑或替换源码。任一 bytes/SHA 不符，分级
`blocked_p6_3c_r2_source_or_resource_gate`，停在 NPU 前。

## 4. 同步、全局互斥与 Git 前置门

### 4.1 只允许 fast-forward 同步

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git status --short --branch
git fetch origin main
git switch main
git pull --ff-only origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
```

必须同时满足：

```text
branch=main
HEAD=origin/main
ahead/behind=0/0
tracked-clean=true
```

不得在服务器编辑、提交、stash、merge、rebase 或 push。若非 fast-forward、工作树不干净
或 `RESULT_DIR` 已存在，立即阻断并报告，不得删除已有结果目录。

### 4.2 全局互斥

先通过服务器的全局任务协调信息确认没有其他会话在运行、恢复或清理。再执行只读检查：

```bash
pgrep -af 'run_deepseek|vllm.*serve|npu_stop|npu_keep_alive' || true
ss -ltnp | grep -E ':(7000|8000|8001|9000)\b' || true
test ! -e "${RESULT_DIR}"
```

任何活动任务、DeepSeek vLLM 服务、协调不明或端口冲突都属于
`blocked_p6_3c_r2_source_or_resource_gate`。不要杀掉别的任务，不要抢卡，不要等待后自动
续跑；向用户报告后停止。

### 4.3 keep-alive 规则

本任务正式执行需要 NPU 0–7，driver 会在所有事实门通过后停止 keep-alive，并在成功、
失败、中断或早退的每条退出路径恢复同一集合：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

不要在正式 driver 之前手工停卡，不要再包一层额外 lifecycle。报告必须给出 stopped IDs、
restored IDs、16 个 marker、0–7 覆盖、7000 端口残留、vLLM 残留和 tracked-clean 状态。

## 5. 17 项任务资产 SHA 门

同步后逐项核对；任一不符都在 NPU 前停止，不得“修一下再跑”：

| # | 文件 | bytes | SHA-256 |
|---:|---|---:|---|
| 1 | `tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh` | 2107 | `a035f9ce05840891e75e876720dfc917de462f7bcf376eb1da9765102bf760db` |
| 2 | `tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh` | 10206 | `a6a25483e15b603b2f9cf804a2d991cb29a387d08e60fda83a13d806a467cae8` |
| 3 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh` | 3865 | `70fd8adb27a3c0cf9cf1ff2b58bbdefa86dc65e8eee15778034e1d24170e54be` |
| 4 | `tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh` | 535 | `36ecea4ddd254919c1aad6cf16bf81507287e0515565d601ab7c261b86a4c970` |
| 5 | `tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh` | 18377 | `3109b61be4712b17e448c5c8633da5831ae03ca1cf58325b7efbfddd13a555e8` |
| 6 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py` | 18767 | `9192aa43fde8cc129cee8029905e3ba620951d86774929a227c89ec386f4ab3a` |
| 7 | `tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py` | 62332 | `de04fca9241a17d74350e49449c5292e69411381aa7118827326603b197eec1c` |
| 8 | `tools/inference_contracts/p6_3c_startup_resource_summary.py` | 5009 | `b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a` |
| 9 | `tools/inference_contracts/p6_3c_r1_scheduler_observer.py` | 7251 | `c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4` |
| 10 | `tools/inference_contracts/canonicalize_server_argv.py` | 1238 | `c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d` |
| 11 | `tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py` | 10250 | `6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c` |
| 12 | `tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py` | 2733 | `9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631` |
| 13 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml` | 9984 | `1d031b7e0116cb28952b6f9d3d3b417528246417be0b002f74e9e13f37d9dd42` |
| 14 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch` | 769 | `75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1` |
| 15 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch` | 830 | `2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f` |
| 16 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch` | 1054 | `cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e` |
| 17 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch` | 896 | `ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b` |

建议用只读循环输出 `path / bytes / SHA-256`，与表格逐项比较。特别注意第 14 项正确值
包含 `...f261a3...`，不是旧交接 typo 的 `...f262a3...`。

## 6. 零 NPU audit-only

只有 §3–§5 全部通过、全局无冲突且 `RESULT_DIR` 不存在时才执行：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
```

audit-only 不触 NPU、不停 keep-alive、不创建结果目录。必须核对：

```text
task_id=p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
expected_result_basename=p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
model_lifecycle_count_exact=6
engine_request_count_exact=90
batched_http_call_count_exact=48
request_retry_count_exact=0
shared_hybrid_kv_repair=enabled_both_modes_all_lifecycles
capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_2
cells=no_pressure_4k_4k,asymmetric_pressure_10k_6k,symmetric_pressure_8k_8k
```

六个 lifecycle 必须全部显示：

```text
prefix_caching=false
shared_hybrid_kv_repair=1
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=2
```

同一 track 的 canonical argv：

```text
Off SHA-256=568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10
On  SHA-256=cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017
delta_count=1
delta=--no-enable-chunked-prefill ↔ --enable-chunked-prefill
```

任一项不符，分级 `blocked_p6_3c_r2_source_or_resource_gate` 并停止。不得为了通过 audit
编辑脚本、文档、argv、环境或 site-packages。

## 7. 正式执行：只允许一次

所有前置门通过后，执行下面唯一命令一次：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
bash tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
```

driver 负责：

- 复核 result basename、Git parity、tracked-clean、端口、vLLM 残留和固定输入；
- 停止 NPU 0–7 keep-alive；
- prepare 14 个 canonical request bodies；
- 依次运行 6 个 fresh lifecycles；
- 首次失败后停止后续 lifecycles，零 retry；
- 每个已启动 lifecycle 汇总启动资源和首错；
- 无论退出原因都恢复 NPU 0–7 keep-alive；
- finalize、grade、生成有界 candidate manifest 和固定报告段。

禁止：

- 不得手工调用 mode runner 或 scheduler-pressure runner；
- 不得手工补跑缺失 lifecycle，不得创建 run02；
- 不得改 12288、三组 prompt 长度、输出 64 tokens、重复次数或顺序；
- 不得 retry、sweep、自动回退、加 profiler 或让 observer 进入性能轨道；
- 不得启用 Prefix Cache；
- 不得编辑仓库、base conda、site-packages、模型或生成的 JSON/TSV/grade；
- 不得混跑原 P6.3C、R1、K2、K3、P8.3、P9 或任何下一任务；
- 不得因为性能正负自行改分级；
- 不得自动 email 或 upload。

## 8. 分级规则

| grade | 条件 |
|---|---|
| `blocked_p6_3c_r2_source_or_resource_gate` | 全局冲突、Git/SHA/输入/端口/资源/audit 任一前置门失败；未触 NPU |
| `red_p6_3c_r2_startup_kv_capacity_no_success` | 已进入正式任务，但首个或后续 lifecycle 因 KV cache 容量不足而未 ready |
| `red_p6_3c_r2_scheduler_pressure_no_success` | 已进入正式任务，但没有形成可用请求/调度证据的其他失败 |
| `yellow_p6_3c_r2_scheduler_pressure_partial` | 有部分成功，但不足 6/6 lifecycle、90/90 requests 或 48/48 batches |
| `red_p6_3c_r2_scheduler_pressure_evidence_incomplete` | 工作量完成但单变量、observer、队列、MTP、健康或必需证据不完整 |
| `candidate_green_p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab` | 6/6、90/90、48/48、零 retry、共同 repair identity、单开关、机制轨道和性能轨道全部完整 |
| `red_cleanup_incomplete` | keep-alive、残留进程、端口或 tracked-clean 任一未恢复；优先级高于实验结果 |

`candidate_green` 仍需开发机复核，不等于普遍正向成果。若 On 没有观察到预期 partial
prefill，不得强行判绿；若性能没有改善，也不得删掉机制证据。

## 9. 结果、清理和回报

大文件、raw vLLM 日志、请求体、scheduler JSONL、模型输出或 profiler 数据必须留在：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01
```

优先核对以下有界结果候选：

```text
result_summary.md
environment_and_hashes.json
request_body_manifest.json
lifecycle_summary.tsv
startup_resource_summary.tsv
mechanism_scheduler_summary.json
mechanism_request_chunk_summary.tsv
performance_mode_cell_summary.tsv
performance_order_balanced_pairs.tsv
grading_inputs.json
resource_recovery_summary.json
cleanup_status.txt
first_failure_excerpt.txt
candidate_manifest.server_local.json
```

若某文件因首错未产生，manifest 和 result summary 必须如实表达，不得手工补造。

把 driver 输出的以下整个区间原样回复：

```text
P6_3C_R2_SERVER_REPORT_BEGIN
...
P6_3C_R2_SERVER_REPORT_END
```

并在报告外简要列出：

1. formal grade 与首个失败阶段；
2. HEAD、origin/main、ahead/behind、tracked-clean；
3. 17 项 SHA 和 audit-only 是否全部通过；
4. lifecycle、engine request、batched HTTP call、scheduler step 实际/计划；
5. 六个 lifecycle 的 server-ready、available/required KV、estimated max len；
6. Off/On canonical argv SHA 和唯一 delta；
7. 两个压力单元的 partial-prefill/chunk/队列事实；
8. TTFT、E2EL、TPOT、ITL、批吞吐、两请求完成时间差的描述性摘要；
9. stopped/restored card IDs、marker 数、端口、vLLM residual、tracked-clean；
10. result dir；
11. 完整有界包清单：每项 path、bytes、SHA-256、sensitivity；
12. 可用方法 `email` / `upload-api` / `server-local` 以及一个推荐方法和原因；
13. 是否存在任何偏离；正确答案应为无参数调整、无 retry、无 server edit、无下一任务。

## 10. 传输边界

服务器通信小载荷上限为：邮件正文和每个附件均不超过 70KB。不要请求或发送 raw logs、
trace、数据集、模型输出或实验目录。

`result_transfer_authorized: true` 仅表示本任务生成的完整有界结果包具备候选传输资格，不
选择传输方法，也不扩大文件范围。服务器必须先报告完整候选清单、bytes、SHA-256、
sensitivity、可用方法和推荐理由，然后暂停，等待用户明确选择一次：

```text
email
upload-api
server-local
```

没有选择前不得发状态邮件、不得上传。选 `email` 时，将结果摘要作为正文并一次附上用户
批准的完整附件集合；选 `upload-api` 时，在一个具名 multi-file session 中提交摘要和
全部批准附件。token 只保存在服务器本地 `.env`。遇到 401、409、413、代理/重定向、
timeout、服务异常或 hash 校验失败，不得自动换渠道，必须重新等待用户选择。

## 11. 停止条件

以下任一情况都立即停止：

- 没有本 P6 文件的明确派发；
- 其他任务仍运行、恢复、清理或协调状态不明；
- Git 非 main、非 parity、非 tracked-clean 或不能 fast-forward；
- 固定源码、输入或 17 项任务资产任一 bytes/SHA 不符；
- `RESULT_DIR` 已存在；
- audit-only 与 §6 不一致；
- 正式 driver 已经运行过一次；
- keep-alive、端口或 vLLM 残留恢复不完整。

停止后只报告事实和建议，不编辑服务器代码，不创建下一任务，不自动传输结果。
