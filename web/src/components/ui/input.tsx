import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

// A focused input turns its border to the accent and carries the ring (§8).
export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-8 w-full rounded-md border border-border bg-bg px-3 text-base text-text placeholder:text-text-muted",
        "focus-visible:border-accent focus-visible:shadow-[0_0_0_2px_var(--surface-raised),0_0_0_4px_var(--accent)] focus-visible:outline-none",
        "aria-invalid:border-danger disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
