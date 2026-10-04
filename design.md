# The interface

How the web app looks and behaves, decided before any component is written. The
HTTP contract is [api.md](api.md), the stream contract is [events.md](events.md);
this is the third contract: what a person sees for every endpoint and every event.

The mockups made from [the brief at the end](#appendix-a--brief-for-mockups) live
in [mockups/](mockups/): they are the visual reference for this document, and where
the two disagree, this document wins. What changes in a mockup changes here first,
then in code.

---

## 1. What the interface has to get across

The product is a data analyst that shows its work. The interface carries that
promise, or nothing does. Three things, in this order:

1. **The work is visible while it happens.** Code appears as the model writes it,
   runs as cells, and fails in plain view — a retry looks like a retry. Nothing
   collapses into a spinner and a final paragraph.
2. **Every answer can be traced.** The number in the chat points at the cell that
   printed it. What the profile found in the file is on screen before the first
   question, and the answer says what was done about it.
3. **The notebook is real.** Cells are objects you read, edit, re-run and keep. A
   cell the agent wrote and a cell you wrote are the same thing with a different
   label.

The tone follows: calm, precise, dense where data is, quiet everywhere else. A
tool for people who read code — not a toy, not a dashboard.

### Principles

- **Data is the loudest thing on the screen.** Chrome is neutral and thin; colour
  is spent on state (running, failed, stale) and on charts.
- **State is never ambiguous.** Every cell says whether it ran, failed, is running,
  is stale. Every run says whether it is thinking, running code, waiting for you.
- **Nothing is hidden that was done.** Failed attempts stay one click away;
  findings stay attached to their file; the kernel's restarts are announced.
- **Keyboard first, mouse fine.** The notebook works without touching the mouse.
- **Dense, not cramped.** 14 px base, tight line heights in tables and code, air
  between sections — the density of a code editor, not of a spreadsheet.

---

## 2. Screens

| Screen | Route | What it is for |
| --- | --- | --- |
| Sign in | `/login` | email and password; Google and GitHub buttons only when enabled |
| Create account | `/register` | the same form; gone when registration is closed |
| Conversation | `/c/:id` | the product: chat beside the notebook, files in the chat's files bar |
| Home | `/` | one centred composer: ask, or drop a file |
| Settings | `/settings/:section` | a page of its own, sections in a side nav: General, Account, Models |

There is no separate "conversations" page: the list lives in the sidebar of every
screen, the way a mail client keeps its folders.

### 2.1 The shell

```
┌────────────────────┬──────────────────────────────────────────────────────┐
│ ▢ not-a-notebook  ◧│ Sales 2025 by region ✎  [Claude ▾]  ● Kernel ready ⋯ │  header 48
│ ✎ New conversation ├──────────────────────┬───────────────────────────────┤
│ ⌕ Search        ⌘K │ Chat               ⤢ │ Notebook · 5 cells          ⤢ │  tabs 36
│                    │ [relatorio.csv ⚠5] + │                               │  files bar
│ Today              │                      │                               │
│  Sales…          • │                      │                               │
│  Churn…            │                      │                               │
│ Earlier            │                      │                               │
│  …                 │                      │                               │
│────────────────────│                      │                               │
│ ⚙ Settings         │ [ composer        ↑ ]│                               │
│ (r) rafael@…     ⋯ │ Enter to send · …    │                               │
└────────────────────┴──────────────────────┴───────────────────────────────┘
  sidebar 248           chat 40%               notebook 60%  (resizable)
```

- **Sidebar** (248 px, `surface`, a `border` on its right; collapsible to 56 px
  icons):
  - a 48 px top row with the wordmark — a 12 px outlined square and
    `not-a-notebook` in JetBrains Mono 600, 13 px, lowercase — and the collapse
    button;
  - *New conversation* (square-pen icon) and *Search* with its `⌘K` key chip,
    32 px rows;
  - the conversations grouped by activity (Today, Yesterday, Last 7 days,
    Earlier) from `updated_at` — group labels `text-xs` 500 muted, rows 32 px,
    one line, ellipsised. The open conversation's row is filled with `text` at
    8% and set in 500; a conversation with a run in progress carries a 6 px
    `accent` dot at the row's end. Infinite scroll over `GET /conversations`
    pages;
  - at the bottom, above a `border`: the gear labelled **Settings** (with its
    `⌘,` hint while Settings is open) and a 40 px account row — a 24 px round
    avatar with the email's first letter, the email, and a `⋯` menu holding
    *Sign out*. The account has no name in the API; the email stands in.
- **Header** of a conversation (48 px, a `border` under it): the title, 600, with
  a pencil to rename; the model picker, an outlined 32 px button (`PATCH
  model_id`); the kernel indicator (§3.2); and an overflow menu: Run all,
  Restart kernel, Swap panes, Export (Phase 8), Delete.
- **Panes as tabs.** Chat and Notebook are two panes, split **40/60** by default.
  There is no files column: files live in the chat's files bar. Each pane has a
  **36 px tab strip** with a `border` under it, the way an editor docks its views:
  the tab — a 14 px icon (message-square, notebook) and its label, 13 px 500 —
  is marked as the pane's own by a 2 px `text` underline; the Notebook tab adds
  its cell count, muted (*· 5 cells*). **Maximise** (a 28 px icon button,
  maximize-2) sits at the right end of the strip.
  - **Swap by dragging.** Drag a tab towards the other side. The tab leaves a
    dashed outline where it was and follows the pointer as a raised chip at 80%
    opacity. The pane it would land on is tinted (`accent-soft` at 85%, a 2 px
    `accent` edge inset) and labelled **Drop to swap panes** in a 32 px raised
    chip at its centre; dropping there swaps the panes — chat right and notebook
    left, or back. Escape cancels.
  - **The same without a mouse:** *Swap panes* in the header's overflow menu and
    `Ctrl/Cmd+Alt+\`. A drag is never the only way to do something.
  - **Resize** by dragging the divider: a 1 px `border` line with an 8 px hit
    area and the column cursor. On hover the line darkens to `text-muted` and a
    **13 × 32 px grip** appears at its middle — `surface-raised`, a `border`,
    radius 6, a 12 px grip-vertical icon — with the tooltip *Drag to resize ·
    double-click for 40/60*. Each pane keeps at least 360 px; double-clicking the
    divider goes back to 40/60. A maximised pane is restored from the same
    button.
  - Side and ratio are remembered per browser, for every conversation — it is a
    preference about the screen, not about the analysis.

### 2.2 Sign in and create account

A centred card on a `surface` page: 400 px, `surface-raised`, a `border`, radius
12, padding 32, its blocks 24 px apart. From the top: the wordmark; the title
(*Sign in* or *Create account*, `text-xl` 600) with one line under it, muted — *A
data analyst that shows its work.*; the form — labels 13 px 500, 32 px inputs on
`bg`, the primary button full width; an *or* divider; and the OAuth buttons,
outlined and full width (*Continue with Google*, *Continue with GitHub*, each
with its mark) — rendered only for the providers `GET /auth/options` lists, and
the divider with them. Last, centred and muted: *No account yet? Create one* (or
the way back), absent when registration is closed. Under the card, 16 px below,
the instance's host in JetBrains Mono 12 px, muted — which instance this is.

A `?error=` from an OAuth callback becomes a sentence above the form (table in
§6).

### 2.3 Home — a new conversation

No panes, no empty notebook, no drop zone: the sidebar, and in the rest of the
screen one composer, centred, on a background of its own.

```
┌──────────┬───────────────────────────────────────────────────────────────┐
│ sidebar  │            ·  ·  soft light, a faint grid  ·  ·               │
│          │                                                               │
│          │              What do you want to know about                   │
│          │                       your data?                              │
│          │   ┌───────────────────────────────────────────────────────┐   │
│          │   │ Ask a question, or drop a file…                        │   │
│          │   │                                                       │   │
│          │   │ [📎 Attach]  [ vendas_2025.xlsx × ]    [Claude ▾]  (↑) │   │
│          │   └───────────────────────────────────────────────────────┘   │
│          │          CSV, TSV, Excel or Parquet — drop it anywhere        │
└──────────┴───────────────────────────────────────────────────────────────┘
```

- **The background** is the one place the interface is decorative, and it stays
  quiet: three large, blurred patches of colour at the edges — `accent` at 12%
  (620 px, off the top-left corner), the chart palette's second colour at 10%
  (680 px, off the bottom-right), `accent` again at 8% (420 px, off the top
  right), all blurred 120 px — over a grid of 1 px `border` lines every 96 px,
  masked by a radial gradient so it fades out towards the centre and the
  composer sits on calm ground. It follows the theme — teal and orange in Light
  and Dark, mauve and blue in Catppuccin Mocha. Still under
  `prefers-reduced-motion`; otherwise the patches drift slowly enough not to be
  noticed (the mockups are static; the drift is the build's).
- **The headline**, `text-xl` 500, one line of what the product does, in the
  interface's voice — no product name, no marketing: *What do you want to know
  about your data?* The headline, the composer and the hint under it sit 24 px
  apart, a little above the centre.
- **The composer**, 720 px wide, `surface-raised` with a `border` and the overlay
  shadow, radius 16, padding 16 / 12 / 12 / 16, three lines tall (66 px) and
  growing with the text. Inside, at the bottom: *Attach* (a ghost button with
  the paperclip), the chips of the files attached so far (28 px, `surface`, a
  file icon, name, size, ×), then — pushed right — the model picker (borderless
  here) and the round 32 px send button. Focused on load. **Focus shows as the
  caret only** — no ring around the composer; the caret is the focus indicator
  of a text field, and a ring around the one thing on the page adds nothing.
- **Send is enabled** as soon as there is text **or a file**: a file can be sent
  alone. Disabled, it is filled with `text` at 8% and its icon muted, and its
  tooltip says why (*type a question or attach a file first*).
- Under the composer, muted: *CSV, TSV, Excel or Parquet — drop it anywhere*.
- **Files drop anywhere** on the page. While one is dragged over, the area gets a
  2 px dashed `accent` outline **inset 12 px** from its edges (radius 12) over an
  `accent-soft` tint at 55%, and a label — *Drop to attach*, 16 px 500, a 20 px
  upload icon in `accent`, in a 40 px raised chip with the overlay shadow — set
  **above the composer**, so the composer stays readable under the tint.
  Dropping attaches the file to the composer; nothing is uploaded yet.
- **Sending** creates the conversation, uploads the attached files one at a time
  (each is a profile run, and a conversation has one run at a time), then posts
  the message — so a conversation exists only once there is something in it,
  and empty ones never pile up in the list. A file sent alone is profiled and
  its findings are shown; there is no message, so the analyst says nothing until
  asked.
- **Then the screen becomes the conversation**: the composer slides down into the
  chat pane (200 ms), the notebook pane opens on the side last used, and the first
  run streams in.

### 2.4 Conversation — the chat pane

From top to bottom, in order of time:

- **Files bar**, pinned under the tab strip (padding 8 / 16, a `border` under
  it): a 28 px chip per file on `surface-raised` — a file icon, the name (13 px
  500), the size (muted), and a findings badge: *⚠ 5 findings* in `warning` on
  `warning` at 14%, grey *clean* when there are none, a pulsing dot while the
  profile runs. Clicking a chip opens the **profile drawer** (§3.6). A 28 px
  dashed `+` uploads more.
- **The timeline** is anchored to the bottom, its items 24 px apart, padding 24.
  It interleaves, by time:
  - **A file arriving**, as one muted 12 px line: *relatorio.csv added · 1,286
    rows × 6 columns · 5 findings* and an **Open profile** link in `accent`.
  - **Messages.** Yours right-aligned, at most 85% wide, on `surface`, radius 12,
    padding 8 / 12. The analyst's left-aligned under a muted *Analyst* label
    (12 px 500), no bubble, full width — it reads like a document, with markdown
    tables rendered (13 px, tabular figures, a `border` between rows).
  - **A kernel restart**, as a muted 12 px divider line across the timeline:
    *Kernel restarted · idle for 15 min · 14:41*. It is drawn when a
    `kernel.restarted` arrives; it is not stored, so a reloaded conversation
    does not show it.
- **The analyst at work** is **inside its message** while a run is live (§4): the
  streamed text as it arrives, and under it the **activity line** — an
  `accent-soft` block, radius 6, padding 8 / 12: a spinning loader in `accent`,
  the activity (13 px 500: *Thinking…*, *Writing cell 3*, *Running cell 3*,
  *Retrying cell 3 (attempt 2)*), a muted 12 px second line when there is
  something to add (*Attempt 1: `KeyError: 'data'`*, the error in mono), and the
  cell's `[3]` in `accent` mono at the right — a link to the cell.
- **The answer**, when it settles: its lead line in `text-md`, then the rest at
  `text-base`; then its **grounding badge** (§3.5) and, beside it, *from cells*
  and the `[n]` of the cells the run wrote — links to them.
- **A question back** (`ask_user`) is styled as a question: a distinct left rule
  and the composer focused, placeholder *"Answer the question…"*.
- **Composer** at the bottom (padding 0 / 16 / 16): `surface-raised`, a `border`,
  radius 8, padding 12 / 8 / 8 / 12, two lines tall and growing; placeholder
  *Ask a follow-up…*. Its bottom row: an upload icon button, then — pushed right
  — the 32 px send button, square with radius 6 (`accent`, `on-accent` arrow).
  Under it, muted 12 px: *Enter to send · Shift+Enter for a new line*. Enter
  sends, Shift+Enter breaks a line. While a run is live the send button becomes
  **Stop** — outlined, a 10 px square glyph, *Stop*, and an `Esc` key chip
  (`POST /runs/{id}/cancel`). Disabled with a reason when the conversation has
  no model.

### 2.5 Conversation — the notebook pane

A vertical list of cells, like a notebook, 24 px apart (padding 24 / 32 / 24 / 8),
each cell a 48 px gutter and its body:

```
  [*]▌ agent · attempt 2                     Running · 1.8 s  ■  ⌫  +    header 28
     ▌ ┌──────────────────────────────────────────────────────────────┐
     ▌ │ › ⊗ Attempt 1 failed  KeyError: 'data'                 0.2 s │  failed attempt
     ▌ └──────────────────────────────────────────────────────────────┘
     ▌ ┌──────────────────────────────────────────────────────────────┐
     ▌ │ vendas["Data"] = pd.to_datetime(vendas["Data"], dayfirst=True)│  code
     ▌ │ por_regiao = vendas.groupby("Região")["Faturamento"].sum()   │
     ▌ └──────────────────────────────────────────────────────────────┘
          total: 10238700.00                                              stdout
         ┌ Região  │ faturamento ┐                                       table
         │ Sudeste │  4218340.50 │
         └─────────┴─────────────┘
          4 of 4 rows                          2 attempts · 640 ms · 14:06  footer
```

- **Gutter**: the execution count, right-aligned, JetBrains Mono 12 px, muted —
  `[3]`, `[ ]` when never run, `[*]` in `accent` 600 while running — and a 2 px
  bar at its right edge for status (§3.3).
- **Cell header** (28 px, 12 px muted; shown on hover, on the focused cell and
  while the cell runs): the origin — *agent* or *you*, in `text` 500 — and,
  while it runs, *· attempt 2* and *Running · 1.8 s* in `accent`; then the
  28 px actions: Run (Stop while running), Delete, Add cell below.
- **Source**: CodeMirror on `surface`, a `border`, radius 8, padding 8 / 12,
  JetBrains Mono 13 / 20, with the syntax colours of §5.3; read-only until
  clicked or Enter is pressed; Escape leaves it. The focused cell's border is
  `accent` mixed 55% into `border`. Editing marks the cells below as stale.
- **Failed attempts** are a **collapsed row inside the cell**, one per failed
  attempt, above the source: 32 px, a `border`, radius 6 — a chevron, a
  `danger` circle-x, *Attempt 1 failed* (500), the error's name and value in
  mono 600 `danger`, and its duration at the right. Opening it shows that
  attempt's code and its error output. They come from the run's events: live,
  as they happen; for a cell that already settled, the footer's *2 attempts* is
  a link that loads them (`GET /runs/{run_id}/events`, the cell's events only)
  and shows the rows again. The notebook holds the working cell; the attempts
  are one click away (decision 18).
- **Outputs**, under the source, indented 12 px, in the order they came (§3.4).
  Until the first one arrives, a running cell shows *Waiting for output…* with a
  small loader.
- **Footer** (12 px, muted): at the left what the outputs need said (*5 of 1,284
  rows*); at the right the attempts when more than one, the duration and when it
  ran — *2 attempts · 640 ms · 14:06*.
- **Between cells**, a thin `+` line on hover inserts a cell there
  (`after_cell_id`).
- **Stale** cells keep their outputs at 45% opacity, the count at 60%, and a
  label row above the source in `warning` 12 px 500 — a triangle-alert, *stale —
  a cell above changed*, a muted `·`, *Run all* in `accent` — with the origin at
  the row's right end.
- The pane scrolls to follow a live run unless you scrolled away; a *Jump to
  running cell* pill brings you back.
- An empty notebook says, muted and centred: *Cells appear here as the analysis
  runs.*

### 2.6 Settings

A page of its own, not a dialog, reached from **Settings** — the gear, labelled,
at the bottom of the sidebar. The sidebar stays. The content area gets a **48 px
header** with a back arrow (a 32 px button, 20 px icon; tooltip *Back to the
conversation (Esc)*) and *Settings* in 600; under it, a side nav (200 px,
padding 16 / 8, 32 px items, the current one filled with `text` at 8% and set in
500, a `border` on its right) and the section on its right (padding 32 / 48), at
most **760 px** wide. The arrow and Escape go to the last conversation. Each
section has its own route, so it can be linked to.

| Section | Route | Holds |
| --- | --- | --- |
| General | `/settings/general` | the theme; per browser |
| Account | `/settings/account` | §2.7 |
| Models | `/settings/models` | §2.6.1 |

New sections join this nav as later phases need them (export, usage), never as
dialogs elsewhere. Each section is a title (`text-lg` 600) and one muted line of
what it is for, 32 px above its groups. A group is a 13 px 600 label over a
bordered box (radius 8) of rows; a row is a 200 px column with the label (500)
and its help (muted) on the left, 24 px of gap, and the control on the right;
rows are divided by a `border`.

**General** — *How not-a-notebook looks in this browser.* One group,
*Appearance*, one row, *Theme* (help: *Saved in this browser, not in your
account. System follows your operating system's light or dark setting.*): four
cards in a row — System, Light, Dark, Catppuccin Mocha. Each card is an 80 px
miniature of the screen painted in its theme's own colours (System split down
the middle, Light on the left and Dark on the right), a radio and the name under
it. The chosen card has a 2 px `accent` ring 3 px outside it and a filled radio.
Under the cards, one muted 12 px line with an info icon says the Mocha
trade-off of §5.4: *Catppuccin Mocha's chart colours are close in lightness, so
charts with five or more series are harder to tell apart with colour
blindness.*

#### 2.6.1 Models

*The models this instance offers and the ones you added. Each conversation
picks one in its header.* — and **Add model** (primary, plus icon) on the
title's right.

Laid out for 760 px, a bordered table (header row on `surface`, 13 px):

| Column | Shows |
| --- | --- |
| Name | the name (500), and **under it** its source: an *instance* badge (bordered, 12 px) for `environment`, *yours* muted for `user` |
| Adapter | *Anthropic*, *OpenAI (Responses)* or *OpenAI-compatible*, and under it the endpoint's host in mono 12 muted (`localhost:11434/v1`; the provider's own host when `base_url` is null) |
| Model · key | the model in mono, and **under it** the key — `…x9Qa` in mono muted, or *no key* in muted italics |
| Dialect | *Tool calling* or *Code blocks* |
| — | a 28 px **Test** button (flask icon); then a lock for instance models (tooltip *Set in the server's environment*) or a `⋯` menu (Edit, Delete) for yours |

A test's result goes **on its own line under the row**, the full table width,
so a failure message is never cramped: *✓ 4.8 s* in `success`, or *✗ the model
answered without calling the tool · 3.1 s* in `danger` with the time muted.
Under the table, a muted note with an info icon: *A test sends one short
question and checks that the model answers in its dialect. If a model keeps
answering without calling the tool, switch it to **Code blocks**.*

*Add model* (and Edit) open a dialog: name, adapter (three cards with one line
each on what they cover), base URL (required for OpenAI-compatible), model,
dialect (two cards: *Tool calling — for models that do it well*; *Code blocks —
for small and local models*), key (password field; on edit, *Leave empty to keep
the current key* and a *Remove key* link).

### 2.7 Account (a settings section)

*How you sign in to this instance.* Two groups:

- **Sign-in.** *Email* — a read-only 320 px field on `surface` with a lock (help:
  *You sign in with it. It can't be changed here.*). *Password* — help:
  *Changing it signs you out on every device, this one included.*; the current
  password (only when the account has one), the new one (*8 to 128 characters.*)
  and a secondary button, *Change password* or *Set password*. The warning is
  there before you submit.
- **Linked accounts** — the providers the account signs in with (`oauth` in
  `GET /account`), each a row with its mark and name and *Signed in with
  GitHub*. Read-only: linking and unlinking are not in the API yet (api.md,
  *What is not here yet*). The group is absent when there are none.

---

## 3. Components

### 3.1 Buttons

Primary (`accent` fill, `on-accent` text), secondary (outline: a `border`,
transparent fill), ghost (text), danger (red, only for deletion). Height 32 px
(28 compact in cell headers, tab strips and banners), radius 6, 13 px 500,
padding 0 / 12. Icon buttons are square, muted, with a tooltip always. A hovered
or selected neutral item is filled with `text` at 8%.

**Key chips** name a shortcut beside the thing it does (`⌘K`, `Esc`): JetBrains
Mono 12 px, muted, a `border`, radius 4, padding 0 / 4.

### 3.2 Kernel indicator

An 8 px dot, *Kernel* muted and the state in `text` 500, in the header:

| State | Dot | Tooltip |
| --- | --- | --- |
| ready | `success` | *Variables are in memory* |
| busy | `accent`, with a 4 px halo of `accent` at 22% | *A run is using the kernel* |
| starting | `text-muted`, pulsing | *Starting — a few seconds* |
| stopped | hollow, a 2 px `text-muted` ring | *The next run starts one — a few seconds* |

### 3.3 Cell status

| Status | Gutter bar | Execution count | Notes |
| --- | --- | --- | --- |
| `new` | none | `[ ]` | never ran |
| `running` | `accent`, fading downwards | `[*]` in `accent` | source on `accent-soft` with an `accent` border at 45% and a 2 px shimmer along its top edge; outputs stream in |
| `ok` | none (quiet is the default) | `[n]` | |
| `error` | `danger` | `[n]` | the error output is open |
| `cancelled` | grey | `[ ]` | *stopped by you* |
| stale | `warning`, dashed | `[n]` at 60% | outputs at 45%; the label row (§2.5) |

An attempt that ran past the execution timeout (`timed_out` in `attempt.finished`)
settles as an error that says so: *Stopped after 300 s — the time limit for one
cell.*

### 3.4 Outputs

| Kind | Rendering |
| --- | --- |
| `stream` stdout | monospace, plain, no box; consecutive chunks join |
| `stream` stderr | monospace, amber-tinted text — warnings are common and not errors |
| `error` | red left rule; the exception name and message in bold; the traceback collapsed to its last frames, *show all* expands |
| `table` | compact data table in a `border` box (radius 6), as wide as its content: header row on `surface`, 600, sticky; JetBrains Mono 13 / 20, cells padded 2 / 8, a `border` between rows; the index column muted; numbers right-aligned, `null` in muted italics; *100 of 12,480 rows* at the left of the cell's footer |
| `plotly` | the figure, full cell width, 300 px tall by default, rendered with the app's chart theme (§5.4) and resizable |
| `text` | monospace, like stdout |
| `image` | the PNG, max cell width, with a *matplotlib* caption — a hint that plotly is preferred |

### 3.5 Grounding badge

A pill under the answer: 24 px tall, radius 12, padding 0 / 8, 12 px 500, a
14 px icon. `success` on `success` at 13%, with a check, when every number was
found — *All 22 numbers come from the cells' output*; `warning` on `warning` at
13%, with a triangle, when any was not — *1 number not found in any output:
41%*. Clicking it lists the unfound ones and says what the check does and does
not prove (*it catches invented numbers, not code that silently drops rows*).

The badge stays with its answer: it comes from `grounding.checked` while the run
is live and is stored with the message, so a reloaded conversation shows it too
(the message's `grounding`, added to api.md with the chat).

### 3.6 Profile drawer

Slides in from the right **over the notebook pane**, which a `scrim` covers: 480
px wide, inset 8 px from the pane's top, right and bottom, `surface-raised`, a
`border`, radius 12, the overlay shadow.

- **Header** (padding 16 / 12 / 16 / 24, a `border` under it): a 20 px file icon,
  the name (`text-md` 600) and the close button; under them one muted 12 px line
  of facts — format, size, encoding, the sheets, *1,286 rows × 6 columns* — with
  *data looks to be on "Vendas"* when relevant.
- **Findings first** (the body's padding 16 / 24 / 24, sections 24 px apart): a
  heading — *Findings*, the count in `warning`, and at the right, muted, *The
  profile reports. It doesn't change the data.* — then a card per finding: a
  `border`, radius 8, padding 12; a 16 px icon in `warning` for its kind; the
  title (13 px 600) and, at the right, where it sits — *table*, *file* or the
  column's name — in mono 12 muted; the message in 13 px muted; and its rows as
  `accent` links (*rows 1–3*, *row 10*).
- **Values** inside a finding are mono chips on `surface` (radius 4, padding
  2 / 4) with their counts beside them (*"R$ 15,00" 812 rows*). Ambiguous values
  are shown both ways — *"1.250" → 1.25 or 1250*, *"03/04/2025" → 3 Apr 2025 or
  4 Mar 2025* — never resolved: the profile does not fix data.
- **Then the columns**, per table: a heading with the count, and a 12 px table —
  name, type, missing, distinct, samples (ellipsised) — in mono, a `border`
  between rows. A column with a finding carries a 12 px `warning` triangle by
  its name.

A finding sits at the level it belongs to — the file (data not on the first
sheet), a table (header not on the first row, subtotal rows, duplicates,
contradicting columns) or a column (number and date formats, inconsistent
labels, a dominating value, missing values). Each kind has its icon:

| Kind | Icon |
| --- | --- |
| `data_not_on_first_sheet` | sheet |
| `header_not_on_first_row` | rows-3 |
| `subtotal_rows` | sigma |
| `exact_duplicates` | copy |
| `number_formats` | hash |
| `date_formats` | calendar |
| `inconsistent_labels` | case-sensitive |
| `contradicting_columns` | equal-not |
| `dominating_value` | chart-pie |
| `missing_values` | circle-dashed |

### 3.7 Banners

A bar at the top of the notebook pane, under its tab strip, one at a time: at
least 40 px, `surface`, a `border` under it, padding 4 / 12 / 4 / 16, 13 px — a
16 px icon, the news in 500, what it means muted, and the action as a 28 px
button at the right.

- **Kernel restarted** (rotate-ccw, `role="status"`) — *The kernel restarted
  (idle for 15 min). Variables are gone; outputs are kept.* — with **Run all**,
  primary: it is what to do next. The reason comes from `kernel.restarted`
  (idle · died · requested · run_all · lost), which arrives only at the start of
  the next run: a reaped kernel announces nothing when it goes. So a page that
  opens on a stopped kernel whose cells had run says it without a reason — *The
  kernel stopped. Variables are gone; outputs are kept.* — with the same **Run
  all**, and the reason appears when the event does.
- **Stale cells** (triangle-alert in `warning`) — *1 cell is stale. A cell above
  it changed after it ran.* — with **Run all**, secondary.
- **No model** — *Pick a model to ask questions.* — with the picker.

### 3.8 Toasts

Bottom-right, for what happened elsewhere or failed quietly: a file too large, a
name already taken, a provider unavailable. Never for success that is already
visible.

---

## 4. The stream, on screen

One live run per conversation; the client attaches to `active_run_id` when the
page opens mid-run, and resumes with `Last-Event-ID` when the connection drops —
a *Reconnecting…* line in the activity area while it does.

| Event | What changes |
| --- | --- |
| `run.started` | composer → Stop; kernel indicator → busy; activity line appears |
| `kernel.starting` / `kernel.ready` | activity: *Starting the kernel…* (cold start, seconds) |
| `kernel.restarted` | the banner (§3.7) and the divider line in the chat (§2.4) |
| `file.uploaded` | the file chip appears, profile pending |
| `file.profiled` | the chip's badge settles; the *added* line in the chat, with the findings count |
| `llm.started` | activity: *Thinking…* |
| `llm.delta` | text streams into the analyst's message |
| `llm.finished` | — (the next event says what follows) |
| `code.proposed` | attempt 1: activity *Writing cell n*; attempt > 1: *Retrying cell n (attempt k)* |
| `cell.created` | the cell appears at the bottom of the notebook, running |
| `attempt.started` | attempt > 1: the failed attempt folds into a collapsed row in the cell (§2.5), and the activity line's second line names its error; the cell's source is replaced by the attempt's code; outputs cleared |
| `cell.output` | the output is appended to its cell |
| `attempt.finished` | — |
| `cell.finished` | the cell's status settles (§3.3) |
| `cells.stale` | those cells turn stale |
| `answer` | the streamed text is replaced by the settled message |
| `grounding.checked` | the grounding badge |
| `question` | the message styled as a question; composer focused |
| `run.error` | an inline error in the chat (§6) |
| `run.finished` | composer → send; kernel → ready; activity line gone; a `seq` gap shows *Some updates were lost — reload* |

---

## 5. Visual system

### 5.1 Type

| Token | Size / line height | Use |
| --- | --- | --- |
| `text-xs` | 12 / 16 | labels, badges, footers |
| `text-sm` | 13 / 20 | tables, cell headers, sidebar |
| `text-base` | 14 / 22 | body, chat |
| `text-md` | 16 / 24 | dialog titles, the answer's lead line |
| `text-lg` | 20 / 28 | page titles |
| `text-xl` | 24 / 32 | the sign-in title and the home headline |

- **UI**: Inter, weights 400 / 500 / 600.
- **Code, outputs, tables**: JetBrains Mono, 400 / 600, 13 px.
- **The wordmark** is `not-a-notebook` in JetBrains Mono 600, 13 px, lowercase,
  after a 12 px square outlined in `text` (2 px, radius 3).
- **Both fonts ship with the app.** A self-hosted instance may run with no
  internet; no font is fetched from a CDN.
- Numbers in tables use tabular figures.

### 5.2 Spacing and shape

- **Spacing scale** (4 px base): 0 · 2 · 4 · 8 · 12 · 16 · 24 · 32 · 48. Nothing in
  between.
- **Radius**: 4 (badges, inputs inside cells) · 6 (buttons, inputs) · 8 (cells,
  cards) · 12 (dialogs, drawer).
- **Borders**: 1 px, the border token; never shadows for structure. One shadow
  level, for overlays (menus, dialogs, drawer).

### 5.3 Colour

Neutrals carry the interface; one accent marks what is live or chosen; semantic
colours mark state. Tokens, light / dark:

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `bg` | `#FFFFFF` | `#0B0D10` | page |
| `surface` | `#F7F7F8` | `#121418` | sidebar, your messages, code background |
| `surface-raised` | `#FFFFFF` | `#181B20` | cells, cards, dialogs |
| `border` | `#E4E4E7` | `#26292F` | lines |
| `text` | `#18181B` | `#E7E7EA` | body |
| `text-muted` | `#6B6B74` | `#9A9AA3` | secondary, footers |
| `accent` | `#0E7490` | `#22B8CF` | primary actions, live state, focus ring |
| `accent-soft` | `#ECFEFF` | `#0E2A30` | selected rows, running cell tint |
| `success` | `#15803D` | `#4ADE80` | ok, grounding found |
| `warning` | `#B45309` | `#FBBF24` | findings, stale, stderr, unfound numbers |
| `danger` | `#B91C1C` | `#F87171` | errors, deletion |
| `on-accent` | `#FFFFFF` | `#0B0D10` | text and icons on an `accent` fill |
| `shadow` | `0 12px 32px rgba(24,24,27,.12), 0 2px 6px rgba(24,24,27,.06)` | `0 12px 32px rgba(0,0,0,.5), 0 2px 6px rgba(0,0,0,.3)` | the one overlay shadow |
| `scrim` | `rgba(24,24,27,.14)` | `rgba(0,0,0,.4)` | behind the drawer and dialogs |

Tints are mixes of a token, not new colours: `text` at 8% for a hovered or
selected neutral item, `text` at 12% for the avatar, `warning` at 14% and
`success` at 13% for badges, `accent-soft` at 55% and 85% for drop targets.

The accent is a deep teal: calm, technical, distinct from the blue every SaaS uses
and from the green and red that already mean ok and error. Every text pair meets
WCAG AA (4.5:1) on its background; state is never colour alone — a word or an
icon goes with it.

#### Syntax

Code is highlighted with five tokens per theme. In Light and Dark: keywords
violet, strings ochre, numbers orange, function names in the accent colour,
comments grey.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `syntax-keyword` | `#6D28D9` | `#C4B5FD` | `import`, `as`, `True`, `False`, `None`, … |
| `syntax-string` | `#A16207` | `#E9C46A` | strings, f-string text |
| `syntax-number` | `#C2410C` | `#FB923C` | numbers |
| `syntax-function` | `#0E7490` | `#22B8CF` | called names, builtins |
| `syntax-comment` | `#6B6B74` | `#8A8E97` | comments |

Everything else is `text`. The mockups drew comments lighter (`#8A8A93`,
`#6E727B`); those fall under 4.5:1 on `surface`, and a comment carries meaning
(`# header on row 4`), so they were darkened until they pass on `surface` and on
a running cell's `accent-soft`.

#### Themes

Three themes, picked in Settings → General and remembered per browser: **Light**,
**Dark** and **Catppuccin Mocha** — plus **System**, the default, which follows the
operating system to Light or Dark. A theme is one block of the tokens above and
nothing else: components never name a colour, so a theme cannot be half-applied.

**Catppuccin Mocha** is the dark theme in Catppuccin's palette, for those who already
live in it. Its tokens are taken from the palette's named colours, never invented
between them, with one exception (`accent-soft`, a blend):

| Token | Mocha | Palette name |
| --- | --- | --- |
| `bg` | `#1E1E2E` | base |
| `surface` | `#181825` | mantle |
| `surface-raised` | `#1E1E2E` | base — cells and cards stand out by their border, not their fill |
| `border` | `#313244` | surface0 |
| `text` | `#CDD6F4` | text |
| `text-muted` | `#A6ADC8` | subtext0 |
| `accent` | `#CBA6F7` | mauve — the palette's signature accent |
| `accent-soft` | `#332E46` | mauve at 12% over base |
| `success` | `#A6E3A1` | green |
| `warning` | `#F9E2AF` | yellow |
| `danger` | `#F38BA8` | red |
| `on-accent` | `#11111B` | crust — text on an accent fill, as the palette does |
| `shadow` | `0 12px 32px rgba(17,17,27,.55), 0 2px 6px rgba(17,17,27,.35)` | crust, as shadow |
| `scrim` | `rgba(17,17,27,.45)` | crust, as scrim |

Code is highlighted with Catppuccin's own syntax mapping, so a cell reads like the
editor its users already have:

| Token | Mocha | Palette name |
| --- | --- | --- |
| `syntax-keyword` | `#CBA6F7` | mauve |
| `syntax-string` | `#A6E3A1` | green |
| `syntax-number` | `#FAB387` | peach |
| `syntax-function` | `#89B4FA` | blue |
| `syntax-comment` | `#9399B2` | overlay2 |

### 5.4 Charts

Charts come from the kernel as Plotly specs and are restyled by the client, so a
chart always matches the app, in both modes (decision: charts are a spec, never a
picture).

- **Template** applied over every figure: transparent backgrounds; the title in
  Inter 13 px 500, `text`, aligned with the plot area; Inter 12 px `text-muted`
  for tick and axis labels; `border` for gridlines (horizontal only on bar
  charts) and a `text-muted` baseline; bars with 2 px rounded tops; no chart
  border; legend on top when there is more than one series.
- **Categorical palette** — eight colours, distinguishable with colour blindness,
  each with a light and a dark variant (the same eight across both modes, tuned
  for contrast):

  | # | Light | Dark |
  | --- | --- | --- |
  | 1 | `#0E7490` | `#22B8CF` |
  | 2 | `#C2410C` | `#FB923C` |
  | 3 | `#6D28D9` | `#A78BFA` |
  | 4 | `#15803D` | `#4ADE80` |
  | 5 | `#B91C1C` | `#F87171` |
  | 6 | `#A16207` | `#FACC15` |
  | 7 | `#BE185D` | `#F472B6` |
  | 8 | `#475569` | `#94A3B8` |

- **Sequential** scale for heatmaps: from `surface` to `accent`. **Diverging**: from
  `danger` through neutral to `accent`.
- Colours the code set explicitly are kept — the model or the user chose them.
- **In Catppuccin Mocha**, the chart palette is the palette's own accents, ordered
  so the most distinguishable pairs come first: blue `#89B4FA`, peach `#FAB387`,
  green `#A6E3A1`, red `#F38BA8`, mauve `#CBA6F7`, yellow `#F9E2AF`, teal
  `#94E2D5`, pink `#F5C2E7`. Its pastels sit close in lightness, so it is weaker for
  colour blindness than the default palette from the fifth series on — the
  trade-off of choosing the theme, said in a line under the theme cards in
  Settings → General. Sequential runs from base to
  mauve; diverging from red through overlay0 to blue. Gridlines are surface0, axes
  subtext0.

### 5.5 Motion

Short and functional: 120 ms for hover and focus, 200 ms for drawers and dialogs,
an indeterminate shimmer on running cells. Nothing animates on its own when idle.
`prefers-reduced-motion` turns the shimmer and transitions off.

### 5.6 Icons

Lucide (shadcn/ui's set), 16 px in dense places, 20 px in the header. One stroke
width.

---

## 6. Words

UI copy is English (decision 14); the analyst answers in the user's language.
Short, plain, no exclamation marks, no blame. The error codes of api.md and
events.md map to sentences:

| Code | What the person reads |
| --- | --- |
| `INVALID_CREDENTIALS` | Wrong email or password. |
| `REGISTRATION_CLOSED` | This instance isn't accepting new accounts. |
| `EMAIL_ALREADY_REGISTERED` | That email already has an account. Sign in with its password. |
| `OAUTH_FAILED` | Signing in with {provider} didn't complete. Try again. |
| `NO_MODEL_SELECTED` | Pick a model for this conversation first. |
| `CONVERSATION_BUSY` | Something is already running here. Wait for it, or stop it. |
| `FILE_ALREADY_EXISTS` | There's already a file named {name} here. |
| `FILE_TOO_LARGE` | That file is over this instance's limit. |
| `UNSUPPORTED_FILE_TYPE` | Only CSV, TSV, Excel and Parquet files can be added. |
| `MODEL_UNAVAILABLE` | The model's provider failed: {message} |
| `MODEL_REFUSED` | The model declined to answer this. |
| `STEP_LIMIT` | The analyst kept running code without reaching an answer, and was stopped. |
| `SANDBOX_UNAVAILABLE` | The kernel couldn't start. Try again in a moment. |
| `MODEL_MANAGED_BY_ENVIRONMENT` | This model is set in the server's environment and can't be changed here. |
| `OAUTH_PROVIDER_NOT_ENABLED` | Signing in with {provider} isn't enabled on this instance. |
| `VALIDATION_ERROR` | shown on the field it names, not as a sentence |
| `UNAUTHENTICATED` | never shown: the client refreshes once, then goes to sign in |
| `*_NOT_FOUND` | a quiet page: *This conversation doesn't exist, or isn't yours.* |
| `INTERNAL_ERROR` | Something went wrong on our side. Reference: {request_id or error_id}. |

---

## 7. Keyboard

| Keys | Action |
| --- | --- |
| Enter | send (composer) · edit the focused cell (notebook) |
| Shift+Enter | new line (composer) · run the cell and move to the next (editing) |
| Ctrl/Cmd+Enter | run the cell and stay |
| Escape | leave the cell editor · close a drawer or dialog · stop a live run when the composer is focused |
| ↑ / ↓ | move between cells |
| A / B | add a cell above / below the focused one |
| D D | delete the focused cell (asks once) |
| Ctrl/Cmd+K | search conversations |
| Ctrl/Cmd+Shift+Enter | Run all |
| Ctrl/Cmd+Alt+\ | swap the chat and notebook panes |
| Ctrl/Cmd+, | Settings |

Shortcuts follow Jupyter's where Jupyter has one; a `?` overlay lists them.

---

## 8. Accessibility

- WCAG 2.2 AA: contrast (§5.3), visible focus (2 px accent ring, offset 2; a
  focused input also turns its border `accent`), targets 24 px minimum. The
  composers are the one exception to the ring: their focus is the caret (§2.3).
- Every icon button has an accessible name; status is never colour alone.
- The live run is announced politely: an `aria-live="polite"` region speaks the
  activity line changes and the settled answer, not every streamed chunk.
- Charts carry a text alternative from their title and trace names; tables are
  real `<table>` elements.
- Everything is reachable by keyboard; dialogs and the drawer trap focus and return
  it.

---

## 9. Sizes

| Width | Layout |
| --- | --- |
| ≥ 1280 px | sidebar + chat + notebook, the default |
| 960 – 1279 | sidebar collapsed to icons; chat and notebook side by side |
| 640 – 959 | one pane at a time: the two tabs become a Chat / Notebook switch; sidebar as a drawer |
| < 640 | reading and asking: chat, with cells shown inline under the answers that made them, collapsed; editing cells is desktop-only |

---

## 10. How it is built

Decided in PLAN (decision 13), repeated here so the design and the build read
together:

- **Vite + React + TypeScript**, strict (`strict`, `noUncheckedIndexedAccess`,
  `exactOptionalPropertyTypes`); a static build served by Caddy.
- **TanStack Router** (routes in §2) and **TanStack Query** (server state; the
  conversation screen is one query, `GET /conversations/{id}`, patched by events).
- **Tailwind** with the tokens above as its theme, each a CSS variable redefined per
  theme under `[data-theme]` — no colour, size or space is
  written outside the tokens — and **shadcn/ui** components copied into the repo.
- **CodeMirror 6** for cells; **plotly.js** (the partial bundle with the trace types
  the kernel emits) for charts.
- **The event stream** read with `fetch` and a small SSE parser, typed as one
  discriminated union on `type` with an exhaustive `switch` (CLAUDE.md).
- **Auth**: the access token in memory only; on load, `POST /auth/refresh` with the
  cookie decides whether the person is signed in.
- **To decide at the start of the build:** Biome or ESLint + Prettier.

---

## Appendix A — brief for mockups

A prompt to paste into a design tool, with this document attached:

> Design the web interface of **not-a-notebook**, a self-hosted AI data analyst
> that shows its work: chat on the surface, a real Jupyter-style notebook
> underneath. Users are data analysts and engineers who read code. Follow the
> attached design document — its layout, components, colours, type and spacing
> tokens are the spec; where it is silent, choose and say what you chose.
>
> Mock these, in light and dark mode, at 1440 × 900 — and screens 3 and 4 also in
> the Catppuccin Mocha theme the document specifies:
>
> 1. **Sign in**, with Google and GitHub buttons.
> 2. **Home**: the centred composer on its background (§2.3), one file attached
>    as a chip, and the same screen while a file is dragged over it.
> 3. **Conversation, mid-run**: a file chip with "4 findings"; the user asked
>    "Qual região faturou mais em 2025, e quanto?"; the analyst's activity line
>    reads "Retrying cell 3 (attempt 2)"; the notebook shows cell 1 (ok, stdout),
>    cell 2 (ok, a data table), and cell 3 running with its first attempt's
>    KeyError visible as a collapsed attempt.
> 4. **Conversation, finished**: the answer in Portuguese with a markdown table and
>    the list of what was cleaned, a green grounding badge "All 22 numbers come
>    from the cells' output", and a bar chart cell (four regions) under the table
>    cell. One cell further down marked **stale**.
> 5. **Profile drawer** open over the notebook for `relatorio.csv`: findings
>    first — header on row 4, a TOTAL row on row 10, numbers stored as text with
>    mixed formats ("R$ 15,00", "15,00"), ambiguous dates, "Sudeste"/"sudeste" —
>    then the columns.
> 6. **Kernel restarted** banner (idle for 15 min) with a Run all button.
> 7. **Settings → Models** (§2.6), the side nav showing General, Account and
>    Models; and **Settings → General** with the four theme cards. Models: one instance model (Claude, locked) and two of the
>    user's (a local Qwen in the code-block dialect, DeepSeek via OpenRouter),
>    with one inline test result passing and one failing.
>
> Keep the chrome neutral and thin: colour is for state and for charts. Dense like
> a code editor, not like a spreadsheet. Use realistic content, not lorem ipsum.

## Appendix B — decided on the mockups

What was left open for the mockups, and what they settled (4 Oct 2026):

- **The split is 40/60** (chat/notebook), and **files get no column of their
  own** — the files bar in the chat holds them, and a third column would squeeze
  both panes at 1440 px (§2.1).
- **The analyst's activity lives inside its message**, not in a strip above the
  composer: the work stays next to the words it explains (§2.4).
- **The accent stays deep teal** in Light and Dark; mauve in Catppuccin Mocha.
- **A failed attempt is a collapsed row inside its cell**, not a timeline in the
  chat: the failure stays with the code that replaced it (§2.5).

Along the way the mockups also fixed the syntax colours (§5.3), the 36 px tab
strip with maximise at its right (§2.1), the *Drop to swap panes* label and the
13 × 32 divider grip (§2.1), Settings' 48 px header with a back arrow and the
gear labelled *Settings* (§2.6), the Mocha trade-off as a line under the theme
cards (§2.6), the Models table laid out for 760 px (§2.6.1), the home's drop
outline and label (§2.3), Send enabled by a file alone and the composer's
caret-only focus (§2.3), and the wordmark (§5.1).
