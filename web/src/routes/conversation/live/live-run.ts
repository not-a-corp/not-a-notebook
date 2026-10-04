import type { Cell, ConversationDetail, Message } from "@/api/conversation-detail";
import type { FinishedStatus, RestartReason, RunEvent, RunKind } from "@/api/events";
import type { Output } from "@/api/outputs";

// design.md §4 — the stream, on screen. Every event changes two things: the
// conversation as GET /conversations/{id} shows it (the query cache), and what
// only the live run knows — what the analyst is doing now, the words streaming
// in, the attempts that failed. Both are changed here, by one pure function,
// so a run replayed from its first event lands where the live one did.

export type Activity =
  | { kind: "starting-kernel" }
  | { kind: "thinking" }
  | { kind: "writing"; cell: number }
  | { kind: "running"; cell: number; cellId: string }
  | { kind: "retrying"; cell: number; cellId: string; attempt: number; lastError: string | null };

export interface FailedAttempt {
  attempt: number;
  code: string;
  error: string | null;
  outputs: Output[];
  durationMs: number;
}

export interface RunFailure {
  code: string;
  message: string;
  errorId: string | null;
}

export interface LiveRun {
  runId: string;
  kind: RunKind | null;
  activity: Activity | null;
  // The analyst's words as they stream, one entry per step.
  steps: string[];
  // Code proposed for a cell's next attempt, until that attempt starts.
  proposed: Record<string, string>;
  failedAttempts: Record<string, FailedAttempt[]>;
  // Cells whose outputs this run has already reset — so a replayed run does not
  // add its outputs twice to what GET /conversations/{id} already showed.
  resetCells: string[];
  // When each cell's current attempt started, for its running clock.
  startedAt: Record<string, string>;
  restarted: { reason: RestartReason; at: string } | null;
  failure: RunFailure | null;
  finished: FinishedStatus | null;
  lastSeq: number;
  lost: boolean;
}

export interface ScreenState {
  detail: ConversationDetail;
  live: LiveRun | null;
}

export function newLiveRun(runId: string): LiveRun {
  return {
    runId,
    kind: null,
    activity: null,
    steps: [],
    proposed: {},
    failedAttempts: {},
    resetCells: [],
    startedAt: {},
    restarted: null,
    failure: null,
    finished: null,
    lastSeq: 0,
    lost: false,
  };
}

// ── the conversation ─────────────────────────────────────────────────────────

function withCells(detail: ConversationDetail, cells: Cell[]): ConversationDetail {
  return {
    id: detail.id,
    title: detail.title,
    modelId: detail.modelId,
    kernel: detail.kernel,
    activeRunId: detail.activeRunId,
    files: detail.files,
    messages: detail.messages,
    cells,
  };
}

function changeCell(
  detail: ConversationDetail,
  cellId: string,
  change: (cell: Cell) => Cell,
): ConversationDetail {
  const cells = detail.cells.map((cell) => {
    if (cell.id !== cellId) {
      return cell;
    }
    return change(cell);
  });
  return withCells(detail, cells);
}

export interface CellChanges {
  source?: string;
  status?: Cell["status"];
  stale?: boolean;
  attempts?: number;
  executionCount?: number | null;
  outputs?: Output[];
  executedAt?: string | null;
  durationMs?: number | null;
}

export function updatedCell(cell: Cell, changes: CellChanges): Cell {
  return {
    id: cell.id,
    position: cell.position,
    origin: cell.origin,
    runId: cell.runId,
    source: changes.source ?? cell.source,
    status: changes.status ?? cell.status,
    stale: changes.stale ?? cell.stale,
    attempts: changes.attempts ?? cell.attempts,
    executionCount:
      changes.executionCount === undefined ? cell.executionCount : changes.executionCount,
    outputs: changes.outputs ?? cell.outputs,
    executedAt: changes.executedAt === undefined ? cell.executedAt : changes.executedAt,
    durationMs: changes.durationMs === undefined ? cell.durationMs : changes.durationMs,
  };
}

interface DetailChanges {
  kernel?: ConversationDetail["kernel"];
  activeRunId?: string | null;
  files?: ConversationDetail["files"];
  messages?: Message[];
}

function updatedDetail(detail: ConversationDetail, changes: DetailChanges): ConversationDetail {
  return {
    id: detail.id,
    title: detail.title,
    modelId: detail.modelId,
    kernel: changes.kernel ?? detail.kernel,
    activeRunId: changes.activeRunId === undefined ? detail.activeRunId : changes.activeRunId,
    files: changes.files ?? detail.files,
    messages: changes.messages ?? detail.messages,
    cells: detail.cells,
  };
}

function addMessage(detail: ConversationDetail, message: Message): ConversationDetail {
  if (detail.messages.some((known) => known.id === message.id)) {
    return detail;
  }
  return updatedDetail(detail, { messages: [...detail.messages, message] });
}

// ── the live run ─────────────────────────────────────────────────────────────

function cellNumber(detail: ConversationDetail, cellId: string): number {
  const index = detail.cells.findIndex((cell) => cell.id === cellId);
  if (index === -1) {
    return detail.cells.length + 1;
  }
  return index + 1;
}

function errorLine(outputs: Output[]): string | null {
  for (const output of outputs) {
    if (output.kind === "error") {
      return `${output.name}: ${output.value}`;
    }
  }
  return null;
}

function updatedLive(live: LiveRun, changes: Partial<LiveRun>): LiveRun {
  return Object.assign(structuredClone(live), changes);
}

function withStep(steps: string[], step: number, text: string): string[] {
  const next = steps.slice();
  while (next.length < step) {
    next.push("");
  }
  next[step - 1] = (next[step - 1] ?? "") + text;
  return next;
}

// ── one event ────────────────────────────────────────────────────────────────

// `now` is when the event arrived, for what the events do not time themselves.
export function applyEvent(state: ScreenState, event: RunEvent, now: string): ScreenState {
  let detail = state.detail;
  let live = state.live;
  live ??= newLiveRun(detail.activeRunId ?? "");

  // A gap in seq means an event was lost (events.md): the screen says so.
  const lost = live.lost || event.seq > live.lastSeq + 1;
  live = updatedLive(live, { lastSeq: Math.max(live.lastSeq, event.seq), lost });

  switch (event.type) {
    case "run.started":
      live = updatedLive(live, { runId: event.runId, kind: event.kind });
      detail = updatedDetail(detail, { activeRunId: event.runId });
      break;

    case "run.error":
      live = updatedLive(live, {
        failure: { code: event.code, message: event.message, errorId: event.errorId },
      });
      break;

    case "run.finished":
      live = updatedLive(live, { finished: event.status, activity: null, steps: [] });
      detail = updatedDetail(detail, { activeRunId: null });
      break;

    case "kernel.starting":
      live = updatedLive(live, { activity: { kind: "starting-kernel" } });
      break;

    case "kernel.ready":
      live = updatedLive(live, { activity: null });
      detail = updatedDetail(detail, { kernel: "running" });
      break;

    case "kernel.restarted":
      live = updatedLive(live, { restarted: { reason: event.reason, at: now } });
      break;

    case "file.uploaded":
      if (!detail.files.some((file) => file.id === event.file.id)) {
        detail = updatedDetail(detail, { files: [...detail.files, event.file] });
      }
      break;

    case "file.profiled": {
      const files = detail.files.map((file) => {
        if (file.id !== event.fileId) {
          return file;
        }
        return {
          id: file.id,
          name: file.name,
          bytes: file.bytes,
          profile: event.profile,
          createdAt: file.createdAt,
        };
      });
      detail = updatedDetail(detail, { files });
      break;
    }

    case "llm.started":
      live = updatedLive(live, { activity: { kind: "thinking" } });
      break;

    case "llm.delta":
      live = updatedLive(live, { steps: withStep(live.steps, event.step, event.text) });
      break;

    case "llm.finished":
      break;

    case "code.proposed": {
      const cell = cellNumber(detail, event.cellId);
      const proposed = structuredClone(live.proposed);
      proposed[event.cellId] = event.code;
      let activity: Activity = { kind: "writing", cell };
      if (event.attempt > 1) {
        const failed = live.failedAttempts[event.cellId] ?? [];
        activity = {
          kind: "retrying",
          cell,
          cellId: event.cellId,
          attempt: event.attempt,
          lastError: failed.at(-1)?.error ?? null,
        };
      }
      live = updatedLive(live, { proposed, activity });
      break;
    }

    case "cell.created":
      if (!detail.cells.some((cell) => cell.id === event.cell.id)) {
        detail = withCells(detail, [...detail.cells, event.cell]);
      }
      break;

    case "attempt.started": {
      const source = live.proposed[event.cellId];
      detail = changeCell(detail, event.cellId, (cell) => {
        const changes: CellChanges = {
          status: "running",
          attempts: event.attempt,
          outputs: [],
          stale: false,
        };
        if (source !== undefined) {
          changes.source = source;
        }
        return updatedCell(cell, changes);
      });
      const cell = cellNumber(detail, event.cellId);
      let activity: Activity = { kind: "running", cell, cellId: event.cellId };
      if (live.activity?.kind === "retrying") {
        activity = live.activity;
      }
      const startedAt = structuredClone(live.startedAt);
      startedAt[event.cellId] = now;
      live = updatedLive(live, {
        activity,
        resetCells: [...live.resetCells, event.cellId],
        startedAt,
      });
      break;
    }

    case "cell.output": {
      const reset = !live.resetCells.includes(event.cellId);
      detail = changeCell(detail, event.cellId, (cell) => {
        // A cell you run has no attempt.started; its first output of this run
        // starts its outputs over.
        let outputs = [...cell.outputs, event.output];
        if (reset) {
          outputs = [event.output];
        }
        return updatedCell(cell, { outputs, status: "running" });
      });
      if (reset) {
        const startedAt = structuredClone(live.startedAt);
        startedAt[event.cellId] = now;
        live = updatedLive(live, { resetCells: [...live.resetCells, event.cellId], startedAt });
      }
      break;
    }

    case "attempt.finished": {
      if (event.status === "error" || event.status === "timed_out") {
        const cell = detail.cells.find((known) => known.id === event.cellId);
        if (cell !== undefined) {
          const failedAttempts = structuredClone(live.failedAttempts);
          const earlier = failedAttempts[event.cellId] ?? [];
          earlier.push({
            attempt: event.attempt,
            code: cell.source,
            error: errorLine(cell.outputs),
            outputs: cell.outputs,
            durationMs: event.durationMs,
          });
          failedAttempts[event.cellId] = earlier;
          live = updatedLive(live, { failedAttempts });
        }
      }
      detail = changeCell(detail, event.cellId, (cell) =>
        updatedCell(cell, { executionCount: event.executionCount, durationMs: event.durationMs }),
      );
      break;
    }

    case "cell.finished":
      detail = changeCell(detail, event.cellId, (cell) =>
        updatedCell(cell, {
          status: event.status,
          attempts: event.attempts,
          executionCount: event.executionCount,
          durationMs: event.durationMs,
          executedAt: now,
          stale: false,
        }),
      );
      live = updatedLive(live, { activity: null });
      break;

    case "cells.stale":
      detail = withCells(
        detail,
        detail.cells.map((cell) => {
          if (!event.cellIds.includes(cell.id)) {
            return cell;
          }
          return updatedCell(cell, { stale: true });
        }),
      );
      break;

    case "answer":
    case "question":
      detail = addMessage(detail, event.message);
      live = updatedLive(live, { steps: [], activity: null });
      break;

    case "grounding.checked":
      // The answer already carries its check (api.md); nothing left to change.
      break;

    default: {
      const unhandled: never = event;
      throw new Error(`Unhandled event ${JSON.stringify(unhandled)}`);
    }
  }

  return { detail, live };
}
