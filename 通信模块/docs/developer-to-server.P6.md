# P6.3C-R3E-F2-D2 服务器任务：既有 raw profiler 的零 NPU 离线解析与证据收口

本文件是当前唯一 P6 服务器交接，取代 D1 的 marker 路径诊断与 S1 retry 任务。D1 已经把问题从
“worker marker 是否传播”收缩到“Ascend profiler 的 daemon-process 导出与离线解析是否能产生现有
analyzer 可读的 Chrome JSON”。本轮只复用已经存在的 raw profiler 数据做 CPU/磁盘侧离线处理；禁止
启动 vLLM、禁止新 lifecycle、禁止停止 keep-alive、禁止任何 NPU 工作。

## 1. 任务身份、授权与当前事实

- task ID：
  `p6_3c_r3e_f2_d2_offline_profiler_analysis_and_evidence_finalize_2026_0820`；
- source experiment task ID：
  `p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820`；
- source experiment commit：`b146b5005b9774aed134701119b1bf233f68ac11`；
- D1 task ID：
  `p6_3c_r3e_f2_d1_marker_path_diagnosis_and_bounded_s1_retry_2026_0820`；
- D1 task commit：`31198020a4bbdd528389eff4d1eb274d87acf5b5`；
- task execution authorized：`true`；
- NPU operation authorized：`false`；
- S1/S2/new lifecycle authorized：`false`；
- `result_transfer_authorized: true`；
- `transfer_method_selected: false`；
- `next_larger_task_authorized: false`；
- 服务器不得 push remote `main`。

开发机已只读审计 D1 回传目录
`/Volumes/SSD1/Inbox/2026-08-20/p6_3c_r3e_f2_d1_2026_0820/`。收到 8 个文件、共 24,613 bytes，
4 个 JSON 均可解析；但没有终态 `candidate_manifest.server_local.json`，也没有 D1 的 final result、
scientific outcome 与独立 resource-recovery 文件。因此以下事实按“服务器报告支持，但仍待 D2 补齐
逐 rank 与终态 manifest”处理：

1. engine PID 1474335 在 step 31 发出一次 `dependency_marker_scheduled`，context ID 为
   `1474335:31:281454312491088`；
2. rank 0–7 的 8 个真实 worker 均有一次 `dependency_marker_worker_enter` 与一次
   `dependency_marker_worker_exit`，context ID 与 step 均一致；
3. D0 报告 8 份 raw `FRAMEWORK/torch.op_range` 各含一次 `AK_P6_R3E_F2` marker；
4. 现有 analyzer 只发现 `trace_view.json(.gz)` 或 `.pt.trace.json(.gz)`，D0/D1 均发现 0 份；
5. D1 在新的 S1 上尝试 `export_chrome_trace()`，但运行该调用的 vLLM worker 是 daemon process，
   torch-npu 报告 `The profiling data cannot be parsed during the daemon process`；
6. D1 报告该 S1 完成 10/10 requests、raw marker 8/8，并报告 0–7 keep-alive 精确恢复；但这些 D1
   终态结果未以完整 result/resource/manifest 小包返回，D2 必须核对服务器本地原件；
7. S2 从未执行；`causal_bottleneck_resolved=false`、`optimization_target_selected=false`、
   `performance_gain_claimed=false` 保持不变。

## 2. D2 研究问题与声明边界

D2 只回答三个顺序问题：

1. 在非 daemon、零 NPU 的独立 Python 进程中，已安装 torch-npu 的官方
   `torch_npu.profiler.profiler.analyse()` 能否把 D1 已有 raw profiler 目录导出为完整
   `ASCEND_PROFILER_OUTPUT/trace_view.json`；
2. 若能，8 个 rank 的 Chrome JSON 是否均包含格式精确且恰好一次的 F2 marker；
3. 若能，发布版 F2 analyzer 能否在这一个 S1 pressure step 上恢复 marker→host、host→runtime、
   runtime→actual-device-kernel 三段结构化依赖链。

D2 不生成新的性能样本，不重新测量请求，不改变 policy、参数、marker payload、profiler window、
event-domain/link 定义或 metric。即使 8/8 rank 的三段链全部闭合，也只能把这一个 S1 canary 记为
positive；本轮固定：

```text
S1_retry_executed=false
S2_executed=false
causal_bottleneck_resolved=false
optimization_target_selected=false
performance_gain_claimed=false
```

时间包含、duration sum、`Free/Computing/Communication/Communication(Not Overlapped)/Notify_Wait`
等派生轨道不得满足 actual-kernel edge。后两段边只接受发布版 analyzer 定义的 flow/correlation 共同
标识。不得为获得“更好结论”写自定义 raw-binary→Chrome 转换器、放宽 edge 定义或手工构造 analyzer
输出；若官方离线解析仍失败，精确报告工具边界就是本轮有效结果。

## 3. 同步、独立 worktree 与来源目录保护

immutable Inbox prompt 会设置 `AK_SERVER_TASK_COMMIT`。服务器先同步并锁定该 commit：

```bash
SHARED_REPO=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_3c_r3e_f2_d2_offline_profiler_analysis_and_evidence_finalize_2026_0820
AK_SERVER_TASK_COMMIT=${AK_SERVER_TASK_COMMIT:?set from immutable Inbox prompt}
WORKTREE=/data/node0_disk1/liguowei/server_worktrees/p6_3c_r3e_f2_d2_2026_0820
D2_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_d2_2026_0820_attempt_01

git -C "${SHARED_REPO}" fetch origin main
test "$(git -C "${SHARED_REPO}" rev-parse origin/main)" = "${AK_SERVER_TASK_COMMIT}"
git -C "${SHARED_REPO}" cat-file -e "${AK_SERVER_TASK_COMMIT}^{commit}"
test ! -e "${WORKTREE}"
git -C "${SHARED_REPO}" worktree add --detach "${WORKTREE}" "${AK_SERVER_TASK_COMMIT}"
cd "${WORKTREE}"
test "$(git rev-parse HEAD)" = "${AK_SERVER_TASK_COMMIT}"
test "$(git rev-list --left-right --count HEAD...origin/main)" = $'0\t0'
test -z "$(git status --porcelain --untracked-files=no)"
test ! -e "${D2_ROOT}"
mkdir -p "${D2_ROOT}"
```

若 worktree 或 `D2_ROOT` 已存在，不删除、不覆盖；核对任务归属后使用后缀 `_attempt_02` 并记录原因。
不得修改共享 checkout、已安装 package、D0/D1 诊断目录或任何 source/retry result。不得使用硬链接或
指向 source result 的 symlink 作为可写 offline-parse 目标，因为官方 parser 会在输入树内生成输出。

进入 worktree 后完整阅读：

```text
docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md
通信模块/docs/developer-to-server.P6.md
tools/inference_contracts/analyze_torch_profiler_traces.py
tools/inference_contracts/analyze_p6_3c_r3e_f2_dependency_markers.py
tools/inference_contracts/p6_3c_r3e_f2_dependency_marker.py
```

## 4. D2-0：只读发现 D1 原件并补齐来源身份

按以下候选路径核对，不凭回传摘要创建空目录：

```bash
SOURCE_ATTEMPT_01=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_2026_0820_attempt_01/p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820
D1_DIAG_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_d1_2026_0820_attempt_01
RETRY_RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_f2_2026_0820_attempt_02/p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820
```

1. 优先验证 `RETRY_RESULT_DIR`。若不存在，只在
   `/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/` 第一层按 source task ID、D1 task ID 与
   mtime 做有界查找；报告所有候选后选择身份可证的唯一目录。不得递归扫描其他项目或全盘。
2. 核对 retry 中只有一个 `f2_s1_01=admission_on_t4096` lifecycle、一个 selected pressure step，
   且没有 S2 lifecycle；核对 request count、run plan、scheduler trace、server log、cleanup、existing
   stage analysis 与 raw profiler 根。
3. 找到 8 个 rank 目录；逐 rank 记录 rank、PID、精确 path、文件数、总 bytes、目录 mtime，以及
   `profiler_info*.json`、`FRAMEWORK/torch.op_range`、`FRAMEWORK/torch.op_mark` 与 CANN raw 数据的实际
   路径/bytes。
4. 对 `torch.op_range`、`torch.op_mark`、`profiler_info*.json` 生成逐 rank SHA-256；记录 marker 的
   byte-level exact-name occurrence count 与使用的命令。原始 marker 字符串不得写入对外小包，计数和
   schema-safe 名称可返回。
5. 生成 source metadata inventory（relative path、bytes、mtime_ns、type）及其 SHA-256。D2 结束后
   重算并要求完全一致；若来源变化，停止并报告，不得继续解释分析结果。
6. 核对 D1 报告的 patch、attempt history、10/10 requests 与 resource recovery 原件。找不到的字段
   记为 `not_evidenced_server_local`，不能用开发机回传摘要补造。

至少输出：

```text
source_retry_identity.json
source_retry_inventory.tsv
source_key_file_sha256.tsv
d1_terminal_artifact_review.json
```

## 5. D2-1：核对服务器实际 torch-npu 解析实现

使用 retry 原件记录的 Python/conda 环境；预期环境为：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
```

先以原件的 `environment_and_hashes.json`、server command 与进程环境核对，再设置并验证：

```bash
PYTHON_BIN=/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
test -x "${PYTHON_BIN}"
PYTHON_BIN=$(readlink -f "${PYTHON_BIN}")
```

不得只依据预期路径。记录实际 Python realpath/version，以及下列实际安装文件的 realpath、bytes、
SHA-256 与相关源码行：

```text
torch_npu/profiler/profiler.py
torch_npu/profiler/profiler_interface.py
torch_npu/profiler/analysis/_npu_profiler.py
torch_npu/profiler/analysis/prof_common_func/_constant.py
```

核对并报告：

- `torch_npu.__version__`、`torch.__version__`；
- public `analyse` 的真实 signature 与合法 `export_type` 值；
- `_KinetoProfile.export_chrome_trace()` 最终调用路径；
- `multiprocessing.current_process().daemon` guard 的真实条件和提示；
- offline parser 默认输出位置、是否写输入目录、是否会启动 multiprocessing pool；
- `@no_exception_func` 是否可能吞掉异常，使 process exit code 0 但没有有效输出。

生成 `installed_profiler_source_review.json`。若实际 2.10.0 源码与 D1 描述不同，按真实源码自适应离线
调用方式，保留命令与差异；不得修改已安装源码。

## 6. D2-2：建立独立可写副本与 rank-0 离线 canary

先记录 source tree bytes、目标文件系统可用空间和 copy strategy。默认以 reflink 建立独立 inode 的
完整工作副本：

```bash
OFFLINE_RESULT_DIR=${D2_ROOT}/offline_working_result
test ! -e "${OFFLINE_RESULT_DIR}"
cp -a --reflink=always "${RETRY_RESULT_DIR}" "${OFFLINE_RESULT_DIR}"
```

若文件系统不支持 reflink，可在空间足够容纳 `source_bytes + 20%` 安全余量时使用
`cp -a --reflink=auto`；否则停止并报告 `insufficient_safe_copy_capacity`。不得使用 `cp -al`、硬链接、
bind mount 或可写 symlink。抽查并记录 source/copy 的 device+inode 不同、key-file SHA 相同、总文件
数与总 bytes 一致。copy 失败不得部分解析，也不得删除 source；可保留 D2 部分目录供审计。

在工作副本中先选择 rank 0 的单个 `*_ascend_pt` 目录。以顶层、非 daemon Python 进程调用服务器实际
public API；下面仅是预期形态，参数必须以 D2-1 的真实 signature 为准：

```bash
export CANARY_PROFILER_PATH=/absolute/path/in/offline_working_result/to/rank0_ascend_pt
"${PYTHON_BIN}" - <<'PY' >"${D2_ROOT}/offline_rank0.stdout.log" 2>"${D2_ROOT}/offline_rank0.stderr.log"
import multiprocessing
import os
from torch_npu.profiler.profiler import analyse

assert multiprocessing.current_process().daemon is False
analyse(
    profiler_path=os.environ["CANARY_PROFILER_PATH"],
    max_process_number=1,
    export_type=["text"],
)
PY
```

记录开始/结束时间、命令、exit code、stdout/stderr SHA 与解析前后新增文件 inventory。由于 profiler API
可能吞异常，exit 0 不是成功门。rank-0 canary 只有同时满足以下条件才通过：

1. 在 rank-0 工作副本中生成唯一 `ASCEND_PROFILER_OUTPUT/trace_view.json` 或服务器实际官方等价
   Chrome trace；
2. 文件非空，顶层 schema 为裸 event array 或含 `traceEvents` 的 object；
3. 发布版 streaming parser 两遍均读到 JSON 末尾、无 event cap、无 parse error；
4. rank mapping 可证，格式精确的 F2 marker 恰好一次；
5. source result metadata manifest 与 key-file SHA 未变化；
6. 没有 NPU/vLLM process 被启动，keep-alive 未被停止。

若 canary 失败，只允许在 D2 范围内修正 offline invocation、输入根选择、合法 export type、环境变量或
task-local wrapper，并记录 before/after command/diff/SHA。若同一失败重复、官方 parser 不生成 Chrome
JSON、输出不含 record_function range，或 source/copy 风险出现，立即停止；不得新跑 S1、不得写自定义
binary converter、不得修改发布版 edge semantics。

## 7. D2-3：条件式 8-rank 离线解析与发布版 analyzer

只有 rank-0 canary 全部门通过，才按 rank 0→7 顺序离线解析剩余 7 个工作副本目录。默认每次
`max_process_number=1`，不得为了速度启动无界并发。每 rank 记录：

- input/output exact path、bytes、SHA-256；
- profiler parse exit、stdout/stderr 首个有效 warning/error；
- Chrome trace 顶层 schema、两遍 event count、parse complete、event-limit reached、parse error；
- exact marker count、marker schema、PID/rank mapping；
- output inventory 与磁盘余量。

8 rank 产出后，在保持 retry artifact 目录结构的 `OFFLINE_RESULT_DIR` 上运行发布版 analyzer：

```bash
"${PYTHON_BIN}" tools/inference_contracts/analyze_p6_3c_r3e_f2_dependency_markers.py \
  --artifact-dir "${OFFLINE_RESULT_DIR}" \
  --output-dir "${D2_ROOT}/stage_analysis/s1" \
  --stage S1 \
  --lifecycle-id f2_s1_01
```

不得手工改写 analyzer 输出。若输出与 raw exact-name count 矛盾，保留两者并将 outcome 标为
`offline_analysis_evidence_conflict`；自动 grade 不得覆盖结构化事实。D2 必须分别报告：

- trace coverage 与 parser completeness；
- marker exactly-once rank coverage；
- marker→host、host→runtime、runtime→actual-device-kernel 的 rank-row coverage；
- exact missing edge/link kind；
- derived analysis timeline 排除是否生效；
- source result before/after 是否不变。

## 8. 结果分类与停止规则

终态只能落入以下一类，并保留精确证据：

1. `offline_text_parse_complete_marker_8_of_8`：8 rank 完整解析且 marker 恰好一次；继续报告三段 edge，
   但固定 causal/optimization/performance 为 false；
2. `offline_text_parse_complete_marker_or_edge_incomplete`：Chrome trace 完整，但 marker 或依赖边不完整；
   报告缺失 rank、schema 与 edge，不运行新实验；
3. `offline_parser_output_incompatible_with_published_analyzer`：官方离线解析成功但没有可用 Chrome JSON，
   或 schema 不被发布版 analyzer 支持；返回最小 schema inventory 与建议，不写 converter；
4. `offline_parser_failed_with_exact_tool_boundary`：非 daemon 官方解析失败；返回真实源码 SHA、命令、
   stderr、输出 inventory 与失败阶段；
5. `source_or_copy_integrity_failure`：来源在分析期间变化或安全副本无法建立；立即停止，不解释科学结果。

无论哪一类，都不得执行 NPU、新 S1、S2、budget sweep、性能比较或 optimization task。D2 完成后停止
等待开发机审计；是否开发 converter、调整采集方式或运行任何新 profiler lifecycle 是新的任务决策。

## 9. 自适应记录、资源证明与产物

所有尝试写入 `adaptive_execution_review.json`：base commit、worktree、source/copy path、命令、开始/
结束时间、exit code、首个有效故障、调整原因、task-local patch/diff/SHA、是否改变科学合同、采用或
拒绝原因。不得用后一次覆盖前一次。

本轮资源字段固定并需由事实核对：

```text
npu_used=false
vllm_started=false
new_lifecycle_executed=false
keep_alive_action=left_running
stopped_card_ids=[]
restored_card_ids=[]
```

零 NPU 任务必须保持 low-priority keep-alive 运行。以下命令只作为项目操作规则保留，D2 不得执行：

```bash
# Stop the low-priority keep-alive workload on selected cards only for an authorized NPU task.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart it on exactly the same selected cards after that authorized NPU task.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

`resource_recovery_summary.json` 至少报告 keep-alive marker/card inventory before/after、端口 7000 listener、
vLLM residual process、NPU process inventory 是否未被 D2 改变、shared checkout/installed package/source
result 是否未修改。若发现 D1 遗留资源问题，D2 只报告；不得误杀其他会话或停止 keep-alive。

D2 至少形成：

```text
d2_result_summary.md
source_retry_identity.json
source_retry_inventory.tsv
source_key_file_sha256.tsv
d1_terminal_artifact_review.json
installed_profiler_source_review.json
offline_analysis_attempts.json
offline_trace_inventory.server_local.tsv
trace_marker_inventory.server_local.tsv
marker_propagation_summary.json
step_rank_marker_coverage.tsv
dependency_edge_summary.tsv
cross_domain_link_chains.tsv
bottleneck_hypothesis_review.json
resource_recovery_summary.json
scientific_outcome.json
adaptive_execution_review.json
candidate_manifest.server_local.json
```

raw profiler、Chrome trace、完整日志、copy tree 和大表全部留服。

## 10. 有界结果包与传输选择门

优先候选小包如下；总大小必须小于 70KB，超限时保留完整 server-local 表，只返回摘要与 manifest 中的
路径/SHA：

```text
d2_result_summary.md
source_retry_identity.json
d1_terminal_artifact_review.json
installed_profiler_source_review.json
offline_analysis_attempts.json
offline_trace_inventory.server_local.tsv
trace_marker_inventory.server_local.tsv
marker_propagation_summary.json
step_rank_marker_coverage.tsv
dependency_edge_summary.tsv
cross_domain_link_chains.tsv
resource_recovery_summary.json
scientific_outcome.json
adaptive_execution_review.json
```

所有 adaptive write 结束后，最后生成 `candidate_manifest.server_local.json`。manifest 记录候选文件的
relative path、bytes、SHA-256、sensitivity 与总 bytes；manifest 自身不列入其 entries，但必须单独报告
manifest bytes/SHA，并在用户批准传输时与全部候选文件一并发送。

服务器先在会话中一次报告：result summary 精确路径、完整候选清单、每文件 bytes/SHA/sensitivity、
candidate total bytes、manifest bytes/SHA、可用 `email/upload-api/server-local`，以及一个建议方式和
原因。`result_transfer_authorized=true` 只表示该有界包可被选择，不选择方式、不扩大范围。

当前 `transfer_method_selected=false`。没有用户对这一次完整 scope 的明确选择前，不得 email 或
upload-api，不发送 status-only 邮件，不沿用 D1 的方式。遇到 `401/409/413`、代理/重定向、timeout、
service 或 hash-validation 失败时停止并重新取得选择，不自动换名、重试或切换渠道。

## 11. 服务器报告模板

```text
P6_3C_R3E_F2_D2_SERVER_REPORT_BEGIN
task_id / source_task_id / d1_task_id / attempt_id / task_status:
repo_head / origin_main / ahead_behind / tracked_clean / shared_mutated:
source_attempt_01 / d1_diag_root / retry_result_dir:
retry_identity_complete / lifecycle_count / selected_pressure_step / s2_present:
source_before_after_metadata_sha / source_key_files_unchanged:

npu_used: false
vllm_started: false
new_lifecycle_executed: false
keep_alive_action: left_running
stopped_card_ids: []
restored_card_ids: []
keep_alive_before_after / port_7000_listener / vllm_residual_process:

python_realpath / python_version / torch_version / torch_npu_version:
profiler_source_paths_and_sha:
public_analyse_signature / daemon_guard / valid_export_type / exception_swallowing:
copy_strategy / source_copy_inode_distinct / copy_file_count_bytes / disk_free_before_after:

rank0_offline_command / daemon_false / exit_code / first_warning_or_error:
rank0_trace_view_path_bytes_sha / schema / two_pass_event_count / parse_complete:
rank0_marker_exact_count / canary_gate:
all_rank_offline_parse_executed / parsed_rank_ids:
all_rank_trace_inventory / marker_exactly_once_rank_coverage:

marker_to_host_rank_coverage:
host_to_runtime_rank_coverage:
runtime_to_actual_kernel_rank_coverage:
dependency_linkage_gap / derived_timeline_excluded:
scientific_outcome / claim_boundary:
S1_retry_executed: false
S2_executed: false
causal_bottleneck_resolved: false
optimization_target_selected: false
performance_gain_claimed: false

d2_root / offline_working_result / server_local_raw_and_chrome_paths:
result_summary_path:
candidate_files_with_bytes_sha_sensitivity:
candidate_total_bytes / candidate_manifest_bytes_sha:
available_transfer_methods: email, upload-api, server-local
recommended_transfer_method_and_reason:
transfer_method_selected: false
result_transfer_authorized: true
next_larger_task_authorized: false
P6_3C_R3E_F2_D2_SERVER_REPORT_END
```

最终结论必须把三层事实分开：engine→worker context/marker 传播、raw profiler 是否捕获 marker、离线
Chrome trace 与三段 dependency edge 是否闭合。任何一层缺证据都不得被上一层替代。
