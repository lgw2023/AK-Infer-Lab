export type LayerId =
  | "L0"
  | "L1"
  | "L2"
  | "L3"
  | "L4"
  | "L5"
  | "L6"
  | "L7"
  | "L8"
  | "L9"
  | "L10"
  | "L11";

export type PathType = "hot" | "warm" | "cold" | "remote" | "control" | "observe";

export interface HardwareLayer {
  id: LayerId;
  name: string;
  hardware: string;
  bottleneck: string;
  representativeMoves: string;
  simFields: string;
}

export interface WorkItem {
  id: string;
  name: string;
  category: string;
  hardwarePath: string[];
  topology: {
    summary: string;
    primaryPath: string[];
    hardwareClaims: string[];
    nonClaims: string;
    criticalAssumption: string;
    frontendHighlight: string;
    frontendWarning: string;
    highlightNodeIds: string[];
  };
  layers: LayerId[];
  stateObjects: string[];
  solves: string;
  approach: string;
  boundary: string;
  akRelevance: string;
  evidence: string[];
}

export interface HardwareNode {
  id: string;
  label: string;
  group: "request" | "runtime" | "accelerator" | "memory" | "host" | "storage" | "fabric" | "observe";
  role: string;
  linkedLayers: LayerId[];
  x: number;
  y: number;
}

export interface HardwareEdge {
  from: string;
  to: string;
  label: string;
  pathType: PathType;
  relatedWorks: string[];
}

export interface StateObject {
  name: string;
  growth: string;
  tiers: string[];
  works: string[];
  hardwareAction: string;
}

export interface AkStage {
  id: "P0" | "P1" | "P2" | "P3";
  title: string;
  goal: string;
  actions: string[];
  risk: string;
}

export interface SimulatorModule {
  name: string;
  fields: string[];
}

export type GlmPhase = "prefill" | "decode";

export interface GlmModelFact {
  label: string;
  value: string;
  detail: string;
}

export interface GlmComponent {
  id: string;
  title: string;
  layerScope: string;
  hardwareOwner: string;
  prefill: string;
  decode: string;
  bottleneck: string;
  akMove: string;
}

export interface GlmFlowStep {
  phase: GlmPhase;
  order: number;
  title: string;
  hardware: string;
  summary: string;
  componentIds: string[];
  risk: string;
}

export interface GlmPathComparison {
  id: "standard-gpu" | "neo" | "ktransformers";
  title: string;
  mainCompute: string;
  statePlacement: string;
  cpuRole: string;
  benefit: string;
  risk: string;
  changedComponents: string[];
}
