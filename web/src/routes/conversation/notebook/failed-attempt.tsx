import { ChevronRight, CircleX } from "lucide-react";
import { useState } from "react";

import { PythonCode } from "@/components/code";
import { Outputs } from "@/components/outputs/outputs";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";

import type { FailedAttempt } from "../live/live-run";

// design.md §2.5: a failed attempt is a collapsed row inside its cell; opening
// it shows that attempt's code and its error.
export function FailedAttemptRow({ attempt }: { attempt: FailedAttempt }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col rounded-md border border-border">
      <button
        type="button"
        aria-expanded={open}
        className="flex h-8 items-center gap-2 pr-3 pl-2 text-xs text-text-muted"
        onClick={() => {
          setOpen(!open);
        }}
      >
        <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
        <CircleX className="size-3.5 text-danger" />
        <span className="font-medium text-text">Attempt {attempt.attempt} failed</span>
        {attempt.error !== null && (
          <span className="truncate font-mono font-semibold text-danger">{attempt.error}</span>
        )}
        <span className="flex-1" />
        <span className="whitespace-nowrap">{formatDuration(attempt.durationMs)}</span>
      </button>
      {open && (
        <div className="flex flex-col gap-2 border-t border-border py-2">
          <div className="overflow-x-auto px-3">
            <PythonCode source={attempt.code} />
          </div>
          <Outputs outputs={attempt.outputs} />
        </div>
      )}
    </div>
  );
}
