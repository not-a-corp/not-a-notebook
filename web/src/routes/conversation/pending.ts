// What the home composer hands to the conversation it just created: the files
// to upload and the question to ask, in that order (design.md §2.3). Kept in
// memory for the one navigation between them, and taken once.

export interface PendingStart {
  files: File[];
  text: string;
}

const pending = new Map<string, PendingStart>();

export function setPendingStart(conversationId: string, start: PendingStart): void {
  pending.set(conversationId, start);
}

export function takePendingStart(conversationId: string): PendingStart | null {
  const start = pending.get(conversationId) ?? null;
  pending.delete(conversationId);
  return start;
}
