import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Ellipsis,
  FlaskConical,
  Info,
  LoaderCircle,
  Lock,
  Pencil,
  Plus,
  Trash,
  X,
} from "lucide-react";
import { Fragment, useState } from "react";

import { deleteModel, listModels, testModel, type Model, type ModelTestResult } from "@/api/models";
import { toast } from "@/components/toaster";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip } from "@/components/ui/tooltip";
import { formatDuration } from "@/lib/format";
import { sentenceForError } from "@/lib/words";

import { SectionTitle } from "../settings-ui";
import { ModelDialog } from "./model-dialog";
import { endpointOf } from "./model-form";

const ADAPTER_NAMES = {
  anthropic: "Anthropic",
  openai_responses: "OpenAI (Responses)",
  openai_compatible: "OpenAI-compatible",
} as const;

const DIALECT_NAMES = { tools: "Tool calling", text: "Code blocks" } as const;

type TestState = { kind: "running" } | { kind: "done"; result: ModelTestResult };

// design.md §2.6.1 — the models this instance offers, and the ones you added.
export function ModelsSettings() {
  const queryClient = useQueryClient();
  const models = useQuery({ queryKey: ["models"], queryFn: listModels });
  const [editing, setEditing] = useState<Model | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<Model | null>(null);
  const [tests, setTests] = useState<Record<string, TestState>>({});

  function setTest(modelId: string, state: TestState) {
    setTests((current) => {
      const next = structuredClone(current);
      next[modelId] = state;
      return next;
    });
  }

  async function runTest(model: Model) {
    setTest(model.id, { kind: "running" });
    try {
      const result = await testModel(model.id);
      setTest(model.id, { kind: "done", result });
    } catch (error) {
      toast(sentenceForError(error));
      setTests((current) => {
        const kept = Object.entries(current).filter(([id]) => id !== model.id);
        return Object.fromEntries(kept);
      });
    }
  }

  async function remove(model: Model) {
    try {
      await deleteModel(model.id);
      await queryClient.invalidateQueries({ queryKey: ["models"] });
      // Conversations that used it lose their model (api.md).
      await queryClient.invalidateQueries({ queryKey: ["conversation"] });
    } catch (error) {
      toast(sentenceForError(error));
    }
  }

  return (
    <>
      <SectionTitle
        title="Models"
        description="The models this instance offers and the ones you added. Each conversation picks one in its header."
        action={
          <Button
            className="flex-none"
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="size-4" strokeWidth={2} />
            Add model
          </Button>
        }
      />

      <div className="rounded-lg border border-border">
        <table className="w-full border-collapse text-sm tabular-nums">
          <thead>
            <tr className="bg-surface text-text-muted">
              <th className="rounded-tl-lg border-b border-border py-2 pr-3 pl-4 text-left font-medium">
                Name
              </th>
              <th className="border-b border-border px-3 py-2 text-left font-medium">Adapter</th>
              <th className="border-b border-border px-3 py-2 text-left font-medium">
                Model · key
              </th>
              <th className="border-b border-border px-3 py-2 text-left font-medium">Dialect</th>
              <th className="rounded-tr-lg border-b border-border py-2 pr-4 pl-3" />
            </tr>
          </thead>
          <tbody>
            {(models.data ?? []).map((model, index) => (
              <Fragment key={model.id}>
                <ModelRow
                  model={model}
                  first={index === 0}
                  test={tests[model.id] ?? null}
                  onTest={() => void runTest(model)}
                  onEdit={() => {
                    setEditing(model);
                    setDialogOpen(true);
                  }}
                  onDelete={() => {
                    setDeleting(model);
                  }}
                />
                {tests[model.id] !== undefined && <TestRow test={tests[model.id] ?? null} />}
              </Fragment>
            ))}
            {models.data?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text-muted">
                  No models yet. Add one to start asking questions.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="flex items-start gap-2 text-sm text-text-muted">
        <Info className="mt-0.5 size-4 flex-none" />
        <span className="text-pretty">
          A test sends one short question and checks that the model answers in its dialect. If a
          model keeps answering without calling the tool, switch it to{" "}
          <span className="font-medium text-text">Code blocks</span>.
        </span>
      </p>

      <ModelDialog
        model={editing}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSaved={(saved) => {
          setDialogOpen(false);
          // A changed model is untested again.
          setTests((current) => {
            const kept = Object.entries(current).filter(([id]) => id !== saved.id);
            return Object.fromEntries(kept);
          });
          void queryClient.invalidateQueries({ queryKey: ["models"] });
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        title={`Delete ${deleting?.name ?? "this model"}?`}
        description="Conversations that used it keep their history and lose their model until another is picked."
        confirmLabel="Delete"
        onConfirm={() => {
          if (deleting !== null) {
            void remove(deleting);
          }
          setDeleting(null);
        }}
      />
    </>
  );
}

function ModelRow({
  model,
  first,
  test,
  onTest,
  onEdit,
  onDelete,
}: {
  model: Model;
  first: boolean;
  test: TestState | null;
  onTest: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const instance = model.source === "environment";
  const pad = test === null ? "py-3" : "pt-3 pb-2";

  return (
    <tr className={first ? undefined : "border-t border-border"}>
      <td className={`${pad} pr-3 pl-4 align-top`}>
        <div className="font-medium">{model.name}</div>
        {instance && (
          <span className="inline-flex h-5 items-center rounded-sm border border-border px-1 text-xs font-medium text-text-muted">
            instance
          </span>
        )}
        {!instance && <div className="text-xs text-text-muted">yours</div>}
      </td>
      <td className={`${pad} px-3 align-top`}>
        <div className="whitespace-nowrap">{ADAPTER_NAMES[model.adapter]}</div>
        <div className="font-mono text-xs whitespace-nowrap text-text-muted">
          {endpointOf(model.adapter, model.baseUrl)}
        </div>
      </td>
      <td className={`${pad} px-3 align-top`}>
        <div className="font-mono text-sm break-all">{model.model}</div>
        {model.keyHint !== null && (
          <div className="font-mono text-xs text-text-muted">{model.keyHint}</div>
        )}
        {model.keyHint === null && <div className="text-xs text-text-muted italic">no key</div>}
      </td>
      <td className={`${pad} px-3 align-top whitespace-nowrap`}>{DIALECT_NAMES[model.dialect]}</td>
      <td className={`${pad} pr-4 pl-3 align-top`}>
        <div className="flex items-center justify-end gap-1">
          <Button
            variant="secondary"
            size="compact"
            disabled={test?.kind === "running"}
            onClick={onTest}
          >
            <FlaskConical className="size-3.5" />
            Test
          </Button>
          {instance && (
            <Tooltip label="Set in the server's environment">
              <span
                tabIndex={0}
                className="flex size-7 items-center justify-center text-text-muted"
              >
                <Lock className="size-4" />
              </span>
            </Tooltip>
          )}
          {!instance && (
            <DropdownMenu>
              <Tooltip label="Edit or delete">
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-compact"
                    aria-label={`Edit or delete ${model.name}`}
                  >
                    <Ellipsis className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
              </Tooltip>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={onEdit}>
                  <Pencil />
                  Edit
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-danger" onSelect={onDelete}>
                  <Trash />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </td>
    </tr>
  );
}

// A test's result on its own line under the row, so a failure is never cramped.
function TestRow({ test }: { test: TestState | null }) {
  let content = (
    <span className="flex items-center gap-2 text-text-muted">
      <LoaderCircle className="size-4 animate-spin text-accent" />
      Testing…
    </span>
  );
  if (test?.kind === "done" && test.result.ok) {
    content = (
      <span className="flex items-center gap-2 font-medium text-success">
        <Check className="size-4" strokeWidth={2.25} />
        {formatDuration(test.result.latencyMs)}
      </span>
    );
  }
  if (test?.kind === "done" && !test.result.ok) {
    content = (
      <span className="flex items-center gap-2 text-danger">
        <X className="size-4" strokeWidth={2.25} />
        <span className="font-medium">{test.result.error ?? "the test failed"}</span>
        <span className="text-text-muted">· {formatDuration(test.result.latencyMs)}</span>
      </span>
    );
  }

  return (
    <tr>
      <td colSpan={5} className="px-4 pb-3" role="status">
        {content}
      </td>
    </tr>
  );
}
