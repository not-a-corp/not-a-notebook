import { TriangleAlert } from "lucide-react";

import type { Cell } from "@/api/conversation-detail";
import { plural } from "@/lib/format";

import { CellView } from "./cell-view";

// design.md §2.5 — the notebook: a banner when something needs saying, then
// the cells.
export function NotebookPane({ cells }: { cells: Cell[] }) {
  const stale = cells.filter((cell) => cell.stale).length;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {stale > 0 && <StaleBanner count={stale} />}
      {cells.length === 0 && (
        <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
          Cells appear here as the analysis runs.
        </div>
      )}
      {cells.length > 0 && (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="flex flex-col gap-6 py-6 pr-8 pl-2">
            {cells.map((cell) => (
              <CellView key={cell.id} cell={cell} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// §3.7. Run all joins it with feat/web-cells, where running cells arrives.
function StaleBanner({ count }: { count: number }) {
  let lead = `${plural(count, "cell", "cells")} are stale.`;
  let rest = "A cell above them changed after they ran.";
  if (count === 1) {
    lead = "1 cell is stale.";
    rest = "A cell above it changed after it ran.";
  }

  return (
    <div className="flex min-h-10 flex-none items-center gap-2 border-b border-border bg-surface py-1 pr-3 pl-4 text-sm">
      <TriangleAlert className="size-4 text-warning" />
      <span className="font-medium">{lead}</span>
      <span className="text-text-muted">{rest}</span>
    </div>
  );
}
