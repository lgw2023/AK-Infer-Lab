# Developer to Server

## 当前唯一服务器动作：P8.2-K2-R0 — 跑通 UCM DRAM-first 外部前缀对象链

```text
task_id: p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728
execution_mode: authorized_pinned_ucm_dependency_and_single_lifecycle_dram_external_prefix_path
server_execution_authorized: true
server_sync_review_authorized: true
dependency_install_authorized: true
dependency_install_scope: isolated_server_local_venv_only
base_conda_environment_mutation_authorized: false
server_side_code_edit_authorized: false
npu_execution_authorized: true
npu_card_ids: [0,1,2,3,4,5,6,7]
formal_model_lifecycle_count_exact: 1
model_request_count_exact: 3
request_retry_count_exact: 0
profiler_authorized: false
parameter_sweep_authorized: false
run02_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
bounded_transfer_max_bytes: 71680
next_task_authorized: false
k3_authorized: false
p8_3_i1_authorized: false
```

本文件已经清空 R17 的旧执行内容，只描述当前 K2-R0。服务器助手不需要设计实验、
补写代码、临场换依赖版本或把结果“调成绿色”；开发机已经把依赖安装、请求生成、
唯一 lifecycle、UCM 路径判定、资源恢复、结果归并和有界清单写进唯一入口。

## 一、先理解本轮目标，避免按错误预设执行

### 1. 项目全局位置

R17 已在服务器以零 NPU 全轨迹重放正式接受：

```text
grade = green_p8_2_k1a_r5_f1_r17_restore_h2d_mechanism_closed
canonical trace events = 1369
D2H workers/completed = 8/8
H2D workers/completed = 8/8
H2D bytes = 1076510720
async copy failures = 0
```

这关闭了 K1A-F1 的 accepted-capacity 机制链：

```text
physical CPU-only target
→ logical CPU hit
→ allocate/update
→ _reqs_to_load
→ load schedule
→ H2D copy
→ restore completion
```

因此本轮不再改 K1A observer，不再追 pairing repair 的“唯一根因”，也不重跑
R15/R16/R17。P8 当前开始 K2 的首个可运行切片：把 KV/Prefix 从 vLLM 内部 cache
路径推进到 UCM 管理的外部前缀对象，并在同一进程生命周期内实际跑通：

```text
prime 生成 KV
→ UCM save
→ UCM Cache(DRAM) 持有外部前缀对象
→ byte-identical follower 做 external lookup/hit
→ UCM Cache load
→ H2D load
→ follower 推理完成
```

### 2. 本轮验收边界

性能收益不是本轮实现通过的前置条件。服务器必须如实记录 prime/follower 的 TTFT、
TPOT、ITL P95 和 E2EL，但当前 Atlas A2 机器上的延迟差值正负不决定上述路径是否已经
实现。不得因为当前机器未加速就把“代码跑通、方法实现、环境测通”判为失败；也不得
反向把一次延迟改善外推为其他硬件上的普遍收益。

同样，pairing repair 是否为唯一或普遍根因不是本轮门槛。R17 的机制证据作为已关闭
parent 保留；K2-R0 要回答的是 UCM 外部对象路径能否在当前 DeepSeek-V4-Flash /
vLLM-Ascend / 910B 环境真实安装、启动、store、hit、load 和完成推理。

## 二、开发机已经写好的实现

服务器只运行，不修改以下文件：

```text
唯一服务器入口：
tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh

单 lifecycle：
tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh

请求、指标归因、finalize、package：
tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py

workload：
benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml

审计合同：
benchmarks/deepseek_v4_flash/p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml

本地合同测试：
tests/inference_contracts/test_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
```

唯一入口自动完成：

```text
Git HEAD/origin/main/tracked-clean gate
→ 精确 UCM source commit 获取/复用
→ server_local 隔离 venv 创建
→ UCM Ascend native extension 安装与 import probe
→ dependency/environment provenance
→ stop keep-alive 0–7
→ task-local vllm_ascend overlay + 既有 MTP positions CPU patch
→ UCM config 与 vLLM 命令生成
→ 单个 TP8+EP+MTP lifecycle 启动
→ warmup / prime / exact follower 顺序请求
→ 每请求前后 UCM/vLLM metrics 快照
→ server cleanup
→ same-card keep-alive restore
→ port/process/worktree recovery check
→ path finalize
→ 9-payload + 1-manifest 有界包
→ copy-ready report
```

服务器助手禁止：

- 修改 Python、Bash、YAML、依赖源码、模型或 base conda 环境；
- 将 UCM 安装进 base conda 环境或系统 Python；
- 自选 UCM tag/branch/commit、PyPI wheel 或其他 connector；
- 打开 vLLM 内部 Prefix Cache；
- 改 context、output、并发、TP/EP、MTP、cache 容量或请求顺序；
- 重试请求、做参数 sweep、加 profiler、启动第二个 lifecycle；
- 删除已存在的 run01、创建 run02 或临场复制结果；
- 重跑 R15/R16/R17；
- 自动进入 K2-R1、K3、P8.3-I1、P8.4、P8.5 或 P9；
- 自动邮件、自动上传或只发一封“待确认”状态邮件。

### 2.1 当前提交中的固定输入 SHA-256

同步到交接指定的 `main` 后，先核对以下输入；任一不匹配都不要停卡或启动模型：

```text
d92bd266a86e1c59a080d1f5f4df8e0b283b89d48200d8c94e005108d41a0b93  benchmarks/deepseek_v4_flash/p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml
469e708e4b623eaed624dd34580e9a63344ccb02c441a0770fb4514c5961ed5b  benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml
b92aa3f8abcdd170a0b2bbdcbf5e81804b81070e1c76ca8595a8d1a9b162a8ee  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
a017dd8d921f88af56cdb098785cf689cea6f6cb27879b4c2f843438133c191f  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh
51627b40981d0551b0f8c7eecb100efff3e351def35ccbf346bc53bb58c9009b  tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh
b0a46e848cc19ba3106ac1e7e026bf1c752afd1d33317a743dc42143a9bee9f3  tests/inference_contracts/test_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
```

## 三、固定依赖与为什么选它

本轮固定官方 UCM 源码：

```text
repository: https://github.com/ModelEngine-Group/unified-cache-management.git
commit: 01cbf9b71892c88319862fa57f195b0bef93fa6f
source provenance branch: develop
source license: MIT
package: uc-manager
PLATFORM: ascend
ENABLE_SPARSE: false
ENABLE_UCM_PATCH: 1
UCM_ENGINE_TYPE: vllm-ascend.a2
```

这个精确提交已包含本轮所需的当前实现面：

- vLLM/vLLM-Ascend 0.22.1 monkey patch；
- Ascend hybrid/compressed cache allocation recovery；
- MTP speculative decoding 与 multi-group load failure recovery；
- Ascend variable block-size 支持；
- 多 rank 共享 cache load failure 传播；
- DeepSeek V4 Flash Prefix Cache 的 vLLM-Ascend 支持登记。

安装位置固定为服务器本地、Git ignored 的隔离目录：

```text
source:
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/third_party/unified-cache-management-01cbf9b

venv:
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/python_envs/ucm-vllm-ascend0221-01cbf9b

build log:
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/ucm_dependency_build_p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728.log
```

隔离 venv 使用 base vLLM-Ascend 环境的 system-site-packages，但只在隔离 venv 内安装
`wrapt==1.17.2` 和 pinned UCM。本轮不得改写：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
```

若服务器不能访问 GitHub、native extension 构建失败、import probe 失败，唯一入口会
保留 build log，在 run01 中形成正式 blocked package，并恢复所有资源。不要换源、换
commit、手改代码或创建 run02；原样回报 dependency status 和 log 的服务器路径。

## 四、固定 UCM 与请求合同

### 4.1 UCM DRAM-first pipeline

```yaml
ucm_connector_name: UcmPipelineStore
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

Posix backend 仅在本轮 result runtime 下；8 GiB DRAM cache 是第一层。本轮期望
32K exact follower 从 Cache 层命中而不从 Posix 回读。`use_gdr=false` 是当前机器的
保守、可运行选择，仍须形成 Cache→HBM 的 H2D load。

### 4.2 vLLM 固定项

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
kv connector module = ucm.integration.vllm.ucm_connector
kv role = kv_both
port = 7000
```

### 4.3 唯一三条请求

```text
1. warmup:
   unrelated 4096-token context + 64 output

2. prime:
   exact 32768-token context + 64 output

3. follower:
   与 prime request body byte-identical
   exact 32768-token reused prefix + 64 output
```

全部串行、concurrency=1、零 retry。请求体 SHA 只留服务器 raw runtime，不进有界包；
生成文本、request IDs、token IDs 也不进有界包。

## 五、实际执行顺序

### 5.1 同步并证明 Git 现场

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git fetch origin main
git checkout main
git merge --ff-only origin/main
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --porcelain --untracked-files=no
```

必须满足：

```text
HEAD = origin/main
ahead/behind = 0 0
tracked-clean = true
```

未跟踪的历史 `server_local/` 结果可以存在；不得删除 parent 或其他任务结果。

### 5.2 零 NPU audit-only

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
AUDIT_DIR=/tmp/p8_2_k2_r0_audit
mkdir -p "${AUDIT_DIR}"
P8_2_K2_R0_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  "${AUDIT_DIR}"
```

audit-only 不安装依赖、不停卡、不启动 vLLM、不发请求。确认输出至少含：

```text
task_id=p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728
ucm_commit=01cbf9b71892c88319862fa57f195b0bef93fa6f
base_conda_environment_mutation=false
formal_model_lifecycle_count_exact=1
model_request_count_exact=3
request_retry_count_exact=0
internal_prefix_cache_enabled=false
performance_benefit_required=false
unique_root_cause_required=false
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
```

### 5.3 唯一正式 run01

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run01
test ! -e "${RESULT_DIR}"
bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  "${RESULT_DIR}"
```

只执行一次。即使返回非零，先确认 keep-alive、端口、vLLM residual 和结果包，再原样
回报；不得自动再跑。

## 六、keep-alive 是常规资源管理，不是异常

本轮使用 NPU 0–7，允许且要求入口在正式 lifecycle 前停止这八卡的低优先级
keep-alive。停止本身不需要特殊解释；关键是每个成功、失败、中断或提前退出路径都
恢复完全相同的 0–7。

唯一入口实际调用：

```bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

服务器报告必须写明：

```text
stopped_card_ids
restored_card_ids
stop_exit_code
restart_exit_code
keep_alive_marker_count / expected=16
keep_alive_restored_exact
port_7000_listener_count
vllm_residual_process_count
tracked_worktree_clean
cleanup_status
```

## 七、如何判读，不要只报一个颜色

### 7.1 完整实现

下列事实全部成立时，正式 grade：

```text
implemented_p8_2_k2_r0_ucm_dram_external_prefix_path
```

所需事实：

```text
3/3 requests HTTP/token/SSE exact and successful
prime save_bytes_delta > 0
prime cache_dump_bytes_delta > 0
follower ucm_hit_tokens_delta > 0
follower gpu_hbm_hit_tokens_delta = 0
follower cache_lookup_hit_blocks_delta > 0
follower cache_load_bytes_delta > 0
follower load_bytes_delta > 0
follower posix_s2h_bytes_delta = 0
UCM error/invalid counter delta total = 0
server log corroborates external hit > 0
cleanup = clean
same-card recovery = exact
```

这表示在当前服务器已实际跑通：

```text
UCM save → DRAM external hit → Cache load → H2D load → inference completion
```

无论 follower 延迟相对 prime 是快、慢还是接近，都不改变上述实现事实；延迟只作为
该硬件/该配置的一次实测描述回报。

### 7.2 部分实现或结构阻断

若已有 external hit 和 H2D load，但不是 DRAM-first，或 recovery/evidence 不完整：

```text
partial_p8_2_k2_r0_ucm_external_hit_non_dram_or_incomplete_recovery
```

若依赖安装或 server startup 前被阻断且没有请求：

```text
blocked_p8_2_k2_r0_dependency_or_startup_preflight
```

其他请求/机制不完整：

```text
incomplete_p8_2_k2_r0_ucm_external_prefix_path
```

这些不是让服务器助手“修颜色”的指令。请同时报告完成到哪一条机制边、首个未成立
事实和原始日志路径；开发机据此决定下一轮。

## 八、原始证据与有界包

以下均留服务器本地，不进入小包：

```text
runtime/vllm_server.log
runtime/raw_metrics/*.prom
runtime/request_results.jsonl
runtime/request body/manifest
runtime/UCM logs
runtime/UCM Posix backend
dependency build log
生成内容、request IDs、token IDs、raw hash
```

有界包固定 9 个 payload：

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
```

加 1 个 manifest：

```text
candidate_manifest.server_local.json
```

总大小必须 `<=71680 bytes`；每个文件都要报 relative path、bytes、完整 SHA-256、
sensitivity。统一 sensitivity：

```text
bounded_operational_metadata_no_content_or_token_ids
```

## 九、服务器最终回报清单

请一次性完整回报，不要只回 grade：

1. `HEAD`、`origin/main`、ahead/behind、tracked-clean；
2. audit-only 完整合同字段；
3. UCM URL、expected/actual commit、source path、tracked-clean；
4. isolated venv path、`uc-manager`/vLLM/vLLM-Ascend/wrapt 版本、
   `base_conda_environment_mutated=false`；
5. dependency install/import probe 状态；失败时 build log 绝对路径和末段有界摘要；
6. formal lifecycle count、request count、success count、retry count；
7. warmup/prime/follower 的 HTTP、token、SSE、TTFT、TPOT、ITL P95、E2EL；
8. prime 的 save/cache dump bytes delta；
9. follower 的 UCM hit tokens、HBM hit tokens、Cache hit blocks、
   Cache load bytes、connector load bytes、Posix S2H bytes；
10. UCM error/invalid counter delta total与外部命中日志 corroboration；
11. `path_class`、`mechanism_implemented`、正式 grade；
12. stopped/restored card sets、16 marker、7000、vLLM residual、tracked-clean、
    cleanup；
13. `result_summary.md` 绝对路径；
14. 完整 9-payload + manifest 清单：每文件 bytes、完整 SHA-256、sensitivity，
    以及 payload/transfer 总字节；
15. `generated_content_retained=false`、`request_ids_retained=false`、
    `token_ids_retained=false`、raw artifacts 的服务器绝对路径；
16. available methods=`email/upload-api/server-local`，推荐 `server-local` 及理由，
    然后暂停等待用户对完整清单选择一种渠道。

入口终端会输出：

```text
K2_R0_SERVER_REPORT_BEGIN
...
K2_R0_SERVER_REPORT_END
```

请保留这两个 marker，并把其中内容与上述清单合并成一次完整回报。

`result_transfer_authorized: true` 只表示完整有界包具备被选择传输的资格，不等于已经
选择渠道。没有用户对这一次完整 inventory 的明确 `email / upload-api /
server-local` 选择前，禁止外发。

## 十、终止条件

完成 run01、资源恢复、结果 package、完整回报后暂停。不得自行开始 K2-R1、K3、
P8.3-I1 或任何额外 lifecycle；下一轮必须由开发机结合本轮真实机制边重新设计。
