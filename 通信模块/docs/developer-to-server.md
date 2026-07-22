# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R6 逻辑恢复键空间对齐

~~~text
task_id: p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723
execution_mode: authorized_single_lifecycle_logical_keyspace_restore
server_sync_review_authorized: true
offline_parent_gate_required: true
npu_execution_authorized: true
keep_alive_stop_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
result_directory_creation_authorized: true
keep_alive_card_ids_exact: 0,1,2,3,4,5,6,7
server_task_driver_required: true
manual_internal_step_reconstruction_authorized: false
formal_model_lifecycle_count_exact: 1
model_request_count_min: 3
model_request_count_max: 4
pressure_request_count_exact: 1
request_retry_count_exact: 0
accepted_cpu_blocks_per_rank_exact: 128
accepted_cpu_bytes_per_rank_exact: 430604288
accepted_cpu_bytes_total_exact: 3444834304
logical_target_block_count_exact: 128
required_restore_block_count_exact: 128
block_size_tokens_exact: 128
restore_match_tokens_exact: 16384
pressure_context_tokens_exact: 36800
runtime_pool_key_count_fixed: false
runtime_cpu_coordinator_lookup_required: true
all_relevant_kv_groups_required: true
kv_connector: SimpleCPUOffloadConnector
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

### 先读结论：服务器助手不需要现场设计或改代码

F1-R5 不是 accepted capacity 失败证据；accepted capacity 没有失效，也没有证明完整逻辑
128-block CPU-only 窗口不可形成。
它把 128 个 plain request hash 直接拿去查以 `BlockHashWithGroupId` 为键的 runtime pool；这里的
request hash 不是 runtime pool key，所以 41 个进度点都错误显示 `CPU=0/GPU=0`。同一份原始状态已经证明
真实 CPU pool 中至少有 group 0 的 64 个 key 和 group 1 的 2 个 key。压缩/稀疏 KV 组的
physical pool key 数量可以不是 128，不能用某个组的物理 key 数代替 16K 前缀的逻辑 128-block 覆盖。

F1-R6 已把代码写好：观察器以只读方式调用运行时自身的
`find_longest_cache_hit(request_hashes, 16384)`，以返回的命中 token 数判定逻辑 128-block 窗口，
同时保留运行时返回的真实 group pool key 做 CPU/GPU 驻留和后续 eviction 检查。只有以下条件同时
成立才允许中止 pressure 并发送 restore：

1. 128 个逻辑 request hash 候选完整；
2. `logical_restore_match_tokens=16384`，即逻辑 128-block 完整命中；
3. 运行时返回的全部非空 group pool key 都在 CPU pool；
4. 这些真实 pool key 在 GPU pool 的匹配数为 0；
5. request-local progress 唯一、单请求，且 post-abort idle 后复查仍成立。

这是一条 observe-only 路径：不修改调度、请求顺序、复制参数或依赖。不要退回旧的
`select_target_hashes` 推断，不要把 physical key count 强行设成 128，不要因为仍未看到窗口就放弃
accepted capacity。

F1-R5 的 keep-alive 恢复也是假阴性：重启退出码为 0、同卡集合一致且八卡健康，但旧 driver 查找
不存在的 `npu_keep_alive.py` 进程名。真实 worker 参数以 `#0#` 到 `#7#` 标卡，正常总 marker 数为
16。F1-R6 driver 已在恢复后最多等待 30 秒，按 `#card_id#` 做总数与八卡覆盖双校验。

本轮唯一入口：

~~~text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
~~~

它自动执行 `parent/repo preflight（keep-alive 仍运行） -> stop 0-7 -> one lifecycle -> cleanup ->
restore 0-7 -> real marker probe -> resource recovery record -> bounded finalize`。
不要手工分步重现 runner 内部流程，不要直接运行 mode runner，不要修改脚本，不要创建 run02，
不要 retry 或 sweep。

## 0. 必须冻结的 F1-R5 parent

直接 parent 目录必须原位存在：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722_run01
~~~

以下五个文件必须精确匹配；driver 会在停卡前自动验证：

~~~text
62eb1cf78270c163a4bc861b21c20bbd165161f2172118928294403c5e61a806  grading_summary.json
79214a8ee8c226fae23acf36da482636d8976638e5e2dc96c5050cf41c4ac3aa  h2d_trigger_summary.json
6c44139c0f6500af5e09f7de67efc7a619cb856f52a70ec13755f4363e561dca  residency_gate_timeline.json
237bcf8456cc9269bd182efeb34d27e3b71b6c9e07563ba8ad4aa7dcf750a429  resource_recovery_summary.json
9d820400ef21df57f67540946b2b17917bae1c3949613c1057c661596f274c4e  candidate_manifest.server_local.json
~~~

已接受 parent 事实：

~~~text
parent_server_grade=red_p8_2_k1a_r5_f1_r5_cleanup_or_recovery_incomplete
parent_experimental_terminal=pressure_completed_without_trigger
parent_request_count=3
parent_http_200_full_response_count=3
parent_legacy_successful_request_count=2
parent_request_retry_count=0
parent_configured_target_blocks=128
parent_request_hash_candidate_count=128
parent_observed_cpu_target_blocks=0
parent_observed_gpu_target_blocks=0
parent_group0_cpu_pool_keys=64
parent_group1_cpu_pool_keys=2
parent_pressure_progress_event_count=41
parent_restore_sent=false
parent_h2d_restore_attempted=false
parent_cleanup=clean
parent_keep_alive_restart_exit_code=0
parent_keep_alive_marker_count_from_invalid_probe=0
parent_same_card_set_restored=true
parent_all_eight_npu_healthy=true
accepted_capacity_invalidated=false
full_logical_128_block_cpu_only_window_disproven=false
~~~

本轮还修正请求计数语义：`http_transport_success_count` 只统计 HTTP 200 + `[DONE]` 的完整传输，
`contract_completed_role_count` 统计 warmup/target/restore 成功及 pressure 按 trigger 有意中止的合同完成。
pressure 完整返回但没有 trigger 时，前者增加、后者不增加，并单列
`pressure_full_response_without_trigger_count`；不得再把传输成功写成请求失败。

拉取后以下 repo 文件 SHA-256 必须精确匹配。R4/R5 文件只用于冻结 parent 链；唯一可执行入口仍是
R6 server task：

~~~text
6679e7abf67d3e4a2852273e54f1071a106933228a07a30e6b3987d7db5d4fc5  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_audit.yaml
2acc928a5b351cd290e3496caaea5ebece58c1caa731a8a83068f3aa5f8b68c8  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.yaml
09bd6a02da715416f1af85689045ce91841d8279812cd483ec3be62deb6f0288  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
34acb760e6d76eb2f7748b6b45c6240bfc6e1a23c1709b11bf17a5e787913bf0  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
2835fffdd7876125d947c50bf6246da9038edac4e417e188ca6fc5cd0716ac85  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py
5628a1109164146a33e082c9622c31a88c2fcf209808326219be7fd531c19ee9  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
61bdd399a4742e3ae4b76614628b939a234bae6bd160ad7d22f8fe67ec54a89b  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
557bec74ec427a2bc37165eea3c38eab6f809ec46ac6cd4f904c1e5386b30240  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r5_effective_restore_contract_audit.yaml
2ed46e8df421076b00a1d71a6dfb1a30e315c21a2ba5990ae1fce7bcedc4211d  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r5_effective_restore_contract.yaml
96cc47e1574e2f56eddef8b5e4886491d00af946dee30a66ea761c68eb03a143  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py
41fc23b2d793f62ff7ecd58ac091afd5c6200b2816a7845b5e72c89200405337  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.sh
c81be3a3cf7da92ce4c9279bb4cc1e1039991b2c7a01c398b87b51ae3655a4f7  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh
7679c5e30829294015d65aed6416ec8986c557937cc8c8fb850003f7037e8244  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py
0b7a1b0e2ed18849570fe4b290bd308fcf53997be51e3aae0283edcdd288d793  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r6_logical_keyspace_restore_audit.yaml
6e4bcc70c78b77f74b834aa51a0f58d46c438206e248311068cc71dd32a3d4e2  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r6_logical_keyspace_restore.yaml
cb1fc04245741e110f36f3a5296d39de0dc57651e0523d5f07cb338583db173a  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py
2140e68e1e39f6c0d05fb8629ecea39dbefac7aaf422ec4d4866c6ad15ca29cd  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
bba3061051cd19eaab1c61a214081842a73d9dced23fca2c937308e6e4825fc7  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
5b5b051afd774b2ca6f7c97f9ec19932028e7644f09ded07948fbddcbe3969ed  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py
~~~

以下历史阶段已冻结，不授权重跑；这些精确标签只用于防止 lineage 丢失：

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
red_p8_2_k1a_r5_f1_r4_cleanup_or_recovery_incomplete
red_p8_2_k1a_r5_f1_r5_cleanup_or_recovery_incomplete
parent_task_id=p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
parent_f1_r5_task=p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
~~~

F1-R1/R2/R3/R4/R5、K2、P8.3-I1 及其后续阶段都不得重跑。

为兼容完整历史合同，以下参数别名继续冻结；它们不扩大授权：

~~~text
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
logical_restore_gate=CPU=128/GPU=0
pressure_status_on_trigger=aborted_on_trigger
parent_grade=red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
upstream_f1_r3_request_count=4
parent_successful_request_count=3
parent_d2h_store_complete=true
parent_h2d_worker_count=0
parent_cleanup=clean
historical_single_group_window=CPU=64/GPU=0
current_pressure_role=pressure_01
conditional_restore_role=restore_follower
historical_invalid_runner=tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
~~~

不得进入 K2；不得进入 P8.3-I1。

## 1. 同步 main 与离线合同门（此时不要停 keep-alive）

只允许从 tracked-clean `main` 普通 fast-forward。服务器本地 `server_local/` 未跟踪结果不在
tracked-clean 判定内。禁止 reset、stash、rebase、cherry-pick、server commit 或 push。

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

拉取后重新打开本文件，并按顺序运行以下离线门：

~~~bash
set -euo pipefail
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh

P8_2_K1A_F1_R6_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r6_unused
~~~

audit-only 必须同时看到：

~~~text
task_id=p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723
server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize
keep_alive_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_format=#card_id#
expected_keep_alive_marker_count=16
same_card_set_restore_on_every_exit=true
parent_f1_r5_keyspace_probe_invalid=true
accepted_capacity_invalidated=false
logical_target_block_count=128
logical_restore_match_tokens=16384
runtime_pool_key_count_fixed=false
runtime_cpu_coordinator_lookup_required=true
same_capacity_and_context=true
pressure_context_tokens=36800
request_retry_count_exact=0
capacity_search_authorized=false
resource_recovery_summary_always_recorded=true
finalize_after_recovery=true
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
~~~

任一离线门失败：保持 keep-alive 运行，回报完整命令、退出码和不超过 200 行的首尾错误摘要后停止。
不得现场修代码继续。

## 2. keep-alive 是常规资源操作，driver 自动负责

本任务需要 0-7 八卡，允许直接停。停卡本身不是事故，也无需单独请示。driver 内部使用：
下面两条命令的末尾数字是卡号，本轮固定为 0-7；最终回报必须包含实际停卡卡号、实际恢复卡号与恢复状态。

~~~bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

无论成功、失败、中断或提前退出，必须恢复完全相同的 0-7，并以真实 `#0#`...`#7#` worker
参数验证：`expected_keep_alive_marker_count=16` 且 marker card coverage 恰为 0-7。不要另开终端手工停卡
或恢复；driver 的 trap 会统一收尾。

## 3. 唯一一次正式执行

确认 `run01` 目录不存在；存在就停止，不覆盖、不删除、不改名、不建 run02。

~~~bash
set -euo pipefail
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}_run01"
cd "${REPO_ROOT}"
test ! -e "${RESULT_DIR}"

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh \
  "${RESULT_DIR}"
TASK_EXIT=$?
set -e
printf 'server_task_exit=%s\n' "${TASK_EXIT}"
printf 'result_dir=%s\n' "${RESULT_DIR}"
~~~

非零退出可能是预期 RED 终态；不要据此重跑。driver 已负责 cleanup、恢复、recovery record 和
finalize。若进程被外部硬杀导致 trap 未运行，才允许只执行 keep-alive 恢复命令和只读健康检查，
不得补跑实验。

## 4. 服务器必须怎样判读，禁止脑补

按以下优先级读取结果：

1. `resource_recovery_summary.json`：操作恢复真值；必须报告 stop/restart exit、stopped/restored IDs、
   marker count、expected count、marker card IDs、coverage、八卡健康、7000、vLLM residual、tracked-clean。
2. `residency_gate_timeline.json`：实验时序真值；必须报告 initial/best/trigger/post-abort gate、
   pressure start/trigger/abort/client exit/idle/restore 的 monotonic ns。
3. `h2d_trigger_summary.json`：H2D 机制证据；报告 D2H、CPU hit/load、H2D workers/bytes/completion。
4. `grading_summary.json`：同时报告 `experimental_grade`、`operational_grade`、`server_grade`，不得只报
   被 cleanup/recovery 覆盖的 server grade。

逻辑键空间最少必须回报：

~~~text
configured_target_block_count
request_hash_candidate_count
target_capture_source
target_capture_cardinality_exact
target_keyspace_matchable
target_capture_exact
logical_restore_match_tokens
logical_restore_window_exact
target_count_unit
cpu_target_count_unit
gpu_target_count_unit
target_pool_key_count_unit
cpu_target_block_count
gpu_target_block_count
target_pool_key_count
cpu_target_pool_key_match_count
gpu_target_pool_key_match_count
restore_group_count
restore_group_rows（只报每组 bounded count，不报 hash/block/request ID）
~~~

合法终态：

- 若始终没有 `logical_restore_match_tokens=16384`：记录
  `pressure_completed_without_trigger`；这只是这一次固定生命周期未观察到，不得宣称 accepted
  capacity 不可能形成完整窗口。
- 若完整窗口出现但 abort/client exit/idle/post-abort gate 任一不精确：按对应 RED 终态停止。
- 只有 post-abort gate 仍为 `trigger_ready` 才可发送唯一 restore follower。
- 只有 restore CPU hit、load scheduled、8 个 H2D worker 完成和 load request completed 全部成立，才可
  给出 H2D mechanism candidate；不得给 performance 或唯一根因结论。

请求计数必须分别报告：`request_count`、`http_transport_success_count`、
`contract_completed_role_count`、`intentional_pressure_abort_count`、
`pressure_full_response_without_trigger_count`、`request_retry_count=0`。

## 5. 完整有界回报和传输门

最终一次性回报：

1. HEAD、origin/main、ahead/behind、tracked-clean；
2. 五个 parent SHA-256 与 parent grade；
3. pytest、py_compile、bash -n、audit-only 的命令/退出码/关键合同字段；
4. lifecycle/request/transport/contract outcome 全部计数；
5. 逻辑键空间字段与 best near-miss/trigger 的 bounded group counts；
6. trigger/abort/idle/post-abort/restore 的精确顺序与延迟；
7. D2H/H2D worker、bytes、pipeline、completion 与三种 grade；
8. cleanup、7000、vLLM residual、八卡健康、stopped/restored IDs、真实 marker 验证；
9. `result_summary.md` 绝对路径；
10. 完整候选清单：每个文件的 bytes、完整 SHA-256、sensitivity；总文件数与总 bytes 双校验。

bounded package 总计不得超过 71680 bytes。不得放入生成内容、请求体、request ID、token ID、原始
hash、raw vLLM log/trace；大文件只留服务器，回报绝对路径。若包超限，先原位压缩摘要字段而不是
遗漏清单。

候选 manifest 必须显式报告 `payload_file_count`、`transfer_file_count_including_manifest`、
`candidate_total_bytes` 与上限校验。

`result_transfer_authorized: true` 仅表示这个完整 bounded package 有资格传输，不代表已经选定渠道。
必须先展示完整清单、exact result-summary path、每文件 bytes/SHA-256/sensitivity、可用
`email / upload-api / server-local` 三种方法及推荐理由，然后暂停等待用户明确选择一种方法。
不得先发状态邮件，不得自动上传，不得失败后自动换渠道。

回报完成后暂停；不得自行进入任何下一任务。
