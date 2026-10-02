#!/usr/bin/env python3
"""ab_score.py — score the AGENTS.md A/B (tools/ab_agents.sh). Not installed into game repos.

    ab_score.py DIR                 DIR holds <arm>-<model>-q<n>-r<k>.json (claude -p --output-format json)
    ab_score.py --self-test

Each answer (`result`) is scored by its question's regexes; the table gives passes, mean `total_cost_usd` and mean
`num_turns` per arm and model. Keep rule: with AGENTS.md scores at least as well as without, at no more than +20% cost.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import tempfile

# A compiler or assembler version stated as a fact: question 3 must not name one (each game pins its own).
TRIPLE = r"\b(?:gcc|cc1)[ -]?v?2\.\d|\b(?:m?aspsx)[ -]?v?2\.\d"
QUESTIONS = {
    1: ("How do I run tier 1 of this repository's tests? Answer in at most five lines.",
        [r"test_pipeline", r"PSXDECOMP_KIT"], []),
    2: ("Where does the Project Architect version that psxdecomp pins live? Name the file.",
        [r"compat\.toml"], []),
    3: ("Which compiler triple (compiler, assembler) does a game repository bootstrapped by psxdecomp use? Answer in "
        "at most five lines.",
        [r"\b1\.4\b", r"(?i)\b(?:its own|each game|per[- ]game|the game(?: repo(?:sitory)?)? pins)"], [TRIPLE]),
}
NAME = re.compile(r"^(with|without)-([\w.-]+)-q(\d+)-r(\d+)\.json$")
KEEP_COST = 1.20


def score(q: int, text: str) -> bool:
    must, must_not = QUESTIONS[q][1], QUESTIONS[q][2]
    return all(re.search(p, text) for p in must) and not any(re.search(p, text, re.I) for p in must_not)


def table(root: pathlib.Path) -> tuple[list[str], bool | None]:
    cells: dict[tuple[str, str], list[tuple[bool, float, int]]] = {}
    for f in sorted(root.glob("*.json")):
        m = NAME.match(f.name)
        if not m:
            continue
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            d = {}
        ok = score(int(m[3]), d.get("result") or "") and not d.get("is_error")
        cost, turns = float(d.get("total_cost_usd") or 0), int(d.get("num_turns") or 0)
        cells.setdefault((m[1], m[2]), []).append((ok, cost, turns))
    out = ["| Arm | Model | Score | Mean cost (USD) | Mean turns |", "|---|---|---|---|---|"]
    agg = {}
    for (arm, model), rows in sorted(cells.items()):
        n = len(rows)
        s, c, t = sum(r[0] for r in rows), sum(r[1] for r in rows) / n, sum(r[2] for r in rows) / n
        agg[(arm, model)] = (s / n, c)
        out.append("| %s | %s | %d/%d | %.4f | %.1f |" % (arm, model, s, n, c, t))
    models = sorted({m for _, m in agg})
    if not models or any((a, m) not in agg for a in ("with", "without") for m in models):
        return out, None
    keep = all(agg[("with", m)][0] >= agg[("without", m)][0] and
               agg[("with", m)][1] <= agg[("without", m)][1] * KEEP_COST for m in models)
    out.append("")
    out.append("AB %s (with >= without on score, cost <= +%d%%, per model)" % ("KEEP" if keep else "DROP",
                                                                               round((KEEP_COST - 1) * 100)))
    return out, keep


def self_test() -> int:
    good = {1: "Run `PSXDECOMP_KIT=/path pytest -q tests/test_pipeline.py`.", 2: "In compat.toml, [pa3] version.",
            3: "None is fixed: each game pins its own triple in its phase 1.4 (docs/ops/compiler-pin.md)."}
    bad = {1: "Run pytest.", 2: "In README.md.", 3: "It uses gcc 2.7.2 with aspsx 2.56; each game pins its own in 1.4."}
    ok = all(score(q, t) for q, t in good.items()) and not any(score(q, t) for q, t in bad.items())
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        for q in QUESTIONS:
            for arm, text, cost in (("with", good[q], 0.10), ("without", bad[q], 0.09)):
                (d / ("%s-opus-q%d-r1.json" % (arm, q))).write_text(json.dumps(
                    {"result": text, "total_cost_usd": cost, "num_turns": 2}))
        (d / "notes.json").write_text("{}")                                # ignored: not an arm file
        rows, keep = table(d)
        ok &= keep is True and "| with | opus | 3/3 | 0.1000 | 2.0 |" in rows
        (d / "with-opus-q1-r1.json").write_text(json.dumps({"result": good[1], "total_cost_usd": 0.5}))
        ok &= table(d)[1] is False                                         # +20% cost rule
    print("SELF-TEST %s ab_score" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--questions", action="store_true", help="print the questions, one per line (for the runner)")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.questions:
        for q, (text, _, _) in QUESTIONS.items():
            print("%d\t%s" % (q, text))
        return 0
    if not a.dir:
        ap.error("DIR is required")
    rows, keep = table(pathlib.Path(a.dir))
    print("\n".join(rows))
    return 0 if keep is not False else 1


if __name__ == "__main__":
    sys.exit(main())
