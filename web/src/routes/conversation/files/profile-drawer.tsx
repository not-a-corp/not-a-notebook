import { useQueryClient } from "@tanstack/react-query";
import {
  Calendar,
  CaseSensitive,
  ChartPie,
  CircleDashed,
  Copy,
  EqualNot,
  FileSpreadsheet,
  Hash,
  Rows3,
  Sheet,
  Sigma,
  Trash,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import { Dialog } from "radix-ui";
import { useState, type ReactNode } from "react";

import type { FileInfo } from "@/api/conversation-detail";
import { isRecord } from "@/api/decode";
import { deleteFile } from "@/api/files";
import { allFindings, readProfile, type Finding, type Profile } from "@/api/profile";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/toaster";
import { Tooltip } from "@/components/ui/tooltip";
import { formatBytes, formatCount, plural } from "@/lib/format";
import { sentenceForError } from "@/lib/words";

import { conversationKey } from "../live/use-live-run";

// design.md §3.6 — the profile drawer, over the notebook pane.

const ICONS: Record<string, LucideIcon> = {
  data_not_on_first_sheet: Sheet,
  header_not_on_first_row: Rows3,
  subtotal_rows: Sigma,
  exact_duplicates: Copy,
  number_formats: Hash,
  date_formats: Calendar,
  inconsistent_labels: CaseSensitive,
  contradicting_columns: EqualNot,
  dominating_value: ChartPie,
  missing_values: CircleDashed,
};

interface ProfileDrawerProps {
  conversationId: string;
  file: FileInfo | null;
  container: HTMLElement | null;
  busy: boolean;
  onClose: () => void;
}

export function ProfileDrawer({
  conversationId,
  file,
  container,
  busy,
  onClose,
}: ProfileDrawerProps) {
  const open = file !== null;

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
    >
      <Dialog.Portal container={container}>
        <Dialog.Overlay className="absolute inset-0 z-20 bg-scrim" />
        <Dialog.Content
          aria-describedby={undefined}
          // Focus lands on Close, not on Delete: the first thing Escape or
          // Enter does here should never be the destructive one.
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            const target = event.currentTarget;
            if (target instanceof HTMLElement) {
              target.querySelector<HTMLElement>("[data-drawer-close]")?.focus();
            }
          }}
          className="absolute top-2 right-2 bottom-2 z-30 flex w-[480px] max-w-[calc(100%-16px)] flex-col overflow-hidden rounded-xl border border-border bg-surface-raised shadow-overlay"
        >
          {file !== null && (
            <DrawerBody conversationId={conversationId} file={file} busy={busy} onClose={onClose} />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function DrawerBody({
  conversationId,
  file,
  busy,
  onClose,
}: {
  conversationId: string;
  file: FileInfo;
  busy: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  async function remove() {
    try {
      await deleteFile(conversationId, file.id);
      onClose();
      await queryClient.invalidateQueries({ queryKey: conversationKey(conversationId) });
    } catch (error) {
      toast(sentenceForError(error));
    }
  }

  let profile: Profile | null = null;
  if (file.profile !== null) {
    profile = readProfile(file.profile);
  }

  return (
    <>
      <div className="flex flex-none flex-col gap-2 border-b border-border py-4 pr-3 pl-6">
        <div className="flex items-center gap-2">
          <FileSpreadsheet className="size-5 text-text-muted" />
          <Dialog.Title className="min-w-0 flex-1 truncate text-md font-semibold">
            {file.name}
          </Dialog.Title>
          <Tooltip label="Delete file">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Delete file"
              disabled={busy}
              onClick={() => {
                setConfirming(true);
              }}
            >
              <Trash className="size-4" />
            </Button>
          </Tooltip>
          <Dialog.Close asChild>
            <Button variant="ghost" size="icon" aria-label="Close" data-drawer-close>
              <X className="size-4" />
            </Button>
          </Dialog.Close>
        </div>
        <Facts file={file} profile={profile} />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-6 pt-4 pb-6">
        {profile === null && (
          <p className="text-sm text-text-muted">The profile is still running…</p>
        )}
        {profile !== null && !profile.readable && (
          <p className="text-sm text-danger">
            This file couldn't be read{profile.error !== null && `: ${profile.error}`}
          </p>
        )}
        {profile?.readable === true && <ProfileReport profile={profile} />}
      </div>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Delete ${file.name}?`}
        description="It is gone from disk. Cells that read it keep their code and outputs, and fail the next time they run."
        confirmLabel="Delete"
        onConfirm={() => {
          void remove();
        }}
      />
    </>
  );
}

function Facts({ file, profile }: { file: FileInfo; profile: Profile | null }) {
  const facts: string[] = [];
  if (profile !== null) {
    facts.push(profile.format.toUpperCase());
  }
  facts.push(formatBytes(file.bytes));
  if (profile?.encoding != null) {
    facts.push(profile.encoding);
  }
  if (profile !== null && profile.sheets.length > 1) {
    facts.push(plural(profile.sheets.length, "sheet", "sheets"));
  }
  for (const table of profile?.tables ?? []) {
    let shape = `${formatCount(table.rows)} rows × ${formatCount(table.columnCount)} columns`;
    if (table.sheet !== null && profile !== null && profile.sheets.length > 1) {
      shape = `${table.sheet}: ${shape}`;
    }
    facts.push(shape);
  }

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs whitespace-nowrap text-text-muted">
      {facts.map((fact) => (
        <span key={fact}>{fact}</span>
      ))}
    </div>
  );
}

function ProfileReport({ profile }: { profile: Profile }) {
  const findings = allFindings(profile);
  const flagged = new Set(findings.map((finding) => finding.where));

  return (
    <>
      <section className="flex flex-col gap-2">
        <div className="flex items-baseline gap-2">
          <h3 className="text-sm font-semibold">Findings</h3>
          <span className="text-xs font-medium text-warning">{findings.length}</span>
          <div className="flex-1" />
          <span className="text-xs whitespace-nowrap text-text-muted">
            The profile reports. It doesn't change the data.
          </span>
        </div>
        {findings.length === 0 && (
          <p className="text-sm text-text-muted">Nothing a careful analyst would stop at.</p>
        )}
        {findings.map((finding, index) => (
          <FindingCard key={index} finding={finding} />
        ))}
      </section>

      {profile.tables.map((table, index) => (
        <section key={index} className="flex flex-col gap-2">
          <div className="flex items-baseline gap-2">
            <h3 className="text-sm font-semibold">Columns</h3>
            <span className="text-xs text-text-muted">
              {table.columnCount}
              {table.sheet !== null && profile.sheets.length > 1 && ` · ${table.sheet}`}
            </span>
          </div>
          <table className="w-full border-collapse text-xs tabular-nums">
            <thead>
              <tr className="text-text-muted">
                <th className="border-b border-border py-1 pr-2 text-left font-medium">Name</th>
                <th className="border-b border-border px-2 py-1 text-left font-medium">Type</th>
                <th className="border-b border-border px-2 py-1 text-right font-medium">Missing</th>
                <th className="border-b border-border px-2 py-1 text-right font-medium">
                  Distinct
                </th>
                <th className="border-b border-border py-1 pl-2 text-left font-medium">Samples</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {table.columns.map((column) => (
                <tr key={column.name} className="border-t border-border first:border-t-0">
                  <td className="py-1 pr-2">
                    <span className="flex items-center gap-1">
                      {column.name}
                      {flagged.has(column.name) && (
                        <TriangleAlert
                          aria-label="Has a finding"
                          className="size-3 flex-none text-warning"
                        />
                      )}
                    </span>
                  </td>
                  <td className="px-2 py-1 text-text-muted">{column.dtype}</td>
                  <td className="px-2 py-1 text-right">{formatCount(column.missing)}</td>
                  <td className="px-2 py-1 text-right">{formatCount(column.distinct)}</td>
                  <td className="max-w-[120px] truncate py-1 pl-2 text-text-muted">
                    {column.samples.join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}

function titleOf(finding: Finding): string {
  const details = finding.details;
  switch (finding.kind) {
    case "data_not_on_first_sheet":
      return `The data is on “${String(details.largest)}”, not the first sheet`;
    case "header_not_on_first_row":
      return `Header is on row ${String(details.header_row)}`;
    case "subtotal_rows":
      return "Total rows inside the data";
    case "exact_duplicates":
      return "Rows that copy an earlier row";
    case "number_formats":
      return "Numbers stored as text";
    case "date_formats":
      return "Dates stored as text";
    case "inconsistent_labels":
      return "One label spelled several ways";
    case "contradicting_columns":
      return "Columns that contradict each other";
    case "dominating_value":
      return "One value dominates the column";
    case "missing_values":
      return "Missing values";
    default:
      return finding.kind.replaceAll("_", " ");
  }
}

function FindingCard({ finding }: { finding: Finding }) {
  const Icon = ICONS[finding.kind] ?? TriangleAlert;

  return (
    <div className="grid grid-cols-[16px_minmax(0,1fr)] gap-3 rounded-lg border border-border p-3">
      <Icon className="mt-0.5 size-4 text-warning" />
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-baseline gap-2">
          <span className="flex-1 text-sm font-semibold">{titleOf(finding)}</span>
          <span className="font-mono text-xs text-text-muted">{finding.where}</span>
        </div>
        <p className="text-sm text-pretty text-text-muted">{finding.message}</p>
        <FindingValues finding={finding} />
        <FindingRows finding={finding} />
      </div>
    </div>
  );
}

// Rows numbered as in the file (api.md), at most ten beside a count.
function FindingRows({ finding }: { finding: Finding }) {
  if (finding.rows.length === 0) {
    return null;
  }

  let label = `rows ${finding.rows.join(", ")}`;
  if (finding.rows.length === 1) {
    label = `row ${String(finding.rows[0])}`;
  }
  if (finding.count !== null && finding.count > finding.rows.length) {
    label = `${label} — ${formatCount(finding.count)} in all`;
  }

  return <div className="text-xs font-medium text-accent">{label}</div>;
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-sm bg-surface px-1 py-0.5 font-mono text-xs whitespace-nowrap text-text">
      {children}
    </span>
  );
}

function counted(value: unknown): [string, number][] {
  if (!isRecord(value)) {
    return [];
  }
  const pairs: [string, number][] = [];
  for (const [key, amount] of Object.entries(value)) {
    if (typeof amount === "number") {
      pairs.push([key, amount]);
    }
  }
  return pairs;
}

function Counts({ pairs, quote }: { pairs: [string, number][]; quote: boolean }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
      {pairs.map(([label, amount]) => (
        <span key={label} className="flex items-center gap-2 whitespace-nowrap">
          <Chip>{quote ? `"${label}"` : label}</Chip>
          {plural(amount, "row", "rows")}
        </span>
      ))}
    </div>
  );
}

// Suspicious values are shown both ways, never resolved (design.md §3.6).
function BothWays({ value, first, second }: { value: string; first: string; second: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
      <Chip>"{value}"</Chip>→<span className="text-text">{first}</span>or
      <span className="text-text">{second}</span>
    </div>
  );
}

function FindingValues({ finding }: { finding: Finding }) {
  const details = finding.details;
  const ambiguous = Array.isArray(details.ambiguous) ? details.ambiguous : [];

  switch (finding.kind) {
    case "number_formats":
      return (
        <>
          <Counts pairs={counted(details.formats)} quote={false} />
          {ambiguous.filter(isRecord).map((item, index) => {
            const readings = Object.values(isRecord(item.readings) ? item.readings : {});
            return (
              <BothWays
                key={index}
                value={String(item.value)}
                first={String(readings[0])}
                second={String(readings[1])}
              />
            );
          })}
        </>
      );
    case "date_formats":
      return (
        <>
          <Counts pairs={counted(details.formats)} quote={false} />
          {ambiguous.filter(isRecord).map((item, index) => (
            <BothWays
              key={index}
              value={String(item.value)}
              first={String(item.as_dd_mm)}
              second={String(item.as_mm_dd)}
            />
          ))}
        </>
      );
    case "inconsistent_labels": {
      const variants = Array.isArray(details.variants) ? details.variants : [];
      return (
        <>
          {variants.map((variant, index) => (
            <Counts key={index} pairs={counted(variant)} quote />
          ))}
        </>
      );
    }
    case "missing_values":
      return <Counts pairs={counted(details.placeholders)} quote />;
    case "contradicting_columns": {
      const columns = Array.isArray(details.columns) ? details.columns.map(String) : [];
      if (columns.length !== 3) {
        return null;
      }
      return (
        <div className="text-xs text-text-muted">
          <Chip>{columns[0]}</Chip> ≠ <Chip>{columns[1]}</Chip> × <Chip>{columns[2]}</Chip>
        </div>
      );
    }
    default:
      return null;
  }
}
