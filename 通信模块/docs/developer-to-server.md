# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-L1 accepted-capacity lazy H2D trigger 单生命周期

~~~text
task_id: p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721
execution_mode: authorized_accepted_capacity_single_lazy_dynamic_pressure_h2d_trigger_lifecycle
server_sync_review_authorized: true
parent_r5_f0_and_r2_provenance_read_authorized: true
frozen_source_and_installed_runtime_audit_authorized: true
result_directory_creation_authorized: true
npu_execution_authorized: true
keep_alive_stop_and_restore_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
formal_model_lifecycle_count_max: 1
model_request_count_min: 4
model_request_count_max: 8
pressure_request_count_max: 5
request_retry_count_exact: 0
runtime_overlay_authorized: true
runtime_behavior_patch_authorized: false
capacity_search_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
runtime_or_dependency_mutation_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
next_task_authorized: false
k2_authorized: false
p8_3_i1_authorized: false
no_k2_k3_k4_p8_3_i1_p8_4_p8_5_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

这是一次完整但有界的正式机制实验，不是简单 smoke。任务同时关闭 repository/source/provenance、运行时
身份、资源、安全清理、动态 trigger、D2H/H2D 八 worker 链和 bounded package 七类证据门；仍只允许一个
model lifecycle。`result_transfer_authorized:true` 只表示小结果包可以进入渠道选择，不是自动上传或发邮件的命令。

## 0. 已接受事实、实验问题和不可变边界

以下历史事实只作 provenance，不重跑、不撤销：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p6_3c_not_strict_single_variable
blocked_p8_2_k1_frozen_stack_import_incompatible
ready_p8_2_k1a_r2_allocator_capacity
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
~~~

R5-L1 继承但不改写的直接 parent/source provenance：

~~~text
parent_server_grade=red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete
parent_developer_grade=yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore
parent_transport_success_count_after_developer_refinalization=6
parent_d2h_store_complete=true
parent_h2d_restore_complete=false
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
~~~

R5-L1 在正式 lifecycle 前先精确重放 R4-R1 bounded package，并精确重放 R2 geometry/rendezvous/allocator。
R5-F0 已由开发机独立复核：下载包为 `9 files / 7122 bytes`；eager path 因 accepted CPU tier 的
capacity churn 被拒绝；lazy path 只形成 runtime candidate。R5-L1 仅回答：在冻结的 W8A8、TP8+EP、MTP、
R2 repair、Prefix Cache/Chunked Prefill enabled、`430604288 bytes/rank` 下，能否先观测 target
`CPU-present + GPU-absent`，再完成真实 CPU hit/load 和 8-worker H2D restore。

本任务明确采用 `P8.2-K1A-R5-L1`：`F0` 是 feasibility，`L1` 是首个 formal lazy lifecycle。禁止把
`5` 个 pressure request 当成固定运行事实；它只是上限。controller 每次只发送一个独立 pressure，读取
observe-only residency gate 后再决定继续或停止。target 从 CPU tier 丢失、状态不可判、请求失败，或到
`pressure_05` 仍未形成 trigger 时，均不发送 restore。

candidate green 仍只是服务器候选。开发机必须独立复核结果包后才能接受 H2D mechanism green；它不形成
性能 reference、优化收益、唯一根因、K2 或 P8.3-I1 授权。

## 1. 同步、tracked-clean 与冻结仓库合同

服务器只允许从干净 `main` 普通 fast-forward。不得 reset、stash、rebase、cherry-pick、运行 `sync.sh`、
server commit 或 push；未跟踪服务器产物在 `--untracked-files=no` 边界保留，不删除。

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

同步后，先执行下列仓库合同；正式结果根此时必须尚不存在。任一失败定级
`blocked_p8_2_k1a_r5_l1_repository_contract_gate`，不得停止 keep-alive。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721_run01
cd "${REPO_ROOT}"
test ! -e "${RESULT_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r4_r1_source_semantics_replay.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_l1_lazy_h2d_lifecycle.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh

P8_2_K1A_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh \
  "${RESULT_ROOT}" > /tmp/opencode/p8_2_k1a_r5_l1_top_audit.txt
P8_2_K1A_MODE_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh \
  "${RESULT_ROOT}" > /tmp/opencode/p8_2_k1a_r5_l1_mode_audit.txt

grep -Fx 'task_id=p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721' /tmp/opencode/p8_2_k1a_r5_l1_top_audit.txt
grep -Fx 'lifecycle_count=1' /tmp/opencode/p8_2_k1a_r5_l1_top_audit.txt
grep -Fx 'request_count_min=4' /tmp/opencode/p8_2_k1a_r5_l1_top_audit.txt
grep -Fx 'request_count_max=8' /tmp/opencode/p8_2_k1a_r5_l1_top_audit.txt
grep -Fx 'npu_execution_authorized=true' /tmp/opencode/p8_2_k1a_r5_l1_top_audit.txt
grep -Fx 'lazy_offload=true' /tmp/opencode/p8_2_k1a_r5_l1_mode_audit.txt
grep -Fx 'server_command_sha256=89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f' /tmp/opencode/p8_2_k1a_r5_l1_mode_audit.txt
grep -Fx 'observer_mode=observe_only_with_controller_role_marker_no_runtime_decision_or_copy_mutation' /tmp/opencode/p8_2_k1a_r5_l1_mode_audit.txt
~~~

冻结 repo 文件 SHA-256 由本次发布最终值填写在这里，服务器必须逐项验证后再进入 Section 2：

~~~json
{
  "benchmarks/deepseek_v4_flash/p8_2_k1a_r5_l1_lazy_h2d_lifecycle_audit.yaml": "a53876a6daa3d754c56bb8d26963e4bf6c4dc3d8a9c9f2b537bfb6a54b890642",
  "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle.yaml": "816b4945ebb35c3df7e93f1f4b39290fa8db9e13f53ef3d5c023debe0ed6f454",
  "tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py": "0c7a4ae499d64c1e40abbaa0f869e9ccbe9147ad4d11182e7a0c0ef701f4ab01",
  "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py": "81bd77401c74037220d1dff3582888761802df8e55c96cc97f3ab50ace9af0aa",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh": "60aa6ad5f01e8c574b7497f48382b23fa1b10ef03a078b818e08f812491a6486",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh": "0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "d1c874110847d927f832b2675f12642e704bab8bff5b5f16b2b82c1a37c6d0dd",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r5_l1_lazy_h2d_lifecycle.py": "f3d7317bf45235afda77890214c6496ec05504f3fa321d29121b5866211125be",
  "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch": "5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6"
}
~~~

## 2. 零 NPU provenance/source/import/observer 前门

本节仍不得停止 keep-alive、启动 vLLM 或发请求。先验证：

1. server-local R5-F0 根存在，manifest SHA-256 为
   `d9b5c157ff2ef0804a3cbc01bbb8ab17c6897600efaf484a47dbd6c6bfe1d0b8`，grade 为
   `candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility`，9 文件总量 7122 bytes；
2. R2 geometry/rendezvous/allocator 的三个既有 SHA-256 仍分别为
   `8430730a...`、`fa258790...`、`99f997a6...`，且 world/rank/capacity 闭合；
3. frozen vLLM commit=`0decac0d96c42b49572498019f0a0e3600f50398`，安装态 vLLM-Ascend 内容仍通过既有
   9-file source hash gate；不得要求不存在的 Ascend checkout；
4. `SimpleCPUOffloadConnector` registration、Ascend connector override、worker/copy backend import、R2 hybrid
   multi-group repair 和 MTP overlay 的只读 probe 全过；
5. H2D observer self-test 必须声明原 return/exception 保留、不改变 scheduler decision/request order/copy args，
   不输出 raw hash、generated content 或 token IDs；
6. controller role marker 只含 `role/schema/timestamp`。服务端随机 request ID 仅作诊断，不作为
   target/restore 合同身份。

用服务器现有 R2 hash-first resolver 查找三份唯一 evidence；零个或多个匹配都 fail closed。R5-F0 package、
R2 evidence 和 frozen source 全部只读，不得修改旧结果根、checkpoint、site-packages 或 source checkout。

本节任一失败定级 `blocked_p8_2_k1a_r5_l1_source_or_provenance_gate`，保持 keep-alive 原样并停止。

## 3. 资源前门、keep-alive 安全暂退与恢复责任

先记录：tracked HEAD/status、7000 端口、vLLM process、8 卡健康/HBM、系统 MemAvailable/swap，以及 keep-alive
所有 marker PID/PGID/设备号。资源门要求 model path 可读、端口空闲、无残留 vLLM、8 卡健康、
MemAvailable 不低于既有 `384 GiB` 门且 swap 未用。

只允许终止已确认完全属于官方 keep-alive 的 process group。必须先证明其 marker 覆盖 `#0#..#7#`、没有
混入未知命令；若 provenance 不完整，定级 `blocked_p8_2_k1a_r5_l1_source_or_resource_gate`，不得发送信号。
不得触碰 unattended-upgrades 或任何无关进程。

安全暂退后必须确认 16 个 marker 归零、8 卡均显示无运行进程、AICore 0、7000 端口空闲，然后才允许
唯一 lifecycle。无论后续成功或失败，都必须在退出前运行：

~~~bash
set -euo pipefail
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

恢复后要求 16 marker、设备 `#0#..#7#`、8 卡健康、7000 空闲、vLLM residual=0、tracked clean；写入
`${RESULT_ROOT}/resource_recovery_summary.json`，字段至少包含：

~~~json
{
  "keep_alive_restored_exact": true,
  "port_7000_free": true,
  "vllm_residual_process_count": 0,
  "all_eight_npu_healthy": true,
  "tracked_worktree_clean": true
}
~~~

## 4. 唯一 formal lifecycle：lazy + 动态 pressure + 条件式 restore

本任务固定 `lazy_offload=true`、`cpu_bytes_to_use=3444834304`、
`cpu_bytes_to_use_per_rank=430604288`。其余 server argv 与已接受主线相同：W8A8、TP8+EP、MTP
`num_speculative_tokens=1`、`FULL_DECODE_ONLY`、`max_model_len=135168`、
`max_num_batched_tokens=4096`、`max_num_seqs=1`、block size 128、Prefix Cache 与 Chunked Prefill enabled、
同 R2 hybrid-KV repair。禁止调参、eager fallback、容量搜索、第二 patch、第二 lifecycle 或 retry。

先准备全部 8 个冻结 body：warmup、target prime、pressure_01..pressure_05、restore follower。每个 body 的
token count/bytes/SHA-256 在 server 启动前冻结；pressure bodies 与 target 不共享 cacheable block；restore 与
target 的实际 LCP 保持 16384 tokens。generated text/token IDs 不写入结果。

执行 wrapper 一次。wrapper 只准备 body、启动唯一 server lifecycle 并运行动态 controller；finalize 被刻意延后到
keep-alive 恢复以后：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721_run01
cd "${REPO_ROOT}"
test ! -e "${RESULT_ROOT}"

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh "${RESULT_ROOT}"
MODE_OR_CONTROLLER_EXIT=$?
set -e
printf '%s\n' "${MODE_OR_CONTROLLER_EXIT}" > "${RESULT_ROOT}/initial_runner_exit_code.txt"
~~~

controller 顺序严格为：

~~~text
warmup
target_prime
pressure_01
读取 residency gate
若 target CPU-present + GPU-absent -> restore_follower
否则依次 pressure_02 ... pressure_05，每次只发一个并重新读取 gate
若 CPU target lost / unobservable / request failure / pressure_05 后仍未 trigger -> 停止，不发 restore
~~~

controller role marker 是测试控制面，不是 runtime 决策 patch；observer 仍不改变 scheduler、request order 或 copy
参数。target hash 值只留在 engine 内存，不写文件；输出只含 64-block count 和 CPU/GPU residency count。

每个已发送请求必须 HTTP 200、prompt/generated/streamed token 精确、finish reason=`length`、SSE done、MTP
activity、health/queue/counter continuity 全过。任一请求失败首错停止，无 retry。

## 5. 延后 finalization、分级与首错保留

mode runner 的 trap 必须先停止 vLLM、释放 7000 并写 `cleanup_status.txt=clean`；随后按 Section 3 恢复
keep-alive 并写 `resource_recovery_summary.json`。最后才运行一次正式 finalizer：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721_run01
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
cd "${REPO_ROOT}"

set +e
"${PYTHON_BIN}" tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py \
  finalize --artifact-dir "${RESULT_ROOT}"
FINALIZE_EXIT=$?
set -e
printf '%s\n' "${FINALIZE_EXIT}" > "${RESULT_ROOT}/finalize_exit_code.txt"
~~~

分级：

- provenance/source/resource 前门失败：`blocked_p8_2_k1a_r5_l1_source_or_resource_gate`；
- 无成功请求：`red_p8_2_k1a_r5_l1_lazy_h2d_no_success`；
- target 从 CPU tier 丢失：`red_p8_2_k1a_r5_l1_cpu_target_lost`；
- 到 pressure 上限仍未触发：`yellow_p8_2_k1a_r5_l1_trigger_not_reached`；
- 请求可用但 D2H/H2D/residency/cleanup 任一链不完整：`red_p8_2_k1a_r5_l1_h2d_evidence_incomplete`；
- 只有所有实际请求首次成功、restore 严格晚于 CPU-only trigger、target GPU eviction、16K CPU hit/load、
  D2H/H2D 8-worker submit/enqueue/copy-enter/copy-return/poll/complete、load completion、repair/health/queue、
  cleanup 与 keep-alive restore 全过，才给
  `candidate_green_p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle`。

candidate green 不证明 CPU tier 自身发生 eviction，也不证明唯一根因或性能收益。服务器不得自行接受 developer
green，不得继续 K2/P8.3-I1。

## 6. 小结果包、完整清单和传输停点

raw vLLM log、metrics、request bodies、raw trace、active role marker、generated output/token IDs 留服务器。候选范围最多
16 files（15 payload + manifest；第 15 个 payload 只可能是失败摘要），含 manifest 的总量必须不超过 71680 bytes，全部标记
`bounded_operational_metadata_no_content_or_token_ids`。候选 payload 可包括：

~~~text
result_summary.md
environment_and_hashes.json
request_body_manifest.json
request_summary.tsv
residency_gate_timeline.json
h2d_trigger_summary.json
transfer_trace_summary.json
connector_resolution_summary.json
mtp_queue_health_summary.json
repair_diagnostic_summary.json
host_memory_summary.json
grading_summary.json
cleanup_status.txt
resource_recovery_summary.json
first_failure_excerpt.txt（仅失败时）
candidate_manifest.server_local.json（控制文件）
~~~

`environment_and_hashes.json` 必须实际记录 task_id、HEAD、origin/main、ahead/behind、tracked-clean、版本/commit、
canonical argv SHA、repo file hashes 和 source hashes，避免聊天表格丢字段。

任务完成后只报告：精确 RESULT_ROOT、grade、首错、实际 pressure/request 数、每项机制门、清理恢复状态，以及
完整候选清单的逐文件 relative path/bytes/SHA-256/sensitivity 和总量。然后列出
`email / upload-api / server-local` 三种方法并推荐一种；在用户针对这份完整范围明确选择前，不得外发。不得预先执行 upload-api、
不得发状态邮件、不得失败后自动换渠道。

## 7. 完成后的等待状态

报告完成后保持：

~~~text
next_task_authorized=false
k2_authorized=false
p8_3_i1_authorized=false
performance_reference_accepted=false
cause_proven_as_unique=false
~~~

不得进入 K2，不得进入 P8.3-I1。不要因为 R5-L1 blocked/red/yellow 撤销 P6.3B-R4-R1、P8.1-R1、P8.2-K0、R2 capacity、R4-R1
store-only 或 R5-F0 feasibility 的既有窄边界结论。
