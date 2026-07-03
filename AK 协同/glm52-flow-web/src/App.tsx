import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  Boxes,
  CircuitBoard,
  Cpu,
  Database,
  GitBranch,
  HardDrive,
  Loader2,
  MemoryStick,
  Megaphone,
  Network,
  Route,
  Star
} from "lucide-react";
import type { FlowData, ScenarioId } from "./types";

const scenarioNames: Record<ScenarioId, string> = {
  standard: "标准推理框架",
  neo: "NEO",
  ktransformers: "KTransformers"
};

const tierIcons: Record<string, typeof Cpu> = {
  npu: Cpu,
  hbm: MemoryStick,
  dma: GitBranch,
  cpu: CircuitBoard,
  ddr: Database,
  ssd: HardDrive
};

function phaseSummary(data: FlowData, id: "prefill" | "decode") {
  return data.phases.find((phase) => phase.id === id);
}

function scenario(data: FlowData, id: ScenarioId) {
  const item = data.scenarios.find((entry) => entry.id === id);
  if (!item) {
    throw new Error(`Missing scenario ${id}`);
  }
  return item;
}

function Status() {
  return (
    <main className="center-state">
      <Loader2 className="spin" />
      <p>正在加载 GLM-5.2 推理图谱</p>
    </main>
  );
}

export function App() {
  const [data, setData] = useState<FlowData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/flow")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`API ${response.status}`);
        }
        return response.json() as Promise<FlowData>;
      })
      .then(setData)
      .catch((apiError: Error) => setError(apiError.message));
  }, []);

  const groupedPipeline = useMemo(() => {
    if (!data) {
      return [];
    }
    return data.pipeline;
  }, [data]);

  if (error) {
    return (
      <main className="center-state">
        <AlertTriangle />
        <p>网站数据读取失败：{error}</p>
      </main>
    );
  }

  if (!data) {
    return <Status />;
  }

  const standard = scenario(data, "standard");
  const neo = scenario(data, "neo");
  const kt = scenario(data, "ktransformers");
  const prefill = phaseSummary(data, "prefill");
  const decode = phaseSummary(data, "decode");

  return (
    <main className="infographic-app">
      <section className="infographic-sheet" aria-label="GLM-5.2 推理计算流与异构协同对比图">
        <header className="poster-header">
          <h1>GLM-5.2 推理计算流与 CPU/GPU/NPU 异构协同对比</h1>
          <p>标准推理框架 vs 文献中新方案（NEO / KTransformers）</p>
        </header>

        <section className="top-flow">
          <div className="model-object">
            <strong>GLM-5.2<br />逻辑模型</strong>
            <span>共同分析对象</span>
          </div>

          <div className="flow-strip">
            {groupedPipeline.slice(0, 3).map((step) => (
              <article className="flow-node" key={step.id}>
                <strong>{step.label}</strong>
              </article>
            ))}
            <section className="transformer-box">
              <h2>Transformer Blocks（78 Layers）</h2>
              <div className="transformer-inner">
                <article>
                  <strong>Attention</strong>
                  <span>MLA / Sparse Attention / IndexShare</span>
                </article>
                <article>
                  <strong>Residual + Norm</strong>
                </article>
                <article className="moe-mini">
                  <strong>MLP / MoE</strong>
                  <div>
                    <span>Router</span>
                    <span>Shared Expert</span>
                    <span>Routed Experts<br />top-k 路由，256 experts，top-8</span>
                  </div>
                </article>
              </div>
            </section>
            {groupedPipeline.slice(5).map((step) => (
              <article className="flow-node" key={step.id}>
                <strong>{step.label}</strong>
              </article>
            ))}
          </div>

          <div className="model-facts">
            {data.modelFacts.slice(2, 6).map((fact) => (
              <span key={fact.label}>• {fact.value}</span>
            ))}
          </div>
        </section>

        <section className="main-panels">
          <ScenarioPanel
            kind="standard"
            title="标准推理框架（GPU/NPU 主导）"
            scenario={standard}
            callouts={[
              "CPU 负责请求接入、批处理、调度与采样",
              "GPU/NPU 执行主干推理计算",
              "热数据常驻 HBM，高频访问"
            ]}
          />
          <ScenarioPanel
            kind="neo"
            title="NEO 类：CPU 系统算力 Decode Attention 与 KV"
            scenario={neo}
            callouts={[
              "保持主干于加速器计算",
              "系统部分 Decode Attention 与 KV，降低显存瓶颈",
              "KV 分层：热点 HBM，温存 DDR"
            ]}
          />
          <KTransformersPanel scenario={kt} />
        </section>

        <section className="stage-row">
          <article>
            <strong>Prefill：计算密集，偏 compute-bound</strong>
            <span>{prefill?.summary}</span>
          </article>
          <article>
            <strong>Decode：状态相关强，偏 memory-bound</strong>
            <span>{decode?.summary}</span>
          </article>
          <article className="megaphone">
            <Megaphone />
            <strong>对比基线行为：全部 decode attention 在 GPU/NPU</strong>
          </article>
          <article className="star-note">
            <Star />
            <span>核心判断：不是 CPU 替代 NPU，而是状态对象分层、预取与可重叠调度。</span>
          </article>
        </section>

        <section className="bottom-grid">
          <HardwareStrip data={data} />
          <ComparisonTable data={data} />
        </section>

        <section className="legend-row">
          <div className="legend-title">图例说明</div>
          <div className="legend-item">
            <span className="solid-line" />
            实际流动：主数据流
          </div>
          <div className="legend-item">
            <span className="dash-line" />
            逻辑虚线：调度 / 预取 / 旁路
          </div>
          <div className="legend-chip blue">深蓝：GPU/NPU 主算</div>
          <div className="legend-chip green">绿色：CPU 计算/控制</div>
          <div className="legend-chip orange">橙色：HBM / 热状态</div>
          <div className="legend-chip yellow">黄色：DDR / 温状态</div>
          <div className="legend-chip pale">浅蓝：SSD / 冷状态</div>
        </section>
      </section>
    </main>
  );
}

function ScenarioPanel({
  kind,
  title,
  scenario,
  callouts
}: {
  kind: "standard" | "neo";
  title: string;
  scenario: FlowData["scenarios"][number];
  callouts: string[];
}) {
  return (
    <article className={`scenario-panel ${kind}`}>
      <h2>{title}</h2>
      <div className="panel-body">
        <div className="side-icons">
          <CircuitBoard />
          <Cpu />
          <MemoryStick />
          <HardDrive />
        </div>
        <div className="lane-stack">
          {scenario.lanes.map((lane, index) => (
            <section className={`mini-lane lane-${lane.id}`} key={lane.id}>
              <h3>{lane.title}</h3>
              <div className="mini-items">
                {lane.items.slice(0, 4).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
              {index < scenario.lanes.length - 1 ? <ArrowDown className="down-arrow" /> : null}
            </section>
          ))}
        </div>
        <aside className="callout-stack">
          {callouts.map((callout) => (
            <p key={callout}>{callout}</p>
          ))}
        </aside>
      </div>
      <footer>
        <strong>优势：</strong>
        <span>{scenario.benefits.join("；")}</span>
      </footer>
    </article>
  );
}

function KTransformersPanel({ scenario }: { scenario: FlowData["scenarios"][number] }) {
  const lanes = scenario.lanes;
  return (
    <article className="scenario-panel ktransformers">
      <h2>KTransformers 类：MoE Experts 分层与 CPU/GPU 协同</h2>
      <div className="kt-body">
        <div className="control-column">
          {lanes.slice(3).map((lane, index) => (
            <section className="dashed-control" key={lane.id}>
              <strong>{index + 1} 路由层</strong>
              <span>{lane.items.join(" / ")}</span>
            </section>
          ))}
          <section className="dashed-control">
            <strong>Expert Prefetch</strong>
            <span>预取 Warm/Cold</span>
          </section>
          <section className="dashed-control">
            <strong>Expert Hotness</strong>
            <span>热度评估与调度</span>
          </section>
        </div>
        <div className="kt-tiers">
          <section className="kt-tier hot">
            <b>① GPU/NPU / HBM</b>
            <div>
              <span>Shared Expert</span>
              <span>Hot Routed Experts</span>
              <span>Attention 主路径</span>
              <span>主干计算</span>
            </div>
            <p>热 Expert 直接在 HBM 执行</p>
          </section>
          <section className="kt-tier warm">
            <b>② CPU DDR</b>
            <div>
              <span>Warm Routed Experts</span>
              <span>Expert Cache / Index</span>
              <span>低频 CPU Expert Compute</span>
            </div>
            <p>温 Expert 存放于 DDR，可步进计算</p>
          </section>
          <section className="kt-tier cold">
            <b>③ SSD / 外部存储</b>
            <div>
              <span>Cold Experts</span>
            </div>
            <p>冷 Expert 存储于 SSD，按需回收 / 预取</p>
          </section>
        </div>
      </div>
      <footer>
        <strong>作用：</strong>
        <span>{scenario.benefits.join("；")}</span>
      </footer>
    </article>
  );
}

function HardwareStrip({ data }: { data: FlowData }) {
  return (
    <article className="hardware-strip">
      <h2>统一硬件层级（由近到远）</h2>
      <div className="tier-row">
        {data.hardwareTiers.map((tier, index) => {
          const Icon = tierIcons[tier.id] ?? Network;
          return (
            <div className={`tier-node tone-${tier.tone}`} key={tier.id}>
              <Icon />
              <strong>{tier.label}</strong>
              <span>{tier.role}</span>
              {index < data.hardwareTiers.length - 1 ? <ArrowRight className="tier-flow" /> : null}
            </div>
          );
        })}
      </div>
      <div className="route-lines">
        <p><b>标准推理框架：</b><span className="route blue-route" /></p>
        <p><b>NEO 类：</b><span className="route green-route" /></p>
        <p><b>KTransformers 类：</b><span className="route orange-route" /><em>Expert Prefetch Path</em></p>
      </div>
    </article>
  );
}

function ComparisonTable({ data }: { data: FlowData }) {
  return (
    <article className="compact-table">
      <div className="table-row table-head">
        <span>方案</span>
        <span>主优化对象</span>
        <span>CPU 角色</span>
        <span>主要收益</span>
        <span>主要风险</span>
      </div>
      {data.comparisonRows.slice(0, 1).map(() =>
        (["standard", "neo", "ktransformers"] as ScenarioId[]).map((id) => {
          const item = scenario(data, id);
          return (
            <div className="table-row" key={id}>
              <strong>{scenarioNames[id]}</strong>
              <span>{item.offloadObject}</span>
              <span>{id === "standard" ? "调度与控制" : id === "neo" ? "KV warm tier + 部分 attention" : "expert warm tier / prefetch / compute"}</span>
              <span>{item.benefits[0]}</span>
              <span>{item.risks[0]}</span>
            </div>
          );
        })
      )}
    </article>
  );
}
