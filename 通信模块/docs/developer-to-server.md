# Developer to Server

## 当前唯一服务器动作：同步并执行 P6.3A matched MTP on/off

~~~text
task_id: p6_3a_deepseek_v4_flash_w8a8_mtp_matched_ab_2026_0715
execution_mode: authorized_for_execution
workload: benchmarks/deepseek_v4_flash/workloads/p6_3a_mtp_matched_ab.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
~~~

用户已明确授权当前 P6.3A 服务器、NPU 与 vLLM 执行，并允许后续已发布的明确 workload
持续使用 NPU/vLLM，不需要再把资源消费门切回 false。本授权不允许服务器在缺少新 workload
和唯一 handoff 时自行发明实验；本任务完成后不得自动进入 P6.3B、P6.3C、P7 或 P8。
不得自动进入 P8，也不得把 standing resource authorization 当作跨 workload 执行许可。
同步到远程 `main` 后通过全部硬门立即执行，不需要再等待一次资源授权确认。同步方法仍固定为：

~~~bash
git fetch origin main
git merge --ff-only origin/main
~~~

P6.1C-R1、P6.1 与 P6.2 已分别由开发机接受为
`green_mtp_official_context_ladder`、`green_mtp_unprofiled_baseline` 和
`green_mtp_profiled_evidence`。P6.2 已由开发机接受为 `green_mtp_profiled_evidence`。
本任务只回答同一冻结 runtime 下 MTP on/off 的 matched mechanism effect；不运行 profiler、
HBM sampler，不覆盖 P6.1 performance reference，也不预设 MTP 一定更快。

## 1. Matched 合同与执行边界

两个 fresh lifecycle 固定按 `mtp_off -> mtp_on` 执行。唯一 server 自变量是：

- `mtp_off`：省略 `--speculative-config`；
- `mtp_on`：增加 `--speculative-config '{"method":"mtp","num_speculative_tokens":1}'`。

两边其余模型、runtime、NPU 0-7、TP8+EP、W8A8、graph、`max_num_seqs=1`、prefix cache、
chunked prefill、环境变量、task-local overlay 和全部 server 参数完全相同。冻结哈希：

~~~text
patch: 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
overlay proposer: 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
base proposer: 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
mtp_off server command: c8490730b269ca2cf8a72704877ab040099341ec5fe576ee010d3613a61902bc
mtp_on server command: 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
source payload: 19487 bytes / 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
~~~

每个 mode 先执行一次排除统计的 `4096+64+c1` warmup，再按相同顺序执行以下 8 个 cell，
每 cell 3 个 measured batch：

~~~text
short_prefill:  4096+64+c1
short_decode:   4096+256+c1
short_decode_c8:4096+256+c8
mid_prefill:    65536+64+c1
mid_prefill_c4: 65536+64+c4
mid_decode:     65536+256+c1
long_prefill:   131072+64+c1
long_decode:    131072+256+c1
~~~

总计 2 个 lifecycle、2 个 warmup、48 个 measured batch、108 个 measured request、0 retry。
55 份 canonical body 在第一个 server 启动前只生成一次；两个 mode 必须复用相同字节和 SHA-256。
mode 内独立 batch 失败后，只要原 server 存活、health=200、queue idle，可继续后续 batch；
第一个 mode 失败后只要 cleanup clean、7000 端口释放，仍执行第二 mode，以保全 matched 证据。

服务器助手可直接修正 server-local 的 mkdir/path、shell quoting、`set -u` source 兼容、
真实命令输出 parser 和等价错误处理，不必等待新往返；必须在摘要中记录修正，并证明未改变
tracked 文件、runtime/site-packages、body、cell/repeat/order、server 单变量或指标定义。禁止重试、
同 mode restart、第二 patch、调参、降档、eager fallback、版本升级或 profiler/HBM sampler。

## 2. 同步、资源门、执行与清理

从一个 shell 完整执行以下区块。不得使用 `pull-remote` alias、
`server_local_git_sync.sh`、reset、restore、stash、commit 或 push。

~~~bash
set -euo pipefail

NPU_EXECUTION_AUTHORIZED=true
test "${NPU_EXECUTION_AUTHORIZED}" = true

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_3a_deepseek_v4_flash_w8a8_mtp_matched_ab_2026_0715
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
PYTHON_BIN="${ENV_PREFIX}/bin/python"
WORKLOAD_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_3a_mtp_matched_ab.yaml"
RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3a_matched_ab.py"
MODE_RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3a_mode.sh"
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

modes=(mtp_off mtp_on)
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

## 3. 计量、分级与声明边界

client 只累计 token-ID 数量和到达时间，不保存 token IDs 或 generated text。TTFT、TPOT、ITL、
E2EL、per-request throughput、batch output throughput 与 request throughput 使用 P6.1 相同定义；
c4/c8 的 E2EL 包含 `max_num_seqs=1` 下的排队时间。每个 cell/report 同时保留 mode、n、
min/median/max/mean/CV，以及按 `cell_id + repeat_index` 配对的 on-minus-off 绝对/相对差。
3 个 pair 只作描述统计，不声明显著性；固定 `mtp_off -> mtp_on` 顺序必须列为限制。

两种 mode 都要求 health=200、running=waiting=0 和 queue metrics 完整。`mtp_on` 每个成功 batch
要求 drafts/draft_tokens 正增量，全部 measured 累计 accepted >0；`mtp_off` 允许 speculative
counters 不导出，若导出则三项 delta 必须为 0。counter continuity 只要求各 lifecycle 内连续，
不跨 fresh lifecycle 比较。

48/48 measured batch、108/108 measured request 全部首次成功，8 个 cell 双边齐全、body pairing、
token/stream/finish、health/queue/counter、两次 cleanup 和命令哈希全部通过，服务器才给
`candidate_green_p6_3a_mtp_matched_ab`。这个 green 表示 matched evidence 完整，不表示 MTP 更快；
只有开发机复核小结果包后才能接受 `green_p6_3a_mtp_matched_ab` 和具体 mechanism effect。
失败不撤销既有 P6.1C-R1、P6.1 或 P6.2 green。

## 4. 结果回报与传输门

raw timestamps、metrics、server logs、request bodies、token arrival 和错误正文留服务器。
候选小结果总和不得超过 71680 bytes，generated text/token IDs 禁止进入候选包。

不得发送 email、不得调用 upload-api、不得自动选择 server-local。完成后先在当前会话报告：

1. HEAD/origin、tracked 状态、resource/hash/command 门、两个 lifecycle PID/ready/cleanup；
2. 两个 warmup、48 batch、108 request、8-cell 双边、body pairing 与 MTP activity 汇总；
3. 每 cell 的 mode 统计和 paired delta，明确固定顺序限制且不预设收益；
4. server grade、任何 server-local 适配、raw result root；
5. 精确 `result_summary.md`、完整候选清单、逐文件 bytes/SHA-256/sensitivity、总 bytes；
6. 可用 `email / upload-api / server-local` 方法及一个推荐方法和理由。

等待用户对该完整范围重新选择唯一传输方法；过去选择不继承，失败后不得自动换方法。
