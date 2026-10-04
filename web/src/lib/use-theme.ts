import { useSyncExternalStore } from "react";

// The theme in effect, as <html data-theme> says it — so what draws with the
// tokens outside CSS (a chart's canvas) redraws when the theme changes.

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => {
    observer.disconnect();
  };
}

function current(): string {
  return document.documentElement.dataset.theme ?? "light";
}

export function useAppliedTheme(): string {
  return useSyncExternalStore(subscribe, current);
}

export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
}
