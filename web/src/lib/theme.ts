// The theme is a preference about this browser, not about the account
// (design.md §2.6), so it lives in localStorage and nowhere else.

export type ThemeChoice = "system" | "light" | "dark" | "mocha";
export type Theme = "light" | "dark" | "mocha";

const STORAGE_KEY = "not-a-notebook.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === "system" || value === "light" || value === "dark" || value === "mocha";
}

export function readThemeChoice(storage: Storage): ThemeChoice {
  const stored = storage.getItem(STORAGE_KEY);
  if (!isThemeChoice(stored)) {
    return "system";
  }

  return stored;
}

export function saveThemeChoice(storage: Storage, choice: ThemeChoice): void {
  storage.setItem(STORAGE_KEY, choice);
}

export function resolveTheme(choice: ThemeChoice, systemPrefersDark: boolean): Theme {
  if (choice !== "system") {
    return choice;
  }

  if (systemPrefersDark) {
    return "dark";
  }

  return "light";
}

export function applyTheme(root: HTMLElement, choice: ThemeChoice): void {
  const systemPrefersDark = window.matchMedia(DARK_QUERY).matches;
  root.dataset.theme = resolveTheme(choice, systemPrefersDark);
}

// System follows the operating system while the page is open, not only on load.
export function followSystemTheme(root: HTMLElement, storage: Storage): () => void {
  const query = window.matchMedia(DARK_QUERY);

  function onChange(): void {
    applyTheme(root, readThemeChoice(storage));
  }

  query.addEventListener("change", onChange);

  return () => {
    query.removeEventListener("change", onChange);
  };
}
