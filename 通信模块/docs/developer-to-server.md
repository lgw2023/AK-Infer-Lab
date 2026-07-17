# Developer to Server

## 当前唯一服务器动作：执行 P8.2-K0 order-balanced Prefix Cache on/off baseline

~~~text
task_id: p8_2_k0_deepseek_v4_flash_order_balanced_prefix_cache_baseline_2026_0717
execution_mode: authorized_p8_2_k0_order_balanced_prefix_cache_on_off_unprofiled_pilot
workload: benchmarks/deepseek_v4_flash/workloads/p8_2_k0_order_balanced_prefix_cache_baseline.yaml
parent_observe_workload: benchmarks/deepseek_v4_flash/workloads/p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
result_transfer_authorized: false
lifecycle_count_exact: 4
request_count_exact: 20
measured_request_count_exact: 12
matched_measured_pair_count_exact: 6
request_retry_count: 0
profiler_authorized: false
hbm_sampler_authorized: false
offload_authorized: false
placement_or_payload_mutation_authorized: false
p8_2_k1_execution_authorized: false
no_k1_k2_k3_k4_p8_3_or_p9: true
next_stage_after_task: wait_for_external_developer_review
claim_boundary: order_balanced_64k_exact_reuse_prefix_cache_on_off_descriptive_baseline_only
~~~

P8.1 parent 继续保留 `yellow_p8_1_matrix_trace_invalid`。P8.1-R1 已由开发机独立复核并接受为
`green_p8_1_r1_official_mtp_observe_only_matrix`：6/6 请求，64K shared follower Prefix hit=`49152`，
其余五条 hit=`0`，MTP、health/queue、body、repair、resolved Prefix、trace/replay/join 和 cleanup 全过。
R1 支持“parent 缺完整 R2 repair”的主诊断，但 `cause_proven_as_unique: false`。服务器 editable install
导致首次默认 site-packages `BASE_VLLM_ROOT` source gate 在零请求阶段中止；改用经用户授权且哈希匹配的
`/data/node0_disk1/vllm-0.22.1/vllm` 后，正式六请求 lifecycle 一次完成。这一 provenance 是
`1 aborted pre-request source-gate invocation + 1 request lifecycle + 0 request retry`，不得改写或删除。

P6.3C 继续保留 `blocked_p6_3c_not_strict_single_variable`，不得通过第二变量重开。K0 消费
`green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab` mechanism green 与 P8.1-R1 trace green，但不能直接复用 P6.3B 固定 off→on
顺序宣称性能。本任务冻结 `off→on/on→off` 两个反向 pair：`pair_01=off→on`、`pair_02=on→off`。每个 fresh lifecycle
运行 1 个独立 64K warmup、1 个 64K prime 和 3 个 measured follower；四侧使用相同 5 个 body bytes/hash，
总计 20 request、12 measured、6 matched pair。两套 server argv 只允许显式 Prefix Cache boolean flag
不同；same R2 repair、W8A8、TP8+EP、MTP、Chunked Prefill、graph、context 和所有其他 runtime 参数相同。

冻结 normalized server command SHA-256 为：Prefix Cache off
`def3dd8bf71ee4cac1922b0d4fa14321e1df5369fd8a5997771d00f3be6418ea`，Prefix Cache on
`370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19`；二者只允许显式布尔 flag
不同，不能接受其他 resolved drift。

K0 只建立 `65536+64,c1,exact-reuse` primary cell 的 order-balanced unprofiled 描述性 baseline。
负、零、正 timing delta 都是可报告结果；candidate green 只代表证据完整，不代表 Prefix Cache 更快，
不升级为新的 performance reference，也不构成 KV Cache CPU Offload、UCM / External KV Cache、
D2H/H2D、restore/recompute/overlap、HBM/DRAM 分层或 hardware bottleneck 证据。

### 1. 同步、tracked-clean、冻结哈希、合同与 source-root 门

只在服务器主镜像 fast-forward 同步。允许既有 untracked runtime artifacts，但 tracked 文件必须干净；
不得 reset/stash/checkout 覆盖、运行自定义同步脚本、创建服务器提交或 push。localhost 请求必须同时显式
绕过公司 proxy。`BASE_VLLM_ROOT` 固定指向 editable checkout；不得退回不存在的 site-packages 路径，
不得修改 checkout/site-packages/runtime tracked 文件。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ENV_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
PYTHON_BIN=${ENV_PREFIX}/bin/python
TASK_ID=p8_2_k0_deepseek_v4_flash_order_balanced_prefix_cache_baseline_2026_0717
WORKLOAD=${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p8_2_k0_order_balanced_prefix_cache_baseline.yaml
R1_WORKLOAD=${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.sh
MODE_RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k0_mode.sh
REQUEST_RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py
R4_R1_MODE=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_r4_r1_mode.sh
R4_MODE=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_r4_mode.sh
RUNTIME_IMPL=${REPO_ROOT}/tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py
RUNTIME_LOADER=${REPO_ROOT}/tools/inference_contracts/p6_3b_r2_hybrid_kv_runtime_patch.py
MTP_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
HYBRID_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch
DEFERRED_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch
SOURCE_PAYLOAD=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
BASE_VLLM_ROOT=/data/node0_disk1/vllm-0.22.1/vllm
BASE_PLUGIN_ROOT=${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}_run01
export BASE_VLLM_ROOT

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
test ! -e "${RESULT_DIR}"

test "$(sha256sum "${R1_WORKLOAD}" | awk '{print $1}')" = e7a86be58c79097b55abd3a077504b8d283d74d0a3dd259bd6ddbd0e140e4cdf
test "$(sha256sum "${WORKLOAD}" | awk '{print $1}')" = 0ef27f0de8f4b03d10d6231af1dea70dd5564e86b4f4d0be6408ec7458260298
test "$(sha256sum "${REQUEST_RUNNER}" | awk '{print $1}')" = a07f0f28b4c4b7a36e5e604345714eecfb7c2027ade07e4b4d15a95b6b019b71
test "$(sha256sum "${RUNNER}" | awk '{print $1}')" = 963c31c8599741ca0fad1dcd56761da3e41ef6590e937e6fc1af1fc11faf4188
test "$(sha256sum "${MODE_RUNNER}" | awk '{print $1}')" = a65263913f334560789a5e007cb1db69951e1606e6895c4f89421b56c6036b6c
test "$(sha256sum "${R4_R1_MODE}" | awk '{print $1}')" = 5ebc4e0a8ba8163b56ab26cb72abd93206da64741a303cec6ef9d601cc257b5d
test "$(sha256sum "${R4_MODE}" | awk '{print $1}')" = 1092ae2978c37a103862d7ef76059ef0d71b68c5caa74c6cb3db1e1a45612a57
test "$(sha256sum "${RUNTIME_IMPL}" | awk '{print $1}')" = 6be8eaf168279a6daba1aff891a289b19becb157d794adde0028457bb9821f6c
test "$(sha256sum "${RUNTIME_LOADER}" | awk '{print $1}')" = 9d720389f520918642ddecf288d0ac3922f61873251760129ba34ba203d02631
test "$(sha256sum "${MTP_PATCH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(sha256sum "${HYBRID_PATCH}" | awk '{print $1}')" = cac1e77ca08781fbaaf483d903733f9e2875091e6e8f9b33467e4da9c124390e
test "$(sha256sum "${DEFERRED_PATCH}" | awk '{print $1}')" = ad845854461605ae28ae7000f24ada0cb07c5c17f3b0c23ee1485ec537a7a85b
test "$(stat -c '%s' "${SOURCE_PAYLOAD}")" = 19487
test "$(sha256sum "${SOURCE_PAYLOAD}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1

test "$(git -C /data/node0_disk1/vllm-0.22.1 rev-parse HEAD)" = 0decac0d96c42b49572498019f0a0e3600f50398
test "$(stat -c '%s' "${BASE_VLLM_ROOT}/v1/core/single_type_kv_cache_manager.py")" = 53714
test "$(sha256sum "${BASE_VLLM_ROOT}/v1/core/single_type_kv_cache_manager.py" | awk '{print $1}')" = d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1
test "$(stat -c '%s' "${BASE_VLLM_ROOT}/v1/core/kv_cache_coordinator.py")" = 25255
test "$(sha256sum "${BASE_VLLM_ROOT}/v1/core/kv_cache_coordinator.py" | awk '{print $1}')" = a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89
test "$(sha256sum "${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(sha256sum "${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_coordinator.py" | awk '{print $1}')" = dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20
test "$(sha256sum "${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_interface.py" | awk '{print $1}')" = a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2

grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'execution_mode: authorized_p8_2_k0_order_balanced_prefix_cache_on_off_unprofiled_pilot' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'npu_execution_authorized: true' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'result_transfer_authorized: false' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'lifecycle_count_exact: 4' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'request_count_exact: 20' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F 'p8_2_k1_execution_authorized: false' "${REPO_ROOT}/通信模块/docs/developer-to-server.md"

bash -n "${RUNNER}" "${MODE_RUNNER}" "${R4_R1_MODE}" "${R4_MODE}"
"${PYTHON_BIN}" -m py_compile "${REQUEST_RUNNER}"
"${PYTHON_BIN}" -m pytest \
  tests/inference_contracts/test_deepseek_p6_3b_r4_r1_nfs_portability.py \
  tests/inference_contracts/test_deepseek_p8_1_official_mtp_observe_only_matrix.py \
  tests/inference_contracts/test_deepseek_p8_1_r1_hybrid_kv_repair_replay.py \
  tests/inference_contracts/test_deepseek_p8_2_k0_order_balanced_prefix_baseline.py \
  -q

P8_2_K0_AUDIT_ONLY=1 bash "${RUNNER}" /tmp/p8_2_k0_audit_not_created > /tmp/p8_2_k0_audit.txt
test "$(sha256sum /tmp/p8_2_k0_audit.txt | awk '{print $1}')" = 10d3182ae258ea15e93808758e63b836a8faba37f315f490699ae3582b968c85
test ! -e /tmp/p8_2_k0_audit_not_created
cat /tmp/p8_2_k0_audit.txt
printf 'HEAD=%s\n' "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
printf 'origin/main=%s\n' "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
printf 'RESULT_DIR=%s\n' "${RESULT_DIR}"
~~~

任一同步、tracked-clean、hash、source-root、合同、audit-only、旧结果目录或模型路径门失败，评级
`blocked_p8_2_k0_source_or_resource_gate` 并停止；不得释放 keep-alive、启动 vLLM 或发请求。

### 2. 八卡 keep-alive、端口与资源门

执行前将 marker `#0#`–`#7#`、PID、PPID、PGID、命令行、父子树和每卡 HBM 写入 server-local inventory。
官方 keep-alive 可能是一个共享 PGID，也可能是多个 PGID；必须按完整 marker/父子树核实，只终止确认属于
keep-alive 的 process group，不得触碰其他用户、任务或非 marker 进程。停止后必须确认：

- NPU 0–7 均无运行进程、AICore 空闲且 health 正常；
- 端口 7000 空闲，无 residual vLLM/engine worker；
- 模型路径、conda runtime、vLLM checkout 与 plugin root 可读；
- 服务器 tracked worktree 仍干净，`${RESULT_DIR}` 仍不存在。

资源门失败按 blocked 停止。inventory、`npu-smi info`、端口和原始日志留服务器，不加入 bounded candidates。

### 3. 执行冻结 AB/BA 四 lifecycle、20 请求 K0

top runner 会在任何模型请求前从 frozen 4096-token source payload 构造 5 个 canonical 64K body，冻结
token count、bytes、SHA-256、warmup↔primary LCP `<128` 与 primary follower token-LCP/16K floor，
再把相同 body bytes 复制到四个 lifecycle。每个 mode runner 使用 ownership-safe task-local overlay，
应用同一 R2 runtime impl/deferred loader/MTP+hybrid+deferred-install patch，逐 lifecycle 验证 repair identity、
full diagnostics、retention unset、resolved Prefix false/true 和 normalized server argv hash。

冻结顺序与请求数：

1. `lifecycle_01 / pair_01 / first / prefix_cache_off`：warmup + prime + 3 measured；
2. `lifecycle_02 / pair_01 / second / prefix_cache_on`：同一 5 body；
3. `lifecycle_03 / pair_02 / first / prefix_cache_on`：同一 5 body；
4. `lifecycle_04 / pair_02 / second / prefix_cache_off`：同一 5 body。

每请求固定 `input=65536, output=64, c=1, temperature=0, ignore_eos=true, min=max=64, streaming=true`。
on 侧 6 个 measured follower 的 expected Prefix hit 均为 `49152`；off 侧全部请求以及 on 侧 warmup/prime
expected hit 均为 `0`。逐请求还必须满足 HTTP 200、prompt/generated/streamed token 精确、finish reason、
SSE done、MTP activity/counter continuity、health、running/waiting=0，并记录 TTFT/TPOT/ITL/E2EL/throughput。

执行：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_2_k0_deepseek_v4_flash_order_balanced_prefix_cache_baseline_2026_0717
RUNNER=${REPO_ROOT}/tools/inference_contracts/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.sh
RESULT_DIR=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/${TASK_ID}_run01
KEEP_ALIVE=/data/node0_disk1/Public/npu_keep_alive.sh
export BASE_VLLM_ROOT=/data/node0_disk1/vllm-0.22.1/vllm

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
if test -f "${RESULT_DIR}/grading_inputs.json"; then
  "${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python" - "${RESULT_DIR}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
grading = json.loads((root / "grading_inputs.json").read_text(encoding="utf-8"))
for key in (
    "server_grade",
    "successful_request_count",
    "warmup_request_count",
    "prime_request_count",
    "measured_request_count",
    "matched_measured_pair_count",
    "order_balance_exact",
    "body_pairing_exact",
    "single_variable_server_argv_exact",
    "same_r2_repair_all_lifecycles",
    "diagnostic_ok_all_lifecycles",
    "resolved_prefix_control_exact",
    "on_measured_hit_exact_count",
    "off_prefix_hit_total",
    "on_non_measured_prefix_hit_total",
    "request_evidence_exact",
    "measured_metrics_complete",
    "cleanup",
    "performance_reference_accepted",
    "offload_evidence_accepted",
    "candidate_file_count",
    "candidate_total_bytes",
    "candidate_size_gate_pass",
):
    print(f"{key}={grading[key]}")
delivery = root / "delivery_candidates.tsv"
if delivery.is_file():
    print(delivery.read_text(encoding="utf-8"), end="")
PY
else
  printf '%s\n' 'server_grade=blocked_red_or_partial_before_finalizer'
  find "${RESULT_DIR}" -maxdepth 4 -type f -printf 'existing_artifact\t%p\t%s\n' | sort
fi

git -C "${REPO_ROOT}" status --short --branch --untracked-files=no
exit "${runner_exit}"
~~~

无论成功或失败，都要确认 vLLM 已停止、端口 7000 释放、无 residual engine worker，并用官方脚本恢复
8 卡 keep-alive，固定恢复命令为 `bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7`。恢复后报告
marker/进程数、每卡 HBM、端口和 tracked-clean；不得因 K0 失败改 body、顺序、
repair、runtime 参数、版本或增加 retry。

### 4. 分级、候选清单与停止边界

- source/resource/config/audit gate 失败且未发请求：`blocked_p8_2_k0_source_or_resource_gate`；
- 没有 successful measured request：`red_p8_2_k0_order_balanced_prefix_baseline_no_success`；
- 只有部分 lifecycle/request/pair：`yellow_p8_2_k0_order_balanced_prefix_baseline_partial`；
- 20/20 成功但单变量、AB/BA、body pairing、hit、repair、resolved、MTP/queue/metrics 或 cleanup 任一不完整：
  `red_p8_2_k0_order_balanced_prefix_baseline_evidence_incomplete`；
- 所有门完整：服务器只能给 `candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline`，等待开发机复核。

任一首错即停，无 request/lifecycle retry，不补第 5 lifecycle 或第 21 请求。K0 blocked/red/yellow 不撤销
P6 或 P8.1-R1 green。K0 candidate/green 也不自动证明 Prefix Cache 更快；不得执行 profiler、HBM sampler、
KV Cache CPU Offload、UCM/External KV、D2H/H2D move、placement/payload mutation、第二 repair、runtime upgrade、
K1/K2/K3/K4、P8.3 或 P9。

raw logs、Prometheus metrics、request bodies、generated content/token IDs、overlay 和 full diagnostics 留服务器。
bounded candidates 最多 14 文件、总量不超过 70KB，不含 generated content/token IDs。任务结束先报告：

1. `RESULT_DIR` 与 `result_summary.md` 精确路径；
2. 14-file 完整候选清单，逐文件 bytes/SHA-256/sensitivity 与总量；
3. `email / upload-api / server-local` 三种可用方法与一个推荐方法/理由；
4. runner exit、server candidate grade、四 lifecycle/20 request/6 pair、hit/MTP/queue/metrics/cleanup 和 keep-alive 恢复摘要。

`result_transfer_authorized:false`：用户对该完整范围重新选择一个方法前，不得外发（包括不得自动外发）、
不得创建发送附件、
不得调用外发接口，也不得从旧选择继承或失败后自动切换。完成后等待开发机独立复核；不得自动进入 K1。
