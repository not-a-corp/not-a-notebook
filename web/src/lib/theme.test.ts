import { describe, expect, it } from "vitest";

import { readThemeChoice, resolveTheme, saveThemeChoice } from "./theme";

describe("resolveTheme", () => {
  it("follows the system when the choice is system", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });

  it("keeps an explicit choice whatever the system says", () => {
    expect(resolveTheme("mocha", false)).toBe("mocha");
    expect(resolveTheme("light", true)).toBe("light");
  });
});

describe("readThemeChoice", () => {
  it("is system when nothing was saved", () => {
    localStorage.clear();

    expect(readThemeChoice(localStorage)).toBe("system");
  });

  it("reads back what was saved", () => {
    saveThemeChoice(localStorage, "mocha");

    expect(readThemeChoice(localStorage)).toBe("mocha");
  });

  it("ignores a value it does not know", () => {
    localStorage.setItem("not-a-notebook.theme", "solarized");

    expect(readThemeChoice(localStorage)).toBe("system");
  });
});
