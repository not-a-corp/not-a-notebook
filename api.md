# The API

The contract. The front door is [README.md](README.md).

Base: `/api/v1` · Auth: `Authorization: Bearer <access_token>`

Dates are ISO-8601 in UTC, so they end in `Z`. Every id in a URL or a response is a
UUID; the database's sequential id never leaves.

A list always comes inside an object, as `{"data": [...]}`. A bare array cannot
grow: the day a list needs a cursor or a total beside it, an array has to become an
object, and that breaks every client. A field added next to `data` breaks none.

### Tokens

Signing in returns two tokens, and they live in different places:

| | Lifetime | Where it lives |
| --- | --- | --- |
| **Access token** | 15 minutes | a JWT, returned in the body. The client keeps it in memory and sends it as `Bearer`. |
| **Refresh token** | 30 days of inactivity, 90 days total | an `HttpOnly; Secure; SameSite=Strict` cookie named `nan_refresh`, scoped to `/api/v1/auth`. The client never sees its value. |

The access token is checked without a database lookup. The refresh token is the
session: it is stored hashed, rotated on every use, and deleting it is what signing
out means. An access token keeps working until it expires — at most 15 minutes after
a sign-out.

### Errors

Every failure uses the same envelope:

```json
{ "error": { "code": "CONVERSATION_NOT_FOUND", "message": "No such conversation." } }
```

`code` is the contract and its text never changes. `message` is for humans and
**must not be interpreted by code**. A `500` also carries a `request_id`, and the
traceback goes to the log under it — never into the response:

```json
{ "error": { "code": "INTERNAL_ERROR", "message": "Something went wrong.",
             "request_id": "5f0c6a52-…" } }
```

A `422` never repeats the rejected input — it may have been a password.

| code | HTTP | When |
| --- | --- | --- |
| `VALIDATION_ERROR` | 422 | missing body, missing field, or malformed input |
| `UNAUTHENTICATED` | 401 | access token absent, invalid or expired; refresh cookie absent or unknown |
| `INVALID_CREDENTIALS` | 401 | wrong email or password |
| `REGISTRATION_CLOSED` | 403 | this instance does not accept new accounts |
| `EMAIL_ALREADY_REGISTERED` | 409 | that email already has an account |
| `OAUTH_PROVIDER_NOT_ENABLED` | 404 | that provider is not configured on this instance |
| `MODEL_NOT_FOUND` | 404 | the model does not exist **or is not yours** |
| `MODEL_MANAGED_BY_ENVIRONMENT` | 409 | the model comes from `.env` and cannot be changed through the API |
| `NO_MODEL_SELECTED` | 409 | the conversation has no model to answer with |
| `CONVERSATION_NOT_FOUND` | 404 | the conversation does not exist **or is not yours** |
| `CONVERSATION_BUSY` | 409 | a run is already in progress in this conversation |
| `FILE_NOT_FOUND` | 404 | the file does not exist **or is not yours** |
| `FILE_ALREADY_EXISTS` | 409 | the conversation already has a file with that name |
| `FILE_TOO_LARGE` | 413 | over the instance's upload limit |
| `UNSUPPORTED_FILE_TYPE` | 415 | not CSV, TSV, Excel or Parquet |
| `CELL_NOT_FOUND` | 404 | the cell does not exist **or is not yours** |
| `RUN_NOT_FOUND` | 404 | the run does not exist **or is not yours** |
| `SANDBOX_UNAVAILABLE` | 503 | a kernel could not be started |
| `INTERNAL_ERROR` | 500 | unexpected failure, with no internal detail |

Someone else's resource returns `404`, not `403` — a `403` would confirm that it
exists.

Two more come from the framework, before a route is reached:

| code | HTTP | When |
| --- | --- | --- |
| `NOT_FOUND` | 404 | no such path |
| `METHOD_NOT_ALLOWED` | 405 | the path exists, the method does not |

### One run at a time

Anything that touches a conversation's kernel — a message, a file upload, running a
cell, Run all — is a **run**. It answers `202` with a `run_id` straight away, does
its work in the background, and streams what happens at
[`GET /runs/{id}/events`](#get-runsidevents).

A kernel executes one thing at a time, so a conversation has at most one run in
progress. Starting a second one is `CONVERSATION_BUSY`.

---

## Auth

### `GET /auth/options`

What the sign-in screen should offer. No authentication.

```json
// 200
{ "registration_open": true, "oauth": ["google", "github"] }
```

`oauth` lists only the providers whose credentials are configured — often none.

`registration_open` is also `true` on an instance with `REGISTRATION_OPEN=false`
that has no accounts yet — the first one can still get in.

---

### `POST /auth/register`

```json
{ "email": "rafael@example.com", "password": "the account password" }
```
```json
// 201
{ "id": "018f3a2b-…", "email": "rafael@example.com",
  "created_at": "2026-10-03T14:02:11.204517Z" }
```
`VALIDATION_ERROR` · `REGISTRATION_CLOSED` · `EMAIL_ALREADY_REGISTERED`

Passwords are 8 to 128 characters, nothing else required. Returns no token — only
sign-in issues tokens.

With `REGISTRATION_OPEN=false`, registration still works **while the instance has no
users**, so a self-hoster can close the door from the first boot and still create
their own account.

---

### `POST /auth/login`

```json
{ "email": "rafael@example.com", "password": "the account password" }
```
```json
// 200 — and Set-Cookie: nan_refresh=…
{ "access_token": "eyJhbGciOi…", "expires_at": "2026-10-03T14:17:11Z" }
```
`VALIDATION_ERROR` · `INVALID_CREDENTIALS`

An account created through OAuth has no password until one is set, and signing in
with a password answers `INVALID_CREDENTIALS` like any other wrong attempt.

---

### `POST /auth/refresh`

No body — the refresh cookie is the credential.

```json
// 200 — and Set-Cookie: nan_refresh=<a new one>
{ "access_token": "eyJhbGciOi…", "expires_at": "2026-10-03T14:32:11Z" }
```
`UNAUTHENTICATED`

The refresh token is **rotated**: the old one stops working the moment the new one
is issued. A client loading the page calls this first — a valid cookie means the
user is already signed in.

Two refreshes sent at once with the same cookie — two tabs loading together — do
not both succeed: one gets the new cookie, the other `UNAUTHENTICATED`. The browser
holds the winner's cookie by then, so retrying once is enough.

---

### `POST /auth/logout`

No body. `204`. Deletes the session behind the refresh cookie and clears it.

`UNAUTHENTICATED`

---

### `GET /auth/oauth/{provider}/start`

`provider` is `google` or `github`. A browser navigation, not a `fetch`.

`302` to the provider's consent screen. The `state` and the PKCE verifier travel in
a short-lived `HttpOnly` cookie — `SameSite=Lax`, not `Strict`, because the provider
sends the browser back with a cross-site redirect, and a `Strict` cookie would not
come with it.

`OAUTH_PROVIDER_NOT_ENABLED`

---

### `GET /auth/oauth/{provider}/callback`

Where the provider sends the browser back. Never called by a client.

On success: `302` to the web app at `PUBLIC_URL`, with the refresh cookie set. The
app then calls `/auth/refresh` like on any page load.

On failure: `302` to `PUBLIC_URL/login?error=<code>`, never a JSON body — there is
no client on the other end to read one. Possible codes: `OAUTH_FAILED` (denied
consent, bad or missing `state`, provider error, an email the provider has not
verified), `REGISTRATION_CLOSED`, and `EMAIL_ALREADY_REGISTERED`.

Only an email the provider marks as **verified** is accepted — on GitHub, the
verified primary one.

**An OAuth sign-in never joins an existing password account**, even with the same
email. Emails registered with a password are not verified, so someone could
register your address first and wait for you to arrive through Google. The answer
is `EMAIL_ALREADY_REGISTERED`: sign in with the password instead. The same goes for
an email that already arrived through the other provider.

A first OAuth sign-in with a new email creates the account, subject to
`REGISTRATION_OPEN` like `/auth/register`.

---

## Account

### `GET /account`

```json
// 200
{ "id": "018f3a2b-…", "email": "rafael@example.com",
  "has_password": true, "oauth": ["github"],
  "created_at": "2026-10-03T14:02:11.204517Z" }
```
`UNAUTHENTICATED`

---

### `PUT /account/password`

```json
{ "current_password": "…", "new_password": "…" }
```
`204` · `VALIDATION_ERROR` · `INVALID_CREDENTIALS` · `UNAUTHENTICATED`

Requires the current password even with a valid token. An account with
`has_password: false` leaves `current_password` out — that is how an OAuth account
gets a password.

**Deletes every session, including yours** — you sign in again afterwards.

---

## Models

A model is a provider, an endpoint, a model name and a dialect. It comes from one of
two places:

| `source` | Scope | Who sets it |
| --- | --- | --- |
| `environment` | every user on the instance | the operator, in `.env` |
| `user` | that user only | the user, here |

The key is never returned. `key_hint` shows its last four characters, or is `null`
when there is no key (a local Ollama).

### `GET /models`

```json
// 200
{
  "data": [
    { "id": "019b1c02-…", "name": "Claude", "source": "environment",
      "adapter": "anthropic", "base_url": null, "model": "claude-sonnet-5-5",
      "dialect": "tools", "key_hint": "…x9Qa" },
    { "id": "019b1c4e-…", "name": "Local Qwen", "source": "user",
      "adapter": "openai_compatible", "base_url": "http://host.docker.internal:11434/v1",
      "model": "qwen3:14b", "dialect": "text", "key_hint": null }
  ]
}
```
`UNAUTHENTICATED`

Environment models first, then yours, each by `name`. Not paginated — nobody
configures fifty.

---

### `POST /models`

```json
{ "name": "Local Qwen", "adapter": "openai_compatible",
  "base_url": "http://host.docker.internal:11434/v1",
  "model": "qwen3:14b", "dialect": "text", "api_key": null }
```

| Field | |
| --- | --- |
| `adapter` | `anthropic` · `openai_responses` · `openai_compatible` |
| `base_url` | required for `openai_compatible`, optional otherwise |
| `dialect` | `tools` (native tool calling) or `text` (the model writes a code block) |
| `api_key` | optional — encrypted before it is stored |

`201` with the model, as in the list. · `VALIDATION_ERROR` · `UNAUTHENTICATED`

---

### `PATCH /models/{id}`

Only the fields you send change. Sending `"api_key": null` removes the key.

`200` with the model. · `VALIDATION_ERROR` · `MODEL_NOT_FOUND` ·
`MODEL_MANAGED_BY_ENVIRONMENT` · `UNAUTHENTICATED`

---

### `DELETE /models/{id}`

`204`. Conversations that used it keep their history and lose their model — the next
message answers `NO_MODEL_SELECTED` until another one is picked.

`MODEL_NOT_FOUND` · `MODEL_MANAGED_BY_ENVIRONMENT` · `UNAUTHENTICATED`

---

### `POST /models/{id}/test`

Sends one short prompt that asks for one short piece of code, in the model's
dialect. No body.

```json
// 200 — whether or not the model passed
{ "ok": false, "latency_ms": 2140,
  "error": "the model answered without calling the tool" }
```
`MODEL_NOT_FOUND` · `UNAUTHENTICATED`

A failing model is still a `200`: the test ran, and its result is the answer. This
is the button behind "does this model work here?".

---

## Conversations

### `GET /conversations`

```
GET /conversations?page=1&per_page=50&q=sales
```

| Parameter | Default | Range |
| --- | --- | --- |
| `page` | 1 | >= 1 |
| `per_page` | 50 | 1 to 200 |
| `q` | — | searches `title`, in any case; 1 to 200 characters, `%` and `_` taken literally |

```json
// 200
{
  "data": [
    { "id": "019b2a7d-…", "title": "Sales 2025 by region",
      "model_id": "019b1c02-…", "kernel": "running",
      "created_at": "2026-10-03T14:05:40.118302Z",
      "updated_at": "2026-10-03T14:21:09.774120Z" }
  ],
  "meta": { "page": 1, "per_page": 50, "total": 12, "pages": 1 }
}
```
`VALIDATION_ERROR` · `UNAUTHENTICATED`

Newest activity first. `kernel` is `running` or `stopped`.

A page past the end returns `200` with an empty `data`.

---

### `POST /conversations`

```json
{ "title": "Sales 2025 by region", "model_id": "019b1c02-…" }
```

Both optional. `title` defaults to `Untitled`.

`201` with the conversation. · `VALIDATION_ERROR` · `MODEL_NOT_FOUND` ·
`UNAUTHENTICATED`

No kernel starts here. The first run starts it.

---

### `GET /conversations/{id}`

Everything the conversation screen needs, in one call.

```json
// 200
{
  "id": "019b2a7d-…", "title": "Sales 2025 by region",
  "model_id": "019b1c02-…", "kernel": "stopped",
  "active_run_id": null,
  "files": [
    { "id": "019b2a80-…", "name": "vendas_2025.xlsx", "bytes": 482113,
      "profile": { "...": "see events.md" },
      "created_at": "2026-10-03T14:05:52.901455Z" }
  ],
  "messages": [
    { "id": "019b2a91-…", "role": "user", "run_id": "019b2a92-…",
      "text": "Which region sold the most?",
      "created_at": "2026-10-03T14:06:10.330192Z" },
    { "id": "019b2a95-…", "role": "assistant", "run_id": "019b2a92-…",
      "text": "Sudeste, with R$ 1.84M — 41% of the total.",
      "created_at": "2026-10-03T14:06:24.004817Z" }
  ],
  "cells": [
    { "id": "019b2a93-…", "position": 1, "origin": "agent",
      "run_id": "019b2a92-…", "source": "df = pd.read_excel(...)",
      "status": "ok", "stale": false, "attempts": 2, "execution_count": 1,
      "outputs": [
        { "kind": "stream", "name": "stdout", "text": "dropped 3 subtotal rows\n" }
      ],
      "executed_at": "2026-10-03T14:06:18.551023Z", "duration_ms": 812 }
  ]
}
```
`CONVERSATION_NOT_FOUND` · `UNAUTHENTICATED`

`run_id` is what ties an answer to the cells it came with. `active_run_id` is set
while a run is in progress — a client opening the page mid-run attaches to its
stream.

**Cell `status`:** `new` (never run) · `running` · `ok` · `error` · `cancelled`.
**`stale`** means a cell above was re-run, edited or deleted after this one ran.
**`attempts`** counts the agent's tries — a failed attempt is replaced in place by
the next one, and every attempt stays visible in the run's events.

**Output `kind`:**

| kind | Fields |
| --- | --- |
| `stream` | `name` (`stdout` · `stderr`), `text` |
| `error` | `name`, `value`, `traceback` — a list of lines, without terminal colour codes |
| `plotly` | `spec` — rendered by the client, in the client's theme |
| `table` | `columns`, `rows`, `total_rows` — at most 100 rows travel |
| `text` | `text` — the plain value of the last expression |
| `image` | `png` (base64) — for code that insists on matplotlib |

---

### `PATCH /conversations/{id}`

```json
{ "title": "Sales by region", "model_id": "019b1c4e-…" }
```
`200` with the conversation, as in the list. · `VALIDATION_ERROR` ·
`CONVERSATION_NOT_FOUND` · `MODEL_NOT_FOUND` · `UNAUTHENTICATED`

Only the fields you send change. `"model_id": null` takes the model away — the
next message answers `NO_MODEL_SELECTED` until another is picked. A model that is
not found changes nothing, the title included.

Changing the model mid-conversation is allowed. The new model reads the same
history and the same cells.

---

### `DELETE /conversations/{id}`

`204`. Stops the kernel, cancels a run in progress, and deletes the files from disk.
There is no trash.

`CONVERSATION_NOT_FOUND` · `UNAUTHENTICATED`

---

### `POST /conversations/{id}/messages`

```json
{ "text": "Which region sold the most?" }
```
```json
// 202
{ "message": { "id": "019b2a91-…", "role": "user", "run_id": "019b2a92-…",
               "text": "Which region sold the most?",
               "created_at": "2026-10-03T14:06:10.330192Z" },
  "run_id": "019b2a92-…" }
```
`VALIDATION_ERROR` · `CONVERSATION_NOT_FOUND` · `NO_MODEL_SELECTED` ·
`CONVERSATION_BUSY` · `UNAUTHENTICATED`

When the last run ended by asking a question, this is also how it gets answered —
the reply is a message like any other, and a new run picks it up.

---

### `POST /conversations/{id}/run-all`

No body. `202` with `{ "run_id": "…" }`.

Restarts the kernel and runs every cell in order, stopping at the first error. Clears
every `stale` mark it gets past. This is the reproducibility button.

`CONVERSATION_NOT_FOUND` · `CONVERSATION_BUSY` · `UNAUTHENTICATED`

---

### `POST /conversations/{id}/kernel/restart`

No body. `204`.

Throws the kernel's state away without running anything. The next run starts a fresh
one. The cells keep their outputs; the agent is told the state is gone.

`CONVERSATION_NOT_FOUND` · `CONVERSATION_BUSY` · `UNAUTHENTICATED`

---

### `GET /conversations/{id}/export`

```
GET /conversations/{id}/export?format=ipynb
```

| `format` | |
| --- | --- |
| `ipynb` | a Jupyter notebook — the cells, their outputs, and the chat as markdown cells |
| `py` | a plain script — the cells in order, the chat as comments |

`200` with the file, `Content-Disposition: attachment`. ·
`VALIDATION_ERROR` · `CONVERSATION_NOT_FOUND` · `UNAUTHENTICATED`

File paths in the code point at `/data/<name>`. The export notes that at the top,
so running it elsewhere means putting the files there or changing one line.

---

## Files

### `POST /conversations/{id}/files`

`multipart/form-data`, one field: `file`.

```json
// 202
{ "file": { "id": "019b2a80-…", "name": "vendas_2025.xlsx", "bytes": 482113,
            "profile": null, "created_at": "2026-10-03T14:05:52.901455Z" },
  "run_id": "019b2a81-…" }
```
`VALIDATION_ERROR` · `CONVERSATION_NOT_FOUND` · `FILE_ALREADY_EXISTS` ·
`FILE_TOO_LARGE` · `UNSUPPORTED_FILE_TYPE` · `CONVERSATION_BUSY` · `UNAUTHENTICATED`

The file is stored, then **profiled inside the sandbox** — that is the run. `profile`
is `null` until the run's `file.profiled` event; the profile is what the model sees
of the file, never the raw rows. Until the event stream exists, the profile shows
up in [`GET /conversations/{id}`](#get-conversationsid) when the run ends.

```json
{ "format": "csv", "readable": true, "encoding": "latin-1", "sheets": null,
  "findings": [],
  "tables": [
    { "sheet": null, "rows": 3, "column_count": 2,
      "columns": [
        { "name": "região", "dtype": "str", "missing": 0, "distinct": 3,
          "samples": ["Sudeste", "Nordeste", "TOTAL"] } ],
      "findings": [
        { "kind": "subtotal_rows", "rows": [4], "count": 1,
          "sums_checked": [{ "row": 4, "column": "vendas" }],
          "message": "1 row(s) look like totals mixed in with the records (rows [4]). …" } ] } ] }
```

`format` is `csv` · `tsv` · `excel` · `parquet`. `encoding` is set for CSV and TSV;
`sheets` lists an Excel workbook's sheets in its own order, with one entry in
`tables` per sheet. A file that cannot be read is still a profile —
`{"format": …, "readable": false, "error": "…"}` — and its run still succeeds:
"this is not a valid Parquet file" is the answer, not a failure.

**Findings** are what a careful analyst would catch, before any question. Every
one has a `kind` and a `message`; `rows` are numbered as in the file (a header on
line 4 makes the first record row 5), at most ten listed beside a `count`.
Suspicious values are shown both ways, never fixed.

| `kind` | Where | Says |
| --- | --- | --- |
| `data_not_on_first_sheet` | file | the workbook's data is on `largest`, not on `first` |
| `header_not_on_first_row` | table | the header is on `header_row`; `above` holds what came before. The table is described from the header down. |
| `subtotal_rows` | table | rows labelled as totals; `sums_checked` lists those that equal the sum of the rows above them |
| `exact_duplicates` | table | rows that copy an earlier row |
| `number_formats` | column | numbers stored as text, the `formats` they use, whether they are `mixed`, and `ambiguous` values with every `readings` (`"1.234"` → `plain` 1.234, `brazilian` 1234) |
| `date_formats` | column | dates stored as text, their `formats`, and `ambiguous` values as both `as_dd_mm` and `as_mm_dd` |
| `inconsistent_labels` | column | `variants`: one label spelled several ways (`Sudeste`, `sudeste`, `Sudeste `) |
| `contradicting_columns` | table | `columns[0]` equals `columns[1]` × `columns[2]` on most rows, but not on `rows` |
| `dominating_value` | column | one value is `share` of the column's total |
| `missing_values` | column | `count` missing, and the `placeholders` typed in their place (`-`, `n/d`) |

The name is what the code sees at `/data/<name>`, so it is kept as given: one path
component, at most 255 characters, not starting with a dot. A name that cannot be
a file there is `VALIDATION_ERROR`; so is an empty file.

Accepted: `.csv`, `.tsv`, `.xlsx`, `.xls`, `.xlsm`, `.parquet`. The size limit is
`MAX_UPLOAD_MB` on the instance.

---

### `DELETE /conversations/{id}/files/{file_id}`

`204`. The file is gone from disk. Cells that read it keep their code and outputs —
and will fail the next time they run.

`CONVERSATION_NOT_FOUND` · `FILE_NOT_FOUND` · `CONVERSATION_BUSY` · `UNAUTHENTICATED`

---

## Cells

### `POST /conversations/{id}/cells`

A cell written by you.

```json
{ "source": "df.groupby('region')['revenue'].sum()", "after_cell_id": "019b2a93-…" }
```

`after_cell_id` is optional — without it, the cell goes at the end. `null` puts it
first.

`201` with the cell, `status: "new"`. It does not run. · `VALIDATION_ERROR` ·
`CONVERSATION_NOT_FOUND` · `CELL_NOT_FOUND` · `UNAUTHENTICATED`

---

### `PATCH /cells/{id}`

```json
{ "source": "df.groupby('region')['revenue'].sum().sort_values()" }
```

`200` with the cell. Editing does not run it — but every cell below that already
ran becomes `stale`.

`VALIDATION_ERROR` · `CELL_NOT_FOUND` · `CONVERSATION_BUSY` · `UNAUTHENTICATED`

Editing an agent's cell is allowed and expected. The agent sees your version on its
next turn.

---

### `POST /cells/{id}/run`

No body. `202` with `{ "run_id": "…" }`.

Runs this one cell in the live kernel — Jupyter semantics. Every cell below that
already ran becomes `stale`.

`CELL_NOT_FOUND` · `CONVERSATION_BUSY` · `SANDBOX_UNAVAILABLE` · `UNAUTHENTICATED`

---

### `DELETE /cells/{id}`

`204`. Cells below that already ran become `stale` — the deleted cell may have built
something they use.

`CELL_NOT_FOUND` · `CONVERSATION_BUSY` · `UNAUTHENTICATED`

---

## Runs

### `GET /runs/{id}`

```json
// 200
{ "id": "019b2a92-…", "conversation_id": "019b2a7d-…",
  "kind": "message", "status": "succeeded",
  "model": "claude-sonnet-5-5",
  "tokens_in": 6120, "tokens_out": 911, "tokens_reasoning": 340,
  "started_at": "2026-10-03T14:06:10.331004Z",
  "finished_at": "2026-10-03T14:06:24.009311Z", "wall_ms": 13678 }
```
`RUN_NOT_FOUND` · `UNAUTHENTICATED`

**`kind`:** `message` · `profile` · `cell` · `run_all`.

**`status`:** `running` · `awaiting_user` (ended by asking you a question) ·
`succeeded` · `failed` · `cancelled` · `timed_out`. Only `running` is in progress.

`model` is the model name at the time of the run, so the record survives the
model's configuration changing.

---

### `GET /runs/{id}/events`

The run, as a stream. Server-Sent Events.

```
event: cell.output
id: 8
data: {"seq":8,"t":1.39,"type":"cell.output","cell_id":"019b2a93-…","attempt":1,"kind":"error",...}

```

Every event is also **stored**, so this endpoint works the same during a run and
after it: it replays what is stored, then follows live until `run.finished`, then
closes. Reconnecting with `Last-Event-ID: 8` resumes from `seq` 9 — a dropped tab
loses nothing.

`RUN_NOT_FOUND` · `UNAUTHENTICATED`

- `seq` starts at 1 and never skips. A gap means loss, and the client can say so.
- `run.finished` is always the last event, even when something broke.
- A `: keepalive` comment every 15 seconds, so proxies do not drop the connection
  while the model thinks.
- A browser's `EventSource` cannot send an `Authorization` header — clients read
  this with `fetch` and a stream parser.

The events, by group. Their payloads are the contract in **[events.md](events.md)**.

| Group | Events |
| --- | --- |
| Run | `run.started` · `run.error` (our bug, not the code's) · `run.finished` |
| Kernel | `kernel.starting` · `kernel.ready` · `kernel.restarted` |
| Files | `file.uploaded` · `file.profiled` |
| Model | `llm.started` · `llm.delta` · `llm.finished` |
| Attempts | `attempt.started` · `code.proposed` · `attempt.finished` |
| Cells | `cell.created` · `cell.output` · `cell.finished` · `cells.stale` |
| Ending | `answer` · `grounding.checked` · `question` |

---

### `POST /runs/{id}/cancel`

No body. `202`. Interrupts the kernel and stops the agent; the stream ends with
`run.finished` and `status: "cancelled"`. The kernel's state survives an interrupt.

Cancelling a run that already finished is a `202` that changes nothing.

`RUN_NOT_FOUND` · `UNAUTHENTICATED`

---

## Operations

### `GET /health`

```json
// 200
{ "status": "ok" }
```

The service is up and reached the database within two seconds. No authentication.
Anything else is `INTERNAL_ERROR`.

---

# Using it

A full path with `curl`:

```bash
BASE=http://localhost:8000/api/v1

# 1. create the account
curl -X POST $BASE/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"rafael@example.com","password":"a good password"}'

# 2. sign in — keep the refresh cookie in a jar
TOKEN=$(curl -s -c jar.txt -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"rafael@example.com","password":"a good password"}' \
  | jq -r .access_token)

# 3. add a model — a local Ollama
MODEL=$(curl -s -X POST $BASE/models \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Local Qwen","adapter":"openai_compatible",
       "base_url":"http://host.docker.internal:11434/v1",
       "model":"qwen3:14b","dialect":"text"}' \
  | jq -r .id)

# 4. start a conversation
CONV=$(curl -s -X POST $BASE/conversations \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"model_id\":\"$MODEL\"}" \
  | jq -r .id)

# 5. upload a file, and watch it get profiled
RUN=$(curl -s -X POST $BASE/conversations/$CONV/files \
  -H "Authorization: Bearer $TOKEN" -F file=@vendas_2025.xlsx \
  | jq -r .run_id)
curl -N $BASE/runs/$RUN/events -H "Authorization: Bearer $TOKEN"

# 6. ask, and watch the answer get built
RUN=$(curl -s -X POST $BASE/conversations/$CONV/messages \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"Which region sold the most?"}' \
  | jq -r .run_id)
curl -N $BASE/runs/$RUN/events -H "Authorization: Bearer $TOKEN"

# 7. export it
curl -OJ "$BASE/conversations/$CONV/export?format=ipynb" \
  -H "Authorization: Bearer $TOKEN"

# 8. a new access token, when the old one expires
TOKEN=$(curl -s -b jar.txt -c jar.txt -X POST $BASE/auth/refresh | jq -r .access_token)

# 9. sign out
curl -b jar.txt -X POST $BASE/auth/logout -H "Authorization: Bearer $TOKEN"
```

---

## What is not here yet

| | Comes in when |
| --- | --- |
| Deleting the account | the hosted version opens to strangers |
| Linking an OAuth provider to an existing account | someone asks for it — today it is one or the other |
| Listing and revoking devices | there is a screen for it |
| Reordering cells | inserting where you want stops being enough |
| Downloading files the code produced | the agent writes files worth keeping |
| Database connectors | v1 |
| Password reset by email | an email provider is configured |
