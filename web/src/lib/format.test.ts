import { describe, expect, it } from "vitest";

import { formatBytes, formatCount, formatDuration, plural } from "./format";

describe("format", () => {
  it("reads sizes the way the mockups do", () => {
    expect(formatBytes(86_016)).toBe("84 KB");
    expect(formatBytes(1_258_291)).toBe("1.2 MB");
    expect(formatBytes(512)).toBe("512 B");
  });

  it("reads durations in ms under a second, in seconds above", () => {
    expect(formatDuration(412)).toBe("412 ms");
    expect(formatDuration(1300)).toBe("1.3 s");
  });

  it("counts with separators and agrees in number", () => {
    expect(formatCount(1286)).toBe("1,286");
    expect(plural(1, "row", "rows")).toBe("1 row");
    expect(plural(12480, "row", "rows")).toBe("12,480 rows");
  });
});
