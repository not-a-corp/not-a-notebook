import { followRun } from "./runs";

// Resolves when the run has finished — a conversation runs one thing at a time,
// so what comes next waits for this (api.md, One run at a time).
export async function waitForRun(runId: string, signal: AbortSignal): Promise<void> {
  await followRun(
    runId,
    {
      onEvent: () => undefined,
      onConnection: () => undefined,
    },
    signal,
  );
}
