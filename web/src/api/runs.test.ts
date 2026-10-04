import { afterEach, describe, expect, it, vi } from "vitest";

import type { RunEvent } from "./events";
import { followRun, type Connection } from "./runs";

function sse(events: object[]): string {
  return events
    .map((event) => {
      const json = JSON.stringify(event);
      return `event: x\nid: ${String(Reflect.get(event, "seq"))}\ndata: ${json}\n\n`;
    })
    .join("");
}

function streamOf(text: string): Response {
  return new Response(text, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("followRun", () => {
  it("resumes after the last seq it saw when the connection drops", async () => {
    const sent: (string | null)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        const resumeFrom = new Headers(init?.headers).get("Last-Event-ID");
        sent.push(resumeFrom);
        if (resumeFrom === null) {
          // The first connection drops after two events.
          return Promise.resolve(
            streamOf(
              sse([
                { seq: 1, t: 0, type: "run.started", run_id: "r", kind: "cell", model: null },
                { seq: 2, t: 0.1, type: "kernel.starting" },
              ]),
            ),
          );
        }
        return Promise.resolve(
          streamOf(sse([{ seq: 3, t: 0.2, type: "run.finished", status: "succeeded" }])),
        );
      }),
    );

    const seen: RunEvent[] = [];
    const connections: Connection[] = [];
    await followRun(
      "r",
      {
        onEvent: (event) => seen.push(event),
        onConnection: (connection) => connections.push(connection),
      },
      new AbortController().signal,
    );

    expect(sent).toEqual([null, "2"]);
    expect(seen.map((event) => event.seq)).toEqual([1, 2, 3]);
    expect(connections).toEqual(["live", "reconnecting", "live"]);
  });
});
