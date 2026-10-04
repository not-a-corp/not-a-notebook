// Preferences about this browser's screen (design.md §2.1): kept in
// localStorage, and never worth an error when storage is unavailable.

const PREFIX = "not-a-notebook.";

export function readPreference(key: string): string | null {
  try {
    return localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function savePreference(key: string, value: string): void {
  try {
    localStorage.setItem(PREFIX + key, value);
  } catch {
    // A private window without storage: the preference lasts until reload.
  }
}
