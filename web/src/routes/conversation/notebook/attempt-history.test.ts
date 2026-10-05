import { afterEach, describe, expect, it, vi } from "vitest";

import { loadFailedAttempts } from "./attempt-history";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stream(events: object[]): Response {
  const body = events
    .map(
      (event) =>
        `event: x\nid: ${String(Reflect.get(event, "seq"))}\ndata: ${JSON.stringify(event)}\n\n`,
    )
    .join("");
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("loadFailedAttempts", () => {
  it("rebuilds a settled cell's failed attempts from its run's events", async () => {
    const error = { kind: "error", name: "KeyError", value: "'data'", traceback: [] };
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          stream([
            {
              seq: 1,
              t: 0,
              type: "code.proposed",
              step: 1,
              cell_id: "c",
              attempt: 1,
              code: "df['data']",
            },
            Object.assign({ seq: 2, t: 0.1, type: "cell.output", cell_id: "c", attempt: 1 }, error),
            {
              seq: 3,
              t: 0.2,
              type: "attempt.finished",
              cell_id: "c",
              attempt: 1,
              status: "error",
              execution_count: 1,
              duration_ms: 200,
            },
            {
              seq: 4,
              t: 0.3,
              type: "code.proposed",
              step: 2,
              cell_id: "c",
              attempt: 2,
              code: "df['Data']",
            },
            {
              seq: 5,
              t: 0.4,
              type: "attempt.finished",
              cell_id: "c",
              attempt: 2,
              status: "ok",
              execution_count: 2,
              duration_ms: 640,
            },
            {
              seq: 6,
              t: 0.5,
              type: "code.proposed",
              step: 3,
              cell_id: "other",
              attempt: 1,
              code: "x",
            },
            { seq: 7, t: 0.6, type: "run.finished", status: "succeeded" },
          ]),
        ),
      ),
    );

    const failed = await loadFailedAttempts("run", "c");

    expect(failed).toEqual([
      {
        attempt: 1,
        code: "df['data']",
        error: "KeyError: 'data'",
        outputs: [{ kind: "error", name: "KeyError", value: "'data'", traceback: [] }],
        durationMs: 200,
      },
    ]);
  });
});
