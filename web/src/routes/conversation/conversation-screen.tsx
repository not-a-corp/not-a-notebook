import { useQuery } from "@tanstack/react-query";

import { getConversation } from "@/api/conversations";
import { ApiError } from "@/api/errors";
import { sentenceForError } from "@/lib/words";

import { ConversationHeader } from "./conversation-header";

export function ConversationScreen({ conversationId }: { conversationId: string }) {
  const conversation = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => getConversation(conversationId),
  });

  if (conversation.isError) {
    return <QuietPage error={conversation.error} />;
  }

  if (conversation.data === undefined) {
    return null;
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <ConversationHeader conversation={conversation.data} />
      <div className="min-h-0 flex-1" />
    </div>
  );
}

// design.md §6: someone else's conversation, or none, is a quiet page.
function QuietPage({ error }: { error: Error }) {
  let text = sentenceForError(error);
  if (error instanceof ApiError && error.code === "CONVERSATION_NOT_FOUND") {
    text = "This conversation doesn't exist, or isn't yours.";
  }

  return (
    <div className="flex flex-1 items-center justify-center text-sm text-text-muted">{text}</div>
  );
}
