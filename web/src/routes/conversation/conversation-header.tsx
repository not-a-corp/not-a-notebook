import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ChevronDown, Ellipsis, Pencil, Trash } from "lucide-react";
import { useState } from "react";

import {
  deleteConversation,
  updateConversation,
  type Conversation,
  type ConversationChanges,
} from "@/api/conversations";
import { listModels } from "@/api/models";
import { KernelIndicator, type KernelStatus } from "@/components/kernel-indicator";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip } from "@/components/ui/tooltip";

function kernelStatus(conversation: Conversation): KernelStatus {
  if (conversation.activeRunId !== null) {
    return "busy";
  }
  if (conversation.kernel === "running") {
    return "ready";
  }
  return "stopped";
}

// design.md §2.1 — the conversation's header, 48 px.
export function ConversationHeader({ conversation }: { conversation: Conversation }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const update = useMutation({
    mutationFn: (changes: ConversationChanges) => updateConversation(conversation.id, changes),
    onSuccess: (updated) => {
      queryClient.setQueryData<Conversation>(["conversation", conversation.id], (current) => {
        if (current === undefined) {
          return current;
        }
        return {
          id: current.id,
          title: updated.title,
          modelId: updated.modelId,
          kernel: current.kernel,
          activeRunId: current.activeRunId,
        };
      });
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteConversation(conversation.id),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ["conversation", conversation.id] });
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      await navigate({ to: "/" });
    },
  });

  return (
    <header className="flex h-12 flex-none items-center gap-2 border-b border-border pr-3 pl-6">
      <Title
        title={conversation.title}
        onRename={(title) => {
          update.mutate({ title });
        }}
      />
      <div className="flex-1" />
      <ModelPicker
        modelId={conversation.modelId}
        onPick={(modelId) => {
          update.mutate({ modelId });
        }}
      />
      <KernelIndicator status={kernelStatus(conversation)} />
      <DropdownMenu>
        <Tooltip label="More">
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="More">
              <Ellipsis className="size-5" />
            </Button>
          </DropdownMenuTrigger>
        </Tooltip>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            className="text-danger"
            onSelect={() => {
              setConfirmDelete(true);
            }}
          >
            <Trash />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this conversation?"
        description="Its messages, cells and files go with it. There is no trash."
        confirmLabel="Delete"
        onConfirm={() => {
          remove.mutate();
        }}
      />
    </header>
  );
}

function Title({ title, onRename }: { title: string; onRename: (title: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);

  function finish() {
    setEditing(false);
    const next = draft.trim();
    if (next !== "" && next !== title) {
      onRename(next);
    }
  }

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        aria-label="Conversation title"
        maxLength={200}
        className="h-8 w-[360px] rounded-md border border-accent bg-bg px-2 text-base font-semibold outline-none"
        onChange={(event) => {
          setDraft(event.target.value);
        }}
        onBlur={finish}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            finish();
          }
          if (event.key === "Escape") {
            setDraft(title);
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <button
      type="button"
      className="group flex min-w-0 items-center gap-2 rounded-md text-left"
      onClick={() => {
        setDraft(title);
        setEditing(true);
      }}
    >
      <span className="truncate font-semibold">{title}</span>
      <Pencil aria-hidden="true" className="size-3.5 flex-none text-text-muted" />
      <span className="sr-only">Rename</span>
    </button>
  );
}

const NO_MODEL = "none";

function ModelPicker({
  modelId,
  onPick,
}: {
  modelId: string | null;
  onPick: (modelId: string | null) => void;
}) {
  const models = useQuery({ queryKey: ["models"], queryFn: listModels });
  const all = models.data ?? [];
  const current = all.find((model) => model.id === modelId);

  let label = "Pick a model";
  if (current !== undefined) {
    label = current.name;
  }

  return (
    <DropdownMenu>
      <Tooltip label="Model for this conversation">
        <DropdownMenuTrigger asChild>
          <Button variant="secondary" className="pr-2 pl-3">
            {label}
            <ChevronDown className="size-4 text-text-muted" />
          </Button>
        </DropdownMenuTrigger>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Model</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={modelId ?? NO_MODEL}
          onValueChange={(value) => {
            if (value === NO_MODEL) {
              onPick(null);
              return;
            }
            onPick(value);
          }}
        >
          {all.map((model) => (
            <DropdownMenuRadioItem key={model.id} value={model.id}>
              {model.name}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        {all.length === 0 && (
          <p className="px-2 py-1 text-sm text-text-muted">No models yet. Add one in Settings.</p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
