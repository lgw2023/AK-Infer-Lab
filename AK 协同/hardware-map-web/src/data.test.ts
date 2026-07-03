import { describe, expect, it } from "vitest";
import { hardwareEdges, hardwareLayers, hardwareNodes, layerIds, works } from "./data";
import * as data from "./data";

describe("hardware map data", () => {
  it("covers L0-L11 exactly once", () => {
    expect(hardwareLayers.map((layer) => layer.id)).toEqual(layerIds);
    expect(new Set(hardwareLayers.map((layer) => layer.id)).size).toBe(12);
  });

  it("keeps all work layer references valid", () => {
    const validLayerIds = new Set(layerIds);
    for (const work of works) {
      expect(work.layers.length, work.name).toBeGreaterThan(0);
      for (const layerId of work.layers) {
        expect(validLayerIds.has(layerId), `${work.name} -> ${layerId}`).toBe(true);
      }
    }
  });

  it("preloads the key works named in the implementation plan", () => {
    const ids = new Set(works.map((work) => work.id));
    [
      "neo",
      "tutti",
      "mooncake",
      "vllm-ascend-cpu-offload",
      "vllm-ascend-ucm-kv-pool",
      "ktransformers",
      "flexinfer",
      "bidaw",
      "solidattention",
      "dali",
      "fluxmoe",
      "servegen",
      "profinfer",
      "llmservingsim2",
    ].forEach((id) => expect(ids.has(id), id).toBe(true));
  });

  it("keeps each work item evidence-backed and decision-useful", () => {
    for (const work of works) {
      expect(work.hardwarePath.length, `${work.name} hardwarePath`).toBeGreaterThan(0);
      expect(work.topology.summary.trim(), `${work.name} topology summary`).not.toEqual("");
      expect(work.topology.primaryPath.length, `${work.name} primaryPath`).toBeGreaterThan(0);
      expect(work.topology.hardwareClaims.length, `${work.name} hardwareClaims`).toBeGreaterThan(0);
      expect(work.topology.nonClaims.trim(), `${work.name} nonClaims`).not.toEqual("");
      expect(work.topology.criticalAssumption.trim(), `${work.name} criticalAssumption`).not.toEqual("");
      expect(work.topology.frontendHighlight.trim(), `${work.name} frontendHighlight`).not.toEqual("");
      expect(work.topology.frontendWarning.trim(), `${work.name} frontendWarning`).not.toEqual("");
      expect(work.topology.highlightNodeIds.length, `${work.name} highlightNodeIds`).toBeGreaterThan(0);
      expect(work.solves.trim(), `${work.name} solves`).not.toEqual("");
      expect(work.boundary.trim(), `${work.name} boundary`).not.toEqual("");
      expect(work.evidence.length, `${work.name} evidence`).toBeGreaterThan(0);
    }
  });

  it("keeps hardware edge endpoints and related works valid", () => {
    const nodeIds = new Set(hardwareNodes.map((node) => node.id));
    const workIds = new Set(works.map((work) => work.id));
    for (const edge of hardwareEdges) {
      expect(nodeIds.has(edge.from), edge.label).toBe(true);
      expect(nodeIds.has(edge.to), edge.label).toBe(true);
      expect(edge.relatedWorks.length, edge.label).toBeGreaterThan(0);
      for (const workId of edge.relatedWorks) {
        expect(workIds.has(workId), `${edge.label} -> ${workId}`).toBe(true);
      }
    }
  });

  it("keeps topology highlight nodes valid", () => {
    const nodeIds = new Set(hardwareNodes.map((node) => node.id));
    for (const work of works) {
      for (const nodeId of work.topology.highlightNodeIds) {
        expect(nodeIds.has(nodeId), `${work.name} -> ${nodeId}`).toBe(true);
      }
    }
  });

  it("keeps the server-board topology compact instead of reverting to a tall chain", () => {
    const xValues = hardwareNodes.map((node) => node.x);
    const yValues = hardwareNodes.map((node) => node.y);

    expect(Math.max(...xValues) - Math.min(...xValues)).toBeLessThanOrEqual(1000);
    expect(Math.max(...yValues) - Math.min(...yValues)).toBeLessThanOrEqual(780);
  });

  it("uses the corrected FluxMoE evidence path", () => {
    const fluxmoe = works.find((work) => work.id === "fluxmoe");
    expect(fluxmoe?.evidence).toContain("references/papers/FluxMoE__arxiv-2604.02715v2.pdf");
    expect(fluxmoe?.evidence.join(" ")).not.toContain("2601.07343");
  });

  it("provides GLM-5.2 inference flow data for architecture, phases and path comparison", () => {
    const module = data as typeof data & {
      glmComponents?: Array<{ id: string; title: string; hardwareOwner: string }>;
      glmFlowSteps?: Array<{ phase: string; componentIds: string[] }>;
      glmPathComparisons?: Array<{ id: string; title: string }>;
      glmTraceFields?: string[];
    };

    expect(module.glmComponents?.map((component) => component.id)).toEqual([
      "runtime",
      "embedding",
      "rmsnorm",
      "mla-dsa",
      "kv-cache",
      "dense-mlp",
      "moe-router",
      "shared-expert",
      "routed-experts",
      "lm-head",
    ]);
    expect(module.glmComponents?.map((component) => component.hardwareOwner)).toContain("GPU/NPU + HBM");
    expect(module.glmComponents?.map((component) => component.hardwareOwner)).toContain("CPU runtime");
    expect(module.glmFlowSteps?.filter((step) => step.phase === "prefill").length).toBeGreaterThanOrEqual(6);
    expect(module.glmFlowSteps?.filter((step) => step.phase === "decode").length).toBeGreaterThanOrEqual(6);
    expect(module.glmFlowSteps?.flatMap((step) => step.componentIds)).toContain("mla-dsa");
    expect(module.glmFlowSteps?.flatMap((step) => step.componentIds)).toContain("routed-experts");
    expect(module.glmPathComparisons?.map((path) => path.id)).toEqual(["standard-gpu", "neo", "ktransformers"]);
    expect(module.glmTraceFields).toContain("stall_reason");
  });
});
