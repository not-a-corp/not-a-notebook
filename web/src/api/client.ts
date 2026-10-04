import { readApiError } from "./errors";
import { accessToken, refreshSession } from "./session";

const BASE = "/api/v1";

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions {
  method?: Method;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function buildInit(options: RequestOptions, token: string | null): RequestInit {
  const headers = new Headers(options.headers);
  if (token !== null) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const init: RequestInit = {
    method: options.method ?? "GET",
    headers,
    credentials: "same-origin",
  };

  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(options.json);
  }

  if (options.form !== undefined) {
    init.body = options.form;
  }

  if (options.signal !== undefined) {
    init.signal = options.signal;
  }

  return init;
}

// One request, with the access token. An expired token is refreshed once and
// the request sent again; a refresh that fails signs the person out, and the
// original 401 is what the caller gets. Anything not ok becomes an ApiError.
export async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  let response = await fetch(`${BASE}${path}`, buildInit(options, accessToken()));

  if (response.status === 401) {
    const refreshed = await refreshSession();
    if (refreshed) {
      response = await fetch(`${BASE}${path}`, buildInit(options, accessToken()));
    }
  }

  if (!response.ok) {
    throw await readApiError(response);
  }

  return response;
}

export async function requestJson(path: string, options: RequestOptions = {}): Promise<unknown> {
  const response = await request(path, options);
  const body: unknown = await response.json();
  return body;
}

// For the auth endpoints, which run without a session and must never trigger a
// refresh: a 401 there is the answer (wrong password), not an expired token.
export async function requestAnonymous(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const response = await fetch(`${BASE}${path}`, buildInit(options, null));
  if (!response.ok) {
    throw await readApiError(response);
  }

  return response;
}
