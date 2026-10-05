import { LoaderCircle, Play, Plus, Trash, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { Cell } from "@/api/conversation-detail";
import { CellEditor } from "@/components/cell-editor";
import { PythonCode } from "@/components/code";
import { Outputs } from "@/components/outputs/outputs";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { formatClock, formatCount, formatDuration } from "@/lib/format";
import { useElapsed } from "@/lib/use-elapsed";

import type { FailedAttempt } from "../live/live-run";
import { FailedAttemptRow } from "./failed-attempt";

// design.md §2.5 and §3.3 — one cell: a 48 px gutter and its body.

function executionLabel(cell: Cell): string {
  if (cell.status === "running") {
    return "[*]";
  }
  if (cell.executionCount === null || cell.status === "cancelled") {
    return "[ ]";
  }
  return `[${String(cell.executionCount)}]`;
}

function statusBar(cell: Cell): string | null {
  if (cell.status === "running") {
    return "w-0.5 rounded-full bg-gradient-to-b from-accent to-accent/25";
  }
  if (cell.stale) {
    return "border-l-2 border-dashed border-warning";
  }
  if (cell.status === "error") {
    return "w-0.5 rounded-full bg-danger";
  }
  if (cell.status === "cancelled") {
    return "w-0.5 rounded-full bg-text-muted";
  }
  return null;
}

// What the outputs need said, at the footer's left: how much of a table travelled.
function footerNote(cell: Cell): string | null {
  if (cell.status === "cancelled") {
    return "stopped by you";
  }
  for (const output of cell.outputs.toReversed()) {
    if (output.kind === "table") {
      return `${formatCount(output.rows.length)} of ${formatCount(output.totalRows)} rows`;
    }
  }
  return null;
}

function originLabel(cell: Cell): string {
  if (cell.origin === "agent") {
    return "agent";
  }
  return "you";
}

export interface CellViewProps {
  cell: Cell;
  failedAttempts: FailedAttempt[];
  startedAt: string | null;
  focused: boolean;
  editing: boolean;
  draft: string;
  // A run is in progress in the conversation: nothing else can run now.
  busy: boolean;
  onFocus: () => void;
  onEdit: () => void;
  onDraft: (source: string) => void;
  onLeave: () => void;
  onRun: () => void;
  onRunAndNext: () => void;
  onDelete: () => void;
  onAddBelow: () => void;
  onStop: () => void;
  onShowAttempts: () => void;
}

export function CellView(props: CellViewProps) {
  const { cell, focused, editing } = props;
  const bar = statusBar(cell);
  const running = cell.status === "running";
  const note = footerNote(cell);
  const showHeader = focused || running;

  return (
    <article
      id={`cell-${cell.id}`}
      tabIndex={-1}
      aria-label={`Cell ${executionLabel(cell)}`}
      data-cell-id={cell.id}
      className="group grid scroll-mt-6 grid-cols-[48px_minmax(0,1fr)] outline-none"
      onFocus={props.onFocus}
      onMouseDown={props.onFocus}
    >
      <div
        className={cn(
          "relative pt-2 pr-3 text-right font-mono text-xs text-text-muted",
          running && "font-semibold text-accent",
          cell.stale && "opacity-60",
        )}
      >
        {executionLabel(cell)}
        {bar !== null && <span className={cn("absolute top-0 right-1 bottom-0", bar)} />}
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        {showHeader && <CellHeader actions={headerProps(props)} />}
        {cell.stale && !showHeader && <StaleLabel cell={cell} />}

        {props.failedAttempts.map((attempt) => (
          <FailedAttemptRow key={attempt.attempt} attempt={attempt} />
        ))}

        <div
          className={cn(
            "relative overflow-x-auto rounded-lg border border-border bg-surface px-3 py-2",
            focused && "border-[color-mix(in_oklab,var(--accent)_55%,var(--border))]",
            running && "border-accent/45 bg-accent-soft",
          )}
          // On press, not on click: focusing the cell brings its header in above
          // the code, and the code would move out from under the release.
          onMouseDown={(event) => {
            if (!editing && event.button === 0) {
              // The browser would move focus to the cell after this; the
              // editor takes it instead.
              event.preventDefault();
              props.onEdit();
            }
          }}
        >
          {running && (
            <span className="absolute inset-x-0 top-0 h-0.5 animate-pulse bg-gradient-to-r from-transparent via-accent to-transparent" />
          )}
          {editing && (
            <CellEditor
              source={props.draft}
              onChange={props.onDraft}
              onLeave={props.onLeave}
              onRun={props.onRun}
              onRunAndNext={props.onRunAndNext}
            />
          )}
          {!editing && cell.source !== "" && <PythonCode source={props.draft} />}
          {!editing && cell.source === "" && (
            <span className="font-mono text-sm text-text-muted">Empty cell — Enter to edit</span>
          )}
          {!showHeader && !editing && <HoverActions actions={headerProps(props)} />}
        </div>

        <div className={cn("flex flex-col gap-2", cell.stale && "opacity-45")}>
          <Outputs outputs={cell.outputs} />
          {running && cell.outputs.length === 0 && (
            <div className="flex items-center gap-2 pl-3 text-xs text-text-muted">
              <LoaderCircle className="size-3.5 animate-spin text-accent" />
              Waiting for output…
            </div>
          )}
          <Footer
            cell={cell}
            note={note}
            showAttempts={props.failedAttempts.length === 0 ? props.onShowAttempts : null}
          />
        </div>
      </div>
    </article>
  );
}

interface HeaderProps {
  cell: Cell;
  startedAt: string | null;
  busy: boolean;
  onRun: () => void;
  onDelete: () => void;
  onAddBelow: () => void;
  onStop: () => void;
}

function headerProps(props: CellViewProps): HeaderProps {
  return {
    cell: props.cell,
    startedAt: props.startedAt,
    busy: props.busy,
    onRun: props.onRun,
    onDelete: props.onDelete,
    onAddBelow: props.onAddBelow,
    onStop: props.onStop,
  };
}

function ActionButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip label={label}>
      <Button
        variant="ghost"
        size="icon-compact"
        aria-label={label}
        disabled={disabled}
        onClick={(event) => {
          event.stopPropagation();
          onClick();
        }}
      >
        {children}
      </Button>
    </Tooltip>
  );
}

function Actions({ actions }: { actions: HeaderProps }) {
  const { cell, busy, onRun, onDelete, onAddBelow, onStop } = actions;
  const running = cell.status === "running";

  return (
    <>
      {running && (
        <ActionButton label="Stop" disabled={false} onClick={onStop}>
          <span className="size-2.5 rounded-xs bg-text" />
        </ActionButton>
      )}
      {!running && (
        <ActionButton label="Run cell (Ctrl+Enter)" disabled={busy} onClick={onRun}>
          <Play className="size-4" />
        </ActionButton>
      )}
      <ActionButton label="Delete cell" disabled={busy} onClick={onDelete}>
        <Trash className="size-4" />
      </ActionButton>
      <ActionButton label="Add cell below" disabled={false} onClick={onAddBelow}>
        <Plus className="size-4" />
      </ActionButton>
    </>
  );
}

// Shown on the focused cell and while it runs (design.md §2.5): who wrote it,
// which attempt, the running clock, and the actions.
function CellHeader({ actions }: { actions: HeaderProps }) {
  const { cell, startedAt } = actions;
  const running = cell.status === "running";
  const elapsed = useElapsed(running ? startedAt : null);

  return (
    <div className="flex h-7 items-center gap-2 text-xs text-text-muted">
      {cell.stale && (
        <span className="flex items-center gap-1 font-medium text-warning">
          <TriangleAlert className="size-3.5" />
          stale — a cell above changed
        </span>
      )}
      <span className="font-medium text-text">{originLabel(cell)}</span>
      {running && cell.origin === "agent" && cell.attempts > 1 && (
        <>
          <span>·</span>
          <span className="whitespace-nowrap">attempt {cell.attempts}</span>
        </>
      )}
      <div className="flex-1" />
      {running && (
        <span className="font-medium whitespace-nowrap text-accent">
          Running · {formatDuration(elapsed)}
        </span>
      )}
      <Actions actions={actions} />
    </div>
  );
}

// On hover, the actions float in the code's corner, so hovering never moves
// the list (the header row would).
function HoverActions({ actions }: { actions: HeaderProps }) {
  return (
    <div className="absolute top-1 right-1 hidden items-center rounded-md bg-surface group-hover:flex">
      <Actions actions={actions} />
    </div>
  );
}

function StaleLabel({ cell }: { cell: Cell }) {
  return (
    <div className="flex h-5 items-center gap-2 text-xs font-medium text-warning">
      <TriangleAlert className="size-3.5" />
      <span>stale — a cell above changed</span>
      <div className="flex-1" />
      <span className="font-normal text-text-muted">{originLabel(cell)}</span>
    </div>
  );
}

function Footer({
  cell,
  note,
  showAttempts,
}: {
  cell: Cell;
  note: string | null;
  showAttempts: (() => void) | null;
}) {
  const facts: ReactNode[] = [];
  if (cell.attempts > 1) {
    const label = `${String(cell.attempts)} attempts`;
    if (showAttempts !== null && cell.runId !== null) {
      facts.push(
        <button
          key="attempts"
          type="button"
          className="text-accent hover:underline"
          onClick={showAttempts}
        >
          {label}
        </button>,
      );
    } else {
      facts.push(label);
    }
  }
  if (cell.durationMs !== null) {
    facts.push(formatDuration(cell.durationMs));
  }
  if (cell.executedAt !== null) {
    facts.push(formatClock(cell.executedAt));
  }

  if (note === null && facts.length === 0) {
    return null;
  }

  return (
    <div className="flex justify-between gap-2 pl-3 text-xs whitespace-nowrap text-text-muted">
      <span>{note}</span>
      <span>
        {facts.map((fact, index) => (
          <span key={index}>
            {index > 0 && " · "}
            {fact}
          </span>
        ))}
      </span>
    </div>
  );
}
