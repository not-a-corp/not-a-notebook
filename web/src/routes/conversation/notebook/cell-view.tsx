import { LoaderCircle, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";

import type { Cell } from "@/api/conversation-detail";
import { PythonCode } from "@/components/code";
import { Outputs } from "@/components/outputs/outputs";
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

function footerFacts(cell: Cell): string {
  const facts: string[] = [];
  if (cell.attempts > 1) {
    facts.push(`${String(cell.attempts)} attempts`);
  }
  if (cell.durationMs !== null) {
    facts.push(formatDuration(cell.durationMs));
  }
  if (cell.executedAt !== null) {
    facts.push(formatClock(cell.executedAt));
  }
  return facts.join(" · ");
}

interface CellViewProps {
  cell: Cell;
  failedAttempts: FailedAttempt[];
  startedAt: string | null;
  onStop: () => void;
}

export function CellView({ cell, failedAttempts, startedAt, onStop }: CellViewProps) {
  const bar = statusBar(cell);
  const running = cell.status === "running";
  const note = footerNote(cell);
  const facts = footerFacts(cell);

  return (
    <article
      id={`cell-${cell.id}`}
      aria-label={`Cell ${executionLabel(cell)}`}
      className="group grid scroll-mt-6 grid-cols-[48px_minmax(0,1fr)]"
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
        {running && <RunningHeader cell={cell} startedAt={startedAt} onStop={onStop} />}
        {cell.stale && (
          <div className="flex h-5 items-center gap-2 text-xs font-medium text-warning">
            <TriangleAlert className="size-3.5" />
            <span>stale — a cell above changed</span>
            <div className="flex-1" />
            <span className="font-normal text-text-muted">{originLabel(cell)}</span>
          </div>
        )}

        {failedAttempts.map((attempt) => (
          <FailedAttemptRow key={attempt.attempt} attempt={attempt} />
        ))}

        <div
          className={cn(
            "relative overflow-x-auto rounded-lg border border-border bg-surface px-3 py-2",
            running && "border-accent/45 bg-accent-soft",
          )}
        >
          {running && (
            <span className="absolute inset-x-0 top-0 h-0.5 animate-pulse bg-gradient-to-r from-transparent via-accent to-transparent" />
          )}
          <PythonCode source={cell.source} />
        </div>

        <div className={cn("flex flex-col gap-2", cell.stale && "opacity-45")}>
          <Outputs outputs={cell.outputs} />
          {running && cell.outputs.length === 0 && (
            <div className="flex items-center gap-2 pl-3 text-xs text-text-muted">
              <LoaderCircle className="size-3.5 animate-spin text-accent" />
              Waiting for output…
            </div>
          )}
          {(note !== null || facts !== "") && (
            <div className="flex justify-between gap-2 pl-3 text-xs whitespace-nowrap text-text-muted">
              <span>{note}</span>
              <span>{facts}</span>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function originLabel(cell: Cell): string {
  if (cell.origin === "agent") {
    return "agent";
  }
  return "you";
}

// Shown while the cell runs (design.md §2.5): who wrote it, which attempt, the
// running clock, and Stop.
function RunningHeader({
  cell,
  startedAt,
  onStop,
}: {
  cell: Cell;
  startedAt: string | null;
  onStop: () => void;
}) {
  const elapsed = useElapsed(startedAt);

  return (
    <div className="flex h-7 items-center gap-2 text-xs text-text-muted">
      <span className="font-medium text-text">{originLabel(cell)}</span>
      {cell.origin === "agent" && cell.attempts > 1 && (
        <>
          <span>·</span>
          <span className="whitespace-nowrap">attempt {cell.attempts}</span>
        </>
      )}
      <div className="flex-1" />
      <span className="font-medium whitespace-nowrap text-accent">
        Running · {formatDuration(elapsed)}
      </span>
      <Tooltip label="Stop">
        <Button variant="ghost" size="icon-compact" aria-label="Stop" onClick={onStop}>
          <span className="size-2.5 rounded-xs bg-text" />
        </Button>
      </Tooltip>
    </div>
  );
}
