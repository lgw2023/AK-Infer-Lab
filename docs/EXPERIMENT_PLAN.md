# 实验计划

## 1. 实验分层

本项目实验分为四组。

第一组是 **Readiness / Smoke**：证明环境、模型、runtime、API server、profiler、request-device join 能跑通。Smoke 不能解释为性能 benchmark。

第二组是 **Controlled Benchmark**：固定模型、请求、输出长度、并发、采样和所有环境变量，只改变一个变量。用于判断 prefix cache、chunked prefill、MTP、KV offload 等功能的方向性影响。

第三组是 **State Tiering Experiment**：专门测试 KV、Prefix、Expert 在 HBM/DRAM/SSD 间迁移的收益、开销和失败边界。

第四组是 **Hardware Sensitivity / What-if**：用 trace 和 microbench 驱动仿真器，扫 HBM 容量、DRAM 带宽、SSD I/O、UB/HCCS、CPU 核数和下一代 HMM/PIM 参数。

## 2. P0-P1：当前已完成基础与下一步收束

当前已经具备：服务器可观测体检、小模型 transformers/vLLM smoke、长 prompt calibration、vLLM API continuous16、prefix-cache on/off stats、msprof pairing、SQLite request window overlap、request-device 聚合加速、fixed 64 tokens 受控 replay。

下一步 P1.27 只读 P1.26 final analysis，输出小摘要，不重跑模型、不重新采集 msprof。P1.27 后应形成第一版 `controlled_replay_readout.md`，明确哪些字段可用于 DeepSeek 八卡基准。

## 3. P2：DeepSeek-V4-Flash 八卡基准

### P2.1 环境准备

- 确认 CANN / driver / torch-npu / vLLM-Ascend / container / conda 版本。
- 确认 8 张 NPU health、HBM、HCCL/HCCS、CPU NUMA、DRAM、NVMe。
- 准备 `DeepSeek-V4-Flash-w8a8-mtp` 权重路径。
- 生成 `hardware_snapshot.yaml`。
- 新建 `benchmarks/deepseek_v4_flash/`，先写 experiment card 和 runner 约束，再下发服务器任务。

### P2.2 最小在线 serving

请求形态：

```text
request_count: 1 / 4 / 8 / 16
prompt_len: 4K / 8K / 32K
output_len: fixed 64 first, then 256
reasoning_mode: non-think first, then think/high if parser works
```

验收：

- API server ready。
- 所有请求 HTTP 200。
- generated_token_count 固定。
- vLLM stats 可抽取 Running/Waiting/KV/prefix。
- msprof exit code 0。
- request-device aggregate 完成。

产物边界：
- `smoke` 产物只能证明 server、权重、runtime 和请求路径可运行。
- `controlled_benchmark` 产物必须包含固定输出长度、单变量开关、完整 server command、server stats、msprof、request-device aggregate 和已知混杂因素。
- 降低上下文长度或关闭官方教程关键开关完成的实验必须标为 `degraded_smoke`。

### P2.3 受控 A/B

| A/B | 控制变量 | 判读 |
| --- | --- | --- |
| prefix on/off | `--enable-prefix-caching` | TTFT、device task、KV usage、prefix stats |
| MTP on/off | `--speculative-config` | TPOT、acceptance、tail |
| chunked prefill on/off | `--enable-chunked-prefill` | TTFT、prefill device tasks |
| max_model_len | 32K/128K/384K | HBM/KV/tail risk |
| max_num_seqs | 1/4/8/16 | continuous batching behavior |

## 4. P3：KV / Prefix 分层实验

### P3.1 KV Cache CPU Offload

变量：

```yaml
num_cpu_blocks: [1000, 5000, 10000]
block_size: [64, 128]
pinned_memory: [false, true]
gpu_memory_utilization: [0.80, 0.90, 0.92]
```

指标：

```text
HBM freed
CPU DRAM used
D2H/H2D bytes
D2H/H2D latency
copy overlap ratio
prefix hit/miss
restore latency
TTFT/TPOT/P95/P99
```

### P3.2 UCM / external KV

先做 DRAM local cache，再做 storage backend。SSD 只允许做冷层，不进入逐 token decode 热路径。

### P3.3 Mooncake KV Pool / SSD offload

只在 P3 后半段进入。必须显式配置 SSD quota、per-rank buffer、eviction policy 和 offload path。所有 SSD 读写必须记录 I/O size、queue depth、P95/P99 latency。

## 5. P4：MoE Expert 分层实验

### P4.1 Expert Trace

在中型 MoE 上先跑：

```text
top-k experts per layer
expert score
expert frequency
reuse distance
expert tier
expert hit/miss
expert load latency
prefetch lead time
wrong prefetch bytes
```

### P4.2 Static Hotset

计算 top-N hot expert 常驻命中率曲线：

```text
N = 4, 8, 16, 32, 64 experts per layer
```

输出 hotset coverage、HBM cost、miss penalty。

### P4.3 Warm Tier

把 warm expert 放 DRAM/DUMA，测试 staged H2D 与 NPU execution 是否可重叠。若无法重叠，记录为失败边界。

### P4.4 Cold Tier

SSD cold expert 只做离线或提前预取，不允许在 decode step 发生随机小块读取。若必须读取，实验应标记为 cold miss failure case。

## 6. P5：单卡/双卡极限实验

### 单卡目标

- 跑通小模型 4K/8K/16K trace。
- 跑通中型 MoE expert trace。
- 用 DeepSeek 子图或模拟 expert pool 验证容量分层。
- 记录为什么 official DeepSeek-V4-Flash W8A8-MTP 不 fit。

### 双卡目标

- 验证 2-rank TP/EP 下 runtime 和 trace。
- 测 rank 间通信、HBM 分布、KV placement。
- 作为 simulator 的低资源校准点。

## 7. P6：规格反推

输出 `hardware_sensitivity_report.md`：

| 参数 | 扫描范围 | 输出 |
| --- | --- | --- |
| HBM per NPU | 64/84/128/200/400GB | fit boundary、hotset coverage |
| HBM bandwidth | current × 0.5/1/2 | TPOT sensitivity |
| DRAM bandwidth | current × 0.5/1/2 | KV/expert warm tier sensitivity |
| NPU-CPU link | current / 200GB/s / 400GB/s | H2D/H2D stall |
| SSD bandwidth/IOPS | current / direct path | cold tier feasibility |
| CPU cores | 48/96/192 | metadata/I/O/prefetch capacity |
| HMM/PIM | modeled | next-gen benefit |
