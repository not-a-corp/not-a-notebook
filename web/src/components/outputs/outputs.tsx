import { useState } from "react";

import { isRecord, type Json } from "@/api/decode";
import type { ErrorOutput, Output, TableCell, TableOutput } from "@/api/outputs";
import { cn } from "@/lib/cn";

import { PlotlyChart } from "./plotly-chart";

// Consecutive stream chunks of the same name join (design.md §3.4): stdout
// arrives in chunks, not lines, and a line split across two chunks is one line.
export function joinStreams(outputs: Output[]): Output[] {
  const joined: Output[] = [];

  for (const output of outputs) {
    const last = joined.at(-1);
    if (output.kind === "stream" && last?.kind === "stream" && last.name === output.name) {
      joined[joined.length - 1] = {
        kind: "stream",
        name: last.name,
        text: last.text + output.text,
      };
    } else {
      joined.push(output);
    }
  }

  return joined;
}

export function Outputs({ outputs }: { outputs: Output[] }) {
  const shown = joinStreams(outputs);

  return (
    <>
      {shown.map((output, index) => (
        <OutputView key={index} output={output} />
      ))}
    </>
  );
}

function OutputView({ output }: { output: Output }) {
  switch (output.kind) {
    case "stream":
      return (
        <pre
          className={cn(
            "px-3 font-mono text-sm whitespace-pre-wrap",
            output.name === "stderr" && "text-warning",
          )}
        >
          {output.text}
        </pre>
      );
    case "text":
      return <pre className="px-3 font-mono text-sm whitespace-pre-wrap">{output.text}</pre>;
    case "error":
      return <ErrorView output={output} />;
    case "table":
      return <TableView output={output} />;
    case "plotly":
      return (
        <div className="px-3">
          <PlotlyChart spec={output.spec} label={chartLabel(output.spec)} />
        </div>
      );
    case "image":
      return (
        <figure className="flex flex-col gap-1 px-3">
          <img src={`data:image/png;base64,${output.png}`} alt="" className="max-w-full" />
          <figcaption className="text-xs text-text-muted">matplotlib</figcaption>
        </figure>
      );
  }
}

// design.md §8: a chart's text alternative, from its title and trace names.
export function chartLabel(spec: Json): string {
  let title = "Chart";
  const layout = spec.layout;
  if (isRecord(layout) && isRecord(layout.title) && typeof layout.title.text === "string") {
    title = `Chart: ${layout.title.text}`;
  }

  const names: string[] = [];
  if (Array.isArray(spec.data)) {
    for (const trace of spec.data) {
      if (isRecord(trace) && typeof trace.name === "string" && trace.name !== "") {
        names.push(trace.name);
      }
    }
  }

  if (names.length === 0) {
    return title;
  }
  return `${title}. ${names.join(", ")}.`;
}

const TRACEBACK_TAIL = 6;

// An interrupt has a name and no message: "KeyboardInterrupt", not "…Interrupt:".
function errorTitle(output: ErrorOutput): string {
  if (output.value === "") {
    return output.name;
  }
  return `${output.name}: ${output.value}`;
}

// A red left rule; the exception in bold; the traceback cut to its last frames
// until asked for (§3.4).
function ErrorView({ output }: { output: ErrorOutput }) {
  const [all, setAll] = useState(false);
  const lines = output.traceback.join("\n").split("\n");
  const hidden = lines.length - TRACEBACK_TAIL;

  let shown = lines;
  if (!all && hidden > 0) {
    shown = lines.slice(-TRACEBACK_TAIL);
  }

  return (
    <div className="mx-3 flex flex-col gap-1 border-l-2 border-danger pl-3">
      <p className="font-mono text-sm font-semibold text-danger">{errorTitle(output)}</p>
      {lines.length > 0 && (
        <pre className="font-mono text-xs whitespace-pre-wrap text-text-muted">
          {shown.join("\n")}
        </pre>
      )}
      {hidden > 0 && (
        <button
          type="button"
          className="self-start text-xs font-medium text-accent"
          onClick={() => {
            setAll(!all);
          }}
        >
          {all ? "Show less" : `Show all ${String(lines.length)} lines`}
        </button>
      )}
    </div>
  );
}

function isNumeric(column: number, rows: TableCell[][]): boolean {
  let numbers = 0;
  for (const row of rows) {
    const value = row[column];
    if (typeof value === "number") {
      numbers += 1;
    } else if (value !== null && value !== undefined) {
      return false;
    }
  }
  return numbers > 0;
}

function TableView({ output }: { output: TableOutput }) {
  const numeric = output.columns.map((_, column) => isNumeric(column, output.rows));

  return (
    <div className="ml-3 max-h-[420px] max-w-[calc(100%-24px)] self-start overflow-auto rounded-md border border-border">
      <table className="border-collapse font-mono text-sm whitespace-nowrap tabular-nums">
        <thead className="sticky top-0 bg-surface">
          <tr>
            {output.columns.map((column, index) => (
              <th
                key={index}
                className={cn(
                  "border-b border-border px-2 py-0.5 font-semibold",
                  numeric[index] === true ? "text-right" : "text-left",
                )}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {output.rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-border first:border-t-0">
              {row.map((value, column) => (
                <td
                  key={column}
                  className={cn("px-2 py-0.5", numeric[column] === true && "text-right")}
                >
                  <TableValue value={value} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableValue({ value }: { value: TableCell }) {
  if (value === null) {
    return <span className="text-text-muted italic">null</span>;
  }
  return <>{String(value)}</>;
}
