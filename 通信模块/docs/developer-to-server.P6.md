# 开发机 → Ascend 服务器交接任务（P6 专用）

## P6.3C-R2-F4 run01：request-ID-normalized atomic co-arrival matched A/B

```yaml
dispatch_revision: p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_r1
task_id: p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
run_id: p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
stage: P6.3C-R2-F4
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

本文件只管理 P6，不覆盖、消费或执行 `通信模块/docs/developer-to-server.md` 中其他会话
管理的 K2、K3、P8.3、P9 或其他任务。必须先由服务器全局协调确认没有其他任务正在使用、
停止、恢复或清理 NPU 0–7。若有 K2、K3、P8.3、P9、其他 P6、任何其他实验、
vLLM/NPU 作业、端口占用或协调状态不明确，停在零 NPU 互斥门并报告；不要排队后自动
续跑，不要杀掉别人的进程。

服务器助手不需要写代码、猜测请求 ID、修改 site-packages、补环境变量、创建 wrapper
或人工拼 grade。开发机已经把 F3 实机实际 ID 样例、严格规范化、task-local barrier、
release/scheduler 双轨核验、终态 checkpoint、六生命周期、分级、清理和有界打包写入
唯一 driver。服务器只需 fast-forward 同步远程 `main`、核验事实、运行一次零 NPU
audit、运行一次正式入口、原样回报，然后停止。

## 1. F3 是有效 RED，但不是 Chunked Prefill 负结论

以下历史链全部保留，不得覆盖或重跑：

1. 原 P6.3C 的 `blocked_p6_3c_not_strict_single_variable` 只证明冻结
   `135168/4096/1` 下 Off 侧不能启动。
2. R1 的 `69632/69632/2` 在 KV-cache 初始化失败，0 request。
3. R2、F1 依次暴露 mixed-install overlay 与 loopback proxy 控制面问题。
4. F2 完成 6 lifecycle、90/90 request、48/48 batch，但两个 request 分处相邻
   scheduler step，没有制造同轮预算竞争。
5. F3 共同加入 atomic pair admission，并完成 6 lifecycle、90/90 request、
   48/48 batch、六次 ready、零 retry；所有运行时、argv、请求、资源和清理门通过。

F3 正式 grade：

```text
red_p6_3c_r2_f3_atomic_pair_admission_evidence_incomplete
```

F3 的直接根因不是硬件、容量、代理、模型、cleanup 或 Chunked Prefill：

```text
controller parser 预期：
  cmpl-p6_3c_r2_f3_...-0
  cmpl-p6_3c_r2_f3_...-1

服务器实际 vLLM scheduler ID：
  cmpl-p6_3c_r2_f3_mechanism_no_pressure_4k_4k_r01-0-a19f074f
  cmpl-p6_3c_r2_f3_mechanism_no_pressure_4k_4k_r01-1-94c2f491
```

vLLM 在 canonical member index 后追加 8 位小写十六进制运行时后缀。F3 parser 用
`rpartition("-")` 读取到的是随机后缀，不是 `0/1`，因此 42 个 measured pair 全部绕过
barrier：controller 虽安装，release=0/42、机制首轮合同=0/6。F3 finalizer 还用无后缀
canonical ID 对 release、waiting 和 scheduled map 做 exact equality，所以只修 runtime
parser 仍会在分析侧第二次误判。

F3 另有一个 lifecycle 未留下 shutdown callback trace，但 0–7 keep-alive、端口、
vLLM 残留和 worktree 全部 clean。这要求可靠的终态证据后备，不允许把“少一条 shutdown
trace”误写成“pair 未释放”。

不得创建 F3 run02，不得覆盖 F3 结果目录，不得把 F3 性能数据解释成 controlled
co-arrival 下的 Chunked Prefill 结果。

## 2. F4 修复内容与冻结科学合同

F4 是独立结果链，只共同修复两侧相同的请求 ID 控制面：

1. 只接受严格 actual ID：
   `cmpl-<F4 canonical pair key>-<0|1>-<8 lowercase hex>`。
2. 每个识别结果同时保存：
   `actual_request_id`、`canonical_request_id`、`pair_key`、`pair_index`、
   `runtime_suffix`。
3. 错误前缀、错误 member index、缺失后缀、非 8 位小写 hex 后缀一律不进入 barrier。
4. controller 按 canonical pair 聚合，但调用原 `EngineCore.add_request` 时保留 actual ID；
   第二个 member 到达后按 0→1 连续释放。
5. release trace 明确保存 actual/canonical 两套 ID；finalizer 会重新从 actual ID 独立
   规范化，再与 trace canonical 和冻结 run plan 三方核对。
6. scheduler observer 的 `waiting_order_before` 和 `scheduled_requests` 也先验证 actual ID，
   再按 canonical ID 对照首轮 token 合同；两条证据轨道共用一个规范。
7. 每次 pair 状态变化写持久 state checkpoint。终态优先使用 shutdown；若该 callback
   trace 缺失，只接受最后一个 `pair_complete_released` checkpoint，且必须同时满足
   expected completed count、`pending=0`、`failed=0`、全部 exact release、零 failure
   event 和全局 clean。

F4 不改 Scheduler 和 Chunked Prefill 实现，不改请求 token，不改服务参数。两侧共同冻结：

```text
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=2
Prefix Cache=false（显式）
同一 validated deferred hybrid-KV task-local repair
同一 request-ID-normalized atomic pair admission
atomic pair timeout=30 seconds
MTP num_speculative_tokens=1
TP8 + EP
W8A8 ascend quantization
block_size=128
gpu_memory_utilization=0.92
FULL_DECODE_ONLY
async scheduling=true
模型、graph、请求体、重复数和顺序完全一致
```

唯一 A/B 差异：

```text
Off: --no-enable-chunked-prefill
On:  --enable-chunked-prefill
```

三个 cell 的首个相关 scheduler step 必须精确满足：

| cell | canonical waiting_order_before | Off scheduled tokens | On scheduled tokens |
|---|---|---:|---:|
| 4K+4K | request 0, request 1 | 4096 + 4096 | 4096 + 4096 |
| 10K+6K | request 0, request 1 | 10240 + 0 | 10240 + 2048 |
| 8K+8K | request 0, request 1 | 8192 + 0 | 8192 + 4096 |

机制轨道要求 Off 三组无 partial prefill、On 两个压力组有 partial prefill、4K+4K 两侧
均无 partial。性能轨道仍关闭 scheduler observer 和 profiler，顺序
Off→On→On→Off；TTFT、E2EL、TPOT、ITL、batch throughput、完成时间差和 barrier wait
只作共同受控 co-arrival 环境内描述，不外推自然生产 API 流量。

精确总量：

```text
fresh model lifecycles=6
engine requests=90
batched HTTP calls=48
canonical request bodies=14
tagged measured pairs=42
request retries=0
```

## 3. 固定路径

```bash
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ENV_PREFIX=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
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

先查服务器全局协调状态，再只读检查：

```bash
pgrep -af '[r]un_deepseek.*(server_task|scheduler_pressure)|[v]llm.*serve|[n]pu_stop.sh' || true
ss -ltnp | grep -E ':(7000|8000|8001|9000)\b' || true
```

低优先级 keep-alive 正常存在不算冲突。任何其他 driver、vLLM 服务、停/复卡操作、
端口占用、任务仍在清理或协调状态不明都算冲突。报告后停止；不要抢卡、杀进程或等待后
自动执行。本节失败时不得继续正式命令。

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
git merge-base --is-ancestor 2893747765c63c7c6891a1b45e7b32352704f4ed HEAD
test ! -e /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
```

必须同时满足：

```text
branch=main
HEAD=origin/main
ahead/behind=0/0
tracked-clean=true
F3 发布提交 2893747... 是当前 HEAD 祖先
F4 RESULT_DIR 不存在
```

不得 stash、merge、rebase、commit、push、删除旧结果或编辑 tracked 文件。

## 6. 28 项仓库资产门

同步后逐项核对 bytes 与 SHA-256。任一不符，在零 NPU 阶段停止，不得修改后继续。

| # | 文件 | bytes | SHA-256 |
|---:|---|---:|---|
| 1 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f4_server_task.sh` | 2431 | `76aa5da552078f02a25b6f88409d1dd49a825fe09fda8397be38957808dc72d2` |
| 2 | `tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh` | 6277 | `38f6a4a44feb606ae2a8d4d2d64ab838a09ebc9691a2bda2699a3d92dab2baae` |
| 3 | `tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh` | 10380 | `a6d26058491edcbad64b95a582126e4e0730ab0e01a4893d799f4e3468dce23d` |
| 4 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f4_scheduler_pressure.sh` | 1314 | `1389681e4cbeaccb9e2d72bee6faf90e066cf2675475d885a19b28519057546b` |
| 5 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh` | 4631 | `dc5532c32490cea2ecc994f28d0bcb1db65e71a255fcd10579cc70c40a116a9c` |
| 6 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f4_mode.sh` | 1076 | `7ae6b46e93c12590bed63d287d690b4e2142c69db1cbd34df7dd38a1f0890eb1` |
| 7 | `tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh` | 562 | `108a9fc218ad43694ee7ae3dfceea37ea8837333f66cd9ca90858a084fa6cea1` |
| 8 | `tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh` | 23080 | `148d9ebc67d6c48417b7a88b2e7d4779326a5091a642b57d2e627cda7b6543b6` |
| 9 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f4_atomic_pair_admission.py` | 31563 | `98bdefed22613910e784b87f720d2fc59d7fdf008fb08c4044d86709b14adb06` |
| 10 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f3_atomic_pair_admission.py` | 24151 | `722d992052fb675598f44dd8523621c614bdf35eefd9602e1938170e819f2b93` |
| 11 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py` | 32996 | `0b2f93ae7cb0d1b98a99ff3e635ef2a48829a22a674cc4048cba475a518b6eed` |
| 12 | `tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py` | 62978 | `d5df3d33f611851332b4c89466591f3345ad872fc9347be96359001718c221c1` |
| 13 | `tools/inference_contracts/p6_3c_r2_f4_atomic_pair_admission.py` | 15978 | `6cf48b4f96d779a108bac30aba46bf075ba5e72fd39526d76f9699c1b3ee4a9d` |
| 14 | `tools/inference_contracts/p6_3c_local_http_transport.py` | 3503 | `3e167ac892d1b64e3e03a41e6802ee734d0b4de24ceb59cbb3fc6423dbc4d70e` |
| 15 | `tools/inference_contracts/resolve_p6_3c_runtime_layout.py` | 4663 | `a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897` |
| 16 | `tools/inference_contracts/prepare_p6_3c_runtime_overlay.py` | 13582 | `c99966e955b09c70b2b66eb654603b22be9034dd218028b2be9ff1eb222a8a3c` |
| 17 | `tools/inference_contracts/p6_3c_startup_resource_summary.py` | 5009 | `b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a` |
| 18 | `tools/inference_contracts/p6_3c_r1_scheduler_observer.py` | 7251 | `c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4` |
| 19 | `tools/inference_contracts/canonicalize_server_argv.py` | 1238 | `c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d` |
| 20 | `tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py` | 10250 | `6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c` |
| 21 | `tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py` | 2733 | `9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631` |
| 22 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_matched_ab.yaml` | 7524 | `0ffcccee719dceab21ce1f3ac893e144a4adf5870cf11db25ad526afb3d9a520` |
| 23 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f3_atomic_pair_admission_matched_ab.yaml` | 6310 | `fa4c5c6c100a4a2f40d52ac585ac0a03e4afff7099fdcb3161235a574d1a3920` |
| 24 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch` | 769 | `75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1` |
| 25 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch` | 830 | `2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f` |
| 26 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r2_f4_atomic_pair_admission_overlay.patch` | 822 | `e25c247af17fd729293509fc0aa0d216fa38e3d56f59c552874830a9e8687913` |
| 27 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch` | 1054 | `cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e` |
| 28 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch` | 896 | `ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b` |

只读核验命令：

```bash
while IFS='|' read -r asset expected_bytes expected_sha; do
  test -f "${asset}"
  actual_bytes=$(stat -c '%s' "${asset}")
  actual_sha=$(sha256sum "${asset}" | awk '{print $1}')
  printf '%s\t%s\t%s\n' "${asset}" "${actual_bytes}" "${actual_sha}"
  test "${actual_bytes}" = "${expected_bytes}"
  test "${actual_sha}" = "${expected_sha}"
done <<'EOF'
tools/inference_contracts/run_deepseek_p6_3c_r2_f4_server_task.sh|2431|76aa5da552078f02a25b6f88409d1dd49a825fe09fda8397be38957808dc72d2
tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh|6277|38f6a4a44feb606ae2a8d4d2d64ab838a09ebc9691a2bda2699a3d92dab2baae
tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh|10380|a6d26058491edcbad64b95a582126e4e0730ab0e01a4893d799f4e3468dce23d
tools/inference_contracts/run_deepseek_p6_3c_r2_f4_scheduler_pressure.sh|1314|1389681e4cbeaccb9e2d72bee6faf90e066cf2675475d885a19b28519057546b
tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh|4631|dc5532c32490cea2ecc994f28d0bcb1db65e71a255fcd10579cc70c40a116a9c
tools/inference_contracts/run_deepseek_p6_3c_r2_f4_mode.sh|1076|7ae6b46e93c12590bed63d287d690b4e2142c69db1cbd34df7dd38a1f0890eb1
tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh|562|108a9fc218ad43694ee7ae3dfceea37ea8837333f66cd9ca90858a084fa6cea1
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh|23080|148d9ebc67d6c48417b7a88b2e7d4779326a5091a642b57d2e627cda7b6543b6
tools/inference_contracts/run_deepseek_p6_3c_r2_f4_atomic_pair_admission.py|31563|98bdefed22613910e784b87f720d2fc59d7fdf008fb08c4044d86709b14adb06
tools/inference_contracts/run_deepseek_p6_3c_r2_f3_atomic_pair_admission.py|24151|722d992052fb675598f44dd8523621c614bdf35eefd9602e1938170e819f2b93
tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py|32996|0b2f93ae7cb0d1b98a99ff3e635ef2a48829a22a674cc4048cba475a518b6eed
tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py|62978|d5df3d33f611851332b4c89466591f3345ad872fc9347be96359001718c221c1
tools/inference_contracts/p6_3c_r2_f4_atomic_pair_admission.py|15978|6cf48b4f96d779a108bac30aba46bf075ba5e72fd39526d76f9699c1b3ee4a9d
tools/inference_contracts/p6_3c_local_http_transport.py|3503|3e167ac892d1b64e3e03a41e6802ee734d0b4de24ceb59cbb3fc6423dbc4d70e
tools/inference_contracts/resolve_p6_3c_runtime_layout.py|4663|a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897
tools/inference_contracts/prepare_p6_3c_runtime_overlay.py|13582|c99966e955b09c70b2b66eb654603b22be9034dd218028b2be9ff1eb222a8a3c
tools/inference_contracts/p6_3c_startup_resource_summary.py|5009|b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a
tools/inference_contracts/p6_3c_r1_scheduler_observer.py|7251|c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4
tools/inference_contracts/canonicalize_server_argv.py|1238|c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d
tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py|10250|6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py|2733|9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_matched_ab.yaml|7524|0ffcccee719dceab21ce1f3ac893e144a4adf5870cf11db25ad526afb3d9a520
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f3_atomic_pair_admission_matched_ab.yaml|6310|fa4c5c6c100a4a2f40d52ac585ac0a03e4afff7099fdcb3161235a574d1a3920
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch|769|75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch|830|2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r2_f4_atomic_pair_admission_overlay.patch|822|e25c247af17fd729293509fc0aa0d216fa38e3d56f59c552874830a9e8687913
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch|1054|cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch|896|ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
EOF

test -x tools/inference_contracts/run_deepseek_p6_3c_r2_f4_server_task.sh
test -x tools/inference_contracts/run_deepseek_p6_3c_r2_f4_scheduler_pressure.sh
test -x tools/inference_contracts/run_deepseek_p6_3c_r2_f4_mode.sh
```

特别确认 MTP patch SHA 中段是 `...f261a3...`，不是历史 typo `...f262a3...`。

## 7. 冻结安装源码、overlay 与实际 ID fixture 门

28 项仓库资产通过后，正式入口会在停 keep-alive 前自动用目标环境 Python 的
`importlib.find_spec + realpath` 解析真实包路径，并核对：

```text
vllm/v1/core/single_type_kv_cache_manager.py
d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1

vllm/v1/core/kv_cache_coordinator.py
a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89

vllm/v1/core/sched/scheduler.py
41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983

vllm/v1/engine/core.py
282e53b0f25d1ca05d977643d5b681316779b55ebfc360976ea2e95b464f4ea1

vllm_ascend/spec_decode/llm_base_proposer.py
0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

vllm_ascend/distributed/kv_transfer/__init__.py
dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1

vllm_ascend/patch/platform/patch_kv_cache_coordinator.py
dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20

vllm_ascend/patch/platform/patch_kv_cache_interface.py
a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2
```

driver 会物化 disposable overlay，要求 symlink=0、realpath escape=0、不修改 base
environment/site-packages，并在停卡前 dry-run/apply MTP、hybrid、deferred、F4 atomic
admission 和 observer patch。F4 controller 会被复制为明确模块
`p6_3c_r2_f4_atomic_pair_admission.py`，不得再伪装成 F3 模块名。

F4 顶层入口还会在停卡前自动用以下 F3 实机形态做 parser fixture：

```text
cmpl-p6_3c_r2_f4_mechanism_no_pressure_4k_4k_r01-0-a19f074f
```

必须输出：

```text
request_id_fixture_gate=observed_8hex_suffix_normalized_strict
```

不要创建 `/tmp/p6_3c_r2_env_prefix`，不要手工导出路径，不能编辑安装源码。

## 8. 零 NPU audit-only

只有 §4–§7 全过且结果目录不存在时执行：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r2_f4_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
```

audit-only 不停 keep-alive、不创建结果目录。必须看到：

```text
request_id_fixture_gate=observed_8hex_suffix_normalized_strict
task_id=p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
formal_model_lifecycle_count_exact=6
engine_request_count_exact=90
batched_http_call_count_exact=48
request_retry_count_exact=0
capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_2
atomic_pair_admission=1
atomic_pair_admission_module=p6_3c_r2_f4_atomic_pair_admission
atomic_pair_request_prefix=p6_3c_r2_f4
atomic_pair_timeout_seconds=30
tagged_measured_pair_count_exact=42
shared_hybrid_kv_repair=enabled_both_modes_all_lifecycles
```

六个 lifecycle 都必须输出 F4 prefix。Off 三次 argv SHA 必须全为：

```text
568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10
```

On 三次必须全为：

```text
cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017
```

唯一 argv 差异必须仍是位置 28：

```text
--no-enable-chunked-prefill
--enable-chunked-prefill
```

audit 失败立即停止；不得修后接着跑。

## 9. 唯一正式执行与 keep-alive

再次确认全局无冲突。F4 需要 NPU 0–7，只允许停止这八张卡的低优先级 keep-alive：

```bash
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
```

随后只运行一次：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
bash tools/inference_contracts/run_deepseek_p6_3c_r2_f4_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
```

无论成功、RED、异常、中断或早退，都必须恢复完全相同的卡集：

```bash
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

必须确认：

```text
stopped_card_ids=0,1,2,3,4,5,6,7
restored_card_ids=0,1,2,3,4,5,6,7
keep_alive_restored_exact=true
port_7000_listener_count=0
vllm_residual_process_count=0
tracked_worktree_clean=true
```

禁止 retry、run02、参数 sweep、手工补跑 lifecycle、F3 run02 或下一个任务。

## 10. 结果判定

candidate 必须同时满足：

```text
6/6 lifecycle success
90/90 request success
48/48 batch success
0 retry
6/6 startup/transport/layout/overlay/repair gate
7/7 preflight+lifecycle overlay manifest 均绑定 F4 admission module
request_id_normalization_gate_complete=true
42/42 exact pair release
0 atomic failure event
6/6 clean terminal state（shutdown 或严格 final post-release checkpoint）
6/6 mechanism first-step contract exact
coarrival_gate_complete=true
Off 三 cell partial prefill absent
On 两个压力 cell partial prefill present
4K+4K 两侧 partial prefill absent
global cleanup clean
keep-alive exact restore
```

candidate grade：

```text
candidate_green_p6_3c_r2_f4_chunked_prefill_request_id_normalized_atomic_coarrival_matched_ab
```

若 full execution 但 ID/release/terminal/first-step 任一不完整：

```text
red_p6_3c_r2_f4_atomic_pair_admission_evidence_incomplete
```

若 ID、release 和 co-arrival 均成立，但 Chunked Prefill 预期机制不完整：

```text
red_p6_3c_r2_f4_chunked_prefill_mechanism_evidence_incomplete
```

cleanup 不完整仍最高优先：

```text
red_cleanup_incomplete
```

任何 RED 都是有效结果，原样保留并停止。不要人工改 grade，不要把 RED 改成 yellow，
不要根据性能数字绕过机制门。

## 11. 有界结果包与传输边界

driver 只打包以下 19 个候选文件：

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
atomic_pair_admission_summary.json
atomic_pair_release_summary.tsv
mechanism_atomic_pair_first_step.tsv
cleanup_status.txt
first_failure_excerpt.txt
```

必须生成完整 manifest，逐项报告路径、bytes、完整 SHA-256、sensitivity 和总 bytes。
总包必须 ≤70KB；原始 lifecycle 目录、vLLM log、trace 和大制品留在服务器，不外发。

`result_transfer_authorized: true` 只表示这个有界完整包具备候选资格，不等于选定渠道。
正式运行后先报告：

```text
summary path
完整 19 文件 inventory
每项 bytes/SHA-256/sensitivity
total bytes
available methods=email,upload-api,server-local
recommended method + reason
```

然后等待用户明确选择一个完整渠道。不得先发 status-only 邮件，不得自动 email/upload，
不得拆包发送，不得在失败后自动换渠道。若用户尚未选择，结果保持 `server-local`。

## 12. 回报格式

请返回一个不超过 70KB 的文本报告，至少包含：

```text
P6_3C_R2_F4_SERVER_REPORT_BEGIN
task_id=
head=
origin_main=
ahead_behind=
tracked_clean=
global_mutual_exclusion_gate=
asset_gate=28/28
source_gate=8/8
request_payload_bytes=
request_payload_sha256=
request_id_fixture_gate=
audit_exit=
off_argv_sha256=
on_argv_sha256=
only_argv_difference=
experiment_exit=
finalize_exit=
package_exit=
server_grade=
first_failure_stage=
all_lifecycles_success=
request_count=
successful_request_count=
batch_count=
successful_batch_count=
request_retry_count=
runtime_layout_gate_complete=
f4_overlay_module_gate_complete=
loopback_transport_gate_complete=
request_id_normalization_gate_complete=
expected_pair_release_count=
exact_pair_release_count=
failure_event_count=
shutdown_state_observed_count=
checkpoint_terminal_state_used_count=
all_lifecycle_terminal_states_clean=
first_scheduler_step_contract_exact_count=
mechanism_atomic_coarrival_gate_complete=
off_prefill_partial_absent_all_cells=
on_prefill_partial_present_both_pressure_cells=
low_pressure_partial_absent_both_modes=
mechanism_gate_complete=
parent_p6_3c_r2_f3_grade_preserved=
parent_p6_3c_r2_f3_overwritten=
cleanup_status=
stopped_card_ids=
restored_card_ids=
keep_alive_restored_exact=
port_7000_listener_count=
vllm_residual_process_count=
result_dir=
bounded_manifest_path=
bounded_total_bytes=
available_transfer_methods=
recommended_transfer_method=
transfer_method_selected=
transfer_performed=
deviations=
P6_3C_R2_F4_SERVER_REPORT_END
```

另外附三张小表：

1. 六 lifecycle：track、mode、ready、request、batch、exit、cleanup。
2. 42 个 pair 汇总：lifecycle/cell、actual ID、canonical ID、release exact、wait。
3. 六个机制首轮：canonical waiting、scheduled tokens、expected、contract exact。

回报后停止，等待开发机复核和用户选择传输渠道。
