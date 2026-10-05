import { describe, expect, it } from "vitest";

import { asciiName, filenameFrom } from "./export";

describe("filenameFrom", () => {
  it("reads filename* and takes the accents off, so the browser keeps the name", () => {
    const header =
      "attachment; filename=\"Faturamento-_-2025.ipynb\"; filename*=UTF-8''Faturamento-%C3%A9-2025.ipynb";

    expect(filenameFrom(header, "x.ipynb")).toBe("Faturamento-e-2025.ipynb");
  });

  it("keeps a name ASCII", () => {
    expect(asciiName("Faturamento-por-região-2025.py")).toBe("Faturamento-por-regiao-2025.py");
    expect(asciiName("Vendas-東京.py")).toBe("Vendas-__.py");
  });

  it("falls back to the plain name, then to its own", () => {
    expect(filenameFrom('attachment; filename="Vendas.py"', "x.py")).toBe("Vendas.py");
    expect(filenameFrom(null, "conversation.py")).toBe("conversation.py");
  });
});
