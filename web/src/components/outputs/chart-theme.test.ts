import { describe, expect, it } from "vitest";

import { themeFigure } from "./chart-theme";

const TOKENS = {
  text: "#18181b",
  textMuted: "#6b6b74",
  border: "#e4e4e7",
  palette: ["#0e7490", "#c2410c", "#6d28d9"],
};

// What plotly express sends for px.bar(...) and px.line(..., color=...).
const BAR = {
  data: [{ type: "bar", x: ["Sudeste", "Sul"], y: [4.2, 2.7], marker: { color: "#636efa" } }],
  layout: { template: { layout: { colorway: ["#636efa"] } }, title: { text: "Faturamento" } },
};

describe("themeFigure", () => {
  it("replaces plotly's own colours with the app's palette, position by position", () => {
    const line = {
      data: [
        { type: "scatter", line: { color: "#636efa" } },
        { type: "scatter", line: { color: "#EF553B" } },
      ],
      layout: {},
    };

    const themed = themeFigure(line, TOKENS);

    expect(themed.data[0]?.line).toEqual({ color: "#0e7490" });
    expect(themed.data[1]?.line).toEqual({ color: "#c2410c" });
  });

  it("keeps a colour the code chose", () => {
    const chosen = { data: [{ type: "bar", marker: { color: "#123456" } }], layout: {} };

    expect(themeFigure(chosen, TOKENS).data[0]?.marker).toEqual({ color: "#123456" });
  });

  it("drops the kernel's template and paints the app's look", () => {
    const themed = themeFigure(BAR, TOKENS);

    expect(themed.layout.template).toBeUndefined();
    expect(themed.layout.paper_bgcolor).toBe("rgba(0,0,0,0)");
    expect(themed.layout.height).toBe(300);
    expect(themed.layout.colorway).toEqual(TOKENS.palette);
  });

  it("draws only horizontal gridlines on a bar chart", () => {
    const themed = themeFigure(BAR, TOKENS);

    expect(themed.layout.xaxis).toMatchObject({ showgrid: false });
    expect(themed.layout.yaxis).toMatchObject({ showgrid: true, gridcolor: "#e4e4e7" });
  });

  it("never changes the spec it was given", () => {
    themeFigure(BAR, TOKENS);

    expect(BAR.data[0]?.marker.color).toBe("#636efa");
    expect(BAR.layout.template).toBeDefined();
  });
});
