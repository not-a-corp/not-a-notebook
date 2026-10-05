import { request, requestAnonymous, requestJson } from "./client";
import { array, asRecord, boolean, oneOf, string } from "./decode";
import { decodeTokens, signedIn, signedOut } from "./session";

export const OAUTH_PROVIDERS = ["google", "github"] as const;
export type OAuthProvider = (typeof OAUTH_PROVIDERS)[number];

export interface AuthOptions {
  registrationOpen: boolean;
  oauth: OAuthProvider[];
}

export interface Account {
  id: string;
  email: string;
  hasPassword: boolean;
  oauth: OAuthProvider[];
  createdAt: string;
}

function decodeProvider(value: unknown): OAuthProvider {
  return oneOf({ provider: value }, "provider", OAUTH_PROVIDERS);
}

function decodeAuthOptions(value: unknown): AuthOptions {
  const json = asRecord(value, "auth options");

  return {
    registrationOpen: boolean(json, "registration_open"),
    oauth: array(json, "oauth", decodeProvider),
  };
}

export function decodeAccount(value: unknown): Account {
  const json = asRecord(value, "account");

  return {
    id: string(json, "id"),
    email: string(json, "email"),
    hasPassword: boolean(json, "has_password"),
    oauth: array(json, "oauth", decodeProvider),
    createdAt: string(json, "created_at"),
  };
}

export async function getAuthOptions(): Promise<AuthOptions> {
  const response = await requestAnonymous("/auth/options");
  return decodeAuthOptions(await response.json());
}

export interface Credentials {
  email: string;
  password: string;
}

export async function login(credentials: Credentials): Promise<void> {
  const response = await requestAnonymous("/auth/login", {
    method: "POST",
    json: { email: credentials.email, password: credentials.password },
  });
  const tokens = decodeTokens(await response.json());
  signedIn(tokens.accessToken);
}

// Registering returns no token — only signing in issues one (api.md) — so a new
// account signs in straight after, with the same credentials.
export async function register(credentials: Credentials): Promise<void> {
  await requestAnonymous("/auth/register", {
    method: "POST",
    json: { email: credentials.email, password: credentials.password },
  });
  await login(credentials);
}

export async function logout(): Promise<void> {
  try {
    await request("/auth/logout", { method: "POST" });
  } finally {
    signedOut();
  }
}

// Requires the current password when the account has one; an account made
// through OAuth has none, and sets one by leaving it out (api.md).
export async function changePassword(current: string | null, next: string): Promise<void> {
  const body: Record<string, string> = { new_password: next };
  if (current !== null) {
    body.current_password = current;
  }
  await request("/account/password", { method: "PUT", json: body });
}

export async function getAccount(): Promise<Account> {
  return decodeAccount(await requestJson("/account"));
}

// OAuth is a browser navigation, not a fetch (api.md). The provider is kept for
// the tab so a failed callback — which says only the error code — can still
// name it in its sentence.
const PENDING_PROVIDER_KEY = "not-a-notebook.oauth-provider";

export function oauthStartUrl(provider: OAuthProvider): string {
  return `/api/v1/auth/oauth/${provider}/start`;
}

export function rememberOAuthProvider(provider: OAuthProvider): void {
  sessionStorage.setItem(PENDING_PROVIDER_KEY, provider);
}

export function pendingOAuthProvider(): OAuthProvider | null {
  const stored = sessionStorage.getItem(PENDING_PROVIDER_KEY);
  const match = OAUTH_PROVIDERS.find((provider) => provider === stored);
  if (match === undefined) {
    return null;
  }

  return match;
}
