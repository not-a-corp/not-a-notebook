import { describe, expect, it } from "vitest";

import { decodeOutput, type Output } from "@/api/outputs";

import { chartLabel, joinStreams } from "./outputs";

describe("joinStreams", () => {
  it("joins chunks of the same stream and keeps stderr apart", () => {
    const outputs: Output[] = [
      { kind: "stream", name: "stdout", text: "remov" },
      { kind: "stream", name: "stdout", text: "idas 1\n" },
      { kind: "stream", name: "stderr", text: "warning\n" },
      { kind: "stream", name: "stdout", text: "done\n" },
    ];

    expect(joinStreams(outputs)).toEqual([
      { kind: "stream", name: "stdout", text: "removidas 1\n" },
      { kind: "stream", name: "stderr", text: "warning\n" },
      { kind: "stream", name: "stdout", text: "done\n" },
    ]);
  });
});

describe("decodeOutput", () => {
  it("reads a table as api.md shows it", () => {
    const output = decodeOutput({
      kind: "table",
      columns: ["Região", "faturamento"],
      rows: [
        ["Sudeste", 4218340.5],
        ["Sul", null],
      ],
      total_rows: 4,
    });

    expect(output).toEqual({
      kind: "table",
      columns: ["Região", "faturamento"],
      rows: [
        ["Sudeste", 4218340.5],
        ["Sul", null],
      ],
      totalRows: 4,
    });
  });

  it("refuses an output whose kind it does not know", () => {
    expect(() => decodeOutput({ kind: "video" })).toThrow();
  });
});

describe("chartLabel", () => {
  it("says the chart's title and its series", () => {
    const spec = {
      data: [{ name: "2024" }, { name: "2025" }],
      layout: { title: { text: "Faturamento por região" } },
    };

    expect(chartLabel(spec)).toBe("Chart: Faturamento por região. 2024, 2025.");
  });
});
