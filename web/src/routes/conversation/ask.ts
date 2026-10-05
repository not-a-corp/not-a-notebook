import type { QueryClient } from "@tanstack/react-query";

import type { ConversationDetail } from "@/api/conversation-detail";
import { sendMessage } from "@/api/runs";

import { conversationKey } from "./live/use-live-run";

// Posts a message and puts it, with its run, in the cached conversation — the
// run's stream starts following from there.
export async function ask(
  queryClient: QueryClient,
  conversationId: string,
  text: string,
): Promise<void> {
  const accepted = await sendMessage(conversationId, text);

  // A read of the conversation still in flight was asked before this run
  // existed; landing after this write, it would drop the run and the screen
  // would stop following it. It is cancelled, and the cache written once.
  await queryClient.cancelQueries({ queryKey: conversationKey(conversationId) });
  queryClient.setQueryData<ConversationDetail>(conversationKey(conversationId), (current) => {
    if (current === undefined) {
      return current;
    }
    return {
      id: current.id,
      title: current.title,
      modelId: current.modelId,
      kernel: current.kernel,
      activeRunId: accepted.runId,
      files: current.files,
      messages: [...current.messages, accepted.message],
      cells: current.cells,
    };
  });
}
