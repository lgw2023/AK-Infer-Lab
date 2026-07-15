# Developer to Server

## 当前唯一服务器动作：同步并执行 P6.3B Prefix Cache on/off

~~~text
task_id: p6_3b_deepseek_v4_flash_w8a8_mtp_prefix_cache_matched_ab_2026_0715
execution_mode: authorized_for_execution
workload: benchmarks/deepseek_v4_flash/workloads/p6_3b_prefix_cache_matched_ab.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
~~~

用户已明确授权当前 P6.3B 使用服务器 NPU 0-7 与 vLLM，并允许后续**已经发布且有唯一
handoff 的明确 workload**持续使用 NPU/vLLM。本任务同步到远程 `main`、通过资源/hash/metrics
硬门后立即执行，无需再次等待资源授权。standing authorization 不允许自行发明实验；P6.3B
完成后不得自动进入 P6.3C、P7 或 P8，也不得重复执行已完成的 P6.3A。
不得自动进入 P8。

同步必须使用：

~~~bash
git fetch origin main
git merge --ff-only origin/main
~~~

不得使用 `pull-remote` alias、`server_local_git_sync.sh`、reset、restore、stash、commit 或 push。

P6.1C-R1、P6.1、P6.2 已由开发机分别接受为
`green_mtp_official_context_ladder`、`green_mtp_unprofiled_baseline`、
`green_mtp_profiled_evidence`；P6.3A 已由开发机接受为 `green_p6_3a_mtp_matched_ab`。
本任务只回答 purpose-built
repeated-prefix workload 下 Prefix Cache on/off 的 matched mechanism effect；不运行 profiler、
HBM sampler，不改写既有 reference，也不预设 Prefix Cache 一定更快。

## 1. 单变量合同

两个 fresh lifecycle 固定按 `prefix_cache_off -> prefix_cache_on` 执行。两边都保持 W8A8、
TP8+EP、MTP、graph、chunked prefill、`max_num_seqs=1`、block size 128、task-local overlay、
canonical body 和所有非目标 server 参数相同。唯一 server 自变量是：

- `prefix_cache_off`：省略 `--enable-prefix-caching`；
- `prefix_cache_on`：增加 `--enable-prefix-caching`。

冻结哈希：

~~~text
patch: 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
overlay proposer: 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
base proposer: 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
prefix_cache_off command: 89376c9577dc70671b2b071113397c04de1ee8c1e1e802238ff4b61d753f0b98
prefix_cache_on command: 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
source payload: 19487 bytes / 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
~~~

8 个 group 为 `4096/32768/65536/131072 × 50%/90% shared prefix`，输出固定 64、并发 1。
每个 group 严格顺序执行 1 个 prime（排除性能比较）和紧随其后的 3 个 measured follower；
shared prefix 按 128-token block 对齐，group 间 common prefix 小于 128。两 mode 共 16 prime、
48 measured、64 requests，0 retry。32 份 canonical body 在第一个 server 启动前只生成一次，
两个 mode 复用相同字节与 SHA-256。

Prefix-on 每个 measured follower 必须有正的 `prefix_cache_hits` delta，Prefix-off 的 hit delta
必须为 0（counter 可缺失）。两边都要求 MTP drafts/draft_tokens 正增量、mode 累计 accepted >0、
health=200、running=waiting=0、counter continuity 和 clean cleanup。target shared ratio 是构造参数；
observed hit ratio 单独由 `hits_delta/queries_delta` 报告，不强制等于 target。

允许服务器助手直接修正 server-local mkdir/path、shell quoting、`set -u` source 兼容、真实输出
parser 或等价 runner error handling，但必须报告，并证明没有改变 tracked 文件、runtime/site-packages、
body/group/prime/repeat/order、server 单变量或指标定义。禁止 retry、同 mode restart、第二 patch、调参、
降档、关闭 MTP、修改 chunked prefill/`max_num_seqs`、eager fallback、版本升级或自动进入后续阶段。

## 2. 同步、资源门、执行与清理

从一个 shell 执行：

~~~bash
set -euo pipefail

NPU_EXECUTION_AUTHORIZED=true
test "${NPU_EXECUTION_AUTHORIZED}" = true

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_3b_deepseek_v4_flash_w8a8_mtp_prefix_cache_matched_ab_2026_0715
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
PYTHON_BIN="${ENV_PREFIX}/bin/python"
WORKLOAD_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_3b_prefix_cache_matched_ab.yaml"
RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_prefix_cache_ab.py"
MODE_RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_mode.sh"
PATCH_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
BASE_PROPOSER="${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend/spec_decode/llm_base_proposer.py"
PAYLOAD_PATH="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json"

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F "npu_execution_authorized: true" "${WORKLOAD_PATH}"
grep -F "next_task_authorized: true" "${WORKLOAD_PATH}"
test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"/{modes,runtime}

test "$(sha256sum "${PATCH_PATH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/source_payload_sha256.txt"

npu-smi info > "${RESULT_DIR}/npu_smi_before.txt" 2>&1
"${PYTHON_BIN}" - "${RESULT_DIR}/npu_smi_before.txt" "${RESULT_DIR}/resource_gate.json" <<'PY'
import json
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
health = {
    int(match.group(1)): match.group(2)
    for match in re.finditer(
        r"^\|\s*([0-7])\s+910B1\s+\|\s*(OK)\s+\|", text, re.MULTILINE
    )
}
idle = {int(value) for value in re.findall(r"No running processes found in NPU ([0-7])", text)}
result = {
    "health": health,
    "idle_devices": sorted(idle),
    "all_eight_healthy": health == {index: "OK" for index in range(8)},
    "all_eight_idle": idle == set(range(8)),
}
result["pass"] = result["all_eight_healthy"] and result["all_eight_idle"]
Path(sys.argv[2]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if result["pass"] else 2)
PY
if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
  printf '%s\n' blocked_port_7000 > "${RESULT_DIR}/first_failure_excerpt.txt"
  printf '%s\n' blocked_protocol_or_resource_gate > "${RESULT_DIR}/server_grade.txt"
  exit 2
fi

"${PYTHON_BIN}" "${RUNNER_PATH}" prepare \
  --source-payload "${PAYLOAD_PATH}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name deepseek-v4-flash-w8a8-mtp

modes=(prefix_cache_off prefix_cache_on)
lifecycle_count=0
: > "${RESULT_DIR}/mode_exit_codes.tsv"
for mode in "${modes[@]}"; do
  lifecycle_count=$((lifecycle_count + 1))
  printf '%s\n' "${lifecycle_count}" > "${RESULT_DIR}/server_lifecycle_count.txt"
  set +e
  bash "${MODE_RUNNER_PATH}" "${RESULT_DIR}" "${mode}"
  mode_exit=$?
  set -e
  printf '%s\t%s\n' "${mode}" "${mode_exit}" >> "${RESULT_DIR}/mode_exit_codes.tsv"
  cleanup_path="${RESULT_DIR}/modes/${mode}/cleanup_status.txt"
  if test ! -f "${cleanup_path}" || test "$(<"${cleanup_path}")" != clean; then
    break
  fi
  if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
    printf '%s\n' "${mode}:port_7000_not_released" >> "${RESULT_DIR}/first_failure_excerpt.txt"
    break
  fi
done

cleanup_status=clean
for mode in "${modes[@]}"; do
  cleanup_path="${RESULT_DIR}/modes/${mode}/cleanup_status.txt"
  if test ! -f "${cleanup_path}" || test "$(<"${cleanup_path}")" != clean; then
    cleanup_status=incomplete
  fi
done
if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
  cleanup_status=incomplete
fi
printf '%s\n' "${cleanup_status}" > "${RESULT_DIR}/cleanup_status.txt"

"${PYTHON_BIN}" "${RUNNER_PATH}" finalize --artifact-dir "${RESULT_DIR}"
git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_after.txt"
test ! -s "${RESULT_DIR}/tracked_status_after.txt"
npu-smi info > "${RESULT_DIR}/npu_smi_after.txt" 2>&1 || true
~~~

## 3. 分级与停止边界

- 任一 preflight/hash/resource/live-metrics 门在请求前失败：`blocked_protocol_or_resource_gate`。
- 两边均无 measured success：`red_p6_3b_prefix_cache_matched_ab_no_success`。
- 至少一边有成功但 64 请求、8-group pairing 或 body pairing 不完整：
  `yellow_p6_3b_prefix_cache_matched_ab_partial`。
- 请求完整但 prefix hit/off-inactivity、MTP、queue/counter evidence 不完整：
  `red_p6_3b_prefix_cache_evidence_incomplete`。
- 16/16 prime、48/48 measured 全部首次成功，8 group 双边齐全，Prefix-on 24/24 measured
  follower hit delta >0，Prefix-off hit delta=0，MTP/health/queue/counter/cleanup/hash 全通过：
  `candidate_green_p6_3b_prefix_cache_matched_ab`。

服务器 candidate green 只表示 matched evidence 完整。开发机复核小结果包后，才可接受
`green_p6_3b_prefix_cache_matched_ab` 与具体 mechanism effect。固定 mode/group 顺序、每 group
3 个 measured sample、无显著性检验，禁止扩写为随机化因果、统计显著或任意 workload 普遍收益。
失败不撤销 P6.1C-R1、P6.1、P6.2 或 P6.3A green。

## 4. 结果回报与传输门

raw timestamps、metrics、server logs、request bodies、prompt/token IDs 和 token arrivals 留服务器。
候选小结果总和不得超过 71680 bytes，不得包含 generated content 或 token-ID payload。

不得发送 email、不得调用 upload-api、不得自动选择 server-local。完成后先在当前会话报告：

1. HEAD/origin、tracked 状态、resource/hash/command 门、两个 lifecycle PID/ready/cleanup；
2. 16 prime、48 measured、8-group/body pairing、Prefix on/off counters 与两边 MTP activity；
3. 每 group 的 on/off 描述统计与 paired delta，明确 fixed-order 和无显著性限制；
4. server grade、任何 server-local 适配、raw result root；
5. 精确 `result_summary.md` 路径、完整候选清单、逐文件 bytes/SHA-256/sensitivity、总 bytes；
6. 可用 `email / upload-api / server-local` 方法及一个推荐方法和理由。

等待用户对该完整范围重新选择唯一传输方法；过去选择不继承，失败后不得自动换方法。
