# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F0 H2D trigger 零资源可行性与观测合同复核

~~~text
task_id: p8_2_k1a_r5_f0_h2d_trigger_feasibility_2026_0721
execution_mode: authorized_read_only_r4_r1_r2_source_observer_and_trigger_feasibility_no_npu
server_sync_review_authorized: true
parent_bounded_evidence_read_authorized: true
r2_geometry_provenance_read_authorized: true
frozen_source_semantics_audit_authorized: true
installed_runtime_import_and_method_resolution_authorized: true
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

`standing_npu_and_vllm_consumption_authorization:true` 不是本任务的 NPU 执行许可。本任务从开始到结束都不得停止
keep-alive、启动 vLLM、占用新的 NPU 资源或发送模型请求。任何前门失败都在零资源处停止，不得把
`result_transfer_authorized:true` 当作自动外发命令。

## 0. 已接受事实、开放问题与本轮产物

以下历史门只作 provenance，不重跑、不撤销：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p6_3c_not_strict_single_variable
blocked_p8_2_k1_frozen_stack_import_incompatible
ready_p8_2_k1a_r2_allocator_capacity
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete
yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore
blocked_p8_2_k1a_r4_offline_closeout_gate
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
~~~

R4-R1 已接受的父证据声明保持不变：

~~~text
parent_server_grade=red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete
parent_transport_success_count_after_developer_refinalization=6
parent_d2h_store_complete=true
parent_h2d_restore_complete=false
cpu_bytes_to_use_per_rank=430604288
~~~

开发机已独立接受 R4-R1，但只接受以下窄边界：

- R4-R1 的 9 payload + manifest 为 `10 files / 32546 bytes`，逐文件 hash/size 与 manifest 一致；
- 同一原始证据的 D2H store-only 离线收口成立；旧 R4 blocked grade 保留；
- `popleft_n` source matcher 假阴性已修复，source 支持 capacity churn 作为候选机制；
- actual CPU eviction、CPU hit/load、H2D restore、unique cause、performance 全部仍未证明；
- R4-R1 不是 store→restore runtime green，也不授权 K2。

R5-F0 只回答“能否为下一次 `SimpleCPUOffloadConnector` H2D trigger lifecycle 写出可审计合同”。它一次完成：

1. 精确重放 R4-R1 bounded package；
2. 精确重放 R2 geometry/rendezvous/allocator；
3. 审计 frozen vLLM scheduler 与 block-pool source semantics；
4. 证明 accepted `128 CPU blocks/rank` 下 eager pressure 为什么不能保住 target；
5. 计算 lazy path 的 candidate trigger geometry，但不把 `5` 个 pressure request 当 runtime 事实；
6. 自检 observe-only CPU/GPU target residency/eviction observer；
7. 只读解析 frozen runtime 方法 owner/signature；
8. 生成 bounded plan、grade、manifest 和零资源前后对照。

candidate ready 仍只表示下一次 lifecycle 可以由开发机另行设计和授权。本任务自身 lifecycle/request 必须为 `0/0`。

## 1. 同步门、仓库冻结合同与唯一任务

服务器从当前干净 `main` 普通 fast-forward；不得 reset、stash、rebase、cherry-pick、server commit、push 或运行
`sync.sh`。未跟踪服务器产物只在 `--untracked-files=no` 边界保留，不删除。

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

同步后逐项核对以下 tracked 文件。这里的 hash 必须从拉取后的文档逐字执行，任一不匹配立即停止为
`blocked_p8_2_k1a_r5_f0_repository_contract_gate`，不得创建正式结果根。

~~~json
{
  "benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f0_h2d_trigger_feasibility_audit.yaml": "f597dc91c1ec842f6fac7ab249980fbc28a98ca98477c01f65fda4cc05c6e6fd",
  "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f0_h2d_trigger_feasibility.yaml": "349fcc4347987f795da3cf1f823a9151b8d0c4bb6ecbdf8a005b20a44d86ab62",
  "tools/inference_contracts/p8_2_k1a_h2d_trigger_feasibility.py": "dec26e965a40fe0bbfcfbb2b2f91bbc8746640732d1237c227fd23eec3df0885",
  "tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py": "29fb97b23bad852b5630f71a961077540a05989a82ec6838d5ae53b61e108504",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.sh": "b357ee1e3d48208bea6725ca8aacfcb899128dc23194b1c56e4c83f4390ad668",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.py": "2fc62089e1a3ef7a468d11297d5ac712b5d616b15d512cf79d19c924182a1c96"
}
~~~

执行仓库合同：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r4_store_only_refinalization.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r4_r1_source_semantics_replay.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_trigger_feasibility.py \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.sh

P8_2_K1A_R5_F0_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.sh \
  > /tmp/opencode/p8_2_k1a_r5_f0_audit_only.txt
grep -Fx 'task_id=p8_2_k1a_r5_f0_h2d_trigger_feasibility_2026_0721' /tmp/opencode/p8_2_k1a_r5_f0_audit_only.txt
grep -Fx 'npu_execution_authorized=false' /tmp/opencode/p8_2_k1a_r5_f0_audit_only.txt
grep -Fx 'formal_model_lifecycle_count=0' /tmp/opencode/p8_2_k1a_r5_f0_audit_only.txt
grep -Fx 'model_request_count=0' /tmp/opencode/p8_2_k1a_r5_f0_audit_only.txt
grep -Fx 'formal_h2d_trigger_lifecycle_allowed=false' /tmp/opencode/p8_2_k1a_r5_f0_audit_only.txt
grep -Fx 'result_transfer_authorized=true' /tmp/opencode/p8_2_k1a_r5_f0_audit_only.txt
grep -Fx 'next_task_authorized=false' /tmp/opencode/p8_2_k1a_r5_f0_audit_only.txt
~~~

## 2. 零资源前门与不可扰动证明

在任何证据读取前记录下列状态，任务完成后用同一命令再次记录并比较：

- keep-alive marker PID、PGID、device marker 数量；
- 8 卡健康、HBM 与已有 keep-alive 占用；
- 7000 端口；
- vLLM 推理服务进程；
- tracked Git status。

本节只读。若 keep-alive 当前不存在，也只报告事实，不得由本任务启动、停止或恢复它。不得向任何进程发送信号。

~~~bash
set -euo pipefail

mkdir -p /tmp/opencode/p8_2_k1a_r5_f0
ps -eo pid=,pgid=,args= > /tmp/opencode/p8_2_k1a_r5_f0/process_before.txt
npu-smi info > /tmp/opencode/p8_2_k1a_r5_f0/npu_before.txt
ss -ltnp '( sport = :7000 )' > /tmp/opencode/p8_2_k1a_r5_f0/port_7000_before.txt
git status --porcelain --untracked-files=no > /tmp/opencode/p8_2_k1a_r5_f0/tracked_before.txt
~~~

若检测到本任务自己即将启动 NPU/vLLM/request 的路径，立即停止为
`blocked_p8_2_k1a_r5_f0_resource_contract_gate`。现有 keep-alive 不是失败条件，必须原样保留。

## 3. R4-R1 package 与 R2 geometry 的 hash-first resolver

R4-R1 根固定为：

~~~text
R4_R1_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721_run01
manifest_sha256=008f753135f087201c0e8f0f53662dede1124691a2a551064f89e65a7a23ddde
grade=candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
payload_file_count=9
payload_total_bytes=28190
transfer_file_count=10
transfer_total_bytes=32546
~~~

不得修改旧 R4-R1 目录。runner 会验证 manifest 及全部 payload 的 relative path/bytes/SHA-256/sensitivity，
并拒绝 actual CPU eviction、H2D restore 或 performance 被改写成 true 的 package。

R2 证据不得依赖一个未经验证的手写子目录。只在既有双轨结果根下按 SHA-256 找到唯一文件；零个或多个匹配都
fail closed，不得选“看起来像”的文件：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
R2_SEARCH_ROOT=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p8_dual_track_k1a_r2_rendezvous_and_p8_3_i0_r1_taxonomy_2026_0717_run01

mapfile -t GEOMETRY_MATCHES < <(find "${R2_SEARCH_ROOT}" -type f -name k1a_r2_geometry_summary.json -exec sha256sum {} + | awk '$1=="8430730a583371ebdcc1cb35ff80903376a007cb3f2645ce6a55114bdb9ea6d1" {print $2}')
mapfile -t RENDEZVOUS_MATCHES < <(find "${R2_SEARCH_ROOT}" -type f -name geometry.rendezvous.complete.json -exec sha256sum {} + | awk '$1=="fa258790475303b88a41d4e3f2db684a41a79026b22d434ba9827f0275280796" {print $2}')
mapfile -t ALLOCATOR_MATCHES < <(find "${R2_SEARCH_ROOT}" -type f -name pinned_allocator_envelope_summary.json -exec sha256sum {} + | awk '$1=="99f997a66cb14aeaf1941d34c525729c70dcda0569d45c465a0f1c7f55dfc6b2" {print $2}')

test "${#GEOMETRY_MATCHES[@]}" -eq 1
test "${#RENDEZVOUS_MATCHES[@]}" -eq 1
test "${#ALLOCATOR_MATCHES[@]}" -eq 1

export P8_2_K1A_R5_F0_GEOMETRY_SUMMARY=${GEOMETRY_MATCHES[0]}
export P8_2_K1A_R5_F0_RENDEZVOUS_SUMMARY=${RENDEZVOUS_MATCHES[0]}
export P8_2_K1A_R5_F0_ALLOCATOR_SUMMARY=${ALLOCATOR_MATCHES[0]}
~~~

三份证据必须闭合：同一 `probe_run_id=819f2670c2a24d95a8f04d2a5ef75be3`、rank `0..7`、
world size `8`、geometry parity true、`5048 GPU blocks/rank`、`128 CPU blocks/rank`、
`required_restore_tokens=16384`、`3364096 bytes/block`、`430604288 bytes/rank`、`3444834304 bytes total`，且 allocator 只保留
capacity ready、不自动授权 lifecycle。

## 4. Frozen source semantics 与 runtime method-resolution

冻结 vLLM source：

~~~text
root=/data/node0_disk1/vllm-0.22.1/vllm
commit=0decac0d96c42b49572498019f0a0e3600f50398
v1/simple_kv_offload/manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
v1/core/block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
~~~

只读核对 commit、tracked clean 和两个 source hash。不得 checkout、patch 或写入该 source tree。随后让 analyzer 验证：

- CPU lookup：`find_longest_cache_hit` → pending CPU hit → `_reqs_to_load` → `load_event`；
- eager store 会从包含 cached blocks 的 free queue 继续 `get_new_blocks`，所以压力 store 可先淘汰 CPU target；
- lazy store 的 cursor/free-queue 路径存在，但其动态到达点不能仅由静态 `5` 个 pressure request 证明；
- `BlockPool.get_new_blocks()` 使用 `popleft_n` 并调用 `_maybe_evict_cached_block`，后者移除 cached hash；
- source 支持候选机制不等于 parent lifecycle 已发生 eviction/H2D。

再用冻结运行环境只读解析方法 owner/signature，不安装 observer、不实例化 scheduler、不初始化设备：

~~~bash
set -euo pipefail

PYTHON_BIN=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
OBSERVER=/data/node0_disk1/liguowei/AK-Infer-Lab/tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py

"${PYTHON_BIN}" "${OBSERVER}" self-test \
  --output /tmp/opencode/p8_2_k1a_r5_f0/observer_self_test.json

"${PYTHON_BIN}" - <<'PY' > /tmp/opencode/p8_2_k1a_r5_f0/runtime_method_resolution.json
import inspect
import json
from vllm.v1.core.block_pool import BlockPool
from vllm.v1.simple_kv_offload.manager import SimpleCPUOffloadScheduler

value = {
    "schema_version": "p8_2_k1a_r5_f0_runtime_method_resolution_v1",
    "scheduler_methods": {
        name: str(inspect.signature(getattr(SimpleCPUOffloadScheduler, name)))
        for name in (
            "request_finished_all_groups",
            "get_num_new_matched_tokens",
            "update_state_after_alloc",
            "build_connector_meta",
        )
    },
    "block_pool_methods": {
        "_maybe_evict_cached_block": str(
            inspect.signature(BlockPool._maybe_evict_cached_block)
        )
    },
    "runtime_method_resolution": "pass",
    "observer_installed": False,
    "npu_initialized": False,
}
print(json.dumps(value, indent=2, sort_keys=True))
PY
~~~

若 import 本身触发设备初始化、方法缺失/owner 漂移或 signature 无法解析，停止为
`blocked_p8_2_k1a_r5_f0_source_or_provenance_gate`。不得为通过 probe 修改 site-packages。

## 5. 运行 R5-F0 analyzer（仍为零 NPU）

只有第 1–4 节全部通过才创建一个 fresh 结果根。若同名目录已存在，停止并换新任务，不覆盖、不复用。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f0_h2d_trigger_feasibility_2026_0721_run01
test ! -e "${RESULT_ROOT}"

export P8_2_K1A_R5_F0_R4_R1_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721_run01
export P8_2_K1A_R5_F0_VLLM_ROOT=/data/node0_disk1/vllm-0.22.1/vllm

cd "${REPO_ROOT}"
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.sh "${RESULT_ROOT}"

test "$(cat "${RESULT_ROOT}/task_grade.txt")" = candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
test -f "${RESULT_ROOT}/candidate_manifest.server_local.json"
~~~

trigger plan 的候选计算必须固定：

~~~text
gpu_blocks_per_rank=5048
cpu_blocks_per_rank=128
block_size_tokens=128
target_prefix_tokens=8192
target_prefix_blocks=64
target_cpu_capacity_margin_blocks=64
pressure_context_tokens=131072
pressure_blocks_per_request=1024
minimum_pressure_request_count_to_exceed_gpu_pool=5
eager_mode_can_preserve_target_cpu_residency=false
lazy_mode_requires_runtime_residency_observer=true
fixed_pressure_count_is_candidate_not_runtime_fact=true
formal_h2d_trigger_lifecycle_allowed=false
~~~

`5` 只由 accepted geometry 计算得到 GPU oversubscription candidate；它不证明真实 scheduler 在第五个请求后已形成
`CPU present + GPU absent`。下一 lifecycle 必须以 target residency observer 的实际状态为门，不能只数请求。

## 6. 分级与停止规则

允许的最终 grade 只有：

- `candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility`：R4-R1、R2、frozen source、observer self-test、
  runtime method-resolution 与 trigger plan 全过；仍为零 NPU candidate；
- `blocked_p8_2_k1a_r5_f0_repository_contract_gate`：repo hash/test/audit-only 失败；
- `blocked_p8_2_k1a_r5_f0_source_or_provenance_gate`：parent/R2/source/observer/runtime method 任一失败；
- `blocked_p8_2_k1a_r5_f0_resource_contract_gate`：检测到本任务会扰动 keep-alive/NPU/vLLM/request。

candidate ready 必须同时声明：

~~~text
npu_started=false
vllm_started=false
model_request_sent=false
keep_alive_disrupted=false
formal_model_lifecycle_count=0
model_request_count=0
r4_r1_offline_closeout_accepted=true
store_only_refinalization_accepted=true
eager_mode_can_preserve_target_cpu_residency=false
lazy_mode_trigger_is_candidate_only=true
actual_cpu_eviction_proven=false
h2d_restore_mechanism_accepted=false
cause_proven_as_unique=false
performance_reference_accepted=false
formal_h2d_trigger_lifecycle_allowed=false
k2_authorized=false
p8_3_i1_authorized=false
next_task_authorized=false
~~~

本任务不得在任何 grade 下追加 NPU lifecycle、模型请求、容量 wave、runtime overlay、profiler 或下一阶段动作。
不得进入 K2；不得进入 P8.3-I1；不得进入 K3/K4/P8.4/P8.5/P9。

## 7. 零资源收尾、结果范围与报告

重复第 2 节只读命令，要求：tracked clean；7000 状态不变；无本任务 vLLM；keep-alive PID/PGID/marker 不变；
8 卡健康/HBM 不因本任务变化。把 before/after 对照写进报告，但不把整份 `npu-smi`/process dump 放入传输候选。

正式有界 payload 必须恰好 8 个，加 manifest 共 9 个：

~~~text
result_summary.md
grading_summary.json
task_grade.txt
r4_r1_acceptance_replay.json
geometry_provenance.json
frozen_source_semantics.json
observer_contract_probe.json
trigger_geometry_plan.json
candidate_manifest.server_local.json
~~~

总量必须 `<=71680 bytes`；全部 sensitivity 为
`bounded_operational_metadata_no_content_or_token_ids`。source 文件、raw logs、process/NPU dumps、request bodies、
generated content、token IDs、hash objects 留服务器，不进入候选。

完成后先在聊天中报告：

1. task_id、同步前后 HEAD/origin/ahead-behind/tracked；
2. 各 section pass/fail 与第一个失败点；
3. R4-R1、R2、source hash 与 runtime method-resolution；
4. eager reject 与 lazy candidate 的精确 geometry；
5. observer self-test 与 raw-hash/content 边界；
6. candidate/blocked grade 与全部 required declarations；
7. RESULT_ROOT；
8. 9 文件完整清单：相对/绝对路径、bytes、SHA-256、sensitivity、总量；
9. `email / upload-api / server-local` 三种可用方式和推荐理由。

`result_transfer_authorized:true` 只表示这 9 文件可供用户选择。报告清单后必须等待用户明确选一个方法；当前 handoff
没有选择方法，不得 email、不得调用 upload-api、不得自动改用另一渠道。完成报告后保持等待，不进入下一任务。
