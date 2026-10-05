# The events

The stream contract: what [`GET /runs/{id}/events`](api.md#get-runsidevents) sends,
payload by payload. The HTTP contract is [api.md](api.md).

A run is everything that touches a conversation's kernel — a message, a file
upload, running a cell, Run all. Its events tell what happened in order, as it
happened, and are **stored**: the same stream can be replayed during the run and
after it, and a dropped connection resumes where it stopped.

## The envelope

Every event is one Server-Sent Event:

```
event: cell.output
id: 8
data: {"seq":8,"t":1.39,"type":"cell.output","cell_id":"019b2a93-…","attempt":1,"kind":"stream","name":"stdout","text":"42\n"}

```

| Field | |
| --- | --- |
| `seq` | 1, 2, 3… within the run. Never skips: a gap means loss, and the client can say so. Also the SSE `id`, so `Last-Event-ID` resumes after it. |
| `t` | seconds since the run started, two decimals. What answers "where did the seconds go". |
| `type` | the event's name — the same as the SSE `event:` line, so a client can switch on either. |

Everything else in `data` is the event's own payload, below. Ids are UUIDs, times
inside payloads are ISO-8601 UTC, and a field that has no value is `null`, never
absent.

**Ordering rules a client can rely on:**

- `run.started` is first and `run.finished` is last — always, even when the run
  breaks. Nothing comes after `run.finished`; the stream closes.
- A cell's `cell.output` events come after its `attempt.started` and before that
  attempt's `attempt.finished` — or, for a cell you run, which has no attempts,
  after its `cell.started` and before its `cell.finished`.
- `llm.delta` for a step comes between that step's `llm.started` and
  `llm.finished`.

Between events, a `: keepalive` comment every 15 seconds keeps proxies from
dropping a connection while the model thinks. It has no `seq` and is not stored.

---

## Run

### `run.started`

```json
{ "type": "run.started", "run_id": "019b2a92-…", "conversation_id": "019b2a7d-…",
  "kind": "message", "model": "claude-sonnet-5-5" }
```

`kind` is `message` · `profile` · `cell` · `run_all`. `model` is the model's name for
a `message` run and `null` for the others — they run code, not a model.

### `run.error`

Something broke that is **not the code's fault**: the kernel could not start, the
model's provider failed, or the API has a bug. An exception in the user's or the
model's code is never a `run.error` — it is a `cell.output` of kind `error`.

```json
{ "type": "run.error", "code": "MODEL_UNAVAILABLE",
  "message": "The provider answered: Overloaded", "error_id": null }
```

| `code` | When |
| --- | --- |
| `SANDBOX_UNAVAILABLE` | the kernel could not be started |
| `MODEL_UNAVAILABLE` | the provider refused or failed, after retries; `message` carries its words |
| `MODEL_REFUSED` | the model's safety system declined the request |
| `STEP_LIMIT` | the model kept running code, step after step, without ever answering |
| `INTERNAL_ERROR` | our bug. `message` says nothing about what broke; `error_id` is the id the traceback is logged under |

Always followed by `run.finished` with `status: "failed"`.

A run whose API process died gets these two from the next process, when it
starts: `INTERNAL_ERROR`, "The API stopped while this run was in progress.", then
`run.finished`, numbered after the last event the dead process stored — so a
stream reconnecting after a restart still ends.

### `run.finished`

```json
{ "type": "run.finished", "status": "succeeded",
  "tokens_in": 6120, "tokens_out": 911, "tokens_reasoning": 340, "wall_ms": 13678 }
```

`status` is the run's final status, as in [`GET /runs/{id}`](api.md#get-runsid):
`succeeded` · `awaiting_user` (it ended by asking a question) · `failed` ·
`cancelled` · `timed_out`. A timeout is a status, not an error: the run did
nothing wrong, it ran out of time. Token counts are for the whole run, `0` for
runs that call no model.

---

## Kernel

### `kernel.starting`

```json
{ "type": "kernel.starting" }
```

The conversation had no kernel running, and one is being started — the first run
of a conversation, or the first after its kernel was reaped. The cold start is
seconds; this is what lets a client say so instead of looking stuck.

### `kernel.ready`

```json
{ "type": "kernel.ready", "startup_ms": 2210 }
```

### `kernel.restarted`

```json
{ "type": "kernel.restarted", "reason": "idle" }
```

The kernel this conversation had is gone, and with it every variable (decision 3).
`reason` is `idle` (reaped for not being used) · `died` (out of memory, most often)
· `requested` (the user restarted it) · `run_all` (Run all starts from nothing) ·
`lost` (none was running when this run began, though cells had run before — the
API restarted, and every kernel goes with it).

The cells keep their outputs. The model is told too, before its next step, so it
reloads instead of using a variable that no longer exists.

---

## Files

### `file.uploaded`

```json
{ "type": "file.uploaded",
  "file": { "id": "019b2a80-…", "name": "vendas_2025.xlsx", "bytes": 482113,
            "profile": null, "created_at": "2026-10-03T14:05:52.901455Z" } }
```

The file as [`POST /conversations/{id}/files`](api.md#post-conversationsidfiles)
returned it. First event after `run.started` in a `profile` run.

### `file.profiled`

```json
{ "type": "file.profiled", "file_id": "019b2a80-…", "profile": { "format": "excel", "...": "…" } }
```

`profile` is the whole profile, in the shape api.md documents, findings included.
A file that cannot be read still arrives here, with `"readable": false`.

---

## Model

One **step** is one request to the model: it reads the conversation so far and
answers with words, with code to run, or with both. A `message` run is steps
until the model answers without code.

### `llm.started`

```json
{ "type": "llm.started", "step": 1 }
```

### `llm.delta`

```json
{ "type": "llm.delta", "step": 1, "text": "Let me load the file" }
```

The model's visible words, as they stream — in chunks, not lines or words. Its
thinking, when it thinks, is not streamed.

### `llm.finished`

```json
{ "type": "llm.finished", "step": 1, "stop": "code",
  "tokens_in": 2048, "tokens_out": 180, "tokens_reasoning": 64, "ms": 3120 }
```

`stop` is `code` (it wants code run — the step goes on to an attempt) · `answer`
(it is done) · `max_tokens` (it was cut off) · `refusal` (its safety system
declined; a `run.error` with `MODEL_REFUSED` follows).

---

## Attempts

An **attempt** is one try at running the code the model proposed. When it fails,
the model reads the traceback and tries again — and the retry **replaces the same
cell** (decision 18): the notebook keeps one working cell, and every attempt stays
here, in the run's events.

### `code.proposed`

```json
{ "type": "code.proposed", "step": 2, "cell_id": "019b2a93-…", "attempt": 2,
  "code": "df = pd.read_excel('/data/vendas_2025.xlsx', sheet_name='Vendas', header=3)" }
```

The code the model wants run, before it runs. `attempt` 1 is a new cell; a higher
one rewrites that cell.

### `attempt.started`

```json
{ "type": "attempt.started", "cell_id": "019b2a93-…", "attempt": 2 }
```

### `attempt.finished`

```json
{ "type": "attempt.finished", "cell_id": "019b2a93-…", "attempt": 2,
  "status": "ok", "execution_count": 3, "duration_ms": 812 }
```

`status` is `ok` · `error` · `cancelled` · `timed_out`. After `error`, the model
gets the traceback and the next step may be another attempt at the same cell.

---

## Cells

### `cell.created`

```json
{ "type": "cell.created",
  "cell": { "id": "019b2a93-…", "position": 4, "origin": "agent", "run_id": "019b2a92-…",
            "source": "df = pd.read_excel('/data/vendas_2025.xlsx')", "status": "running",
            "stale": false, "attempts": 1, "execution_count": null, "outputs": [],
            "executed_at": null, "duration_ms": null } }
```

The cell as [`GET /conversations/{id}`](api.md#get-conversationsid) shows it.
Only for a cell the model creates — a cell you run already exists.

### `cell.started`

```json
{ "type": "cell.started", "cell_id": "019b2a93-…" }
```

A cell you run, or one of Run all's, starts executing: its old outputs are about
to be replaced, even if it prints nothing. A cell the model writes announces
`attempt.started` instead, once per attempt.

### `cell.output`

```json
{ "type": "cell.output", "cell_id": "019b2a93-…", "attempt": 1,
  "kind": "stream", "name": "stdout", "text": "dropped 3 subtotal rows\n" }
```

One output, as it is produced. Its fields after `attempt` are the output kinds of
api.md, flattened into the event:

| `kind` | Fields |
| --- | --- |
| `stream` | `name` (`stdout` · `stderr`), `text` — a chunk, not a line |
| `error` | `name`, `value`, `traceback` (a list of lines, no colour codes) |
| `plotly` | `spec` |
| `table` | `columns`, `rows`, `total_rows` — at most 100 rows |
| `text` | `text` |
| `image` | `png` (base64) |

`attempt` is `null` for a cell you run.

### `cell.finished`

```json
{ "type": "cell.finished", "cell_id": "019b2a93-…", "status": "ok",
  "attempts": 2, "execution_count": 3, "duration_ms": 812 }
```

The cell settles: `ok` · `error` (the last attempt failed, and the model moved on
or gave up) · `cancelled`. What the notebook now holds for it.

### `cells.stale`

```json
{ "type": "cells.stale", "cell_ids": ["019b2a97-…", "019b2a98-…"] }
```

These cells ran before a cell above them was run again, edited or deleted; what
they show may no longer follow from the code above (decision 10).

---

## Ending

### `answer`

```json
{ "type": "answer",
  "message": { "id": "019b2a95-…", "role": "assistant", "run_id": "019b2a92-…",
               "text": "Sudeste, with R$ 1.84M — 41% of the total.", "kind": "answer",
               "grounding": { "numbers": 2, "found": 1, "unfound": ["41%"] },
               "created_at": "2026-10-03T14:06:24.004817Z" } }
```

The model's final words, as the message now stored in the conversation — its
grounding check included, the same one `grounding.checked` sends next. The
same text arrived as `llm.delta`s; this is the settled version.

### `grounding.checked`

```json
{ "type": "grounding.checked", "numbers": 3, "found": 2,
  "unfound": ["41%"] }
```

The numbers in the answer, checked against everything the run's code printed or
returned. `unfound` lists the ones no output contains — a number the model may
have invented or computed in its head. A check that finds nothing wrong proves
little: it does not catch code that silently drops rows. It is necessary, not
sufficient.

### `question`

```json
{ "type": "question",
  "message": { "id": "019b2a96-…", "role": "assistant", "run_id": "019b2a92-…",
               "text": "The file ends in March 2025 — do you mean 2025 so far, or 2024?",
               "kind": "question", "grounding": null,
               "created_at": "2026-10-03T14:06:24.004817Z" } }
```

The model asks instead of guessing. The run ends `awaiting_user`; the answer is an
ordinary message, which starts a new run.

---

## A message run, start to finish

```
run.started        kind=message
kernel.starting                              (only if no kernel was running)
kernel.ready
llm.started        step=1
llm.delta          "Let me look at the sheet first."
llm.finished       stop=code
code.proposed      attempt=1
cell.created
attempt.started
cell.output        kind=error  KeyError: 'região'
attempt.finished   status=error
llm.started        step=2
llm.finished       stop=code
code.proposed      attempt=2                (same cell, rewritten)
attempt.started
cell.output        kind=table
attempt.finished   status=ok
cell.finished      status=ok attempts=2
llm.started        step=3
llm.delta          "Sudeste, with R$ 1.84M…"
llm.finished       stop=answer
answer
grounding.checked
run.finished       status=succeeded
```
