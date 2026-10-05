import { X } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";

// design.md §3.8: bottom-right, for what happened elsewhere or failed quietly
// — never for a success that is already visible.

interface Toast {
  id: number;
  text: string;
}

let toasts: Toast[] = [];
let next = 1;
const listeners = new Set<() => void>();

function publish(list: Toast[]) {
  toasts = list;
  for (const listener of listeners) {
    listener();
  }
}

export function toast(text: string): void {
  publish([...toasts, { id: next, text }]);
  next += 1;
}

function dismiss(id: number): void {
  publish(toasts.filter((item) => item.id !== id));
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const LIFETIME_MS = 6000;

export function Toaster() {
  const shown = useSyncExternalStore(subscribe, () => toasts);

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[360px] flex-col gap-2"
    >
      {shown.map((item) => (
        <ToastView key={item.id} item={item} />
      ))}
    </div>
  );
}

function ToastView({ item }: { item: Toast }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      dismiss(item.id);
    }, LIFETIME_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [item.id]);

  return (
    <div className="pointer-events-auto flex items-start gap-2 rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm shadow-overlay">
      <span className="flex-1">{item.text}</span>
      <button
        type="button"
        aria-label="Dismiss"
        className="text-text-muted"
        onClick={() => {
          dismiss(item.id);
        }}
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
