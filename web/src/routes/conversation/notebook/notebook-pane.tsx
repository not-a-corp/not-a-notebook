import { Play, Plus, RotateCcw, TriangleAlert } from "lucide-react";
import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import type { Cell, ConversationDetail } from "@/api/conversation-detail";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/toaster";
import { plural } from "@/lib/format";
import { useStickToBottom } from "@/lib/use-stick-to-bottom";
import { sentenceFor, sentenceForError } from "@/lib/words";

import type { FailedAttempt, LiveRun } from "../live/live-run";
import { loadFailedAttempts } from "./attempt-history";
import { CellView } from "./cell-view";
import { ShortcutsDialog } from "./shortcuts-dialog";
import type { NotebookActions } from "./use-notebook-actions";

interface NotebookPaneProps {
  conversation: ConversationDetail;
  live: LiveRun | null;
  actions: NotebookActions;
  onStop: () => void;
}

// Keys pressed twice: D D deletes (design.md §7), and only within this window.
const DOUBLE_PRESS_MS = 600;

// design.md §2.5 — the notebook: a banner when something needs saying, then
// the cells, workable from the keyboard alone.
export function NotebookPane({ conversation, live, actions, onStop }: NotebookPaneProps) {
  const cells = conversation.cells;
  const busy = conversation.activeRunId !== null;
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [history, setHistory] = useState<Record<string, FailedAttempt[]>>({});
  const [deleting, setDeleting] = useState<Cell | null>(null);
  const [shortcuts, setShortcuts] = useState(false);
  const lastKey = useRef<{ key: string; at: number } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  useStickToBottom(scroller, cells.length);

  function draftOf(cell: Cell): string {
    return drafts[cell.id] ?? cell.source;
  }

  // Functional updates: these run after awaits, when `drafts` may be stale.
  function setDraft(cell: Cell, source: string) {
    setDrafts((current) => {
      const next = structuredClone(current);
      next[cell.id] = source;
      return next;
    });
  }

  function forgetDraft(cell: Cell) {
    setDrafts((current) => {
      const kept = Object.entries(current).filter(([cellId]) => cellId !== cell.id);
      return Object.fromEntries(kept);
    });
  }

  function focusCell(cellId: string) {
    setFocusedId(cellId);
    const element = document.getElementById(`cell-${cellId}`);
    element?.focus({ preventScroll: true });
    element?.scrollIntoView({ block: "nearest" });
  }

  async function leave(cell: Cell) {
    setEditingId(null);
    focusCell(cell.id);
    const saved = await actions.save(cell, draftOf(cell));
    if (saved) {
      forgetDraft(cell);
    }
  }

  // Returns whether the cell is running now. Nothing else can run while a run
  // is in progress (api.md, One run at a time): the editor stays open, its
  // text kept, and the person is told why.
  async function run(cell: Cell): Promise<boolean> {
    if (busy) {
      toast(sentenceFor("CONVERSATION_BUSY", ""));
      return false;
    }
    setEditingId(null);
    focusCell(cell.id);
    const started = await actions.run(cell, draftOf(cell));
    if (!started) {
      setEditingId(cell.id);
      return false;
    }
    forgetDraft(cell);
    return true;
  }

  async function runAndNext(cell: Cell) {
    const started = await run(cell);
    if (!started) {
      return;
    }
    const index = cells.findIndex((known) => known.id === cell.id);
    const next = cells[index + 1];
    if (next !== undefined) {
      focusCell(next.id);
      return;
    }
    const created = await actions.add(cell.id);
    if (created !== null) {
      setFocusedId(created.id);
      setEditingId(created.id);
    }
  }

  async function add(after: string | null) {
    const created = await actions.add(after);
    if (created !== null) {
      setFocusedId(created.id);
      setEditingId(created.id);
    }
  }

  async function showAttempts(cell: Cell) {
    if (cell.runId === null) {
      return;
    }
    try {
      const failed = await loadFailedAttempts(cell.runId, cell.id);
      setHistory((current) => {
        const next = structuredClone(current);
        next[cell.id] = failed;
        return next;
      });
    } catch (error) {
      toast(sentenceForError(error));
    }
  }

  // Command mode (design.md §7): the keys act on the focused cell while no
  // cell is being edited.
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (editingId !== null || event.ctrlKey || event.metaKey || event.altKey) {
      return;
    }
    if (event.target instanceof HTMLElement && event.target.closest("button, input, textarea")) {
      return;
    }

    const index = cells.findIndex((cell) => cell.id === focusedId);
    const focused = cells[index];
    const key = event.key;
    const previous = lastKey.current;
    lastKey.current = { key, at: Date.now() };

    if (key === "?") {
      event.preventDefault();
      setShortcuts(true);
      return;
    }
    if (key === "ArrowDown" || key === "ArrowUp") {
      event.preventDefault();
      let target = cells[0];
      if (focused !== undefined) {
        const step = key === "ArrowDown" ? 1 : -1;
        target = cells[Math.min(Math.max(index + step, 0), cells.length - 1)];
      }
      if (target !== undefined) {
        focusCell(target.id);
      }
      return;
    }
    if (focused === undefined) {
      return;
    }
    if (key === "Enter") {
      event.preventDefault();
      setEditingId(focused.id);
      return;
    }
    if (key === "a" || key === "A") {
      event.preventDefault();
      const above = cells[index - 1];
      void add(above?.id ?? null);
      return;
    }
    if (key === "b" || key === "B") {
      event.preventDefault();
      void add(focused.id);
      return;
    }
    if ((key === "d" || key === "D") && previous !== null) {
      const twice =
        previous.key.toLowerCase() === "d" && Date.now() - previous.at < DOUBLE_PRESS_MS;
      if (twice && !busy) {
        event.preventDefault();
        lastKey.current = null;
        setDeleting(focused);
      }
    }
  }

  const stale = cells.filter((cell) => cell.stale).length;
  const ran = cells.some((cell) => cell.executionCount !== null);
  const kernelGone = conversation.kernel === "stopped" && !busy && ran;

  return (
    <div className="flex min-h-0 flex-1 flex-col" onKeyDown={onKeyDown}>
      <Banner
        kernelGone={kernelGone}
        stale={stale}
        busy={busy}
        onRunAll={() => void actions.runAll()}
      />
      {cells.length === 0 && (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-text-muted">
          Cells appear here as the analysis runs.
          <Button variant="secondary" onClick={() => void add(null)}>
            <Plus className="size-4" />
            Add a cell
          </Button>
        </div>
      )}
      {cells.length > 0 && (
        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
          <div className="flex flex-col py-6 pr-8 pl-2">
            {cells.map((cell, index) => (
              <div key={cell.id} className="flex flex-col">
                {index > 0 && (
                  <InsertLine onInsert={() => void add(cells[index - 1]?.id ?? null)} />
                )}
                <CellView
                  cell={cell}
                  failedAttempts={live?.failedAttempts[cell.id] ?? history[cell.id] ?? []}
                  startedAt={live?.startedAt[cell.id] ?? null}
                  focused={focusedId === cell.id}
                  editing={editingId === cell.id}
                  draft={draftOf(cell)}
                  busy={busy}
                  onFocus={() => {
                    setFocusedId(cell.id);
                  }}
                  onEdit={() => {
                    setFocusedId(cell.id);
                    setEditingId(cell.id);
                  }}
                  onDraft={(source) => {
                    setDraft(cell, source);
                  }}
                  onLeave={() => void leave(cell)}
                  onRun={() => void run(cell)}
                  onRunAndNext={() => void runAndNext(cell)}
                  onDelete={() => {
                    setDeleting(cell);
                  }}
                  onAddBelow={() => void add(cell.id)}
                  onStop={onStop}
                  onShowAttempts={() => void showAttempts(cell)}
                />
              </div>
            ))}
            <InsertLine onInsert={() => void add(cells.at(-1)?.id ?? null)} />
          </div>
        </div>
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        title="Delete this cell?"
        description="Its code and outputs go. The cells below that ran become stale."
        confirmLabel="Delete"
        onConfirm={() => {
          if (deleting !== null) {
            void actions.remove(deleting);
          }
          setDeleting(null);
        }}
      />
      <ShortcutsDialog open={shortcuts} onOpenChange={setShortcuts} />
    </div>
  );
}

// Between cells, a thin + line on hover inserts a cell there (design.md §2.5).
function InsertLine({ onInsert }: { onInsert: () => void }) {
  return (
    <div className="group/insert relative ml-12 flex h-6 items-center justify-center">
      <span className="absolute inset-x-0 top-1/2 h-px bg-transparent group-hover/insert:bg-border" />
      <button
        type="button"
        aria-label="Insert a cell here"
        className="relative flex size-5 items-center justify-center rounded-full border border-border bg-bg text-text-muted opacity-0 group-hover/insert:opacity-100 focus-visible:opacity-100"
        onClick={onInsert}
      >
        <Plus className="size-3" />
      </button>
    </div>
  );
}

// design.md §3.7 — one bar at a time, the kernel's news before the stale cells.
function Banner({
  kernelGone,
  stale,
  busy,
  onRunAll,
}: {
  kernelGone: boolean;
  stale: number;
  busy: boolean;
  onRunAll: () => void;
}) {
  // A kernel.restarted arrives as a run begins, with a new kernel on its way —
  // so a stopped kernel's reason is never the stream's to tell, and the banner
  // says what is true now. The chat's divider keeps each restart and its reason.
  if (kernelGone) {
    return (
      <BannerBar
        icon={<RotateCcw className="size-4 text-text-muted" />}
        lead="The kernel stopped."
        rest="Variables are gone; outputs are kept."
        action={
          <Button size="compact" disabled={busy} onClick={onRunAll}>
            <Play className="size-3.5" />
            Run all
          </Button>
        }
        status
      />
    );
  }

  if (stale > 0) {
    let lead = `${plural(stale, "cell", "cells")} are stale.`;
    let rest = "A cell above them changed after they ran.";
    if (stale === 1) {
      lead = "1 cell is stale.";
      rest = "A cell above it changed after it ran.";
    }
    return (
      <BannerBar
        icon={<TriangleAlert className="size-4 text-warning" />}
        lead={lead}
        rest={rest}
        action={
          <Button variant="secondary" size="compact" disabled={busy} onClick={onRunAll}>
            <Play className="size-3.5" />
            Run all
          </Button>
        }
        status={false}
      />
    );
  }

  return null;
}

function BannerBar({
  icon,
  lead,
  rest,
  action,
  status,
}: {
  icon: ReactNode;
  lead: string;
  rest: string;
  action: ReactNode;
  status: boolean;
}) {
  return (
    <div
      role={status ? "status" : undefined}
      className="flex min-h-10 flex-none items-center gap-2 border-b border-border bg-surface py-1 pr-3 pl-4 text-sm"
    >
      {icon}
      <span className="min-w-0 flex-1 text-pretty">
        <span className="font-medium">{lead}</span> <span className="text-text-muted">{rest}</span>
      </span>
      {action}
    </div>
  );
}
