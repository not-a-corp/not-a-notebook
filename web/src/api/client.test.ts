import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The session is module state; each test gets fresh modules.
async function load() {
  vi.resetModules();
  const session = await import("./session");
  const client = await import("./client");
  const errors = await import("./errors");
  return { session, client, errors };
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const TOKENS = { access_token: "new-token", expires_at: "2026-10-04T15:00:00Z" };
const UNAUTHENTICATED = { error: { code: "UNAUTHENTICATED", message: "Not signed in." } };

type Route = (url: string, init: RequestInit) => Response;

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.href;
  }
  return input.url;
}

function stubFetch(route: Route) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    return Promise.resolve(route(urlOf(input), init ?? {}));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function authorization(init: RequestInit): string | null {
  return new Headers(init.headers).get("Authorization");
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request", () => {
  it("sends the access token it holds", async () => {
    const { session, client } = await load();
    session.signedIn("held-token");
    const fetchMock = stubFetch(() => json(200, { ok: true }));

    await client.request("/account");

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/account");
    expect(authorization(init ?? {})).toBe("Bearer held-token");
  });

  it("refreshes once on a 401 and sends the request again", async () => {
    const { session, client } = await load();
    session.signedIn("expired-token");
    const fetchMock = stubFetch((url, init) => {
      if (url.endsWith("/auth/refresh")) {
        return json(200, TOKENS);
      }
      if (authorization(init) === "Bearer new-token") {
        return json(200, { ok: true });
      }
      return json(401, UNAUTHENTICATED);
    });

    const response = await client.request("/account");

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(session.accessToken()).toBe("new-token");
  });

  it("shares one refresh between requests that fail together", async () => {
    const { session, client } = await load();
    session.signedIn("expired-token");
    const fetchMock = stubFetch((url, init) => {
      if (url.endsWith("/auth/refresh")) {
        return json(200, TOKENS);
      }
      if (authorization(init) === "Bearer new-token") {
        return json(200, { ok: true });
      }
      return json(401, UNAUTHENTICATED);
    });

    await Promise.all([client.request("/account"), client.request("/models")]);

    const refreshes = fetchMock.mock.calls.filter(([url]) => urlOf(url).endsWith("/refresh"));
    expect(refreshes).toHaveLength(1);
  });

  it("signs out and throws the 401 when the refresh fails too", async () => {
    const { session, client, errors } = await load();
    session.signedIn("expired-token");
    stubFetch(() => json(401, UNAUTHENTICATED));

    const failure = client.request("/account");

    await expect(failure).rejects.toBeInstanceOf(errors.ApiError);
    await expect(failure).rejects.toMatchObject({ code: "UNAUTHENTICATED" });
    expect(session.getSession()).toEqual({ status: "signed-out" });
  });

  it("turns the error envelope into an ApiError with its code", async () => {
    const { session, client } = await load();
    session.signedIn("token");
    stubFetch(() =>
      json(409, { error: { code: "CONVERSATION_BUSY", message: "A run is in progress." } }),
    );

    await expect(client.request("/conversations/x/messages")).rejects.toMatchObject({
      code: "CONVERSATION_BUSY",
      status: 409,
    });
  });
});

describe("ensureSession", () => {
  it("is signed in when the cookie still holds a session", async () => {
    const { session } = await load();
    stubFetch(() => json(200, TOKENS));

    await expect(session.ensureSession()).resolves.toBe(true);
    expect(session.accessToken()).toBe("new-token");
  });

  it("retries once when another tab rotated the cookie first", async () => {
    const { session } = await load();
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      if (calls === 1) {
        return json(401, UNAUTHENTICATED);
      }
      return json(200, TOKENS);
    });

    await expect(session.ensureSession()).resolves.toBe(true);
    expect(calls).toBe(2);
  });

  it("is signed out when there is no session", async () => {
    const { session } = await load();
    stubFetch(() => json(401, UNAUTHENTICATED));

    await expect(session.ensureSession()).resolves.toBe(false);
    expect(session.getSession()).toEqual({ status: "signed-out" });
  });
});
