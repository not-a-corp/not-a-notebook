import { Dialog } from "radix-ui";
import { useState, type ReactNode, type SubmitEvent } from "react";

import {
  createModel,
  updateModel,
  type Adapter,
  type Dialect,
  type KeyChange,
  type Model,
} from "@/api/models";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { sentenceForError } from "@/lib/words";

import {
  checkModel,
  fieldsOf,
  hasModelErrors,
  type ModelDraft,
  type ModelErrors,
} from "./model-form";

// design.md §2.6.1 — Add model, and Edit: one dialog.

const ADAPTERS: { value: Adapter; label: string; covers: string }[] = [
  { value: "anthropic", label: "Anthropic", covers: "Claude, through the Messages API." },
  {
    value: "openai_responses",
    label: "OpenAI (Responses)",
    covers: "OpenAI's models, through the Responses API.",
  },
  {
    value: "openai_compatible",
    label: "OpenAI-compatible",
    covers: "Ollama, vLLM, LM Studio, OpenRouter, DeepSeek, Qwen…",
  },
];

const DIALECTS: { value: Dialect; label: string; covers: string }[] = [
  { value: "tools", label: "Tool calling", covers: "For models that do it well." },
  { value: "text", label: "Code blocks", covers: "For small and local models." },
];

function draftOf(model: Model | null): ModelDraft {
  if (model === null) {
    return { name: "", adapter: "anthropic", baseUrl: "", model: "", dialect: "tools", key: "" };
  }
  return {
    name: model.name,
    adapter: model.adapter,
    baseUrl: model.baseUrl ?? "",
    model: model.model,
    dialect: model.dialect,
    key: "",
  };
}

interface ModelDialogProps {
  // The model being edited, or null to add one.
  model: Model | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (model: Model) => void;
}

export function ModelDialog({ model, open, onOpenChange, onSaved }: ModelDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-scrim" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-48px)] w-[560px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-y-auto rounded-xl border border-border bg-surface-raised p-6 shadow-overlay"
        >
          {/* Keyed, so opening it again starts from the model as it is now. */}
          {open && (
            <ModelForm
              key={model?.id ?? "new"}
              model={model}
              onCancel={() => {
                onOpenChange(false);
              }}
              onSaved={onSaved}
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ModelForm({
  model,
  onCancel,
  onSaved,
}: {
  model: Model | null;
  onCancel: () => void;
  onSaved: (model: Model) => void;
}) {
  const [draft, setDraft] = useState<ModelDraft>(() => draftOf(model));
  const [removeKey, setRemoveKey] = useState(false);
  const [errors, setErrors] = useState<ModelErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const editing = model !== null;

  function change(changes: Partial<ModelDraft>) {
    setDraft(Object.assign(structuredClone(draft), changes));
  }

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = checkModel(draft);
    setErrors(found);
    if (hasModelErrors(found)) {
      return;
    }

    setSaving(true);
    setFailure(null);
    try {
      const fields = fieldsOf(draft);
      const key = draft.key.trim();
      let saved: Model;
      if (model === null) {
        let sentKey: string | null = null;
        if (key !== "") {
          sentKey = key;
        }
        saved = await createModel(fields, sentKey);
      } else {
        let keyChange: KeyChange = { kind: "keep" };
        if (removeKey) {
          keyChange = { kind: "remove" };
        }
        if (key !== "") {
          keyChange = { kind: "replace", key };
        }
        saved = await updateModel(model.id, fields, keyChange);
      }
      onSaved(saved);
    } catch (error) {
      setFailure(sentenceForError(error));
      setSaving(false);
    }
  }

  let title = "Add model";
  let action = "Add model";
  if (editing) {
    title = `Edit ${model.name}`;
    action = "Save";
  }

  let keyHelp = "Encrypted before it is stored, and never shown again.";
  if (editing && model.keyHint !== null) {
    keyHelp = `Leave empty to keep the current key (${model.keyHint}).`;
  }
  if (removeKey) {
    keyHelp = "The key will be removed when you save.";
  }

  return (
    <form className="flex flex-col gap-5" noValidate onSubmit={(event) => void submit(event)}>
      <Dialog.Title className="text-md font-semibold">{title}</Dialog.Title>
      {failure !== null && (
        <p role="alert" className="text-sm text-danger">
          {failure}
        </p>
      )}

      <Field label="Name" error={errors.name}>
        <Input
          autoFocus
          value={draft.name}
          placeholder="Local Qwen"
          aria-invalid={errors.name !== undefined}
          onChange={(event) => {
            change({ name: event.target.value });
          }}
        />
      </Field>

      <Choice
        label="Adapter"
        options={ADAPTERS}
        value={draft.adapter}
        columns={3}
        onChange={(adapter) => {
          change({ adapter });
        }}
      />

      <Field
        label="Base URL"
        hint={
          draft.adapter === "openai_compatible"
            ? "Required."
            : "Optional — the provider's own by default."
        }
        error={errors.baseUrl}
      >
        <Input
          value={draft.baseUrl}
          placeholder="http://host.docker.internal:11434/v1"
          className="font-mono text-sm"
          aria-invalid={errors.baseUrl !== undefined}
          onChange={(event) => {
            change({ baseUrl: event.target.value });
          }}
        />
      </Field>

      <Field label="Model" error={errors.model}>
        <Input
          value={draft.model}
          placeholder="qwen3:14b"
          className="font-mono text-sm"
          aria-invalid={errors.model !== undefined}
          onChange={(event) => {
            change({ model: event.target.value });
          }}
        />
      </Field>

      <Choice
        label="Dialect"
        options={DIALECTS}
        value={draft.dialect}
        columns={2}
        onChange={(dialect) => {
          change({ dialect });
        }}
      />

      <Field label="Key" hint={keyHelp} error={undefined}>
        <Input
          type="password"
          autoComplete="off"
          value={draft.key}
          disabled={removeKey}
          onChange={(event) => {
            change({ key: event.target.value });
          }}
        />
      </Field>
      {editing && model.keyHint !== null && (
        <button
          type="button"
          className="-mt-3 self-start text-xs font-medium text-accent"
          onClick={() => {
            setRemoveKey(!removeKey);
            change({ key: "" });
          }}
        >
          {removeKey ? "Keep the key" : "Remove key"}
        </button>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving}>
          {action}
        </Button>
      </div>
    </form>
  );
}

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error: string | undefined;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {error !== undefined && <span className="text-xs text-danger">{error}</span>}
      {error === undefined && hint !== undefined && (
        <span className="text-xs text-text-muted">{hint}</span>
      )}
    </label>
  );
}

function Choice<T extends string>({
  label,
  options,
  value,
  columns,
  onChange,
}: {
  label: string;
  options: { value: T; label: string; covers: string }[];
  value: T;
  columns: 2 | 3;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-sm font-medium">{label}</span>
      <div
        role="radiogroup"
        aria-label={label}
        className={cn("grid gap-2", columns === 3 && "grid-cols-3", columns === 2 && "grid-cols-2")}
      >
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={selected}
              className={cn(
                "flex flex-col gap-1 rounded-lg border p-3 text-left",
                selected && "border-accent bg-accent-soft",
                !selected && "border-border hover:bg-text/8",
              )}
              onClick={() => {
                onChange(option.value);
              }}
            >
              <span className="text-sm font-medium">{option.label}</span>
              <span className="text-xs text-pretty text-text-muted">{option.covers}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
