# 开发机 → Ascend 服务器交接任务（P6 专用）

## P6.3C-R2-F1 run01：科学合同不变的 runtime-layout-portable Chunked Prefill A/B

```yaml
dispatch_revision: p6_3c_r2_f1_runtime_layout_portable_2026_0729_r1
task_id: p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01
run_id: p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01
stage: P6.3C-R2-F1
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
server_side_code_edit_authorized: false
server_side_path_wrapper_authorized: false
retry_authorized: false
run02_authorized: false
next_task_authorized: false
```

本文件只管理 P6，不覆盖 `通信模块/docs/developer-to-server.md` 中其他会话正在管理的
K2 或其他任务。只有用户明确派发本文件，并且服务器全局协调确认没有其他任务正在
使用、停止、恢复或清理 NPU 0–7，才可执行。若 K2、K3、P8.3、P9、其他 P6 或任意
NPU/vLLM 作业仍在运行或收尾，立即停在零 NPU 互斥门，报告冲突；不要排队后自动续跑。

服务器助手不需要写代码，也不需要推测安装路径。本轮开发机已经把真实包路径解析、
任务内 overlay 物化、四类补丁预检、请求准备、六生命周期、结果聚合和资源恢复写入
唯一 driver。服务器只需严格按本文件同步、核验、audit、执行一次和回报。

## 1. 为什么不是重跑 R2 run01

必须保留三条既有证据：

1. 原 P6.3C 的 `blocked_p6_3c_not_strict_single_variable` 只证明冻结
   `135168/4096/1` 下 Off 侧不能启动，不代表 Chunked Prefill 无法研究。
2. P6.3C-R1 的 `69632/69632/2` 在 KV-cache 初始化阶段失败，0 request、
   0 scheduler step，只是容量启动 RED。
3. P6.3C-R2 run01 已通过 Git、17 项任务 SHA、七项冻结源码、请求源与 audit-only，
   但首个 `mechanism_01` 在 vLLM 启动前准备 task-local overlay 时失败：
   `vllm_ascend/spec_decode/llm_base_proposer.py` 没有出现在预期的物化覆盖树中。

R2 run01 的服务器实际安装是：

- `vllm`：editable install，不在固定 `site-packages/vllm`；
- `vllm_ascend`：环境 `site-packages`；
- 旧 driver：接受服务器手工创建的符号链接 wrapper，但复制时没有保证得到真实文件树。

R2 run01 实际为 0 ready、0 startup resource row、0/90 request、0/48 batch、
0 scheduler step。0–7 keep-alive 精确恢复，16 marker、端口 7000、vLLM residual 与
tracked worktree 全部 clean。服务器报告的 `red_cleanup_incomplete` 是旧 finalizer
把五个从未运行的 lifecycle `missing` 误算成 cleanup failure；项目分类是：

```text
runtime_overlay_preparation_failed_before_vllm_startup
```

它不是 Chunked Prefill、KV capacity、调度、性能或资源清理结论。不得覆盖原结果目录，
不得创建 R2 run02，也不得原样重跑旧入口。

## 2. R2-F1 改了什么、没有改什么

### 2.1 科学合同完全不变

两侧共同冻结：

```text
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=2
Prefix Cache=false（显式）
MTP num_speculative_tokens=1
TP8 + EP
W8A8 ascend quantization
block_size=128
gpu_memory_utilization=0.92
FULL_DECODE_ONLY
async scheduling=true
同一 deferred hybrid-KV task-local repair
observer 只在机制轨道启用
profiler 全程关闭
```

三组双请求仍为：

| cell | 同时输入 | 总 Prefill | 作用 |
|---|---:|---:|---|
| `no_pressure_4k_4k` | 4096 + 4096 | 8192 | 低于预算的无压力对照 |
| `asymmetric_pressure_10k_6k` | 10240 + 6144 | 16384 | 长短请求调度压力 |
| `symmetric_pressure_8k_8k` | 8192 + 8192 | 16384 | 对称调度压力 |

唯一 A/B 差异仍是：

```text
Off: --no-enable-chunked-prefill
On:  --enable-chunked-prefill
```

生命周期仍为 `mechanism Off → mechanism On → performance Off → On → On → Off`；
总量仍为 6 个 fresh model lifecycle、90 engine request、48 batched HTTP call、
14 canonical body、零 retry。不得改参数、请求长度、顺序、重复数、输出 64 tokens
或共同 repair。

### 2.2 只修服务器运行布局

正式入口会在停止 keep-alive 之前自动：

1. 用目标 conda 环境自己的 Python `importlib.find_spec` 解析 `vllm` 与
   `vllm_ascend` 的真实包目录并做 `realpath`；
2. 对七个冻结源文件按真实路径做 SHA-256 门；
3. 把真实 `vllm_ascend` 包彻底物化到一次性临时 overlay，解引用符号链接，不保留
   ownership；
4. 验证 overlay 内 package-root symlink=0、realpath escape=0；
5. 在临时树完整 dry-run/apply MTP、hybrid manager、deferred install 与 scheduler
   observer patch，并验证 post-patch hash；
6. 只有这些步骤全部通过，才进入会停止 NPU keep-alive 的基础 driver。

不要再创建 `/tmp/p6_3c_r2_env_prefix` 或任何手工 symlink wrapper，不要导出
`BASE_PLUGIN_ROOT` / `BASE_VLLM_ROOT` 绕过自动解析，不要编辑 site-packages。

正式 lifecycle 复用同一 overlay builder。每个已尝试 lifecycle 在任何早退路径都会写
`lifecycle_exit_code.txt` 与 `cleanup_status.txt`；后续未执行 lifecycle 记为
`not_run`，不会污染全局清理等级。零 request/零 scheduler evidence 的布尔结论记为
`not_observed`，不能从空集合推导“Off 无分块=True”。

## 3. 固定路径

```bash
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01
```

固定请求源：

```text
工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
bytes=19487
sha256=48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
```

冻结运行时：

```text
vLLM commit=0decac0d96c42b49572498019f0a0e3600f50398
vLLM-Ascend commit=5f6faa0cb8830f667266f3b8121cd1383606f2a1
```

## 4. 第一道门：全局互斥

先通过服务器全局任务协调信息确认其他会话已经完全停止并完成资源恢复。再只读检查：

```bash
pgrep -af '[r]un_deepseek.*(server_task|scheduler_pressure)|[v]llm.*serve|[n]pu_stop.sh' || true
ss -ltnp | grep -E ':(7000|8000|8001|9000)\b' || true
```

低优先级 keep-alive 正常存在不算冲突；其他实验 driver、vLLM 服务、停卡/恢复操作、
占用端口或协调状态不明都算冲突。不要杀其他任务，不要抢卡，不要等待后自动续跑。

## 5. 同步与 Git 门

只允许 fast-forward：

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
RESULT_DIR 不存在
```

服务器不得 stash、merge、rebase、commit、push、删除旧结果或编辑任何 tracked 文件。

## 6. 21 项仓库资产门

同步后按表逐项核对 bytes 与 SHA-256。任一不符，在零 NPU 阶段停止；不得修一下再跑。

| # | 文件 | bytes | SHA-256 |
|---:|---|---:|---|
| 1 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f1_server_task.sh` | 748 | `8a3246bcf79228457b15b8214cf861639d6666e23da68621886187025af7e91a` |
| 2 | `tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh` | 5211 | `c62f06bc39f34dfd7c397eb7eb7b63c08692c917e7a0ada1e5bb17e9e935297c` |
| 3 | `tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh` | 10206 | `a6a25483e15b603b2f9cf804a2d991cb29a387d08e60fda83a13d806a467cae8` |
| 4 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh` | 4257 | `d5f07ff8fc894ee6b5c4f53d2d07cf03f46d57c481243c198d334e6c4aad0826` |
| 5 | `tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh` | 562 | `108a9fc218ad43694ee7ae3dfceea37ea8837333f66cd9ca90858a084fa6cea1` |
| 6 | `tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh` | 17414 | `fe796f2bc8da753adfe81eb900b4bbafe8a96462cc1359a9e40e90e20564d03b` |
| 7 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py` | 26034 | `d650c65affcccfcd81d6e3472f754d412096e8bf1d782f2272054e18801622b7` |
| 8 | `tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py` | 62904 | `e7329112f21e39088258fed4c13bcdb0f03bdea1ba3dc597214d1fa4faf1712d` |
| 9 | `tools/inference_contracts/resolve_p6_3c_runtime_layout.py` | 4663 | `a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897` |
| 10 | `tools/inference_contracts/prepare_p6_3c_runtime_overlay.py` | 11757 | `9086250e6b6b879071b0db60eefc873aee5c8dffe77a0e5f28aa40bd72ce6411` |
| 11 | `tools/inference_contracts/p6_3c_startup_resource_summary.py` | 5009 | `b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a` |
| 12 | `tools/inference_contracts/p6_3c_r1_scheduler_observer.py` | 7251 | `c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4` |
| 13 | `tools/inference_contracts/canonicalize_server_argv.py` | 1238 | `c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d` |
| 14 | `tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py` | 10250 | `6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c` |
| 15 | `tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py` | 2733 | `9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631` |
| 16 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f1_runtime_layout_portable_matched_ab.yaml` | 3564 | `3ecbe5d5a67b4047b308669ae36578739a08a78226aeab0957737acfad394d3c` |
| 17 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml` | 10881 | `475fb070c6904e31b9e1dfdb1209f1c088d490fbaf618417eea59d83e23c32ec` |
| 18 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch` | 769 | `75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1` |
| 19 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch` | 830 | `2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f` |
| 20 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch` | 1054 | `cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e` |
| 21 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch` | 896 | `ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b` |

可用以下只读循环核对：

```bash
while IFS='|' read -r path expected_bytes expected_sha; do
  test -f "${path}"
  actual_bytes=$(stat -c '%s' "${path}")
  actual_sha=$(sha256sum "${path}" | awk '{print $1}')
  printf '%s\t%s\t%s\n' "${path}" "${actual_bytes}" "${actual_sha}"
  test "${actual_bytes}" = "${expected_bytes}"
  test "${actual_sha}" = "${expected_sha}"
done <<'EOF'
tools/inference_contracts/run_deepseek_p6_3c_r2_f1_server_task.sh|748|8a3246bcf79228457b15b8214cf861639d6666e23da68621886187025af7e91a
tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh|5211|c62f06bc39f34dfd7c397eb7eb7b63c08692c917e7a0ada1e5bb17e9e935297c
tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh|10206|a6a25483e15b603b2f9cf804a2d991cb29a387d08e60fda83a13d806a467cae8
tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh|4257|d5f07ff8fc894ee6b5c4f53d2d07cf03f46d57c481243c198d334e6c4aad0826
tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh|562|108a9fc218ad43694ee7ae3dfceea37ea8837333f66cd9ca90858a084fa6cea1
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh|17414|fe796f2bc8da753adfe81eb900b4bbafe8a96462cc1359a9e40e90e20564d03b
tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py|26034|d650c65affcccfcd81d6e3472f754d412096e8bf1d782f2272054e18801622b7
tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py|62904|e7329112f21e39088258fed4c13bcdb0f03bdea1ba3dc597214d1fa4faf1712d
tools/inference_contracts/resolve_p6_3c_runtime_layout.py|4663|a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897
tools/inference_contracts/prepare_p6_3c_runtime_overlay.py|11757|9086250e6b6b879071b0db60eefc873aee5c8dffe77a0e5f28aa40bd72ce6411
tools/inference_contracts/p6_3c_startup_resource_summary.py|5009|b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a
tools/inference_contracts/p6_3c_r1_scheduler_observer.py|7251|c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4
tools/inference_contracts/canonicalize_server_argv.py|1238|c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d
tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py|10250|6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py|2733|9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f1_runtime_layout_portable_matched_ab.yaml|3564|3ecbe5d5a67b4047b308669ae36578739a08a78226aeab0957737acfad394d3c
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml|10881|475fb070c6904e31b9e1dfdb1209f1c088d490fbaf618417eea59d83e23c32ec
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch|769|75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch|830|2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch|1054|cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch|896|ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
EOF
```

## 7. 零 NPU audit-only

只有 §4–§6 全过且新 `RESULT_DIR` 不存在时执行：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r2_f1_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01
```

audit-only 不停 keep-alive、不创建结果目录。必须看到：

```text
task_id=p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01
expected_result_basename=p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01
formal_model_lifecycle_count_exact=6
engine_request_count_exact=90
batched_http_call_count_exact=48
request_retry_count_exact=0
capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_2
shared_hybrid_kv_repair=enabled_both_modes_all_lifecycles
```

六个 lifecycle 的 `max_model_len/max_num_batched_tokens/max_num_seqs` 必须都是
`12288/12288/2`，Prefix Cache=false、repair=1。canonical argv 必须是：

```text
Off SHA-256=568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10
On  SHA-256=cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017
唯一 delta=--no-enable-chunked-prefill ↔ --enable-chunked-prefill
```

audit 后再次确认远程 HEAD 未漂移、工作树仍 clean、全局仍无冲突。任一不符停止。

## 8. 正式执行：只允许一次

执行唯一命令：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
bash tools/inference_contracts/run_deepseek_p6_3c_r2_f1_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01
```

入口首先完成真实布局解析、七项源码 SHA、物化 overlay 和全部补丁预检。预期先看到：

```text
runtime_layout_resolved:vllm=...:vllm_ascend=...
runtime_overlay_prepared:files=<positive>:symlinks=0:escapes=0
```

如果出现 `P6_3C_RUNTIME_OVERLAY_PREFLIGHT_BLOCKED`，说明尚未停卡、未创建结果目录：
原样回报首错并停止，不要手工修路径，不要再调用第二次。

预检通过后，基础 driver 才会停止 NPU 0–7 keep-alive、准备请求并运行六个 lifecycle。
不要手工调用 mode/scheduler runner，不要补跑缺失 lifecycle，不要创建第二 attempt。

## 9. keep-alive 硬规则

本任务正式 lifecycle 需要 NPU 0–7。driver 只在前置门通过后执行：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

成功、失败、中断或早退都必须恢复同一集合。服务器报告必须确认：

```text
stopped_card_ids=0,1,2,3,4,5,6,7
restored_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_count=16
keep_alive_restored_exact=true
port_7000_listener_count=0
vllm_residual_process_count=0
tracked_worktree_clean=true
```

不要在 driver 外手工停卡；若前置门失败，keep-alive 必须保持原样运行。

## 10. 分级

| grade | 条件 |
|---|---|
| `blocked_p6_3c_r2_f1_source_or_resource_gate` | 全局冲突、Git/资产/请求/真实源码/layout/overlay preflight/audit 任一前置门失败；未触 NPU |
| `red_p6_3c_r2_f1_runtime_overlay_preparation_no_success` | 已进入 lifecycle 后 overlay 准备仍失败；0 request |
| `red_p6_3c_r2_f1_startup_kv_capacity_no_success` | overlay 已完成，但 vLLM 因 KV capacity 未 ready；0 request |
| `red_p6_3c_r2_f1_scheduler_pressure_no_success` | 其他正式失败且无成功请求 |
| `yellow_p6_3c_r2_f1_scheduler_pressure_partial` | 有部分成功，但不足 6/6 lifecycle、90/90 request 或 48/48 batch |
| `red_p6_3c_r2_f1_scheduler_pressure_evidence_incomplete` | 工作量完成但单变量、layout、observer、repair、请求矩阵或必需证据不完整 |
| `candidate_green_p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_matched_ab` | 6/6、90/90、48/48、零 retry、layout/overlay、共同 repair、单开关、机制和性能轨道全完整 |
| `red_cleanup_incomplete` | 实际尝试生命周期的清理失败，或 keep-alive/残留进程/端口/tracked-clean 任一未恢复 |

未执行 lifecycle 的正确状态是 `not_run`，不单独触发 cleanup RED。即使 candidate green，
仍需开发机复核，不等于普遍性能收益。On 没出现预期 partial prefill 或性能没有改善时，
按真实证据分级，不得手改 JSON/TSV/grade。

## 11. 结果与回报

原始大文件必须留在：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01
```

重点检查：

```text
runtime_layout.json
runtime_overlay_preflight_manifest.json
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

每个已运行 lifecycle 的服务器本地目录还应有
`runtime/runtime_overlay_manifest.json`；raw vLLM log、scheduler trace、请求体和模型输出
不要放进 70KB 有界传输候选。

把 driver 输出的整个区间原样回复：

```text
P6_3C_R2_F1_SERVER_REPORT_BEGIN
...
P6_3C_R2_F1_SERVER_REPORT_END
```

并补充：

1. formal grade、首错阶段、是否在停卡前；
2. HEAD、origin/main、ahead/behind、tracked-clean；
3. 21 项仓库资产、七项真实源码、请求源与 audit-only 是否通过；
4. 解析出的真实 `vllm` / `vllm_ascend` 路径与 source kind；
5. preflight 的 materialized file/dir 数、symlink=0、escape=0、四类 patch method；
6. lifecycle attempted/ready/success、request/batch/scheduler step 实际/计划；
7. 每个启动 lifecycle 的 available/required KV、estimated max len；
8. Off/On argv SHA 和唯一 delta；
9. 两个压力 cell 的 partial-prefill/chunk/等待队列事实；
10. 性能轨道的 TTFT/E2EL/TPOT/ITL/批吞吐/完成差描述；
11. stopped/restored IDs、marker、端口、vLLM residual、tracked-clean；
12. result dir 与完整有界候选清单：path、bytes、SHA-256、sensitivity；
13. available methods=`email/upload-api/server-local` 与推荐方法、原因；
14. 是否有偏离。正确执行应为无参数调整、无 retry、无 server edit、无 wrapper、无下一任务。

## 12. 传输与停止边界

`result_transfer_authorized:true` 只表示有界包具备候选资格，不代表已选择渠道。先报告
完整 manifest，等待用户从 `email`、`upload-api`、`server-local` 中明确选择一个；
不得自动发送、不得先发状态邮件、不得拆包换渠道。单次正文和附件总量上限 70KB。

任务完成或任一失败后都停止，不进入 R2 run02、R1 重跑、K2、K3、P8.3、P8.4、
P8.5 或 P9。
