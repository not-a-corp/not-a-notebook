import type { Output } from "@/api/outputs";
import { followRun } from "@/api/runs";

import type { FailedAttempt } from "../live/live-run";

interface Attempt {
  code: string;
  outputs: Output[];
  status: string | null;
  durationMs: number;
}

// A settled cell's failed attempts live only in its run's events (decision 18):
// replayed from storage, the run already over, and read for this cell alone.
export async function loadFailedAttempts(runId: string, cellId: string): Promise<FailedAttempt[]> {
  const attempts = new Map<number, Attempt>();

  function attempt(number: number): Attempt {
    let known = attempts.get(number);
    if (known === undefined) {
      known = { code: "", outputs: [], status: null, durationMs: 0 };
      attempts.set(number, known);
    }
    return known;
  }

  await followRun(
    runId,
    {
      onEvent: (event) => {
        if (event.type === "code.proposed" && event.cellId === cellId) {
          attempt(event.attempt).code = event.code;
        }
        if (event.type === "cell.output" && event.cellId === cellId && event.attempt !== null) {
          attempt(event.attempt).outputs.push(event.output);
        }
        if (event.type === "attempt.finished" && event.cellId === cellId) {
          const finished = attempt(event.attempt);
          finished.status = event.status;
          finished.durationMs = event.durationMs;
        }
      },
      onConnection: () => undefined,
    },
    new AbortController().signal,
  );

  const failed: FailedAttempt[] = [];
  for (const [number, known] of [...attempts.entries()].sort((a, b) => a[0] - b[0])) {
    if (known.status !== "error" && known.status !== "timed_out") {
      continue;
    }
    let error: string | null = null;
    for (const output of known.outputs) {
      if (output.kind === "error") {
        error = `${output.name}: ${output.value}`;
      }
    }
    failed.push({
      attempt: number,
      code: known.code,
      error,
      outputs: known.outputs,
      durationMs: known.durationMs,
    });
  }
  return failed;
}
