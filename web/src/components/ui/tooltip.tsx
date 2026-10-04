import { Tooltip as Primitive } from "radix-ui";
import type { ReactNode } from "react";

// Icon buttons have a tooltip, always (design.md §3.1).
export const TooltipProvider = Primitive.Provider;

interface TooltipProps {
  label: string;
  side?: "top" | "right" | "bottom" | "left";
  children: ReactNode;
}

export function Tooltip({ label, side = "bottom", children }: TooltipProps) {
  return (
    <Primitive.Root>
      <Primitive.Trigger asChild>{children}</Primitive.Trigger>
      <Primitive.Portal>
        <Primitive.Content
          side={side}
          sideOffset={4}
          className="z-50 rounded-md bg-text px-2 py-1 text-xs font-medium text-bg shadow-overlay"
        >
          {label}
        </Primitive.Content>
      </Primitive.Portal>
    </Primitive.Root>
  );
}
