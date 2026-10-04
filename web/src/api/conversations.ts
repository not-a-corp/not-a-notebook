import { request, requestJson } from "./client";
import { array, asRecord, nullableString, number, oneOf, record, string } from "./decode";

// api.md, Conversations.

export type KernelState = "running" | "stopped";

export interface ConversationSummary {
  id: string;
  title: string;
  modelId: string | null;
  kernel: KernelState;
  // The run in progress, if any: the sidebar marks a busy conversation.
  activeRunId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Page<T> {
  data: T[];
  page: number;
  pages: number;
  total: number;
}

export function decodeConversationSummary(value: unknown): ConversationSummary {
  const json = asRecord(value, "conversation");

  return {
    id: string(json, "id"),
    title: string(json, "title"),
    modelId: nullableString(json, "model_id"),
    kernel: oneOf(json, "kernel", ["running", "stopped"]),
    activeRunId: nullableString(json, "active_run_id"),
    createdAt: string(json, "created_at"),
    updatedAt: string(json, "updated_at"),
  };
}

function decodePage(value: unknown): Page<ConversationSummary> {
  const json = asRecord(value, "conversations");
  const meta = record(json, "meta");

  return {
    data: array(json, "data", decodeConversationSummary),
    page: number(meta, "page"),
    pages: number(meta, "pages"),
    total: number(meta, "total"),
  };
}

export const CONVERSATIONS_PER_PAGE = 50;

export async function listConversations(
  page: number,
  search: string,
): Promise<Page<ConversationSummary>> {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("per_page", String(CONVERSATIONS_PER_PAGE));
  if (search !== "") {
    params.set("q", search);
  }

  return decodePage(await requestJson(`/conversations?${params.toString()}`));
}

export interface ConversationChanges {
  title?: string;
  modelId?: string | null;
}

export async function updateConversation(
  id: string,
  changes: ConversationChanges,
): Promise<ConversationSummary> {
  // Only the fields sent change (api.md), so only the ones given are sent.
  const body: Record<string, unknown> = {};
  if (changes.title !== undefined) {
    body.title = changes.title;
  }
  if (changes.modelId !== undefined) {
    body.model_id = changes.modelId;
  }

  const updated = await requestJson(`/conversations/${id}`, { method: "PATCH", json: body });
  return decodeConversationSummary(updated);
}

export async function deleteConversation(id: string): Promise<void> {
  await request(`/conversations/${id}`, { method: "DELETE" });
}
