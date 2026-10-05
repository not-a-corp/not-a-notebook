import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, NotebookText } from "lucide-react";
import { useEffect, useState } from "react";

import { getConversationDetail } from "@/api/conversation-detail";
import { ApiError } from "@/api/errors";
import { cancelRun } from "@/api/runs";
import { toast } from "@/components/toaster";
import { plural } from "@/lib/format";
import { sentenceForError } from "@/lib/words";

import { ask } from "./ask";
import { ChatPane } from "./chat/chat-pane";
import { ConversationHeader } from "./conversation-header";
import { ProfileDrawer } from "./files/profile-drawer";
import { useUpload } from "./files/use-upload";
import { conversationKey, useLiveRun } from "./live/use-live-run";
import { NotebookPane } from "./notebook/notebook-pane";
import { Pane } from "./panes";
import { takePendingStart } from "./pending";

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
  const { upload, uploading } = useUpload(conversationId);
  const [openFileId, setOpenFileId] = useState<string | null>(null);
  // The drawer slides over the notebook pane, inside it (design.md §3.6).
  const [notebookPane, setNotebookPane] = useState<HTMLElement | null>(null);
  const queryClient = useQueryClient();
  const loaded = conversation.data !== undefined;

  // A conversation started on the home screen: its files go up first, each
  // profiled, then its question is asked (design.md §2.3).
  useEffect(() => {
    if (!loaded) {
      return;
    }
    const start = takePendingStart(conversationId);
    if (start === null) {
      return;
    }

    async function begin(files: File[], text: string) {
      await upload(files);
      if (text === "") {
        return;
      }
      try {
        await ask(queryClient, conversationId, text);
      } catch (error) {
        toast(sentenceForError(error));
      }
    }

    void begin(start.files, start.text);
  }, [loaded, conversationId, queryClient, upload]);

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
  const openFile = detail.files.find((file) => file.id === openFileId) ?? null;

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <ConversationHeader conversation={detail} live={live} />
      <div className="flex min-h-0 flex-1">
        <Pane icon={MessageSquare} label="Chat" className="flex w-2/5 flex-none flex-col">
          <ChatPane
            conversation={detail}
            live={live}
            connection={connection}
            uploading={uploading}
            onShowCell={showCell}
            onOpenFile={setOpenFileId}
            onUpload={(files) => void upload(files)}
          />
        </Pane>
        <div className="w-px flex-none bg-border" />
        <Pane
          icon={NotebookText}
          label="Notebook"
          detail={plural(detail.cells.length, "cell", "cells")}
          className="relative flex min-w-0 flex-1 flex-col"
          ref={setNotebookPane}
        >
          <NotebookPane cells={detail.cells} live={live} onStop={stop} />
          <ProfileDrawer
            conversationId={detail.id}
            file={openFile}
            container={notebookPane}
            busy={detail.activeRunId !== null}
            onClose={() => {
              setOpenFileId(null);
            }}
          />
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
