# GLM-5.2 单卡一体机：950PR Lite 的 E 级分层验证口径

## 页面标题

**950PR Lite：E 级 10/30/60 分层验证锚点，而非 A1 保守最低加载配置**

## 一句话主张

84GB Bailu、384GB DDR5、2TB SSD 可以支撑 **E 级极限分层验证**：HBM / DRAM / SSD 按 **10% / 30% / 60% routed experts** 承接热、温、冷专家；但它不满足 A1 的 **1TB DRAM + 4TB NVMe** 保守最低加载口径，性能必须用 expert hit/miss、预取命中、SSD P95/P99 和 TPOT trace 证明。

## 三块版式

1. **顶部硬件锚点卡片**：84GB Bailu、384GB DDR5、2TB SSD。
2. **左侧横向差距表**：把 A1、A0、E 级放到同一张表里比较。
3. **右侧 GLM-5.2 公式与 E 级风险**：从 A 档通用估算改成 E 级 10/30/60 计算逻辑。

## 顶部：当前硬件锚点

| 锚点 | 当前规格 | 对 E 级的含义 |
|---|---|---|
| 热层 | **84GB Bailu**，NPU-Bailu **1TB/s** | E 级 HBM 规划约 **63-78GB**，当前勉强覆盖 |
| 温层 | **384GB DDR5**，CPU-DDR5 **228GB/s** | E 级 DRAM 规划约 **249-419GB**，当前落入中高区间 |
| 冷层 | **512GB x 4 SSD = 2TB**，CPU-SSD **40GB/s** | 可放 60% cold routed experts 与 checkpoint，但要看随机 I/O 和 P95/P99 |

## 左侧：横向差距表，把 E 级一起对比

| 维度 | 当前 950PR Lite | A1 保守最低加载 | A0 极限加载 | E 级 10/30/60 | 风险点 |
|---|---|---|---|---|---|
| HBM / 热层 | **84GB Bailu**，1TB/s | 64-96GB HBM；只承接 hot working set | 64-96GB HBM；少量 hot experts | 10% routed experts = **36.2GB**；加公共层/KV/workspace 后约 **63-78GB** | 84GB 只适合 32K 以内验证；1M 或大 prefetch buffer 会挤压热专家 |
| DRAM / 温层 | **384GB DDR5**，228GB/s | **1TB**；全量低比特权重尽量 resident / warm | **512-768GB**；只保留 warm set / page cache | 30% routed experts = **108.7GB**；加 metadata/staging/page cache 后约 **249-419GB** | 384GB 不能保留全量 395-465GB 工程权重；必须压低 runtime 与 page cache |
| SSD / 冷层 | **2TB SSD**，40GB/s | **4TB NVMe**，聚合读 >=14GB/s | 依赖 SSD cold expert / cold KV | 60% routed experts = **217.4GB**；另加 checkpoint、cold KV、trace/profile | 容量可做单版本验证；SSD 一旦进 token critical path，TPOT/P95/P99 会恶化 |
| CPU / 链路 | 鲲鹏 CPU；UB **200GB/s**；64 核口径 | 32-48 cores，PCIe Gen4/5 x16 | 调度、I/O、metadata、mmap/page cache | E 级更依赖 CPU 预测、预取、回流组织和 NPU-SSD 直通 | 必须 chunk/object 化预取；不能让 DDR/SSD 逐 token 阻塞供给 |
| 定位 | A+K 分层验证平台 | 最低能加载，基本生成更稳定 | 加载与少量 decode proof | **代表性极限容量压缩锚点** | 不能对外写成“GLM-5.2 单卡可用”或稳定交互速度 |

## 右侧：GLM-5.2 推理公式与 E 级性能风险

### 1. 模型规模底账

```text
GLM-5.2 = 744B-A40B MoE
sparse MoE 层 = 75
routed experts = 256 / layer
experts per token = 8
单 expert = 3 * 6144 * 2048 = 37.75M
全部 routed experts = 75 * 256 * 37.75M = 724.78B
active_core ≈ 39.15B
```

### 2. E 级容量拆分公式

```text
全部 routed experts INT4 裸容量 ≈ 362.4GB
HBM hot  = 362.4GB * 10% = 36.2GB
DRAM warm = 362.4GB * 30% = 108.7GB
SSD cold  = 362.4GB * 60% = 217.4GB
```

加工程项后的规划口径：

| 层级 | 裸容量 | 工程项 | 规划口径 |
|---|---:|---|---:|
| HBM 热层 | 36.2GB | non-routed/shared 约 9.2GB、32K KV 1.37-2.74GiB、workspace/prefetch 15-30GB | **63-78GB** |
| DRAM 温层 | 108.7GB | metadata/index 30-60GB、staging 40-80GB、page cache 50-120GB、系统/KV 20-50GB | **249-419GB** |
| SSD 冷层 | 217.4GB | checkpoint、cold KV/prefix、trace/profile、失败恢复余量 | **2TB 可验证，但余量不宽** |

### 3. E 级 decode 风险公式

```text
decode_TPOT_E_lower_bound
= active_INT4_bytes / HBM_bandwidth
 + routed_active_INT4_bytes * (p_warm / PCIe_or_UB_bandwidth)
 + routed_active_INT4_bytes * (p_cold / SSD_bandwidth)

active_INT4_bytes ≈ 39B * 0.5 byte = 19.5GB/token
routed_active_INT4_bytes ≈ 11.32GB/token
HBM bandwidth 取 1.2TB/s
PCIe/UB 有效带宽参考 40GB/s
SSD cold-tier 顺序带宽参考 14GB/s
```

关键解释：`10%/30%/60%` 是容量放置比例，不等于逐 token 命中比例；真正决定 TPOT 的是实际 `p_warm` 和 `p_cold`。

| E 级场景 | 计算口径 | 理想下界 | 解释 |
|---|---|---:|---|
| 热度/预取较好 | `p_warm=10%, p_cold=5%` | `16 + 28 + 40 ≈ 85ms/token`，约 **12 tok/s 理想上界** | 未计入 dequant、dispatch、同步和 page fault；不能承诺 |
| 按容量比例粗暴落入路径 | `p_warm=30%, p_cold=60%` | `16 + 85 + 485 ≈ 586ms/token`，约 **1.7 tok/s 理想上界** | 工程开销后可能低于 1 tok/s；这就是 E 级最大风险 |
| SSD 冷 miss 常态化 | `p_cold` 持续升高 | 秒级 stall | 只能算极慢 proof，不是正常 decode 路径 |

### 4. KV 公式只解释上下文压力，不是当前最大容量项

```text
KV ≈ B * S * 78 * (512 + 64) * bytes
   ≈ B * S * 78 * 576 * bytes
```

| 上下文 | BF16 KV | FP8 KV | 对 E 级的意义 |
|---|---:|---:|---|
| 32K x 1 | 2.74GiB | 1.37GiB | KV 可放入 HBM，但会挤压 hot expert 和 workspace |
| 128K x 1 | 10.97GiB | 5.48GiB | 明显压缩 prefetch buffer |
| 1M x 1 | 87.75GiB | 43.88GiB | 不建议在 84GB 热层上承诺稳定服务 |

## 底部总结结论

1. **当前 950PR Lite 是 E 级 10/30/60 热温冷分层验证锚点，不是 A1 保守最低加载配置。**
2. **E 级能把 DRAM 从 A1 的 615-1085GB 压到约 249-419GB，但代价是 60% routed experts 位于 SSD 冷层。**
3. **右侧公式必须按 E 级 `p_warm / p_cold` 风险讲清楚：如果 SSD cold miss 进入 token critical path，TPOT/P95/P99 会迅速恶化。**

## 页脚证据口径

- 当前硬件锚点：84GB Bailu + 384GB DDR5 + 512GB x 4 SSD；NPU-Bailu 1TB/s、UB 200GB/s、CPU-DDR5 228GB/s、CPU-SSD 40GB/s。
- GLM-5.2 计算口径：744B 总参数、约 39.15B active 参数、全部 routed experts INT4 裸容量约 362.4GB。
- E 级口径：HBM/DRAM/SSD = 10%/30%/60%，加工程项后 HBM 约 63-78GB、DRAM 约 249-419GB。
