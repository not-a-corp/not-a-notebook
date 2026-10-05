import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ArrowUp, ChevronDown, FileSpreadsheet, Paperclip, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent } from "react";

import { createConversation } from "@/api/conversations";
import { ACCEPTED_EXTENSIONS, isAcceptedFile } from "@/api/files";
import { listModels, type Model } from "@/api/models";
import { toast } from "@/components/toaster";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip } from "@/components/ui/tooltip";
import { formatBytes } from "@/lib/format";
import { readPreference, savePreference } from "@/lib/preferences";
import { sentenceFor, sentenceForError } from "@/lib/words";

import { setPendingStart } from "../conversation/pending";
import { HomeBackground } from "./home-background";

const TITLE_LENGTH = 60;
const MAX_HEIGHT = 320;

// A conversation is named after what it began with: the question's first
// words, or the file's name when a file was sent alone.
export function titleFor(text: string, files: File[]): string {
  const question = text.trim().replace(/\s+/g, " ");
  if (question !== "") {
    if (question.length <= TITLE_LENGTH) {
      return question;
    }
    return `${question.slice(0, TITLE_LENGTH - 1).trimEnd()}…`;
  }

  const first = files[0];
  if (first !== undefined) {
    return first.name;
  }
  return "Untitled";
}

// The model last picked here, if it still exists; else the first one offered.
function defaultModel(models: Model[]): Model | null {
  const remembered = readPreference("model");
  const found = models.find((model) => model.id === remembered);
  if (found !== undefined) {
    return found;
  }
  return models[0] ?? null;
}

function hasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer.types).includes("Files");
}

// design.md §2.3 — a new conversation: one centred composer on a background of
// its own. Nothing is created until something is sent.
export function Home() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const models = useQuery({ queryKey: ["models"], queryFn: listModels });
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [modelId, setModelId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [sending, setSending] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  // dragenter and dragleave fire for every child crossed; only the outermost pair counts.
  const dragDepth = useRef(0);

  const all = models.data ?? [];
  let model = all.find((candidate) => candidate.id === modelId) ?? null;
  model ??= defaultModel(all);

  useEffect(() => {
    textarea.current?.focus();
  }, []);

  useEffect(() => {
    const element = textarea.current;
    if (element === null) {
      return;
    }
    element.style.height = "auto";
    element.style.height = `${String(Math.min(element.scrollHeight, MAX_HEIGHT))}px`;
  }, [text]);

  function attach(added: File[]) {
    const accepted: File[] = [];
    for (const file of added) {
      if (!isAcceptedFile(file.name)) {
        toast(sentenceFor("UNSUPPORTED_FILE_TYPE", ""));
        continue;
      }
      if (files.some((known) => known.name === file.name)) {
        continue;
      }
      accepted.push(file);
    }
    setFiles([...files, ...accepted]);
  }

  // A file can be sent alone, with no question (design.md §2.3).
  const canSend = (text.trim() !== "" || files.length > 0) && model !== null && !sending;

  async function send() {
    if (!canSend || model === null) {
      return;
    }

    setSending(true);
    try {
      const created = await createConversation({
        title: titleFor(text, files),
        modelId: model.id,
      });
      setPendingStart(created.id, { files, text: text.trim() });
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      await navigate({ to: "/c/$conversationId", params: { conversationId: created.id } });
    } catch (error) {
      toast(sentenceForError(error));
      setSending(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  }

  let sendTooltip = "Send";
  if (model === null) {
    sendTooltip = "Add a model in Settings first";
  } else if (!canSend) {
    sendTooltip = "Send — type a question or attach a file first";
  }

  return (
    <div
      className="relative flex min-w-0 flex-1 flex-col items-center justify-center gap-6 overflow-hidden px-4 pb-12"
      onDragEnter={(event) => {
        if (!hasFiles(event)) {
          return;
        }
        event.preventDefault();
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => {
        if (hasFiles(event)) {
          event.preventDefault();
        }
      }}
      onDragLeave={() => {
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) {
          setDragging(false);
        }
      }}
      onDrop={(event) => {
        event.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        attach(Array.from(event.dataTransfer.files));
        textarea.current?.focus();
      }}
    >
      <HomeBackground />

      <h1 className="relative text-xl font-medium tracking-[-0.2px]">
        What do you want to know about your data?
      </h1>

      <div className="relative flex w-[720px] max-w-full flex-col gap-3 rounded-2xl border border-border bg-surface-raised pt-4 pr-3 pb-3 pl-4 shadow-overlay">
        {/* Focus shows as the caret only: no ring around the one thing on the page (§2.3). */}
        <textarea
          ref={textarea}
          value={text}
          rows={3}
          aria-label="Ask a question"
          placeholder="Ask a question, or drop a file…"
          className="min-h-[66px] resize-none bg-transparent outline-none placeholder:text-text-muted"
          onChange={(event) => {
            setText(event.target.value);
          }}
          onKeyDown={onKeyDown}
        />
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={picker}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="hidden"
            onChange={(event) => {
              attach(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
          <Button
            variant="ghost"
            className="pr-3 pl-2 text-text-muted"
            onClick={() => {
              picker.current?.click();
            }}
          >
            <Paperclip className="size-4" />
            <span className="text-text">Attach</span>
          </Button>
          {files.map((file) => (
            <div
              key={file.name}
              className="flex h-7 items-center gap-2 rounded-md border border-border bg-surface pr-1 pl-2"
            >
              <FileSpreadsheet className="size-3.5 text-text-muted" />
              <span className="text-sm font-medium">{file.name}</span>
              <span className="text-xs text-text-muted">{formatBytes(file.size)}</span>
              <Tooltip label={`Remove ${file.name}`}>
                <button
                  type="button"
                  aria-label={`Remove ${file.name}`}
                  className="flex size-5 items-center justify-center rounded-sm text-text-muted hover:bg-text/8"
                  onClick={() => {
                    setFiles(files.filter((known) => known !== file));
                  }}
                >
                  <X className="size-3.5" />
                </button>
              </Tooltip>
            </div>
          ))}
          <div className="flex-1" />
          <ModelPicker
            models={all}
            model={model}
            onPick={(id) => {
              setModelId(id);
              savePreference("model", id);
            }}
          />
          <Tooltip label={sendTooltip}>
            <span>
              <Button
                size="icon"
                aria-label="Send"
                className="rounded-full text-on-accent disabled:bg-text/8 disabled:text-text-muted disabled:opacity-100"
                disabled={!canSend}
                onClick={() => void send()}
              >
                <ArrowUp className="size-4" strokeWidth={2} />
              </Button>
            </span>
          </Tooltip>
        </div>
      </div>

      <p className="relative text-sm text-text-muted">
        CSV, TSV, Excel or Parquet — drop it anywhere
      </p>

      {dragging && <DropOverlay />}
    </div>
  );
}

// §2.3: a dashed outline inset 12 px, a tint, and the label set above the
// composer so the composer stays readable underneath.
function DropOverlay() {
  return (
    <>
      <div className="pointer-events-none absolute inset-3 rounded-xl border-2 border-dashed border-accent bg-accent-soft/55" />
      <div className="pointer-events-none absolute top-[200px] left-1/2 flex h-10 -translate-x-1/2 items-center gap-2 rounded-lg border border-border bg-surface-raised px-4 text-md font-medium shadow-overlay">
        <Upload className="size-5 text-accent" />
        Drop to attach
      </div>
    </>
  );
}

function ModelPicker({
  models,
  model,
  onPick,
}: {
  models: Model[];
  model: Model | null;
  onPick: (modelId: string) => void;
}) {
  let label = "No model";
  if (model !== null) {
    label = model.name;
  }

  return (
    <DropdownMenu>
      <Tooltip label="Model for this conversation">
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="pr-2 pl-3">
            {label}
            <ChevronDown className="size-4 text-text-muted" />
          </Button>
        </DropdownMenuTrigger>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Model</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={model?.id ?? ""} onValueChange={onPick}>
          {models.map((candidate) => (
            <DropdownMenuRadioItem key={candidate.id} value={candidate.id}>
              {candidate.name}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        {models.length === 0 && (
          <p className="px-2 py-1 text-sm text-text-muted">No models yet. Add one in Settings.</p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
