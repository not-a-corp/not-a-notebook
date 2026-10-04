import { asRecord, isRecord, string } from "./decode";

// Every failure from the API comes in the same envelope (api.md, Errors). `code`
// is the contract; `message` is for humans and nothing branches on it.
export class ApiError extends Error {
  override name = "ApiError";
  readonly code: string;
  readonly status: number;
  readonly requestId: string | null;

  constructor(code: string, message: string, status: number, requestId: string | null) {
    super(message);
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

export async function readApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // A proxy's HTML error page, or nothing at all: still an error, without a code.
  }

  if (!isRecord(body) || !isRecord(body.error)) {
    return new ApiError("INTERNAL_ERROR", response.statusText, response.status, null);
  }

  const error = asRecord(body.error, "error");
  let requestId: string | null = null;
  if (typeof error.request_id === "string") {
    requestId = error.request_id;
  }

  return new ApiError(string(error, "code"), string(error, "message"), response.status, requestId);
}
