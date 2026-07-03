import { useMemo, useState } from "react";
import {
  Activity,
  Boxes,
  Cable,
  Cpu,
  DatabaseZap,
  Filter,
  GitBranch,
  Layers3,
  MemoryStick,
  Network,
  Route,
  Search,
  Server,
  SlidersHorizontal,
} from "lucide-react";
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "@xyflow/react/dist/style.css";
import paperTopologyNotesMarkdown from "../../代表工作原文硬件拓扑映射精读笔记.md?raw";
import {
  akStages,
  glmComponents,
  glmModelFacts,
  glmTraceFields,
  hardwareEdges,
  hardwareLayers,
  hardwareNodes,
  simulatorModules,
  sourceDocument,
  stateObjects,
  works,
} from "./data";
import type { HardwareNode, PathType, WorkItem } from "./types";

type ViewId = "map" | "glm" | "layers" | "works" | "state" | "ak";

const tabs: Array<{ id: ViewId; label: string; icon: typeof Server }> = [
  { id: "map", label: "服务器硬件地图", icon: Server },
  { id: "glm", label: "GLM-5.2 推理流", icon: Network },
  { id: "layers", label: "L0-L11 层级矩阵", icon: Layers3 },
  { id: "works", label: "代表工作对照", icon: Boxes },
  { id: "state", label: "状态对象流", icon: Route },
  { id: "ak", label: "A+K 迁移与仿真", icon: Activity },
];

const pathTypeLabels: Record<PathType, string> = {
  hot: "热路径",
  warm: "温路径",
  cold: "冷路径",
  remote: "远端数据面",
  control: "控制面",
  observe: "观测/仿真",
};

const nodeIcons: Record<HardwareNode["group"], typeof Server> = {
  request: Route,
  runtime: SlidersHorizontal,
  accelerator: Cpu,
  memory: MemoryStick,
  host: Server,
  storage: DatabaseZap,
  fabric: Cable,
  observe: Activity,
};

const paperNoteHeadings: Record<string, string> = {
  neo: "NEO",
  flexinfer: "FlexInfer",
  "llm-npu": "llm.npu",
  ktransformers: "KTransformers",
  finemoe: "FineMoE",
  dali: "DALI",
  fluxmoe: "FluxMoE",
  mooncake: "Mooncake",
  "lmcache-ucm": "LMCache",
  bidaw: "Bidaw",
  solidattention: "SolidAttention",
  cacheslide: "CacheSlide",
  tutti: "Tutti",
  servegen: "ServeGen",
  profinfer: "ProfInfer",
  llmservingsim2: "LLMServingSim2.0",
  burstgpt: "BurstGPT",
};

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function extractPaperNoteSection(markdown: string, heading: string) {
  const headingPattern = new RegExp(`^##\\s+\\d+\\.\\s+${escapeRegExp(heading)}\\s*$`, "m");
  const headingMatch = headingPattern.exec(markdown);
  if (!headingMatch || headingMatch.index === undefined) {
    return "";
  }

  const start = headingMatch.index;
  const afterHeading = start + headingMatch[0].length;
  const rest = markdown.slice(afterHeading);
  const nextHeading = /^##\s+\d+\.\s+/m.exec(rest);
  const end = nextHeading?.index === undefined ? markdown.length : afterHeading + nextHeading.index;
  return markdown.slice(start, end).trim();
}

function searchable(work: WorkItem) {
  return [
    work.name,
    work.category,
    work.hardwarePath.join(" "),
    work.topology.summary,
    work.topology.primaryPath.join(" "),
    work.topology.hardwareClaims.join(" "),
    work.topology.nonClaims,
    work.topology.criticalAssumption,
    work.topology.frontendHighlight,
    work.topology.frontendWarning,
    work.layers.join(" "),
    work.stateObjects.join(" "),
    work.solves,
    work.approach,
    work.boundary,
    work.akRelevance,
  ]
    .join(" ")
    .toLowerCase();
}

function useFilteredWorks(query: string, category: string) {
  return useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const rankWork = (work: WorkItem) => {
      if (normalized.length === 0) {
        return 0;
      }
      const name = work.name.toLowerCase();
      const id = work.id.toLowerCase();
      if (name === normalized || id === normalized) {
        return 0;
      }
      if (name.includes(normalized) || id.includes(normalized)) {
        return 1;
      }
      if (work.category.toLowerCase().includes(normalized)) {
        return 2;
      }
      return 3;
    };

    return works.filter((work) => {
      const categoryMatch = category === "全部" || work.category === category;
      const queryMatch = normalized.length === 0 || searchable(work).includes(normalized);
      return categoryMatch && queryMatch;
    }).sort((a, b) => rankWork(a) - rankWork(b));
  }, [category, query]);
}

function getActiveNodeIds(activeWork: WorkItem | undefined) {
  if (!activeWork) {
    return new Set<string>();
  }

  const ids = new Set<string>(activeWork.topology.highlightNodeIds);
  for (const edge of hardwareEdges) {
    if (edge.relatedWorks.includes(activeWork.id)) {
      ids.add(edge.from);
      ids.add(edge.to);
    }
  }

  if (ids.size > 0) {
    return ids;
  }

  const pathText = `${activeWork.hardwarePath.join(" ")} ${activeWork.topology.primaryPath.join(" ")}`.toLowerCase();
  for (const node of hardwareNodes) {
    const label = `${node.label} ${node.role}`.toLowerCase();
    if (
      pathText.includes("hbm") && node.id === "hbm" ||
      pathText.includes("ddr") && node.id === "ddr" ||
      pathText.includes("numa") && node.id === "ddr" ||
      pathText.includes("ssd") && node.id === "ssd" ||
      pathText.includes("rdma") && node.id === "nic" ||
      pathText.includes("nixl") && node.id === "nic" ||
      pathText.includes("pcie") && node.id === "dma" ||
      pathText.includes("dma") && node.id === "dma" ||
      pathText.includes("cpu") && node.id === "cpu" ||
      pathText.includes("gpu") && node.id === "accelerator" ||
      pathText.includes("npu") && node.id === "accelerator" ||
      activeWork.layers.some((layer) => node.linkedLayers.includes(layer)) && label.length > 0
    ) {
      ids.add(node.id);
    }
  }
  return ids;
}

function categoryOptions() {
  return ["全部", ...Array.from(new Set(works.map((work) => work.category)))];
}

function App() {
  const [activeView, setActiveView] = useState<ViewId>("map");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部");
  const [selectedWorkId, setSelectedWorkId] = useState("neo");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const filteredWorks = useFilteredWorks(query, category);
  const selectedWork = works.find((work) => work.id === selectedWorkId);
  const activeWork = selectedWork && filteredWorks.some((work) => work.id === selectedWork.id)
    ? selectedWork
    : filteredWorks[0] ?? selectedWork ?? works[0];
  const activeNode = selectedNodeId ? hardwareNodes.find((node) => node.id === selectedNodeId) : undefined;
  const activeNodeIds = getActiveNodeIds(activeWork);
  const categories = categoryOptions();

  const selectWork = (workId: string) => {
    setSelectedWorkId(workId);
    setSelectedNodeId(null);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="title-lockup">
          <div className="title-mark">
            <Server size={26} />
          </div>
          <div>
            <p className="eyebrow">A+K / Ascend + Kunpeng</p>
            <h1>小算力推理硬件对照地图</h1>
          </div>
        </div>
        <div className="source-pill">
          <GitBranch size={16} />
          <span>来源：{sourceDocument}</span>
        </div>
      </header>

      <section className="control-strip" aria-label="筛选控制">
        <label className="search-box">
          <Search size={18} />
          <input
            aria-label="搜索论文、硬件或层级"
            placeholder="搜索论文 / 硬件 / 层级，例如 NEO、Tutti、PCIe、SSD"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="category-filter" aria-label="方向筛选">
          <Filter size={18} />
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            {categories.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </section>

      <nav className="tabbar" aria-label="主视图">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              className={activeView === tab.id ? "tab active" : "tab"}
              onClick={() => setActiveView(tab.id)}
            >
              <Icon size={18} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>

      <section className={activeView === "glm" ? "workspace glm-workspace" : "workspace"}>
        {activeView !== "glm" && (
          <aside className="work-rail" aria-label="代表工作列表">
            <div className="rail-head">
              <span>{filteredWorks.length} 项</span>
              <strong>代表工作</strong>
            </div>
            <div className="work-list">
              {filteredWorks.map((work) => (
                <button
                  type="button"
                  key={work.id}
                  className={work.id === activeWork?.id ? "work-chip active" : "work-chip"}
                  onClick={() => selectWork(work.id)}
                >
                  <span>{work.name}</span>
                  <small>{work.layers.join(" / ")}</small>
                </button>
              ))}
              {filteredWorks.length === 0 && <p className="empty-state">没有匹配项。</p>}
            </div>
          </aside>
        )}

        <div className="view-surface">
          {activeView === "map" && (
            <HardwareMap
              activeWork={activeWork}
              activeNode={activeNode}
              activeNodeIds={activeNodeIds}
              onNodeSelect={setSelectedNodeId}
            />
          )}
          {activeView === "glm" && <GlmInferenceFlow />}
          {activeView === "layers" && <LayerMatrix activeWork={activeWork} onSelectWork={selectWork} />}
          {activeView === "works" && <WorksTable filteredWorks={filteredWorks} activeWork={activeWork} onSelectWork={selectWork} />}
          {activeView === "state" && <StateObjectFlow activeWork={activeWork} onSelectWork={selectWork} />}
          {activeView === "ak" && <AkRoadmap activeWork={activeWork} />}
        </div>
      </section>
    </main>
  );
}

function HardwareMap({
  activeWork,
  activeNode,
  activeNodeIds,
  onNodeSelect,
}: {
  activeWork: WorkItem | undefined;
  activeNode: HardwareNode | undefined;
  activeNodeIds: Set<string>;
  onNodeSelect: (nodeId: string) => void;
}) {
  const flowNodes = useMemo<Node[]>(() => {
    return hardwareNodes.map((node) => {
      const Icon = nodeIcons[node.group];
      const active = activeNodeIds.size === 0 || activeNodeIds.has(node.id);
      return {
        id: node.id,
        position: { x: node.x, y: node.y },
        data: {
          label: (
            <div className="board-node-inner">
              <Icon size={36} />
              <strong>{node.label}</strong>
              <small>{node.linkedLayers.join(" / ")}</small>
            </div>
          ),
        },
        className: `board-node ${node.group} ${active ? "is-active" : "is-muted"}`,
        draggable: false,
      };
    });
  }, [activeNodeIds]);

  const flowEdges = useMemo<Edge[]>(() => {
    return hardwareEdges.map((edge) => {
      const active = activeWork ? edge.relatedWorks.includes(activeWork.id) : true;
      return {
        id: `${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        animated: active,
        className: `board-edge edge-${edge.pathType} ${active ? "is-active" : "is-muted"}`,
        style: { strokeWidth: active ? 3 : 1.2 },
      };
    });
  }, [activeWork]);

  const activeEdgeLabels = useMemo(() => {
    return hardwareEdges.filter((edge) => !activeWork || edge.relatedWorks.includes(activeWork.id));
  }, [activeWork]);

  return (
    <div className="map-layout">
      <section className="board-panel" data-testid="board-map">
        <div className="panel-title-row">
          <div>
            <p className="eyebrow">Server board view</p>
            <h2>服务器硬件俯视拓扑</h2>
          </div>
          <div className="path-legend">
            {Object.entries(pathTypeLabels).map(([type, label]) => (
              <span key={type} className={`legend-dot ${type}`}>
                {label}
              </span>
            ))}
          </div>
        </div>
        <div className="reactflow-frame">
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            fitView
            fitViewOptions={{ padding: 0.02 }}
            minZoom={0.18}
            maxZoom={1.35}
            onNodeClick={(_, node) => onNodeSelect(node.id)}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1.2} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <div className="board-edge-label-strip" aria-label="当前高亮连线">
          {activeEdgeLabels.map((edge) => (
            <span key={`${edge.from}-${edge.to}`} className={`board-edge-label edge-label-chip ${edge.pathType}`}>
              {edge.label}
            </span>
          ))}
        </div>
        <TopologySummary activeWork={activeWork} />
      </section>
      <DetailPanel activeWork={activeWork} activeNode={activeNode} />
    </div>
  );
}

function TopologySummary({ activeWork }: { activeWork: WorkItem | undefined }) {
  if (!activeWork) {
    return null;
  }

  return (
    <section className="topology-summary" data-testid="topology-summary">
      <div className="summary-head">
        <div>
          <p className="eyebrow">Paper-calibrated view</p>
          <h3>{activeWork.name} 原文校准摘要</h3>
        </div>
        <span>{activeWork.category}</span>
      </div>
      <p className="summary-line">{activeWork.topology.summary}</p>
      <div className="path-strip" data-testid="primary-path">
        {activeWork.topology.primaryPath.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
      <div className="summary-grid">
        <DetailBlock title="原文明确涉及" text={activeWork.topology.hardwareClaims.join("；")} />
        <DetailBlock title="不要误读" text={activeWork.topology.nonClaims} />
        <DetailBlock title="关键假设" text={activeWork.topology.criticalAssumption} />
      </div>
      <PaperNotesMarkdown activeWork={activeWork} />
    </section>
  );
}

function PaperNotesMarkdown({ activeWork }: { activeWork: WorkItem }) {
  const sectionHeading = paperNoteHeadings[activeWork.id];
  const noteMarkdown = sectionHeading ? extractPaperNoteSection(paperTopologyNotesMarkdown, sectionHeading) : "";

  return (
    <section className="paper-notes-panel" data-testid="paper-notes-markdown">
      <div className="paper-notes-head">
        <div>
          <p className="eyebrow">Selected markdown notes</p>
          <h3>{activeWork.name} 原文精读小节</h3>
        </div>
        <span>{sectionHeading ? `来自 ## ${sectionHeading}` : "暂无独立小节"}</span>
      </div>
      {noteMarkdown ? (
        <div className="markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{noteMarkdown}</ReactMarkdown>
        </div>
      ) : (
        <div className="paper-note-empty">
          <h4>这份精读笔记里还没有该工作的独立小节</h4>
          <p>当前仍保留上方的校准摘要、主链路、边界和证据。待补齐该工作的一手文档精读后，这里会只显示它自己的 Markdown 小节。</p>
        </div>
      )}
    </section>
  );
}

function DetailPanel({ activeWork, activeNode }: { activeWork: WorkItem | undefined; activeNode: HardwareNode | undefined }) {
  const relatedWorks = activeNode
    ? works.filter((work) => work.layers.some((layer) => activeNode.linkedLayers.includes(layer)))
    : [];

  return (
    <aside className="detail-panel" aria-label="详情">
      {activeWork && (
        <>
          <p className="eyebrow">当前关注</p>
          <h2 data-testid="active-work-title">{activeWork.name}</h2>
          <p className="category-tag">{activeWork.category}</p>
          <DetailBlock title="原文一句话拓扑" text={activeWork.topology.summary} />
          <div className="detail-section">
            <h3>硬件路径</h3>
            <div className="chip-cloud" data-testid="highlighted-hardware">
              {activeWork.hardwarePath.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          </div>
          <div className="detail-section">
            <h3>主链路</h3>
            <div className="chip-cloud path-chips" data-testid="primary-path-detail">
              {activeWork.topology.primaryPath.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          </div>
          <div className="detail-section">
            <h3>涉及层级</h3>
            <div className="chip-cloud compact">
              {activeWork.layers.map((layer) => (
                <span key={layer}>{layer}</span>
              ))}
            </div>
          </div>
          <DetailBlock title="解决的问题" text={activeWork.solves} />
          <DetailBlock title="核心做法" text={activeWork.approach} />
          <DetailBlock title="收益边界" text={activeWork.boundary} />
          <DetailBlock title="不应暗示" text={activeWork.topology.nonClaims} />
          <DetailBlock title="前端高亮口径" text={activeWork.topology.frontendHighlight} />
          <DetailBlock title="前端警告" text={activeWork.topology.frontendWarning} />
          <DetailBlock title="A+K 迁移含义" text={activeWork.akRelevance} />
          <div className="detail-section">
            <h3>证据</h3>
            <ul className="evidence-list">
              {activeWork.evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </>
      )}
      {activeNode && (
        <div className="node-detail">
          <p className="eyebrow">硬件节点</p>
          <h2>{activeNode.label}</h2>
          <p>{activeNode.role}</p>
          <div className="chip-cloud compact">
            {activeNode.linkedLayers.map((layer) => (
              <span key={layer}>{layer}</span>
            ))}
          </div>
          <h3>相关工作</h3>
          <div className="mini-work-grid">
            {relatedWorks.slice(0, 8).map((work) => (
              <span key={work.id}>{work.name}</span>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}

function DetailBlock({ title, text }: { title: string; text: string }) {
  return (
    <div className="detail-section">
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

function GlmInferenceFlow() {
  const comparisonRows = [
    { scheme: "标准推理框架", target: "主干推理", cpuRole: "调度与控制", benefit: "实现成熟", risk: "HBM 压力大" },
    { scheme: "NEO", target: "Decode Attention + KV", cpuRole: "KV warm tier + 部分 attention", benefit: "扩大并发", risk: "CPU / DDRx 瓶颈" },
    { scheme: "KTransformers", target: "MoE Experts", cpuRole: "expert warm tier / prefetch / 部分 expert compute", benefit: "大模型放得下", risk: "expert miss / 回取延迟" },
  ];

  return (
    <section className="glm-infographic" data-testid="glm-infographic">
      <header className="glm-poster-title">
        <h2>GLM-5.2 推理计算流与 CPU/GPU/NPU 异构协同对比</h2>
        <p>标准推理框架 vs 文献中新方案（NEO / KTransformers）</p>
      </header>

      <section className="glm-model-pipeline" data-testid="glm-model-pipeline" aria-label="GLM-5.2 模型计算总链路">
        <div className="glm-model-stamp">
          <strong>GLM-5.2<br />逻辑模型</strong>
          <span>共同分析对象</span>
        </div>
        {["Prompt / Tokens", "Tokenizer", "Embedding"].map((label) => (
          <div key={label} className="glm-flow-box compact-box">{label}</div>
        ))}
        <div className="glm-transformer-block">
          <div className="glm-block-title">Transformer Blocks (78 Layers)</div>
          <div className="glm-block-cells">
            <div className="glm-flow-box attention-box">Attention<br /><small>MLA / Sparse Attention / IndexShare</small></div>
            <div className="glm-flow-box">Residual + Norm</div>
            <div className="glm-moe-box">
              <span>MLP / MoE</span>
              <div>
                <b>Router</b>
                <b>Shared Expert</b>
                <b>Routed Experts<br /><small>top-k / top-8</small></b>
              </div>
            </div>
          </div>
        </div>
        {["LM Head", "Logits", "Sampling / Decode", "Output Tokens"].map((label) => (
          <div key={label} className="glm-flow-box compact-box">{label}</div>
        ))}
        <div className="glm-fact-note">
          {glmModelFacts.slice(0, 4).map((fact) => (
            <span key={fact.label}>{fact.value}</span>
          ))}
        </div>
      </section>

      <section className="glm-three-columns">
        <article className="glm-lane lane-standard" data-testid="glm-standard-column">
          <h3>标准推理框架（GPU/NPU 主算）</h3>
          <div className="lane-stack">
            <div className="lane-tier cpu-tier">
              <strong>CPU 侧</strong>
              <div className="mini-box-row">
                <span>Tokenizer</span>
                <span>Scheduler / Runtime</span>
                <span>Sampling / Metadata</span>
              </div>
            </div>
            <div className="lane-tier gpu-tier">
              <strong>GPU/NPU 侧</strong>
              <div className="mini-box-row">
                <span>Attention</span>
                <span>MoE 主计算</span>
                <span>LM Head</span>
              </div>
            </div>
            <div className="lane-tier hbm-tier">
              <strong>HBM / NPU Memory</strong>
              <div className="mini-box-row">
                <span>热权重</span>
                <span>Active KV Cache</span>
                <span>Activation / Workspace</span>
                <span>Hot Experts</span>
              </div>
            </div>
            <div className="lane-tier cold-tier muted-tier">
              <strong>CPU DDR / SSD（非热路径）</strong>
              <span>加载 / staging / 外部缓存，不在主热路径上</span>
            </div>
          </div>
          <div className="phase-strip">
            <span>Prefill：计算密集，偏 compute-bound</span>
            <span>Decode：状态访问频繁，偏 memory-bound</span>
          </div>
          <div className="lane-callout warning">对比基线：全部 decode attention 在 GPU/NPU</div>
          <div className="lane-note">优点：链路短、实现成熟、热路径清晰。问题：HBM 同时承载权重、KV、Experts、workspace。</div>
        </article>

        <article className="glm-lane lane-neo" data-testid="glm-neo-column">
          <h3>NEO 类：CPU 承接部分 Decode Attention 与 KV</h3>
          <div className="neo-grid">
            <div className="neo-device gpu-tier">
              <strong>GPU/NPU</strong>
              <span>主 Attention 主路径</span>
              <span>Linear / MoE</span>
              <span>LM Head</span>
            </div>
            <div className="neo-device cpu-tier">
              <strong>CPU + DDR</strong>
              <span>部分 Decode Attention</span>
              <span>部分 KV Cache 驻留</span>
              <span>Load-aware Scheduling</span>
            </div>
          </div>
          <div className="kv-tier-box">
            <strong>KV 分层（Tiering）结构</strong>
            <div>
              <span>GPU HBM：Hot KV 最近访问</span>
              <b>↔</b>
              <span>CPU DDR：Warm KV 被请求、可解码</span>
            </div>
          </div>
          <div className="pipeline-band">Asymmetric Pipeline：Overlap / 并行重叠</div>
          <div className="phase-strip">
            <span>Prefill：仍以 GPU/NPU 为主</span>
            <span>Decode：状态访问与 KV 分层更关键</span>
          </div>
          <div className="lane-callout warning">NEO：部分 decode attention + KV 下沉到 CPU/DDR</div>
          <div className="lane-note">作用：缓解 HBM KV 压力，扩大 batch / concurrency。代价：CPU attention、DDR 带宽或 overlap 不足会反噬 TPOT / P99。</div>
        </article>

        <article className="glm-lane lane-ktransformers" data-testid="glm-ktransformers-column">
          <h3>KTransformers 类：MoE Experts 分层与 CPU/GPU 协同</h3>
          <div className="kt-layout">
            <div className="kt-control">
              <strong>控制面</strong>
              <span>Expert Routing</span>
              <span>Expert Prefetch</span>
              <span>Expert Hotness Scheduling</span>
            </div>
            <div className="kt-tiers">
              <div className="lane-tier gpu-tier">
                <strong>① GPU/NPU / HBM</strong>
                <div className="mini-box-row">
                  <span>Shared Expert</span>
                  <span>Hot Routed Experts</span>
                  <span>Attention 主路径</span>
                  <span>主干计算</span>
                </div>
              </div>
              <div className="lane-tier ddr-tier">
                <strong>② CPU DDR</strong>
                <div className="mini-box-row">
                  <span>Warm Routed Experts</span>
                  <span>Expert Cache / Expert Index</span>
                  <span>低频 CPU Expert Compute</span>
                </div>
              </div>
              <div className="lane-tier ssd-tier">
                <strong>③ SSD / 外部存储</strong>
                <span>Cold Experts：按需回取 / 预取</span>
              </div>
            </div>
          </div>
          <div className="phase-strip">
            <span>Prefill：主链路仍偏 compute-bound</span>
            <span>Decode：MoE 分层优势更明显</span>
          </div>
          <div className="lane-note">作用：解决大 MoE expert 放不下的问题。关键思想：把 Expert 视为分层、可预取、可迁移的状态对象。</div>
        </article>
      </section>

      <section className="glm-bottom-row">
        <article className="glm-hardware-tier" data-testid="glm-hardware-tier">
          <h3>统一硬件层级（由近到远）</h3>
          <div className="hardware-chain">
            {["GPU/NPU Compute", "HBM / NPU Memory", "PCIe / UB / DMA", "CPU Cores", "CPU DDR", "SSD / NVMe"].map((tier) => (
              <span key={tier}>{tier}</span>
            ))}
          </div>
          <div className="path-lines">
            <div><b>标准推理框架</b><span className="line standard-line" /></div>
            <div><b>NEO 类</b><span className="line neo-line" /></div>
            <div><b>KTransformers 类</b><span className="line kt-line" /></div>
          </div>
        </article>

        <article className="glm-summary-table" data-testid="glm-comparison-table">
          <table>
            <thead>
              <tr>
                <th>方案</th>
                <th>主优化对象</th>
                <th>CPU 角色</th>
                <th>主要收益</th>
                <th>主要风险</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((row) => (
                <tr key={row.scheme}>
                  <td>{row.scheme}</td>
                  <td>{row.target}</td>
                  <td>{row.cpuRole}</td>
                  <td>{row.benefit}</td>
                  <td>{row.risk}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      </section>

      <footer className="glm-legend" data-testid="glm-legend">
        <span><b className="solid-arrow" />实线箭头：主数据流</span>
        <span><b className="dash-arrow" />虚线箭头：控制流 / 调度 / 预取</span>
        <span><i className="legend-blue" />深蓝：GPU/NPU 主算</span>
        <span><i className="legend-green" />绿色：CPU 计算/控制</span>
        <span><i className="legend-orange" />橙色：HBM / 热状态</span>
        <span><i className="legend-yellow" />黄色：DDR / 温状态</span>
        <span><i className="legend-sky" />灰蓝：SSD / 冷状态</span>
        <span className="phase-badge prefill">Prefill = compute-intensive</span>
        <span className="phase-badge decode">Decode = memory/state-intensive</span>
      </footer>

      <section className="glm-trace-footer" data-testid="glm-trace-schema">
        {glmTraceFields.map((field) => (
          <span key={field}>{field}</span>
        ))}
      </section>
    </section>
  );
}

function LayerMatrix({ activeWork, onSelectWork }: { activeWork: WorkItem | undefined; onSelectWork: (id: string) => void }) {
  return (
    <section className="matrix-view">
      <div className="section-heading">
        <p className="eyebrow">Layer matrix</p>
        <h2>L0-L11 硬件层级地图</h2>
      </div>
      <div className="layer-grid">
        {hardwareLayers.map((layer) => {
          const related = works.filter((work) => work.layers.includes(layer.id));
          const active = activeWork?.layers.includes(layer.id);
          return (
            <article key={layer.id} className={active ? "layer-card active" : "layer-card"}>
              <div className="layer-card-head">
                <span>{layer.id}</span>
                <strong>{layer.name}</strong>
              </div>
              <p className="hardware-line">{layer.hardware}</p>
              <DetailBlock title="主要瓶颈" text={layer.bottleneck} />
              <DetailBlock title="代表处理" text={layer.representativeMoves} />
              <DetailBlock title="仿真字段" text={layer.simFields} />
              <div className="inline-work-list">
                {related.slice(0, 6).map((work) => (
                  <button type="button" key={work.id} onClick={() => onSelectWork(work.id)}>
                    {work.name}
                  </button>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function WorksTable({
  filteredWorks,
  activeWork,
  onSelectWork,
}: {
  filteredWorks: WorkItem[];
  activeWork: WorkItem | undefined;
  onSelectWork: (id: string) => void;
}) {
  return (
    <section className="table-view">
      <div className="section-heading">
        <p className="eyebrow">Work comparison</p>
        <h2>代表性工作的硬件对照表</h2>
      </div>
      <div className="comparison-table">
        <div className="table-row table-head">
          <span>工作</span>
          <span>主硬件链路</span>
          <span>解决的问题</span>
          <span>边界</span>
        </div>
        {filteredWorks.map((work) => (
          <button
            type="button"
            key={work.id}
            className={work.id === activeWork?.id ? "table-row active" : "table-row"}
            onClick={() => onSelectWork(work.id)}
          >
            <span>
              <strong>{work.name}</strong>
              <small>{work.layers.join(" / ")}</small>
            </span>
            <span>{work.topology.primaryPath.join(" -> ")}</span>
            <span>{work.solves}</span>
            <span>{work.boundary}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function StateObjectFlow({ activeWork, onSelectWork }: { activeWork: WorkItem | undefined; onSelectWork: (id: string) => void }) {
  return (
    <section className="state-view">
      <div className="section-heading">
        <p className="eyebrow">State object flow</p>
        <h2>KV / Expert / Prefix 状态对象流</h2>
      </div>
      <div className="state-grid">
        {stateObjects.map((object) => {
          const active = activeWork?.stateObjects.some((name) => object.name.toLowerCase().includes(name.toLowerCase()) || name.toLowerCase().includes(object.name.toLowerCase()));
          return (
            <article key={object.name} className={active ? "state-card active" : "state-card"}>
              <div className="state-title">
                <MemoryStick size={20} />
                <h3>{object.name}</h3>
              </div>
              <p>{object.growth}</p>
              <div className="tier-lane">
                {object.tiers.map((tier) => (
                  <span key={tier}>{tier}</span>
                ))}
              </div>
              <DetailBlock title="硬件动作" text={object.hardwareAction} />
              <div className="inline-work-list">
                {object.works.map((workId) => {
                  const work = works.find((item) => item.id === workId);
                  return work ? (
                    <button type="button" key={work.id} onClick={() => onSelectWork(work.id)}>
                      {work.name}
                    </button>
                  ) : null;
                })}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function AkRoadmap({ activeWork }: { activeWork: WorkItem | undefined }) {
  return (
    <section className="ak-view">
      <div className="section-heading">
        <p className="eyebrow">Ascend + Kunpeng</p>
        <h2>A+K 迁移路线与仿真字段</h2>
      </div>
      <div className="ak-grid">
        {akStages.map((stage) => (
          <article key={stage.id} className="ak-card">
            <span className="stage-id">{stage.id}</span>
            <h3>{stage.title}</h3>
            <p>{stage.goal}</p>
            <div className="stage-actions">
              {stage.actions.map((action) => (
                <span key={action}>{action}</span>
              ))}
            </div>
            <p className="risk-line">{stage.risk}</p>
          </article>
        ))}
      </div>
      <div className="simulator-panel">
        <div>
          <p className="eyebrow">当前关注的 A+K 含义</p>
          <h3 data-testid="ak-active-work">{activeWork?.name ?? "全部工作"}</h3>
          <p>{activeWork?.akRelevance ?? "按 state object、硬件链路和 stall reason 组织仿真字段。"}</p>
        </div>
        <div className="sim-grid">
          {simulatorModules.map((module) => (
            <article key={module.name} className="sim-card">
              <h4>{module.name}</h4>
              <div className="chip-cloud compact">
                {module.fields.map((field) => (
                  <span key={field}>{field}</span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export default App;
