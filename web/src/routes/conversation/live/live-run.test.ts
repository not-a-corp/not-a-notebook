import { describe, expect, it } from "vitest";

import type { Cell, ConversationDetail, Message } from "@/api/conversation-detail";
import type { RunEvent } from "@/api/events";

import { applyEvent, type ScreenState } from "./live-run";

const NOW = "2026-10-04T14:06:24.000Z";
const RUN = "run-1";
const CELL = "cell-1";

function conversation(cells: Cell[] = []): ConversationDetail {
  return {
    id: "conversation-1",
    title: "Vendas",
    modelId: "model-1",
    kernel: "stopped",
    activeRunId: RUN,
    files: [],
    messages: [],
    cells,
  };
}

const CREATED: Cell = {
  id: CELL,
  position: 1,
  origin: "agent",
  runId: RUN,
  source: "df['região']",
  status: "running",
  stale: false,
  attempts: 1,
  executionCount: null,
  outputs: [],
  executedAt: null,
  durationMs: null,
};

const ANSWER: Message = {
  id: "message-2",
  role: "assistant",
  runId: RUN,
  text: "Sudeste, with R$ 1.84M.",
  kind: "answer",
  grounding: { numbers: 1, found: 1, unfound: [] },
  createdAt: NOW,
};

// events.md, "A message run, start to finish", as typed events.
type Body = RunEvent extends infer E ? (E extends RunEvent ? Omit<E, "seq" | "t"> : never) : never;

const BODIES: Body[] = [
  { type: "run.started", runId: RUN, kind: "message", model: "scripted" },
  { type: "kernel.starting" },
  { type: "kernel.ready", startupMs: 2210 },
  { type: "llm.started", step: 1 },
  { type: "llm.delta", step: 1, text: "Let me look at " },
  { type: "llm.delta", step: 1, text: "the sheet first." },
  { type: "llm.finished", step: 1, stop: "code" },
  { type: "code.proposed", step: 1, cellId: CELL, attempt: 1, code: "df['região']" },
  { type: "cell.created", cell: CREATED },
  { type: "attempt.started", cellId: CELL, attempt: 1 },
  {
    type: "cell.output",
    cellId: CELL,
    attempt: 1,
    output: { kind: "error", name: "KeyError", value: "'região'", traceback: [] },
  },
  {
    type: "attempt.finished",
    cellId: CELL,
    attempt: 1,
    status: "error",
    executionCount: 1,
    durationMs: 200,
  },
  { type: "llm.started", step: 2 },
  { type: "llm.finished", step: 2, stop: "code" },
  { type: "code.proposed", step: 2, cellId: CELL, attempt: 2, code: "df['Região']" },
  { type: "attempt.started", cellId: CELL, attempt: 2 },
  {
    type: "cell.output",
    cellId: CELL,
    attempt: 2,
    output: { kind: "stream", name: "stdout", text: "1840231.5\n" },
  },
  {
    type: "attempt.finished",
    cellId: CELL,
    attempt: 2,
    status: "ok",
    executionCount: 2,
    durationMs: 640,
  },
  {
    type: "cell.finished",
    cellId: CELL,
    status: "ok",
    attempts: 2,
    executionCount: 2,
    durationMs: 640,
  },
  { type: "llm.started", step: 3 },
  { type: "llm.delta", step: 3, text: "Sudeste, with R$ 1.84M." },
  { type: "llm.finished", step: 3, stop: "answer" },
  { type: "answer", message: ANSWER },
  { type: "grounding.checked", numbers: 1, found: 1, unfound: [] },
  { type: "run.finished", status: "succeeded" },
];

function numbered(bodies: Body[]): RunEvent[] {
  return bodies.map((body, index) => {
    const event: RunEvent = Object.assign({ seq: index + 1, t: index / 10 }, body);
    return event;
  });
}

const EVENTS = numbered(BODIES);

function play(start: ScreenState, events: RunEvent[]): ScreenState[] {
  const states: ScreenState[] = [];
  let state = start;
  for (const event of events) {
    state = applyEvent(state, event, NOW);
    states.push(state);
  }
  return states;
}

function at(states: ScreenState[], type: RunEvent["type"], nth = 1): ScreenState {
  let seen = 0;
  for (const [index, event] of EVENTS.entries()) {
    if (event.type === type) {
      seen += 1;
      if (seen === nth) {
        const state = states[index];
        if (state === undefined) {
          throw new Error("no state");
        }
        return state;
      }
    }
  }
  throw new Error(`no ${type}`);
}

describe("applyEvent", () => {
  const states = play({ detail: conversation(), live: null }, EVENTS);

  it("says what the analyst is doing, step by step", () => {
    expect(at(states, "kernel.starting").live?.activity).toEqual({ kind: "starting-kernel" });
    expect(at(states, "llm.started").live?.activity).toEqual({ kind: "thinking" });
    expect(at(states, "code.proposed").live?.activity).toEqual({ kind: "writing", cell: 1 });
    expect(at(states, "attempt.started").live?.activity).toMatchObject({ kind: "running" });
    expect(at(states, "code.proposed", 2).live?.activity).toEqual({
      kind: "retrying",
      cell: 1,
      cellId: CELL,
      attempt: 2,
      lastError: "KeyError: 'região'",
    });
  });

  it("streams the words of each step", () => {
    expect(at(states, "llm.delta", 2).live?.steps).toEqual(["Let me look at the sheet first."]);
  });

  it("replaces a failed attempt in the cell and keeps it aside", () => {
    const retried = at(states, "attempt.started", 2);
    expect(retried.detail.cells[0]?.source).toBe("df['Região']");
    expect(retried.detail.cells[0]?.outputs).toEqual([]);
    expect(retried.live?.failedAttempts[CELL]).toEqual([
      {
        attempt: 1,
        code: "df['região']",
        error: "KeyError: 'região'",
        outputs: [{ kind: "error", name: "KeyError", value: "'região'", traceback: [] }],
        durationMs: 200,
      },
    ]);
  });

  it("settles the cell, the answer and the run", () => {
    const last = states.at(-1);
    expect(last?.detail.cells[0]).toMatchObject({
      status: "ok",
      attempts: 2,
      executionCount: 2,
      outputs: [{ kind: "stream", name: "stdout", text: "1840231.5\n" }],
    });
    expect(last?.detail.messages).toEqual([ANSWER]);
    expect(last?.detail.activeRunId).toBeNull();
    expect(last?.detail.kernel).toBe("running");
    expect(last?.live).toMatchObject({
      finished: "succeeded",
      activity: null,
      steps: [],
      lost: false,
    });
  });

  it("lands in the same place when a page opened mid-run replays from the start", () => {
    // GET /conversations/{id} already had the cell, an output and the answer.
    const midRun = conversation([
      Object.assign(structuredClone(CREATED), {
        outputs: [{ kind: "stream", name: "stdout", text: "1840231.5\n" }],
      }),
    ]);
    midRun.messages = [ANSWER];

    const replayed = play({ detail: midRun, live: null }, EVENTS).at(-1);

    expect(replayed?.detail.cells).toEqual(states.at(-1)?.detail.cells.map((cell) => cell));
    expect(replayed?.detail.messages).toEqual([ANSWER]);
  });

  it("notices a gap in seq", () => {
    const skipped = EVENTS.filter((event) => event.seq !== 3);

    expect(play({ detail: conversation(), live: null }, skipped).at(-1)?.live?.lost).toBe(true);
  });
});
