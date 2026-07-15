我们在 Atlas 800T A2 八卡上测试 DeepSeek-V4-Flash W8A8-MTP 的 Prefix Cache，遇到了“缓存已开启、也被查询，但始终零命中”的问题。

### 测试环境

- 模型：DeepSeek-V4-Flash W8A8-MTP
- 硬件：Atlas 800T A2，8 卡
- 并行：TP8 + EP
- Runtime：
  - vLLM commit：`0decac0d96c42b49572498019f0a0e3600f50398`
  - vLLM-Ascend `0.22.1rc1` commit：`5f6faa0cb8830f667266f3b8121cd1383606f2a1`
- MTP 开启，`num_speculative_tokens=1`
- Chunked Prefill 开启
- Graph 模式：`FULL_DECODE_ONLY`
- `max_num_seqs=1`
- KV block size：128 tokens
- 唯一变量：是否增加 `--enable-prefix-caching`

### 测试方法

测试了 8 组长上下文：

- Context：4096、32768、65536、131072
- 共享前缀比例：50% 和 90%
- 每组先发送 1 个 prime 请求，再立即发送 3 个具有相同前缀的 follower 请求
- 每个请求输出固定 64 tokens
- Prefix Cache off/on 两轮使用完全相同的 request body 和 SHA-256
- 共享前缀按照 128-token block 对齐
- Prefix Cache off 固定先运行，on 后运行
- 总计 64 个请求：16 个 prime + 48 个 measured follower

### 实际结果

模型推理本身全部正常：

- 64/64 请求均 HTTP 200
- 输入、输出和流式 token 数都准确
- MTP 在两种模式下均正常工作
- health、queue、counter continuity 和 cleanup 都正常

但 Prefix Cache 开启后：

- 24/24 个 measured follower 都产生了正的 `prefix_cache_queries` 增量
- 说明运行时确实查询了 Prefix Cache
- 但 24/24 的 `prefix_cache_hits` 增量都是 0
- `prefix_cache_on_positive_hit_measured_count = 0/24`
- `prefix_cache_on_hit_delta_total = 0`

因此报告中的“40/64 successful”不是说有 24 个推理请求失败，而是：

> 24 个 Prefix Cache-on follower 推理均正常完成，但由于缓存命中数为零，不满足实验合同的 Prefix Cache 证据门，所以被标记为 failed。

表面性能上，Prefix Cache-on 相对 off 的 24 对请求平均为：

- TTFT：`-1.35%`
- TPOT：`-3.06%`
- E2EL：`-2.77%`
- 输出吞吐：`+2.89%`

但由于实际缓存命中为零，而且执行顺序固定为 off → on，这些差异只能看作运行顺序、热态或系统波动，不能证明 Prefix Cache 加速。

### 当前根因判断

我们的高置信假设是：

DeepSeek-V4-Flash 使用 hybrid KV 结构，同时存在压缩 attention KV 组和 sliding-window attention KV 组。当前 vLLM-Ascend 的 hybrid KV coordinator 需要不同 KV 组共同确认可复用的前缀长度；如果 sliding-window 组得到零命中，最终对外的共同命中长度可能被收缩为零。

固定版本源码中也有针对 DSV4 的注释，描述 SWA 零命中会令整体 prefix hit 变成零。同版本 A2 部署教程默认使用 `--no-enable-prefix-caching`。

不过，我们还没有在服务器上直接导出每个 KV group 的 spec、实际 block size 和 per-group hit length，因此这仍是高置信源码推断，不是已经完成的运行时根因证明。

### 想向专家请教的问题

1. 当前版本是否正式支持 DeepSeek-V4-Flash 的 hybrid KV Prefix Cache？
2. 在 MLA/压缩 attention 与 sliding-window attention 并存时，SWA 零命中导致整体零命中是否属于已知行为？
3. 是否需要特殊的 block size、KV group 对齐方式、调度参数或补丁，才能产生真实命中？
4. Prefix Cache 是否与 MTP、Chunked Prefill 或当前 graph 模式存在已知兼容性问题？
5. 应该通过什么日志或代码接口导出各 KV group 的 `KVCacheSpec`、有效 block size 和 per-group hit length？
6. 官方 A2 示例默认关闭 Prefix Cache，是因为当前不支持、收益有限，还是存在已知实现限制？
7. 如果完整模型路径无法命中，是否建议单独验证 prefill-only、PD 分离或不含 SWA 的执行路径？

本次最终结论是：**Prefix Cache 功能开关生效、查询发生、推理正常，但所有重复前缀请求均为零命中，暂时不能声称任何 Prefix Cache 加速效果。**





# 判定

你们的实验结论是正确的，而且可以进一步收敛：

> **在锁定的 `vLLM-Ascend v0.22.1rc1 / 5f6faa0` 上，这已经不只是“hybrid KV 可能导致零命中”的源码推断，而是与该版本之后合入的 DeepSeek‑V4‑Flash Prefix Cache 已知缺陷高度一致。**

`v0.22.1rc1` 于 **2026 年 6 月 30 日**发布；修复 DSV4+MTP 零命中的 PR #11107 于 **7 月 1 日**合入；修复 SWA 对齐单位问题的 PR #11383 于 **7 月 10 日**合入。因此你们当前镜像不包含这两项修复。截止 2026 年 7 月 15 日，GitHub 发布列表中最新的已发布版本仍是 `v0.22.1rc1`。([GitHub](https://github.com/vllm-project/vllm-ascend/releases))

最高概率的直接故障链是：

```text
DeepSeek-V4-Flash 多 KV group
    +
MTP / EAGLE group
    ↓
AscendHybridKVCacheCoordinator 没有把 use_eagle
传播给同一 attention group 中的所有 manager
    ↓
SWA 写入侧保留边界与读取侧 EAGLE lookahead/drop 语义不一致
    ↓
SWA group 返回 0 hit
    ↓
hybrid coordinator 对各组求共同可复用长度
    ↓
整体 prefix hit 被收缩为 0
```

这正是 #11107 的修复说明：当某个同组 manager 保持默认 `use_eagle=False` 时，SWA 写入尾部会比读取侧期望少一个 block，导致 SWA 永远无法命中，随后 “min-over-groups” 将整体命中率压成 0%。修复本身就是把 EAGLE 标记传播给同一 attention group 的所有 single-type managers。([GitHub](https://github.com/vllm-project/vllm-ascend/pull/11107/files))

不过，**仍然建议保留“运行时根因待 per-group 日志确认”这一句**。因为公开复现中还存在另外一种多组 hybrid 缓存故障：首先归零的是 MLA group，随后其他 SWA group 只是因为输入上限已经变成 0 而被动归零。也就是说，“任一组归零导致共同命中归零”已经可以确认，但“你们这次第一个归零的一定是 SWA”还需要日志证明。([GitHub](https://github.com/vllm-project/vllm/issues/42948))

------

## 1. 当前版本是否正式支持 DSV4-Flash hybrid KV Prefix Cache

需要拆成三个层次。

| 层次                                   | 判断                                                         |
| -------------------------------------- | ------------------------------------------------------------ |
| 配置入口                               | **支持**。`--enable-prefix-caching` 能被接受，缓存查询和 aggregate metrics 正常工作。 |
| A2 + DSV4 + hybrid KV + MTP 的正确命中 | **在你们锁定版本上不能视为完整支持**，因为存在版本匹配的零命中缺陷。 |
| 当前主线状态                           | 已合入若干修复，但仍处于持续完善阶段；DSV4 hybrid 的 partial-group/partial-hit 在 vLLM-Ascend RFC 中仍标为 `TBD`。 |

精确版本的 A2 单机教程默认带有：

```text
--no-enable-prefix-caching
--block-size 128
MTP num_speculative_tokens=1
FULL_DECODE_ONLY
```

同一文档又说明，删除 `--no-enable-prefix-caching` 即可启用。这只能证明**开关路径存在**，不能证明该组合经过了正确命中验证。([GitHub](https://github.com/vllm-project/vllm-ascend/blob/5f6faa0cb8830f667266f3b8121cd1383606f2a1/docs/source/tutorials/models/DeepSeek-V4-Flash.md))

因此建议对问题 1 的正式回答写成：

> **当前版本具备 Prefix Cache 的配置和查询路径，但 DeepSeek‑V4‑Flash hybrid KV + MTP 在 v0.22.1rc1 上存在已知正确性缺陷，不应视为生产可用的完整支持。**

------

## 2. SWA 零命中导致整体零命中是否属于已知行为

**是已知问题，但应称为“已知缺陷”，而不是架构上预期的正常行为。**

你们锁定版本的 Ascend coordinator 源码中已经直接写有注释：DeepSeek‑V4 的 SWA `hit_length` 为 0，会使 decode node 无法得到 Prefix Cache hit。([GitHub](https://github.com/vllm-project/vllm-ascend/blob/5f6faa0cb8830f667266f3b8121cd1383606f2a1/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py))

同时，coordinator 的算法确实是共同前缀的固定点求交：

1. 先计算所有 attention group 的有效 block size；
2. 求 `lcm_block_size`；
3. 依次询问每个 group 的最长命中；
4. 任何 group 都可以缩短当前候选长度；
5. 候选值单调下降，最低为 0；
6. 某组返回 0 后，最终共同命中就是 0。([GitHub](https://github.com/vllm-project/vllm-ascend/blob/5f6faa0cb8830f667266f3b8121cd1383606f2a1/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py))

所以你们的核心机制判断成立：

> **当前实现不是“MLA 命中多少就复用多少、SWA 单独重算”，而是要求不同 KV group 对共同可复用长度达成一致；任一参与求交的 group 返回 0，都可能把最终命中压为 0。**

长期方向是 per-group partial hit，但当前 RFC 对 DeepSeek V4 的 vLLM-Ascend partial hit 仍标记为 `TBD`。([GitHub](https://github.com/vllm-project/vllm-ascend/issues/10517))

------

## 3. 是否需要特殊 block size、对齐方式或补丁

### 首要动作：补 #11107 的语义修复

在你们的版本上，最值得优先验证的是这一段：

```python
# 放在 eagle_attn_group_indices 计算完成之后
for idx in self.eagle_attn_group_indices:
    for gid in self.attention_groups[idx][1]:
        self.single_type_managers[gid].use_eagle = True
```

它就是合入 #11107 的核心修复。([GitHub](https://github.com/vllm-project/vllm-ascend/pull/11107/files))

建议在单独诊断分支中手工移植这三行并补测试，**不要直接无检查地 cherry-pick 整个 v0.23 PR**：你们的 `0.22.1`路径仍使用 `use_eagle` 参数，而后续版本部分接口已经改为 `drop_eagle_block`，存在 API 差异。([GitHub](https://github.com/vllm-project/vllm-ascend/blob/5f6faa0cb8830f667266f3b8121cd1383606f2a1/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py))

### Block size 128 本身不是错误

\#11107 的通过测试使用的正是：

- DeepSeek‑V4‑Flash W8A8
- TP8 + EP
- MTP `num_speculative_tokens=1`
- `block-size=128`
- `FULL_DECODE_ONLY`
- Prefix Cache 开启

修复后可以正常命中。因此，不需要为了获得第一个真实命中而先放弃 128。([GitHub](https://github.com/vllm-project/vllm-ascend/pull/11107))

32、64、128 都是后来支持的 compressor block size。较小 block size 可以把 compressed KV 的匹配粒度最多缩小约 4 倍，但它解决的是**命中粒度和浪费问题**，不能修复 MTP/SWA 写读不一致导致的结构性零命中。([GitHub](https://github.com/vllm-project/vllm-ascend/issues/10517))

### 128-token 对齐只是必要条件，不是充分条件

Ascend coordinator 中的有效 block size 是：

```text
effective_block_size
= spec.block_size
× DCP world size
× PCP world size
× compress_ratio
```

随后所有 group 的有效 block size 再求 LCM。源码甚至专门注释 compressed model 可能使用约 16K 的 alignment。([GitHub](https://github.com/vllm-project/vllm-ascend/blob/5f6faa0cb8830f667266f3b8121cd1383606f2a1/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py))

所以你们真正需要满足的是：

```text
shared_prefix_tokens % coordinator.lcm_block_size == 0
```

而不是只满足：

```text
shared_prefix_tokens % 128 == 0
```

这不太可能解释你们在 64K、128K 长前缀上仍然全部为零，但会影响修复后可观察到的命中长度。

### 检查 retention interval

先执行：

```bash
env | grep '^VLLM_PREFIX_CACHE_RETENTION_INTERVAL=' || echo UNSET
```

如果该变量大于 0，还需要考虑 #11383。该问题是 Ascend SWA 把 physical slots、token 数和 `alignment_tokens` 混用了，修复后统一使用 coordinator 的真实 `lcm_block_size`；DeepSeek‑V4‑Flash、MTP=1 的验证中，数据集命中率从 33% 提升到 86%。该修复只在 selective retention 路径启用时改变行为。([GitHub](https://github.com/vllm-project/vllm-ascend/pull/11383))

对 `v0.22.1`，#11383 不能只移植一行，因为你们版本的 manager 明确还不接收 `scheduler_block_size`。([GitHub](https://github.com/vllm-project/vllm-ascend/blob/5f6faa0cb8830f667266f3b8121cd1383606f2a1/vllm_ascend/patch/platform/patch_kv_cache_coordinator.py))

------

## 4. MTP、Chunked Prefill 和 Graph 模式的兼容性判断

| 组件                 | 判断                                                         |
| -------------------- | ------------------------------------------------------------ |
| **MTP**              | 与你们现象存在直接、版本匹配的已知缺陷，是第一排查项。       |
| **Chunked Prefill**  | 不是充分根因。已有公开复现在关闭 Chunked Prefill、关闭 MTP、关闭异步调度后，完全相同的串行请求仍然是 0 hit。 |
| **FULL_DECODE_ONLY** | 目前没有证据表明它会必然导致零命中。官方 A2 配置和 #11107 修复验证均使用该模式。 |
| **TP8 + EP**         | #11107 的验证配置即为 TP8 + EP，因此并行方式本身不是必然阻断项。 |
| **max_num_seqs=1**   | 是合理的隔离条件，减少并发淘汰和 batch 内时序干扰，不需要优先修改。 |

公开的无 MTP 复现中，Prefix Cache 开关和 queries 都正常，hits 始终为 0；关闭 Chunked Prefill 后问题仍存在。这说明 #11107 很可能解释你们当前的 MTP 场景，但 hybrid 多组路径还存在其他独立缺陷，不能把“MTP 关闭后仍为 0”直接解释成测试错误。([GitHub](https://github.com/vllm-project/vllm-ascend/issues/10710))

因此建议的兼容性结论是：

> **MTP 是当前版本的明确风险项；Chunked Prefill 和 FULL_DECODE_ONLY 适合作为 A/B 变量，但不是已有证据支持的首要根因。**

------

## 5. 如何导出各 KV group 的 spec、有效 block size 和 per-group hit length

当前 aggregate 指标只能告诉你“查了多少、最终命中了多少”，不能识别是哪一组首先归零。最直接的观测点是：

```text
vllm_ascend/patch/platform/patch_kv_cache_coordinator.py
```

### 建议在 `verify_and_split_kv_cache_groups()` 末尾加入

```python
import logging
import os

logger = logging.getLogger("vllm.kvdbg")
_KVDBG = os.getenv("VLLM_KV_CACHE_DEBUG", "0") == "1"
```

在计算完 `self.lcm_block_size` 后：

```python
if _KVDBG:
    logger.warning(
        "KVDBG_CONFIG hash_block=%s lcm=%s eagle_groups=%s "
        "eagle_attn_groups=%s",
        self.hash_block_size,
        self.lcm_block_size,
        sorted(self.eagle_group_ids),
        sorted(self.eagle_attn_group_indices),
    )

    for gid, group in enumerate(self.kv_cache_config.kv_cache_groups):
        spec = group.kv_cache_spec
        manager = self.single_type_managers[gid]

        logger.warning(
            "KVDBG_GROUP gid=%d layers=%s is_eagle=%s "
            "manager=%s manager.use_eagle=%s "
            "spec=%s block=%s effective_block=%s "
            "compress_ratio=%s sliding_window=%s "
            "storage_block=%s alignment=%s",
            gid,
            getattr(group, "layer_names", None),
            getattr(group, "is_eagle_group", None),
            type(manager).__name__,
            getattr(manager, "use_eagle", None),
            type(spec).__name__,
            getattr(spec, "block_size", None),
            self._get_effective_block_size(spec),
            getattr(spec, "compress_ratio", None),
            getattr(spec, "sliding_window", None),
            getattr(spec, "storage_block_size", None),
            getattr(spec, "alignment", None),
        )

    for idx, (spec, gids, manager_cls) in enumerate(self.attention_groups):
        logger.warning(
            "KVDBG_ATTN_GROUP idx=%d gids=%s spec=%s manager_cls=%s "
            "effective_block=%d",
            idx,
            gids,
            type(spec).__name__,
            manager_cls.__name__,
            self._get_effective_block_size(spec),
        )
```

### 在 `find_longest_cache_hit()` 中，每次 manager 返回后加入

放在 `_new_hit_length` 计算之后：

```python
if _KVDBG:
    logger.warning(
        "KVDBG_LOOKUP idx=%d gids=%s spec=%s "
        "candidate_in=%d max_in=%d "
        "use_eagle=%s manager_eagle=%s "
        "block_counts=%s effective_block=%d group_hit=%d",
        idx,
        group_ids,
        type(spec).__name__,
        curr_hit_length,
        _max_length,
        use_eagle,
        [
            getattr(self.single_type_managers[gid], "use_eagle", None)
            for gid in group_ids
        ],
        [len(blocks) for blocks in hit_blocks],
        effective_block_size,
        _new_hit_length,
    )
```

返回前再加：

```python
if _KVDBG:
    logger.warning(
        "KVDBG_RESULT requested_max=%d final_hit=%d lcm=%d",
        max_cache_hit_length,
        hit_length,
        self.lcm_block_size,
    )
```

启动：

```bash
export VLLM_KV_CACHE_DEBUG=1
export VLLM_LOGGING_LEVEL=INFO
```

### 你们要观察的决定性证据

理想日志应该能直接回答：

```text
manager.use_eagle 是否在同一 attention group 内全部为 True？
哪个 group 第一个把 candidate 从正数压成 0？
该组是 MLAAttentionSpec 还是 SlidingWindowMLASpec？
每组 effective_block_size 是多少？
最终 lcm_block_size 是多少？
```

具体判定：

```text
SWA: candidate_in > 0, group_hit = 0
    → 支持你们当前 SWA 根因

MLA: candidate_in > 0, group_hit = 0
    → 优先调查 hash entry / block reassignment / allocator 路径

所有 group 都有正 hit，但 final_hit = 0
    → 调查 LCM、EAGLE 尾块和截断逻辑

同组 manager.use_eagle 出现 [True, False, ...]
    → 直接证明 #11107
```

------

## 6. 为什么官方 A2 示例默认关闭 Prefix Cache

官方文档没有明确写出内部原因，因此不能把某一种解释表述成官方结论。

但从外部证据判断，**“当前实现限制和验证成熟度不足”明显比“单纯收益有限”更符合事实**：

1. A2 默认组合关闭 Prefix Cache；
2. 文档仅说明删除参数即可打开，没有给出 hit-rate 验收数据；
3. 该版本发布后一天就合入了 DSV4+MTP 0% 命中修复；
4. 十天后又合入了 SWA alignment 修复；
5. 还有直接针对 `v0.22.1rc1` 的回归报告：相同配置在 `v0.21.0rc1` 能命中，升级后无法命中。([GitHub](https://github.com/vllm-project/vllm-ascend/blob/5f6faa0cb8830f667266f3b8121cd1383606f2a1/docs/source/tutorials/models/DeepSeek-V4-Flash.md))

因此建议回答专家时使用：

> **官方教程没有披露默认关闭的具体决策原因；结合后续修复和回归报告，更可能是该组合当时尚未达到稳定验证状态，而不能简单解释为收益有限。**

------

## 7. 是否建议验证 prefill-only、PD 或不含 SWA 的路径

建议，但按以下顺序进行。

| 运行 | 改动                                              | 判定价值                                                     |
| ---- | ------------------------------------------------- | ------------------------------------------------------------ |
| R0   | 当前镜像，增加 per-group 日志                     | 确定第一个归零的 group 和真实 LCM。                          |
| R1   | 当前镜像，MTP off、Chunked Prefill off、eager     | 隔离 MTP、chunking 和 graph；若仍为 0，转向非 MTP hybrid 故障。 |
| R2   | 只移植 #11107 核心修复，恢复 MTP=1，其他保持原样  | 最有价值的根因验证。若由 0 变为正命中，基本完成闭环。        |
| R3   | 如 retention interval > 0，再移植 #11383 语义修复 | 验证 SWA 对齐和命中率损失。                                  |
| R4   | 修复后测试 32/64/128，并将共享前缀对齐到实际 LCM  | 测粒度和收益，不再测基本正确性。                             |
| R5   | 同一机器运行一个无 SWA 的普通 attention 模型      | 验证 A2 上通用 Prefix Cache、hash、block pool 和 metrics 路径。 |
| R6   | DSV4 prefill-only / P 节点                        | 验证 P 侧建立与查询，但不能代替完整本地路径证明。            |
| R7   | PD 分离                                           | 用于后续系统验证，不建议作为当前零命中的首要绕过方案。       |

PD 不是天然解决方案。公开 A2 报告中，PDD Prefix Cache hit 大部分仍为 0、最高约 3%，而单节点约 16%，说明 PD 又会引入 connector、远端状态和 group 对齐问题。([GitHub](https://github.com/vllm-project/vllm-ascend/issues/10365))

------

## 建议的实验通过门

只有同时满足以下条件，才进入性能比较：

```text
1. follower prefix_cache_queries_delta > 0
2. follower prefix_cache_hits_delta > 0
3. 每个参与共同求交的 KV group 都有可解释的非零 hit
4. final_hit_length > 0
5. final_hit_length 与 floor(shared_prefix / lcm) × lcm 基本一致
   允许扣除明确记录的 MTP/EAGLE 尾块
```

随后再做：

- on/off 顺序随机化或 ABBA；
- 每组独立冷启动；
- 固定热身请求；
- 报告 hit token 数和命中比例；
- 只比较实际命中请求的 TTFT；
- TPOT 和输出吞吐作为副指标，因为 Prefix Cache 的主要直接收益应体现在 prefill/TTFT。

------

## 最终报告口径

建议将 “40/64 successful” 拆成三个指标，避免误解：

```text
Inference functional success:       64 / 64
Experiment-contract pass:           40 / 64
Cache-on follower evidence pass:     0 / 24
```

最终结论可升级为：

> **DeepSeek‑V4‑Flash W8A8‑MTP 在 Atlas 800T A2 八卡上的 Prefix Cache 配置入口已经生效，所有请求均正常推理，且 follower 请求确实执行了缓存查询；但锁定版本 `vLLM-Ascend v0.22.1rc1` 位于已知 DSV4+MTP Prefix Cache 零命中修复之前，24/24 个 measured follower 均未产生任何实际命中。源码和后续修复表明，hybrid KV group 的共同命中求交以及 MTP/EAGLE 与 SWA 写读边界不一致可导致整体命中被压为零。当前性能差异没有缓存命中证据支持，不能归因于 Prefix Cache。下一步应先导出 per-group spec、有效 block size、manager EAGLE 状态及 per-group hit length，并以 #11107 的语义修复完成运行时根因闭环。**