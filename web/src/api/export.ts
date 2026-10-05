import { request } from "./client";

// api.md, GET /conversations/{id}/export.

export type ExportFormat = "ipynb" | "py";

const REVOKE_AFTER_MS = 60_000;

// Chrome drops a download name with letters outside ASCII and saves the file as
// "download"; accents are taken off instead ("região" → "regiao"), and anything
// else outside ASCII becomes "_".
export function asciiName(name: string): string {
  const bare = name.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  return bare.replace(/[^\x20-\x7e]/g, "_");
}

// The file's name as the API sent it — filename*, then the plain filename — in
// a form every browser keeps.
export function filenameFrom(disposition: string | null, fallback: string): string {
  return asciiName(sentName(disposition, fallback));
}

function sentName(disposition: string | null, fallback: string): string {
  if (disposition === null) {
    return fallback;
  }

  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (encoded?.[1] !== undefined) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      // A malformed name: the plain one below will do.
    }
  }

  const plain = /filename="([^"]+)"/i.exec(disposition);
  if (plain?.[1] !== undefined) {
    return plain[1];
  }
  return fallback;
}

// A download needs the access token, which a plain link cannot carry: the file
// is fetched, then handed to the browser through a short-lived object URL.
export async function downloadExport(conversationId: string, format: ExportFormat): Promise<void> {
  const response = await request(`/conversations/${conversationId}/export?format=${format}`);
  const name = filenameFrom(response.headers.get("Content-Disposition"), `conversation.${format}`);
  const url = URL.createObjectURL(await response.blob());

  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  // Not at once: revoked before the browser has started the download, the
  // file loses its name (Chrome saves it as "download"), or is lost.
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, REVOKE_AFTER_MS);
}
