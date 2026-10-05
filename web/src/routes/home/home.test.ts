import { describe, expect, it } from "vitest";

import { titleFor } from "./home";

describe("titleFor", () => {
  it("names the conversation after its question", () => {
    expect(titleFor("  Qual região   faturou mais?  ", [])).toBe("Qual região faturou mais?");
  });

  it("cuts a long question at a word-ish edge with an ellipsis", () => {
    const title = titleFor("a".repeat(80), []);

    expect(title).toHaveLength(60);
    expect(title.endsWith("…")).toBe(true);
  });

  it("is the file's name when a file was sent alone", () => {
    const file = new File(["x"], "vendas_2025.xlsx");

    expect(titleFor("", [file])).toBe("vendas_2025.xlsx");
  });
});
