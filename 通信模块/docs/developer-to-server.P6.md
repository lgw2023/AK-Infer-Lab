# 开发机 → Ascend 服务器交接任务（P6 专用）

## P6.3C-R2-F3 run01：atomic-pair-admission Chunked Prefill matched A/B

```yaml
dispatch_revision: p6_3c_r2_f3_atomic_pair_admission_2026_0730_r1
task_id: p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01
run_id: p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01
stage: P6.3C-R2-F3
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

服务器助手不需要写代码、修改 site-packages、补环境变量、创建 wrapper 或解释实验。
开发机已经把 F3 的 task-local atomic pair admission、overlay、请求、六生命周期、首轮
scheduler 证据、分级、清理与有界打包写入唯一 driver。服务器只需 fast-forward 同步远程
`main`、核验事实、运行一次 audit、运行一次正式入口、原样回报，然后停止。

## 1. 为什么必须新建 F3，不能重跑 F2

以下历史结果全部独立保留：

1. 原 P6.3C 的 `blocked_p6_3c_not_strict_single_variable` 只证明冻结
   `135168/4096/1` 下 Off 侧不能启动，不代表 Chunked Prefill 无法研究。
2. R1 的 `69632/69632/2` 在 KV-cache 初始化阶段失败，0 request、0 scheduler step。
3. R2 run01 的 mixed-install overlay 没有物化，在 vLLM 启动前失败。
4. R2-F1 修复了布局并完成 vLLM 启动，但 loopback health 被代理误路由，0 request。
5. R2-F2 修复了代理：6/6 lifecycle、90/90 engine request、48/48 HTTP batch、
   六次 server ready、零 retry、资源恢复 clean，证明 layout、overlay、模型启动、
   direct-loopback、共同 repair 和请求执行链都已可用。

F2 最终仍为：

```text
red_p6_3c_r2_f2_scheduler_pressure_evidence_incomplete
```

原因不是 Chunked Prefill 无效，而是 OpenAI multi-prompt 被 serving/AsyncLLM 拆成两个
EngineCore message。EngineCore 收到第一条后已有 scheduler work，可能在第二条到达前
开始 step。F2 observer 的直接证据是：

```text
4K+4K:  request 0/1 分处 step 35 / 36
10K+6K: request 0/1 分处 step 71 / 72
8K+8K:  request 0/1 分处 step 107 / 108
Off 与 On 均为每请求一次完整 prefill，partial prefill=0
```

4K+4K 总量 8192 小于预算 12288；若两请求首次调度前都在 waiting，本应同一 step
准入。相邻 step 因此证明 F2 没有建立同轮 token-budget 竞争。F2 的 timing delta 也不能
归因为 Chunked Prefill。不得创建 F2 run02，不得覆盖 F2 目录或把它改判为机制负结论。

F3 保留相同科学参数，在 Off/On 两侧共同加入 task-local controlled co-arrival：

- 只识别 `p6_3c_r2_f3` measured request pair；
- 首个 member 在调用原 `EngineCore.add_request` 前缓冲，不产生 scheduler work；
- 第二个 member 到达后按 pair index 0→1 连续调用原 `add_request`；
- timeout WAKEUP 只挂到固定源码中实际拥有该入口的
  `EngineCoreProc._handle_client_request`；不要把它改挂到基础 `EngineCore`；
- warmup 和其他请求原样通过；
- 不改 Scheduler、Chunked Prefill、token budget、请求 token 或输出；
- peer 缺失、abort、duplicate、release failure、shutdown pending 均有 fail-closed
  清理和证据。

这是两侧共同的新冻结控制环境，不是 A/B 第二差异。F3 只支持受控 co-arrival 下的机制
辨识，不代表自然生产 OpenAI API 请求到达行为。

## 2. 冻结科学合同与期望机制

两侧共同冻结：

```text
max_model_len=12288
max_num_batched_tokens=12288
max_num_seqs=2
Prefix Cache=false（显式）
同一 validated deferred hybrid-KV task-local repair
同一 atomic pair admission（tagged measured pair only）
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

| cell | waiting_order_before | Off scheduled tokens | On scheduled tokens |
|---|---|---:|---:|
| 4K+4K | request 0, request 1 | 4096 + 4096 | 4096 + 4096 |
| 10K+6K | request 0, request 1 | 10240 + 0 | 10240 + 2048 |
| 8K+8K | request 0, request 1 | 8192 + 0 | 8192 + 4096 |

机制轨道要求：

```text
Off: 三个 cell 均无 partial prefill
On: 10K+6K 与 8K+8K 均有 partial prefill
On/Off: 4K+4K 均无 partial prefill
```

性能轨道仍关闭 scheduler observer 和 profiler，顺序为 Off→On→On→Off；atomic
admission 是两侧共同环境并留下必要 release/wait 审计。TTFT、E2EL、TPOT、ITL、batch
throughput、完成时间差和 barrier wait 只作该控制环境内描述，不作普遍收益声明。

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
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01
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
自动执行。本节失败时不得继续同步后的 audit 或正式命令。

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
git merge-base --is-ancestor c6f3d5fbf1598645456fc1aae9433a7919ebaefc HEAD
```

必须同时满足：

```text
branch=main
HEAD=origin/main
ahead/behind=0/0
tracked-clean=true
F2 发布提交 c6f3d5fb... 是当前 HEAD 祖先
RESULT_DIR 不存在
```

不得 stash、merge、rebase、commit、push、删除旧结果或编辑 tracked 文件。

## 6. 27 项仓库资产门

同步后逐项核对 bytes 与 SHA-256。任一不符，在零 NPU 阶段停止，不得修改后继续。

| # | 文件 | bytes | SHA-256 |
|---:|---|---:|---|
| 1 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f3_server_task.sh` | 1089 | `de6a13a435a82ca420f6991a05c4a23ecd8cec35a6dcd4d33ad52be58016e0e9` |
| 2 | `tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh` | 6111 | `910e9aa964f6f39487611f805ba7289f7bad4a9dd0d09d95e5b8c65c1b05d37d` |
| 3 | `tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh` | 10380 | `a6d26058491edcbad64b95a582126e4e0730ab0e01a4893d799f4e3468dce23d` |
| 4 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f3_scheduler_pressure.sh` | 756 | `824830360e28b918654b1c38ba2ab79812357adb75e88a76090438f7f1996976` |
| 5 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh` | 4631 | `dc5532c32490cea2ecc994f28d0bcb1db65e71a255fcd10579cc70c40a116a9c` |
| 6 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f3_mode.sh` | 519 | `25f0dc0f3090c80844ed54149e4ec14beaf5ee208f9591ea671737630b98ca5b` |
| 7 | `tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh` | 562 | `108a9fc218ad43694ee7ae3dfceea37ea8837333f66cd9ca90858a084fa6cea1` |
| 8 | `tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh` | 22063 | `4c665fd6e8ef7ad9e1e28661ef6142f18f2533f98a29ef8177bda6eb04964533` |
| 9 | `tools/inference_contracts/run_deepseek_p6_3c_r2_f3_atomic_pair_admission.py` | 24151 | `722d992052fb675598f44dd8523621c614bdf35eefd9602e1938170e819f2b93` |
| 10 | `tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py` | 32996 | `0b2f93ae7cb0d1b98a99ff3e635ef2a48829a22a674cc4048cba475a518b6eed` |
| 11 | `tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py` | 62978 | `d5df3d33f611851332b4c89466591f3345ad872fc9347be96359001718c221c1` |
| 12 | `tools/inference_contracts/p6_3c_r2_f3_atomic_pair_admission.py` | 13002 | `87ee8f07c33eab4ee38000768933467cdc145e49b48122a3d947f1309d776901` |
| 13 | `tools/inference_contracts/p6_3c_local_http_transport.py` | 3503 | `3e167ac892d1b64e3e03a41e6802ee734d0b4de24ceb59cbb3fc6423dbc4d70e` |
| 14 | `tools/inference_contracts/resolve_p6_3c_runtime_layout.py` | 4663 | `a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897` |
| 15 | `tools/inference_contracts/prepare_p6_3c_runtime_overlay.py` | 12701 | `af3b3d0ced22d8729b21447a3d1528f0a5643527481e6a285689c9e5db4342b2` |
| 16 | `tools/inference_contracts/p6_3c_startup_resource_summary.py` | 5009 | `b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a` |
| 17 | `tools/inference_contracts/p6_3c_r1_scheduler_observer.py` | 7251 | `c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4` |
| 18 | `tools/inference_contracts/canonicalize_server_argv.py` | 1238 | `c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d` |
| 19 | `tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py` | 10250 | `6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c` |
| 20 | `tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py` | 2733 | `9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631` |
| 21 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f3_atomic_pair_admission_matched_ab.yaml` | 6310 | `fa4c5c6c100a4a2f40d52ac585ac0a03e4afff7099fdcb3161235a574d1a3920` |
| 22 | `benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f2_loopback_proxy_safe_matched_ab.yaml` | 4174 | `31aa1a09fabee527376e0323777e4457302a8dd8a3fba8ae6eb8fc4e2caaca80` |
| 23 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch` | 769 | `75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1` |
| 24 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch` | 830 | `2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f` |
| 25 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r2_f3_atomic_pair_admission_overlay.patch` | 821 | `f474683e3dae779e13023f618bc650195e475deae26c5837458e5a9a12dacb74` |
| 26 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch` | 1054 | `cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e` |
| 27 | `benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch` | 896 | `ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b` |

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
tools/inference_contracts/run_deepseek_p6_3c_r2_f3_server_task.sh|1089|de6a13a435a82ca420f6991a05c4a23ecd8cec35a6dcd4d33ad52be58016e0e9
tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh|6111|910e9aa964f6f39487611f805ba7289f7bad4a9dd0d09d95e5b8c65c1b05d37d
tools/inference_contracts/run_deepseek_p6_3c_r1_server_task.sh|10380|a6d26058491edcbad64b95a582126e4e0730ab0e01a4893d799f4e3468dce23d
tools/inference_contracts/run_deepseek_p6_3c_r2_f3_scheduler_pressure.sh|756|824830360e28b918654b1c38ba2ab79812357adb75e88a76090438f7f1996976
tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh|4631|dc5532c32490cea2ecc994f28d0bcb1db65e71a255fcd10579cc70c40a116a9c
tools/inference_contracts/run_deepseek_p6_3c_r2_f3_mode.sh|519|25f0dc0f3090c80844ed54149e4ec14beaf5ee208f9591ea671737630b98ca5b
tools/inference_contracts/run_deepseek_p6_3c_r2_mode.sh|562|108a9fc218ad43694ee7ae3dfceea37ea8837333f66cd9ca90858a084fa6cea1
tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh|22063|4c665fd6e8ef7ad9e1e28661ef6142f18f2533f98a29ef8177bda6eb04964533
tools/inference_contracts/run_deepseek_p6_3c_r2_f3_atomic_pair_admission.py|24151|722d992052fb675598f44dd8523621c614bdf35eefd9602e1938170e819f2b93
tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.py|32996|0b2f93ae7cb0d1b98a99ff3e635ef2a48829a22a674cc4048cba475a518b6eed
tools/inference_contracts/run_deepseek_p6_3c_r1_scheduler_pressure.py|62978|d5df3d33f611851332b4c89466591f3345ad872fc9347be96359001718c221c1
tools/inference_contracts/p6_3c_r2_f3_atomic_pair_admission.py|13002|87ee8f07c33eab4ee38000768933467cdc145e49b48122a3d947f1309d776901
tools/inference_contracts/p6_3c_local_http_transport.py|3503|3e167ac892d1b64e3e03a41e6802ee734d0b4de24ceb59cbb3fc6423dbc4d70e
tools/inference_contracts/resolve_p6_3c_runtime_layout.py|4663|a9c09b49494a1137b51dee6e054acde110be5140edf5f6a9dfe225f9df8c3897
tools/inference_contracts/prepare_p6_3c_runtime_overlay.py|12701|af3b3d0ced22d8729b21447a3d1528f0a5643527481e6a285689c9e5db4342b2
tools/inference_contracts/p6_3c_startup_resource_summary.py|5009|b82cf274bdcf33939643980b8245c19830bf04ead182f21e4b7e6d250f8b3d2a
tools/inference_contracts/p6_3c_r1_scheduler_observer.py|7251|c94af51c9777f750668c7cdaa422cd1fc665876437a227d8c7ab2b5387014ea4
tools/inference_contracts/canonicalize_server_argv.py|1238|c1bfd1cc7df7b18a5b8abfb5b50e827a2c245d716ab4100f48d831a8fa5eea0d
tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py|10250|6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py|2733|9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f3_atomic_pair_admission_matched_ab.yaml|6310|fa4c5c6c100a4a2f40d52ac585ac0a03e4afff7099fdcb3161235a574d1a3920
benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f2_loopback_proxy_safe_matched_ab.yaml|4174|31aa1a09fabee527376e0323777e4457302a8dd8a3fba8ae6eb8fc4e2caaca80
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch|769|75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch|830|2b770705f09b6cfc5bd3c7f79a1c01493e486e93845f620c87f101b5524f1c9f
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r2_f3_atomic_pair_admission_overlay.patch|821|f474683e3dae779e13023f618bc650195e475deae26c5837458e5a9a12dacb74
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch|1054|cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch|896|ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
EOF

test -x tools/inference_contracts/run_deepseek_p6_3c_r2_f3_server_task.sh
test -x tools/inference_contracts/run_deepseek_p6_3c_r2_f3_scheduler_pressure.sh
test -x tools/inference_contracts/run_deepseek_p6_3c_r2_f3_mode.sh
```

特别确认第 23 项 MTP patch 正确 SHA 中段是 `...f261a3...`，不是历史 typo
`...f262a3...`。

## 7. 冻结安装源码门

27 项仓库资产通过后，正式入口会在停 keep-alive 前自动用目标环境 Python 的
`importlib.find_spec + realpath` 解析真实包路径，并核对以下八个文件：

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

随后 driver 会物化 disposable `vllm_ascend` overlay，要求 symlink=0、realpath escape=0、
不修改 base environment/site-packages，并在停卡前 dry-run/apply MTP、hybrid、deferred、
atomic admission 和 scheduler observer patch。不要创建 `/tmp/p6_3c_r2_env_prefix`，
不要手工导出 `BASE_PLUGIN_ROOT` / `BASE_VLLM_ROOT`，不要编辑安装源码。

## 8. 零 NPU audit-only

只有 §4–§7 全过且结果目录不存在时执行：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
P6_3C_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p6_3c_r2_f3_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01
```

audit-only 不停 keep-alive、不创建结果目录。必须看到：

```text
task_id=p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01
formal_model_lifecycle_count_exact=6
engine_request_count_exact=90
batched_http_call_count_exact=48
request_retry_count_exact=0
capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_2
atomic_pair_admission=1
atomic_pair_request_prefix=p6_3c_r2_f3
atomic_pair_timeout_seconds=30
tagged_measured_pair_count_exact=42
shared_hybrid_kv_repair=enabled_both_modes_all_lifecycles
```

六个 lifecycle 都必须输出 `atomic_pair_admission=1`。Off 三次 argv SHA 必须全为：

```text
568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10
```

On 三次必须全为：

```text
cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017
```

两 SHA 与 F2 一致，证明共同 atomic admission 不改变 server argv；两者唯一差异仍是
Chunked Prefill flag。audit 输出不符时停止，不手工修。

## 9. 唯一正式命令

只有全局互斥、Git、27 项资产、八项源码、overlay preflight 和 audit 全过后，执行一次：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
bash tools/inference_contracts/run_deepseek_p6_3c_r2_f3_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01
```

不要拆分 driver，不要后台重启，不要重试失败 lifecycle，不要创建 run02，不要追加请求，
不要运行 profiler/HBM sampler，不要调参数或 cell，不要进入下一任务。

正式 driver 内部会对 NPU 0–7 执行以下规则：只在所有停卡前门通过后停止低优先级
keep-alive，并在成功、失败、异常、中断或早退时精确恢复同一组卡。

```bash
# Driver 内部停止本任务需要的卡。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Driver 的 trap 在每种退出路径恢复完全相同的卡。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

服务器助手不要在 driver 外重复停卡。若 driver 被外部强制终止且 trap 明确未完成，唯一
授权的人工补救是先执行上面的 keep-alive 恢复命令，再报告偏差并停止；不得继续实验。

## 10. Driver 应产生的关键证据

每个 lifecycle：

```text
runtime/runtime_overlay_manifest.json
runtime/loopback_transport_contract.json
runtime/server_ready_probe_summary.tsv
runtime/startup_resource_summary.json
runtime/resolved_scheduler_config.json
runtime/atomic_pair_trace/trace.*.jsonl
raw_request_results.jsonl
raw_batch_results.jsonl
cleanup_status.txt
lifecycle_exit_code.txt
```

机制 lifecycle 还必须有只读：

```text
runtime/scheduler_trace/trace.*.jsonl
```

最终新增关键摘要：

```text
atomic_pair_admission_summary.json
atomic_pair_release_summary.tsv
mechanism_atomic_pair_first_step.tsv
mechanism_scheduler_summary.json
mechanism_request_chunk_summary.tsv
performance_mode_cell_summary.tsv
performance_order_balanced_pairs.tsv
grading_inputs.json
first_failure_excerpt.txt
```

`atomic_pair_admission_summary.json` candidate 所需硬门：

```text
installed_lifecycle_count=6
expected_pair_release_count=42
exact_pair_release_count=42
failure_event_count=0
all_lifecycle_shutdown_states_clean=true
atomic_pair_release_gate_complete=true
mechanism_cell_count=6
first_scheduler_step_contract_exact_count=6
mechanism_atomic_coarrival_gate_complete=true
coarrival_gate_complete=true
```

任何 lifecycle 的 pending pair、failed pair、timeout、abort-before-release、duplicate、
release failure、请求 ID/顺序/长度漂移或第一轮 scheduled-token 不符都必须阻断 candidate。

F3 finalizer 已修复 F2 的小缺陷：若 90/90 请求完成但最终为 RED，
`first_failure_excerpt.txt` 必须写实际 F3 `server_grade`，不能残留 R1 grade 前缀。

## 11. 分级与停止语义

可能的主要 grade：

```text
candidate_green_p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_matched_ab
red_p6_3c_r2_f3_atomic_pair_admission_evidence_incomplete
red_p6_3c_r2_f3_chunked_prefill_mechanism_evidence_incomplete
red_p6_3c_r2_f3_scheduler_pressure_no_success
yellow_p6_3c_r2_f3_scheduler_pressure_partial
red_cleanup_incomplete
```

解释：

- atomic admission RED：请求可成功，但 42 个 pair release 或六个首轮 co-arrival 几何不全；
- mechanism RED：co-arrival 已证明，但 Chunked Prefill Off/On 的冻结调度模式未完整出现；
- partial：生命周期、90-request 或 48-batch 矩阵不完整但资源恢复 clean；
- cleanup RED：keep-alive、端口、残留进程、tracked worktree 或实际尝试 lifecycle 清理失败。

即使得到 candidate green，也只能称为“受控 atomic co-arrival 三个冻结 cell 的直接
scheduler 机制证据”。不得宣称自然 API 到达、任意请求组合、统计显著性、生产吞吐或
普遍性能收益。完成后必须等待开发机独立复核，不能自动进入 P7/K2/K3/P8.3/P9。

## 12. 服务器回报格式

正式命令完成后，原样保留 driver 的：

```text
P6_3C_R2_F3_SERVER_REPORT_BEGIN
...
P6_3C_R2_F3_SERVER_REPORT_END
```

另外用简洁中文明确列出：

1. Git HEAD、origin/main、ahead/behind、tracked-clean；
2. 27/27 资产、8/8 冻结源码、request payload、audit 是否通过；
3. experiment/finalize/package exit；
4. 六 lifecycle 的 ready、request、batch、exit、cleanup；
5. 42/42 release、6/6 first-step contract、failure event 与 shutdown pending/failed；
6. 三个 cell 的 Off/On 第一轮 waiting order、scheduled tokens、partial prefill；
7. 两个 order-balanced pair 的全部性能 delta，不要只摘一个 pair；
8. stopped/restored card IDs、16 marker、端口 7000、vLLM residual、tracked-clean；
9. 任何偏差、首错摘录与服务器原始结果目录。

若命令因非 candidate grade 返回非零，但 package 完成且资源恢复 clean，这是合同内结果；
不要重跑。

## 13. 70KB 有界结果与传输选择

大日志、raw trace、请求体、模型输出和完整结果目录留在服务器。driver 只把以下小文件纳入
候选清单，合计必须 ≤71680 bytes：

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
startup_resource_summary.tsv
loopback_transport_summary.tsv
runtime_layout.json
runtime_overlay_preflight_manifest.json
atomic_pair_admission_summary.json
atomic_pair_release_summary.tsv
mechanism_atomic_pair_first_step.tsv
resource_recovery_summary.json
cleanup_status.txt
first_failure_excerpt.txt
```

完成后先报告：

```text
result_summary_path
candidate_manifest.server_local.json 的 bytes/SHA-256
每个候选文件的 path/bytes/SHA-256/sensitivity
candidate_total_bytes
available_methods=email,upload-api,server-local
recommended_method=upload-api
recommended_reason=multi_file_atomic_session_with_per_file_hash_validation
```

`result_transfer_authorized: true` 表示该有界包可被选择传输，不等于已经选择渠道。服务器
不得自动 email/upload，不得先发状态邮件。等待用户对完整清单明确选择一个：
`email` / `upload-api` / `server-local`。本轮默认执行后只报告并留在 `server-local`。

## 14. 首错分支

- 全局冲突：零 NPU 停止，只报告冲突对象。
- Git/资产/源码/request payload/audit 不符：零 NPU 停止，只报告实际值；不修。
- overlay preflight 失败：零 NPU 停止，回报 bounded failure excerpt。
- keep-alive stop 失败：driver 退出并尝试同卡恢复；报告 stop/restart exit。
- lifecycle 失败：停止后续 lifecycle，driver 清理 vLLM、恢复 0–7、finalize/package；
  不重跑。
- atomic timeout/abort/duplicate/release failure：按 evidence RED 收口；不补请求。
- cleanup/restart 不完整：优先 `red_cleanup_incomplete`，报告并停止。
- package 超过 70KB：不传输；报告 manifest/大小，等待开发机修改。

执行到任一终点后停止，等待用户和开发机复核。
