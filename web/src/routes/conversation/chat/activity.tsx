import { LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { Connection } from "@/api/runs";

import type { Activity } from "../live/live-run";

export function activityLabel(activity: Activity): string {
  switch (activity.kind) {
    case "starting-kernel":
      return "Starting the kernel…";
    case "thinking":
      return "Thinking…";
    case "writing":
      return `Writing cell ${String(activity.cell)}`;
    case "running":
      return `Running cell ${String(activity.cell)}`;
    case "retrying":
      return `Retrying cell ${String(activity.cell)} (attempt ${String(activity.attempt)})`;
  }
}

// design.md §2.4 — inside the analyst's message while the run is live.
export function ActivityLine({
  activity,
  connection,
  onShowCell,
}: {
  activity: Activity | null;
  connection: Connection;
  onShowCell: (cellId: string) => void;
}) {
  let title = "Thinking…";
  let detail: ReactNode = null;
  let cellId: string | null = null;
  let cell: number | null = null;

  if (activity !== null) {
    title = activityLabel(activity);
  }
  if (activity?.kind === "starting-kernel") {
    detail = "A cold start takes a few seconds.";
  }
  if (activity?.kind === "running" || activity?.kind === "retrying") {
    cellId = activity.cellId;
    cell = activity.cell;
  }
  if (activity?.kind === "retrying" && activity.lastError !== null) {
    detail = (
      <>
        Attempt {activity.attempt - 1}: <span className="font-mono">{activity.lastError}</span>
      </>
    );
  }
  if (connection === "reconnecting") {
    title = "Reconnecting…";
    detail = null;
  }

  return (
    <div className="flex items-start gap-2 rounded-md bg-accent-soft px-3 py-2">
      <LoaderCircle className="mt-0.5 size-4 flex-none animate-spin text-accent" />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-sm font-medium">{title}</span>
        {detail !== null && <span className="truncate text-xs text-text-muted">{detail}</span>}
      </div>
      {cellId !== null && cell !== null && (
        <button
          type="button"
          className="font-mono text-xs leading-5 text-accent"
          onClick={() => {
            onShowCell(cellId);
          }}
        >
          [{cell}]
        </button>
      )}
    </div>
  );
}
