// A small Server-Sent Events parser for a fetch body. Not EventSource: it cannot
// send an Authorization header (PLAN decision 12, api.md).

export interface SseMessage {
  event: string;
  id: string | null;
  data: string;
}

// Feed it text as it arrives; it calls `onMessage` for each complete event.
// Chunks split anywhere — inside a line, between \r and \n — and the parser
// keeps what is left over until the next chunk.
export function createSseParser(onMessage: (message: SseMessage) => void) {
  let buffer = "";
  let event = "";
  let id: string | null = null;
  let data: string[] = [];

  function dispatch() {
    if (data.length > 0) {
      onMessage({ event: event === "" ? "message" : event, id, data: data.join("\n") });
    }
    event = "";
    id = null;
    data = [];
  }

  function line(text: string) {
    if (text === "") {
      dispatch();
      return;
    }
    // A comment: the server's keepalive.
    if (text.startsWith(":")) {
      return;
    }

    const colon = text.indexOf(":");
    let field = text;
    let value = "";
    if (colon !== -1) {
      field = text.slice(0, colon);
      value = text.slice(colon + 1);
      if (value.startsWith(" ")) {
        value = value.slice(1);
      }
    }

    if (field === "event") {
      event = value;
    } else if (field === "data") {
      data.push(value);
    } else if (field === "id") {
      id = value;
    }
  }

  return function feed(chunk: string) {
    buffer += chunk;

    for (;;) {
      const match = /\r\n|\r|\n/.exec(buffer);
      if (match === null) {
        return;
      }
      // A \r at the very end may be the first half of \r\n: wait for more.
      if (match[0] === "\r" && match.index === buffer.length - 1) {
        return;
      }
      line(buffer.slice(0, match.index));
      buffer = buffer.slice(match.index + match[0].length);
    }
  };
}
