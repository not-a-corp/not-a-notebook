import { array, asRecord, isRecord, number, oneOf, string, type Json } from "./decode";

// api.md, Output kind — the same shape in GET /conversations/{id} and, flattened
// after `attempt`, in cell.output events.

export interface StreamOutput {
  kind: "stream";
  name: "stdout" | "stderr";
  text: string;
}

export interface ErrorOutput {
  kind: "error";
  name: string;
  value: string;
  traceback: string[];
}

export interface PlotlyOutput {
  kind: "plotly";
  // A Plotly figure ({data, layout}) as the kernel built it. It is checked to be
  // an object and handed to plotly.js, which validates the rest itself.
  spec: Json;
}

export type TableCell = string | number | boolean | null;

export interface TableOutput {
  kind: "table";
  columns: string[];
  rows: TableCell[][];
  totalRows: number;
}

export interface TextOutput {
  kind: "text";
  text: string;
}

export interface ImageOutput {
  kind: "image";
  png: string;
}

export type Output =
  StreamOutput | ErrorOutput | PlotlyOutput | TableOutput | TextOutput | ImageOutput;

export const OUTPUT_KINDS = ["stream", "error", "plotly", "table", "text", "image"] as const;

function decodeString(value: unknown): string {
  if (typeof value !== "string") {
    throw new TypeError("not a string");
  }
  return value;
}

function decodeTableCell(value: unknown): TableCell {
  if (value === null) {
    return null;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  // A nested value (a list in a cell): shown as its JSON, never dropped.
  return JSON.stringify(value);
}

function decodeRow(value: unknown): TableCell[] {
  if (!Array.isArray(value)) {
    throw new TypeError("a table row is not a list");
  }
  return value.map(decodeTableCell);
}

// The output's fields, read from `json` — a stored output or a flattened event.
export function decodeOutputFields(json: Json): Output {
  const kind = oneOf(json, "kind", OUTPUT_KINDS);

  switch (kind) {
    case "stream":
      return { kind, name: oneOf(json, "name", ["stdout", "stderr"]), text: string(json, "text") };
    case "error":
      return {
        kind,
        name: string(json, "name"),
        value: string(json, "value"),
        traceback: array(json, "traceback", decodeString),
      };
    case "plotly": {
      const spec = json.spec;
      if (!isRecord(spec)) {
        throw new TypeError('"spec" is not an object');
      }
      return { kind, spec };
    }
    case "table":
      return {
        kind,
        columns: array(json, "columns", decodeString),
        rows: array(json, "rows", decodeRow),
        totalRows: number(json, "total_rows"),
      };
    case "text":
      return { kind, text: string(json, "text") };
    case "image":
      return { kind, png: string(json, "png") };
  }
}

export function decodeOutput(value: unknown): Output {
  return decodeOutputFields(asRecord(value, "output"));
}
