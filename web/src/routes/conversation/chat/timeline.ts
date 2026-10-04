import type { FileInfo, Message } from "@/api/conversation-detail";
import type { RestartReason } from "@/api/events";

// design.md §2.4: the chat interleaves, by time, the files arriving, the
// messages, and — while the page is open — the kernel restarting.

export type TimelineItem =
  | { kind: "file"; at: string; file: FileInfo }
  | { kind: "message"; at: string; message: Message }
  | { kind: "restart"; at: string; reason: RestartReason };

export interface Restart {
  at: string;
  reason: RestartReason;
}

export function buildTimeline(
  files: FileInfo[],
  messages: Message[],
  restarts: Restart[] = [],
): TimelineItem[] {
  const items: TimelineItem[] = [];
  for (const file of files) {
    items.push({ kind: "file", at: file.createdAt, file });
  }
  for (const message of messages) {
    items.push({ kind: "message", at: message.createdAt, message });
  }
  for (const restart of restarts) {
    items.push({ kind: "restart", at: restart.at, reason: restart.reason });
  }

  // ISO-8601 in UTC sorts as text; a stable sort keeps same-instant items in
  // the order the API gave them.
  return items.toSorted((a, b) => a.at.localeCompare(b.at));
}
