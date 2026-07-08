# 实验计划

## 1. 实验分层

本项目实验分为四组。

第一组是 **Readiness / Smoke**：证明环境、模型、runtime、API server、profiler、request-device join 能跑通。Smoke 不能解释为性能 benchmark。

第二组是 **Controlled Benchmark**：固定模型、请求、输出长度、并发、采样和所有环境变量，只改变一个变量。用于判断 prefix cache、chunked prefill、MTP、KV offload 等功能的方向性影响。

第三组是 **State Tiering Experiment**：专门测试 KV、Prefix、Expert 在 HBM/DRAM/SSD 间迁移的收益、开销和失败边界。

第四组是 **Hardware Sensitivity / What-if**：用 trace 和 microbench 驱动仿真器，扫 HBM 容量、DRAM 带宽、SSD I/O、UB/HCCS、CPU 核数和下一代 HMM/PIM 参数。

## 2. P0-P4：当前已完成基础与收尾口径

当前已经具备：服务器可观测体检、小模型 transformers/vLLM smoke、长 prompt calibration、vLLM API continuous16、prefix-cache on/off stats、msprof pairing、SQLite request window overlap、request-device 聚合加速、fixed 64 tokens 受控 replay、P0/P3 synthetic hardware ceiling sweep。

P0-P4 已按三类目标收尾：

- 服务器环境与硬件天花板基线已完成。
- 小模型推理链路已跑通。
- 小 prompt 推理链路观测已闭环。

边界：

- P0/P3 `hardware_ceiling_sweep_2026_0708_p0_007` 是 synthetic hardware microbench ceiling，不是模型推理 benchmark。
- P1.28 `runtime_vllm_api_msprof_larger_controlled_replay_2026_0708_p1_028` 是 fixed 64 tokens raw counter readout，不是吞吐、scheduler 效率、prefix cache 命中率或瓶颈归因结论。
- 当前不重复执行 P0/P3 sweep 或 P1.28，也不自动启动 DeepSeek-V4-Flash 服务器任务。

## 3. P5：DeepSeek-V4-Flash 实验对象与环境可行性定版

### P5.1 测试对象

| 对象 | 本地状态 | 后续用途 | 边界 |
| --- | --- | --- | --- |
| `DeepSeek-V4-Flash-w8a8-mtp` | `/Volumes/Elements/DeepSeek-V4-Flash-w8a8-mtp`，ModelScope 版本已下载完成 | P6 单机八卡 baseline 的首选对象；优先匹配 vLLM-Ascend `--quantization ascend` reference | 本地路径不是服务器路径；服务器兼容性和权重完整性必须由后续 handoff 验证 |
| `deepseek-ai/DeepSeek-V4-Flash` | `/Volumes/Elements/DeepSeek-V4-Flash`，仍在下载 | 官方来源、版本对照、转换/兼容性评估、P7/P8 边界研究候选 | 下载未完成前不能写成 ready；未验证前不能等同于 Ascend W8A8-MTP runtime 格式 |

用户会自行把模型目录拷贝到 Ascend 服务器。本仓库只登记对象、版本、实验卡和边界，不复制模型 payload，不写服务器路径猜测。

### P5.2 本地定版

- 刷新并记录 DeepSeek HF model card、vLLM-Ascend DeepSeek-V4-Flash guide、KV CPU Offload、UCM、KV Pool 的 URL、版本和日期。
- 建立 `benchmarks/deepseek_v4_flash/` 下的 model object registry、P5 readiness card 和固定输出 smoke workload。
- 明确 official source checkpoint、ModelScope W8A8-MTP、非官方转换/PoC 候选之间的关系。
- 只在用户提供服务器模型路径和目标 runtime 后，才重写 `通信模块/docs/developer-to-server.md`。

## 4. P6：DeepSeek-V4-Flash 单机八卡 baseline

### P6.1 环境准备

- 确认 CANN / driver / torch-npu / vLLM-Ascend / container / conda 版本。
- 确认 8 张 NPU health、HBM、HCCL/HCCS、CPU NUMA、DRAM、NVMe。
- 准备服务器上的 `DeepSeek-V4-Flash-w8a8-mtp` 权重路径。
- 生成 `hardware_snapshot.yaml`。
- 固定 experiment card 后再下发服务器任务。

### P6.2 最小在线 serving

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

### P6.3 受控 A/B

| A/B | 控制变量 | 判读 |
| --- | --- | --- |
| prefix on/off | `--enable-prefix-caching` | TTFT、device task、KV usage、prefix stats |
| MTP on/off | `--speculative-config` | TPOT、acceptance、tail |
| chunked prefill on/off | `--enable-chunked-prefill` | TTFT、prefill device tasks |
| max_model_len | 32K/128K/384K | HBM/KV/tail risk |
| max_num_seqs | 1/4/8/16 | continuous batching behavior |

## 5. P7：单卡/双卡极限实验

单卡/双卡只做边界研究，不写成 official DeepSeek-V4-Flash 可部署承诺。

### 单卡目标

- 跑通小模型 4K/8K/16K trace。
- 跑通中型 MoE expert trace。
- 用 DeepSeek 子图、低比特/裁剪变体或模拟 expert pool 验证容量分层。
- 记录为什么 full official DeepSeek-V4-Flash W8A8-MTP 不 fit。

### 双卡目标

- 验证 2-rank TP/EP 下 runtime 和 trace。
- 测 rank 间通信、HBM 分布、KV placement。
- 作为 simulator-only full model 或低资源校准点。

## 6. P8：AK 协同技术注入与对照实验

### P8.1 KV / Prefix 分层实验

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

优先顺序：

- Prefix cache / KV CPU Offload。
- UCM local DRAM hierarchy。
- Mooncake/KV Pool later。SSD 只允许做 cold tier，不进入逐 token decode 热路径。

### P8.2 MoE Expert 分层实验

在中型 MoE、DeepSeek 子图或 P6/P7 可观测 expert trace 上先跑：

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

静态 hotset 先计算 top-N 常驻命中率曲线，再进入 warm/cold tier。SSD cold expert 只做离线或提前预取，不允许在 decode step 发生随机小块读取。

## 7. P9：规格反推

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
