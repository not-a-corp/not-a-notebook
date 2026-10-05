import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { ConversationDetail } from "@/api/conversation-detail";
import { isAcceptedFile, uploadFile } from "@/api/files";
import { waitForRun } from "@/api/wait-for-run";
import { toast } from "@/components/toaster";
import { sentenceFor, sentenceForError } from "@/lib/words";

import { conversationKey } from "../live/use-live-run";

// Uploads files into a conversation, one at a time: each is profiled in the
// sandbox, and that profile is the conversation's one run until it ends. The
// file appears at once, its profile pending; the stream fills it in.
export function useUpload(conversationId: string) {
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);

  async function upload(files: File[]) {
    setUploading(true);
    const controller = new AbortController();
    try {
      for (const file of files) {
        if (!isAcceptedFile(file.name)) {
          toast(sentenceFor("UNSUPPORTED_FILE_TYPE", ""));
          continue;
        }

        let runId: string;
        try {
          const accepted = await uploadFile(conversationId, file);
          runId = accepted.runId;
          queryClient.setQueryData<ConversationDetail>(
            conversationKey(conversationId),
            (current) => {
              if (current === undefined) {
                return current;
              }
              return {
                id: current.id,
                title: current.title,
                modelId: current.modelId,
                kernel: current.kernel,
                activeRunId: accepted.runId,
                files: [...current.files, accepted.file],
                messages: current.messages,
                cells: current.cells,
              };
            },
          );
        } catch (error) {
          toast(sentenceForError(error, { name: file.name }));
          continue;
        }

        await waitForRun(runId, controller.signal);
      }
    } finally {
      setUploading(false);
    }
  }

  return { upload, uploading };
}
