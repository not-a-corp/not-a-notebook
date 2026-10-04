import { AlertDialog as Primitive } from "radix-ui";
import type { ReactNode } from "react";

import { Button } from "./button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  children?: ReactNode;
}

// A question that must be answered before something that cannot be undone.
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  onConfirm,
  onOpenChange,
}: ConfirmDialogProps) {
  return (
    <Primitive.Root open={open} onOpenChange={onOpenChange}>
      <Primitive.Portal>
        <Primitive.Overlay className="fixed inset-0 z-50 bg-scrim" />
        <Primitive.Content className="fixed top-1/2 left-1/2 z-50 flex w-[400px] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-xl border border-border bg-surface-raised p-6 shadow-overlay">
          <div className="flex flex-col gap-1">
            <Primitive.Title className="text-md font-semibold">{title}</Primitive.Title>
            <Primitive.Description className="text-sm text-text-muted">
              {description}
            </Primitive.Description>
          </div>
          <div className="flex justify-end gap-2">
            <Primitive.Cancel asChild>
              <Button variant="secondary">Cancel</Button>
            </Primitive.Cancel>
            <Primitive.Action asChild>
              <Button variant="danger" onClick={onConfirm}>
                {confirmLabel}
              </Button>
            </Primitive.Action>
          </div>
        </Primitive.Content>
      </Primitive.Portal>
    </Primitive.Root>
  );
}
