import { describe, expect, it } from "vitest";

import { clampShare } from "./pane-layout";

describe("clampShare", () => {
  it("keeps a share that leaves both panes 360 px wide", () => {
    expect(clampShare(0.4, 1192)).toBe(0.4);
  });

  it("stops each pane at 360 px", () => {
    expect(clampShare(0.05, 1200)).toBeCloseTo(0.3);
    expect(clampShare(0.95, 1200)).toBeCloseTo(0.7);
  });

  it("splits evenly when the screen holds less than two panes", () => {
    expect(clampShare(0.4, 600)).toBe(0.5);
  });
});
