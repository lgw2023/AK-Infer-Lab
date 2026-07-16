# Developer to Server

## 当前唯一服务器动作：执行 P8.1-R1 完整 R2 repair observe-only 六请求复跑

~~~text
task_id: p8_1_r1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0717
execution_mode: authorized_p8_1_r1_full_r2_repair_observe_only_six_request_replay
workload: benchmarks/deepseek_v4_flash/workloads/p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml
parent_workload: benchmarks/deepseek_v4_flash/workloads/p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
result_transfer_authorized: false
lifecycle_count_max: 1
request_count_exact: 6
profiler_authorized: false
offload_authorized: false
placement_or_payload_mutation_authorized: false
no_p8_2_p7_or_p9: true
cause_proven_before_replay: false
next_stage_after_task: wait_for_external_developer_review
claim_boundary: official_mtp_shared_prefix_observe_only_trace_repair_replay_not_performance
~~~

P8.1 parent 已完成并由开发机接受为 `yellow_p8_1_matrix_trace_invalid`：6/6 请求、
MTP、health/queue、18 个 request-stage、6 个 Prefix StateObject/no-op decision、双 bundle replay 与
request→runtime→object join 均通过，且 `replay_determinism` / `join_coverage` 证据完整；唯一失配是 `medium_shared_follower` Prefix hit=`0`，
不等于预期 `49152`。Parent 任务不得原样重跑，其 workload/result 必须保留为 historical yellow。

开发机的高置信主诊断是：parent P8.1 只携带 MTP positions patch，却引用了 P6.3B-R4-R1
在完整 R2 hybrid-KV repair 下形成的 `49152` 行为预期。这还不是已证明的唯一原因。R1 保持 parent
的六个 request body SHA-256、顺序、server argv、runtime 参数、一个 lifecycle 和 observe-only 证据口径，
只把 P6.3B-R2 已验收的 same R2 repair task-local 基线补齐，并增加 repair identity/diagnostic、resolved Prefix Cache、
localhost proxy 和 retention-unset 门。它不是性能 A/B，不改 site-packages，不进入 P8.2。

P6.1C-R1、P6.1、P6.2、P6.3A 和 `green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab` 全部保持；P6.3C 继续
`blocked_p6_3c_not_strict_single_variable`：冻结配置 `4096 < 135168`，off 侧会在请求前被 validation 拒绝，
而绕过必须改变第二变量，因此没有 workload。本任务不重跑 P6，不启动 profiler/HBM sampler/
offload，不改 placement 或 payload，不保存 generated text/token IDs，不得自动进入 P8.2。

### 1. 同步、tracked-clean、冻结哈希与本地合同门

只在服务器主镜像 fast-forward 同步。允许已有 untracked runtime artifacts，但 tracked 文件必须干净；
不得 reset/stash/checkout 覆盖、运行自定义同步脚本、创建服务器侧提交或 push。服务器 localhost
调用不得经过公司 HTTP proxy；下列 `no_proxy/NO_PROXY` 是协议基础设施，不是实验变量。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
TASK_ID=p8_1_r1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0717
BASELINE=${REPO_ROOT}/benchmarks/deepseek_v4_flash/p8/p8_official_mtp_observe_matrix_contract.yaml
PARENT_WORKLOAD=${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml
WORKLOAD=${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml
PREPARER=${REPO_ROOT}/tools/inference_contracts/prepare_deepseek_p8_1_r1_observe_matrix.py
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_1_r1_observe_only_matrix.sh
FINALIZER=${REPO_ROOT}/tools/inference_contracts/finalize_deepseek_p8_1_r1_observe_only_matrix.py
RUNTIME_IMPL=${REPO_ROOT}/tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py
RUNTIME_LOADER=${REPO_ROOT}/tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py
MTP_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
HYBRID_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch
DEFERRED_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch
OBSERVER=${REPO_ROOT}/tools/ak_state_runtime/vllm_ascend_observer.py
CLI=${REPO_ROOT}/tools/ak_state_runtime/cli.py
ADAPTER=${REPO_ROOT}/tools/ak_state_runtime/adapters/vllm_ascend.py
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}_run01

append_no_proxy() {
  local value=$1
  local host
  for host in 127.0.0.1 localhost; do
    case ",${value}," in
      *",${host},"*) ;;
      *) value=${value:+${value},}${host} ;;
    esac
  done
  printf '%s' "${value}"
}
export no_proxy="$(append_no_proxy "${no_proxy:-}")"
export NO_PROXY="$(append_no_proxy "${NO_PROXY:-}")"

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"

test "$(sha256sum "${BASELINE}" | awk '{print $1}')" = 9405853cea52683828c99dfa55bc0093270102b4fe27110494502854d7dc49cb
test "$(sha256sum "${PARENT_WORKLOAD}" | awk '{print $1}')" = 12e379a56b7abd7eafc1022ff52181eed8fcc9e3624b78dd322598a599cd45cf
test "$(sha256sum "${WORKLOAD}" | awk '{print $1}')" = 596780a9e9a0416ead6f495524f2de251f46c75524f824bc0c1d47743f3c0710
test "$(sha256sum "${PREPARER}" | awk '{print $1}')" = 8d6e1a294bfd301f98cb5230c6ee3ba6adcec2663d9506f0085ffa3cd8824ad5
test "$(sha256sum "${RUNNER}" | awk '{print $1}')" = c9f7c7cbaeeba903cb2e439ba7fc64afdf5a4fd4f02ce145d3ae983f273d92a1
test "$(sha256sum "${FINALIZER}" | awk '{print $1}')" = 4745e4bf263b1343fd6d17e755b1b3989c09dd64646ed4cf5a43e0837186e599
test "$(sha256sum "${RUNTIME_IMPL}" | awk '{print $1}')" = 6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
test "$(sha256sum "${RUNTIME_LOADER}" | awk '{print $1}')" = 9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
test "$(sha256sum "${MTP_PATCH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(sha256sum "${HYBRID_PATCH}" | awk '{print $1}')" = cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
test "$(sha256sum "${DEFERRED_PATCH}" | awk '{print $1}')" = ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
test "$(sha256sum "${OBSERVER}" | awk '{print $1}')" = ecc7122b01c0b56cdc4817d2be780f18266097db2d16b19de0f471668765f201
test "$(sha256sum "${CLI}" | awk '{print $1}')" = 9eb3ab2d408b84361916d61fadc981ec2674be9ea154b0f47205524d5b4af5f6
test "$(sha256sum "${ADAPTER}" | awk '{print $1}')" = 17b4d344b66324a8703e8bf5599dfa2082d60fedea5db9ef208cfdb625ef158e

grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'execution_mode: authorized_p8_1_r1_full_r2_repair_observe_only_six_request_replay' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'npu_execution_authorized: true' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'next_task_authorized: true' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'result_transfer_authorized: false' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'full_p6_3b_r2_task_local_repair_required: true' "${WORKLOAD}"
grep -F 'cause_proven_before_replay: false' "${WORKLOAD}"
grep -F 'request_count: 6' "${WORKLOAD}"
grep -F 'expected_server_command_sha256: 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19' "${WORKLOAD}"

bash -n "${RUNNER}"
"${PYTHON_BIN}" -m py_compile "${PREPARER}" "${FINALIZER}" "${OBSERVER}" "${CLI}" "${ADAPTER}"
"${PYTHON_BIN}" -m pytest \
  tests/inference_contracts/test_deepseek_p6_3b_r1_hybrid_kv_repair.py \
  tests/inference_contracts/test_deepseek_p6_3b_r2_deferred_install.py \
  tests/inference_contracts/test_deepseek_p8_1_official_mtp_observe_only_matrix.py \
  tests/inference_contracts/test_deepseek_p8_1_r1_hybrid_kv_repair_replay.py \
  tests/ak_state_runtime/test_baseline_contract.py \
  tests/ak_state_runtime/test_vllm_ascend_adapter.py \
  tests/ak_state_runtime/test_vllm_ascend_observer.py \
  -q

P8_1_R1_AUDIT_ONLY=1 bash "${RUNNER}" /tmp/p8_1_r1_audit_only_not_created > /tmp/p8_1_r1_server_command.txt
test "$(sha256sum /tmp/p8_1_r1_server_command.txt | awk '{print $1}')" = 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
test ! -e "${RESULT_DIR}"
printf 'task_id=%s\n' "${TASK_ID}"
printf 'HEAD=%s\n' "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
printf 'origin/main=%s\n' "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
printf 'result_dir=%s\n' "${RESULT_DIR}"
~~~

任一同步、tracked-clean、hash、source、test、argv 或旧结果目录门失败，评级
`blocked_p8_1_r1_source_or_resource_gate` 并停止；不得启动 vLLM 或发请求。

### 2. 八卡 keep-alive 资源门

执行前先把 marker `#0#`–`#7#`、PID、PGID、命令行和每卡 HBM 写入 server-local inventory。
官方 keep-alive 在不同 shell/job-control 形态下可能是一个共享 PGID 或多个 PGID；必须以完整父子树和
8 个 marker 核实，不得硬猜 PGID 数。只允许终止已核对的 keep-alive 后代 process group，不得触碰
其他用户、其他任务或非 marker 进程。终止后必须确认：

- NPU 0–7 均无运行进程、AICore 空闲且 health 正常；
- 端口 7000 空闲，没有 residual vLLM/engine worker；
- 模型、conda runtime、`/data/node0_disk1/vllm-0.22.1` 可读，vLLM Git HEAD 精确为
  `0decac0d96c42b49572498019f0a0e3600f50398`；
- base vLLM/plugin source bytes/SHA-256 与 runner 冻结门一致。

任一资源门不满足，按 blocked 停止且不创建正式结果目录。inventory、停止后 `npu-smi info`
和端口证据留服务器，不加入 bounded candidates。

### 3. 一次 lifecycle 执行完整 P8.1-R1 matrix

runner 将在任何请求前：

1. 从冻结 `19487-byte` source payload 重建六个 body，对六个 SHA-256 逐项精确比较；
2. 用 `cp -a --no-preserve=ownership` 建立 task-local plugin overlay，不改 site-packages；
3. 应用已验收的 runtime impl、deferred loader、MTP positions、hybrid EAGLE manager 和 deferred-install
   repair，验证 base/overlay source hash 与 `require_ascend_manager_resolution()`；
4. 显式 unset `VLLM_PREFIX_CACHE_RETENTION_INTERVAL`，在 live process cmdline 证明
   `--enable-prefix-caching` 存在、反向 flag 不存在；
5. 保留 parent server argv 字节完全一致，然后才允许发送六个请求。

六请求矩阵仍为 `4096/65536/131072 × 2`，顺序固定且无 retry：

1. `short_isolated_a = 4096+64`，hit=0；
2. `medium_shared_prime = 65536+64`，hit=0；
3. `medium_shared_follower = 65536+64`，LCP=58880，hit=49152；
4. `long_isolated_a = 131072+64`，hit=0；
5. `short_isolated_b = 4096+64`，hit=0；
6. `long_isolated_b = 131072+64`，hit=0。

执行：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_1_r1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0717
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}_run01
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_1_r1_observe_only_matrix.sh
KEEP_ALIVE=/data/node0_disk1/Public/npu_keep_alive.sh

append_no_proxy() {
  local value=$1
  local host
  for host in 127.0.0.1 localhost; do
    case ",${value}," in
      *",${host},"*) ;;
      *) value=${value:+${value},}${host} ;;
    esac
  done
  printf '%s' "${value}"
}
export no_proxy="$(append_no_proxy "${no_proxy:-}")"
export NO_PROXY="$(append_no_proxy "${NO_PROXY:-}")"

restore_keep_alive() {
  bash "${KEEP_ALIVE}" 0 1 2 3 4 5 6 7
}
trap restore_keep_alive EXIT

set +e
bash "${RUNNER}" "${RESULT_DIR}"
runner_exit=$?
set -e

restore_keep_alive
trap - EXIT

printf 'runner_exit=%s\n' "${runner_exit}"
test -f "${RESULT_DIR}/cleanup_status.txt"
printf 'cleanup=%s\n' "$(cat "${RESULT_DIR}/cleanup_status.txt")"

if test -f "${RESULT_DIR}/grading_inputs.json"; then
  "${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python" - "${RESULT_DIR}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
grading = json.loads((root / "grading_inputs.json").read_text(encoding="utf-8"))
for key in (
    "grade",
    "successful_request_count",
    "shared_prefix_exact",
    "isolated_zero_hit",
    "per_request_mtp_ok",
    "health_queue_ok",
    "replay_deterministic",
    "join_coverage_complete",
    "trace_validation_errors",
    "frozen_body_gate_ok",
    "repair_gate_ok",
    "resolved_prefix_cache_gate_ok",
    "persistent_shared_prefix_failure",
    "cause_supported_by_replay",
    "cause_proven_as_unique",
    "cleanup",
    "next_action",
):
    print(f"{key}={grading[key]}")
delivery = root / "delivery_candidates.tsv"
if delivery.is_file():
    print(delivery.read_text(encoding="utf-8"), end="")
    print(f"candidate_total_bytes={(root / 'candidate_total_bytes.txt').read_text().strip()}")
PY
else
  printf '%s\n' 'server_grade=blocked_red_or_partial_before_finalizer'
  find "${RESULT_DIR}" -maxdepth 3 -type f -printf 'existing_artifact\t%p\t%s\n' | sort
fi

git -C "${REPO_ROOT}" status --short --branch --untracked-files=no
exit "${runner_exit}"
~~~

无论 runner 成功或失败都必须执行与 `bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7`
等价的官方恢复动作，再核对 marker `#0#`–`#7#`、
预期后代进程与每卡 HBM。恢复失败必须在回报中标红，但不得用额外模型请求验证恢复。
不得发送第 7 个请求，不得对任一 slot 补发或 retry。

### 4. 分级、停止和因果边界

只有以下全部成立，服务器才可给
`candidate_green_p8_1_r1_official_mtp_observe_only_matrix`：

- 6/6 请求按固定顺序首次成功，prompt/generated/streamed/finish/SSE done 精确；
- 六个 request body SHA-256 与 parent 冻结值逐项一致，LCP 关系不漂移；
- runtime impl/deferred loader/三个 patch/overlay hashes 精确，hybrid diagnostic 证明 deferred install、
  source hashes、retention-unset、EAGLE manager propagation、lookahead target 和 reachable mask 门完整；
- live process resolved Prefix Cache=true；follower Prefix hit 精确为 49152，其余五个精确为 0；
- 每请求 MTP drafts/draft tokens 正增、accepted 不倒退，health 正常、结束 running/waiting=0；
- trace 仍为 18 个 request-stage、6 个 StateObject、6 个 `executed=false` no-op decision，
  payload ref 全为 null，`trace_validation_errors=0`；双 bundle 重放逐文件一致，join 完整；
- cleanup clean、端口释放、无 residual vLLM，keep-alive 恢复。

分级：preflight/resource/hash 失败为 `blocked_p8_1_r1_source_or_resource_gate`；server 未 ready 为
`red_p8_1_r1_server_not_ready`；零成功为 `red_p8_1_r1_request_no_success`；1–5 个成功为
`yellow_p8_1_r1_matrix_partial`；6 个成功但任一 body/repair/Prefix/MTP/queue/trace/replay/join 门不完整为
`yellow_p8_1_r1_matrix_trace_invalid`。

若 R2 identity/diagnostic 完整但 follower 仍 hit=0，保留首错并停止；`next_action` 只可为
`read_only_frozen_source_and_server_local_log_diagnosis`，不得加第二 repair、改 runtime/body/参数、重试、
进入 P8.2 或声称服务器故障。若 R1 恢复 49152 hit，只能说复跑支持“parent 缺 R2 repair”
诊断，不证明它是逻辑上唯一原因，也不形成性能收益、offload、placement 或 hardware bottleneck 结论。

### 5. 回报与外发禁令

在当前任务通道回报：

- task_id、HEAD/origin/main、tracked status、定向 pytest 和冻结 hash/argv 门；
- keep-alive 原始 marker/PID/PGID 形态、安全停止与恢复摘要；
- runner exit/server grade、6 个 slot 的 request/Prefix/MTP/health/queue 摘要；
- body relationship、repair identity/diagnostic、resolved Prefix、trace/replay/join/cleanup 的所有硬门；
- 精确结果目录、`delivery_candidates.tsv` 的完整逐文件 bytes/SHA-256/sensitivity 和候选总 bytes。

raw server log、Prometheus snapshots、六份 request body、逐请求 observations、两个完整 bundle、完整 hybrid diagnostic
与 generated token IDs 留服务器。bounded candidates 只限 workload 声明的 15 个小文件，总量不得超过
70KB，且 `body_relationship_summary.json` 只含 hash/bytes/LCP，不含 body/token。

当前 `result_transfer_authorized:false`：必须先报告完整候选范围、`email / upload-api / server-local`
三种方法与一个推荐理由；用户对该精确范围重新选择一个方法前，不得外发、不得创建发送附件、
不得调用外发接口。服务器只能给 candidate grade，开发机独立复核前不得升级为 accepted green，
也不得自动进入任何下一阶段。
