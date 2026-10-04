import { Check, TriangleAlert } from "lucide-react";

import type { Cell, Grounding, Message } from "@/api/conversation-detail";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/cn";
import { formatCount } from "@/lib/format";

// design.md §3.5. Clicking says what the check does and does not prove.
export function GroundingBadge({
  message,
  grounding,
  cells,
  onShowCell,
}: {
  message: Message;
  grounding: Grounding;
  cells: Cell[];
  onShowCell: (cellId: string) => void;
}) {
  const clean = grounding.unfound.length === 0;
  const fromCells = cells.filter((cell) => cell.runId !== null && cell.runId === message.runId);

  let label = `All ${formatCount(grounding.numbers)} numbers come from the cells' output`;
  if (grounding.numbers === 1) {
    label = "The number comes from the cells' output";
  }
  if (!clean) {
    const missing = grounding.unfound.length;
    let noun = "numbers";
    if (missing === 1) {
      noun = "number";
    }
    label = `${formatCount(missing)} ${noun} not found in any output: ${grounding.unfound.join(", ")}`;
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Popover>
        <PopoverTrigger
          className={cn(
            "inline-flex h-6 items-center gap-1 rounded-full px-2 text-xs font-medium",
            clean && "bg-success/13 text-success",
            !clean && "bg-warning/13 text-warning",
          )}
        >
          {clean && <Check className="size-3.5" strokeWidth={2.25} />}
          {!clean && <TriangleAlert className="size-3.5" />}
          {label}
        </PopoverTrigger>
        <PopoverContent className="flex flex-col gap-2">
          {!clean && (
            <p>
              Not found in any output:{" "}
              <span className="font-mono font-semibold">{grounding.unfound.join(", ")}</span>
            </p>
          )}
          <p className="text-text-muted">
            Every number in the answer is looked for in what the run's code printed or returned. It
            catches invented numbers, not code that silently drops rows.
          </p>
        </PopoverContent>
      </Popover>
      {fromCells.length > 0 && (
        <>
          <span className="text-xs whitespace-nowrap text-text-muted">from cells</span>
          <span className="flex gap-1 font-mono text-xs text-accent">
            {fromCells.map((cell) => (
              <button
                key={cell.id}
                type="button"
                onClick={() => {
                  onShowCell(cell.id);
                }}
              >
                [{cell.executionCount ?? " "}]
              </button>
            ))}
          </span>
        </>
      )}
    </div>
  );
}
