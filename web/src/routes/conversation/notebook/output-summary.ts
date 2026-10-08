import { joinStreams } from "@/components/outputs/outputs";
import type { Output } from "@/api/outputs";

// What a cell's closed outputs say on their one line: what is inside, so the
// user knows whether it is worth opening (design.md §2.5).
export interface OutputSummary {
  label: string;
  failed: boolean;
}

function nameOf(output: Output): string {
  switch (output.kind) {
    case "stream":
    case "text":
      return "text";
    case "table":
      return "table";
    case "plotly":
      return "chart";
    case "image":
      return "image";
    case "error":
      return output.name;
    default: {
      const unreachable: never = output;
      return unreachable;
    }
  }
}

export function summarizeOutputs(outputs: Output[]): OutputSummary {
  const counts = new Map<string, number>();
  let failure: string | null = null;

  for (const output of joinStreams(outputs)) {
    if (output.kind === "error") {
      failure = output.name;
      continue;
    }
    const name = nameOf(output);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }

  const parts: string[] = [];
  for (const [name, count] of counts) {
    if (count > 1) {
      parts.push(`${name} ×${String(count)}`);
    } else {
      parts.push(name);
    }
  }

  if (failure !== null) {
    parts.unshift(failure);
    return { label: `Error · ${parts.join(", ")}`, failed: true };
  }

  return { label: `Output · ${parts.join(", ")}`, failed: false };
}
