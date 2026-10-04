import { useQueryClient } from "@tanstack/react-query";
import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import type { ConversationDetail } from "@/api/conversation-detail";
import { cancelRun, sendMessage } from "@/api/runs";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { sentenceForError } from "@/lib/words";

import { conversationKey } from "../live/use-live-run";

const MAX_HEIGHT = 240;

// design.md §2.4 — the composer at the bottom of the chat.
export function Composer({ conversation }: { conversation: ConversationDetail }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);

  const runId = conversation.activeRunId;
  const live = runId !== null;
  const noModel = conversation.modelId === null;
  const lastMessage = conversation.messages.at(-1);
  const answering = lastMessage?.kind === "question";

  let placeholder = "Ask a follow-up…";
  if (conversation.messages.length === 0) {
    placeholder = "Ask a question about your data…";
  }
  if (answering) {
    placeholder = "Answer the question…";
  }
  if (noModel) {
    placeholder = "Pick a model to ask questions.";
  }

  // A question back focuses the composer (design.md §2.4).
  useEffect(() => {
    if (answering && !live) {
      textarea.current?.focus();
    }
  }, [answering, live]);

  // Grows with the text, up to a limit, then scrolls.
  useEffect(() => {
    const element = textarea.current;
    if (element === null) {
      return;
    }
    element.style.height = "auto";
    element.style.height = `${String(Math.min(element.scrollHeight, MAX_HEIGHT))}px`;
  }, [text]);

  async function send() {
    const question = text.trim();
    if (question === "" || live || noModel || sending) {
      return;
    }

    setSending(true);
    setError(null);
    try {
      const accepted = await sendMessage(conversation.id, question);
      setText("");
      queryClient.setQueryData<ConversationDetail>(conversationKey(conversation.id), (current) => {
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
    } catch (failure) {
      setError(sentenceForError(failure));
    } finally {
      setSending(false);
    }
  }

  async function stop() {
    if (runId === null) {
      return;
    }
    try {
      await cancelRun(runId);
    } catch (failure) {
      setError(sentenceForError(failure));
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
      return;
    }
    if (event.key === "Escape" && live) {
      event.preventDefault();
      void stop();
    }
  }

  const canSend = text.trim() !== "" && !noModel && !sending;
  let sendTooltip = "Send";
  if (noModel) {
    sendTooltip = "Pick a model for this conversation first";
  }

  return (
    <div className="flex flex-none flex-col gap-2 px-4 pb-4">
      {error !== null && (
        <p role="alert" className="px-1 text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface-raised pt-3 pr-2 pb-2 pl-3">
        <textarea
          ref={textarea}
          value={text}
          rows={2}
          disabled={noModel}
          placeholder={placeholder}
          aria-label="Message"
          className="min-h-11 resize-none bg-transparent outline-none placeholder:text-text-muted disabled:cursor-not-allowed"
          onChange={(event) => {
            setText(event.target.value);
          }}
          onKeyDown={onKeyDown}
        />
        <div className="flex items-center gap-2">
          <div className="flex-1" />
          {live && (
            <Button variant="secondary" className="pr-2 pl-3" onClick={() => void stop()}>
              <span className="size-2.5 rounded-xs bg-text" />
              Stop
              <kbd className="rounded-sm border border-border px-1 font-mono text-xs font-normal text-text-muted">
                Esc
              </kbd>
            </Button>
          )}
          {!live && (
            <Tooltip label={sendTooltip}>
              <span>
                <Button
                  size="icon"
                  aria-label="Send"
                  className="text-on-accent disabled:bg-text/8 disabled:text-text-muted disabled:opacity-100"
                  disabled={!canSend}
                  onClick={() => void send()}
                >
                  <ArrowUp className="size-4" strokeWidth={2} />
                </Button>
              </span>
            </Tooltip>
          )}
        </div>
      </div>
      <div className="px-1 text-xs text-text-muted">Enter to send · Shift+Enter for a new line</div>
    </div>
  );
}
