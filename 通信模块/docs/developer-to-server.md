# 开发机 → Ascend 服务器：当前唯一任务

## 当前唯一服务器动作：K2-R0 run03 FAWA 启动内层异常归因

```yaml
task_id: p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729
run_id: p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729_run01
stage: P8.2-K2-R0
execution_mode: zero_npu_read_only_parent_runtime_and_pinned_source_attribution
npu_execution_authorized: false
formal_model_lifecycle_count_exact: 0
model_request_count_exact: 0
request_retry_count_exact: 0
keep_alive_action: leave_running
parent_and_source_mutation_authorized: false
dependency_install_authorized: false
server_side_code_edit_authorized: false
run04_authorized: false
parameter_sweep_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
next_task_authorized: false
```

这是一项零 NPU、零 vLLM、零模型请求的服务器本地归因任务。服务器助手只负责：

1. fast-forward 同步远程 `main`；
2. 核对本文件和固定输入；
3. 运行一次 audit-only；
4. 运行一次唯一归因 driver；
5. 原样回报 `K2_R0_RUN03_ATTRIBUTION_REPORT_BEGIN/END` 全段；
6. 列出完整有界包并等待用户选择传输渠道。

解析、父包校验、原始日志只读检查、pinned source 语义检查、异常抽取、FA/WA
store 几何恢复、敏感字段裁剪、有界打包和最终判级都已经由开发机写入仓库。服务器
助手不得再写代码、改参数、安装依赖、重启 run03、创建 run04，或根据日志自行启动
一次 NPU “验证”。

不要运行已开发但排队的 P6.3C-R1；不要进入 K2-R1、K3、P8.3-I1 或 P9。

## 1. 项目目标与本轮为什么必要

DeepSeek-V4-Flash / vLLM-Ascend 的分层 KV 工程已经完成：

- K1A-F1 R17：内建 warm-tier 的
  `physical CPU-only → logical hit → H2D restore` 机制闭环；
- K2-R0：正在实现独立的 UCM external KV 路径
  `prime save → DRAM external lookup/hit → Cache load/H2D → follower completion`。

K2-R0 run03 已经越过此前两个前置阻塞：

1. NFS `root_squash` / `nobody` 污染已经由四节点 `no_root_squash` 修复并由 live
   `0:3000` probe 复验；
2. run02 的 8 GiB CacheStore 容量门已经由 16 GiB/rank 配置和主机容量 preflight
   越过。

run03 仍在三请求之前启动失败。现有有界包只保留：

```text
startup_class=lifecycle_startup_failed_other
known outer frame=ucm/integration/vllm/ucm_connector.py:2669
operation=UCMFAWAConnector(vllm_config, role, kv_cache_config)
```

它没有保留真正可修复的内层异常类型、异常消息、嵌套 traceback、失败构造方法，以及
分别属于 FA/WA、scheduler/worker 的实际 store 配置。只凭 `2669` 不能判断是：

- group meta / Ascend hybrid geometry；
- FA store；
- WA store；
- scheduler store；
- worker cache registration；
- shard/block/tensor size；
- 两个 store 对显式 16 GiB 的容量语义；
- Posix namespace / 权限；
- host allocation；
- 其他 native store 初始化错误。

因此本轮不是“为了红绿黄而测”，而是为下一次唯一的定向修复 lifecycle 取得缺失的
机制证据。未拿到精确内层异常前，禁止盲目继续加内存或重跑 NPU。

## 2. run03 已确认事实：不要重新调查已关闭的门

父任务：

```text
p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run03
```

已确认：

- server HEAD 与当时 `origin/main` 一致、tracked-clean；
- dependency=`ready`；
- NFS 新对象身份=`root:shareddata (uid=0,gid=3000)`；
- pinned UCM HEAD=`01cbf9b71892c88319862fa57f195b0bef93fa6f`；
- UCM source/env 原子 promotion 成立；
- CMake wrapper 将 staging venv Python 3.11 正确绑定；
- import probe：
  `uc-manager 0.6.0 | vllm 0.22.1+empty | vllm-ascend 0.22.1rc1 |
  wrapt 1.17.2 | UCMConnector | UCMConnectorV1`；
- startup capacity=`ready`；
- 显式 capacity=`16 GiB/rank`；
- run02 shard 预测下 `2592 >= required 2048`；
- `/dev/shm` 可用约 745 GiB；
- `MemAvailable` 约 1.28 TiB；
- run02 的
  `too small buffer(8589934592) on shard(6627328)` 未在 run03 重现；
- 正式 lifecycle=`1`，server ready=false；
- request=`0/3`，retry=`0`；
- grade=`blocked_p8_2_k2_r0_lifecycle_startup`；
- cleanup clean；
- 7000 空闲，vLLM 残留 0；
- 0–7 keep-alive 同卡恢复，marker 16。

本轮不得重建 UCM source/env、不得再验证 NFS export、不得调整 16 GiB、不得启动
模型。driver 会对父包和 source 进行只读一致性检查，但不会重复 run03 的工程动作。

## 3. 父证据与固定路径

仓库：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab
```

run03 父结果根：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run03
```

本轮唯一要读的原始启动日志：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run03/runtime/vllm_server.log
```

pinned UCM source：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/third_party/unified-cache-management-01cbf9b
```

父 manifest：

```text
bytes=3434
sha256=a278c44dbf879c42fe2119ca8a7708b7bc0aea8103e4387af1ff3c73b974cbe4
payload_file_count=11
payload_total_bytes=15138
transfer_file_count=12
transfer_total_bytes=18572
```

driver 会：

1. 验证父 manifest 的固定 bytes/SHA；
2. 对 manifest 中 11 个 payload 逐文件复算 bytes/SHA；
3. 验证父 grade、dependency、capacity、lifecycle/request 事实；
4. 记录 raw log 的 size/mtime，分析结束再次检查不变；
5. 不在 bounded package 中保存 raw log SHA；
6. 不删除、不截断、不改写父目录任何文件。

如果上述固定父目录或 raw log 不存在，不要全盘搜索、不要改指向 run02、不要从旧
terminal 文本拼一个替代输入。只回报缺失的精确路径并停止；本轮仍不得触 NPU。

## 4. pinned UCM 构造链：服务器助手无需手工读源码

固定 commit：

```text
01cbf9b71892c88319862fa57f195b0bef93fa6f
```

driver 会验证 HEAD、tracked-clean 和三个关键源码文件：

```text
ucm/integration/vllm/ucm_connector.py
ucm/integration/vllm/hma_connector.py
ucm/store/cache/cc/cache_store.cc
```

开发机对 pinned source 已确认的构造语义：

1. `ucm_connector.py:2669` 只是外层选择并实例化 `UCMFAWAConnector`；
2. `UCMFAWAConnector.__init__` 先 `_init_group_metas()`；
3. scheduler role 随后按 FA→WA 顺序创建两个 store；
4. `_base_store_config()` 对用户 connector config 做 `deepcopy`，FA/WA 各复制一次；
5. 显式存在 `cache_buffer_capacity_gb` 时，
   `_set_default_shm_buffer_capacity()` 立即返回；
6. 因此 run03 YAML 的显式 16 GiB 会进入 FA 和 WA 两个 store；源码中的
   `128 // 2 = 64 GiB/store` 默认分拆只在未显式配置时生效；
7. worker role 会根据实际 tensor size list 计算 padded `shard_size` 和
   `block_size`；
8. store config 在 factory create 之前写入日志；
9. CacheStore 的 `device_id=-1` scheduler 路径在 size gate 前返回，worker 才使用
   shard/buffer 数量门。

“显式 16 GiB 复制给两个 store”表示每个 connector instance 的配置语义预测为
FA 16 + WA 16 GiB，不等同于已经证明总主机实际分配 32 GiB，也不能替代真实日志里的
role/shard 证据。本轮脚本会把源码语义和 runtime 观察分开输出。

## 5. 本轮代码实际会提取什么

唯一 analyzer：

```text
tools/inference_contracts/run_deepseek_p8_2_k2_r0_run03_fawa_startup_attribution.py
```

它会从完整 raw log 中提取：

- 精确 exception type；
- 精确 exception message；
- generic `Worker failed...` 外层 wrapper 与内层异常的区分；
- UCM/vLLM bounded traceback frames；
- 是否再次出现 outer `ucm_connector.py:2669`；
- 是否出现内层 `hma_connector.py` frame；
- 最接近失败的 constructor method；
- failure stage；
- 所有可解析的
  `create FAWA FA|WA ... with config: {...}` 事件；
- label：FA/WA；
- role：scheduler/worker（由 `device_id` 判断）；
- `block_size`；
- `shard_size`；
- `tensor_count` / `tensor_bytes`；
- `cache_buffer_capacity_gb`；
- `cache_load_exclusive_buffer_number`；
- `store_pipeline`；
- `share_buffer_enable`；
- `local_rank_size`；
- 能计算时的 `buffer_number`、required number 与预测 gate；
- runtime 日志未提供时的明确 `null`，不会用 run02 的 shard 冒充 run03 实测。

异常 excerpt：

- 最大 18000 bytes；
- 只选 traceback、UCM frame、FAWA store config 和 worker failure 附近窗口；
- request ID、token IDs、prompt/generated text 做 fail-safe 裁剪；
- raw log、生成内容、token IDs、request IDs、raw log hash 不进入有界包；
- run03 实际为零请求，仍按同一敏感边界处理。

## 6. grade 与后续判读

预期正式 grade：

```text
attributed_p8_2_k2_r0_run03_fawa_startup_failure
```

要求同时成立：

- 父 manifest 和全部 payload 一致；
- raw log 分析前后 size/mtime 不变；
- pinned source exact 且 tracked-clean；
- 恢复精确 exception type；
- 恢复精确 exception message；
- 至少一个 UCM inner/outer frame；
- 零 NPU、零 vLLM、零请求；
- keep-alive 全程保持；
- 7000 和 vLLM residual 前后均为 0。

可能的非预期 grade：

```text
partial_p8_2_k2_r0_run03_startup_failure_attribution
blocked_p8_2_k2_r0_run03_startup_evidence_incomplete
```

这些 grade 只描述父日志能否支持精确归因，不评价 external KV 方案性能，也不否定
机制目标。无论 grade 如何，本轮都不授权服务器自行修复或启动 run04。

`grading_summary.json` 会给出一个面向开发机的
`recommended_developer_action`，可能是：

- 按 FA/WA 各自真实 shard 重算容量；
- 分离并约束 FA/WA host buffer；
- 修复失败 role 的 shard/block/tensor geometry；
- 修复 namespaced Posix backend preflight；
- 在已恢复的精确 primary frame 做定向代码修复；
- 如果父日志仍缺异常，则增加构造器精确 capture。

这只是下一开发轮输入，不是对服务器的自动执行授权。

## 7. keep-alive 规则

本轮不需要 NPU，必须让低优先级 keep-alive 全程继续运行。唯一 driver 只读
process/port 状态并要求前后均为：

```text
keep_alive_marker_count=16
keep_alive_card_ids=[0,1,2,3,4,5,6,7]
port_7000_listener_count=0
vllm_residual_process_count=0
```

下面两条是仓库要求每份交接都必须明确给出的常规命令，但本轮**禁止执行**：

```bash
# 本轮禁止：不要停止任何卡上的 keep-alive。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 本轮不应发生 stop，因此也不应执行 restore。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
```

如果开始时 marker/card set 不符合预期，driver 会在分析前失败。服务器助手只回报
现场状态，不得为了通过本任务主动 stop/restart keep-alive。

## 8. 同步与 tracked-clean

在服务器执行：

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

git status --short --branch
git fetch origin main
git merge --ff-only origin/main

git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --porcelain --untracked-files=no
```

硬门：

```text
branch=main
HEAD=origin/main
ahead/behind=0 0
tracked-clean=true
```

`server_local/`、`server_results/` 的未跟踪产物允许保留。若有 tracked 修改，不要
stash、reset、checkout 或覆盖；回报精确 tracked paths 后停止。

## 9. 固定开发输入 SHA-256

同步完成后运行：

```bash
sha256sum -c <<'EOF'
90064ab273536bf7c94405246a35e05e0ea8846b37eef1b407260f17ce1fba7a  tools/inference_contracts/run_deepseek_p8_2_k2_r0_run03_fawa_startup_attribution.py
0f56653c037af79293cb20214691c735bc7c5d666de0aa3902266dec14940bda  tools/inference_contracts/run_deepseek_p8_2_k2_r0_run03_fawa_startup_attribution_server_task.sh
9f0a694d42b527851072ac34fe5fedd30656fb6394a5c535685d96f37393297f  benchmarks/deepseek_v4_flash/workloads/p8_2_k2_r0_run03_fawa_startup_attribution.yaml
a91873e40c1b6104d218019f4a7d3f6e3870a95f7275683f9857323faf503135  benchmarks/deepseek_v4_flash/p8_2_k2_r0_run03_fawa_startup_attribution_audit.yaml
EOF
```

四项必须全部 `OK`。不要自己改文件来匹配 hash。

## 10. 唯一 audit-only

```bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab

RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729_run01

P8_2_K2_R0_RUN03_ATTRIBUTION_AUDIT_ONLY=1 \
bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_run03_fawa_startup_attribution_server_task.sh \
  "${RESULT_DIR}"
```

audit-only 必须 exit 0，且输出至少包含：

```text
task_id=p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729
run_id=p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729_run01
execution_mode=zero_npu_read_only_run03_raw_startup_and_pinned_source_attribution
parent_manifest_sha256=a278c44d...
ucm_commit=01cbf9b...
npu_started=false
vllm_started=false
model_requests_sent=0
keep_alive_action=left_running
run04_authorized=false
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
```

audit-only 不创建 `RESULT_DIR`、不读 raw log、不触 NPU、不停 keep-alive。

## 11. 唯一正式命令

先确认结果目录不存在：

```bash
test ! -e "${RESULT_DIR}"
```

然后只运行一次：

```bash
bash tools/inference_contracts/run_deepseek_p8_2_k2_r0_run03_fawa_startup_attribution_server_task.sh \
  "${RESULT_DIR}"
```

禁止：

- 不要手工拆 analyzer 子命令；
- 不要覆盖 `PARENT_RESULT_DIR` 或 `UCM_SOURCE_ROOT`；
- 不要把 parent 改成 Inbox 副本或 run02；
- 不要复制、截断、tail 覆盖原始日志；
- 不要修改 pinned UCM source；
- 不要安装 Python 包；
- 不要启动 vLLM；
- 不要发送 curl 模型请求；
- 不要执行 keep-alive stop/restore；
- 不要运行第二次；
- 不要创建 run02 或 run04；
- 不要为了得到预期 grade 改源码、日志、判级或结果 JSON。

driver 返回非 0 时也禁止 retry。保留已生成的精确结果目录并回报首错。

## 12. 预期结果文件

结果根：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729_run01
```

有界 payload：

```text
fawa_store_geometry.json
grading_summary.json
parent_provenance.json
resource_observation_summary.json
result_summary.md
source_constructor_lineage.json
startup_exception_summary.json
startup_traceback_excerpt.txt
task_grade.txt
```

manifest：

```text
candidate_manifest.server_local.json
```

共 9 payload + 1 manifest。完整 transfer 必须不超过 71680 bytes。

raw `vllm_server.log`、整个 runtime、UCM source、依赖环境、模型文件、请求体不进入
本轮结果包。

## 13. 完整回报要求

服务器助手必须一次性回报以下全部内容，不要只发“完成”或 task grade：

1. HEAD、origin/main、ahead/behind、tracked-clean；
2. 四个固定开发输入 SHA 是否全部匹配；
3. audit-only exit 与全部关键合同字段；
4. 正式 driver exit；
5. 父 manifest bytes/SHA、11 个 payload 是否逐文件匹配；
6. 父 grade/dependency/capacity/lifecycle/request；
7. raw log 绝对路径、bytes、分析前后 size/mtime 是否不变；
8. pinned UCM HEAD、tracked-clean、三个关键 source SHA；
9. exact exception type；
10. exact exception message；
11. bounded exception entries 与 outer/inner frames；
12. failure stage、basis、是否 inference-only；
13. FA/WA store config 观察数、解析数、按 scheduler/worker/label 的计数；
14. 每个已解析 store 的 role、label、device、block、shard、tensor、capacity、
    buffer number/required number；
15. 显式 16 GiB × FA/WA 的 source semantics 与“非实际 host allocation proof”
    边界；
16. recommended developer action；
17. NPU/vLLM/request 是否严格为 0；
18. keep-alive marker/card set 前后、7000 前后、vLLM residual 前后；
19. result_summary.md 绝对路径；
20. 9 个 payload + manifest 的完整文件名、bytes、SHA-256、sensitivity；
21. payload/manifest/transfer 总 bytes 与 70KB gate；
22. available methods、recommended method/reason；
23. `run04_authorized=false`、`next_task_authorized=false`。

最省歧义的方式是原样回传 driver 的：

```text
K2_R0_RUN03_ATTRIBUTION_REPORT_BEGIN
...
K2_R0_RUN03_ATTRIBUTION_REPORT_END
```

不要删减 `startup_traceback_excerpt`。它已经由开发机代码做了 byte cap 和敏感字段
裁剪。

## 14. 结果传输纪律

本任务固定：

```text
result_transfer_authorized=true
automatic_transfer_allowed=false
transfer_method_selected=false
```

这表示有界包具备传输资格，不表示已经选择渠道。正式运行后先回报：

- `result_summary.md` 绝对路径；
- 完整 9 payload + manifest 清单；
- 每文件 bytes；
- 每文件 SHA-256；
- sensitivity；
- 完整 transfer 总 bytes；
- 可用方法：`email` / `upload-api` / `server-local`；
- 推荐方法：`server-local`；
- 推荐理由：小包已在服务器本地，raw log 也必须留服务器。

然后等待用户对这一个完整 scope 明确选择。不得先发状态邮件，不得自动 email 或
upload，不得因为之前某轮选择过某渠道而沿用。

## 15. 完成后暂停

本轮只负责把 run03 启动失败从外层 `2669` 收敛到可修复的内层异常和 store 几何。
完成后：

- 不修改仓库；
- 不修改 UCM source/env；
- 不删除父 raw log；
- 不启动 run04；
- 不进入 K2-R1/K3/P8.3-I1；
- 不运行 P6.3C-R1；
- 等待开发机根据本轮 exact exception 编写下一次定向修复。
