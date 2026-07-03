export type PhaseId = "prefill" | "decode";
export type ScenarioId = "standard" | "neo" | "ktransformers";

export interface FlowData {
  meta: {
    title: string;
    subtitle: string;
    sources: string[];
  };
  modelFacts: Array<{ label: string; value: string; note: string }>;
  phases: Array<{
    id: PhaseId;
    label: string;
    headline: string;
    summary: string;
    bottlenecks: string[];
    metrics: string[];
  }>;
  pipeline: Array<{
    id: string;
    label: string;
    hardware: string;
    summary: string;
  }>;
  components: Array<{
    id: string;
    label: string;
    group: "control" | "compute" | "state" | "expert" | "transfer";
    layer: string;
    summary: string;
    prefill: string;
    decode: string;
    standard: string;
    neo: string;
    ktransformers: string;
  }>;
  scenarios: Array<{
    id: ScenarioId;
    title: string;
    short: string;
    accent: "blue" | "green" | "amber";
    proposition: string;
    mainHardware: string;
    offloadObject: string;
    benefits: string[];
    risks: string[];
    lanes: Array<{
      id: string;
      title: string;
      items: string[];
      note: string;
    }>;
  }>;
  hardwareTiers: Array<{
    id: string;
    label: string;
    role: string;
    tone: string;
  }>;
  stateObjects: Array<{
    name: string;
    growth: string;
    standard: string;
    neo: string;
    ktransformers: string;
    fields: string[];
  }>;
  comparisonRows: Array<{
    topic: string;
    standard: string;
    neo: string;
    ktransformers: string;
  }>;
  traceFields: string[];
  akTakeaways: string[];
}
