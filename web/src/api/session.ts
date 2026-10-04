import { asRecord, string } from "./decode";

// The access token lives in memory only — never in storage a script could read
// later (PLAN decision 7). The refresh cookie is the session; the browser holds
// it and this code never sees it.

export type Session =
  { status: "unknown" } | { status: "signed-out" } | { status: "signed-in"; accessToken: string };

let session: Session = { status: "unknown" };
const listeners = new Set<() => void>();

export function getSession(): Session {
  return session;
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);

  return () => {
    listeners.delete(listener);
  };
}

function setSession(next: Session): void {
  session = next;
  for (const listener of listeners) {
    listener();
  }
}

export function signedIn(accessToken: string): void {
  setSession({ status: "signed-in", accessToken });
}

export function signedOut(): void {
  setSession({ status: "signed-out" });
}

export function accessToken(): string | null {
  if (session.status !== "signed-in") {
    return null;
  }

  return session.accessToken;
}

export interface Tokens {
  accessToken: string;
  expiresAt: string;
}

export function decodeTokens(value: unknown): Tokens {
  const json = asRecord(value, "tokens");

  return {
    accessToken: string(json, "access_token"),
    expiresAt: string(json, "expires_at"),
  };
}

async function postRefresh(): Promise<Response> {
  return fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin" });
}

// POST /auth/refresh rotates the cookie: two refreshes with the same cookie do
// not both succeed (api.md). So there is only ever one in flight, shared by
// every caller — and when another tab won the race, the browser already holds
// the winner's cookie, so one retry is enough.
let refreshing: Promise<boolean> | null = null;

async function refreshOnce(): Promise<boolean> {
  let response = await postRefresh();
  if (response.status === 401) {
    response = await postRefresh();
  }

  if (!response.ok) {
    signedOut();
    return false;
  }

  const tokens = decodeTokens(await response.json());
  signedIn(tokens.accessToken);
  return true;
}

export function refreshSession(): Promise<boolean> {
  refreshing ??= refreshOnce().finally(() => {
    refreshing = null;
  });

  return refreshing;
}

// On load, the cookie decides whether the person is signed in (design.md §10).
let started: Promise<boolean> | null = null;

export function ensureSession(): Promise<boolean> {
  if (session.status !== "unknown") {
    return Promise.resolve(session.status === "signed-in");
  }

  started ??= refreshSession().catch(() => {
    signedOut();
    return false;
  });

  return started;
}
