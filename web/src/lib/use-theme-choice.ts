import { useState } from "react";

import { applyTheme, readThemeChoice, saveThemeChoice, type ThemeChoice } from "./theme";

// The theme picked in Settings → General: saved in this browser and applied at
// once — the whole screen changes as the card is picked.
export function useThemeChoice(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(() => readThemeChoice(localStorage));

  function choose(next: ThemeChoice) {
    saveThemeChoice(localStorage, next);
    applyTheme(document.documentElement, next);
    setChoice(next);
  }

  return [choice, choose];
}
