import { request, requestJson } from "./client";
import { decodeMessage, type Message } from "./conversation-detail";
import { asRecord, string } from "./decode";
import { ApiError } from "./errors";
import { decodeRunEvent, type RunEvent } from "./events";
import { createSseParser } from "./sse";

export interface MessageAccepted {
  message: Message;
  runId: string;
}

export async function sendMessage(conversationId: string, text: string): Promise<MessageAccepted> {
  const body = await requestJson(`/conversations/${conversationId}/messages`, {
    method: "POST",
    json: { text },
  });
  const json = asRecord(body, "message accepted");

  return { message: decodeMessage(json.message), runId: string(json, "run_id") };
}

export async function cancelRun(runId: string): Promise<void> {
  await request(`/runs/${runId}/cancel`, { method: "POST" });
}

export type Connection = "live" | "reconnecting";

export interface FollowHandlers {
  onEvent: (event: RunEvent) => void;
  onConnection: (connection: Connection) => void;
}

const RETRY_MS = [500, 1000, 2000, 4000, 8000];

// A function rather than reading the property inline: TypeScript narrows
// `signal.aborted` to false inside the loop and would not let it change.
function isAborted(signal: AbortSignal): boolean {
  return signal.aborted;
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

// One connection: reads until the stream closes. Returns the last seq seen and
// whether run.finished arrived — after it, there is nothing more to follow.
async function readOnce(
  runId: string,
  after: number,
  handlers: FollowHandlers,
  signal: AbortSignal,
): Promise<{ last: number; finished: boolean }> {
  const headers: Record<string, string> = {};
  if (after > 0) {
    headers["Last-Event-ID"] = String(after);
  }

  const response = await request(`/runs/${runId}/events`, { headers, signal });
  const body = response.body;
  if (body === null) {
    return { last: after, finished: false };
  }

  handlers.onConnection("live");

  let last = after;
  let finished = false;
  const feed = createSseParser((message) => {
    const event = decodeRunEvent(JSON.parse(message.data));
    last = event.seq;
    if (event.type === "run.finished") {
      finished = true;
    }
    handlers.onEvent(event);
  });

  const reader = body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const chunk = await reader.read();
    if (chunk.done) {
      break;
    }
    feed(chunk.value);
  }

  return { last, finished };
}

// GET /runs/{id}/events, followed until run.finished. A dropped connection is
// resumed with Last-Event-ID — the API replays what was missed from storage, so
// nothing is lost — after a short, growing pause. Aborting the signal stops it.
export async function followRun(
  runId: string,
  handlers: FollowHandlers,
  signal: AbortSignal,
): Promise<void> {
  let last = 0;
  let failures = 0;

  while (!signal.aborted) {
    try {
      const result = await readOnce(runId, last, handlers, signal);
      last = result.last;
      if (result.finished) {
        return;
      }
      failures = 0;
    } catch (error) {
      // Aborting cancels the fetch mid-read, which lands here as an error.
      if (isAborted(signal)) {
        return;
      }
      // The run itself is gone (deleted with its conversation): nothing to resume.
      if (error instanceof ApiError && error.code === "RUN_NOT_FOUND") {
        return;
      }
      failures += 1;
    }

    handlers.onConnection("reconnecting");
    const pause = RETRY_MS[Math.min(failures, RETRY_MS.length - 1)] ?? 8000;
    await wait(pause, signal);
  }
}
