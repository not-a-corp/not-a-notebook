import { FileSpreadsheet, TriangleAlert } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  summarizeProfile,
  type ConversationDetail,
  type FileInfo,
  type Message,
} from "@/api/conversation-detail";
import { formatBytes, formatCount, plural } from "@/lib/format";

import { buildTimeline } from "./timeline";

// design.md §2.4 — the chat pane: files bar, then the timeline.
export function ChatPane({ conversation }: { conversation: ConversationDetail }) {
  const timeline = buildTimeline(conversation.files, conversation.messages);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {conversation.files.length > 0 && <FilesBar files={conversation.files} />}
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {/* Anchored to the bottom: a short conversation sits by the composer. */}
        <div className="mt-auto flex flex-col gap-6 p-6">
          {timeline.map((item) => {
            if (item.kind === "file") {
              return <FileArrived key={`file-${item.file.id}`} file={item.file} />;
            }
            return <MessageView key={item.message.id} message={item.message} />;
          })}
        </div>
      </div>
    </div>
  );
}

function FilesBar({ files }: { files: FileInfo[] }) {
  return (
    <div className="flex flex-none flex-wrap items-center gap-2 border-b border-border px-4 py-2">
      {files.map((file) => (
        <FileChip key={file.id} file={file} />
      ))}
    </div>
  );
}

function FileChip({ file }: { file: FileInfo }) {
  return (
    <div className="flex h-7 items-center gap-2 rounded-md border border-border bg-surface-raised pr-1 pl-2">
      <FileSpreadsheet className="size-3.5 text-text-muted" />
      <span className="text-sm font-medium">{file.name}</span>
      <span className="text-xs text-text-muted">{formatBytes(file.bytes)}</span>
      <FindingsBadge file={file} />
    </div>
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

function FileArrived({ file }: { file: FileInfo }) {
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
    </div>
  );
}

function MessageView({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="max-w-[85%] self-end rounded-xl bg-surface px-3 py-2 whitespace-pre-wrap">
        {message.text}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs font-medium text-text-muted">Analyst</div>
      <AnswerText text={message.text} />
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
