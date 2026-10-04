import { describe, expect, it } from "vitest";

import type { FileInfo, Message } from "@/api/conversation-detail";

import { buildTimeline } from "./timeline";

function file(name: string, createdAt: string): FileInfo {
  return { id: name, name, bytes: 1, profile: null, createdAt };
}

function message(text: string, createdAt: string): Message {
  return { id: text, role: "user", runId: null, text, kind: null, grounding: null, createdAt };
}

describe("buildTimeline", () => {
  it("puts files and messages in the order they happened", () => {
    const items = buildTimeline(
      [file("vendas.csv", "2026-10-04T14:05:52Z"), file("metas.xlsx", "2026-10-04T14:09:00Z")],
      [
        message("Qual região?", "2026-10-04T14:06:10Z"),
        message("E por mês?", "2026-10-04T14:10:00Z"),
      ],
    );

    expect(items.map((item) => item.at)).toEqual([
      "2026-10-04T14:05:52Z",
      "2026-10-04T14:06:10Z",
      "2026-10-04T14:09:00Z",
      "2026-10-04T14:10:00Z",
    ]);
  });
});
