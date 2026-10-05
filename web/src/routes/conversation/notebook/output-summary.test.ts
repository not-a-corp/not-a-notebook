import { describe, expect, it } from "vitest";

import type { Output } from "@/api/outputs";

import { summarizeOutputs } from "./output-summary";

const STDOUT: Output = { kind: "stream", name: "stdout", text: "1\n" };
const MORE_STDOUT: Output = { kind: "stream", name: "stdout", text: "2\n" };
const TABLE: Output = { kind: "table", columns: ["a"], rows: [[1]], totalRows: 1 };
const CHART: Output = { kind: "plotly", spec: {} };
const ERROR: Output = { kind: "error", name: "KeyError", value: "'região'", traceback: [] };

describe("what closed outputs say", () => {
  it("names each kind once, in the order it came", () => {
    const summary = summarizeOutputs([STDOUT, TABLE, CHART]);

    expect(summary).toEqual({ label: "Output · text, table, chart", failed: false });
  });

  it("joins consecutive chunks of a stream into one text", () => {
    const summary = summarizeOutputs([STDOUT, MORE_STDOUT]);

    expect(summary.label).toBe("Output · text");
  });

  it("counts a kind that comes more than once", () => {
    const summary = summarizeOutputs([TABLE, CHART, TABLE]);

    expect(summary.label).toBe("Output · table ×2, chart");
  });

  it("leads with the error and marks the cell failed", () => {
    const summary = summarizeOutputs([STDOUT, ERROR]);

    expect(summary).toEqual({ label: "Error · KeyError, text", failed: true });
  });
});
