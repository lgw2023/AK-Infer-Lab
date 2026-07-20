# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R4 store-only 离线收口、raw trace 归因与冻结 source 语义审计

~~~text
task_id: p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720
execution_mode: authorized_read_only_offline_store_only_refinalization_trace_attribution_and_source_semantics
server_sync_review_authorized: true
parent_bounded_evidence_read_authorized: true
parent_raw_evidence_read_authorized: true
offline_refinalization_authorized: true
raw_trace_attribution_authorized: true
frozen_source_semantics_audit_authorized: true
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

## 0. 开发机结论与本轮目标

已关闭门只作 provenance，不得重跑或改写：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p6_3c_not_strict_single_variable
blocked_p8_2_k1_frozen_stack_import_incompatible
ready_p8_2_k1a_r2_allocator_capacity
R2 hybrid-KV repair preserved
SimpleCPUOffloadConnector selected path
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
P8.3-I0 / P8.3-I0-R1 closed within inventory/taxonomy boundaries
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
~~~

上轮任务已消费，不得重跑。必须保留其已执行结果：

~~~text
parent_task_id=p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720
parent_server_grade=red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete
parent_formal_model_lifecycle_count=1
parent_model_request_count=6
parent_producer_status_success_count=5
parent_transport_success_count_after_developer_refinalization=6
parent_d2h_store_complete=true
parent_d2h_worker_count=8
parent_d2h_completed_worker_count=8
parent_d2h_bytes_total=7239534592
parent_store_event_completed_count=41
parent_h2d_restore_complete=false
parent_h2d_worker_count=0
parent_h2d_bytes_total=0
parent_cleanup=clean
parent_keep_alive_restored=true
~~~

开发机已对下载包的 `22 files / 50428 bytes` 做 bytes/SHA-256 复核，并用修复后的
grader 对同一 bounded evidence 离线重算：六请求全部 HTTP 200、prompt/generated/streamed
token 精确、finish/SSE/MTP/health/queue/counter 闭合。`restore_follower` 的 producer
`status=failed` 只来自 `prefix_evidence_ok=false`；原 workload 明确 Prefix 指标不是方向证明。
因此本轮要正式产生：

1. 保留 parent red 的离线重分级：
   `yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore`；
2. 按六个 raw metrics before/after 文件的 wall-clock `mtime_ns` 将 3060 条 trace 分配到
   request window 与 inter-request gap，回答 D2H 何时调度/提交/完成、restore 时是否有
   CPU hit/load；
3. 对冻结 vLLM `0decac0d...` 的 CPU match、eager store、BlockPool 分配/淘汰语义做
   exact-hash source audit，只判断“容量 churn 是否为源码允许的候选解释”；
4. 合并为一个 bounded offline closeout package。

不得把 `7239534592` 写成唯一 CPU 驻留量；这是 8 rank/多次 submit 的累计复制量。
配置 CPU tier 仍是 `3444834304 bytes total / 430604288 bytes per rank`。不得宣称
pressure 已淘汰 prime、prime 仍在 GPU、Prefix hit 等于 H2D，或 H2D 缺失的唯一原因。

本轮直接合同输入必须在执行前逐项匹配：

~~~json
{
  "benchmarks/deepseek_v4_flash/p8_2_k1a_r4_store_only_refinalization_audit.yaml": "a2c7486a94aa8fc8113177ec8fa05d24bff8644d5ef3c686161ad8de0e2d7229",
  "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r4_store_only_refinalization_and_trace_attribution.yaml": "ef906c2a12c16d35a01684b6975614e6ca343a1c30022146ca1d637a0ac32335",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7",
  "tools/inference_contracts/p8_2_k1a_trace_attribution.py": "e81ff6a747615f165249f0938bc9fba32c4166e4771f846aa6846d92da5172ec",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r4_offline_closeout.sh": "cc70baca33d40df0040b80fee7918c50258d876efbfaf09031ee3c37cbdce2a8",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r4_store_only_refinalization.py": "ebadf3f114d647283be88653cb35d040c99305723e52ee9fb526c0404aca43bd"
}
~~~

## 1. 同步、仓库合同与零资源门

从当前干净 `main` 执行普通 fast-forward 同步；不得 reset、stash、rebase、server commit
或 push。同步后报告 HEAD、`origin/main`、ahead/behind 和 tracked status。服务器本地未跟踪
产物只按 `--untracked-files=no` 边界处理，不删除。

先在仓库根目录执行：

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
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_forensics.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r4_store_only_refinalization.py -q

python3 -m py_compile \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py \
  tools/inference_contracts/p8_2_k1a_trace_attribution.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r4_offline_closeout.sh
P8_2_K1A_R4_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r4_offline_closeout.sh \
  > /tmp/opencode/p8_2_k1a_r4_audit_only.txt
grep -Fx 'npu_execution_authorized=false' /tmp/opencode/p8_2_k1a_r4_audit_only.txt
grep -Fx 'model_requests_authorized=false' /tmp/opencode/p8_2_k1a_r4_audit_only.txt
grep -Fx 'result_transfer_authorized=true' /tmp/opencode/p8_2_k1a_r4_audit_only.txt
grep -Fx 'next_task_authorized=false' /tmp/opencode/p8_2_k1a_r4_audit_only.txt
~~~

任一失败立即停止，级别为 `blocked_p8_2_k1a_r4_repository_contract_gate`。此时不创建正式
RESULT_ROOT，不触动 keep-alive，不进入后续节。

本任务全程是零 NPU。开始前只记录 keep-alive marker 数/PGID、8 卡健康与 HBM、7000 端口、
vLLM process 和 tracked status；结束后重复同一组读取并要求完全不变。不得停止或恢复
keep-alive，不得占卡。

## 2. parent bounded package 跨结果根精确重放

冻结输入：

~~~text
manifest_root=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_2026_0720_run01
manifest_path=${manifest_root}/candidate_manifest.server_local.json
manifest_bytes=9243
manifest_sha256=6463f2f13e5c7149e6fcbb502caad5edfce1f9b7d82c16c74a72babd64035498
payload_file_count=21
payload_total_bytes=41185
combined_file_count=22
combined_total_bytes=50428
raw_result_root=/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/p8_2_k1a_r3_r2_r2_r1_r1_r1_deepseek_v4_flash_causal_exception_replay_2026_0720_run01
~~~

manifest 的 21 个 payload 分布在 `server_local` 与 runtime result 两个根。不得用 basename 猜路径；
runner 会优先使用 manifest 同目录的已下载合并包，否则逐条使用 manifest 冻结的
absolute path。必须逐文件验证 bytes/SHA-256/sensitivity，并确认 generated content/token IDs
均为 false。任一文件缺失、重名、hash 漂移或 manifest 计数不等时定级
`blocked_p8_2_k1a_r4_parent_evidence_gate`，不改 parent。

## 3. 一次执行离线重分级、trace 归因、source audit 与联合分级

只允许一个新结果根：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720_run01
test ! -e "${RESULT_ROOT}"

cd "${REPO_ROOT}"
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r4_offline_closeout.sh "${RESULT_ROOT}"

test -f "${RESULT_ROOT}/grading_summary.json"
test -f "${RESULT_ROOT}/candidate_manifest.server_local.json"
test "$(cat "${RESULT_ROOT}/task_grade.txt")" = candidate_green_p8_2_k1a_r4_offline_store_only_closeout
~~~

runner 必须按顺序完成：

1. `refinalization/`：从 bounded package 重算 6/6 request transport evidence，保留 producer 5/6
   与 parent red，只把机制级收口为 full-lineage store-only yellow；
2. `trace_attribution/`：从 raw request/metrics/trace 只读生成六个 request window、五个
   inter-request gap 与 outside-window 汇总，分 role/direction/event/event_idx 计数和累计 submit
   bytes；前后 full-tree inventory 必须 byte-identical；
3. `source_semantics/`：要求
   `manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b`
   且
   `block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283`，
   再确认 CPU match 使用 `find_longest_cache_hit`、eager store 从 CPU block pool 分配、新分配路径
   可淘汰 cached hash；
4. 联合分级与白名单 manifest。

若 raw metrics 边界缺失/重叠、source hash/语义失败、source tree 改变或联合门不完整，
保留已生成的首错并定级 `blocked_p8_2_k1a_r4_offline_closeout_gate`，不尝试修改 source、
补窗口或发起 runtime replay。

## 4. 必须回答的归因问题

报告必须用机器 JSON 字段支撑下列结论，不得只写自由文本：

- prime、pressure、restore_follower、repeat_follower 各窗口和各窗口后 gap 的
  `transfer_scheduled / device_copy_submitted / copy_blocks_entered / transfer_completed /
  store_event_completed / cpu_hit_matched / load_scheduled / load_request_completed` 计数；
- 每个 role 的 D2H/H2D event index 集合与累计 submit bytes；
- prime 窗口是否存在 store schedule/completion，pressure 窗口是否又产生大量 D2H；
- restore follower 的 CPU hit/load 是否仍为 0，repeat follower 的 GPU Prefix hit 是否为 16384；
- 是否能从现有 trace 直接观测 CPU tier occupancy 或 eviction；预期必须是 false；
- 冻结 source 是否支持“pressure 新 store 可以淘汰旧 CPU cached hash”这个候选机制；
- 候选机制是否已在 parent lifecycle 中被唯一证明；预期必须是 false。

如果 request-window 时间边界不能稳定覆盖全部关键事件，仍须输出 by-phase 与
outside-window 计数，定级 blocked；不得为了得到想要的归因而修改文件 mtime、trace
timestamp 或请求记录。

## 5. 结果、资源零扰动与外发边界

结果最多为：

- `candidate_green_p8_2_k1a_r4_offline_store_only_closeout`：只表示 parent red 保留、store-only
  yellow 离线收口、raw trace 归因和冻结 source semantics 全部可重放；
- `blocked_p8_2_k1a_r4_offline_closeout_gate`：任一 parent/hash/window/source/provenance 门失败。

即使 candidate green，也不是 K1A store→pressure→restore runtime green，不证明 H2D，不接受
performance reference/优化收益/唯一根因，不解锁 K2 或 P8.3-I1。下一个 H2D-trigger lifecycle
必须由开发机根据本轮结果重新设计并产生新 handoff，本任务不得连续执行。

明确停止边界：不得进入 K2，不得进入 P8.3-I1，也不得启动任何后续模型 lifecycle。

任务结束时必须报告 keep-alive marker PID/PGID 前后一致、8 卡健康/HBM 前后一致、
7000 端口前后一致、vLLM process 前后一致、tracked clean，以及：

~~~text
npu_started=false
vllm_started=false
model_request_sent=false
keep_alive_disrupted=false
parent_runtime_grade_preserved=true
store_only_refinalization_accepted=true|false
formal_h2d_trigger_lifecycle_allowed=false
cause_proven_as_unique=false
performance_reference_accepted=false
k2_authorized=false
p8_3_i1_authorized=false
next_task_authorized=false
~~~

`candidate_manifest.server_local.json` 只能包含 runner 生成的 9 个白名单 bounded metadata
payload，逐文件列 absolute/relative path、bytes、SHA-256、sensitivity，payload 总量和单文件均
不超过 `71680 bytes`。raw log/metrics/trace/request bodies、generated content/token IDs 继续留服务器。

`result_transfer_authorized:true` 只表示完整白名单包可供选择，不是自动外发授权。先报告
RESULT_ROOT、完整候选清单、逐文件 bytes/SHA-256/sensitivity、总量、可用
`email / upload-api / server-local` 及一个推荐方法，然后等用户对这一完整范围选择
唯一渠道。未选择前不外发，失败后不自动切换渠道。
