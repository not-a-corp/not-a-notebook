import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { createCell, deleteCell, restartKernel, runAll, runCell, updateCell } from "@/api/cells";
import type { Cell, ConversationDetail } from "@/api/conversation-detail";
import { toast } from "@/components/toaster";
import { sentenceForError } from "@/lib/words";

import { conversationKey } from "../live/use-live-run";

async function changeDetail(
  queryClient: QueryClient,
  conversationId: string,
  change: (detail: ConversationDetail) => ConversationDetail,
): Promise<void> {
  const key = conversationKey(conversationId);
  // A read already in flight predates this change and would undo it on landing.
  await queryClient.cancelQueries({ queryKey: key });
  queryClient.setQueryData<ConversationDetail>(key, (current) => {
    if (current === undefined) {
      return current;
    }
    return change(current);
  });
}

function withRun(detail: ConversationDetail, runId: string): ConversationDetail {
  return {
    id: detail.id,
    title: detail.title,
    modelId: detail.modelId,
    kernel: detail.kernel,
    activeRunId: runId,
    files: detail.files,
    messages: detail.messages,
    cells: detail.cells,
  };
}

function withCells(detail: ConversationDetail, cells: Cell[]): ConversationDetail {
  return {
    id: detail.id,
    title: detail.title,
    modelId: detail.modelId,
    kernel: detail.kernel,
    activeRunId: detail.activeRunId,
    files: detail.files,
    messages: detail.messages,
    cells,
  };
}

export interface NotebookActions {
  // Saves the source when it changed — editing marks the cells below stale,
  // which a fresh read of the conversation brings in.
  // Both say whether they succeeded: a failure keeps the draft being edited.
  save: (cell: Cell, source: string) => Promise<boolean>;
  run: (cell: Cell, source: string) => Promise<boolean>;
  // `after` is the cell to insert after, or null for first.
  add: (after: string | null) => Promise<Cell | null>;
  remove: (cell: Cell) => Promise<void>;
  runAll: () => Promise<void>;
  restart: () => Promise<void>;
}

export function useNotebookActions(conversationId: string): NotebookActions {
  const queryClient = useQueryClient();

  return useMemo(() => {
    const key = conversationKey(conversationId);

    async function save(cell: Cell, source: string) {
      if (source === cell.source) {
        return true;
      }
      try {
        const saved = await updateCell(cell.id, source);
        await changeDetail(queryClient, conversationId, (detail) =>
          withCells(
            detail,
            detail.cells.map((known) => {
              if (known.id !== saved.id) {
                return known;
              }
              return saved;
            }),
          ),
        );
        await queryClient.invalidateQueries({ queryKey: key });
        return true;
      } catch (error) {
        toast(sentenceForError(error));
        return false;
      }
    }

    async function run(cell: Cell, source: string) {
      try {
        if (source !== cell.source) {
          await updateCell(cell.id, source);
        }
        const runId = await runCell(cell.id);
        await changeDetail(queryClient, conversationId, (detail) => withRun(detail, runId));
        return true;
      } catch (error) {
        toast(sentenceForError(error));
        return false;
      }
    }

    async function add(after: string | null) {
      try {
        const created = await createCell(conversationId, "", after);
        await changeDetail(queryClient, conversationId, (detail) => {
          const cells = detail.cells.slice();
          let index = 0;
          if (after !== null) {
            index = cells.findIndex((cell) => cell.id === after) + 1;
          }
          cells.splice(index, 0, created);
          return withCells(detail, cells);
        });
        return created;
      } catch (error) {
        toast(sentenceForError(error));
        return null;
      }
    }

    async function remove(cell: Cell) {
      try {
        await deleteCell(cell.id);
        await changeDetail(queryClient, conversationId, (detail) =>
          withCells(
            detail,
            detail.cells.filter((known) => known.id !== cell.id),
          ),
        );
        // The cells below that ran are stale now; the server says which.
        await queryClient.invalidateQueries({ queryKey: key });
      } catch (error) {
        toast(sentenceForError(error));
      }
    }

    async function runEverything() {
      try {
        const runId = await runAll(conversationId);
        await changeDetail(queryClient, conversationId, (detail) => withRun(detail, runId));
      } catch (error) {
        toast(sentenceForError(error));
      }
    }

    async function restart() {
      try {
        await restartKernel(conversationId);
        await queryClient.invalidateQueries({ queryKey: key });
        await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      } catch (error) {
        toast(sentenceForError(error));
      }
    }

    return { save, run, add, remove, runAll: runEverything, restart };
  }, [conversationId, queryClient]);
}
