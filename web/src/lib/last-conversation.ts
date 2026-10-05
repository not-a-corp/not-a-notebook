// Settings' back arrow (and Escape) go to the last conversation (design.md
// §2.6). Kept for the tab, which is where "last" means anything.

const KEY = "not-a-notebook.last-conversation";

export function rememberConversation(conversationId: string): void {
  try {
    sessionStorage.setItem(KEY, conversationId);
  } catch {
    // Without storage, the arrow goes home.
  }
}

export function lastConversation(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}
