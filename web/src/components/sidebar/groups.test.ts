import { describe, expect, it } from "vitest";

import type { ConversationSummary } from "@/api/conversations";

import { groupByActivity, groupLabel } from "./groups";

const NOW = new Date(2026, 9, 4, 15, 30);

function at(daysAgo: number, hour: number): string {
  return new Date(2026, 9, 4 - daysAgo, hour, 0).toISOString();
}

function conversation(id: string, updatedAt: string): ConversationSummary {
  return {
    id,
    title: id,
    modelId: null,
    kernel: "stopped",
    createdAt: updatedAt,
    updatedAt,
  };
}

describe("groupLabel", () => {
  it("counts calendar days, not 24-hour spans", () => {
    expect(groupLabel(at(0, 0), NOW)).toBe("Today");
    expect(groupLabel(at(1, 23), NOW)).toBe("Yesterday");
    expect(groupLabel(at(2, 12), NOW)).toBe("Last 7 days");
    expect(groupLabel(at(7, 12), NOW)).toBe("Last 7 days");
    expect(groupLabel(at(8, 12), NOW)).toBe("Earlier");
  });
});

describe("groupByActivity", () => {
  it("keeps the newest-first order inside each group", () => {
    const groups = groupByActivity(
      [
        conversation("a", at(0, 14)),
        conversation("b", at(0, 9)),
        conversation("c", at(1, 10)),
        conversation("d", at(30, 10)),
      ],
      NOW,
    );

    expect(groups.map((group) => group.label)).toEqual(["Today", "Yesterday", "Earlier"]);
    expect(groups[0]?.conversations.map((item) => item.id)).toEqual(["a", "b"]);
  });
});
