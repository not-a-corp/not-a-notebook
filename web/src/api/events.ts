import {
  decodeCell,
  decodeFile,
  decodeMessage,
  type Cell,
  type FileInfo,
  type Message,
} from "./conversation-detail";
import {
  array,
  asRecord,
  isRecord,
  nullableNumber,
  nullableString,
  number,
  oneOf,
  string,
  type Json,
} from "./decode";
import { decodeOutputFields, type Output } from "./outputs";

// events.md, payload by payload: one discriminated union on `type`. A switch
// over it ends in an exhaustive check, so a new event that is not handled does
// not compile (CLAUDE.md).

export const RUN_KINDS = ["message", "profile", "cell", "run_all"] as const;
export type RunKind = (typeof RUN_KINDS)[number];

export const RUN_STATUSES = [
  "succeeded",
  "awaiting_user",
  "failed",
  "cancelled",
  "timed_out",
] as const;
export type FinishedStatus = (typeof RUN_STATUSES)[number];

export const RESTART_REASONS = ["idle", "died", "requested", "run_all", "lost"] as const;
export type RestartReason = (typeof RESTART_REASONS)[number];

export const ATTEMPT_STATUSES = ["ok", "error", "cancelled", "timed_out"] as const;
export type AttemptStatus = (typeof ATTEMPT_STATUSES)[number];

interface Envelope {
  seq: number;
  t: number;
}

export type RunEvent = Envelope &
  (
    | { type: "run.started"; runId: string; kind: RunKind; model: string | null }
    | { type: "run.error"; code: string; message: string; errorId: string | null }
    | { type: "run.finished"; status: FinishedStatus }
    | { type: "kernel.starting" }
    | { type: "kernel.ready"; startupMs: number }
    | { type: "kernel.restarted"; reason: RestartReason }
    | { type: "file.uploaded"; file: FileInfo }
    | { type: "file.profiled"; fileId: string; profile: Json }
    | { type: "llm.started"; step: number }
    | { type: "llm.delta"; step: number; text: string }
    | { type: "llm.finished"; step: number; stop: string }
    | { type: "code.proposed"; step: number; cellId: string; attempt: number; code: string }
    | { type: "attempt.started"; cellId: string; attempt: number }
    | {
        type: "attempt.finished";
        cellId: string;
        attempt: number;
        status: AttemptStatus;
        executionCount: number | null;
        durationMs: number;
      }
    | { type: "cell.created"; cell: Cell }
    | { type: "cell.started"; cellId: string }
    | { type: "cell.output"; cellId: string; attempt: number | null; output: Output }
    | {
        type: "cell.finished";
        cellId: string;
        status: "ok" | "error" | "cancelled";
        attempts: number;
        executionCount: number | null;
        durationMs: number | null;
      }
    | { type: "cells.stale"; cellIds: string[] }
    | { type: "answer"; message: Message }
    | { type: "grounding.checked"; numbers: number; found: number; unfound: string[] }
    | { type: "question"; message: Message }
  );

export const EVENT_TYPES = [
  "run.started",
  "run.error",
  "run.finished",
  "kernel.starting",
  "kernel.ready",
  "kernel.restarted",
  "file.uploaded",
  "file.profiled",
  "llm.started",
  "llm.delta",
  "llm.finished",
  "code.proposed",
  "attempt.started",
  "attempt.finished",
  "cell.created",
  "cell.started",
  "cell.output",
  "cell.finished",
  "cells.stale",
  "answer",
  "grounding.checked",
  "question",
] as const;

function decodeString(value: unknown): string {
  if (typeof value !== "string") {
    throw new TypeError("not a string");
  }
  return value;
}

export function decodeRunEvent(value: unknown): RunEvent {
  const json = asRecord(value, "event");
  const seq = number(json, "seq");
  const t = number(json, "t");
  const type = oneOf(json, "type", EVENT_TYPES);

  switch (type) {
    case "run.started":
      return {
        seq,
        t,
        type,
        runId: string(json, "run_id"),
        kind: oneOf(json, "kind", RUN_KINDS),
        model: nullableString(json, "model"),
      };
    case "run.error":
      return {
        seq,
        t,
        type,
        code: string(json, "code"),
        message: string(json, "message"),
        errorId: nullableString(json, "error_id"),
      };
    case "run.finished":
      return { seq, t, type, status: oneOf(json, "status", RUN_STATUSES) };
    case "kernel.starting":
      return { seq, t, type };
    case "kernel.ready":
      return { seq, t, type, startupMs: number(json, "startup_ms") };
    case "kernel.restarted":
      return { seq, t, type, reason: oneOf(json, "reason", RESTART_REASONS) };
    case "file.uploaded":
      return { seq, t, type, file: decodeFile(json.file) };
    case "file.profiled": {
      const profile = json.profile;
      if (!isRecord(profile)) {
        throw new TypeError('"profile" is not an object');
      }
      return { seq, t, type, fileId: string(json, "file_id"), profile };
    }
    case "llm.started":
      return { seq, t, type, step: number(json, "step") };
    case "llm.delta":
      return { seq, t, type, step: number(json, "step"), text: string(json, "text") };
    case "llm.finished":
      return { seq, t, type, step: number(json, "step"), stop: string(json, "stop") };
    case "code.proposed":
      return {
        seq,
        t,
        type,
        step: number(json, "step"),
        cellId: string(json, "cell_id"),
        attempt: number(json, "attempt"),
        code: string(json, "code"),
      };
    case "attempt.started":
      return { seq, t, type, cellId: string(json, "cell_id"), attempt: number(json, "attempt") };
    case "attempt.finished":
      return {
        seq,
        t,
        type,
        cellId: string(json, "cell_id"),
        attempt: number(json, "attempt"),
        status: oneOf(json, "status", ATTEMPT_STATUSES),
        executionCount: nullableNumber(json, "execution_count"),
        durationMs: number(json, "duration_ms"),
      };
    case "cell.created":
      return { seq, t, type, cell: decodeCell(json.cell) };
    case "cell.started":
      return { seq, t, type, cellId: string(json, "cell_id") };
    case "cell.output":
      return {
        seq,
        t,
        type,
        cellId: string(json, "cell_id"),
        attempt: nullableNumber(json, "attempt"),
        // The output's own fields are flattened into the event after `kind`.
        output: decodeOutputFields(json),
      };
    case "cell.finished":
      return {
        seq,
        t,
        type,
        cellId: string(json, "cell_id"),
        status: oneOf(json, "status", ["ok", "error", "cancelled"]),
        attempts: number(json, "attempts"),
        executionCount: nullableNumber(json, "execution_count"),
        durationMs: nullableNumber(json, "duration_ms"),
      };
    case "cells.stale":
      return { seq, t, type, cellIds: array(json, "cell_ids", decodeString) };
    case "answer":
      return { seq, t, type, message: decodeMessage(json.message) };
    case "grounding.checked":
      return {
        seq,
        t,
        type,
        numbers: number(json, "numbers"),
        found: number(json, "found"),
        unfound: array(json, "unfound", decodeString),
      };
    case "question":
      return { seq, t, type, message: decodeMessage(json.message) };
  }
}
