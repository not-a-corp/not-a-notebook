import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

// design.md §3.1. Primary fills with the accent; secondary is an outline; ghost
// is text; danger is only for deletion.
export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-on-accent hover:bg-accent/90",
        secondary: "border border-border bg-transparent text-text hover:bg-text/8",
        ghost: "bg-transparent text-text hover:bg-text/8",
        danger: "bg-danger text-on-accent hover:bg-danger/90",
      },
      size: {
        default: "h-8 px-3 text-sm",
        compact: "h-7 px-2 text-sm",
        icon: "size-8 text-text-muted",
        "icon-compact": "size-7 text-text-muted",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return (
    <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}
