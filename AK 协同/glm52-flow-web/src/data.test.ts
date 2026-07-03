import { describe, expect, it } from "vitest";
import data from "../server/flow-data.json";
import type { FlowData, ScenarioId } from "./types";

const flow = data as FlowData;

describe("flow data", () => {
  it("keeps scenario ids stable for UI comparisons", () => {
    expect(flow.scenarios.map((scenario) => scenario.id)).toEqual([
      "standard",
      "neo",
      "ktransformers"
    ]);
  });

  it("has per-scenario mappings for every component", () => {
    const scenarioIds = flow.scenarios.map((scenario) => scenario.id) as ScenarioId[];
    for (const component of flow.components) {
      for (const scenarioId of scenarioIds) {
        expect(component[scenarioId].length).toBeGreaterThan(8);
      }
    }
  });

  it("preserves the prefill/decode distinction", () => {
    expect(flow.phases.map((phase) => phase.id)).toEqual(["prefill", "decode"]);
    expect(flow.components.every((component) => component.prefill && component.decode)).toBe(true);
  });
});
