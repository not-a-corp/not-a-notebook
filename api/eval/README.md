# The eval

Questions put to a running instance, in order, as a user would ask them; each answer
is scored against numbers worked out **without the model**, and each question's cost
is counted: cells, model calls, tokens.

| Verdict | Meaning |
| --- | --- |
| `right` | every number the case expects is in the answer, and the headline leads when the case names one |
| `wrong_warned` | something is missing, and the grounding check flagged a number |
| `wrong_silent` | something is missing and nothing was flagged — the one that matters; the exit code is 1 if any |
| `failed` | the run did not finish, or asked back |

A case also has limits (`max_cells`, `max_calls`); going over one is flagged
`OVER-CELLS` / `OVER-CALLS`, not a wrong answer: a question the notebook already
answers should cost no cell, and an open one should not cost thirty.

```bash
docker compose up -d --build --wait
docker compose run --rm --no-deps -v ./api/eval:/srv/eval \
  -e EVAL_EMAIL=you@example.com -e EVAL_PASSWORD=... api \
  python -m eval.run eval/cases/vendas_teste.json --model "My model" --repeat 3
```

`EVAL_ACCESS_TOKEN` stands in for the email and password. A model must be set up
first (Settings, or `.env`); it spends that model's key. One sample says little:
use `--repeat`.

`cases/vendas_teste.json` is a regression for the agent's economy, not the Phase 9
dataset — its file has errors planted by whoever wrote the test, which the plan
rules out as proof of anything else.
