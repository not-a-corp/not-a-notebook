import { Dialog } from "radix-ui";

// design.md §7 — the `?` overlay. Shortcuts follow Jupyter's where it has one.
const SHORTCUTS: [string, string][] = [
  ["Enter", "Edit the focused cell · send, in a composer"],
  ["Escape", "Leave the cell editor · close a drawer or dialog"],
  ["Shift+Enter", "Run the cell and move to the next"],
  ["Ctrl/Cmd+Enter", "Run the cell and stay"],
  ["↑ / ↓", "Move between cells"],
  ["A / B", "Add a cell above / below"],
  ["D D", "Delete the focused cell"],
  ["Ctrl/Cmd+Shift+Enter", "Run all"],
  ["Ctrl/Cmd+K", "Search conversations"],
  ["?", "This list"],
];

export function ShortcutsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-scrim" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed top-1/2 left-1/2 z-50 flex w-[440px] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 rounded-xl border border-border bg-surface-raised p-6 shadow-overlay"
        >
          <Dialog.Title className="text-md font-semibold">Keyboard</Dialog.Title>
          <table className="text-sm">
            <tbody>
              {SHORTCUTS.map(([keys, action]) => (
                <tr key={keys}>
                  <td className="py-1 pr-4 align-top whitespace-nowrap">
                    <kbd className="rounded-sm border border-border px-1 font-mono text-xs text-text-muted">
                      {keys}
                    </kbd>
                  </td>
                  <td className="py-1 text-text-muted">{action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
