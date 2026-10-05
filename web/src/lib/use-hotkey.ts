import { useEffect, useRef } from "react";

export interface Hotkey {
  key: string;
  // The physical key, for combinations where the character changes — on macOS,
  // Option+\ types «, not \.
  code?: string;
  // Ctrl on Linux and Windows, Cmd on macOS — design.md §7 writes it Ctrl/Cmd.
  mod?: boolean;
  shift?: boolean;
  alt?: boolean;
}

export function matchesHotkey(event: KeyboardEvent, hotkey: Hotkey): boolean {
  const mod = event.ctrlKey || event.metaKey;
  if ((hotkey.mod ?? false) !== mod) {
    return false;
  }
  if ((hotkey.shift ?? false) !== event.shiftKey) {
    return false;
  }
  if ((hotkey.alt ?? false) !== event.altKey) {
    return false;
  }

  if (hotkey.code !== undefined && event.code === hotkey.code) {
    return true;
  }
  return event.key.toLowerCase() === hotkey.key.toLowerCase();
}

export function useHotkey(hotkey: Hotkey, handler: (event: KeyboardEvent) => void): void {
  // The latest hotkey and handler, without re-subscribing on every render.
  const latest = useRef({ hotkey, handler });
  useEffect(() => {
    latest.current = { hotkey, handler };
  });

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      // A key something else already handled — Escape closing a dialog or a
      // menu — is not also a shortcut.
      if (event.defaultPrevented) {
        return;
      }
      if (matchesHotkey(event, latest.current.hotkey)) {
        event.preventDefault();
        latest.current.handler(event);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);
}
