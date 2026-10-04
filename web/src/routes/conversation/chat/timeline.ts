import type { FileInfo, Message } from "@/api/conversation-detail";

// design.md §2.4: the chat interleaves, by time, the files arriving and the
// messages.

export type TimelineItem =
  { kind: "file"; at: string; file: FileInfo } | { kind: "message"; at: string; message: Message };

export function buildTimeline(files: FileInfo[], messages: Message[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  for (const file of files) {
    items.push({ kind: "file", at: file.createdAt, file });
  }
  for (const message of messages) {
    items.push({ kind: "message", at: message.createdAt, message });
  }

  // ISO-8601 in UTC sorts as text; a stable sort keeps same-instant items in
  // the order the API gave them.
  return items.toSorted((a, b) => a.at.localeCompare(b.at));
}
