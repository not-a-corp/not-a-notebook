import { describe, expect, it } from "vitest";

import { wordsOnly } from "./words-only";

describe("wordsOnly", () => {
  it("leaves the words and drops the code, which becomes a cell", () => {
    const text = "Vou ler o arquivo.\n\n```python\nimport pandas as pd\n```\n\nDepois somo.";

    expect(wordsOnly(text)).toBe("Vou ler o arquivo.\n\nDepois somo.");
  });

  it("drops a fence still being written", () => {
    expect(wordsOnly("Vou ler o arquivo.\n\n```python\nimport pan")).toBe("Vou ler o arquivo.");
  });

  it("leaves words with no code alone", () => {
    expect(wordsOnly("O **Sudeste** faturou mais.")).toBe("O **Sudeste** faturou mais.");
  });
});
