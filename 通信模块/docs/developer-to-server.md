# 开发机 → Ascend 服务器：当前唯一任务

## 当前唯一服务器动作：P8.2-K2-R0 run03 UCM DRAM external prefix path

```yaml
task_id: p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728
run_id: p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run03
stage: P8.2-K2-R0
execution_mode: authorized_run03_nfs_identity_cmake_python_capacity_and_single_lifecycle
npu_execution_authorized: true
npu_card_ids: [0, 1, 2, 3, 4, 5, 6, 7]
formal_model_lifecycle_count_exact: 1
model_request_count_exact: 3
request_retry_count_exact: 0
internal_prefix_cache_enabled: false
ucm_cache_buffer_capacity_gb: 16
performance_benefit_required: false
unique_root_cause_required: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
run03_authorized: true
next_task_authorized: false
```

服务器助手只负责：

1. 安全同步远程 `main`；
2. 核对本文件与固定输入；
3. 运行一次只读 audit；
4. 运行一次且仅一次 run03 driver；
5. 原样回报 driver 的完整标准输出；
6. 等待用户选择结果传输渠道。

代码、依赖恢复、NFS 身份复验、CMake Python 绑定、容量预检、启动、三请求、
cleanup、分级和有界打包均已由开发机写入仓库。服务器助手不得再写代码、改参数、
手工拆 runner、创建 run04，或在失败后临场修补并重试。

不要运行当前仓库中已开发但排队的 P6.3C-R1；不要进入 K2-R1、K3、P8.3-I1
或 P9。

## 1. 项目全局背景与本轮目标

DeepSeek-V4-Flash / vLLM-Ascend 的分层 KV 工程已完成两条前置链：

- P8.2-K1A-F1 已由 R17 闭合
  `physical CPU-only → logical hit → H2D restore` 的内建 warm-tier 机制；
- P8.2-K2-R0 继续实现独立的 UCM external KV 路径：
  `prime save → DRAM external lookup/hit → Cache load/H2D → follower completion`。

本轮目标是让真实 UCM `Cache|Posix` 管线在一个 TP8+EP+MTP lifecycle 内启动并
完成三请求，不是做“红绿黄测试工程”。结果中的 TTFT/TPOT/ITL/E2EL 都应忠实记录，
但当前 Atlas A2 上延迟差值的正负不是机制实现门，也不限制该方案在其他硬件上的价值。
性能收益不是本轮实现通过的前置条件。

K2-R0 仍未完成，因此本轮是同一机制的 run03 修复运行，不升级为 K2-R1。

## 2. run01、run02 已确认事实

### run01

- grade：
  `blocked_p8_2_k2_r0_dependency_or_startup_preflight`；
- lifecycle/request：`0 / 0`；
- 失败链：NFS 上旧目录为 `nobody` → Git dubious ownership → 只有半克隆 `.git`
  → 无 package metadata → UCM 未安装；
- NPU 未触碰，keep-alive 全程保持。

### run02

- server HEAD 与当时 `origin/main` 一致、tracked-clean；
- dependency 已完全通过：
  `dependency_status=ready`、pinned source HEAD/remote/关键文件成立；
- import probe：
  `uc-manager=0.6.0`、`vllm=0.22.1+empty`、
  `vllm-ascend=0.22.1rc1`、`wrapt=1.17.2`、
  `UCMConnector` 和 `UCMConnectorV1` 均成功；
- 正式 lifecycle 已启动一次，但服务未 ready，请求数为 0；
- 精确错误：

```text
RuntimeError: Worker failed with error '-50000, too small buffer(8589934592) on shard(6627328)'
```

- cleanup clean，7000 空闲，vLLM 残留 0，0–7 keep-alive 同卡恢复；
- run02 bounded manifest：
  `166e232a...`，payload `9538 bytes`，完整 transfer `12471 bytes`。

run02 不是 UCM 依赖失败，也没有运行到 external hit/H2D 请求路径。它证明：

1. pinned UCM 能在该栈构建和 import；
2. vLLM 能进入 UCM CacheStore 初始化；
3. 8 GiB 配置不足以通过当前模型 shard 几何。

## 3. 为什么 run03 固定 16 GiB

固定 UCM commit：

```text
01cbf9b71892c88319862fa57f195b0bef93fa6f
```

该版本 CacheStore 的容量门等价于：

```text
buffer_number = floor(buffer_capacity_bytes / shard_size_bytes)
required_buffer_number = max(1024, 2 * load_exclusive_buffer_number)
```

本任务中 pinned source 默认：

```text
load_exclusive_buffer_number = 1024
required_buffer_number = 2048
```

run02 实际 shard：

```text
shard_size_bytes = 6627328
```

因此：

```text
8 GiB  / 6627328 = 1296 shards  < 2048  # run02 精确失败
13 GiB / 6627328 = 2106 shards >= 2048  # 最小整数 GiB 可通过
16 GiB / 6627328 = 2592 shards >= 2048  # run03 固定值，保留工程余量
```

run03 配置固定为每 rank 16 GiB。TP8 的保守预算按 `16 GiB × 8 = 128 GiB`
计算，并额外要求 16 GiB headroom；在停卡前同时检查：

- `/dev/shm` 可用字节不少于 144 GiB；
- `/proc/meminfo` 的 `MemAvailable` 不少于 144 GiB；
- 16 GiB 对 run02 实际 shard 的预测 buffer number 为 2592，满足 2048。

这些是停卡前的保守容量门，不冒充当前 lifecycle 已成功分配。driver 会在真实启动后
继续解析 runtime 是否报告新的 buffer/shard 几何。

若容量门失败，driver 不停 keep-alive、不启动 vLLM、不发送请求，并生成独立
`startup_capacity_summary.json`；服务器助手不得自行降低 headroom、改成 13 GiB、
扩大 `/dev/shm`、调整 TP 或绕过门。

## 4. NFS `no_root_squash` 修复如何进入本轮

用户已经在内部昇腾服务器四个节点的 NFS export 中，对所有对端访问规则加入
`no_root_squash` 并重新加载配置；跨节点创建的新文件已验证为：

```text
root:shareddata
uid:gid = 0:3000
```

run03 恢复使用仓库 `server_local` 下的持久 NFS 路径：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/third_party/unified-cache-management-01cbf9b
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/python_envs/ucm-vllm-ascend0221-01cbf9b
```

正式 driver 会先在两个父目录各创建一个临时 probe，核对新对象均为 UID 0 / GID
3000，然后删除精确 probe。此步骤发生在 NPU 操作之前。

若旧 run01 的 `nobody` 半成品仍存在，driver 会将其移动到同父目录 `quarantine/`
保留，不删除；随后在同一 NFS 父目录 staging 中重建，完整验证后原子 rename。

禁止：

- 不要再把 `UCM_SOURCE_ROOT` 或 `UCM_ENV_PREFIX` 覆盖到 `/data/disk2`；
- 不要预先手工 clone/build；
- 不要 `chown -R`；
- 不得执行 `git config --global --add safe.directory`；
- 不要删除 quarantine；
- 不要删除或改写 base conda 环境。

若 live probe 不是 `0:3000`，这是 NFS 现场配置未在当前挂载路径生效。driver 会在
停卡前失败；服务器助手只回报证据，不做第二种修复。

## 5. CMake Python 3.11 绑定修复

run02 的人工准备还暴露了一个可重复构建问题：

- UCM `setup.py` 传入 `-DPYTHON_EXECUTABLE=<venv python>`；
- 当前 CMake `find_package(Python ...)` 使用大小写敏感的
  `Python_EXECUTABLE`；
- 直接构建可能误选系统 Python 3.10，而目标隔离 venv 为 Python 3.11。

run03 已新增 tracked wrapper：

```text
tools/inference_contracts/run_ucm_cmake_python_wrapper.sh
```

driver 在构建 venv 时只对该次 pip native build 的 PATH 注入名为 `cmake` 的 wrapper：

- 将 `-DPYTHON_EXECUTABLE=...` 转为
  `-DPython_EXECUTABLE=<本次 staging venv/bin/python>`；
- build/install 子命令透传给真实 CMake；
- 不编辑 pinned UCM source；
- 不修改全局 PATH、CMake、conda 或 site-packages；
- 写 server-local wrapper 使用日志和 bounded 次数/哈希摘要；
- import probe 通过后才写 install marker。

服务器助手不要再创建临时 CMake wrapper，也不要手工传 CMake 参数。

## 6. 固定依赖与运行合同

### 依赖

- UCM URL：
  `https://github.com/ModelEngine-Group/unified-cache-management.git`
- UCM commit：
  `01cbf9b71892c88319862fa57f195b0bef93fa6f`
- base env：
  `/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1`
- UCM 安装范围：独立 `server_local/python_envs` venv；
- base conda mutation：false；
- `ENABLE_UCM_PATCH=1`；
- `UCM_ENGINE_TYPE=vllm-ascend.a2`。

### 模型与服务

- model：
  `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp`
- served name：`deepseek-v4-flash-w8a8-mtp`
- TP8 + EP；
- MTP：`method=mtp`、`num_speculative_tokens=1`；
- quantization：`ascend`；
- graph：`FULL_DECODE_ONLY`；
- `max_model_len=135168`；
- `max_num_batched_tokens=4096`；
- `max_num_seqs=1`；
- block size 128；
- GPU memory utilization 0.92；
- Chunked Prefill 开启；
- vLLM internal Prefix Cache 显式关闭；
- 端口 7000。

### UCM

- connector：`UCMConnector`；
- role：`kv_both`；
- pipeline：`Cache|Posix`；
- `cache_buffer_capacity_gb=16`；
- Posix capacity 32 GiB；
- `use_layerwise=true`；
- `enable_event_sync=true`；
- `enable_metrics=true`；
- `use_gdr=false`；
- `persist_token_threshold=0`；
- `load_tokens_threshold=2048`；
- raw hash trace 关闭。

### 唯一请求顺序

并发固定为 1，输出固定 64 token，零 retry：

1. unrelated warmup：4096 context；
2. prime：32768 context；
3. follower：与 prime 的 32768 request body 字节完全一致。

不得增加请求、改 context、重发 follower、运行第二 lifecycle 或做 sweep。

## 7. 同步前置条件

仓库：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab
```

先检查。如果 tracked 文件有本地修改，不得覆盖；停止并回报。

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git status --short --branch
git fetch origin main
git switch main
git pull --ff-only origin main
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --short --branch
```

必须同时满足：

- branch=`main`；
- `HEAD == origin/main`；
- ahead/behind=`0 0`；
- `git status --porcelain --untracked-files=no` 为空。

不要删除未跟踪的历史 `server_local` 结果；它们不影响 tracked-clean。

## 8. 固定输入 SHA-256

同步后在仓库根执行：

```bash
sha256sum \
  benchmarks/deepseek_v4_flash/p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml \
  benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh \
  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py \
  tools/inference_contracts/run_ucm_cmake_python_wrapper.sh \
  tests/inference_contracts/test_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
```

必须逐项等于：

```text
55e7e5a1e762e6c0d18b0935438de533888fcb6136295ad8436375e2cae0fc4a  benchmarks/deepseek_v4_flash/p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml
2e54320ba97ce5644f669c567984c4311fa5ac869ffbcf593f0edca2637d0010  benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml
0ec29d4e67716fc6c8e9b4a591ffd6524e6468915a7cd1332343ffeb391bec51  tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh
1a04a6bae1d80998fd245285aa135e9652b8c0c32a969aca3fe0c823f3022fdf  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh
45b7809acefc265fc148c4f24cb2e17fd44bfd4238ee55e7bf54f1a666fe84fe  tools/inference_contracts/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
eb42b473cc8b729e515cd4bc8732d65c69c1315bf9cb879be1cd9c4385b4c2af  tools/inference_contracts/run_ucm_cmake_python_wrapper.sh
168b332d183bd27f6113caf9ded955a58705f1bf1f137bfc17fcddff983853f8  tests/inference_contracts/test_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
```

任一 SHA 不匹配，停止。不要继续运行旧代码，也不要在服务器编辑文件。

## 9. 只读 audit-only

audit 不使用 NPU，不停 keep-alive：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
P8_2_K2_R0_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run03
```

至少核对：

```text
expected_result_basename=..._run03
nfs_no_root_squash_operator_verified=true
nfs_expected_new_object_uid=0
nfs_expected_new_object_gid=3000
dependency_default_root=repo_server_local_nfs
ucm_cmake_python_binding=tracked_wrapper_rewrites_to_Python_EXECUTABLE
ucm_cache_buffer_capacity_gib_per_rank=16
run02_observed_shard_size_bytes=6627328
ucm_required_buffer_number=2048
ucm_configured_buffer_number=2592
conservative_total_buffer_gib=128
pre_npu_shm_and_memavailable_gate=true
formal_model_lifecycle_count_exact=1
model_request_count_exact=3
request_retry_count_exact=0
internal_prefix_cache_enabled=false
ucm_store_pipeline=Cache|Posix
```

audit 失败时不运行正式命令、不停卡、不改代码。

## 10. NPU keep-alive 规则

本任务使用全部八张卡。正式 driver 会只对卡 `0 1 2 3 4 5 6 7` 停止
低优先级 keep-alive：

```bash
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
```

无论成功、失败、中断或提前退出，都必须恢复完全相同的卡集：

```bash
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

driver 已自动执行。不要在正式命令前手工停卡。依赖、NFS 或容量预检失败时必须保持
keep-alive 原样运行。

最终必须核：

- stopped cards 与 restored cards 恰好都是 `[0,1,2,3,4,5,6,7]`，或预检失败时
  两者均为空；
- 正式 lifecycle 后 16 个 marker 恢复；
- 7000 listener=0；
- vLLM residual=0；
- tracked worktree clean。

## 11. 唯一正式执行命令

结果目录必须预先不存在。只运行一次：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_server_task.sh \
  /data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run03
```

不要通过 `tee` 截断标准输出；请保留并完整贴回
`K2_R0_SERVER_REPORT_BEGIN` 到 `K2_R0_SERVER_REPORT_END`。

不要：

- 不创建 run04；
- 不重跑 run01/run02；
- 不覆盖已有结果目录；
- 不单独运行 lifecycle/request Python；
- 不改 16 GiB、32K prime/follower 或任何启动参数；
- 不 retry；
- 不启用 vLLM internal Prefix Cache；
- 不开启 profiler；
- 不保留生成内容、request ID 或 token ID 到 bounded 包；
- 不运行 P6.3C-R1、K2-R1、K3、P8.3-I1 或 P9；
- 不在服务器提交或推送代码；
- 不自动邮件或上传。

## 12. driver 内部执行顺序

服务器助手不需要手工执行，但要理解结果：

1. 核 `main == origin/main` 和 tracked-clean；
2. 建 run03 result/runtime；
3. 在 NFS source/env 父目录做 UID/GID 创建 probe；
4. 校验或 quarantine 旧 UCM source；
5. pinned clone → 校验 → 原子 promote；
6. 校验或 quarantine 旧隔离 venv；
7. 用 tracked CMake wrapper 构建 UCM；
8. import probe 后写 marker；
9. 写 `dependency_and_environment_summary.json`；
10. 检查 shard geometry、`/dev/shm`、`MemAvailable`；
11. 只有全部 pre-NPU gate 通过才停止 0–7 keep-alive；
12. 启动一个 TP8+EP+MTP lifecycle；
13. health 与 UCM metrics ready 后发送 3 个固定请求；
14. 逐请求冻结 metrics delta 和 server log 区间；
15. 清理 vLLM；
16. 恢复同一卡集；
17. 生成 capacity/startup/path/grading/recovery 摘要；
18. 生成完整 bounded manifest；
19. 输出一次性完整报告。

## 13. 分级语义

分级已拆开，不再把所有零请求都写成“dependency or startup”：

```text
blocked_p8_2_k2_r0_dependency_preflight
blocked_p8_2_k2_r0_startup_capacity_preflight
blocked_p8_2_k2_r0_lifecycle_startup
incomplete_p8_2_k2_r0_ucm_external_prefix_path
partial_p8_2_k2_r0_ucm_external_hit_non_dram_or_incomplete_recovery
implemented_p8_2_k2_r0_ucm_dram_external_prefix_path
```

`implemented...` 要求：

- dependency ready；
- pre-NPU capacity gate ready；
- server ready；
- 3/3 请求成功；
- prime save bytes 与 Cache dump bytes 都正；
- follower UCM hit tokens 正；
- follower GPU HBM hit tokens 为 0；
- follower Cache lookup hit blocks 正；
- follower Cache load bytes 与 connector load bytes 都正；
- follower Posix S2H bytes 为 0；
- UCM error/invalid delta 为 0；
- server log 有 external hit 佐证；
- cleanup clean；
- keep-alive 同卡恢复。

这表示指定环境和固定 cell 的真实 DRAM-first external prefix 机制实现跑通。它不要求
本机性能收益为正，也不声明通用于所有硬件、模型或请求。

如果 server ready 但请求或机制门不全，忠实报 incomplete/partial；不要为了得到
implemented 修改参数或重跑。

## 14. 有界结果包

预计 payload：

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

raw vLLM log、UCM log、metrics、dependency build log、CMake wrapper log、请求 body、
request IDs、token IDs 与生成内容均留服务器本地。bounded 文件必须为
`bounded_operational_metadata_no_content_or_token_ids`，完整 transfer 不超过 71680
bytes。

## 15. 完整回报清单

请一次性回报以下全部内容，不要只给一句 grade：

1. HEAD、origin/main、ahead/behind、tracked-clean；
2. 七个固定输入逐文件 SHA-256；
3. audit-only 完整输出与 exit；
4. live NFS probe 两个父目录、UID/GID、是否精确 `0:3000`；
5. source root、HEAD、remote、tracked-clean、tree UID/GID、是否 reused/quarantined/promoted；
6. venv root、marker、import probe、是否 reused/quarantined/promoted；
7. CMake wrapper SHA、invocation/configure/rewrite 次数、Python binding 状态；
8. dependency exit/status 和 build log server-local 路径；
9. 16 GiB、shard size、configured/required buffer number；
10. `/dev/shm` available、MemAvailable、128 GiB conservative total、16 GiB headroom、
    pre-NPU gate；
11. lifecycle count、server ready、startup class、若失败则 bounded buffer/shard 分类；
12. 三请求逐项 HTTP/token/SSE/TTFT/TPOT/ITL P95/E2EL 与 retry=0；
13. prime save/cache dump delta；
14. follower external hit、HBM hit、Cache hit/load、connector load、Posix S2H delta；
15. UCM error/invalid 总 delta 与 external lookup log 摘要；
16. path class、mechanism implemented、formal grade；
17. cleanup、7000、vLLM residual、实际停卡/恢复卡集、16 marker、tracked-clean；
18. result summary 绝对路径；
19. candidate manifest 全文；
20. manifest 自身 bytes/SHA-256、payload/transfer 文件数与总 bytes；
21. sensitivity、available methods、recommended method/reason；
22. 明确 `next_task_authorized=false`。

正式 driver 会输出上述核心 JSON/TSV。请从
`K2_R0_SERVER_REPORT_BEGIN` 到 `K2_R0_SERVER_REPORT_END` 原样回传，不重新省略或
改写；若某字段未执行，写 `not_executed`，不要猜值。

## 16. 结果传输边界

`result_transfer_authorized: true` 只表示 bounded package 可供用户选择，不是自动发送
许可。

正式运行后先报告：

- result summary 精确绝对路径；
- 完整文件清单；
- 每个文件 bytes / SHA-256 / sensitivity；
- 总 bytes；
- 可用方法：`email` / `upload-api` / `server-local`；
- 一个推荐方法与理由。

然后暂停，等待用户对完整 scope 选择一种方法。不得先发状态邮件，不得自动上传，
不得在渠道失败后自动切换。大日志继续留服务器。

## 17. 终止条件

以下任一情况都停止，不做第二次尝试：

- Git 不能 fast-forward 或 tracked dirty；
- 固定输入 SHA 不匹配；
- audit 失败；
- NFS probe 不是 UID/GID `0:3000`；
- dependency build/import 失败；
- capacity preflight 失败；
- keep-alive stop 失败；
- lifecycle startup 失败；
- 任一请求失败；
- cleanup 或同卡恢复不完整；
- package 自校验失败。

即使失败，也必须让 driver 完成有界结果、cleanup 和完整报告。完成后暂停等待开发机
复核；`next_task_authorized=false`。
