"""Runs a suite against a running instance and prints what each question cost and got.

    docker compose run --rm --no-deps -v ./api/eval:/srv/eval \\
      -e EVAL_EMAIL=you@example.com -e EVAL_PASSWORD=... api \\
      python -m eval.run eval/cases/vendas_teste.json --model "My model" --repeat 3

The questions go in order in one conversation, as a user would ask them, so a
question the notebook already answers can cost no cell. `--repeat` runs the whole
conversation again, from nothing: one sample says little about a model.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from eval.cases import Case, Suite, load_suite
from eval.client import Api
from eval.scoring import Outcome, Score, score

RUN_SECONDS = 600


@dataclass(frozen=True)
class Result:
    repeat: int
    question: str
    status: str
    verdict: str
    cells: int
    calls: int
    tokens_in: int
    tokens_out: int
    seconds: float
    over_cells: bool
    over_calls: bool
    missing: list[float]
    unfound: list[str]
    answer: str


def settled(api: Api, run_id: str) -> str:
    status = api.wait(run_id, RUN_SECONDS)
    if status == "timed_out":
        return "failed"

    return status


def measure(api: Api, run_id: str, case: Case, repeat: int) -> Result:
    status = settled(api, run_id)
    events = api.events(run_id)

    cells = 0
    calls = 0
    answer = ""
    unfound: list[str] = []
    finished: dict[str, object] = {}

    for event in events:
        kind = event["type"]
        if kind == "cell.created":
            cells += 1
        elif kind == "llm.started":
            calls += 1
        elif kind in ("answer", "question"):
            answer = event["message"]["text"]
        elif kind == "grounding.checked":
            unfound = event["unfound"]
        elif kind == "run.finished":
            finished = event

    # A question the agent asked back ends the run awaiting the user: it is an
    # answer to nothing, and counts as a run that did not finish.
    if status == "awaiting_user":
        status = "asked_back"

    outcome = Outcome(status=status, cells=cells, calls=calls, answer=answer, unfound=unfound)
    scored: Score = score(case, outcome)

    return Result(
        repeat=repeat,
        question=case.question,
        status=status,
        verdict=scored.verdict,
        cells=cells,
        calls=calls,
        tokens_in=int(str(finished.get("tokens_in", 0))),
        tokens_out=int(str(finished.get("tokens_out", 0))),
        seconds=float(str(finished.get("wall_ms", 0))) / 1000,
        over_cells=scored.over_cells,
        over_calls=scored.over_calls,
        missing=scored.missing,
        unfound=unfound,
        answer=answer,
    )


def converse(api: Api, suite: Suite, model_id: str, repeat: int, keep: bool) -> list[Result]:
    conversation = api.create_conversation(f"eval {suite.file.stem} #{repeat}", model_id)

    profiled = api.upload(conversation, suite.file)
    settled(api, profiled)

    results = []
    for case in suite.cases:
        run_id = api.ask(conversation, case.question)
        results.append(measure(api, run_id, case, repeat))

    if not keep:
        api.delete_conversation(conversation)

    return results


def signed_in(base_url: str) -> Api:
    api = Api(base_url)

    token = os.environ.get("EVAL_ACCESS_TOKEN")
    if token is not None:
        api.use_token(token)
        return api

    email = os.environ["EVAL_EMAIL"]
    password = os.environ["EVAL_PASSWORD"]
    api.sign_in(email, password)

    return api


def report(results: list[Result]) -> None:
    print(f"{'#':>2} {'verdict':<13} {'cells':>5} {'calls':>5} {'tok in':>8} {'secs':>5}  question")

    for result in results:
        flags = ""
        if result.over_cells:
            flags += " OVER-CELLS"
        if result.over_calls:
            flags += " OVER-CALLS"

        print(
            f"{result.repeat:>2} {result.verdict:<13} {result.cells:>5} {result.calls:>5} "
            f"{result.tokens_in:>8} {result.seconds:>5.0f}  {result.question}{flags}"
        )
        if result.missing:
            print(f"   missing: {result.missing}")

    print()
    counts = Counter(result.verdict for result in results)
    for verdict in ("right", "wrong_warned", "wrong_silent", "failed"):
        print(f"{verdict:<13} {counts[verdict]:>3} of {len(results)}")

    for question in dict.fromkeys(result.question for result in results):
        cells = [result.cells for result in results if result.question == question]
        calls = [result.calls for result in results if result.question == question]
        print(
            f"median {statistics.median(cells):>4} cells {statistics.median(calls):>4} calls"
            f"  {question}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("--model", required=True, help="a model's name or id, as GET /models")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--keep", action="store_true", help="keep the conversations")
    parser.add_argument("--out", type=Path, help="write the results here, as JSON")
    arguments = parser.parse_args()

    base_url = os.environ.get("EVAL_BASE_URL", "http://api:8000/api/v1")
    api = signed_in(base_url)
    model_id = api.model_id(arguments.model)
    suite = load_suite(arguments.suite)

    def one(repeat: int) -> list[Result]:
        return converse(signed_in(base_url), suite, model_id, repeat, arguments.keep)

    with ThreadPoolExecutor(max_workers=arguments.repeat) as pool:
        batches = list(pool.map(one, range(1, arguments.repeat + 1)))

    results = [result for batch in batches for result in batch]
    report(results)

    if arguments.out is not None:
        arguments.out.write_text(
            json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    silent = sum(1 for result in results if result.verdict == "wrong_silent")
    if silent > 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
