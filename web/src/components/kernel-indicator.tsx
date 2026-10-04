import { cn } from "@/lib/cn";

import { Tooltip } from "./ui/tooltip";

export type KernelStatus = "ready" | "busy" | "starting" | "stopped";

// design.md §3.2: a dot, "Kernel", and the state — never the colour alone.
const STATES: Record<KernelStatus, { dot: string; tooltip: string }> = {
  ready: { dot: "bg-success", tooltip: "Variables are in memory" },
  busy: {
    dot: "bg-accent shadow-[0_0_0_4px_color-mix(in_oklab,var(--accent)_22%,transparent)]",
    tooltip: "A run is using the kernel",
  },
  starting: { dot: "animate-pulse bg-text-muted", tooltip: "Starting — a few seconds" },
  stopped: {
    dot: "border-2 border-text-muted",
    tooltip: "The next run starts one — a few seconds",
  },
};

export function KernelIndicator({ status }: { status: KernelStatus }) {
  const state = STATES[status];

  return (
    <Tooltip label={state.tooltip}>
      <span className="flex h-8 items-center gap-2 px-3 text-sm text-text-muted" tabIndex={0}>
        <span className={cn("size-2 rounded-full", state.dot)} />
        Kernel
        <span className="font-medium text-text">{status}</span>
      </span>
    </Tooltip>
  );
}
