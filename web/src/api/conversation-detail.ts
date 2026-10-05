import { requestJson } from "./client";
import {
  array,
  asRecord,
  boolean,
  isRecord,
  nullableNumber,
  nullableOneOf,
  nullableString,
  number,
  oneOf,
  string,
  type Json,
} from "./decode";
import { decodeOutput, type Output } from "./outputs";
import type { KernelState } from "./conversations";

// GET /conversations/{id}: everything the conversation screen needs, in one
// call (decision 19). The stream patches this same object as events arrive.

export interface Grounding {
  numbers: number;
  found: number;
  unfound: string[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  runId: string | null;
  text: string;
  // The analyst's: an answer, or a question asked instead of guessing. Yours: null.
  kind: "answer" | "question" | null;
  // An answer's grounding check, kept with it (api.md).
  grounding: Grounding | null;
  // A question's suggested replies, to click or to ignore; empty when it offered
  // none. Null for anything that is not a question (api.md).
  options: string[] | null;
  createdAt: string;
}

// What the screen shows of a profile before the drawer opens it: enough for a
// chip and a line. The whole profile stays as it came, for the drawer to read.
export interface ProfileSummary {
  readable: boolean;
  rows: number;
  columns: number;
  findings: number;
}

export interface FileInfo {
  id: string;
  name: string;
  bytes: number;
  profile: Json | null;
  createdAt: string;
}

export type CellStatus = "new" | "running" | "ok" | "error" | "cancelled";

export interface Cell {
  id: string;
  position: number;
  origin: "agent" | "user";
  runId: string | null;
  source: string;
  status: CellStatus;
  stale: boolean;
  attempts: number;
  executionCount: number | null;
  outputs: Output[];
  executedAt: string | null;
  durationMs: number | null;
}

export interface ConversationDetail {
  id: string;
  title: string;
  modelId: string | null;
  kernel: KernelState;
  activeRunId: string | null;
  files: FileInfo[];
  messages: Message[];
  cells: Cell[];
}

function decodeUnfound(value: unknown): string {
  if (typeof value !== "string") {
    throw new TypeError("an unfound number is not a string");
  }
  return value;
}

function decodeOption(value: unknown): string {
  if (typeof value !== "string") {
    throw new TypeError("an option is not a string");
  }
  return value;
}

function decodeOptions(json: Json): string[] | null {
  if (json.options === null) {
    return null;
  }
  return array(json, "options", decodeOption);
}

function decodeGrounding(value: unknown): Grounding | null {
  if (value === null) {
    return null;
  }
  const json = asRecord(value, "grounding");

  return {
    numbers: number(json, "numbers"),
    found: number(json, "found"),
    unfound: array(json, "unfound", decodeUnfound),
  };
}

export function decodeMessage(value: unknown): Message {
  const json = asRecord(value, "message");

  return {
    id: string(json, "id"),
    role: oneOf(json, "role", ["user", "assistant"]),
    runId: nullableString(json, "run_id"),
    text: string(json, "text"),
    kind: nullableOneOf(json, "kind", ["answer", "question"]),
    grounding: decodeGrounding(json.grounding),
    options: decodeOptions(json),
    createdAt: string(json, "created_at"),
  };
}

export function decodeFile(value: unknown): FileInfo {
  const json = asRecord(value, "file");
  let profile: Json | null = null;
  if (isRecord(json.profile)) {
    profile = json.profile;
  }

  return {
    id: string(json, "id"),
    name: string(json, "name"),
    bytes: number(json, "bytes"),
    profile,
    createdAt: string(json, "created_at"),
  };
}

export const CELL_STATUSES = ["new", "running", "ok", "error", "cancelled"] as const;

export function decodeCell(value: unknown): Cell {
  const json = asRecord(value, "cell");

  return {
    id: string(json, "id"),
    position: number(json, "position"),
    origin: oneOf(json, "origin", ["agent", "user"]),
    runId: nullableString(json, "run_id"),
    source: string(json, "source"),
    status: oneOf(json, "status", CELL_STATUSES),
    stale: boolean(json, "stale"),
    attempts: number(json, "attempts"),
    executionCount: nullableNumber(json, "execution_count"),
    outputs: array(json, "outputs", decodeOutput),
    executedAt: nullableString(json, "executed_at"),
    durationMs: nullableNumber(json, "duration_ms"),
  };
}

export function decodeConversationDetail(value: unknown): ConversationDetail {
  const json = asRecord(value, "conversation");

  return {
    id: string(json, "id"),
    title: string(json, "title"),
    modelId: nullableString(json, "model_id"),
    kernel: oneOf(json, "kernel", ["running", "stopped"]),
    activeRunId: nullableString(json, "active_run_id"),
    files: array(json, "files", decodeFile),
    messages: array(json, "messages", decodeMessage),
    cells: array(json, "cells", decodeCell),
  };
}

export async function getConversationDetail(id: string): Promise<ConversationDetail> {
  return decodeConversationDetail(await requestJson(`/conversations/${id}`));
}

function countFindings(value: unknown): number {
  if (!Array.isArray(value)) {
    return 0;
  }
  return value.length;
}

// Findings sit at the file and at each table; a column's findings are among its
// table's, naming the column (api.md, Findings).
export function summarizeProfile(profile: Json): ProfileSummary {
  if (profile.readable !== true) {
    return { readable: false, rows: 0, columns: 0, findings: 0 };
  }

  let rows = 0;
  let columns = 0;
  let findings = countFindings(profile.findings);
  const tables = Array.isArray(profile.tables) ? profile.tables : [];
  for (const table of tables) {
    if (!isRecord(table)) {
      continue;
    }
    if (typeof table.rows === "number") {
      rows += table.rows;
    }
    if (typeof table.column_count === "number") {
      columns = Math.max(columns, table.column_count);
    }
    findings += countFindings(table.findings);
  }

  return { readable: true, rows, columns, findings };
}
