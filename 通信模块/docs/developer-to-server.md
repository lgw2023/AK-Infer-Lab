# Developer to Server

## 当前唯一服务器动作：立即执行 P6.3B-R4 explicit Prefix Cache control matched A/B

~~~text
task_id: p6_3b_r4_deepseek_v4_flash_w8a8_mtp_explicit_prefix_cache_matched_ab_2026_0716
execution_mode: authorized_for_execution
workload: benchmarks/deepseek_v4_flash/workloads/p6_3b_r4_explicit_prefix_cache_matched_ab.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
code_sync_and_task_local_r2_repair_authorized: true
claim_boundary: explicit_prefix_cache_control_repaired_hybrid_kv_matched_ab_mechanism_effect_only
~~~

用户已明确授权服务器同步远程 `main`、使用 NPU 0-7、启动 vLLM，并立即执行本任务；不再等待额外
NPU/vLLM 确认。同步只允许：

~~~bash
git fetch origin main
git merge --ff-only origin/main
~~~

不得使用 `pull-remote` alias、`server_local_git_sync.sh`、reset、restore、stash、服务器 commit 或 push。
主镜像 tracked 文件、checkpoint 和 tokenizer 均不得修改；不得修改 base environment 或 site-packages；R2 repair 只加载到
每个 mode 的 task-local overlay 与进程内。

若资源门前唯一占卡者是已知 `npu_trigger_alive` placeholder 及其 worker/forkserver 子进程，允许停止它、
记录 PID/命令/释放结果，并在 cleanup 后恢复；不得终止其他用户、真实服务或来源不明的进程。存在真实
资源冲突时停止并报告。

## 1. 为什么执行 R4

原 P6.3B 保留 `yellow_p6_3b_prefix_cache_matched_ab_partial`。R2 已由开发机接受为
`green_p6_3b_r2_hybrid_kv_repair`，证明 deferred-install repair 能在
`32768/65536/131072 × 90%` 重复前缀下形成 9/9 positive hit。R3 的 64/64 HTTP/token/MTP、same
R2 repair、hybrid diagnostics 和 cleanup 均完成，但它保留为
`yellow_p6_3b_r3_repaired_prefix_cache_matched_ab_partial`，原因不是推理失败，而是 control 合同错误：

~~~text
R3 prefix_cache_off: 省略 --enable-prefix-caching -> 继承 vLLM 默认 true
R3 prefix_cache_on:  显式 --enable-prefix-caching -> true
effective comparison: repaired Prefix Cache on vs on
~~~

R3 两侧 24/24 measured pair 的 hit delta 完全相同，两侧均为 9/24 positive、总 hit=540672；不得接受
任何 on-minus-off mechanism/performance effect。R4 只修复这个控制变量：

~~~text
prefix_cache_off: --no-enable-prefix-caching
prefix_cache_on:  --enable-prefix-caching
~~~

两侧继续加载逐字节相同的 same R2 repair（runtime/deferred/MTP/coordinator/interface），其他 server args、32 个
canonical bodies、八组顺序和 repeats 全同。R4 保留原完整矩阵：
`4096/32768/65536/131072 × 50%/90%`，每 mode 每组 `1 prime + 3 measured`，总计
`16 prime + 48 measured = 64` request；两个 fresh lifecycle 固定 `off -> on`，无 warmup、无 retry。

`P6 R3.md` 提出的 token-LCP 建议已进入 tracked runner：prepare 阶段会从 server-local body 计算
`planned_shared_tokens / actual_token_lcp / actual_lcp_sha256 / actual_lcp_mod_128 /
actual_lcp_mod_16384 / expected_prefix_hit_tokens`。小结果 manifest 不含 prompt/token IDs；body 与 token IDs
仍留服务器。

Green 的正命中 hard gate 只绑定 R2/R3 已证明的三个 primary group：

~~~text
ctx32768_prefix90 / ctx65536_prefix90 / ctx131072_prefix90
9/9 measured follower 必须 positive hit
每条 observed hit 必须等于 floor(actual_token_lcp / 16384) * 16384
~~~

其余 5 组共 15 个 measured follower 是 boundary diagnosis：允许 on 侧 hit=0，但必须完整报告实际 LCP、
query/hit 和 16K floor；不得再用“所有 50% shared prefix 小于 16K”解释长 context 的零命中。off 侧
所有 request 的 hit delta 总和必须严格为 0。

R4 candidate green 只表示 repaired explicit-control matched evidence 完整。TTFT/TPOT/E2EL/throughput 仅作
固定顺序描述统计；服务器不得自动接受 mechanism effect、普遍加速、统计显著性或优化收益。完成后停止，
不得自动进入 P6.3C、P7、P8 或 P9。

## 2. 执行合同

不要预先创建任务结果目录。从同一个 shell 完整执行：

~~~bash
set -euo pipefail

NPU_EXECUTION_AUTHORIZED=true
NEXT_TASK_AUTHORIZED=true
test "${NPU_EXECUTION_AUTHORIZED}" = true
test "${NEXT_TASK_AUTHORIZED}" = true

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_3b_r4_deepseek_v4_flash_w8a8_mtp_explicit_prefix_cache_matched_ab_2026_0716
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
PYTHON_BIN="${ENV_PREFIX}/bin/python"
WORKLOAD_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_3b_r4_explicit_prefix_cache_matched_ab.yaml"
RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_r4_explicit_matched_ab.py"
MODE_RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_r4_mode.sh"
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

test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1

npu-smi info > /tmp/p6_3b_r4_npu_smi_before.txt 2>&1
"${PYTHON_BIN}" - /tmp/p6_3b_r4_npu_smi_before.txt <<'PY'
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
assert health == {index: "OK" for index in range(8)}, health
assert idle == set(range(8)), idle
PY
if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
  printf '%s\n' blocked_port_7000 >&2
  exit 2
fi

mkdir -p "${RESULT_DIR}/modes"
cp /tmp/p6_3b_r4_npu_smi_before.txt "${RESULT_DIR}/npu_smi_before.txt"
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/source_payload_sha256.txt"
export REPO_ROOT ENV_PREFIX PYTHON_BIN
export BASE_VLLM_ROOT BASE_PLUGIN_ROOT
BASE_VLLM_ROOT=$("${PYTHON_BIN}" -c 'from importlib.util import find_spec; from pathlib import Path; print(Path(find_spec("vllm").origin).resolve().parent)')
BASE_PLUGIN_ROOT=$("${PYTHON_BIN}" -c 'from importlib.util import find_spec; from pathlib import Path; print(Path(find_spec("vllm_ascend").origin).resolve().parent)')

"${PYTHON_BIN}" "${RUNNER_PATH}" prepare \
  --source-payload "${PAYLOAD_PATH}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name deepseek-v4-flash-w8a8-mtp

"${PYTHON_BIN}" - "${RESULT_DIR}/request_body_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert manifest["token_lcp_evidence_ok"] is True
assert manifest["request_count"] == 32
assert manifest["generated_text_retained"] is False
assert manifest["token_ids_retained"] is False
measured = [row for row in manifest["records"] if row["request_role"] == "measured"]
assert len(measured) == 24
assert all(len(row["actual_lcp_sha256"]) == 64 for row in measured)
PY

printf '%s\n' 0 > "${RESULT_DIR}/server_lifecycle_count.txt"
for mode in prefix_cache_off prefix_cache_on; do
  set +e
  bash "${MODE_RUNNER_PATH}" "${RESULT_DIR}" "${mode}"
  mode_exit=$?
  set -e
  printf '%s\n' "${mode_exit}" > "${RESULT_DIR}/modes/${mode}/mode_exit_code.txt"
  lifecycle_count=$(cat "${RESULT_DIR}/server_lifecycle_count.txt")
  printf '%s\n' "$((lifecycle_count + 1))" > "${RESULT_DIR}/server_lifecycle_count.txt"

  test -f "${RESULT_DIR}/modes/${mode}/cleanup_status.txt"
  if test "$(cat "${RESULT_DIR}/modes/${mode}/cleanup_status.txt")" != clean; then
    break
  fi
  if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
    printf '%s\n' incomplete > "${RESULT_DIR}/modes/${mode}/cleanup_status.txt"
    break
  fi
done

set +e
"${PYTHON_BIN}" "${RUNNER_PATH}" finalize --artifact-dir "${RESULT_DIR}"
finalize_exit=$?
set -e
printf '%s\n' "${finalize_exit}" > "${RESULT_DIR}/finalize_exit_code.txt"

git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_after.txt"
test ! -s "${RESULT_DIR}/tracked_status_after.txt"
npu-smi info > "${RESULT_DIR}/npu_smi_after.txt" 2>&1 || true
if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
  printf '%s\n' incomplete > "${RESULT_DIR}/cleanup_status.txt"
fi

printf 'HEAD=%s\n' "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
printf 'origin/main=%s\n' "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
printf 'server_grade=%s\n' "$(cat "${RESULT_DIR}/server_grade.txt")"
printf 'result_summary=%s\n' "${RESULT_DIR}/result_summary.md"
printf 'delivery_candidates=%s\n' "${RESULT_DIR}/delivery_candidates.tsv"
printf 'delivery_total_bytes=%s\n' "$(cat "${RESULT_DIR}/delivery_candidates_total_bytes.txt")"
exit "${finalize_exit}"
~~~

`BASE_VLLM_ROOT`/`BASE_PLUGIN_ROOT` 只适配 editable install 的真实 import root；R4 mode runner 会对四个
installed source、R2 repair、三份 patch 和最终 overlay hashes 做精确 gate。R4 wrapper 冻结两个 command
SHA-256：off=`def3dd8b…`、on=`370f8d25…`。

每个 server PID 启动后、任何请求前，runner 会读取冻结 server command 与 live
`/proc/<PID>/cmdline`，写 `resolved_prefix_cache_config.json`。off 必须只有
`--no-enable-prefix-caching` 且 resolved=false；on 必须只有 `--enable-prefix-caching` 且 resolved=true。
任一 expected flag 缺失、opposite flag 出现或 JSON 缺失，立即 cleanup 并停止该 mode；不得靠 metrics 猜开关。

## 3. 停止、分级和允许的就地适配

- 不允许 retry、same-mode restart、交换 mode order、删组、降 context/ratio/repeat、改 body、改 repair、
  改 Prefix Cache flag、关闭 MTP/chunked prefill/graph、改变 `max_num_seqs`、eager fallback、版本升级、
  profiler/HBM sampler 或自动修复。
- off mode 失败但 cleanup clean 时继续独立 on mode，以保留诊断；cleanup 不 clean 立即停止。
- source/hash/resource/config/LCP 门未过且无请求：`blocked_p6_3b_r4_source_or_resource_gate`。
- 无 matched measured success：`red_p6_3b_r4_explicit_prefix_cache_matched_ab_no_success`。
- 结构不完整：`yellow_p6_3b_r4_explicit_prefix_cache_matched_ab_partial`。
- 64/64 请求完成但显式 control、off zero-hit、primary 9/9、LCM floor、same repair、diagnostic、MTP/
  health/queue/counter 或 cleanup 任一不完整：`red_p6_3b_r4_explicit_prefix_cache_evidence_incomplete`。
- 全门通过：`candidate_green_p6_3b_r4_explicit_prefix_cache_matched_ab`；只有开发机复核后才能接受
  `green_p6_3b_r4_explicit_prefix_cache_matched_ab` 与 mechanism effect。

无需新往返即可做且必须逐项报告的 server-local 适配仅限：目录创建、shell quoting/line-ending、`set -u`
source 兼容、精确 source hash 相同前提下的 editable import-root 选择、实际命令输出解析、等价 runner 错误处理、
已知 placeholder 的停止与恢复。不得修改 tracked 文件、site-packages、runtime/model/body/order/repeat/R2 repair、
两个显式 flag 或指标定义。

R4 失败不撤销 R2、P6.1C-R1、P6.1、P6.2、P6.3A green，也不覆盖原 P6.3B/R1/R3 负证据。

## 4. 回报与传输门

执行完成后先在当前对话回报：HEAD/origin/tracked；资源/source/patch/command/config/LCP 门；两个 PID、ready/
mode/finalize exit 与 cleanup；64-request、逐组 prime/measured、off/on query/hit、primary 9/9、boundary 15 条、
MTP counters、hybrid diagnostics；server grade、首错和 raw root。

原始 logs/metrics/diagnostics/bodies/token IDs 留服务器。只准备 workload 所列 bounded candidates，总量必须
`<=71680` bytes；结果离开服务器前必须报告精确 summary 路径、完整候选清单、逐文件 bytes/SHA-256/
sensitivity、可用 `email / upload-api / server-local` 和推荐理由，并等待用户对这一次完整范围作单一选择。
当前 handoff 不含传输授权：不得调用 upload-api，不得发送 email，不得继承旧选择，也不得失败后自动换方法。

任务完成后停止；不得自动进入 P6.3C。
