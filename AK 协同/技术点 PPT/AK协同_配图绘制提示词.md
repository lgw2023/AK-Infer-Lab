# AK 协同单页 PPT 配图绘制提示词

## 总体建议

这页不要再直接贴论文截图或旧 PPT 截图。建议重新画成统一风格的矢量技术示意图，优先做 **1 张主图 + 3 个小型问题图标**。

交付格式建议：
- `SVG` 或可编辑 PPT 矢量源文件，另导出 `PNG`，透明背景或纯白背景。
- 主图尺寸：16:9，或横向 2.2:1，方便放在 PPT 中部。
- 小图尺寸：1:1 或 4:3，方便放在“当前问题挑战”三行旁边。
- 字体：中文用微软雅黑 / 思源黑体，英文与数字用 Aptos / Calibri。
- 风格：企业技术架构图，不要科技海报风；白底、细线、清晰箭头、少量强调色。
- 禁忌：不要 3D 芯片渲染图、不要炫光背景、不要堆论文原图、不要 logo、水印、人物、服务器照片。

建议配色：
- 热路径 / 近端 HBM / 主计算：红橙色 `#D9482B`
- 温路径 / CPU DDR / DUMA：青绿色 `#0F7F7A`
- 冷路径 / SSD / 远端状态：紫色 `#6E45B8`
- 控制面 / 调度 / 仿真：深蓝色 `#1F4E79`
- 背景与容器：白色、浅灰 `#F6F8FA`

## 主图提示词：A+K 异构推理容量分层与状态协同主图

画一张面向技术汇报 PPT 的矢量架构图，主题是：

**“A+K 协同异构推理：Ascend NPU 专注热计算主路径，Kunpeng CPU 与分级内存承接状态与数据底座”**

图中从左到右展示一次大模型推理请求的执行链路：

1. 左侧是用户请求 / Agent 任务入口，包含三个小入口标签：
   - AI Coding Agent
   - 办公助手 Agent
   - 多模态生成
2. 中间是主计算区，画一个大的芯片框，标签为：
   - `Ascend NPU / HBM`
   - 内部标注：`Attention / FFN / MoE hot experts / KV hot / activation workspace`
   - 这一区域用红橙色表示“热路径”，强调 NPU 负责高频、稠密、关键路径计算。
3. 右侧或下方是 CPU 与温状态区，画一个 CPU 框，标签为：
   - `Kunpeng CPU / DDR / DUMA`
   - 内部标注：`scheduler / router / expert index / state filter / prefetch / fallback`
   - 用青绿色表示“温路径”，强调 CPU 承接路由、索引、状态筛选、预取和低频补算。
4. 最下方是冷存储区，画成 SSD / NVMe / local object store，标签为：
   - `SSD / NVMe cold tier`
   - 内部标注：`cold experts / cold KV / prefix snapshots / checkpoints`
   - 用紫色表示“冷路径”。
5. 在 NPU、CPU、SSD 之间画三类箭头：
   - 红橙色粗实线：`Hot compute path: token -> NPU/HBM -> decode`
   - 青绿色实线：`Warm prefetch path: CPU predicts and warms expert/KV before use`
   - 紫色虚线：`Cold recovery path: SSD/remote state recovery, may hit TTFT/TPOT/P99`
6. 图中央增加一个统一状态对象账本，标签为：
   - `State Object Ledger`
   - 下方小字：`expert / KV / prefix / weight / activation / context`
   - 再下方用小字段表示：`tier / hotness / next_use / load_cost / recompute_cost`
7. 在右下角画一个闭环小模块，标签为：
   - `Profiler + Simulator`
   - 输入：`expert hit rate / KV reuse / recovery latency / bus bandwidth / power`
   - 输出：`capacity cliff / latency boundary / hardware spec recommendation`
   - 用箭头回连到 NPU、CPU、DDR、SSD，表示通过观测和仿真反推硬件规格。

图中必须明确表达三层状态分层：
- `HBM: hot weights, hot experts, hot KV`
- `DDR / DUMA: warm experts, warm KV, prefetch buffer`
- `SSD / NVMe: cold experts, cold KV, checkpoints`

图中必须出现三个问题点 callout：
- `expert miss -> decode stall`
- `cold KV recovery -> TTFT / TPOT jitter`
- `CPU-NPU sync / data movement may cancel gains`

画面要求：
- 16:9 横向构图，白底。
- 标题不要太大，主体图占 75% 以上面积。
- 所有文字必须可读，不要把论文截图嵌进去。
- 箭头不要交叉太多，优先用 swimlane 或分层布局。
- 最终效果像严肃的系统架构图，适合华为/企业技术汇报，不像营销海报。

## 问题图提示词 1：专家权重与 KV 状态回取导致尾延迟

画一张小型技术示意图，主题是：

**“近端容量不足时，专家权重与 KV 状态回取进入解码关键路径”**

构图：
- 左侧画 `Decode step t` 的 token 流水线，包含 `Attention`、`Router`、`MoE Expert`、`Sampling` 四个小方块。
- 中间画 NPU/HBM，标签：`HBM near memory`，内部有少量 `hot experts` 和 `hot KV`。
- 下方画 DDR/DUMA，标签：`warm tier`，内部有 `warm experts`、`warm KV`。
- 最下方画 SSD/NVMe，标签：`cold tier`，内部有 `cold experts`、`prefix snapshots`、`cold KV`。
- 从 DDR/SSD 向 HBM 画回取箭头，标注：
  - `expert miss`
  - `KV miss`
  - `cold recovery`
- 在右侧画一个小延迟曲线，横轴为 token step，纵轴为 latency，曲线出现红色尖峰，标注：
  - `TTFT`
  - `TPOT`
  - `P95 / P99 spike`

视觉要求：
- 小图要能放进 PPT 左侧问题区，信息要少而清楚。
- 用红色强调“进入主链路的阻塞”，用紫色表示冷路径。
- 不要出现复杂论文图，不要出现密集公式。

## 问题图提示词 2：多类状态同时挤压近端内存

画一张小型技术示意图，主题是：

**“长上下文下，权重、专家、KV、Prefix、激活和工作区共同争抢 HBM”**

构图：
- 画一个大容器 `HBM capacity`，容器顶部显示容量条，接近满载。
- 容器中用不同颜色的小块表示：
  - `weights`
  - `MoE experts`
  - `KV cache`
  - `Prefix cache`
  - `activation`
  - `workspace`
- 容器外有三个输入压力源：
  - `long context`
  - `multi-turn session`
  - `tool / code repository state`
- 当容量满时，几个对象被挤到 `DDR / SSD`，旁边标注：
  - `evict`
  - `reload`
  - `recompute`
- 右下角加一个风险标签：
  - `capacity cliff -> jitter`

视觉要求：
- 更像“容量水位图 + 对象块迁移”，不要画成普通饼图。
- 色彩与主图一致：HBM 红橙，DDR 青绿，SSD 紫色。
- 文字少，强调容量挤压和状态迁移。

## 问题图提示词 3：CPU 参与边界不清会抵消收益

画一张小型技术示意图，主题是：

**“CPU 不是替代 NPU，而是承接冷、短、稀疏、状态相关子路径；边界不清会被同步和搬运抵消收益”**

构图：
- 画两条横向 swimlane：
  - 上方：`NPU hot path`
  - 下方：`CPU warm / control path`
- NPU lane 中放：`dense attention`、`FFN`、`hot expert compute`。
- CPU lane 中放：`routing`、`index lookup`、`state filter`、`prefetch`、`fallback compute`。
- 两条 lane 之间画少量同步点，标注：
  - `sync`
  - `DMA / PCIe / UB`
- 在同步点过多的位置画红色警示：
  - `too much interaction -> gain cancelled`
- 在合理分工处画绿色标注：
  - `overlap prefetch with NPU compute`

视觉要求：
- 图要清楚表达“CPU 做辅助路径，不抢主算”。
- 不要让 CPU 和 NPU 看起来是对等替代关系。
- 强调阶段边界、重叠执行、同步成本。

## 解决方案图提示词：四项关键技术闭环

画一张可以放在 PPT 右侧的技术路线图，主题是：

**“从状态对象治理到系统仿真反推的 A+K 协同闭环”**

构图采用四段流程，从上到下或从左到右均可：

1. `Expert tiering`
   - 图标：多个 expert block 分布在 HBM / DDR / SSD。
   - 关键词：`hot resident`、`warm prefetch`、`cold restore`
2. `KV / Prefix / Context tiering`
   - 图标：上下文片段和 KV block 被标上 hot/warm/cold。
   - 关键词：`reuse`、`compress`、`reload`、`recompute`
3. `Stage-level CPU-NPU collaboration`
   - 图标：CPU lane 与 NPU lane 交错执行。
   - 关键词：`router`、`index`、`prefetch`、`fallback`
4. `Profiling + simulation + spec reverse inference`
   - 图标：监控曲线进入仿真器，输出硬件规格旋钮。
   - 关键词：`CPU cores`、`DDR bandwidth`、`SSD I/O`、`UB link`、`HBM capacity`

四段之间用箭头连接，形成闭环：

`Observe -> Place -> Prefetch / Recover -> Execute -> Simulate -> Spec`

必须在图中显示最终输出：
- `capacity boundary`
- `latency boundary`
- `recommended hardware spec`

视觉要求：
- 不要用大段文字，用图标 + 关键词。
- 每一段最多 2 行标签。
- 使用统一颜色和线宽，避免像临时拼贴。

## 给设计师的一句话说明

这页的核心不是展示某篇论文，而是说明：

**大模型单卡一体机的瓶颈不是单纯算力，而是 MoE expert、KV、Prefix、activation 等状态对象在 HBM、DDR/DUMA、SSD 之间如何分层、预取、恢复和仿真反推。A+K 的价值是让 Ascend NPU 保持热计算连续执行，让 Kunpeng CPU 与分级内存承接状态管理和冷路径协同。**

