# Developer to Server

## 当前唯一服务器动作：P8.2-K2-R0 run02 — 修复 UCM 依赖现场后跑原定 DRAM-first 外部前缀链

```text
task_id: p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728
execution_attempt: run02_explicit_dependency_repair
execution_mode: authorized_run02_dependency_recovery_then_single_lifecycle_dram_external_prefix_path
server_execution_authorized: true
server_sync_review_authorized: true
dependency_repair_authorized: true
dependency_install_authorized: true
dependency_install_scope: isolated_server_local_venv_only
base_conda_environment_mutation_authorized: false
server_side_code_edit_authorized: false
global_git_safe_directory_mutation_authorized: false
invalid_dependency_state_deletion_authorized: false
invalid_dependency_state_quarantine_authorized: true
npu_execution_authorized_after_dependency_ready_only: true
npu_card_ids: [0,1,2,3,4,5,6,7]
formal_model_lifecycle_count_exact: 1
model_request_count_exact: 3
request_retry_count_exact: 0
profiler_authorized: false
parameter_sweep_authorized: false
run01_rerun_authorized: false
run02_authorized: true
run03_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
bounded_transfer_max_bytes: 71680
next_task_authorized: false
k2_r1_authorized: false
k3_authorized: false
p8_3_i1_authorized: false
```

本文件已清空旧 K2-R0 run01 执行说明，只保留当前修复后的 run02。服务器助手不需要
分析设计、补写代码、修改 UCM 源码、改变实验参数或手工修复目录；开发机已把半克隆
源码隔离、毒化 venv 隔离、精确提交重建、导入验证、原子发布、NPU no-touch 失败语义、
单 lifecycle、三请求、资源恢复和有界报告全部写入唯一入口。

## 一、先读结论：run01 没有运行到 UCM 机制，也没有触碰 NPU

run01 的正式结果是：

```text
grade = blocked_p8_2_k2_r0_dependency_or_startup_preflight
path_class = not_executed
formal_model_lifecycle_count = 0
request_count = 0
successful_request_count = 0
npu_stop_attempted = false（由 stopped_card_ids=[] 与完整 keep-alive 现场确认）
stopped_card_ids = []
restored_card_ids = []
keep_alive_marker_count = 16
keep_alive_restored_exact = true
port_7000_listener_count = 0
vllm_residual_process_count = 0
cleanup_status = clean
```

这不是 UCM DRAM store/hit/load 机制失败；该机制在 run01 根本没有开始。唯一已证实的
失败链是：

```text
目标 UCM 源码目录已存在，但 owner=nobody
→ Git 以 dubious ownership 拒绝读取
→ 目录实际只有不完整 .git，工作树未 checkout
→ setup.py / pyproject.toml 不存在
→ pip install 失败
→ ucm import probe 失败
→ 在停 keep-alive、启动 vLLM、发送请求之前结束
```

run01 的旧入口另有两个会放大问题的缺陷，本轮已一并修掉：

1. 旧入口只判断 `.git` 是否存在，没有验证 owner、remote、HEAD、tracked-clean 和必要
   源文件。
2. 旧入口在调用依赖函数时关闭了失败即停，使 checkout/install 的失败可能继续向下。
3. 旧入口在 `pip install` 失败后仍无条件写成功 marker，可能让后续尝试误判为已安装。
4. 旧 build log 只追加不清空，可能把不同尝试混成一个日志。

run01 关键父证据（服务器本地原对象应继续保留，不删除、不覆盖）：

```text
7d51625e1585c51edad64f9b914c08fc6276826451eb86026699c8a720ab1b6a  dependency_and_environment_summary.json
19615a9c3ed3baa78e55369716d9ef3a72a4723cec31b7bfcfaf0b8aa270d449  grading_summary.json
7bae57307f2d4e6860c2e485423951c5651ea38d9a6e0b1b2e0ed2f4f838aa45  resource_recovery_summary.json
345caf05d0d5f275e146027e39beac81f05ab47fb8eb013df0a632749f79ca13  candidate_manifest.server_local.json
dde10605c70b78784fe661e55dfa4fdc1b3de52932815491aa6281698848aa3e  task_grade.txt
```

服务器父目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run01
```

## 二、本轮代码实际做了什么

唯一入口：

```text
tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh
```

它现在严格执行下面的状态机：

```text
验证 repo main / HEAD=origin/main / tracked-clean
→ 强制 RESULT_DIR basename 必须等于 ..._run02
→ 为 run02 新建并截断 attempt-local dependency log
→ 检查既有 UCM source：
     全树 owner 必须等于当前 UID
     origin URL 必须精确匹配
     HEAD 必须等于 pinned commit
     tracked files 必须 clean
     pyproject.toml/setup.py/5 个关键集成源文件必须存在
→ 不合格 source 只移动到同父目录 quarantine，不删除、不信任、不执行其 Git
→ 在 current-user-owned staging 目录 clone/fetch/checkout 精确 commit
→ staging 完整验证后在同一父目录原子 rename 到正式 source
→ 检查既有隔离 venv：
     全树 owner 必须等于当前 UID
     marker 必须精确等于 pinned commit
     ucm/vllm/vllm_ascend/wrapt/两种 connector 必须完整 import
→ 不合格 venv 只移动到同父目录 quarantine，不删除
→ 在 staging venv 安装 wrapt==1.17.2 和 pinned UCM
→ 先完成完整 import probe，再原子写 marker
→ staging venv 完整验证后原子 rename 到正式 venv
→ 正式路径再次 import probe
→ 只有全部依赖 ready 才停 0–7 keep-alive 并启动一个 TP8 lifecycle
→ warmup / prime / follower 三请求
→ cleanup、同卡恢复、finalize、package、完整回报
```

入口明确不会执行：

```text
git config --global --add safe.directory ...
chown/chmod 修补不可信目录
rm -rf 删除旧源码或旧 venv
修改 base conda 环境
修改 UCM 源码
复用未通过 import probe 的 marker
依赖失败后停卡或启动模型
```

不得执行 `git config --global --add safe.directory`。这既会扩大 Git 信任范围，又不能
证明 `nobody` 所有的半克隆目录可写、完整或属于本次任务。脚本会把该目录移动到
`quarantine` 后，以当前执行用户重新构造可信对象。

## 三、唯一执行步骤

### 3.1 同步并只检查，不要先运行

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git fetch origin
git switch main
git pull --ff-only origin main

git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --porcelain --untracked-files=no
```

必须满足：

```text
branch = main
HEAD = origin/main
ahead/behind = 0 0
tracked-clean = true
```

`server_local/` 的 run01、UCM 目录、venv、quarantine 和日志是 Git ignored 运行产物；
它们可以存在。禁止为了 tracked-clean 删除它们。

### 3.2 核对 run01 父证据仍在

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
PARENT=server_local/p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run01
test -d "${PARENT}"
sha256sum \
  "${PARENT}/dependency_and_environment_summary.json" \
  "${PARENT}/grading_summary.json" \
  "${PARENT}/resource_recovery_summary.json" \
  "${PARENT}/candidate_manifest.server_local.json" \
  "${PARENT}/task_grade.txt"
```

若父证据缺失或 SHA 不匹配：不要运行 run02，不要补造父证据，原样回报。

### 3.3 核对当前代码输入

同步后对以下文件计算 SHA-256，并与本交接第十节的最终 inventory 比较：

```bash
sha256sum \
  benchmarks/deepseek_v4_flash/p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml \
  benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml \
  benchmarks/deepseek_v4_flash/p5_readiness_card.yaml \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  tests/inference_contracts/test_deepseek_p8_2_k2_r0_ucm_dram_prefix.py \
  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
```

任一不匹配：不要停卡、不要启动模型、不要现场改代码。

### 3.4 先跑本地合同验证与 audit-only

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python -m pytest -q \
  tests/inference_contracts/test_deepseek_p8_2_k2_r0_ucm_dram_prefix.py

.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python -m py_compile \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py

bash -n tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh

P8_2_K2_R0_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  /tmp/p8_2_k2_r0_audit_only
```

audit-only 必须明确出现：

```text
dependency_repair_attempt=run02_explicit
expected_result_basename=p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run02
global_git_safe_directory_mutation=false
invalid_dependency_state_action=quarantine_then_atomic_rebuild
dependency_log_attempt_local_and_truncated=true
install_marker_written_after_import_probe_only=true
preflight_failure_npu_touch=false
formal_model_lifecycle_count_exact=1
model_request_count_exact=3
request_retry_count_exact=0
```

### 3.5 唯一正式命令

先确认 run02 不存在：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RESULT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run02
test ! -e "${RESULT}"
```

然后仅执行一次：

```bash
bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh "${RESULT}"
```

不要手工预先 clone、chown、pip install、写 marker、停卡、创建结果目录或重定向另一个
build log；这些动作都由入口管理。

## 四、依赖修复的判读方法

正式报告中的 `dependency_and_environment_summary.json` 必须优先检查：

```text
dependency_attempt = run02_explicit_repair
dependency_log_truncated_before_attempt = true
global_git_safe_directory_mutated = false
expected_current_user_uid = 当前执行 UID
ucm_source_tree_owned_by_current_user = true
ucm_source_remote_url = https://github.com/ModelEngine-Group/unified-cache-management.git
ucm_source_head = 01cbf9b71892c88319862fa57f195b0bef93fa6f
ucm_source_tracked_clean = true
ucm_source_validation_complete = true
所有 ucm_source_required_files = true
ucm_install_marker_value = 01cbf9b71892c88319862fa57f195b0bef93fa6f
ucm_install_marker_valid = true
python_import_probe 含 uc-manager/vllm/vllm-ascend/wrapt/UCMConnector/UCMConnectorV1
```

`provision_events` 的合法路径包括：

```text
run01 毒化现场仍在：
  quarantined source
  quarantined venv（如旧 venv marker/import 无效）
  staging_created source
  promoted source
  staging_created venv
  promoted venv

或目标在同步前已被可信地修复：
  reused source
  reused venv
```

若 clone、checkout、build 或 import 再失败：

- 脚本会把失败 staging 移入 quarantine；
- run02 仍生成正式 blocked 包；
- keep-alive 保持运行，不调用 stop；
- 不创建 lifecycle，不发送请求；
- `resource_state` 应为 `dependency_preflight_failed_before_npu_touch`；
- 原样回报 attempt-local build log 绝对路径、bytes、依赖摘要和 quarantine paths；
- 不得换 UCM commit、换 PyPI 包、改源码、手工写 marker 或创建 run03。

## 五、依赖通过后保持不变的机制目标

固定 UCM：

```text
repository = https://github.com/ModelEngine-Group/unified-cache-management.git
commit = 01cbf9b71892c88319862fa57f195b0bef93fa6f
package = uc-manager
PLATFORM = ascend
ENABLE_SPARSE = false
ENABLE_UCM_PATCH = 1
UCM_ENGINE_TYPE = vllm-ascend.a2
wrapt = 1.17.2
```

固定隔离位置：

```text
source:
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/third_party/unified-cache-management-01cbf9b

venv:
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/python_envs/ucm-vllm-ascend0221-01cbf9b

run02 build log:
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/ucm_dependency_build_p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run02.log
```

base conda 只作为 system-site-packages 来源，禁止修改：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
```

固定机制链：

```text
prime 生成 KV
→ UCM save/cache dump
→ Cache(DRAM) 持有外部前缀对象
→ byte-identical follower external lookup/hit
→ Cache load
→ H2D load
→ follower 推理完成
```

性能收益不是本轮实现通过的前置条件。TTFT、TPOT、ITL P95、E2EL 仍须如实记录，
但本机延迟差值的正负不决定上述路径是否实现，也不得外推到其他硬件。

固定 UCM store：

```yaml
store_pipeline: Cache|Posix
cache_buffer_capacity_gb: 8
posix_capacity_gb: 32
io_direct: false
posix_io_engine: psync
use_gdr: false
enable_event_sync: true
enable_metrics: true
use_layerwise: true
enable_record_traces: false
use_lite: false
persist_token_threshold: 0
load_tokens_threshold: 2048
```

固定 vLLM：

```text
model = /data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
served model = deepseek-v4-flash-w8a8-mtp
TP = 8
EP = enabled
DP = 1
MTP speculative tokens = 1
max model len = 135168
max num batched tokens = 4096
max num seqs = 1
block size = 128
chunked prefill = enabled
internal prefix cache = disabled
kv connector = UCMConnector
kv role = kv_both
port = 7000
```

唯一三请求：

```text
1. warmup：unrelated 4096 context + 64 output
2. prime：32768 context + 64 output
3. follower：与 prime 请求体 byte-identical，32768 exact reuse + 64 output
```

## 六、keep-alive 操作规则

依赖预检阶段不需要 NPU，必须保持 keep-alive 运行。只有入口确认 source、venv、
marker 和 import 全部 ready 后，才会自动执行：

```bash
# Stop the low-priority keep-alive workload on exactly cards 0–7.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
```

任务成功、失败、中断或提前退出后，入口必须自动恢复同一集合：

```bash
# Restart the low-priority keep-alive workload on exactly cards 0–7.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

服务器报告必须区分两种合法状态：

```text
依赖预检失败：
  npu_stop_attempted=false
  formal_model_lifecycle_started=false
  stopped_card_ids=[]
  restored_card_ids=[]
  keep_alive_restored_exact=true
  resource_state=dependency_preflight_failed_before_npu_touch

依赖通过且 lifecycle 已运行：
  npu_stop_attempted=true
  formal_model_lifecycle_started=true
  stopped_card_ids=[0,1,2,3,4,5,6,7]
  restored_card_ids=[0,1,2,3,4,5,6,7]
  keep_alive_restored_exact=true
  resource_state=npu_lifecycle_cleanup_and_same_card_restore_exact
```

停 keep-alive 本身不是严重事项；需要用卡时正常停即可，关键是只停任务所需卡，并在
所有退出路径恢复完全相同的卡集。

## 七、机制验收字段

依赖与 lifecycle 成功后，检查：

```text
formal_model_lifecycle_count = 1
request_count = 3
successful_request_count = 3
request_retry_count = 0

prime_save_bytes_delta > 0
prime_cache_dump_bytes_delta > 0

follower_ucm_hit_tokens_delta > 0
follower_gpu_hbm_hit_tokens_delta = 0
follower_cache_lookup_hit_blocks_delta > 0
follower_cache_load_bytes_delta > 0
follower_load_bytes_delta > 0
follower_posix_s2h_bytes_delta = 0

error_counter_delta_total = 0
positive_external_lookup_line_count > 0
port_7000_listener_count = 0
vllm_residual_process_count = 0
tracked_worktree_clean = true
cleanup_status = clean
```

完整满足时：

```text
grade = implemented_p8_2_k2_r0_ucm_dram_external_prefix_path
path_class = ucm_cache_store_dram_hit_then_h2d_load
mechanism_implemented = true
```

不满足时按实际字段报告，不得人为改成 implemented。无论 grade 如何：

```text
performance_benefit_claimed = false
unique_root_cause_claimed = false
next_task_authorized = false
k2_r1_authorized = false
k3_authorized = false
p8_3_i1_authorized = false
```

## 八、服务器助手禁止事项

- 不修改任何仓库文件、UCM 源码、模型、base conda 环境或系统 Python；
- 不设置 global/system/local `safe.directory`；
- 不 chown/chmod、删除或覆盖 run01、旧 source、旧 venv、quarantine；
- 不换 UCM branch/tag/commit，不改安装选项；
- 不打开 vLLM internal Prefix Cache；
- 不改 context/output/concurrency/TP/EP/MTP/cache 容量/请求顺序；
- 不手工重试请求，不做 sweep，不加 profiler，不启动第二个 lifecycle；
- 不重跑 run01，不创建 run03；
- 不进入 K2-R1、K3、P8.3-I1 或其他下一阶段；
- 不自动发邮件、上传，或先发一封“待确认”状态邮件。

## 九、完整回报要求

正式命令结束后一次性回报：

1. HEAD、origin/main、ahead/behind、tracked-clean；
2. run01 五个父文件的现场 SHA-256 与 parent grade；
3. 当前八个固定输入文件的 SHA-256；
4. pytest、py_compile、两个 `bash -n`、audit-only 结果；
5. dependency status、attempt-local log 路径/bytes；
6. current UID、source root owner、全树 owner 判定、remote、HEAD、clean、必要文件；
7. provision events，尤其 quarantine/staging/promoted/reused 的完整有界清单；
8. venv owner、marker、import probe 与 base conda 未修改证明；
9. 是否在依赖 ready 前触碰 NPU；
10. lifecycle/request/retry 数及三请求 HTTP/token/SSE/延迟；
11. prime store/dump 与 follower hit/load/Posix/HBM/error/log 指标；
12. path_class、mechanism_implemented、grade 与 claim boundary；
13. cleanup、7000、vLLM residual、停卡/恢复卡集、keep-alive marker；
14. `result_summary.md` 绝对路径；
15. 完整候选文件逐项 bytes、完整 SHA-256、sensitivity；
16. payload/manifest/transfer 总数和总 bytes，逐文件复验结论；
17. raw build log、vLLM log、metrics、请求体、请求 ID、token ID、生成内容的服务器路径，
    不把它们放进有界包；
18. 明确 `next_task_authorized=false`，完成后暂停。

如果依赖失败，报告最后一段最多 12KB 的有界 build log 摘要即可；不要把完整 log 放进
有界包或邮件。

## 十、当前提交固定输入 SHA-256

```text
7ea5ab6e4a518cd4ea0b9bf22a2d8e0a2a1939662cf1608f8799cb055ff0d8ca  benchmarks/deepseek_v4_flash/p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml
bcc57ddb453898066c240ab395f24c39b88d5caf321b326ca606d9027bca6a32  benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml
43ecad24e7f98a1a2be3243635edd38b7592a17e9e45cf004dd19c9f6ace26f1  benchmarks/deepseek_v4_flash/p5_readiness_card.yaml
7b309560c815b08877a4fc86aac7c54d095b506f87ee1f9cc81a9bad99ae669b  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
a017dd8d921f88af56cdb098785cf689cea6f6cb27879b4c2f843438133c191f  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh
edf3f3c8ec256e1ec4b19b4a217b15d77ffd836aa17c425f6dba84d0d86fd861  tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh
de50f34011b67f26bfc729f35ecc9661dab8deed6babd88effeec671454168d1  tests/inference_contracts/test_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
```

## 十一、有界结果与传输纪律

大产物全部留服务器。候选包只能包含：

```text
cleanup_status.txt
dependency_and_environment_summary.json
grading_summary.json
request_summary.tsv
resource_recovery_summary.json
result_summary.md
task_grade.txt
ucm_metric_deltas.tsv
ucm_path_summary.json
candidate_manifest.server_local.json
```

每个文件必须：

```text
sensitivity = bounded_operational_metadata_no_content_or_token_ids
```

完整包不超过 71680 bytes。先报告完整 inventory、总大小、SHA-256、敏感级别和以下三种
方法：

```text
email
upload-api
server-local
```

推荐 `server-local`，因为包已在服务器且当前需要先审查完整内容。即使
`result_transfer_authorized=true`，也不等于已经选择传输方式。必须等用户对完整范围
明确选择一种方式；不得自动发送、自动上传或在失败后自动切换方法。

正式任务完成后暂停，等待用户选择传输方式或下发下一任务。
