# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R4 完整恢复资格对齐

~~~text
task_id: p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722
execution_mode: authorized_single_lifecycle_full_restore_eligibility_alignment
server_sync_review_authorized: true
offline_parent_gate_required: true
npu_execution_authorized: true
keep_alive_stop_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
keep_alive_card_ids_exact: 0,1,2,3,4,5,6,7
formal_model_lifecycle_count_exact: 1
model_request_count_exact: 4
completed_request_count_exact: 3
intentional_pressure_abort_count_exact: 1
pressure_request_count_exact: 1
request_retry_count_exact: 0
accepted_cpu_blocks_per_rank_exact: 128
accepted_cpu_bytes_per_rank_exact: 430604288
accepted_cpu_bytes_total_exact: 3444834304
restore_match_tokens_required_exact: 16384
required_restore_block_count_exact: 128
pressure_context_tokens_exact: 36800
legacy_64_block_subset_authorizes_restore: false
all_relevant_kv_groups_required: true
full_request_window_watch_required: true
stop_on_first_near_miss: false
stop_on_first_cpu_target_eviction: false
context_change_authorized: false
capacity_change_authorized: false
capacity_search_authorized: false
pressure_search_or_sweep_authorized: false
concurrent_restore_while_pressure_active_authorized: false
runtime_or_dependency_mutation_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
next_task_authorized: false
k2_authorized: false
p8_3_i1_authorized: false
no_k2_k3_k4_p8_3_i1_p8_4_p8_5_or_p9: true
~~~

F1-R3 已闭合控制链，不重跑、不改写：同一 accepted-capacity lifecycle 内，fixed `36800`
`pressure_01` 在 request-local `CPU=64/GPU=0` 子集窗口被中止，随后 client exit、engine idle、
post-abort gate 与唯一 `restore_follower` 均完成；D2H 为 8 workers、`4548257792 bytes`。

F1-R3 最终仍是 `red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete`：restore 的
`prefix_hits_delta=0`、`restore_cpu_hit_exact=false`、`restore_load_scheduled=false`，H2D worker/bytes
均为零。因此不得继续使用“restore served via prefix cache”表述。准确边界是：restore HTTP 成功，
但 APC/Prefix hit 与 CPU-offload H2D hit 都没有出现；是否完整重算尚无逐组 scheduler 证据，不能写成唯一根因。

本轮只修复 restore eligibility 观测与授权边界。旧 observer 只取单一 `fa_gidx` 的前 64 blocks，覆盖
8192 tokens；实际 restore 需要 16384 tokens，即按 128-token block 推导的完整 128-block 窗口，并且
hybrid KV lookup 必须由全部相关 KV group 共同成立。F1-R4 保持 accepted capacity 与 fixed pressure 不变，
不得通过增容、改 context 或 sweep 绕过问题。

新 controller 必须按以下顺序执行：

~~~text
warmup success
-> target_prime success + D2H store complete
-> capture full 16384-token target geometry across all relevant KV groups
-> async pressure_01 with fixed context 36800
-> watch every request-local progress event for the complete pressure lifetime
-> record bounded required/captured/CPU/GPU counts for every relevant KV group
-> only exact single-request CPU=128/GPU=0 + all-group eligibility may latch trigger
-> abort pressure streaming connection
-> pressure client thread exits
-> engine queue returns idle
-> post-abort full 128-block all-group gate remains trigger_ready
-> switch role to restore_follower
-> exactly one restore request
~~~

“完整 pressure 生命周期窗口”是本任务硬要求。第一次 `CPU<128`、某组不完整、GPU 尚未归零或第一次
CPU target eviction 都只记为 near miss，不得立即把 accepted capacity 判为不兼容，也不得提前结束 watcher。
块在后续 scheduler step 仍可能重新形成完整资格。只有完整 watcher 结束仍没有触发时，才按有界逐组计数和
事件顺序分级；不得因第一次未形成窗口就提前判定容量不兼容。

`max_num_seqs=1`，pressure active 时发送 restore 会排队并污染 role marker，仍禁止并发 restore。
active role 在 pressure client exit 和 engine idle 均确认前必须保持 `pressure_01`。

## 固定 NPU keep-alive 规则

keep-alive 是常规资源管理，不是严重异常。本任务使用 NPU 0–7，开始前直接停止这八张卡上的低优先级
keep-alive 即可；任务完成后恢复相同的 0–7。无论成功、失败、中断或提前退出，都必须恢复完全相同的卡集，
并在最终回报中写明实际停卡卡号、实际恢复卡号与恢复状态。

~~~bash
# 本任务使用全部八卡，开始前执行。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 所有退出路径都恢复完全相同的卡集。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

命令末尾数字是卡号。不得扩大到其他节点或其他机器。

## 0. 已接受 parent 与本轮证据边界

以下 F1-R3 文件必须原位存在且 SHA-256 精确匹配：

~~~text
14d761452ea7f2c2b6259a441fb3995d336bbf9bb8e605045c114095a9f0988e  grading_summary.json
ac14adbba9b80e459c42e4113343be90aa836e533dd56c9812f7727706c82e39  h2d_trigger_summary.json
494cee6c1cbe51957c5d45956a1389c266fcfe533fccefdd5abc5a18fb72e350  residency_gate_timeline.json
4299261a926e342366ce841684c48c083f62259e153ff67038359fe81b438371  candidate_manifest.server_local.json
~~~

已接受 parent 事实：

~~~text
parent_task_id=p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
parent_grade=red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
parent_formal_model_lifecycle_count=1
parent_request_count=4
parent_successful_request_count=3
parent_intentional_pressure_abort_count=1
parent_request_retry_count=0
parent_pressure_context_tokens=36800
parent_trigger_before_abort=true
parent_abort_confirmed=true
parent_engine_idle_after_abort=true
parent_post_abort_window_valid=true
parent_restore_request_completed=true
parent_d2h_store_complete=true
parent_d2h_worker_count=8
parent_d2h_bytes_total=4548257792
parent_restore_cpu_hit_exact=false
parent_restore_load_scheduled=false
parent_h2d_worker_count=0
parent_h2d_bytes_total=0
parent_cleanup=clean
parent_prefix_hits_delta=0.0
parent_actual_cpu_eviction_proven=false
parent_unique_cause_proven=false
~~~

已关闭并继续保持关闭：performance reference、optimization gain、unique cause、K2、P8.3-I1、P8.4、
P8.5、P9。F1-R4 只接受 accepted-capacity 完整 restore eligibility 与条件式 H2D mechanism candidate。

以下已关闭 lineage 只作前置真值，不授权重跑：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
blocked_p6_3c_not_strict_single_variable
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p8_2_k1_frozen_stack_import_incompatible
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
ready_p8_2_k1a_r2_allocator_capacity
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
red_p8_2_k1a_r5_l1_r1_cpu_target_lost
red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
candidate_p8_2_k1a_r5_f1_r2_mid_request_window_endpoint_mismatch
red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use_total=3444834304
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
result_directory_creation_authorized: true
~~~

不得进入 K2；不得进入 P8.3-I1。

## 1. 同步、tracked-clean 与仓库合同（keep-alive 仍运行）

只允许从干净 `main` 普通 fast-forward。不得 reset、stash、rebase、cherry-pick、server commit 或 push。
未跟踪服务器产物保留在 `--untracked-files=no` 边界外。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --short --branch --untracked-files=no
~~~

同步后重新打开本文件，只执行这里的 F1-R4。先在 keep-alive 运行时完成合同门：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh

P8_2_K1A_F1_R4_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r4_unused
~~~

audit-only 必须至少包含：

~~~text
task_id=p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722
accepted_cpu_blocks_per_rank=128
required_restore_block_count=128
restore_match_tokens_required=16384
legacy_64_block_subset_authorizes_restore=false
all_kv_groups_required=true
pressure_context_tokens=36800
capacity_change_authorized=false
full_request_window_watch_required=true
formal_model_lifecycle_count_exact=1
model_request_count_exact=4
request_retry_count_exact=0
result_transfer_authorized=true
transfer_method_selected=false
next_task_authorized=false
~~~

以下 repo 文件 SHA-256 必须精确匹配；最终值以本次提交中的此段为准：

~~~text
6679e7abf67d3e4a2852273e54f1071a106933228a07a30e6b3987d7db5d4fc5  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_audit.yaml
2acc928a5b351cd290e3496caaea5ebece58c1caa731a8a83068f3aa5f8b68c8  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.yaml
670ebf219e70b370e82a99f130ee733460738c60e9d68024cbb1dc92893b082f  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
7ff9d0f7f6b70ae7e0a3a978781edeee22f543d4d168b4d1b8c89865fe907f1f  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
2835fffdd7876125d947c50bf6246da9038edac4e417e188ca6fc5cd0716ac85  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py
5628a1109164146a33e082c9622c31a88c2fcf209808326219be7fd531c19ee9  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
ff038cf51ac79d8eec4fa5b9d926178d494efa630265dafe3e8ade8ea06ce8b1  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
6cd73275427aa3afc736a5aeee816301af30e3acb4332774a32ba1d011e03001  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
~~~

Section 1 任一失败：报告 `blocked_p8_2_k1a_r5_f1_r4_repository_contract_gate` 并停止；不得停卡。

## 2. Parent、资源与冻结配置前门（keep-alive 仍运行）

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
F1_R3_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722_run01
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
cd "${REPO_ROOT}"

test -d "${F1_R3_ROOT}"
test "$(sha256sum "${F1_R3_ROOT}/grading_summary.json" | awk '{print $1}')" = \
  14d761452ea7f2c2b6259a441fb3995d336bbf9bb8e605045c114095a9f0988e
test "$(sha256sum "${F1_R3_ROOT}/h2d_trigger_summary.json" | awk '{print $1}')" = \
  ac14adbba9b80e459c42e4113343be90aa836e533dd56c9812f7727706c82e39
test "$(sha256sum "${F1_R3_ROOT}/residency_gate_timeline.json" | awk '{print $1}')" = \
  494cee6c1cbe51957c5d45956a1389c266fcfe533fccefdd5abc5a18fb72e350
test "$(sha256sum "${F1_R3_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = \
  4299261a926e342366ce841684c48c083f62259e153ff67038359fe81b438371
test -d "${MODEL_PATH}"
test -r "${MODEL_PATH}/config.json"
test -z "$(ss -ltnp | awk '$4 ~ /:7000$/ {print}')"
test -z "$(pgrep -af 'vllm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' || true)"
python3 - <<'PY'
import psutil
assert psutil.virtual_memory().available >= 412316860416
PY
~~~

若 parent/hash/model/port/memory 任一失败，保持 keep-alive 运行，报告对应 blocked grade 并停止。

## 3. 单次正式 lifecycle

本任务只允许一个新目录；不得创建 run02，不得 retry，不得改 context/capacity 后重跑。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722_run01
cd "${REPO_ROOT}"
test ! -e "${RESULT_DIR}"

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh \
  "${RESULT_DIR}"
~~~

runner 内部必须保持以下冻结值：

~~~text
model_path=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
quantization=ascend
tensor_parallel_size=8
expert_parallel=true
mtp_num_speculative_tokens=1
graph_mode=FULL_DECODE_ONLY
max_model_len=135168
max_num_batched_tokens=4096
max_num_seqs=1
block_size_tokens=128
chunked_prefill=true
prefix_caching=true
kv_connector=SimpleCPUOffloadConnector
kv_role=kv_both
lazy_offload=true
cpu_blocks_per_rank=128
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use_total=3444834304
pressure_context_tokens=36800
restore_match_tokens_required=16384
required_restore_block_count=128
request_retry_count=0
~~~

observer 仍必须是 observe-only：不得改变 scheduler 参数、request order、copy 参数、block retention/LRU、
runtime source 或依赖。跨组 hash 只在进程内用于 lookup；raw hash、request ID、token ID、请求体和生成内容
不得进入有界包。

### 3.1 watcher 与 near-miss 要求

每个 request-local progress event 都要保留以下有界元数据：

~~~text
num_computed_tokens_before_schedule
num_scheduled_tokens
num_computed_tokens_after_schedule
target_block_count
cpu_target_block_count
gpu_target_block_count
restore_group_count
restore_groups_captured_exact
restore_groups_cpu_complete_count
restore_groups_gpu_absent_count
restore_group_eligibility_complete
per-group required/captured/cpu/gpu counts
~~~

不能因第一次 CPU eviction 就停止。若稍后形成完整 `CPU=128/GPU=0 + all groups eligible`，早期 eviction
只作为 near miss 记录，不得让 post-abort gate 误判；只有完整窗口之后发生的新丢失才使窗口失效。

若 pressure 自然完成仍无完整窗口，必须从整个生命周期选择最佳 near miss，并报告：最大 CPU target count、
当时 GPU target count、各组差额、首次/最后一次完整 capture、所有 CPU/GPU target eviction 的相对顺序，
以及是否存在“先 eviction 后重新恢复”。只能写“本次 fixed lifecycle 未观察到完整 restore-eligible window”，
不得写成 accepted capacity 的唯一不可能性证明。

### 3.2 成功候选门

candidate green 必须同时满足：

1. exact request-local single-request `CPU=128/GPU=0`；
2. 全部相关 KV group required/captured/CPU/GPU 计数闭合；
3. trigger→abort→client exit→engine idle→post-abort full gate→restore 顺序闭合；
4. restore `cpu_hit_matched=16384`；
5. restore load scheduled；
6. 8 workers H2D submit/enqueue/copy/poll/completion 与 load request completion 闭合；
7. D2H、connector、repair、MTP/queue、cleanup/recovery 全部闭合。

任一不满足均为对应 red，不得提升 H2D mechanism candidate，更不得形成性能或唯一根因结论。

## 4. Cleanup 与 keep-alive 恢复

runner 应覆盖 cleanup；无论 runner 返回何值，操作员都要复核 0–7 keep-alive 已恢复。若未恢复，立即执行：

~~~bash
set -euo pipefail
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
sleep 2
pgrep -af '/data/node0_disk1/Public/npu_keep_alive.py' || true
ss -ltnp | awk '$4 ~ /:7000$/ {print}'
pgrep -af 'vllm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' || true
npu-smi info
~~~

最终必须确认：端口 7000 空闲、无目标 vLLM 残留、八卡健康、实际 stopped/restored 卡集完全相同、
keep-alive 恢复准确、tracked worktree clean。cleanup/recovery 不完整优先覆盖实验 grade 为 red。

## 5. 有界结果包与完整回报

raw vLLM logs、metrics、request bodies、token IDs、generated content、raw trace 与 raw hashes 留在服务器
`RESULT_DIR/runtime/`，只报告路径。候选 transfer 包最多 15 payload + 1 manifest，包含 manifest 在内严格
不超过 `71680 bytes`。

最终一次性回报：

1. `HEAD`、`origin/main`、ahead/behind、tracked-clean；
2. F1-R3 parent 四个 SHA-256 与 parent grade；
3. 定向 pytest、py_compile、Bash、audit-only 与 repo hashes；
4. lifecycle/request/complete/intentional abort/retry 精确计数；
   同时报每个 role 的最终状态，成功触发时 `pressure_01=aborted_on_trigger`；
5. 128-block capture、全部相关 KV group 数量与每组 required/captured/CPU/GPU 最佳/终态计数；
6. 完整 pressure 生命周期 progress 数、最佳 near miss、所有 target eviction 的相对顺序；
7. trigger/abort/client exit/engine idle/post-abort gate/restore 的 monotonic 顺序；
8. restore CPU hit/load、D2H/H2D worker/bytes/pipeline/completion 与最终 grade；
9. cleanup、7000、vLLM residual、八卡健康、实际停卡/恢复卡集、恢复状态；
10. `result_summary.md` 绝对路径与完整候选清单：每个文件 bytes、SHA-256、sensitivity，另报 payload
    bytes、manifest bytes、完整 transfer bytes、`payload_file_count`、`manifest_file_count=1`、
    `transfer_file_count` 并逐文件双校验；可用方法原样报告为 `email / upload-api / server-local`。

结果传输规则：`result_transfer_authorized: true` 仅表示该完整有界包可供选择，不选择渠道、不允许自动发送。
先在当前任务会话给出完整清单、可用方法 `email` / `upload-api` / `server-local`，并推荐
`server-local`（本轮 raw trace 较大且后续很可能需要服务器原位逐组分析；有界包先留原位最稳妥）。随后暂停，
等待用户对完整范围明确选择一种方法。不得先发状态邮件，不得自动切换渠道，不得在本任务里写传输命令。

报告完成后暂停；不得自行进入 K2、P8.3-I1 或任何下一任务。
