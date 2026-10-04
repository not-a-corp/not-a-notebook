import { DropdownMenu as Primitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const DropdownMenu = Primitive.Root;
export const DropdownMenuTrigger = Primitive.Trigger;

export function DropdownMenuContent({
  className,
  sideOffset = 4,
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  return (
    <Primitive.Portal>
      <Primitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-40 rounded-lg border border-border bg-surface-raised p-1 text-sm text-text shadow-overlay",
          className,
        )}
        {...props}
      />
    </Primitive.Portal>
  );
}

export function DropdownMenuItem({ className, ...props }: ComponentProps<typeof Primitive.Item>) {
  return (
    <Primitive.Item
      className={cn(
        "flex h-8 cursor-default items-center gap-2 rounded-md px-2 outline-none select-none data-[disabled]:opacity-50 data-[highlighted]:bg-text/8 [&_svg]:size-4 [&_svg]:text-text-muted",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuLabel({ className, ...props }: ComponentProps<typeof Primitive.Label>) {
  return (
    <Primitive.Label
      className={cn("px-2 py-1 text-xs font-medium text-text-muted", className)}
      {...props}
    />
  );
}

export function DropdownMenuSeparator({
  className,
  ...props
}: ComponentProps<typeof Primitive.Separator>) {
  return <Primitive.Separator className={cn("my-1 h-px bg-border", className)} {...props} />;
}

export const DropdownMenuRadioGroup = Primitive.RadioGroup;

export function DropdownMenuRadioItem({
  className,
  children,
  ...props
}: ComponentProps<typeof Primitive.RadioItem>) {
  return (
    <Primitive.RadioItem
      className={cn(
        "flex h-8 cursor-default items-center gap-2 rounded-md pr-2 pl-7 outline-none select-none data-[highlighted]:bg-text/8 data-[state=checked]:font-medium",
        "relative",
        className,
      )}
      {...props}
    >
      <Primitive.ItemIndicator className="absolute left-2 size-1.5 rounded-full bg-accent" />
      {children}
    </Primitive.RadioItem>
  );
}
