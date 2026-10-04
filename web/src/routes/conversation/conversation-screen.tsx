import { useQuery } from "@tanstack/react-query";
import { MessageSquare, NotebookText } from "lucide-react";

import { getConversationDetail } from "@/api/conversation-detail";
import { ApiError } from "@/api/errors";
import { plural } from "@/lib/format";
import { sentenceForError } from "@/lib/words";

import { cancelRun } from "@/api/runs";

import { ChatPane } from "./chat/chat-pane";
import { ConversationHeader } from "./conversation-header";
import { conversationKey, useLiveRun } from "./live/use-live-run";
import { NotebookPane } from "./notebook/notebook-pane";
import { Pane } from "./panes";

function showCell(cellId: string) {
  document.getElementById(`cell-${cellId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function ConversationScreen({ conversationId }: { conversationId: string }) {
  const conversation = useQuery({
    queryKey: conversationKey(conversationId),
    queryFn: () => getConversationDetail(conversationId),
  });
  const activeRunId = conversation.data?.activeRunId ?? null;
  const { live, connection } = useLiveRun(conversationId, activeRunId);

  function stop() {
    if (activeRunId !== null) {
      void cancelRun(activeRunId);
    }
  }

  if (conversation.isError) {
    return <QuietPage error={conversation.error} />;
  }

  if (conversation.data === undefined) {
    return null;
  }

  const detail = conversation.data;

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <ConversationHeader conversation={detail} live={live} />
      <div className="flex min-h-0 flex-1">
        <Pane icon={MessageSquare} label="Chat" className="flex w-2/5 flex-none flex-col">
          <ChatPane
            conversation={detail}
            live={live}
            connection={connection}
            onShowCell={showCell}
          />
        </Pane>
        <div className="w-px flex-none bg-border" />
        <Pane
          icon={NotebookText}
          label="Notebook"
          detail={plural(detail.cells.length, "cell", "cells")}
          className="flex min-w-0 flex-1 flex-col"
        >
          <NotebookPane cells={detail.cells} live={live} onStop={stop} />
        </Pane>
      </div>
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
