import { describe, expect, it } from "vitest";

import { decodeMessage } from "./conversation-detail";

function question(options: unknown) {
  return {
    id: "message-1",
    role: "assistant",
    run_id: "run-1",
    text: "Which year?",
    kind: "question",
    grounding: null,
    options,
    created_at: "2026-10-05T12:00:00Z",
  };
}

describe("a question's options", () => {
  it("are read as the strings they are", () => {
    const message = decodeMessage(question(["2024", "2025"]));

    expect(message.options).toEqual(["2024", "2025"]);
  });

  it("are empty when the analyst offered none", () => {
    const message = decodeMessage(question([]));

    expect(message.options).toEqual([]);
  });

  it("are null on a message that is not a question", () => {
    const message = decodeMessage({
      id: "message-0",
      role: "user",
      run_id: "run-1",
      text: "Sales this year?",
      kind: null,
      grounding: null,
      options: null,
      created_at: "2026-10-05T12:00:00Z",
    });

    expect(message.options).toBeNull();
  });

  it("refuse an option that is not a string", () => {
    expect(() => decodeMessage(question([2024]))).toThrow();
  });
});
