# 开发机 → Ascend 服务器：当前唯一任务

## 当前唯一服务器动作：K2-R0 run04 FAWA POSIX GC 几何修复并进入三请求外部 KV 路径

```yaml
task_id: p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729
run_id: p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729_run01
stage: P8.2-K2-R0
execution_mode: authorized_single_lifecycle_fawa_split_aware_posix_gc_geometry_repair_and_external_prefix_path
npu_execution_authorized: true
npu_card_ids: [0, 1, 2, 3, 4, 5, 6, 7]
formal_model_lifecycle_count_exact: 1
model_request_count_exact: 3
request_retry_count_exact: 0
parameter_sweep_authorized: false
server_side_code_edit_authorized: false
base_conda_environment_mutation: false
internal_prefix_cache_enabled: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
next_task_authorized: false
k2_r1_authorized: false
k3_authorized: false
p8_3_i1_authorized: false
p6_3c_r1_authorized_in_this_task: false
```

这是当前唯一可执行的服务器任务。开发机已经写完配置、FA/WA 几何计算、父包校验、
依赖复用、停卡前资源门、单 lifecycle、三请求、结果归因、清理恢复和有界打包代码。
服务器助手不需要理解后再补代码，也不要把下面的步骤拆成自选命令组合。

服务器助手只做：

1. fast-forward 同步远程 `main`；
2. 重新读取本文件；
3. 验证 tracked-clean、固定输入 SHA 和 audit-only 输出；
4. 运行一次唯一 server-task driver；
5. 无论成功、失败或中断，确认 0–7 keep-alive 已恢复；
6. 原样回报 `K2_R0_SERVER_REPORT_BEGIN/END` 全段；
7. 报告完整有界包清单，然后暂停等待用户选择传输渠道。

禁止：

- 不编辑仓库、pinned UCM source、site-packages、模型或配置；
- 不手工把 64 GiB 改成 366/380/760 GiB；
- 不改 `data_dir_shard_bytes=2`；
- 不删除或覆盖 run01/run02/run03/attribution 父证据；
- 不创建本任务的 run02；
- 不 retry，不 sweep，不再启动第二个模型 lifecycle；
- 不混跑 P6.3C-R1、K2-R1、K3、P8.3-I1、P8.4、P8.5 或 P9；
- 不因 latency 正负自行改 grade 或停止机制字段收集；
- 不自动 email/upload 结果。

## 1. 全局背景：本轮真正要推进的系统机制

项目主对象是 DeepSeek-V4-Flash W8A8-MTP / vLLM-Ascend 0.22.1rc1。KV 分层路线：

```text
K0  internal Prefix Cache baseline
K1A built-in warm tier: GPU → CPU store → logical hit → H2D restore
K2  UCM external KV: prime save → external lookup/hit → load/H2D → follower
```

K1A-F1 已由 R17 完成机制闭环：

```text
physical CPU-only
→ logical hit
→ restore admission
→ D2H/H2D 8-worker completion
```

K2-R0 的目的不是再证明 K1A，也不是只得到一个“启动成功”颜色。本轮要让独立 UCM
外部对象路径真正进入固定三请求：

```text
warmup
→ prime 保存 exact 32K 前缀到 UCM
→ follower 查询相同 32K 前缀
→ external hit
→ Cache load / H2D
→ follower 正常完成
```

性能字段 TTFT/TPOT/ITL P95/E2EL 必须如实记录；当前硬件上的延迟差值正负不作为
“代码和方法是否实现”的先决条件，也不授权省略性能数据。

## 2. 已关闭的门：不要重复调查

### 2.1 run01

run01 因 NFS root-squash 形成 `nobody` 所有的半克隆目录，pinned UCM 未安装，正式
lifecycle/request=`0/0`。该问题已经关闭。

### 2.2 运维侧 NFS 修复

用户已经在四个节点的 NFS export 对所有对端规则加入 `no_root_squash` 并 reload。
跨节点新建文件已验证：

```text
owner=root:shareddata
uid:gid=0:3000
```

当前 driver 仍会在 NPU 前复验新对象身份，但服务器助手不得重新编辑 export 配置。

### 2.3 run02

run02 完成：

- pinned UCM=`0.6.0`；
- vLLM=`0.22.1+empty`；
- vLLM-Ascend=`0.22.1rc1`；
- wrapt=`1.17.2`；
- `UCMConnector` / `UCMConnectorV1` import；
- 隔离 venv 与 CMake Python 3.11 绑定；
- 正式 lifecycle=`1`。

run02 在 worker CacheStore 命中：

```text
too small buffer(8589934592) on shard(6627328)
```

8 GiB 只有 1296 个 buffer，低于 pinned source 要求 2048。run03 已使用 16 GiB，
WA=`2592`、FA=`5391`，该 CacheStore 门已经关闭。

### 2.4 run03

run03 已通过：

- dependency/source/env；
- NFS live `0:3000`；
- CMake Python 3.11；
- CacheStore 16 GiB；
- `/dev/shm` 与 MemAvailable；
- 一个 TP8+EP+MTP lifecycle 的正式启动尝试。

但服务未 ready，三请求均未发送。原 run03 有界包只有外层
`ucm_connector.py:2669 -> UCMFAWAConnector`，所以开发机追加了一轮零 NPU raw-log
归因。

### 2.5 run03 attribution

固定服务器父目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729_run01
```

固定 parent：

```yaml
grade: attributed_p8_2_k2_r0_run03_fawa_startup_failure
manifest_bytes: 3104
manifest_sha256: 7bb522ad5353d8d0b3ab3b9339a4e0bf92ce3f5a75f77a143c0d52ca664e1d71
payload_file_count: 9
payload_total_bytes: 48079
transfer_file_count: 10
transfer_total_bytes: 51183
npu_started: false
vllm_started: false
model_requests_sent: 0
keep_alive_action: left_running
```

精确首错：

```text
RuntimeError: -50000, posix_capacity_gb(16) is too small,
GC cannot recycle any files. Minimum recommended: 183GB
```

精确构造路径：

```text
UCMFAWAConnector
→ scheduler _create_fa_store
→ _create_store
→ UcmConnectorFactoryV1
→ UcmPipelineStore
→ Cache|Posix pipeline builder
→ ShardGarbageCollector::ValidateAndInitCapacity
```

run03 runtime 还给出：

```yaml
FA:
  worker_block_size_bytes: 3186688
  worker_shard_size_bytes: 3186688
  cache_buffer_capacity_gb: 16
  cache_buffer_number: 5391
WA:
  worker_block_size_bytes: 6627328
  worker_shard_size_bytes: 6627328
  cache_buffer_capacity_gb: 16
  cache_buffer_number: 2592
```

这说明当前唯一启动阻塞在 scheduler FA PosixStore GC 构造。FA/WA worker CacheStore
geometry 均已通过。

## 3. 错误语义：不要再把它解释成旧文件或 namespace 问题

固定 UCM commit：

```text
01cbf9b71892c88319862fa57f195b0bef93fa6f
```

`ucm/integration/vllm/hma_connector.py` 的固定语义：

1. FA 与 WA 分别 deepcopy 同一 connector config；
2. storage backend 已分别追加 `fawa_fa` / `fawa_wa`；
3. scheduler DP0 才启用 `posix_gc_enable`；
4. `posix_capacity_gb` 在 FA/WA config 中各自做整数除 2；
5. scheduler 先创建 FA，再创建 WA；
6. worker 用真实 tensor list 设置各自 block/shard size。

因此旧 YAML：

```yaml
posix_capacity_gb: 32
```

实际进入 FA/WA scheduler store 的是：

```text
FA=16 GiB
WA=16 GiB
```

`ucm/store/posix/cc/shard_gc.cc` 的整数顺序：

```text
max_file_count = capacity_bytes // block_size
files_per_directory_shard = max_file_count // directory_shard_count
threshold_files = int(files_per_directory_shard * 0.7)
recycle_files = int(threshold_files * 0.1)
```

默认 `data_dir_shard_bytes=3`：

```text
directory_shard_count = 16^3 = 4096
```

旧 FA 16 GiB 计算后 `recycle_files=0`，所以构造器拒绝启动。“GC cannot recycle any
files” 是配置整数几何得到 0，并不表示现场已经存在删不掉的旧文件。

run03 日志已经证明 backend 路径分别为 `fawa_fa` 与 `fawa_wa`。本轮不是再次修
namespace。

## 4. run04 的定向修复

唯一 lifecycle 会写入：

```yaml
ucm_connectors:
  - ucm_connector_name: UcmPipelineStore
    ucm_connector_config:
      store_pipeline: Cache|Posix
      cache_buffer_capacity_gb: 16
      posix_capacity_gb: 64
      data_dir_shard_bytes: 2
      posix_gc_trigger_threshold_ratio: 0.7
      posix_gc_recycle_percent: 0.1
      io_direct: false
      posix_io_engine: psync
      use_gdr: false
```

经 pinned FAWA 分流：

```text
total configured POSIX = 64 GiB
FA after split = 32 GiB
WA after split = 32 GiB
directory shards = 16^2 = 256
```

用 run03 实测 block size 和 pinned C++ 整数顺序：

```yaml
FA:
  block_size_bytes: 3186688
  max_file_count: 10782
  files_per_directory_shard: 42
  threshold_files_per_directory_shard: 29
  recycle_files_per_directory_shard: 2
  minimum_capacity_gib_ceil: 12
  configured_capacity_gib: 32
  gate: pass
WA:
  block_size_bytes: 6627328
  max_file_count: 5184
  files_per_directory_shard: 20
  threshold_files_per_directory_shard: 14
  recycle_files_per_directory_shard: 1
  minimum_capacity_gib_ceil: 24
  configured_capacity_gib: 32
  gate: pass
```

为什么不是简单把旧总容量改为 366 GiB：

- 默认 4096 shards 下 FA 最低 183 GiB；
- 同一默认下 WA 最低约 380 GiB；
- FA/WA 又从总配置对半；
- 仅让 FA 通过仍会在 WA 失败；
- 保留默认分片将要求总配置约 760 GiB，并制造不必要的存储承诺。

run04 改的是目录分片与配置容量的共同几何，仍为当前单机验证保留足够余量。

## 5. 停卡前自动门：服务器助手不要手算

唯一 driver 在任何 NPU 触碰前自动验证：

1. 当前 repo 在 `main`；
2. `HEAD=origin/main`；
3. tracked-clean（允许既有 server-local 未跟踪结果）；
4. run03 attribution manifest bytes/SHA；
5. attribution manifest 中 9 个 payload 逐文件 bytes/SHA；
6. attribution grade；
7. attribution `fawa_store_geometry.json` 的 worker FA block size 唯一等于
   `3186688`；
8. worker WA block size 唯一等于 `6627328`；
9. pinned UCM source HEAD exact、tracked-clean、关键源码存在；
10. 隔离 UCM venv marker/import exact；
11. NFS 新对象 `uid:gid=0:3000`；
12. FA/WA CacheStore 16 GiB 的 buffer 数均不少于 2048；
13. FA/WA POSIX GC 的 `recycle_files_per_directory_shard` 均大于 0；
14. `/dev/shm` 可覆盖保守的
    `16 GiB × 2 stores × TP8 + 16 GiB headroom = 272 GiB`；
15. MemAvailable 可覆盖同一保守上限；
16. task-local storage filesystem free space 至少覆盖
    `64 GiB + 16 GiB headroom = 80 GiB`。

任一门失败：

- 不停止 keep-alive；
- 不启动 lifecycle；
- 不发送请求；
- 仍生成 dependency/capacity/recovery/final package；
- 回报精确失败字段；
- 暂停，不手工绕过。

## 6. 固定运行时与请求合同

```yaml
model: /data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
served_model_name: deepseek-v4-flash-w8a8-mtp
vllm: 0.22.1+empty
vllm_ascend: 0.22.1rc1
tensor_parallel_size: 8
expert_parallel: true
mtp_speculative_tokens: 1
max_model_len: 135168
max_num_batched_tokens: 4096
max_num_seqs: 1
block_size: 128
chunked_prefill: true
internal_prefix_cache: false
ucm_connector: UCMConnector
ucm_role: kv_both
ucm_pipeline: Cache|Posix
use_layerwise: true
event_sync: true
metrics: true
record_raw_hash_traces: false
use_gdr: false
port: 7000
```

唯一请求序列：

```yaml
formal_model_lifecycle_count: 1
request_count: 3
request_retry_count: 0
concurrency: 1
output_tokens_each: 64
order:
  - warmup_unrelated_4096
  - prime_exact_32768
  - follower_byte_identical_32768
prime_follower_body_byte_identical: true
```

不要另发 health 之外的手工模型请求，不要在失败后“再试一次”。

## 7. 固定服务器路径

仓库：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab
```

base vLLM-Ascend 环境：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
```

pinned UCM source：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/third_party/unified-cache-management-01cbf9b
```

隔离 UCM venv：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/python_envs/ucm-vllm-ascend0221-01cbf9b
```

唯一结果目录：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729_run01
```

如果该结果目录已经存在：

- 不删除；
- 不覆盖；
- 不改名后继续；
- 回报该精确路径并停止，等待用户决定。

大产物保留在结果目录的 `runtime/`。有界包写在结果目录根。

## 8. 同步远程 main

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

git status --short --branch
git fetch origin main
git pull --ff-only origin main

git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --porcelain --untracked-files=no
```

必须满足：

```text
branch=main
HEAD=origin/main
ahead/behind=0 0
tracked-clean=true
```

如果 tracked 文件有改动或无法 fast-forward，停止并原样回报；不要 stash、reset、
checkout、commit、merge 或手工解决冲突。server-local 未跟踪结果不构成 tracked-dirty。

## 9. 固定输入 SHA-256

在仓库根执行：

```bash
sha256sum \
  benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml \
  benchmarks/deepseek_v4_flash/p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml \
  tools/inference_contracts/p8_2_k2_r0_fawa_posix_gc_geometry.py \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  tools/inference_contracts/run_ucm_cmake_python_wrapper.sh \
  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
```

必须逐项等于：

```text
336187156292937f45039ac998c38ceb8658723cd393579070fdd0af02bbe775  benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml
d6fce7953c992745c911a174cc132c1f8058aa203aab79676983dcdbbc2dc84c  benchmarks/deepseek_v4_flash/p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml
4b61948eab766e9a7863200a1e1cf652c355d7d4cd55da1376247951af96f691  tools/inference_contracts/p8_2_k2_r0_fawa_posix_gc_geometry.py
e5523788322730663bc6913d87efbc09c10b0fb736c02a6ab3b83938bea62f48  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
cebc40c217a2ddb0aeeb2822138b16585dd256d2e3d5f768512463a0ba0d81e9  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh
58fb6fd36a9776cab79ccce1dda0240f2faa2f478a25e8e97087aa9a483e435d  tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh
eb42b473cc8b729e515cd4bc8732d65c69c1315bf9cb879be1cd9c4385b4c2af  tools/inference_contracts/run_ucm_cmake_python_wrapper.sh
75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch
```

任一不匹配立即停止，不要执行旧入口或现场修文件。

## 10. audit-only：零 NPU

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

P8_2_K2_R0_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  /audit/p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729_run01
```

重点检查输出：

```text
task_id=p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729
expected_result_basename=p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729_run01
parent_attribution_manifest_bytes=3104
parent_attribution_manifest_sha256=7bb522ad...
parent_run03_fa_block_size_bytes=3186688
parent_run03_wa_block_size_bytes=6627328
ucm_cache_buffer_capacity_gib_per_fawa_store=16
ucm_configured_fa_buffer_number=5391
ucm_configured_wa_buffer_number=2592
ucm_posix_total_capacity_gib_before_fawa_split=64
ucm_posix_capacity_gib_per_store_after_fawa_split=32
ucm_posix_data_dir_shard_bytes=2
ucm_posix_directory_shard_count=256
ucm_posix_fa_minimum_capacity_gib=12
ucm_posix_wa_minimum_capacity_gib=24
ucm_posix_fa_recycle_files_per_shard=2
ucm_posix_wa_recycle_files_per_shard=1
formal_model_lifecycle_count_exact=1
model_request_count_exact=3
request_retry_count_exact=0
keep_alive_stop_then_same_set_restore=true
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
```

audit-only 不会停止卡、启动 vLLM 或发送请求。

## 11. keep-alive 规则

本任务需要 NPU 0–7。允许正常停止这八卡的低优先级 keep-alive；这不是异常。唯一
driver 已把停止与所有退出路径上的同卡恢复写好。不要在 driver 外另写一套 stop/restore。

规则：

```text
preflight 全过后才 stop 0–7
success/failure/interruption/early-exit 都 restore 0–7
stopped set 必须等于 restored set
最终必须有 cards 0–7 的 16 个 keep-alive markers
```

仓库要求每份交接明确给出常规命令：

```bash
# 本任务实际需要时，driver 会在内部执行：
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 任一退出路径，driver 会在内部恢复同一集合：
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

如果 driver 因外部强制终止而未能打印报告，服务器操作者应先只执行恢复命令，再检查
7000/vLLM residual，然后回报中断，不得继续第二次实验。

## 12. 唯一正式执行命令

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729_run01
```

只执行一次。不要加 `tee` 截断 driver 状态，不要后台另起第二个入口，不要手工发模型
请求，不要在 server ready 等待期间启动其他实验。

driver 自动完成：

```text
parent attribution manifest/all-payload verify
→ NFS/source/venv/import verify or safe isolated rebuild
→ exact FA/WA Cache + POSIX GC geometry preflight
→ host DRAM + /dev/shm + storage free-space preflight
→ stop keep-alive 0–7
→ task-local vLLM-Ascend overlay
→ write fixed UCM config
→ start one TP8+EP+MTP lifecycle
→ wait health
→ warmup 4K
→ prime exact 32K
→ follower byte-identical 32K
→ collect UCM path metrics and descriptive latency
→ stop vLLM
→ restore keep-alive 0–7
→ verify port/process/markers/tracked-clean
→ finalize and build bounded manifest
→ print complete report markers
```

## 13. 结果判读：优先看机制，不要只复述 grade

### 13.1 启动门

先看：

```text
dependency_status
startup_capacity_status
parent_worker_geometry_exact
fawa_posix_gc.all_store_gc_recycle_gates_passed
fawa_posix_gc.filesystem_gate_passed
startup_class
server_ready
```

若旧异常再次出现，必须回报：

```text
ucm_fawa_posix_gc_too_small_observed
reported_posix_capacity_gib_after_fawa_split
reported_posix_minimum_recommended_gib
raw_startup_log_server_path
```

不要自行改参数重跑。

### 13.2 请求与机制主链

若 server ready，逐请求看：

```text
request_count=3
successful_request_count
warmup status/http/tokens/SSE
prime status/http/tokens/SSE
follower status/http/tokens/SSE
```

核心指标：

```text
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
```

目标 path：

```text
ucm_cache_store_dram_hit_then_h2d_load
```

目标机制 grade：

```text
implemented_p8_2_k2_r0_ucm_dram_external_prefix_path
```

如果请求或指标不完整，完整保留实际值。不要为了得到目标 grade 改判据。

### 13.3 性能字段

必须报告 prime/follower：

```text
TTFT
TPOT
ITL P95
E2EL
```

这些值是当前硬件和当前配置的实测。无论快慢都要如实报告，不要用延迟符号替代机制
字段，也不要把当前一次机器结果外推为所有硬件结论。

## 14. cleanup 与资源恢复验收

必须同时满足：

```text
cleanup_status=clean
stopped_card_ids=[0,1,2,3,4,5,6,7]  # 若进入 lifecycle
restored_card_ids=[0,1,2,3,4,5,6,7]
keep_alive_marker_count=16
keep_alive_restored_exact=true
port_7000_listener_count=0
vllm_residual_process_count=0
tracked_worktree_clean=true
```

若在停卡前 preflight 退出，则应为：

```text
stopped_card_ids=[]
restored_card_ids=[]
npu_stop_attempted=false
formal_model_lifecycle_started=false
preflight_failed_before_npu_touch=true
keep_alive_restored_exact=true
```

## 15. 完整回报清单

不要只给一句总结。必须原样粘贴 driver 输出的：

```text
K2_R0_SERVER_REPORT_BEGIN
...
K2_R0_SERVER_REPORT_END
```

并在自然语言回报中明确列出：

1. HEAD；
2. origin/main；
3. ahead/behind；
4. tracked-clean；
5. audit-only 是否全部匹配；
6. attribution parent manifest bytes/SHA 与 all-payload 校验；
7. pinned UCM HEAD、source/env/import 状态；
8. NFS live uid/gid；
9. FA/WA parent block size；
10. FA/WA Cache buffer number/required number；
11. 总 POSIX、分流后各 store 容量；
12. `data_dir_shard_bytes` 与 directory shard count；
13. FA/WA minimum capacity；
14. FA/WA threshold/recycle files per shard；
15. `/dev/shm`、MemAvailable、storage available 与各 gate；
16. dependency/startup-capacity/experiment exit code；
17. lifecycle count；
18. request/success/retry count；
19. warmup/prime/follower HTTP、token、SSE；
20. prime save/cache-dump bytes delta；
21. follower UCM hit/HBM hit/cache lookup/cache load/load/Posix S2H delta；
22. UCM error/invalid counter delta；
23. external lookup log corroboration；
24. prime/follower TTFT/TPOT/ITL P95/E2EL；
25. path_class、mechanism_implemented、formal grade；
26. exact startup exception/class（如有）；
27. stopped/restored card IDs、marker count、restore exact；
28. cleanup、7000、vLLM residual、tracked-clean；
29. `result_summary.md` 绝对路径；
30. bounded package 每个文件的 bytes/SHA-256/sensitivity；
31. manifest bytes/SHA、payload/transfer totals；
32. raw server-local 路径；
33. `next_task_authorized=false`。

## 16. 有界结果包与传输边界

有界 payload 预期：

```text
cleanup_status.txt
dependency_and_environment_summary.json
grading_summary.json
request_summary.tsv
resource_recovery_summary.json
result_summary.md
startup_capacity_summary.json
startup_failure_summary.json
task_grade.txt
ucm_metric_deltas.tsv
ucm_path_summary.json
candidate_manifest.server_local.json
```

总传输上限：

```text
71680 bytes
```

以下只留服务器本地，不进入有界包：

- raw vLLM/UCM logs；
- 完整 Prometheus metrics；
- request bodies；
- request IDs；
- token IDs；
- prompt/generated content；
- overlay/source/env；
- raw hash trace；
- runtime 目录。

`result_transfer_authorized=true` 只表示完整有界包可供选择，不等于已选渠道。完成后先
报告：

```text
result_summary.md absolute path
complete bounded file list
each file bytes
each file SHA-256
each file sensitivity
manifest bytes/SHA
payload and transfer totals
available methods: email / upload-api / server-local
recommended method and reason
```

然后暂停等待用户明确选择一个渠道。不得自动发送、不得先发 status-only 邮件、不得在
失败后自动切换渠道。

## 17. 任务终点

本轮结束后：

- 不创建 run02；
- 不重跑 run04；
- 不自动进入 K2-R1/K3/P8.3-I1；
- 不运行排队的 P6.3C-R1；
- 不根据结果在服务器改代码；
- 保持 0–7 keep-alive 已恢复；
- 等待开发机复核完整有界结果并决定下一轮。
