import { useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Plus, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  summarizeProfile,
  type Cell,
  type ConversationDetail,
  type FileInfo,
  type Message,
} from "@/api/conversation-detail";
import type { RestartReason } from "@/api/events";
import { ACCEPTED_EXTENSIONS } from "@/api/files";
import type { Connection } from "@/api/runs";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { formatBytes, formatClock, formatCount, plural } from "@/lib/format";
import { restartReason } from "@/lib/kernel-words";
import { useStickToBottom } from "@/lib/use-stick-to-bottom";
import { sentenceFor, sentenceForError } from "@/lib/words";

import { ask } from "../ask";
import type { LiveRun } from "../live/live-run";
import { ActivityLine } from "./activity";
import { Composer } from "./composer";
import { GroundingBadge } from "./grounding-badge";
import { buildTimeline, type Restart } from "./timeline";
import { wordsOnly } from "./words-only";

interface ChatPaneProps {
  conversation: ConversationDetail;
  live: LiveRun | null;
  connection: Connection;
  uploading: boolean;
  onShowCell: (cellId: string) => void;
  onOpenFile: (fileId: string) => void;
  onUpload: (files: File[]) => void;
}

// design.md §2.4 — the chat pane: files bar, the timeline, the composer.
export function ChatPane({
  conversation,
  live,
  connection,
  uploading,
  onShowCell,
  onOpenFile,
  onUpload,
}: ChatPaneProps) {
  const picker = useRef<HTMLInputElement>(null);
  const busy = conversation.activeRunId !== null || uploading;

  function pickFiles() {
    picker.current?.click();
  }

  const restarts: Restart[] = [];
  if (live?.restarted != null) {
    restarts.push(live.restarted);
  }
  const timeline = buildTimeline(conversation.files, conversation.messages, restarts);
  const running = conversation.activeRunId !== null;
  const lastMessageId = conversation.messages.at(-1)?.id;
  const scroller = useRef<HTMLDivElement>(null);
  useStickToBottom(scroller, [timeline.length, live?.steps, live?.activity]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <input
        ref={picker}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS.join(",")}
        className="hidden"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (files.length > 0) {
            onUpload(files);
          }
        }}
      />
      {conversation.files.length > 0 && (
        <FilesBar
          files={conversation.files}
          busy={busy}
          onOpenFile={onOpenFile}
          onAdd={pickFiles}
        />
      )}
      <div ref={scroller} className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {/* Anchored to the bottom: a short conversation sits by the composer. */}
        <div className="mt-auto flex flex-col gap-6 p-6">
          {timeline.map((item) => {
            if (item.kind === "file") {
              return (
                <FileArrived key={`file-${item.file.id}`} file={item.file} onOpen={onOpenFile} />
              );
            }
            if (item.kind === "restart") {
              return (
                <RestartDivider key={`restart-${item.at}`} at={item.at} reason={item.reason} />
              );
            }
            // Options are buttons only while the question is the last word and
            // nothing is running: an old question's choices are history.
            const answerable =
              item.message.id === lastMessageId && !busy && conversation.modelId !== null;
            return (
              <MessageView
                key={item.message.id}
                message={item.message}
                cells={conversation.cells}
                conversationId={conversation.id}
                answerable={answerable}
                onShowCell={onShowCell}
              />
            );
          })}
          {running && live?.kind === "message" && (
            <LiveMessage live={live} connection={connection} onShowCell={onShowCell} />
          )}
          {live !== null && <RunEnding live={live} />}
        </div>
      </div>
      <Composer conversation={conversation} uploadDisabled={busy} onUpload={pickFiles} />
    </div>
  );
}

// The analyst at work, inside its message (design.md §2.4). The activity line
// is announced politely; the streamed words are not, chunk by chunk (§8).
function LiveMessage({
  live,
  connection,
  onShowCell,
}: {
  live: LiveRun;
  connection: Connection;
  onShowCell: (cellId: string) => void;
}) {
  const words = live.steps
    .map(wordsOnly)
    .filter((step) => step !== "")
    .join("\n\n");

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs font-medium text-text-muted">Analyst</div>
      {words !== "" && <AnswerText text={words} />}
      <div aria-live="polite">
        <ActivityLine activity={live.activity} connection={connection} onShowCell={onShowCell} />
      </div>
    </div>
  );
}

// How a run ended when it did not end with an answer: our failure, a stop, or
// events lost on the way (design.md §4, §6).
function RunEnding({ live }: { live: LiveRun }) {
  return (
    <>
      {live.failure !== null && (
        <p role="alert" className="border-l-2 border-danger pl-3 text-sm text-danger">
          {sentenceFor(live.failure.code, live.failure.message)}
          {live.failure.errorId !== null && ` Reference: ${live.failure.errorId}.`}
        </p>
      )}
      {live.finished === "cancelled" && live.kind === "message" && (
        <p className="text-sm text-text-muted">Stopped.</p>
      )}
      {live.finished === "timed_out" && (
        <p className="text-sm text-text-muted">The run reached its time limit and was stopped.</p>
      )}
      {live.lost && (
        <p className="text-sm text-warning">
          Some updates were lost —{" "}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => {
              window.location.reload();
            }}
          >
            reload
          </button>
        </p>
      )}
    </>
  );
}

function RestartDivider({ at, reason }: { at: string; reason: RestartReason }) {
  return (
    <div className="flex items-center gap-3 text-xs text-text-muted">
      <span className="h-px flex-1 bg-border" />
      <span>
        Kernel restarted · {restartReason(reason)} · {formatClock(at)}
      </span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

function FilesBar({
  files,
  busy,
  onOpenFile,
  onAdd,
}: {
  files: FileInfo[];
  busy: boolean;
  onOpenFile: (fileId: string) => void;
  onAdd: () => void;
}) {
  return (
    <div className="flex flex-none flex-wrap items-center gap-2 border-b border-border px-4 py-2">
      {files.map((file) => (
        <FileChip key={file.id} file={file} onOpen={onOpenFile} />
      ))}
      <Tooltip label="Add a file">
        <button
          type="button"
          aria-label="Add a file"
          disabled={busy}
          className="flex size-7 items-center justify-center rounded-md border border-dashed border-text/25 text-text-muted hover:bg-text/8 disabled:opacity-50"
          onClick={onAdd}
        >
          <Plus className="size-3.5" />
        </button>
      </Tooltip>
    </div>
  );
}

function FileChip({ file, onOpen }: { file: FileInfo; onOpen: (fileId: string) => void }) {
  return (
    <button
      type="button"
      aria-label={`Profile of ${file.name}`}
      className="flex h-7 items-center gap-2 rounded-md border border-border bg-surface-raised pr-1 pl-2 hover:bg-text/8"
      onClick={() => {
        onOpen(file.id);
      }}
    >
      <FileSpreadsheet className="size-3.5 text-text-muted" />
      <span className="text-sm font-medium">{file.name}</span>
      <span className="text-xs text-text-muted">{formatBytes(file.bytes)}</span>
      <FindingsBadge file={file} />
    </button>
  );
}

// Amber with findings, grey when clean, a pulsing dot while the profile runs.
function FindingsBadge({ file }: { file: FileInfo }) {
  if (file.profile === null) {
    return (
      <span className="flex h-5 items-center gap-1 px-1 text-xs text-text-muted">
        <span className="size-1.5 animate-pulse rounded-full bg-accent" />
        profiling
      </span>
    );
  }

  const summary = summarizeProfile(file.profile);
  if (!summary.readable) {
    return (
      <span className="flex h-5 items-center rounded-sm bg-danger/14 px-1 text-xs font-medium text-danger">
        unreadable
      </span>
    );
  }
  if (summary.findings === 0) {
    return (
      <span className="flex h-5 items-center rounded-sm bg-text/8 px-1 text-xs font-medium text-text-muted">
        clean
      </span>
    );
  }

  return (
    <span className="flex h-5 items-center gap-1 rounded-sm bg-warning/14 px-1 text-xs font-medium text-warning">
      <TriangleAlert className="size-3" />
      {plural(summary.findings, "finding", "findings")}
    </span>
  );
}

function FileArrived({ file, onOpen }: { file: FileInfo; onOpen: (fileId: string) => void }) {
  const facts = [`${file.name} added`];
  if (file.profile !== null) {
    const summary = summarizeProfile(file.profile);
    if (summary.readable) {
      facts.push(`${formatCount(summary.rows)} rows × ${formatCount(summary.columns)} columns`);
      facts.push(plural(summary.findings, "finding", "findings"));
    } else {
      facts.push("couldn't be read");
    }
  }

  return (
    <div className="flex items-center gap-2 text-xs text-text-muted">
      <FileSpreadsheet className="size-3.5" />
      <span className="flex-1">{facts.join(" · ")}</span>
      {file.profile !== null && (
        <button
          type="button"
          className="font-medium text-accent"
          onClick={() => {
            onOpen(file.id);
          }}
        >
          Open profile
        </button>
      )}
    </div>
  );
}

function MessageView({
  message,
  cells,
  conversationId,
  answerable,
  onShowCell,
}: {
  message: Message;
  cells: Cell[];
  conversationId: string;
  answerable: boolean;
  onShowCell: (cellId: string) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="max-w-[85%] self-end rounded-xl bg-surface px-3 py-2 whitespace-pre-wrap">
        {message.text}
      </div>
    );
  }

  // A question back is styled as one: a distinct left rule (§2.4).
  if (message.kind === "question") {
    return (
      <div className="flex flex-col gap-3 border-l-2 border-accent pl-3">
        <div className="text-xs font-medium text-text-muted">The analyst asks</div>
        <AnswerText text={message.text} />
        {answerable && message.options !== null && message.options.length > 0 && (
          <OptionButtons options={message.options} conversationId={conversationId} />
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs font-medium text-text-muted">Analyst</div>
      <AnswerText text={message.text} />
      {message.grounding !== null && (
        <GroundingBadge
          message={message}
          grounding={message.grounding}
          cells={cells}
          onShowCell={onShowCell}
        />
      )}
    </div>
  );
}

// The analyst's suggested replies. A click is an ordinary message with that text;
// the composer below still takes the user's own words.
function OptionButtons({ options, conversationId }: { options: string[]; conversationId: string }) {
  const queryClient = useQueryClient();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick(option: string) {
    if (sending) {
      return;
    }
    setSending(true);
    setError(null);
    try {
      await ask(queryClient, conversationId, option);
    } catch (failure) {
      setError(sentenceForError(failure));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div role="group" aria-label="Suggested replies" className="flex flex-wrap gap-2">
        {options.map((option) => (
          <Button
            key={option}
            variant="secondary"
            size="compact"
            disabled={sending}
            onClick={() => void pick(option)}
          >
            {option}
          </Button>
        ))}
      </div>
      {error !== null && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

// The analyst's words read like a document (§2.4): markdown, its tables
// rendered, its lead line a size up.
export function AnswerText({ text }: { text: string }) {
  return (
    <div className="answer flex flex-col gap-3 text-pretty [&>p:first-child]:text-md">
      <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
    </div>
  );
}
