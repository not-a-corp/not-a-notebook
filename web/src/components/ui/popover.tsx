import { Popover as Primitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Popover = Primitive.Root;
export const PopoverTrigger = Primitive.Trigger;

export function PopoverContent({
  className,
  sideOffset = 4,
  align = "start",
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  return (
    <Primitive.Portal>
      <Primitive.Content
        sideOffset={sideOffset}
        align={align}
        className={cn(
          "z-50 w-80 rounded-lg border border-border bg-surface-raised p-3 text-sm text-text shadow-overlay",
          className,
        )}
        {...props}
      />
    </Primitive.Portal>
  );
}
