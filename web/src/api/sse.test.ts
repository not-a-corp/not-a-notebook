import { describe, expect, it } from "vitest";

import { createSseParser, type SseMessage } from "./sse";

function parse(chunks: string[]): SseMessage[] {
  const messages: SseMessage[] = [];
  const feed = createSseParser((message) => messages.push(message));
  for (const chunk of chunks) {
    feed(chunk);
  }
  return messages;
}

describe("createSseParser", () => {
  it("reads events as the API writes them", () => {
    const messages = parse([
      'event: run.started\nid: 1\ndata: {"seq":1}\n\n',
      'event: llm.delta\nid: 2\ndata: {"seq":2}\n\n',
    ]);

    expect(messages).toEqual([
      { event: "run.started", id: "1", data: '{"seq":1}' },
      { event: "llm.delta", id: "2", data: '{"seq":2}' },
    ]);
  });

  it("joins an event split across chunks anywhere", () => {
    const messages = parse(["event: cell.out", "put\nid: 8\nda", 'ta: {"a":', "1}\r", "\n\r\n"]);

    expect(messages).toEqual([{ event: "cell.output", id: "8", data: '{"a":1}' }]);
  });

  it("ignores the keepalive comment", () => {
    const messages = parse([": keepalive\n\n", "event: x\ndata: 1\n\n"]);

    expect(messages).toEqual([{ event: "x", id: null, data: "1" }]);
  });
});
