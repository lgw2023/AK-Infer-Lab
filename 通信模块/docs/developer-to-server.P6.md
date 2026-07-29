# 开发机 → Ascend 服务器交接任务（P6 专用）

## P6.3C-R2-F2 run01：loopback-proxy-safe Chunked Prefill matched A/B

```yaml
dispatch_revision: p6_3c_r2_f2_loopback_proxy_safe_2026_0730_r1
task_id: p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
run_id: p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
stage: P6.3C-R2-F2
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
server_side_code_edit_authorized: false
server_side_environment_edit_authorized: false
server_side_path_wrapper_authorized: false
retry_authorized: false
run02_authorized: false
next_task_authorized: false
```

本文件只管理 P6，不覆盖或消费 `通信模块/docs/developer-to-server.md` 中其他会话管理的
K2、K3 或其他任务。必须先由服务器全局协调确认没有其他任务正在使用、停止、恢复或
清理 NPU 0–7；若有 K2、K3、P8.3、P9、其他 P6、vLLM/NPU 作业或协调状态不明确，
立即停在零 NPU 互斥门并报告冲突。不要排队后自动续跑，不要杀掉别人的进程。

服务器助手不需要写代码、修补环境或猜测代理设置。本轮开发机已经把真实包布局解析、
task-local overlay、全部补丁、本地 HTTP 直连、六生命周期、请求、聚合、分级和恢复写进
唯一 driver。服务器只需同步远程 `main`、逐项核验、执行一次 audit、执行一次正式入口、
原样回报并停止。

## 1. 证据链：为什么这是 F2，不是 F1 重跑

四条历史结果必须独立保留：

1. 原 P6.3C 的 `blocked_p6_3c_not_strict_single_variable` 只证明原冻结
   `max_model_len=135168、max_num_batched_tokens=4096、max_num_seqs=1` 下 Off 侧
   不能启动，不代表 Chunked Prefill 无法研究。
2. P6.3C-R1 的共同 `69632/69632/2` 环境在 KV-cache 初始化阶段需要
   `36.66 GiB`、只有 `8.27 GiB` 可用，0 request、0 scheduler step；这是容量启动 RED。
3. P6.3C-R2 的 `12288/12288/2` run01 在 vLLM 启动前因 mixed editable/site-packages
   布局没有被旧 overlay 正确物化而停止，0 request；这是运行时布局准备失败。
4. P6.3C-R2-F1 已修好布局：服务器解析到 editable vLLM 与环境内 vLLM-Ascend，
   物化 `1644` 个文件且 `symlinks=0`、`escapes=0`，MTP、hybrid、deferred、observer
   路径通过，八个 TP worker 完成模型加载并出现 `Application startup complete`。
   但旧 health curl 继承服务器代理，访问 `127.0.0.1:7000` 得到代理侧 504；
   同一服务用 `curl --noproxy '*'` 返回 200。旧循环因此等待约 45 分钟，最终
   0/90 request、0/48 batch、0 scheduler step。

F1 接受的项目分类是：

```text
runner_local_loopback_proxy_failure_after_vllm_startup
```

它不是 Chunked Prefill、KV capacity、模型启动、调度或性能 RED。F1 的资源恢复为 clean：
NPU 0–7 keep-alive 精确恢复、16 marker、端口 7000 空闲、无 vLLM 残留、tracked-clean。
不得覆盖 F1 结果目录，不得创建 F1 run02，不得原样调用 F1 入口。

F1 报告中“deferred patch dry-run 失败后 apply skipped”的文字也不要据此修代码。
`runtime_overlay_preflight_manifest.json` 已记录实际 fallback method 为
`git_apply_ignore_whitespace`，说明标准 `patch -l` 因行尾差异失败后，`git apply
--ignore-whitespace` 的 check 与 apply 已成功；随后 vLLM 能启动也是直接佐证。

## 2. F2 改了什么、没有改什么

### 2.1 科学合同逐字继承 F1

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

三组同时到达的双请求不变：

| cell | 输入 | 总 Prefill tokens | 作用 |
|---|---:|---:|---|
| `no_pressure_4k_4k` | 4096 + 4096 | 8192 | 低于 12288 的无压力对照 |
| `asymmetric_pressure_10k_6k` | 10240 + 6144 | 16384 | 长短请求调度压力 |
| `symmetric_pressure_8k_8k` | 8192 + 8192 | 16384 | 对称调度压力 |

唯一 A/B 差异仍是：

```text
Off: --no-enable-chunked-prefill
On:  --enable-chunked-prefill
```

生命周期仍为：

```text
mechanism Off
mechanism On
performance Off
performance On
performance On
performance Off
```

总量仍为 6 个 fresh model lifecycle、90 个 engine request、48 个 batched HTTP call、
14 个 canonical body、每个输出固定 64 tokens、零 retry。不得改参数、cell、请求体、
顺序、重复数、repair、observer 边界或 A/B 开关。

### 2.2 唯一工程修复：本地 HTTP 全链路显式直连

mode runner 现在：

1. 对非 `HOST=127.0.0.1` fail closed；
2. 在任务子进程内给大小写 `NO_PROXY` 和 `no_proxy` 都补齐
   `127.0.0.1,localhost,::1`，不要求服务器手工改环境；
3. shell 的 readiness health、metrics preflight 和 cleanup health probe 均使用
   `curl --noproxy '*' --proxy ''`；
4. Python 的 health、metrics 和 `/v1/completions` streaming 请求统一经
   `ProxyHandler({})` 的 direct opener，并校验 URL 只能是
   `http://127.0.0.1:<port>`；
5. 每个 lifecycle 写 `loopback_transport_contract.json`，只记录代理变量名是否存在，
   永不记录代理 URL、账号、密码或变量值；
6. readiness 改为 900 秒总 deadline、2 秒单次 probe、5 秒轮询，并写
   `server_ready_probe_summary.tsv`，不再出现代理 5 秒 timeout 叠加 10 秒 sleep 的
   45 分钟假等待；
7. finalizer 汇总 `loopback_transport_summary.tsv`，F2 candidate 必须同时满足六个
   lifecycle 的 direct-loopback transport gate。

服务器不得手工 unset/改写 proxy 环境，不得创建临时 wrapper，不得改 host/port，
不得用一次手工 curl 成功来替代 driver。

## 3. 固定路径与版本

```bash
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
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

## 4. 零 NPU 全局互斥门

先查服务器全局任务协调信息，再只读检查：

```bash
pgrep -af '[r]un_deepseek.*(server_task|scheduler_pressure)|[v]llm.*serve|[n]pu_stop.sh' || true
ss -ltnp | grep -E ':(7000|8000|8001|9000)\b' || true
```

低优先级 keep-alive 正常存在不算冲突。任何实验 driver、vLLM 服务、停/复卡操作、
端口占用、其他任务仍在清理或协调状态不明都算冲突。报告后停止；不要抢卡、杀进程或
等待后自动执行。本节失败时不得运行后续命令。

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

不得 stash、merge、rebase、commit、push、删除旧结果或编辑 tracked 文件。

## 6. 23 项仓库资产门

同步后逐项核对 bytes 与 SHA-256。任一不符，在零 NPU 阶段停止，不得修一下再跑。

| # | 文件 | bytes | SHA-256 |
|---:|---|---:|---|
| 1 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f2_server_task.sh` | 740 | `8bef1dec252dc053c2f7012b3cca54b3b6ad54ddfe1e96f4587b9a79d2506fad` |
| 2 | `tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh` | 5205 | `0f2e724ea75ac2ceccd364469def494da8aedf7c3eca49031d207ba2e94cdae6` |
| 3 | `tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh` | 10380 | `a6d26058491edcbad64b95a582126e4e0730ab0e01a4893d799f4e3468dce23d` |
| 4 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh` | 4257 | `d5f07ff8fc894ee6b5c4f53d2d07cf03f46d57c481243c198d334e6c4aad0826` |
| 5 | `tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh` | 562 | `108a9fc218ad43694ee7ae3dfceea37ea8837333f66cd9ca90858a084fa6cea1` |
| 6 | `tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh` | 19092 | `65afb89c7c30bc993e8e7c316f4744dbbbee54f0cbca1d956170285401d836ae` |
| 7 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py` | 31073 | `7dbd476c8604acf97ab4f7e7bf6da11fd4eff01844b6c73cca256a8a3d372598` |
| 8 | `tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py` | 62978 | `d5df3d33f611851332b4c89466591f3345ad872fc9347be96359001718c221c1` |
| 9 | `tools/inference_contracts/p6_3c_local_http_transport.py` | 3503 | `3e167ac892d1b64e3e03a41e6802ee734d0b4de24ceb59cbb3fc6423dbc4d70e` |
| 10 | `tools/inference_contracts/resolve_p6_3c_runtime_layout.py` | 4663 | `a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897` |
| 11 | `tools/inference_contracts/prepare_p6_3c_runtime_overlay.py` | 11757 | `9086250e6b6b879071b0db60eefc873aee5c8dffe77a0e5f28aa40bd72ce6411` |
| 12 | `tools/inference_contracts/p6_3c_startup_resource_summary.py` | 5009 | `b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a` |
| 13 | `tools/inference_contracts/p6_3c_r1_scheduler_observer.py` | 7251 | `c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4` |
| 14 | `tools/inference_contracts/canonicalize_server_argv.py` | 1238 | `c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d` |
| 15 | `tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py` | 10250 | `6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c` |
| 16 | `tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py` | 2733 | `9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631` |
| 17 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f2_loopback_proxy_safe_matched_ab.yaml` | 4174 | `31aa1a09fabee527376e0323777e4457302a8dd8a3fba8ae6eb8fc4e2caaca80` |
| 18 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f1_runtime_layout_portable_matched_ab.yaml` | 3564 | `3ecbe5d5a67b4047b308669ae36578739a08a78226aeab0957737acfad394d3c` |
| 19 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml` | 10881 | `475fb070c6904e31b9e1dfdb1209f1c088d490fbaf618417eea59d83e23c32ec` |
| 20 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch` | 769 | `75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1` |
| 21 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch` | 830 | `2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f` |
| 22 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch` | 1054 | `cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e` |
| 23 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch` | 896 | `ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b` |

可用以下只读循环核对：

```bash
while IFS='|' read -r asset expected_bytes expected_sha; do
  test -f "${asset}"
  actual_bytes=$(stat -c '%s' "${asset}")
  actual_sha=$(sha256sum "${asset}" | awk '{print $1}')
  printf '%s\t%s\t%s\n' "${asset}" "${actual_bytes}" "${actual_sha}"
  test "${actual_bytes}" = "${expected_bytes}"
  test "${actual_sha}" = "${expected_sha}"
done <<'EOF'
tools/inference_contracts/run_deepseek_p6_3c_r2_f2_server_task.sh|740|8bef1dec252dc053c2f7012b3cca54b3b6ad54ddfe1e96f4587b9a79d2506fad
tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh|5205|0f2e724ea75ac2ceccd364469def494da8aedf7c3eca49031d207ba2e94cdae6
tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh|10380|a6d26058491edcbad64b95a582126e4e0730ab0e01a4893d799f4e3468dce23d
tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh|4257|d5f07ff8fc894ee6b5c4f53d2d07cf03f46d57c481243c198d334e6c4aad0826
tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh|562|108a9fc218ad43694ee7ae3dfceea37ea8837333f66cd9ca90858a084fa6cea1
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh|19092|65afb89c7c30bc993e8e7c316f4744dbbbee54f0cbca1d956170285401d836ae
tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py|31073|7dbd476c8604acf97ab4f7e7bf6da11fd4eff01844b6c73cca256a8a3d372598
tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py|62978|d5df3d33f611851332b4c89466591f3345ad872fc9347be96359001718c221c1
tools/inference_contracts/p6_3c_local_http_transport.py|3503|3e167ac892d1b64e3e03a41e6802ee734d0b4de24ceb59cbb3fc6423dbc4d70e
tools/inference_contracts/resolve_p6_3c_runtime_layout.py|4663|a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897
tools/inference_contracts/prepare_p6_3c_runtime_overlay.py|11757|9086250e6b6b879071b0db60eefc873aee5c8dffe77a0e5f28aa40bd72ce6411
tools/inference_contracts/p6_3c_startup_resource_summary.py|5009|b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a
tools/inference_contracts/p6_3c_r1_scheduler_observer.py|7251|c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4
tools/inference_contracts/canonicalize_server_argv.py|1238|c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d
tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py|10250|6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py|2733|9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f2_loopback_proxy_safe_matched_ab.yaml|4174|31aa1a09fabee527376e0323777e4457302a8dd8a3fba8ae6eb8fc4e2caaca80
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f1_runtime_layout_portable_matched_ab.yaml|3564|3ecbe5d5a67b4047b308669ae36578739a08a78226aeab0957737acfad394d3c
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml|10881|475fb070c6904e31b9e1dfdb1209f1c088d490fbaf618417eea59d83e23c32ec
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch|769|75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch|830|2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch|1054|cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch|896|ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
EOF
```

特别确认第 20 项 MTP patch 的正确 SHA 中段是 `...f261a3...`，不要写成
历史交接 typo `...f262a3...`。

## 7. 目标环境与冻结源码门

23 项仓库资产通过后，正式入口会在停 keep-alive 前自动：

1. 用目标环境 Python 的 `importlib.find_spec + realpath` 解析真实 `vllm` 和
   `vllm_ascend` 包目录；
2. 核对下列七个真实源文件 SHA；
3. 物化 disposable overlay，要求 symlink=0、realpath escape=0；
4. dry-run/apply MTP、hybrid manager、deferred install、observer patch 并核
   post-patch hash。

冻结源码 SHA：

```text
vllm/v1/core/single_type_kv_cache_manager.py
d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1

vllm/v1/core/kv_cache_coordinator.py
a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89

vllm_ascend/patch/platform/patch_kv_cache_coordinator.py
dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20

vllm_ascend/patch/platform/patch_kv_cache_interface.py
a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2

vllm_ascend/spec_decode/llm_base_proposer.py
0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

vllm_ascend/distributed/kv_transfer/__init__.py
dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1

vllm/v1/core/sched/scheduler.py
41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983
```

不要创建 `/tmp/p6_3c_r2_env_prefix`，不要导出 `BASE_PLUGIN_ROOT` /
`BASE_VLLM_ROOT`，不要编辑 site-packages 或 editable checkout。

## 8. 零 NPU audit-only

只有 §4–§7 全过且 `RESULT_DIR` 不存在时执行：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r2_f2_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
```

audit-only 不停 keep-alive、不创建结果目录。必须看到：

```text
task_id=p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
expected_result_basename=p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
formal_model_lifecycle_count_exact=6
engine_request_count_exact=90
batched_http_call_count_exact=48
request_retry_count_exact=0
capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_2
shared_hybrid_kv_repair=enabled_both_modes_all_lifecycles
```

六个 lifecycle 均必须输出：

```text
experiment_label=P6_3C_R2_F2
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=2
prefix_cache=false
shared_hybrid_kv_repair=1
local_http_host=127.0.0.1
shell_local_http_proxy=explicitly_disabled
python_local_http_proxy_handler=empty
loopback_no_proxy_env=NO_PROXY_and_no_proxy
```

canonical argv 必须仍为：

```text
Off SHA-256=568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10
On  SHA-256=cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017
唯一 delta=--no-enable-chunked-prefill ↔ --enable-chunked-prefill
```

audit 后再次确认 HEAD 未漂移、tracked-clean、全局仍无冲突。任一不符停止。

## 9. 正式执行：只允许一次

执行唯一命令：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
bash tools/inference_contracts/run_deepseek_p6_3c_r2_f2_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
```

入口先在零 NPU 阶段完成布局、七项源码 SHA、overlay 和补丁预检。预期看到：

```text
runtime_layout_resolved:vllm=...:vllm_ascend=...
runtime_overlay_prepared:files=<positive>:symlinks=0:escapes=0
```

若出现 `P6_3C_RUNTIME_OVERLAY_PREFLIGHT_BLOCKED`，原样回报并停止；此时不应停卡或创建
结果目录。不要手工修路径，不要再次调用。

预检通过后，基础 driver 才停止 0–7 keep-alive，并依次运行六个 lifecycle。每个
lifecycle 应生成：

```text
runtime/loopback_transport_contract.json
runtime/server_ready_probe_summary.tsv
runtime/startup_resource_summary.json
runtime/runtime_overlay_manifest.json
runtime/server_argv.json
```

`loopback_transport_contract.json` 必须满足：

```text
base_url=http://127.0.0.1:7000
loopback_url_validated=true
shell_curl_noproxy_all=true
shell_curl_empty_proxy=true
python_proxy_handler=empty
python_environment_proxy_lookup_allowed=false
NO_PROXY_loopback_entries_complete=true
no_proxy_loopback_entries_complete=true
environment_proxy_values_recorded=false
```

`environment_proxy_variable_names_present` 可以非空，这恰好证明服务器存在代理环境；
只要值不被记录、所有本地客户端显式直连即可。不要为了让该列表为空而改环境。

不要手工调用 mode runner、Python runner、curl 或 finalizer，不要补跑缺失 lifecycle，
不要创建第二 attempt。

## 10. keep-alive 硬规则

正式任务需要 NPU 0–7。driver 只在前置门通过后执行：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

成功、失败、中断和早退都必须恢复同一卡集。报告必须确认：

```text
stopped_card_ids=0,1,2,3,4,5,6,7
restored_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_count=16
keep_alive_restored_exact=true
port_7000_listener_count=0
vllm_residual_process_count=0
tracked_worktree_clean=true
```

不要在 driver 外手工停卡。若前置门失败，keep-alive 保持原样运行。

## 11. 分级与停止条件

| grade | 条件 |
|---|---|
| `blocked_p6_3c_r2_f2_source_or_resource_gate` | 全局冲突、Git/资产/请求/源码/layout/overlay/audit 任一前置门失败；未触 NPU |
| `red_p6_3c_r2_f2_runtime_overlay_preparation_no_success` | 已进入 lifecycle 后 overlay 准备失败；0 request |
| `red_p6_3c_r2_f2_startup_kv_capacity_no_success` | overlay 完成，但 vLLM 因 KV capacity 未 ready；0 request |
| `red_p6_3c_r2_f2_server_not_ready_after_loopback_proxy_isolation` | transport contract 已建立，但 vLLM 仍未 ready；不得再归因为旧 proxy |
| `red_p6_3c_r2_f2_scheduler_pressure_no_success` | 其他正式失败且无成功请求 |
| `yellow_p6_3c_r2_f2_scheduler_pressure_partial` | 有部分成功，但不足 6/6 lifecycle、90/90 request 或 48/48 batch |
| `red_p6_3c_r2_f2_scheduler_pressure_evidence_incomplete` | 工作量完成但单变量、transport、layout、observer、repair、请求矩阵或必需证据不完整 |
| `candidate_green_p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_matched_ab` | 6/6、90/90、48/48、零 retry、六条 transport、layout/overlay、共同 repair、单开关、机制和性能轨道完整 |
| `red_cleanup_incomplete` | keep-alive、残留进程、端口、tracked-clean 或实际尝试 lifecycle 清理未恢复 |

未执行 lifecycle 的正确状态是 `not_run`，不单独触发 cleanup RED。On 没出现预期
partial prefill、短请求 TTFT 没改善或吞吐下降，都必须按真实数据报告；不得为了得到
candidate green 手改 JSON/TSV/grade。candidate 也只表示候选，仍需开发机逐文件复核，
不等于普遍收益、统计显著性或生产吞吐结论。

## 12. 结果重点与回报格式

原始大文件留在：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01
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
loopback_transport_summary.tsv
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

raw vLLM log、scheduler trace、请求体、逐请求明细和模型输出只留服务器，不放进 70KB
有界候选。

把 driver 输出的整个区间原样回复：

```text
P6_3C_R2_F2_SERVER_REPORT_BEGIN
...
P6_3C_R2_F2_SERVER_REPORT_END
```

并补齐以下信息：

1. formal grade、首错阶段、是否发生在停卡前；
2. HEAD、origin/main、ahead/behind、tracked-clean；
3. 23 项仓库资产、七项真实源码、19487-byte 请求源、audit 是否全过；
4. 真实 `vllm` / `vllm_ascend` 路径与 source kind；
5. preflight file/dir 数、symlink/escape、四类 patch method；deferred 若为
   `git_apply_ignore_whitespace`，明确写 fallback applied，不要写 skipped；
6. 每个 lifecycle 的 attempted/ready/exit/cleanup、readiness attempts/elapsed；
7. transport summary 六行是否完整，以及存在的代理变量名；不得报告代理值；
8. request/batch/scheduler step 成功数与计划数；
9. 各启动 lifecycle 的 available/required KV、estimated max len、GPU KV tokens；
10. Off/On argv SHA 和唯一 delta；
11. 机制轨道三 cell 的 scheduled token、partial prefill、chunk、waiting/running 次序；
12. 性能轨道 TTFT、E2EL、TPOT、ITL、批吞吐和双请求完成时间差；
13. stopped/restored IDs、marker、端口、vLLM residual、tracked-clean；
14. result dir、完整有界候选清单：path、bytes、SHA-256、sensitivity；
15. available methods=`email/upload-api/server-local`、推荐方法和原因；
16. 是否有偏离。正确执行应为无代码/环境/参数修改、无 retry、无 wrapper、无下一任务。

若首个 lifecycle 失败，仍要让 driver 完成全局恢复、finalize 和 package；后续生命周期
保持 `not_run`。不要手动伪造缺失结果。

## 13. 70KB 传输与最终停止边界

finalizer 的有界候选应为最多 16 个小文件，总量必须 `<=71680 bytes`：

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
startup_resource_summary.tsv
loopback_transport_summary.tsv
runtime_layout.json
runtime_overlay_preflight_manifest.json
cleanup_status.txt
first_failure_excerpt.txt
```

`result_transfer_authorized:true` 仅表示该完整有界包有资格被选择，不表示已经选定渠道。
先报告 `candidate_manifest.server_local.json` 的完整清单、总 bytes、逐文件 SHA、敏感性、
可用方法与推荐理由，然后等待用户明确选择一个完整范围：

```text
email
upload-api
server-local
```

不得自动发送、不得先发状态邮件、不得拆包、不得失败后自动换渠道。若选择
`upload-api`，一次 named multi-file session 提交全部批准文件；若选择 `email`，
result summary 作正文且批准附件同一封发送；任何 401/409/413、proxy/redirect、timeout、
service 或 hash validation 失败都必须停止并请求新的用户选择。

正式 run01 完成或任一失败后停止，不进入 F2 run02、F1/R2/R1 重跑、K2、K3、
P8.3、P8.4、P8.5 或 P9。
