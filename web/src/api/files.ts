import { request, requestJson } from "./client";
import { decodeFile, type FileInfo } from "./conversation-detail";
import { asRecord, string } from "./decode";

// api.md, Files.

export const ACCEPTED_EXTENSIONS = [".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".parquet"];

export function isAcceptedFile(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

export interface UploadAccepted {
  file: FileInfo;
  runId: string;
}

export async function uploadFile(conversationId: string, file: File): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file, file.name);

  const body = await requestJson(`/conversations/${conversationId}/files`, {
    method: "POST",
    form,
  });
  const json = asRecord(body, "upload accepted");

  return { file: decodeFile(json.file), runId: string(json, "run_id") };
}

export async function deleteFile(conversationId: string, fileId: string): Promise<void> {
  await request(`/conversations/${conversationId}/files/${fileId}`, { method: "DELETE" });
}
