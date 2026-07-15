# Developer to Server

## 当前唯一服务器动作：立即执行 P6.3B-R3 repaired matched A/B

~~~text
task_id: p6_3b_r3_deepseek_v4_flash_w8a8_mtp_repaired_prefix_cache_matched_ab_2026_0715
execution_mode: authorized_for_execution
workload: benchmarks/deepseek_v4_flash/workloads/p6_3b_r3_repaired_prefix_cache_matched_ab.yaml
npu_execution_authorized: true
next_task_authorized: true
standing_npu_and_vllm_consumption_authorization: true
code_sync_and_task_local_r2_repair_authorized: true
claim_boundary: repaired_hybrid_kv_prefix_cache_matched_ab_mechanism_effect_only
~~~

用户已明确授权服务器同步远程 `main`、使用 NPU 0-7、启动 vLLM，并在 Prefix Cache off/on
两个 fresh lifecycle 中加载 same R2 repair。同步、tracked-clean、资源、source/hash 和 patch/self-test
门通过后立即执行，不再等待额外 NPU/vLLM 授权。

若资源门前唯一占卡者是服务器已知的 `npu_trigger_alive` placeholder 及其 worker/forkserver 子进程，
允许停止该 placeholder、记录 PID/命令和释放结果，并在本任务 cleanup 后恢复；不得终止其他用户、
真实模型服务或来源不明的 NPU 进程。若存在真实冲突，停止并报告。

同步只允许：

~~~bash
git fetch origin main
git merge --ff-only origin/main
~~~

不得使用 `pull-remote` alias、`server_local_git_sync.sh`、reset、restore、stash、服务器 commit 或
push。不得修改 base environment 或 site-packages，也不得修改 checkpoint 或 tracked 文件；repair 只存在于每个
mode 的 `server_local/<task_id>/modes/<mode>/runtime/overlay_root` 与该进程内。

## 1. 已关闭证据、当前目的和单变量边界

原 P6.3B 作为历史负证据保留：64/64 HTTP/token/MTP 请求完成，但 Prefix-on 24/24 measured
follower 均 query 正增、hit=0，grade=`yellow_p6_3b_prefix_cache_matched_ab_partial`。R1 因 eager
`sitecustomize` 导入顺序在 server ready 前 `KeyError: AscendMLAAttentionSpec`，0/12 request，
grade=`red_p6_3b_r1_hybrid_kv_repair_no_success`。

P6.3B-R2 已由服务器完成且经开发机复核接受为 `green_p6_3b_r2_hybrid_kv_repair`：3/3 prime、
9/9 measured、9/9 positive hit，32K/64K/128K hit ratio 分别为 0.375/0.5625/0.65625，MTP
accepted delta=384，deferred import order、双 Ascend spec 精确 manager mapping、hybrid diagnostic 与
cleanup 均通过。R2 只证明 repair 与 positive hit，不是 matched performance A/B。

R3 回补原 P6.3B 因 hybrid-KV 缺口而未完成的 matched A/B：

1. 完整复用原 8 组：`4096/32768/65536/131072 × 50%/90% shared prefix`；
2. 每 mode 每组 1 prime + 3 measured，合计 `16 prime + 48 measured = 64`；
3. 两个 fresh lifecycle 固定 `prefix_cache_off -> prefix_cache_on`，无 warmup、无 retry；
4. 两侧加载逐字节相同的 R2 runtime implementation、deferred loader、MTP patch、Ascend
   coordinator patch 与 deferred interface patch；两侧都保持 W8A8、TP8+EP、MTP、graph、
   chunked prefill、`max_num_seqs=1`；
5. 唯一 server argument 差异是 on 侧加入 `--enable-prefix-caching`；
6. 32 个 canonical bodies 只生成一次，跨 mode 按 request ID 逐字节复用；
7. off 侧 hit delta 必须为 0；on 侧 24/24 measured follower 必须逐个 hit delta>0；
8. 两侧 source/hash/self-test、repair identity、deferred import order、retention unset、MTP、
   health/queue/counter、body pairing 与 cleanup 都是 hard gate；on 侧另须完整 hybrid runtime
   diagnostic。off 侧可能不进入 `cache_blocks` 路径，不要求 coordinator snapshot/lookahead 等
   只会在实际缓存分配时出现的事件。

每个 mode 的 runner 都设置 `P6_3B_R2_ENABLE_HYBRID_KV_PATCH=1`，并在启动 NPU server 前确认
`AscendMLAAttentionSpec` 与 `AscendSlidingWindowMLASpec` 两个精确 manager mapping。本任务不运行
profiler 或 HBM sampler；两侧都显式执行 `unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL`。

R3 的 candidate green 只表示 repaired matched evidence 完整。TTFT/TPOT/E2EL/output-throughput
只做固定顺序下的描述统计；是否接受 Prefix Cache mechanism effect 必须由开发机复核，不能由服务器
自动声明普遍加速、统计显著或优化收益。本任务通过后也不得自动进入 P6.3C。

## 2. 执行合同

不要预先创建结果目录。从同一个 shell 完整执行：

~~~bash
set -euo pipefail

NPU_EXECUTION_AUTHORIZED=true
NEXT_TASK_AUTHORIZED=true
test "${NPU_EXECUTION_AUTHORIZED}" = true
test "${NEXT_TASK_AUTHORIZED}" = true

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_3b_r3_deepseek_v4_flash_w8a8_mtp_repaired_prefix_cache_matched_ab_2026_0715
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
PYTHON_BIN="${ENV_PREFIX}/bin/python"
WORKLOAD_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_3b_r3_repaired_prefix_cache_matched_ab.yaml"
RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_r3_repaired_matched_ab.py"
MODE_RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_3b_r3_mode.sh"
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

npu-smi info > /tmp/p6_3b_r3_npu_smi_before.txt 2>&1
"${PYTHON_BIN}" - /tmp/p6_3b_r3_npu_smi_before.txt <<'PY'
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

mkdir -p "${RESULT_DIR}"/modes
cp /tmp/p6_3b_r3_npu_smi_before.txt "${RESULT_DIR}/npu_smi_before.txt"
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/source_payload_sha256.txt"
export REPO_ROOT ENV_PREFIX PYTHON_BIN
export BASE_VLLM_ROOT
export BASE_PLUGIN_ROOT
BASE_VLLM_ROOT=$("${PYTHON_BIN}" -c 'from importlib.util import find_spec; from pathlib import Path; print(Path(find_spec("vllm").origin).resolve().parent)')
BASE_PLUGIN_ROOT=$("${PYTHON_BIN}" -c 'from importlib.util import find_spec; from pathlib import Path; print(Path(find_spec("vllm_ascend").origin).resolve().parent)')

"${PYTHON_BIN}" "${RUNNER_PATH}" prepare \
  --source-payload "${PAYLOAD_PATH}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name deepseek-v4-flash-w8a8-mtp

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

`BASE_VLLM_ROOT`/`BASE_PLUGIN_ROOT` 只用于适配服务器 editable install 的真实 import root；mode runner
仍会对四个 installed source 做精确 bytes/SHA-256 gate。tracked runner 已内置 deferred patch 的
CRLF 兼容：优先 `patch -l`，失败时只在 task overlay 使用 `git apply --ignore-whitespace`，最终
overlay interface/coordinator/proposer hash 必须与冻结值精确相等；不得再创建 server-local wrapper
改变合同逻辑。

## 3. 停止、分级与 cleanup

- 不允许 retry、same-mode restart、改变 mode order、删组/降 context/改 ratio/repeat/body、调参、
  第二 patch、关闭 MTP/chunked prefill/graph、改变 `max_num_seqs`、eager fallback、升级版本或自动修复。
- off mode 请求失败但 cleanup clean 时继续独立 on mode；cleanup 不 clean 时立即停止。
- source/hash/patch/self-test/resource 门未过且未发请求：
  `blocked_p6_3b_r3_source_or_resource_gate`。
- 没有 matched measured success：
  `red_p6_3b_r3_repaired_prefix_cache_matched_ab_no_success`。
- 结构未完整：`yellow_p6_3b_r3_repaired_prefix_cache_matched_ab_partial`。
- 64/64 请求结构完成但 body pairing、双 mode repair/适用诊断、on positive hit、off zero hit、
  MTP/queue/counter 或其他 evidence gate 不完整：
  `red_p6_3b_r3_repaired_prefix_cache_evidence_incomplete`。
- 只有 16/16 prime、48/48 measured、24/24 on measured positive hit、off hit=0、body pairing、
  same R2 repair、双侧安装/导入/源码/retention 证据、on 侧完整 hybrid diagnostic、
  MTP/health/queue/counter 与 cleanup 全过，才可给
  `candidate_green_p6_3b_r3_repaired_prefix_cache_matched_ab`。
- 原 P6.3B yellow、R1 red、R2 green 与其他 P6 green 在 R3 任意失败下均保留。

任务结束必须关闭两个 vLLM lifecycle、释放端口 7000、确认 tracked 工作树干净，并按任务开始前
状态恢复已知 `npu_trigger_alive` placeholder。恢复 placeholder 不改变实验 cleanup 结论，但必须单列
恢复 PID/命令/设备占用状态。

## 4. 回报与传输门

先在当前任务会话中回报：

1. HEAD/origin、tracked status、同步方法、资源门、四 installed source 与全部 repo/overlay hash；
2. 两个 lifecycle PID、ready/mode/finalize exit、server command hash、repair identity 与 cleanup；
3. 8 组 × 2 mode 的 prime/measured success、query/hit、MTP accepted、TTFT/TPOT/E2EL/output
   throughput 描述统计与 24 个 paired row；
4. 双 mode deferred import order、Ascend manager mapping、source hash、retention unset 与 repair
   identity；on 侧另报 KV group/spec/manager、LCM、EAGLE/SWA、lookahead/reachable mask 与完整
   hybrid diagnostic。off 侧若未进入 `cache_blocks` 路径，明确报告缺失这些 runtime event，
   但不得因此单独判失败；
5. server grade、claim boundary、首错、server-local raw root；
6. 精确 `result_summary.md` 路径、完整候选清单、逐文件 bytes/SHA-256/sensitivity、总字节、
   `email / upload-api / server-local` 三种可用方法及一个推荐方法和理由。

bounded candidate 总量不得超过 70KB，不得包含 generated text、token IDs、raw body、raw metrics、
raw diagnostic、vLLM log 或 profiler 文件。原始数据留服务器。当前 handoff 不含传输授权：不得发送 email，
不得调用 upload-api，不得自动选择 server-local。等待用户对该完整范围重新选择唯一传输方法；
过去选择不继承，失败后不得自动重试或换方法。

完成 R3 后停止。即使 candidate green，也不得自动进入 P6.3C、P7、P8 或 P9；P6.3C 必须由开发机
复核 R3 后发布新的 workload 和唯一 handoff。
