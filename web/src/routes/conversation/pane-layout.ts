import { useState } from "react";

import { readPreference, savePreference } from "@/lib/preferences";

// design.md §2.1: which side each pane is on and how the width is split are a
// preference about the screen, not about the analysis — kept per browser, for
// every conversation.

export type PaneName = "chat" | "notebook";
export type ChatSide = "left" | "right";

export const DEFAULT_CHAT_SHARE = 0.4;
export const MIN_PANE_PX = 360;

// The chat's share of the width, kept so that neither pane is narrower than
// MIN_PANE_PX — or, on a screen too narrow for two of those, an even split.
export function clampShare(share: number, width: number): number {
  if (width < MIN_PANE_PX * 2) {
    return 0.5;
  }
  const least = MIN_PANE_PX / width;
  return Math.min(Math.max(share, least), 1 - least);
}

function readSide(): ChatSide {
  if (readPreference("panes.chat-side") === "right") {
    return "right";
  }
  return "left";
}

function readShare(): number {
  const stored = Number(readPreference("panes.chat-share"));
  if (!Number.isFinite(stored) || stored <= 0 || stored >= 1) {
    return DEFAULT_CHAT_SHARE;
  }
  return stored;
}

export interface PaneLayout {
  chatSide: ChatSide;
  chatShare: number;
  maximized: PaneName | null;
  swap: () => void;
  resize: (share: number) => void;
  toggleMaximized: (pane: PaneName) => void;
}

export function usePaneLayout(): PaneLayout {
  const [chatSide, setChatSide] = useState<ChatSide>(readSide);
  const [chatShare, setChatShare] = useState(readShare);
  const [maximized, setMaximized] = useState<PaneName | null>(null);

  function swap() {
    let next: ChatSide = "left";
    if (chatSide === "left") {
      next = "right";
    }
    setChatSide(next);
    savePreference("panes.chat-side", next);
  }

  function resize(share: number) {
    setChatShare(share);
    savePreference("panes.chat-share", String(share));
  }

  function toggleMaximized(pane: PaneName) {
    if (maximized === pane) {
      setMaximized(null);
      return;
    }
    setMaximized(pane);
  }

  return { chatSide, chatShare, maximized, swap, resize, toggleMaximized };
}
