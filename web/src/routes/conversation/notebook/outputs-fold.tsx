import { ChevronRight } from "lucide-react";
import { useState } from "react";

import type { Output } from "@/api/outputs";
import { Outputs } from "@/components/outputs/outputs";
import { cn } from "@/lib/cn";

import { summarizeOutputs } from "./output-summary";

// A cell's outputs, closed until asked for: a notebook of a dozen cells is a
// dozen lines, not a dozen tables (design.md §2.5).
export function OutputsFold({ outputs }: { outputs: Output[] }) {
  const [open, setOpen] = useState(false);

  if (outputs.length === 0) {
    return null;
  }

  const summary = summarizeOutputs(outputs);

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        aria-expanded={open}
        className={cn(
          "flex h-6 items-center gap-1.5 self-start pl-2 text-xs text-text-muted hover:text-text",
          summary.failed && "text-danger hover:text-danger",
        )}
        // Pressing must not focus the cell: its header would slide in above and
        // move this button from under the pointer before the release, and the
        // click would be lost.
        onMouseDown={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
        onClick={() => {
          setOpen(!open);
        }}
      >
        <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
        <span className="font-medium">{summary.label}</span>
      </button>
      {open && <Outputs outputs={outputs} />}
    </div>
  );
}
