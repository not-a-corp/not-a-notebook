import { request, requestJson } from "./client";
import { decodeCell, type Cell } from "./conversation-detail";
import { asRecord, string } from "./decode";

// api.md, Cells — and the two conversation-wide actions on them.

function runIdOf(body: unknown): string {
  return string(asRecord(body, "run accepted"), "run_id");
}

// `after` is where the cell goes: after that cell, or first when null.
export async function createCell(
  conversationId: string,
  source: string,
  after: string | null,
): Promise<Cell> {
  const created = await requestJson(`/conversations/${conversationId}/cells`, {
    method: "POST",
    json: { source, after_cell_id: after },
  });
  return decodeCell(created);
}

export async function updateCell(cellId: string, source: string): Promise<Cell> {
  return decodeCell(await requestJson(`/cells/${cellId}`, { method: "PATCH", json: { source } }));
}

export async function runCell(cellId: string): Promise<string> {
  return runIdOf(await requestJson(`/cells/${cellId}/run`, { method: "POST" }));
}

export async function deleteCell(cellId: string): Promise<void> {
  await request(`/cells/${cellId}`, { method: "DELETE" });
}

export async function runAll(conversationId: string): Promise<string> {
  return runIdOf(await requestJson(`/conversations/${conversationId}/run-all`, { method: "POST" }));
}

export async function restartKernel(conversationId: string): Promise<void> {
  await request(`/conversations/${conversationId}/kernel/restart`, { method: "POST" });
}
