"""Measure review quality per language against planted-bug ground truth.

Calls the REAL OpenAI API (costs a little; that's why this is not a pytest
test). Run from the project root:

    uv run python -m evals.run_eval                  # every sample, 3 runs each
    uv run python -m evals.run_eval --runs 5 --language go
    uv run python -m evals.run_eval --no-hint        # let the model infer the language
    uv run python -m evals.run_eval --set heldout    # the held-out samples (see samples.py)
    uv run python -m evals.run_eval --model gpt-4o --json out.json

What is measured, per sample and per language:
  detected   : an issue was reported on the exact line of a planted bug
  labelled   : ...AND its category is one we accept for that bug
  extras     : issues on lines that are NOT planted bugs (each needs a human look:
               either a legitimate extra finding or noise)
  near-miss  : an extra within 2 lines of a planted bug, i.e. probably the right
               problem attributed to the wrong line
Each sample runs several times because a single LLM run proves little.
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict

from openai import AsyncOpenAI

from app.config import settings
from app.services.review_service import ReviewService
from evals.samples import HELDOUT_SAMPLES, SAMPLES, Sample

CONCURRENCY = 4


async def run_once(service: ReviewService, sample: Sample, hint: bool) -> list[dict]:
    review = await service.review_code(sample.code, sample.language if hint else None)
    return [
        {
            "line": i.line_number,
            "severity": i.severity.value,
            "category": i.category.value,
            "description": i.description,
        }
        for i in review.issues
    ]


def score(sample: Sample, issues: list[dict]) -> dict:
    """Score one run's issues against the sample's planted bugs."""
    planted = {line: e for e in sample.expected for line in sample.lines_of(e)}
    detected, labelled, wrong_label = set(), set(), {}
    for issue in issues:
        expected = planted.get(issue["line"])
        if expected is None:
            continue
        detected.add(expected.id)
        if issue["category"] in expected.cats:
            labelled.add(expected.id)
        else:
            wrong_label[expected.id] = issue["category"]

    extras = [i for i in issues if i["line"] not in planted]
    near = [i for i in extras if i["line"] and any(abs(i["line"] - p) <= 2 for p in planted)]
    return {
        "detected": sorted(detected),
        "labelled": sorted(labelled),
        "wrong_label": wrong_label,
        "extras": extras,
        "near_misses": len(near),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--set", choices=["main", "heldout", "all"], default="main",
                        help="which sample set to run (default: main)")
    parser.add_argument("--language", help="only samples in this language")
    parser.add_argument("--no-hint", action="store_true", help="send language=None")
    parser.add_argument("--model", default=settings.openai_model)
    parser.add_argument("--json", help="write raw results here")
    args = parser.parse_args()

    logging.basicConfig(level=logging.ERROR)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    service = ReviewService(client, args.model)
    pool = {"main": SAMPLES, "heldout": HELDOUT_SAMPLES, "all": SAMPLES + HELDOUT_SAMPLES}[args.set]
    samples = [s for s in pool if not args.language or s.language == args.language]
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def job(sample: Sample, n: int):
        async with semaphore:
            try:
                return sample, n, await run_once(service, sample, hint=not args.no_hint)
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"  ! {sample.id} run {n}: {type(exc).__name__}: {exc}", file=sys.stderr)
                return sample, n, None

    results = await asyncio.gather(*(job(s, n) for s in samples for n in range(args.runs)))

    by_sample: dict[str, list[dict]] = defaultdict(list)
    raw = []
    for sample, n, issues in results:
        if issues is None:
            continue
        scored = score(sample, issues)
        by_sample[sample.id].append(scored)
        raw.append({"sample": sample.id, "run": n, "issues": issues, "score": scored})

    mode = "no language hint (model infers)" if args.no_hint else "language hint given"
    print(f"\nmodel={args.model}  runs/sample={args.runs}  mode={mode}\n")
    print(f"{'sample':<16}{'planted':>8}{'detected':>10}{'labelled':>10}{'extras/run':>12}{'near-miss/run':>15}")

    per_language: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0, 0, 0])  # planted, det, lab, extras, runs
    for sample in samples:
        runs = by_sample[sample.id]
        if not runs:
            continue
        planted = len(sample.expected) * len(runs)
        det = sum(len(r["detected"]) for r in runs)
        lab = sum(len(r["labelled"]) for r in runs)
        extras = sum(len(r["extras"]) for r in runs)
        near = sum(r["near_misses"] for r in runs)
        print(f"{sample.id:<16}{len(sample.expected):>8}{det:>7}/{planted:<3}{lab:>7}/{planted:<3}"
              f"{extras / len(runs):>12.1f}{near / len(runs):>15.1f}")
        agg = per_language[sample.language]
        agg[0] += planted
        agg[1] += det
        agg[2] += lab
        agg[3] += extras
        agg[4] += len(runs)

    print(f"\n{'language':<12}{'detected':>10}{'labelled':>10}{'extras/run':>12}")
    for language, (planted, det, lab, extras, runs) in per_language.items():
        print(f"{language:<12}{100 * det / planted:>9.0f}%{100 * lab / planted:>9.0f}%{extras / runs:>12.1f}")

    # Per-bug detail: which planted bugs are missed or mislabelled, and how often.
    print("\nPer-bug (detected/labelled out of runs) and any wrong labels seen:")
    for sample in samples:
        runs = by_sample[sample.id]
        for e in sample.expected:
            det = sum(e.id in r["detected"] for r in runs)
            lab = sum(e.id in r["labelled"] for r in runs)
            wrong = sorted({r["wrong_label"][e.id] for r in runs if e.id in r["wrong_label"]})
            flag = "" if det == len(runs) and lab == len(runs) else "   <--"
            print(f"  {sample.id:<15}{e.id:<22}{det}/{len(runs)}  {lab}/{len(runs)}"
                  f"{('  labelled as: ' + ','.join(wrong)) if wrong else ''}{flag}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(raw, fh, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
