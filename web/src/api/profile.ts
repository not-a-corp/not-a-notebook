import { isRecord, type Json } from "./decode";

// api.md, the profile: what the sandbox found in a file before any question.
// It is read leniently — a field the drawer does not know is ignored, never a
// crash — because a profile is a report to show, and the API keeps its whole
// shape in api.md's table of finding kinds.

export interface Finding {
  kind: string;
  message: string;
  // Where it sits (design.md §3.6): the file, a table, or a column by name.
  where: string;
  rows: number[];
  count: number | null;
  details: Json;
}

export interface ColumnProfile {
  name: string;
  dtype: string;
  missing: number;
  distinct: number;
  samples: string[];
}

export interface TableProfile {
  sheet: string | null;
  rows: number;
  columnCount: number;
  columns: ColumnProfile[];
  findings: Finding[];
}

export interface Profile {
  format: string;
  readable: boolean;
  error: string | null;
  encoding: string | null;
  sheets: string[];
  findings: Finding[];
  tables: TableProfile[];
}

function text(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  return null;
}

function count(value: unknown): number {
  if (typeof value === "number") {
    return value;
  }
  return 0;
}

function list(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }
  return [];
}

function readFinding(value: unknown, level: "file" | "table"): Finding | null {
  if (!isRecord(value)) {
    return null;
  }
  const kind = text(value.kind);
  const message = text(value.message);
  if (kind === null || message === null) {
    return null;
  }

  const rows: number[] = [];
  for (const row of list(value.rows)) {
    if (typeof row === "number") {
      rows.push(row);
    }
  }

  let total: number | null = null;
  if (typeof value.count === "number") {
    total = value.count;
  }

  return {
    kind,
    message,
    where: text(value.column) ?? level,
    rows,
    count: total,
    details: value,
  };
}

function readFindings(value: unknown, level: "file" | "table"): Finding[] {
  const findings: Finding[] = [];
  for (const item of list(value)) {
    const finding = readFinding(item, level);
    if (finding !== null) {
      findings.push(finding);
    }
  }
  return findings;
}

function readColumn(value: unknown): ColumnProfile | null {
  if (!isRecord(value)) {
    return null;
  }
  const samples: string[] = [];
  for (const sample of list(value.samples)) {
    samples.push(String(sample));
  }

  return {
    name: text(value.name) ?? "",
    dtype: text(value.dtype) ?? "",
    missing: count(value.missing),
    distinct: count(value.distinct),
    samples,
  };
}

function readTable(value: unknown): TableProfile | null {
  if (!isRecord(value)) {
    return null;
  }
  const columns: ColumnProfile[] = [];
  for (const item of list(value.columns)) {
    const column = readColumn(item);
    if (column !== null) {
      columns.push(column);
    }
  }

  return {
    sheet: text(value.sheet),
    rows: count(value.rows),
    columnCount: count(value.column_count),
    columns,
    findings: readFindings(value.findings, "table"),
  };
}

export function readProfile(json: Json): Profile {
  const sheets: string[] = [];
  for (const sheet of list(json.sheets)) {
    if (typeof sheet === "string") {
      sheets.push(sheet);
    }
  }

  const tables: TableProfile[] = [];
  for (const item of list(json.tables)) {
    const table = readTable(item);
    if (table !== null) {
      tables.push(table);
    }
  }

  return {
    format: text(json.format) ?? "unknown",
    readable: json.readable === true,
    error: text(json.error),
    encoding: text(json.encoding),
    sheets,
    findings: readFindings(json.findings, "file"),
    tables,
  };
}

// Every finding, the file's first, then each table's in order.
export function allFindings(profile: Profile): Finding[] {
  const findings = profile.findings.slice();
  for (const table of profile.tables) {
    findings.push(...table.findings);
  }
  return findings;
}
