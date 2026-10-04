// A model in the text dialect writes its code in a fenced block among its words
// (PLAN decision 4). The code becomes a cell; the chat shows only the words —
// including while a fence is still being written and has not closed.
const CLOSED_FENCE = /```[\w-]*\n[\s\S]*?```/g;
const OPEN_FENCE = /```[\s\S]*$/;

export function wordsOnly(text: string): string {
  const withoutClosed = text.replace(CLOSED_FENCE, "");
  const withoutOpen = withoutClosed.replace(OPEN_FENCE, "");
  return withoutOpen.replace(/\n{3,}/g, "\n\n").trim();
}
