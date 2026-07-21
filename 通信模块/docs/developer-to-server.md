# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R4-R1 修复 source binding 假阴性并重放同一离线收口

~~~text
task_id: p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721
execution_mode: authorized_read_only_r4_parent_validation_and_same_evidence_offline_source_semantics_replay
server_sync_review_authorized: true
parent_r4_result_read_authorized: true
parent_bounded_evidence_read_authorized: true
parent_raw_evidence_read_authorized: true
frozen_source_semantics_audit_authorized: true
same_evidence_offline_refinalization_authorized: true
offline_refinalization_authorized: true
raw_trace_attribution_authorized: true
result_directory_creation_authorized: true
npu_execution_authorized: false
keep_alive_stop_authorized: false
vllm_server_start_authorized: false
model_requests_authorized: false
formal_model_lifecycle_count_exact: 0
model_request_count_exact: 0
runtime_overlay_authorized: false
runtime_behavior_patch_authorized: false
capacity_search_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
runtime_or_dependency_mutation_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
next_task_authorized: false
formal_h2d_trigger_lifecycle_allowed: false
k2_authorized: false
p8_3_i1_authorized: false
no_k2_k3_k4_p8_3_i1_p8_4_p8_5_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

## 0. 已接受事实、R4 首错和本轮边界

已关闭门只作 provenance，不得重跑或改写：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p6_3c_not_strict_single_variable
blocked_p8_2_k1_frozen_stack_import_incompatible
ready_p8_2_k1a_r2_allocator_capacity
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
R2 hybrid-KV repair preserved
SimpleCPUOffloadConnector selected path
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
~~~

已执行的 causal lifecycle 与 R4 离线任务都不得重跑为新 runtime：

~~~text
runtime_parent_task_id=p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720
runtime_parent_server_grade=red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete
parent_server_grade=red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete
runtime_parent_model_lifecycle_count=1
runtime_parent_model_request_count=6
developer_refinalized_grade=yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore
runtime_parent_transport_success_count=6
parent_transport_success_count_after_developer_refinalization=6
runtime_parent_producer_success_count=5
runtime_parent_d2h_store_complete=true
parent_d2h_store_complete=true
runtime_parent_d2h_bytes_total=7239534592
runtime_parent_h2d_restore_complete=false
parent_h2d_restore_complete=false
r4_task_id=p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720
r4_server_grade=blocked_p8_2_k1a_r4_offline_closeout_gate
r4_store_only_refinalization_accepted=true
r4_trace_attribution_gate=pass
r4_source_semantics_gate=fail
r4_npu_started=false
r4_vllm_started=false
r4_model_request_sent=false
~~~

R4 唯一失败是 tracked source auditor 的字符串假阴性。冻结 vLLM
`BlockPool.get_new_blocks()` 使用
`self.free_block_queue.popleft_n(num_blocks)`，旧审计只接受 `.popleft(`；随后真实源码仍逐 block
调用 `_maybe_evict_cached_block`，并通过 `cached_block_hash_to_block.pop` 移除旧 hash。因此：

- 修复后的 source 语义应支持 capacity churn 作为候选机制；
- parent lifecycle 没有 CPU tier occupancy/eviction 事件，不能证明 pressure 实际淘汰 prime；
- restore follower 的 CPU hit/load/H2D 仍为零；repeat follower 的 `16384` GPU Prefix hit 只支持
  restore 重算后再次命中，不能证明 prime 在 restore 时仍驻留；
- `7239534592` 仍是累计 submitted copy volume，不是唯一 CPU residency；
- 本轮 candidate green 只关闭离线 store-only 证据，不是 store→restore runtime green。

P8.3-I0 / P8.3-I0-R1 的 inventory/taxonomy green 只保留既有边界；本轮不得进入 K2，
不得进入 P8.3-I1，也不得把 Expert/TP4 线并入本任务。

## 1. 同步、冻结仓库合同与零资源前门

服务器只从当前干净 `main` 做普通 fast-forward 同步；不得 reset、stash、rebase、server commit
或 push。同步后报告 HEAD、`origin/main`、ahead/behind 和 tracked status。服务器本地未跟踪产物
只按 `--untracked-files=no` 边界保留，不删除。

同步后的下列文件必须逐项匹配：

~~~json
{
  "benchmarks/deepseek_v4_flash/p8_2_k1a_r4_r1_source_semantics_replay_audit.yaml": "cd0fae1a26d98b8d9c6c7519ff15775477621c198cde2a32bae8e52c72309ee9",
  "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r4_r1_store_only_source_semantics_replay.yaml": "3f6200e92a853da4e3d8ce61da5a06f374b9858960eef3348c35b731a8968ef4",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7",
  "tools/inference_contracts/p8_2_k1a_trace_attribution.py": "7c022940cf28e705ec9af66942b66a5182abf722edb43f4d9c2dc3e2bc47acbc",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r4_r1_offline_closeout.sh": "7547e3c51749303917ddf0b707977d482bd8afffa4270a723b684f1aa196f4bf",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r4_store_only_refinalization.py": "0242699627454f6b10f1c373fedaff0463e98a99d18cd10021d5584d817581c9",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r4_r1_source_semantics_replay.py": "ae64c2e9fd3a9513cb99dbc55ed6dad2065318c0d12befd37050422f0db18f58"
}
~~~

执行仓库合同：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_simple_cpu_offload_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_formal_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r4_store_only_refinalization.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r4_r1_source_semantics_replay.py -q

python3 -m py_compile \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py \
  tools/inference_contracts/p8_2_k1a_trace_attribution.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r4_r1_offline_closeout.sh

P8_2_K1A_R4_R1_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r4_r1_offline_closeout.sh \
  > /tmp/opencode/p8_2_k1a_r4_r1_audit_only.txt
grep -Fx 'expected_dequeue_method=popleft_n' /tmp/opencode/p8_2_k1a_r4_r1_audit_only.txt
grep -Fx 'npu_execution_authorized=false' /tmp/opencode/p8_2_k1a_r4_r1_audit_only.txt
grep -Fx 'model_requests_authorized=false' /tmp/opencode/p8_2_k1a_r4_r1_audit_only.txt
grep -Fx 'result_transfer_authorized=true' /tmp/opencode/p8_2_k1a_r4_r1_audit_only.txt
grep -Fx 'next_task_authorized=false' /tmp/opencode/p8_2_k1a_r4_r1_audit_only.txt
~~~

任一失败立即停止为 `blocked_p8_2_k1a_r4_r1_repository_contract_gate`，不创建正式结果根。

本任务全程零 NPU。开始前只读记录 keep-alive marker PID/PGID、8 卡健康/HBM、7000 端口、
推理服务进程与 tracked status；结束后重复并要求一致。不得停止或恢复 keep-alive。

## 2. 精确复核已执行 R4 blocked package

冻结 parent R4 根：

~~~text
PARENT_R4_RESULT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720_run01
parent_payload_file_count=9
parent_payload_total_bytes=27943
parent_grade=blocked_p8_2_k1a_r4_offline_closeout_gate
parent_store_only_refinalization_accepted=true
parent_trace_attribution_gate=pass
parent_source_semantics_gate=fail
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
~~~

R4-R1 runner 会先验证 parent R4 的 manifest、九个 payload 的 path/bytes/SHA-256/sensitivity、
grade 和三个 gate。任一 payload 缺失、漂移或字段不符时停止为
`blocked_p8_2_k1a_r4_r1_parent_r4_gate`；不得修改旧 R4 结果。

同时复核下列 R4 机器结论：

- 6/6 transport、5/6 producer；store-only yellow 保留；
- trace event=`3060`，prime/pressure/restore/repeat 的 D2H event index 分别为
  `0-4 / 5-27 / 28-32 / 33-35`；
- restore CPU hit/load/H2D 都为零，repeat GPU Prefix hit=`16384`；
- `unique_cpu_residency_bytes_observed=false`；
- `pressure_evicted_prime_from_cpu_tier_proven=false`；
- `prime_blocks_resident_at_restore_proven=false`；
- `h2d_absence_cause_proven_as_unique=false`。

## 3. 运行同一证据的 R4-R1 全量离线重放

只允许一个 fresh 结果根：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721_run01
test ! -e "${RESULT_ROOT}"

cd "${REPO_ROOT}"
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r4_r1_offline_closeout.sh "${RESULT_ROOT}"

test -f "${RESULT_ROOT}/grading_summary.json"
test -f "${RESULT_ROOT}/candidate_manifest.server_local.json"
test "$(cat "${RESULT_ROOT}/task_grade.txt")" = candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
~~~

runner 必须依次完成：

1. 验证旧 R4 blocked package 而不修改它；
2. 从原 causal parent 的同一 `21 payload + manifest` 重算 bounded refinalization；
3. 从同一 raw result tree 重算六请求 window/gap trace attribution，并证明 source tree 前后不变；
4. 对同一 exact-hash 冻结 vLLM source 重做 source audit；
5. 结构化输出 `free_block_queue_dequeue_method=popleft_n`、
   `cpu_pool_allocation_may_evict_cached_hash_entry=true`、
   `capacity_churn_hypothesis_supported=true`；
6. 联合分级并生成 bounded manifest。

若 parent、raw window、source hash、source 语义、source tree 或联合门任一失败，保留首错并定级
`blocked_p8_2_k1a_r4_r1_offline_closeout_gate`。不得现场修改仓库、冻结 source、raw evidence、
时间戳或 runtime 以绕过。

## 4. R4 与 R4-R1 差异审计

必须报告并用 JSON 支撑：

- 不受修复影响的 refinalization 与 trace 五个 payload 是否逐字节一致；
- old source audit 的 false 字段与 new source audit 的 true 字段；
- new source audit 的 exact dequeue method 是否为 `popleft_n`；
- source hash 是否仍为 manager=`fdcb18a6...`、block pool=`36a1683a...`；
- R4 blocked grade 是否完整保留；
- R4-R1 candidate grade 是否仅来自 source matcher 修复后的同证据离线重放；
- actual CPU eviction、H2D restore、unique cause、performance reference 是否仍全部为 false。

允许用只读字节比较确认下列五项 old/new 一致：

~~~bash
set -euo pipefail

OLD=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720_run01
NEW=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721_run01

cmp "${OLD}/refinalization/offline_refinalization.json" "${NEW}/refinalization/offline_refinalization.json"
cmp "${OLD}/refinalization/corrected_request_summary.tsv" "${NEW}/refinalization/corrected_request_summary.tsv"
cmp "${OLD}/refinalization/source_evidence_provenance.json" "${NEW}/refinalization/source_evidence_provenance.json"
cmp "${OLD}/trace_attribution/trace_attribution_summary.json" "${NEW}/trace_attribution/trace_attribution_summary.json"
cmp "${OLD}/trace_attribution/trace_source_provenance.json" "${NEW}/trace_attribution/trace_source_provenance.json"
~~~

如果这些不一致，不得笼统接受 candidate green；先报告具体文件和首个差异字段，保持 blocked。

## 5. 分级、零资源收尾与完整传输范围

允许的最终 grade 只有：

- `candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout`：同一 bounded/raw evidence 的
  refinalization、trace 与修复后的 frozen source semantics 全部闭合；
- `blocked_p8_2_k1a_r4_r1_offline_closeout_gate`：任一 parent/source/provenance/joint gate 失败。

即使 candidate green，也必须同时声明：

~~~text
npu_started=false
vllm_started=false
model_request_sent=false
keep_alive_disrupted=false
parent_r4_grade_preserved=true
store_only_refinalization_accepted=true
source_semantics_false_negative_repaired=true
free_block_queue_dequeue_method=popleft_n
actual_cpu_eviction_proven=false
h2d_restore_mechanism_accepted=false
cause_proven_as_unique=false
performance_reference_accepted=false
formal_h2d_trigger_lifecycle_allowed=false
k2_authorized=false
p8_3_i1_authorized=false
next_task_authorized=false
~~~

结果白名单为 runner manifest 中的 9 个白名单 bounded metadata payload，即
`9 payload + candidate_manifest.server_local.json`，所以完整传输
范围必须是 10 个文件，而不是只发送 9 个 payload。报告时逐项给出 relative/absolute path、bytes、
SHA-256、sensitivity，并另外给出 manifest 自身 bytes/SHA-256；完整 10-file 总量与每个文件都必须
不超过 `71680 bytes`。raw logs/metrics/traces/request bodies、generated content/token IDs 留服务器。

`result_transfer_authorized:true` 仅表示这 10 个文件可供用户选择，不是自动发送授权。先报告
RESULT_ROOT、完整 10-file 清单、总量、可用 `email / upload-api / server-local` 以及一个推荐方法，
然后等待用户对该完整范围选择唯一渠道。未选择前不外发；失败后不得自动换渠道。

完成报告后停止等待。不得连续进入新的 H2D-trigger lifecycle、K2、P8.3-I1 或其他阶段。
