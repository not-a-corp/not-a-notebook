import type { LucideIcon } from "lucide-react";
import type { ReactNode, Ref } from "react";

// design.md §2.1 — two panes, each under a 36 px tab strip, split 40/60. Swap,
// resize and maximise arrive with feat/web-panes.

interface PaneProps {
  icon: LucideIcon;
  label: string;
  detail?: string;
  className: string;
  children: ReactNode;
  ref?: Ref<HTMLElement>;
}

export function Pane({ icon: Icon, label, detail, className, children, ref }: PaneProps) {
  return (
    <section ref={ref} aria-label={label} className={className}>
      <div className="flex h-9 flex-none items-stretch border-b border-border pr-1 pl-2">
        <div className="flex items-center gap-2 px-3 text-sm font-medium whitespace-nowrap shadow-[inset_0_-2px_0_var(--text)]">
          <Icon className="size-3.5 text-text-muted" />
          {label}
          {detail !== undefined && <span className="font-normal text-text-muted">· {detail}</span>}
        </div>
      </div>
      {children}
    </section>
  );
}
