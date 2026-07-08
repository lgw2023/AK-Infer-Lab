# 09 DeepSeek-V4-Flash 专项计划

## 1. 专项目标

围绕 DeepSeek-V4-Flash 在 Ascend 上的两类场景建立完整实验闭环：

1. 单机八卡官方 W8A8-MTP 基准。
2. 单卡/双卡极限硬件边界与 AK 协同技术探索。

最终输出：模型推理性能、硬件链路画像、状态分层收益/反噬边界、专家分层收益/反噬边界，以及下一代硬件规格建议。

事实来源：
- 模型规格按 `docs/SOURCES_AND_BOUNDARIES.md` 中 DeepSeek Hugging Face model card 记录。
- Ascend 部署基线按 vLLM-Ascend DeepSeek-V4-Flash 教程记录。
- 本项目服务器是 Atlas 800T A2；官方 A2/A3 八卡口径需要在服务器侧做兼容性 smoke 后才能进入 benchmark。

## 2. 测试对象

后续至少保留两个 DeepSeek-V4-Flash 测试对象：

| 对象 | 当前本地状态 | 后续用途 | 边界 |
| --- | --- | --- | --- |
| `DeepSeek-V4-Flash-w8a8-mtp` | ModelScope 版本已下载到 `/Volumes/Elements/DeepSeek-V4-Flash-w8a8-mtp` | 八卡 Ascend official baseline 首选对象 | 本地路径不是服务器路径；服务器路径由用户拷贝后填入 |
| `deepseek-ai/DeepSeek-V4-Flash` | 官方 HF 版本正在 `/Volumes/Elements/DeepSeek-V4-Flash` 下载 | 来源 checkpoint、格式兼容性、转换/对照、P7 边界研究对象 | 未验证前不能写成 vLLM-Ascend `--quantization ascend` 可直接加载的 W8A8-MTP 形态 |

用户会自行把模型拷贝到服务器；本项目只在实验卡片中登记对象、来源、形态、server path 占位、预期 runtime 和边界。

## 3. 场景 A：八卡基准

### 目标

建立 DeepSeek-V4-Flash 在 Atlas 800 A2 / 800T A2 8×64GB 上的官方 Ascend 基准。首选对象为 `DeepSeek-V4-Flash-w8a8-mtp`。

### 必备配置

```text
model: DeepSeek-V4-Flash-w8a8-mtp
runtime: vLLM-Ascend
tp: 8
ep: enabled
quantization: ascend
prefix_cache: enabled
chunked_prefill: enabled
mtp: enabled first, then A/B
```

### 阶段

| 阶段 | 任务 | 验收 |
| --- | --- | --- |
| A0 | 权重和环境 readiness | 模型路径、版本、8卡、CANN、vLLM-Ascend 可见 |
| A1 | 单请求 4K+64 | HTTP 200、trace、server stats、msprof |
| A2 | 4/8/16 请求 mixed | fixed output、request-device join |
| A3 | prefix-cache A/B | on/off 同负载、固定输出、raw delta 可读 |
| A4 | MTP A/B | acceptance 与 TPOT/tail 可读 |
| A5 | 32K/128K/384K | HBM/KV/tail 风险曲线 |

注意：如果 A1/A2 需要降低上下文、关闭 MTP、关闭 prefix cache 或改变官方教程关键开关才能跑通，记录为 `degraded_smoke`，不要写成正式八卡基准。

## 4. 场景 B：单卡/双卡极限

### 目标

验证 64GB/128GB 近端容量下，DeepSeek-V4-Flash 或其等效压力组件为什么会失效，以及哪些 AK 技术可以改善容量边界。

### 方法

- 小模型：验证 trace、prefix、KV offload、profiler。
- 中型 MoE：验证 expert trace 和 hotset。
- DeepSeek 子图或 source checkpoint：验证模型局部算子、权重分片、KV shape、格式转换和 kernel/runtime 兼容性。
- Simulator：用 DeepSeek 全模型参数进行 what-if。

### 禁止误写

- 不写“单卡可跑官方 DeepSeek-V4-Flash”。
- 不写“SSD 可支撑逐 token 冷专家随机回取”。
- 不写“CPU 可替代 NPU 主算”。
- 不写“prefix hit rate 单次数字就是性能收益”。

## 5. AK 技术插入点

| 技术 | 插入阶段 | 先决条件 | 输出 |
| --- | --- | --- | --- |
| Prefix cache | P6/P8 | vLLM API baseline + fixed output | on/off controlled delta |
| KV CPU Offload | P8 | fixed output + request-device join | HBM freed vs H2D stall |
| UCM | P8 | KV object schema | DRAM/storage hierarchy report |
| Mooncake KV Pool | P8 后半段 | UCM 或 KV connector readiness | KV pool / SSD offload boundary |
| Expert trace | P7/P8 | 中型 MoE 或 DeepSeek 子图可跑 | hotset/miss/reuse report |
| Expert tiering | P8 | expert trace | HBM/DRAM/SSD tiering report |
| Simulator | P9 | microbench + trace | hardware sensitivity report |

## 6. 下一步任务建议

1. 先执行 P5：新增 `benchmarks/deepseek_v4_flash/` 文档目录和模型对象登记，不下发服务器任务。
2. 写 `deepseek_v4_flash_model_objects.yaml`，把 `DeepSeek-V4-Flash-w8a8-mtp` 与 `deepseek-ai/DeepSeek-V4-Flash` 分开登记。
3. 写 `p5_readiness_card.yaml`，以 W8A8-MTP 作为 P6 首选 baseline，并保留官方 HF checkpoint 的来源/转换/边界角色。
4. 新增 fixed-output workload plan：4K、8K、32K、128K 四档。
5. 等用户拷贝模型到服务器并填入 server path 后，再决定是否写新的 `developer-to-server.md`。
6. 在 MoE 中型模型上补 expert trace，避免直接在 DeepSeek 上盲目实现专家分层。
