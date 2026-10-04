import type { ConversationSummary } from "@/api/conversations";

// design.md §2.1: the conversations grouped by activity, from `updated_at`, on
// the calendar of the person reading — "Today" is their today, not UTC's.

export type GroupLabel = "Today" | "Yesterday" | "Last 7 days" | "Earlier";

export interface ConversationGroup {
  label: GroupLabel;
  conversations: ConversationSummary[];
}

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(date: Date): number {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy.getTime();
}

export function groupLabel(updatedAt: string, now: Date): GroupLabel {
  const today = startOfDay(now);
  const updated = new Date(updatedAt).getTime();

  if (updated >= today) {
    return "Today";
  }
  if (updated >= today - DAY_MS) {
    return "Yesterday";
  }
  if (updated >= today - 7 * DAY_MS) {
    return "Last 7 days";
  }
  return "Earlier";
}

// The list arrives newest first (api.md), so each group keeps that order and the
// groups come out in the order they are met.
export function groupByActivity(
  conversations: ConversationSummary[],
  now: Date,
): ConversationGroup[] {
  const groups: ConversationGroup[] = [];

  for (const conversation of conversations) {
    const label = groupLabel(conversation.updatedAt, now);
    const last = groups.at(-1);
    if (last?.label === label) {
      last.conversations.push(conversation);
    } else {
      groups.push({ label, conversations: [conversation] });
    }
  }

  return groups;
}
