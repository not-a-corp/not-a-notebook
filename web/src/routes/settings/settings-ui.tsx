import type { ReactNode } from "react";

// design.md §2.6: a section is a title and one line of what it is for, then
// groups of rows — label and help on the left, the control on the right.

export function SectionTitle({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-end gap-4">
      <div className="flex flex-1 flex-col gap-1">
        <h1 className="text-lg font-semibold">{title}</h1>
        <p className="text-pretty text-text-muted">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold">{label}</h2>
      <div className="rounded-lg border border-border [&>*+*]:border-t [&>*+*]:border-border">
        {children}
      </div>
    </section>
  );
}

export function Row({
  label,
  help,
  children,
}: {
  label: ReactNode;
  help?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid grid-cols-[200px_minmax(0,1fr)] gap-6 p-4">
      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium">{label}</span>
        {help !== undefined && <span className="text-sm text-pretty text-text-muted">{help}</span>}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
