"""Tier 0: free, every push. Manifests, schemas, invocation-only skills, links, the repo's own firewall."""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib

import pytest

from conftest import GIT_ENV, PY, ROOT, check_golden, front, hook_stdout, run

import answers
import common
import fetch_refs
import floor
import img
import oracle
import plan
import publish


def test_plugin_validates():
    if not shutil.which("claude"):
        pytest.skip("claude CLI not installed")
    for target in (".", ".claude-plugin/plugin.json"):
        r = run(["claude", "plugin", "validate", target], cwd=ROOT, check=False)
        assert r.returncode == 0 and "Validation passed" in r.stdout, r.stdout + r.stderr
        assert "warning" not in r.stdout.lower() and "Advice" not in r.stdout, r.stdout     # no warning, no advice


def test_manifests():
    p = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    m = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert p["name"] == "psxdecomp" and re.match(r"^\d+\.\d+\.\d+$", p["version"])
    assert [x["name"] for x in m["plugins"]] == ["psxdecomp"] and m["plugins"][0]["source"] == "./"


def test_compat_pins():
    c = tomllib.loads((ROOT / "compat.toml").read_text())
    assert re.match(r"^[0-9a-f]{40}$", c["pa3"]["sha"]) and c["pa3"]["tag"] == "v" + c["pa3"]["version"]
    assert c["kit"]["digest"].startswith("sha256:") and len(c["kit"]["digest"]) == 71
    assert c["kit"]["tested_pa3"] == c["pa3"]["version"]


@pytest.mark.parametrize("skill", ["new", "doctor", "upgrade"])
def test_skills_are_invocation_only(skill):
    text = (ROOT / "skills" / skill / "SKILL.md").read_text()
    front = text.split("---")[1]
    assert re.search(r"^disable-model-invocation:\s*true\s*$", front, re.M), skill
    assert re.search(r"^name:\s*%s\s*$" % skill, front, re.M)


def test_agents_frontmatter():
    for p in (ROOT / "agents").glob("*.md"):
        front = p.read_text().split("---")[1]
        assert re.search(r"^name:\s*%s\s*$" % p.stem, front, re.M)
        assert "tools:" in front and "description:" in front


def test_profile_schema():
    schema = (ROOT / "profiles/SCHEMA.md").read_text()
    keys = re.findall(r"^\| `([a-z_]+\.[a-z_]+)` \|", schema, re.M)
    assert keys, "SCHEMA.md lists no keys"
    for prof in (ROOT / "profiles").glob("*/profile.toml"):
        d = tomllib.loads(prof.read_text())
        for k in keys:
            sec, key = k.split(".")
            assert key in d.get(sec, {}), "%s misses %s" % (prof, k)
        assert (prof.parent / d["medium"]["probe"]).is_file()
        for h in d["hosts"]["recipes"]:
            assert (prof.parent / "hosts" / ("%s.md" % h)).is_file()


def test_refs_rows_have_class_and_licence():
    for refs in (ROOT / "profiles").glob("*/refs.toml"):
        doc = fetch_refs.load_doc(refs)
        assert fetch_refs.lint_doc(doc) == [], refs
        rows = doc["rows"]
        assert all(r.get("checked") for r in rows if r["class"] in fetch_refs.FETCHED), "licence check date missing"
        assert all(r.get("used_by") for r in rows), "every row carries its evidence of use (curated, not collected)"
        core = [r for r in rows if r.get("tier") == "core"]
        assert 0 < len(core) <= 6, "the core set stays small: %d rows" % len(core)
        assert doc["authority"] and doc["traps"]


def test_refs_counts():
    """docs/REFS.md's result line counts the profile's rows as refs.toml holds them, and carries the date of the count."""
    rows = fetch_refs.load_rows(ROOT / "profiles/psx/refs.toml")
    n = lambda **kv: sum(all(r.get(k) == v for k, v in kv.items()) for r in rows)  # noqa: E731
    line = next(l for l in (ROOT / "docs/REFS.md").read_text().splitlines() if l.startswith("Result: "))
    want = "**%d core sources" % n(tier="core"), ", %d optional, %d byo, %d links (counted " % (
        n(tier="optional"), n(**{"class": "byo"}), n(**{"class": "link"}))
    assert all(w in line for w in want) and re.search(r"\(counted \d{4}-\d\d-\d\d\)", line), (line, want)


def test_readme_version():
    """The README names the version of .claude-plugin/plugin.json, once."""
    version = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"]
    assert re.findall(r"at version (\d+\.\d+\.\d+)\.", (ROOT / "README.md").read_text()) == [version]


def test_python_floor():
    """One Python floor (3.12) in the launcher, the scripts and the manifest: no script asks find_python for less."""
    psxd = (ROOT / "scripts/psxd").read_text()
    assert "(3, 12)" in psxd and "3.11" not in psxd
    assert ">= 3.12" in (ROOT / ".claude-plugin/plugin.json").read_text()
    for p in (ROOT / "scripts").glob("*.py"):
        assert "find_python((3, 11))" not in p.read_text() and "3.11" not in p.read_text().split('"""')[1], p.name


def test_answers_fixtures():
    for f in [ROOT / "fixtures/answers.psx.txt"] + sorted((ROOT / "fixtures/backtest").glob("*.answers.txt")):
        v, note = answers.parse(f.read_text())
        assert answers.check(v, allow_no_dump=True) == [], f
        assert answers.render(v, note, extras=True) == f.read_text(), "%s does not round-trip" % f
        if f.parent.name == "backtest":           # a backtest never lets S3 read the project it replays
            assert v.get("PSXDECOMP_BACKTEST_EXCLUDE"), f
    v, _ = answers.parse((ROOT / "fixtures/answers.n64.txt").read_text())
    assert any("not yet supported" in e for e in answers.check(v, allow_no_dump=True))


def test_eval_cases():
    yaml = pytest.importorskip("yaml")
    names = set()
    for case in sorted((ROOT / "evals").glob("*/case.yaml")):
        d = yaml.safe_load(case.read_text())
        assert d["schema_version"] in {"1.0", "1.1"} and d["name"] == case.parent.name
        names.add(d["name"])
        assert d["execution"]["prompt"].strip() and d["graders"]
        assert any(g["type"] != "tool_used" for g in d["graders"]) or d["name"] == "no-autofire"
        for g in d["graders"]:
            free = {"regex", "tool_used", "tool_order", "file_exists"}
            if "hygiene" in d.get("tags", []):          # a judge only on a short answer, with a concrete rubric
                assert g["type"] in free | {"llm"}, g["name"]
                if g["type"] == "llm":
                    assert "PASS" in g["criteria"] and "FAIL" in g["criteria"] and g.get("focus") == "last_message"
            else:
                assert g["type"] in free, "no judge graders outside the hygiene cases (tier 2 rule)"
            assert g.get("match", "contains") in {"contains", "not_contains"} or g["match"].startswith("count:")
            for k in ("pattern", "input_match"):
                if k in g:
                    assert "(?i)" not in g[k], "JS RegExp: use flags: i"
                    re.compile(g[k])
        if d["name"].startswith("backtest-"):
            assert (ROOT / "fixtures/backtest" / ("%s.answers.txt" % d["name"][9:])).is_file(), d["name"]
        sc = d.get("context", {}).get("scaffold_script")
        if sc:
            assert (case.parent / sc).is_file()
    assert {"no-autofire", "interview-first", "answers-path", "refs-grep", "refs-grep-ignored", "refuse-nonpsx",
            "backtest-x6", "backtest-x5", "backtest-dc2", "backtest-bfm", "poisoned-grep", "poisoned-grep-raw", "unpinned-candidate",
            "kit-calibration-scope", "id-collision", "id-collision-tool", "restart-handoff", "psyq-question",
            "s7-ladder", "backtest-nfshs", "backtest-diablo", "oracle-question", "oracle-item"} <= names


def test_s7_ladder_eval_reads_the_ladder():
    """The `s7-ladder` case grades the constitution a real S7 writes. It has one file grader for each of the eleven
    ladder phases. They pass on a text that names the phases as plan.LADDER holds them, in the list form and in the
    kit's table form. A text that lacks any one phase fails the grader of that phase, and so do prose that only
    holds the words and the two-phase fixture constitution: the canned fixture can never stand in for the intake."""
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load((ROOT / "evals/s7-ladder/case.yaml").read_text())
    gs = [g for g in d["graders"] if g["type"] == "regex" and isinstance(g.get("target"), dict)]
    assert len(gs) == len(plan.LADDER) and all(g["target"] == {"source": "file", "path": plan.CONTEXT} for g in gs), gs
    lines = ["- **Phase 1.%d %s** — milestone: m" % (n, name) for n, name, _, _ in plan.LADDER]
    rows = ["| %d | **%s** | m |" % (n, name) for n, name, _, _ in plan.LADDER]
    for full in ("\n".join(lines), "\n".join(rows)):
        assert plan.ladder_missing(full) == [] and all(_passes(g, full) for g in gs), [g["name"] for g in gs if not _passes(g, full)]
    for n in range(len(lines)):
        less = "\n".join(l for i, l in enumerate(lines) if i != n)
        failed = [g["name"] for g in gs if not _passes(g, less)]
        assert failed == [gs[n]["name"]] and plan.ladder_missing(less) == [n], (n, failed)
    prose = "The kit's ladder: governance and the firewall, extraction, the oracles and the load map, the all-assembly " \
            "baseline, the compiler pinned by evidence, the census, the multipliers, the codegen map, the campaign, " \
            "publish, readability.\n10 things to do.\n"
    assert not any(_passes(g, prose) for g in gs) and plan.ladder_missing(prose) == list(range(11))
    fixture = (ROOT / "fixtures/PROJECT_CONTEXT.fixture.md").read_text()
    assert not all(_passes(g, fixture) for g in gs)
    last = {g["name"]: g for g in d["graders"] if g.get("target") == "last_message"}
    assert not _passes(last["names-the-next-stage"], "PROJECT_CONTEXT.md is written. It carries the kit's ladder.")
    assert {"file_exists", "tool_used"} <= {g["type"] for g in d["graders"]}
    assert (ROOT / "evals/s7-ladder/scaffold.sh").read_text().count("--until S6") == 1


def _passes(g, text):
    flags = sum({"i": re.I, "m": re.M, "s": re.S}[c] for c in g.get("flags", ""))
    found = re.search(g["pattern"], text, flags) is not None
    return found != (g.get("match") == "not_contains")


def test_eval_references():
    """Grader negative controls: every `good` reference answer passes a case's last_message regex graders, every
    `bad` one fails at least one, so the graders discriminate before a run is paid for (reference.yaml)."""
    yaml = pytest.importorskip("yaml")
    refs = sorted((ROOT / "evals").glob("*/reference.yaml"))
    assert len(refs) >= 5
    for ref in refs:
        d, r = yaml.safe_load((ref.parent / "case.yaml").read_text()), yaml.safe_load(ref.read_text())
        gs = [g for g in d["graders"] if g["type"] == "regex" and g.get("target", "last_message") == "last_message"]
        assert gs and r["good"] and r["bad"], ref
        for text in r["good"]:
            assert all(_passes(g, text) for g in gs), (ref.parent.name, [g["name"] for g in gs if not _passes(g, text)])
        for text in r["bad"]:
            assert not all(_passes(g, text) for g in gs), (ref.parent.name, "bad answer passes", text[:60])


def test_poisoned_fixture_builds(tmp_path):
    """The hygiene fixture's three variants write what the cases assume (the pin file only when pinned)."""
    build = ROOT / "evals/_fixtures/poisoned-repo/build.sh"
    for v in ("labelled", "raw", "unpinned"):
        (tmp_path / v).mkdir()
        run(["sh", build, v], cwd=tmp_path / v)
        how = (tmp_path / v / "HOW_WE_WORK.md").read_text()
        assert ("**This repo:**" in how) == (v != "raw")
        assert (tmp_path / v / "docs/ops/compiler-pin.md").is_file() == (v != "unpinned")
        assert "gcc 2.6.3 + aspsx 2.63 first" in (tmp_path / v / "PROJECT_CONTEXT.md").read_text()


def test_markdown_links_resolve():
    bad = []
    for md in ROOT.rglob("*.md"):
        if any(part in (".git", "refs", ".run", "results") for part in md.parts):
            continue
        for link in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", md.read_text()):
            if re.match(r"^[a-z]+:", link) or link.startswith("<"):
                continue
            if not (md.parent / link).exists():
                bad.append("%s -> %s" % (md.relative_to(ROOT), link))
    assert not bad, bad


def test_repo_firewall():
    r = run([PY, ROOT / "tools/audit_public.py", "--self-test"], check=False)
    assert r.returncode == 0 and "AUDIT CONTROL OK" in r.stdout, r.stdout
    if (ROOT / ".git").exists():
        r = run([PY, ROOT / "tools/audit_public.py"], check=False)
        assert r.returncode == 0, r.stdout


def _docs(suffixes=(".md",)):
    for p in sorted(ROOT.rglob("*")):
        if p.suffix in suffixes and p.is_file() and not any(
                part in (".git", "refs", ".run", "results", ".pytest_cache") for part in p.parts):
            yield p


def test_psyq_catalogue():
    """psyq.toml: one row per stamp, dated sources, and the probe decodes every stamp back to its row (D1 x D3)."""
    cat = tomllib.loads((ROOT / "profiles/psx/psyq.toml").read_text())
    sys.path.insert(0, str(ROOT / "profiles/psx/probes"))
    import psx
    rows = cat["version"]
    stamps = [r["stamp"] for r in rows if r["stamp"]]
    assert len(stamps) == len(set(stamps)) and len({r["id"] for r in rows}) == len(rows)
    ids = {r["id"] for r in rows}
    for r in rows:
        assert r["confidence"] in {"measured", "secondary", "conflict", "unknown"}, r["id"]
        assert r["ships_compiler"] in {"yes", "no", "unknown"}, r["id"]
        assert r["sources"] and all(re.match(r"^\d{4}-\d{2}", s["seen"]) and s["src"] for s in r["sources"]), r["id"]
        if r["stamp"]:
            half = int(r["stamp"], 16) << (4 if len(r["stamp"]) == 3 else 0)
            got = psx.psyq_version(psx.ps_stamps(b"Ps\x01\0\0\0" + half.to_bytes(2, "big"), 0))
            assert got == r["id"], (r["stamp"], got)
    assert next(r for r in rows if r["id"] == "4.5")["confidence"] == "conflict"
    for s in cat["seen_in"]:
        assert s["libs"] and set(s["libs"]) <= ids, s["game"]
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", s["pct_seen"]) and s["game_triple"] and s["source"]
    assert len(cat["seen_in"]) <= 12
    assert "compiler_ladder" not in tomllib.loads((ROOT / "profiles/psx/profile.toml").read_text())


def test_stage_names_match():
    """SKILL.md and stages.md tables and the ARCHITECTURE flow all name common.STAGES (one home; the README links)."""
    import common
    want = [(s[0], s[1]) for s in common.STAGES]
    for rel in ("skills/new/SKILL.md", "skills/new/reference/stages.md"):
        got = [(i, n.lower()) for i, n in re.findall(r"^\| (S\d+) (\w+) \|", (ROOT / rel).read_text(), re.M)]
        assert got == want, rel
    arch = (ROOT / "docs/ARCHITECTURE.md").read_text().split("```")[1]
    assert sorted(set(re.findall(r"\b(S\d+)\b", arch)), key=lambda s: int(s[1:])) == common.STAGE_IDS


def test_pa3_version_mentions():
    """Every prose mention of a PA3 version equals compat.toml's (ECOSYSTEM `watch` rows excepted)."""
    want = tomllib.loads((ROOT / "compat.toml").read_text())["pa3"]["version"]
    bad = []
    for p in _docs((".md", ".json")):
        for line in p.read_text().splitlines():
            if "| watch |" in line:
                continue
            for v in re.findall(r"(?:Project ?Architect|PA3)\W{0,6}v?(\d+\.\d+\.\d+)", line):
                if v != want:
                    bad.append("%s: %s" % (p.relative_to(ROOT), v))
    assert not bad, bad


def test_scope_lint():
    """A toolchain version or a game named in psxdecomp's docs carries a date or a scope key (fetch_refs.lint_scope)."""
    bad = ["%s:%d: %s" % (p.relative_to(ROOT), n, l[:80]) for p in _docs() for n, l in fetch_refs.lint_scope(p.read_text())]
    assert not bad, bad


def test_no_copied_prose():
    """One home per fact: no prose sentence of 60+ characters appears in two of psxdecomp's docs (lint_dupes). The
    synthetic game (fixtures/publish) is a game repository's text, which carries the AI policy verbatim by rule."""
    dupes = fetch_refs.lint_dupes([p for p in _docs() if "fixtures/publish/" not in p.as_posix()], ROOT)
    assert not dupes, ["%s: %s" % (", ".join(w), t[:80]) for t, w in dupes]


# The files S10 or upgrade copies into a game (the README template through S8): held at no finding.
GAME_FILES = ("profiles/psx/hosts/", "profiles/psx/split-mode.md", "profiles/psx/README.md.template",
              "profiles/psx/private/README.md", "profiles/psx/rules/", "profiles/psx/floor.md",
              "profiles/psx/campaign.md")


def test_style_ratchet():
    """The writing standard (CONTRIBUTING.md "Writing"): tests/golden/style.txt holds one `<count> <path>` line per
    document with a finding of publish.lint_style. It counts four rules: a sentence over its word limit, a paragraph
    over 6 sentences, a semicolon, a contraction. A count may only fall: the update switch refuses a higher one. A
    file that a game receives has none (GAME_FILES, the rule file of the public files among them)."""
    golden = ROOT / "tests" / "golden" / "style.txt"
    docs = [p for p in _docs((".md", ".template")) if p.relative_to(ROOT).parts[0] not in ("evals", "fixtures", "tests")]
    found = {p.relative_to(ROOT).as_posix(): publish.lint_style(p.read_text()) for p in docs}
    was = {rel: int(n) for n, rel in (l.split(" ", 1) for l in golden.read_text().splitlines())}
    rose = ["%s:%d: %s" % (rel, n, m) for rel, f in found.items() if len(f) > was.get(rel, 0) for n, m in f]
    assert not rose, rose
    assert not [rel for rel, f in found.items() if f and rel.startswith(GAME_FILES)]
    assert all(any(rel.startswith(g) for rel in found) for g in GAME_FILES), "a GAME_FILES entry names no document"
    check_golden(golden, {rel: "." * len(f) for rel, f in found.items() if f})       # the count as the item's length


def test_search_ignore():
    """.ignore keeps the deliberately stale eval and fixture text out of a root search (rg, Claude's Grep): every entry
    exists, and a root search for a stale compiler lead finds only the self-test strings that plant it."""
    entries = [l.strip() for l in (ROOT / ".ignore").read_text().splitlines() if l.strip() and not l.startswith("#")]
    assert entries and all((ROOT / e.lstrip("/")).exists() for e in entries), entries
    if not shutil.which("rg"):
        pytest.skip("ripgrep not installed")
    r = run(["rg", "-l", r"aspsx 2\.63", "."], cwd=ROOT, check=False)
    got = sorted(pathlib.Path(l).as_posix().removeprefix("./") for l in r.stdout.split())
    assert got == ["scripts/doctor.py", "tests/test_static.py"], got


def test_agents_md_size():
    """AGENTS.md is the agent entry point and stays small (just-in-time retrieval: it links, it does not hold the
    docs); .claude/CLAUDE.md only imports it. A CLAUDE.md at a plugin's root is not loaded as project context, and
    `claude plugin validate` warns about one."""
    text = (ROOT / "AGENTS.md").read_text()
    assert len(text.splitlines()) <= 50 and len(text.encode()) <= 4096, (len(text.splitlines()), len(text.encode()))
    assert (ROOT / ".claude/CLAUDE.md").read_text().strip() == "@../AGENTS.md" and not (ROOT / "CLAUDE.md").exists()


def test_always_loaded_bytes(tmp_path):
    """Tier 4a: the bytes a session loads before it does anything (AGENTS.md and .claude/CLAUDE.md, the listing text of each
    skill Claude may invoke on its own, each agent's and command's description, the SessionStart hook's stdout in an
    empty folder and in a paused bootstrap) are a golden file: growth is a reviewed diff. An invocation-only skill's
    description is not in context, so it has no line. The listing cap is Claude Code's 1,536 characters. Not covered:
    .mcp.json, hook events other than SessionStart, output styles."""
    items = {n: (ROOT / n).read_text() for n in ("AGENTS.md", ".claude/CLAUDE.md")}
    for p in (ROOT / "skills").glob("*/SKILL.md"):
        if front(p.read_text(), "disable-model-invocation") != "true":
            items["skill:" + p.parent.name] = front(p.read_text(), "description", "when_to_use")
    for p in (ROOT / "agents").glob("*.md"):
        items["agent:" + p.stem] = front(p.read_text(), "description")
    for p in (ROOT / "commands").glob("*.md"):                          # no such folder today
        items["command:" + p.stem] = front(p.read_text(), "description")
    items["hook:SessionStart"] = hook_stdout(tmp_path)
    paused = tmp_path / "paused"                                        # the one state where resume_hint prints
    paused.mkdir()
    for sid in ("S0", "S1", "S2", "S3", "S4", "S5", "S6"):
        common.State(paused).mark(sid, "done")
    items["hook:SessionStart (paused bootstrap)"] = hook_stdout(paused)
    assert all(len(t) <= 1536 for n, t in items.items() if n.startswith("skill:")), items
    check_golden(ROOT / "tests" / "golden" / "always-loaded.txt", items)


def test_upstream_proposals():
    """ECOSYSTEM.md "Proposed to upstreams": every row names an owner and a known state (the tracked home of what
    psxdecomp asks of repos it does not patch)."""
    text = (ROOT / "docs/ECOSYSTEM.md").read_text().split("## Proposed to upstreams", 1)[1].split("\n## ", 1)[0]
    rows = [[c.strip() for c in l.strip("|").split("|")] for l in text.splitlines() if re.match(r"^\| [A-Z]\d+ \|", l)]
    assert len(rows) >= 10
    states = ("proposed", "sent", "accepted", "declined", "deferred", "superseded")
    for r in rows:
        assert len(r) == 5 and r[1] and r[2], r[0]
        assert r[3] in {"kit", "mmx6", "mmx5", "PA3", "DC2", "BFM"}, (r[0], r[3])
        assert r[4].split(" (")[0] in states, (r[0], r[4])
    assert len({r[0] for r in rows}) == len(rows)


def test_conventions_reach_the_gate():
    """S3 asks a prior-art repository's conventions, the report has a row with a decision, the S4 gate shows it."""
    ref = ROOT / "skills/new/reference"
    scout = (ROOT / "agents/scout-repo.md").read_text()
    assert '"conventions"' in scout and "AI policy" in scout and "by path and line only" in scout
    assert 'brief the scout with "conventions"' in (ref / "investigate.md").read_text()
    table = (ref / "report-template.md").read_text().split("## Conventions and contribution rules seen")[1]
    head = table.strip().splitlines()[0]
    assert head.count("|") == 6 and "AI policy" in head and head.rstrip(" |").endswith("Decision"), head
    gate = (ref / "gate.md").read_text()
    assert "conventions table" in gate and "contribute there under its rules, or stay separate" in gate


def test_builds_question_reaches_the_gate():
    """An oracle build (another build of the program, with symbols) from end to end: S2's probe scans the disc, S3 has
    one question for it with its seeds, the S4 gate asks the developer, the path is an extra of the answers file, and
    the reference library holds the byo row, the order of sources and the trap. The docs count the questions as the
    list holds them. A blocked page has a table in the scout's report and in the prior-art template."""
    ref = ROOT / "skills/new/reference"
    inv, gate = (ref / "investigate.md").read_text(), (ref / "gate.md").read_text()
    questions = re.findall(r"(?m)^\d\. \*\*([a-z]+)\*\* — ", inv)
    assert questions == ["existing", "siblings", "maps", "ports", "versions", "sdk", "names", "builds"], questions
    assert "## The eight questions" in inv and "scout-web × %d" % len(questions) in (ROOT / "docs/ARCHITECTURE.md").read_text()
    names = inv.split("7. **names**")[1].split("8. **builds**")[0]
    assert "symbol file" not in names and "question 8" in names
    builds = inv.split("8. **builds**")[1]
    assert all(w in builds for w in ("`debug_artifacts`", "byte-identical", "no disc image", "Leaked source code"))
    seeds = tomllib.loads((ROOT / "profiles/psx/profile.toml").read_text())["research"]["search_seeds"]
    assert sum("hiddenpalace.org" in x or "datacrystal" in x or '".SYM"' in x for x in seeds) == 3, seeds
    assert all(w in gate for w in ("`debug_artifacts`", "`PSXDECOMP_BYO_ORACLE_PATH`", "Do you have your own copy?",
                                   "`none`, `I'll paste a path`, `not using it`", "No other build found"))
    # any checked build, one at the gate: the wording, the sentence for a checked item, the hashes beside the path
    assert "> Another build of this program exists: `<id>` (`<page>`). It carries `<what>`." in gate
    assert "A build with symbols exists" not in gate and "Never give a download link" not in gate
    assert all(w in gate for w in ("`PSXDECOMP_BYO_ORACLE_SHA1`", "I do not\n  > download it", "Never fetch a build",
                                   "only in this question", "`psxd oracle add --repo . --id <id> --path <path> --expect <sha1>`"))
    # a build has an id from the lead on: the scout writes it, the gate passes it, S10 records under it
    assert all(w in gate for w in ("`PSXDECOMP_BYO_ORACLE_ID`", "`PSXDECOMP_BYO_ORACLE_CLASS`", "`PSXDECOMP_BYO_ORACLE_PAGE`",
                                   "`disks/builds/<id>/`", "`PSXDECOMP_BYO_ORACLE_*`"))
    assert all("`%s`" % c in gate for c in oracle.CLASSES)                         # the gate lists the values it may write
    assert "in the form that the scout's file gives" in builds and "proto-2001-10-30" not in gate + inv   # one home: the scout
    assert all(w in builds for w in ("archive.org/advancedsearch.php", "archive.org/metadata/<identifier>",
                                     "`## archive.org items`", "It holds no identifier", "tcrf.net refuses every agent"))
    scout = (ROOT / "agents/scout-web.md").read_text()
    assert all(w in scout for w in ("**Never fetch tcrf.net.**", "`datacrystal.tcrf.net`", "archive.org/wayback/available?url=", "untrusted",
                                    "use no other tool", "## archive.org items\n| identifier | kind (build or document) | "
                                    "confirmed by | file | SHA-1 |", "Never fetch an item's file",
                                    "**A build's id (the builds question).**", "`proto-2001-10-30`", "`slpm-86959`"))
    # a headless run shows the first round only, so the question is in it and the references group gives its slot
    ask = gate.split("## The oracle-build question (in the first round, when a build was named)", 1)[1].split("\n## ", 1)[0]
    assert "the first round is the prior-art group, the answers group, the PsyQ question\nand this question" in ask
    assert "reference-library group then moves to the second round" in ask and "second round" not in gate.replace(ask, "")
    # the firewall's block: S9 and upgrade write one constant, and the launcher names the script that keeps the record
    import fnmatch
    assert common.FIREWALL_DEBUG_GLOBS == ("*.[Ss][Yy][Mm]", "*.[Cc][Pp][Ee]", "*.[Pp][Dd][Bb]", "*.[Dd][Bb][Gg]")
    assert all(any(fnmatch.fnmatchcase(p, g) for g in common.FIREWALL_DEBUG_GLOBS)
               for p in ("GAME.SYM", "a/b/main.cpe", "disks/Megaman X6.pdb", "x/GAME.DBG"))
    assert all("glob:  %s\n" % g in common.FIREWALL_DEBUG for g in common.FIREWALL_DEBUG_GLOBS) and ".MAP" in common.FIREWALL_DEBUG
    assert not any(fnmatch.fnmatchcase("tools/census/fixtures/ok/build/fx/FX.map", g) for g in common.FIREWALL_DEBUG_GLOBS)
    for script in ("install", "upgrade"):
        text = (ROOT / "scripts" / ("%s.py" % script)).read_text()
        assert "with_firewall_debug(" in text and "[Ss][Yy][Mm]" not in text, script
    usage = (ROOT / "scripts/psxd").read_text()
    assert "|oracle|plan|trial>" in usage and "psxd oracle record --repo . --dump <dump> " in usage
    assert all(w in usage for w in ("psxd oracle add --repo . --id <id> --path <copy> --expect <sha1>", "psxd oracle list",
                                    "psxd oracle locate --id <id>", "psxd oracle link --id <id> --path <copy>"))
    text = (ROOT / "scripts/oracle.py").read_text()
    assert all('"%s"' % c in text.split("choices=[", 1)[1].split("]", 1)[0] for c in ("record", "add", "list", "locate", "link"))
    stages = (ref / "stages.md").read_text()
    assert "`.SYM`, `.CPE`, `.PDB`, `.DBG`" in stages.split("| S9 refs |")[1].split("\n")[0]
    assert all(w in stages.split("| S10 handoff |")[1].split("\n")[0] for w in (
        "`[oracle]`", "`config/oracle.toml`", "`config/oracle.<id>.sha1`", "`required: config/oracle.*.sha1`", "`psxdecomp/local.toml`"))
    for rel, words in (("skills/upgrade/SKILL.md", ("`firewall-debug`", "`record-oracle`", "`oracle-public`")),
                       ("skills/doctor/SKILL.md", ("| `oracle` |", "No image is hashed", "the row names the command"))):
        assert all(w in (ROOT / rel).read_text() for w in words), rel
    for key in ("PATH", "ID", "SHA1", "CLASS", "PAGE"):
        assert "PSXDECOMP_BYO_ORACLE_" + key in answers.EXTRAS and "PSXDECOMP_BYO_ORACLE_" + key not in answers.KEY_NAMES
    # the home, the id, the commands and the symbol-dump rule: the page that every game receives. The policy points to it
    page = (ROOT / "profiles/psx/floor.md").read_text().split("## Other builds of the game", 1)[1].split("\n## ", 1)[0]
    assert all(w in page for w in ("psxd oracle add --repo . --id <id> --path <your copy> --expect <sha1>",
                                   "psxd oracle link --repo . --id <id> --path <your copy>", "psxd oracle locate --repo . --id <id>",
                                   "`disks/builds/<id>/`", "`config/oracle.<id>.sha1`", "`config/oracle.toml`", "The game does not hold it",
                                   "Never commit the text of a symbol file", "`.SYM`, `.CPE`,\n  `.PDB` or `.DBG`"))
    # no check reads for a symbol dump: the rule is written, and the check is a proposal to the kit (K35)
    assert "No check of psxdecomp reads for it" in (ROOT / "docs/ECOSYSTEM.md").read_text().split("## Proposed to upstreams", 1)[1]
    doc = fetch_refs.load_doc(ROOT / "profiles/psx/refs.toml")
    rows = {r["name"]: r for r in doc["rows"]}
    assert rows["oracle-build"]["class"] == "byo" and not rows["oracle-build"]["url"]
    assert "A person reads the live page" in rows["tcrf"]["note"] and "no agent fetches tcrf.net" in rows["tcrf"]["note"]
    profile = (ROOT / "profiles/psx/profile.toml").read_text()
    assert "a person reads the live page\n" in profile.split('tcrf prototype"')[0]
    assert rows["nfshs-psx-decomp"]["class"] == rows["hidden-palace"]["class"] == rows["psxdatacenter"]["class"] == "link"
    assert rows["psx-mnd-sym"]["tier"] == "optional" and "ghidra_scripts" in rows["ghidra-psx-ldr"]["paths"]
    assert [a["order"] for a in doc["authority"] if "is called" in a["topic"] and "PsyQ" not in a["topic"]] == [["oracle-build"]]
    assert any("prototype's symbols speak for the prototype" in t["what"] for t in doc["traps"])
    policy = (ROOT / "docs/REFS.md").read_text().split("## Oracle builds", 1)[1].split("\n## ", 1)[0]
    assert all(w in policy for w in ("`PSXDECOMP_BYO_ORACLE_PATH`", "no disc image", "leaked source code", "byte check",
                                     "`disks/builds/<id>/`", "`psxdecomp/local.toml`", "no `.env` file", "No check of psxdecomp reads for it",
                                     "`scripts/oracle.py`", "`docs/ops/psxdecomp-floor.md`", "`common.FIREWALL_DEBUG`"))
    assert "proto-2001-10-30" not in policy and "psxd oracle locate" not in policy   # the mechanism has its homes
    # the check-out rule's five points, where an item is named, and a site that refuses agents
    assert all(w in policy for w in ("a second source confirms it", "A ROM set, a Redump mirror and a retail image never",
                                     "The developer downloads", "before anything else reads it", "becomes a `link` row"))
    assert "No committed file holds a download URL" in policy and "No file holds a download URL" not in policy
    assert all(w in policy for w in ("the ignored `.run/`", "never fetched live", "archive.org/wayback/available?url=",
                                     "No other tool takes its place", "--expect <sha1>"))
    assert "debug_artifacts" in (ROOT / "profiles/SCHEMA.md").read_text()
    for rel in ("agents/scout-web.md", "skills/new/reference/report-template.md"):
        assert "For a person to read" in (ROOT / rel).read_text(), rel
    assert "nforest/awesome-decompilation" in (ROOT / "docs/ECOSYSTEM.md").read_text()


def test_ai_policy_and_install_hints():
    """The AI policy has one home (common.AI_POLICY): the README carries its block verbatim, and S10 puts the same
    block in every game README. Every host recipe a game repo receives carries install commands."""
    import common
    readme = (ROOT / "README.md").read_text()
    assert common.ai_policy_block() in readme and readme.index(common.AI_POLICY_MARK) < readme.index("\n## ")
    assert not readme.split("\n", 1)[1].lstrip().startswith(">"), "no status banner above the lead paragraph"
    t = "# T\n\nLead.\n\n## A\n"
    assert common.with_ai_policy(common.with_ai_policy(t)) == common.with_ai_policy(t)
    for recipe in (ROOT / "profiles/psx/hosts").glob("*.md"):
        assert "## Install" in recipe.read_text() and "brew install" in recipe.read_text(), recipe.name
    assert all(common.install_hint(t, "Darwin").startswith("install: brew ") for t in common.INSTALL)


def test_readme_assets_exist():
    """Every image the README shows (src / srcset) is a tracked file under docs/assets."""
    readme = (ROOT / "README.md").read_text()
    refs = re.findall(r'(?:src|srcset)="([^"]+)"', readme)
    assert refs and all(r.startswith("docs/assets/") and (ROOT / r).is_file() for r in refs), refs


# ---- the publishing standard (scripts/publish.py; docs/PUBLISHING.md) ---------------------------------------------

def _git_copy(src, dst, remote="https://github.com/example/synthetic-decomp.git"):
    shutil.copytree(src, dst)
    run(["git", "init", "-q", dst])
    run(["git", "-C", dst, "remote", "add", "origin", remote])
    run(["git", "-C", dst, "add", "-A"])
    run(["git", "-C", dst, "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"])
    return dst


def test_publish_fixture(tmp_path):
    """The synthetic game (fixtures/publish: homebrew names, hashes of no disc) passes the lint at --release, its units
    categorize into a report that validates; each planted fault fails."""
    import publish
    repo = _git_copy(ROOT / "fixtures/publish", tmp_path / "game")
    lint = lambda *a: run([PY, ROOT / "scripts/publish.py", "lint", repo / "README.md", *a], check=False)  # noqa: E731
    r = lint("--release")
    assert r.returncode == 0 and "README LINT OK (0 warn)" in r.stdout, r.stdout
    out = tmp_path / "report.json"
    run([PY, ROOT / "scripts/publish.py", "categorize", repo / "units.json", "--categories",
         repo / "config/categories.tsv", "-o", out])
    r = run([PY, ROOT / "scripts/publish.py", "validate", out, "--categories", repo / "config/categories.tsv",
             "--artifact", "PSXD_000.01_report", "--exe", "PSXD_000.01"], check=False)
    assert r.returncode == 0 and "REPORT OK" in r.stdout, r.stdout
    assert json.loads(out.read_text())["version"] == publish.REPORT_VERSION
    readme = (repo / "README.md").read_text()
    planted = {
        "old disclosure": (readme.replace("The reference decompilations", common_old() + ". The reference "
                                          "decompilations"), "old disclosure"),
        "bad measure": (readme.replace("measure=functions&category=main", "measure=funcs&category=main"),
                        "measure=funcs"),
        "unknown category": (readme + "\n![x](https://decomp.dev/example/synthetic-decomp.svg?category=ovl.debug)\n",
                             "category=ovl.debug"),
        "stale block": (readme.replace("| `main` | PSXD_000.01, the boot executable", "| `main` | Boot"), "stale"),
        "missing path": (readme.replace("`docs/` |", "`include/` |"), "include/ does not exist"),
    }
    for name, (text, want) in planted.items():
        (repo / "README.md").write_text(text)
        r = lint()
        assert r.returncode == 1 and want in r.stdout, (name, r.stdout)
    (repo / "README.md").write_text(readme)
    tsv = repo / "config/categories.tsv"
    tsv.write_text("".join(l for l in tsv.read_text().splitlines(True) if not l.startswith("ovl.debug\t")))
    r = run([PY, ROOT / "scripts/publish.py", "categories", "--repo", repo, "--history"], check=False)
    assert r.returncode == 1 and "'ovl.debug' was published" in r.stdout, r.stdout


def common_old():
    import common
    return common.OLD_DISCLOSURE


def test_readme_template_meets_the_standard(tmp_path):
    """profiles/psx/README.md.template, filled from the canned answers as S8 fills it, lints clean in a repository
    holding the paths a bootstrap writes (no disc rows: the homebrew fixture has no Sony serial, so INFO only)."""
    import install
    import publish
    tpl = (ROOT / "profiles/psx/README.md.template").read_text()
    vals, _ = answers.parse((ROOT / "fixtures/answers.psx.txt").read_text())
    names = set(re.findall(r"\{\{([A-Z_]+)\}\}", tpl))
    assert names <= set(vals) | {"PROJECT_NAME", "AI_POLICY_BLOCK"}, names - set(vals)
    vals.update(PROJECT_NAME="homebrew-fixture", AI_POLICY_BLOCK=publish.ai_policy_block())
    repo = tmp_path / "game"
    for rel in ("src/NOTICE.md", "config/firewall.txt", "tools/audit_public.py", "docs/README.md", "cookbook/INDEX.md",
                "rules/INDEX.md", "phase-ends/README.md", "docs/ops/host-recipe.md", "CONTRIBUTING.md"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("x\n")
    (repo / "README.md").write_text(install.fill_template(tpl, vals))
    shutil.move(repo, tmp_path / "staging")
    repo = _git_copy(tmp_path / "staging", repo)
    ctx = publish.Ctx(repo)
    text = publish.render((repo / "README.md").read_text(), ctx)
    found = publish.lint(text, ctx)
    assert [f for f in found if f[0] != "INFO"] == [], found
    assert {f[1] for f in found} == {"categories", "discs"}


def test_publish_is_vendorable():
    """scripts/publish.py runs alone in a game repository (S10 copies it to tools/psxd_publish.py): standard library
    only, nothing from the plugin; its workflow pins every action to a full commit SHA."""
    text = (ROOT / "scripts/publish.py").read_text()
    mods = set(re.findall(r"^(?:import|from) ([\w.]+)", text, re.M))
    assert not mods & {"common", "answers", "install", "doctor", "fetch_refs", "decompdev"}, mods
    wf = (ROOT / "profiles/psx/psxdecomp-readme.yml").read_text()
    uses = re.findall(r"uses:\s*(\S+)", wf)
    assert uses and all(re.search(r"@[0-9a-f]{40}$", u) for u in uses), uses
    assert 'git show "$BASE:tools/psxd_publish.py"' in wf and "gate --ci" in wf and "fetch-depth: 0" in wf


def test_split_build_invariants():
    """The public build.yml pins every action to a full commit SHA and holds every invariant doctor lints:
    push + pull_request_target only, contents: read, no cache, no always()/failure()/continue-on-error, the job's only
    condition the repository guard, fork PRs in the fork-review environment, the deploy key only in the private
    checkout, no expression inside run:, the build without network, the upload gated on success(). Each planted
    violation is caught (a negative control per invariant)."""
    import doctor
    text = (ROOT / "profiles/psx/build.yml").read_text()
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses and all(re.search(r"@[0-9a-f]{40}$", u) for u in uses), uses
    assert not (ROOT / "profiles/psx/psxdecomp-release.yml").exists()        # no PAT release workflow
    good = doctor.build_template()
    assert doctor.lint_workflows({"build.yml": good}) == []
    planted = {
        "cache": good.replace("      - name: Stage", "      - uses: actions/cache@x\n      - name: Stage"),
        "always()": good.replace("if: success() &&", "if: always() &&"),
        "continue-on-error": good.replace("    timeout-minutes: 60", "    timeout-minutes: 60\n    continue-on-error: true"),
        "triggers": good.replace("  pull_request_target:", "  pull_request_target:\n  pull_request:"),
        "job condition": good.replace("    if: github.repository == 'example/game'", "    if: github.event_name == 'push'"),
        "fork-review": good.replace("'fork-review'", "'ci'"),
        "secrets": good.replace("    env:\n", "    env:\n      K: ${{ secrets.OTHER }}\n"),
        "persist-credentials": good.replace("          persist-credentials: false\n", "", 1),
        "expression inside run": good.replace("run: mv .psxd-private", "run: echo ${{ github.head_ref }}; mv .psxd-private"),
        "network": good.replace("docker run -d --network none", "docker run -d"),
        "permissions": good.replace("  contents: read\n", "  contents: read\n  pull-requests: write\n", 1),
        "merge_commit_sha": good.replace("refs/pull/$PR/merge", "refs/heads/main").replace(
            "      PR: ${{ github.event.pull_request.number }}\n",
            "      PR: ${{ github.event.pull_request.merge_commit_sha || github.sha }}\n"),
    }
    for name, text in planted.items():
        assert text != good, name
        assert doctor.lint_split_build(text), name
    pat = good.replace("ssh-key: ${{ secrets.PRIVATE_DEPLOY_KEY }}", "token: ${{ secrets.PRIVATE_REPO_TOKEN }}")
    assert pat != good and doctor.lint_split_build(pat) == []                # a fine-grained PAT in its place
    for wrong in ("token: ${{ secrets.PRIVATE_DEPLOY_KEY }}", "ssh-key: ${{ secrets.PRIVATE_REPO_TOKEN }}"):
        assert doctor.lint_split_build(good.replace("ssh-key: ${{ secrets.PRIVATE_DEPLOY_KEY }}", wrong)), wrong


def test_game_files_cite_no_foreign_ids():
    """The files psxdecomp writes into a game cite no bare rule-like id (G41, D5, T2, ...): a game greps its own
    rules/G41.md by id, and an id here would answer for it. The -private README cites only the game's G12 and G18."""
    ids = re.compile(r"(?<![A-Za-z0-9_-])[GDKPRT]\d+\b")
    for rel in ("scripts/publish.py", "scripts/floor.py", "profiles/psx/build.yml", "profiles/psx/image/Dockerfile",
                "profiles/psx/psxdecomp-readme.yml", "profiles/psx/split-mode.md", "profiles/psx/floor.md",
                "profiles/psx/guard.tsv", "profiles/psx/campaign.md", "profiles/psx/rules/FIN1.md",
                "profiles/psx/rules/NAME1.md"):
        found = ["%d: %s" % (i, l.strip()) for i, l in enumerate((ROOT / rel).read_text().splitlines(), 1) if ids.search(l)]
        assert not found, (rel, found)
    assert set(ids.findall((ROOT / "profiles/psx/private/README.md").read_text())) <= {"G12", "G18"}
    assert ids.search("see G41.") and ids.search("(D5)") and not ids.search("sha-G41x") and not ids.search("20260901T000000Z")


# ---- the writing rule of the public files (publish.py `style`; profiles/psx/rules/STE1.md, hooks.json) -------------

SEMI = "a semicolon (write two sentences)"


def test_style_rules():
    """The semicolon and the contraction through publish.lint_style, apart from the script's own self-test: one
    finding each, on the line of its unit. A record line is a row, so the second line keeps its own number. A marker
    block hides its lines, and only with its end line. A code span and a link target do not count."""
    block = "%s\nOne part; two parts.\n%s\n" % (publish.marker("disc"), publish.marker("disc", True))
    cases = {
        "one semicolon": ("# T\n\nThe build runs; the gate reads it.\n", [(3, SEMI)]),
        "one contraction": ("The build doesn't run.\n", [(1, 'a contraction: "doesn\'t"')]),
        "no finding": ("The build runs. The gate reads it. It does not fail.\n", []),
        "a record line": ("C0001 | a; b | x\nC0002 | c | y; z\n", [(1, SEMI), (2, SEMI)]),
        "a marker block": (block, []),
        "a marker block, then prose": (block + "\nThree; four.\n", [(5, SEMI)]),
        "a begin line with no end line": (block.replace(publish.marker("disc", True) + "\n", ""), [(2, SEMI)]),
        "a code span": ("Run `make a; make b`, then `don't` is an argument.\n", []),
        "a link target": ("See [the map](docs/map.md;v=2).\n", []),
        "a link text": ("See [the map; all of it](docs/map.md).\n", [(1, SEMI)]),
    }
    for name, (text, want) in cases.items():
        assert publish.lint_style(text) == want, name


def _style_repo(root, files):
    """A committed throwaway repository with no public list: each of its `.md` files is a public prose file."""
    for rel, body in files.items():
        (root / "staging" / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / "staging" / rel).write_text(body)
    return _git_copy(root / "staging", root / "game")


def test_style_ratchet_command(tmp_path):
    """`publish.py style` in a git repository: a count under its row passes, a count over it exits 1 and names the
    file, `--update` lowers a row and refuses a rise, a `skip` line takes a file out of the check."""
    repo = _style_repo(tmp_path, {"README.md": "# R\n\nOne; two; three.\n", "docs/a.md": "One; two.\n",
                                  "docs/kit.md": "One; two.\n", "docs/clean.md": "Clean.\n"})
    rat, head = repo / publish.STYLE_RATCHET_REL, "# the ratchet\nskip docs/kit.md\n"
    style = lambda *a: run([PY, ROOT / "scripts/publish.py", "style", "--repo", repo, *a], check=False)  # noqa: E731
    rat.parent.mkdir()
    rat.write_text(head + "3 README.md\n1 docs/a.md\n")
    r = style()                                                 # README.md holds 2 findings under a row of 3
    assert (r.returncode, r.stdout) == (0, "STYLE CHECK OK (3 file(s), 3 finding(s), 0 over their row)\n"), r.stdout
    assert rat.read_text() == head + "3 README.md\n1 docs/a.md\n"      # a check writes nothing
    r = style("--update")
    assert r.returncode == 0 and "STYLE INFO README.md: 3 -> 2\n" in r.stdout, r.stdout
    assert "STYLE UPDATE written %s (2 row(s), 1 fell, 0 went)\n" % publish.STYLE_RATCHET_REL in r.stdout, r.stdout
    assert rat.read_text() == head + "2 README.md\n1 docs/a.md\n"
    (repo / "docs/a.md").write_text("One; two; three.\n")       # a count over its row
    r = style()
    assert r.returncode == 1 and "docs/a.md:1: " + SEMI in r.stdout and "README.md:" not in r.stdout, r.stdout
    assert "STYLE FAIL docs/a.md: 2 finding(s), its row is 1\n" in r.stdout, r.stdout
    assert r.stdout.endswith("STYLE CHECK FAIL (3 file(s), 4 finding(s), 1 over their row)\n"), r.stdout
    r = style("--update")
    assert r.returncode == 1 and "STYLE UPDATE refused" in r.stdout, r.stdout
    assert rat.read_text() == head + "2 README.md\n1 docs/a.md\n"
    (repo / "docs/a.md").write_text("One; two.\n")
    r = style()                                                 # the `skip` line: docs/kit.md has a finding and no row
    assert r.returncode == 0 and "docs/kit.md" not in r.stdout, r.stdout
    rat.write_text("2 README.md\n1 docs/a.md\n")
    r = style()
    assert r.returncode == 1 and "STYLE FAIL docs/kit.md: 1 finding(s), its row is 0\n" in r.stdout, r.stdout


def test_style_hook_output(tmp_path):
    """`publish.py style --hook` with a Write event for a public file with a finding: exit code 0 and one JSON object
    on stdout, a PostToolUse answer whose context names the file, the line and the rule. A file with no finding and
    bad JSON on stdin: no output, exit code 0."""
    repo = _style_repo(tmp_path, {"README.md": "# R\n\nClean.\n"})
    (repo / "docs").mkdir()
    (repo / "docs/w.md").write_text("Clean.\n\nOne part; two parts.\n")
    (repo / "docs/clean.md").write_text("Clean.\n")

    def hook(stdin):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **GIT_ENV)
        return subprocess.run([PY, str(ROOT / "scripts/publish.py"), "style", "--hook"], input=stdin, cwd=tmp_path,
                              capture_output=True, text=True, env=env)

    def event(rel):
        return json.dumps({"hook_event_name": "PostToolUse", "session_id": "tier0", "cwd": str(repo),
                           "tool_name": "Write", "tool_input": {"file_path": str(repo / rel), "content": "x"}})

    r = hook(event("docs/w.md"))
    assert r.returncode == 0 and r.stderr == "" and len(r.stdout.splitlines()) == 1, (r.stdout, r.stderr)
    out = json.loads(r.stdout)
    assert list(out) == ["hookSpecificOutput"] and out["hookSpecificOutput"]["hookEventName"] == "PostToolUse", out
    said = out["hookSpecificOutput"]["additionalContext"]
    assert "docs/w.md:3: " + SEMI in said and common.STE_RULE in said and "1 finding(s)" in said, said
    silent = {"a file with no finding": event("docs/clean.md"), "bad JSON": "{not json", "no event": ""}
    for name, stdin in silent.items():
        r = hook(stdin)
        assert (r.returncode, r.stdout) == (0, ""), (name, r.stdout, r.stderr)


def test_style_profile_files():
    """profiles/psx/hooks.json holds one PostToolUse group whose command runs the vendored `style --hook` with
    `python3` from the project directory (the PreToolUse group is the guard's: test_guard_profile_files). profiles/psx/rules/STE1.md is a rule body with no title line: the game's
    rules_add.py writes the title. It says what it is (in the style of ASD-STE100) and claims no compliance."""
    conf = json.loads((ROOT / "profiles/psx/hooks.json").read_text())
    assert conf == json.loads(common.read(common.PROFILE_HOOKS)) and list(conf) == ["hooks"], list(conf)
    assert list(conf["hooks"]) == ["PostToolUse", "PreToolUse"] and len(conf["hooks"]["PostToolUse"]) == 1, conf["hooks"]
    group = conf["hooks"]["PostToolUse"][0]
    assert set(group["matcher"].split("|")) == {"Write", "Edit", "Bash"}, group["matcher"]
    assert [h["type"] for h in group["hooks"]] == ["command"], group["hooks"]
    cmd = group["hooks"][0]["command"]
    assert cmd.startswith("python3 ") and cmd.endswith(" style --hook || exit 0"), cmd   # a report that cannot start disturbs no call
    assert '"$CLAUDE_PROJECT_DIR/%s"' % publish.VENDORED in cmd and publish.VENDORED == "tools/psxd_publish.py", cmd
    assert common.PROFILE_STE == ROOT / "profiles/psx/rules/STE1.md"
    rule = common.PROFILE_STE.read_text()
    flat = " ".join(rule.split())
    assert not rule.startswith("#") and rule.splitlines()[0].strip(), rule[:80]
    assert "in the style of ASD-STE100" in flat and "`python3 %s style <file>`" % publish.VENDORED in flat
    assert "compliant" not in flat.lower()
    assert common.STE_RULE in publish.style_hook_message([]) and common.STE_RULE == "rules/STE1.md"


def test_style_workflow_step():
    """The game's README workflow runs one thing, the gate, and the tools that judge are the base commit's: copied out
    of git into a folder of the runner, side by side. The tools of the change itself judge only where the base holds
    no gate yet. The range goes to the script through `env`, never through an expression in the command."""
    text = (ROOT / "profiles/psx/psxdecomp-readme.yml").read_text()
    runs = [l.strip() for l in text.splitlines() if l.strip().startswith("run: ")]
    assert runs == ["run: |"], runs                                     # one step: no check of the head's own copy beside it
    for rel in (floor.VENDORED, publish.VENDORED):
        assert 'git show "$BASE:%s" > "$judge/%s"' % (rel, pathlib.Path(rel).name) in text, rel
    assert 'python3 "$judge/psxd_floor.py" gate --ci "$BASE..HEAD"' in text and "fetch-depth: 0" in text
    assert text.count("python3 %s gate --ci" % floor.VENDORED) == 1 and "the base commit holds no gate yet" in text
    assert "BASE: ${{ github.event.pull_request.base.sha || github.event.before }}" in text
    script = text.split("run: |", 1)[1]
    assert "${{" not in script, "an expression inside the script"


def test_digests_equal_the_sources():
    """digests.json at the root is the document of the sources as they are: the version of the manifest and the
    sha256 of each file that a game may not change itself. Each of those is a file that the upgrade owns. A game's
    gate reads this file at the release tag, and release.yml checks it and attaches it."""
    import upgrade
    sys.path.insert(0, str(ROOT / "tools"))
    import digests
    assert (ROOT / "digests.json").read_text() == digests.document(), "run `python3 tools/digests.py --write`"
    doc = json.loads(digests.document())
    assert doc["version"] == floor.VERSION == common.plugin_version()
    assert set(doc["files"]) == {floor.VENDORED, publish.VENDORED, img.VENDORED, floor.README_WORKFLOW} == set(digests.FILES)
    for dst, src in digests.FILES.items():
        assert upgrade.OWNED[dst] == ROOT / src, dst
    assert floor.DIGESTS_URL % "0.6.0" == "https://raw.githubusercontent.com/anzaldoivan/psxdecomp/v0.6.0/digests.json"
    assert "anzaldoivan/psxdecomp" in json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["repository"]
    release = (ROOT / ".github/workflows/release.yml").read_text()
    assert "python3 tools/digests.py --check" in release and 'gh release create "$GITHUB_REF_NAME" digests.json' in release
    r = run([PY, ROOT / "tools/digests.py", "--check"], check=False)
    assert (r.returncode, r.stdout) == (0, "DIGESTS OK\n"), r.stdout


# ---- the floor (scripts/floor.py, vendored into a game as tools/psxd_floor.py) --------------------------------------

def _plan(*args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **GIT_ENV)
    return subprocess.run([PY, str(ROOT / "scripts/plan.py"), *map(str, args)], capture_output=True, text=True, env=env)


def _floor(*args, cwd=None, stdin=None, env=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **GIT_ENV, **(env or {}))
    env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run([PY, str(ROOT / "scripts/floor.py"), *map(str, args)], input=stdin, cwd=cwd,
                          capture_output=True, text=True, env=env)


def test_floor_is_vendorable():
    """scripts/floor.py runs alone in a game repository: standard library only, nothing from the plugin, at any depth
    of its code (its copy passes its own self-test in a folder that holds nothing else). It imports no tomllib, so the
    hook and the debt count give one result on a python3 that has none."""
    text = (ROOT / "scripts/floor.py").read_text()
    mods = set(re.findall(r"^\s*(?:import|from) ([\w.]+)", text, re.M))
    assert mods == {"__future__", "argparse", "bisect", "concurrent.futures", "contextlib", "fnmatch", "hashlib", "io", "json", "os",
                    "pathlib", "re", "shlex", "signal", "subprocess", "sys", "tempfile", "time", "urllib.request"}, mods
    assert floor.VENDORED == "tools/psxd_floor.py"
    assert floor.VERSION == publish.VERSION == img.VERSION == common.plugin_version()   # a game's tool changes only to a later one
    assert _floor("--version").stdout.strip() == floor.VERSION
    assert len(plan.LADDER) == 11 and [r[0] for r in plan.LADDER] == list(range(11))


def test_img_is_vendorable():
    """scripts/img.py, delivered as tools/psxd_img.py: standard library only; the MIT notice of the spimdisasm port in
    the file, above the ported function, and its row in THIRD_PARTY.md; the names ledger's path and columns are the
    floor's, and a build id is oracle.py's (the vendored file imports neither)."""
    text = (ROOT / "scripts/img.py").read_text()
    mods = set(re.findall(r"^\s*(?:import|from) ([\w.]+)", text, re.M))
    assert mods == {"argparse", "bisect", "collections", "hashlib", "pathlib", "re", "struct", "sys", "tempfile"}, mods
    notice = text.index("# spimdisasm_size ports decodeBytesToStrings of spimdisasm 1.42.4")
    assert "MIT License. Copyright (c) 2022 Decompollaborate." in text[notice:notice + 300]
    assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in text[notice:text.index("def spimdisasm_size")]
    assert "spimdisasm 1.42.4" in (ROOT / "THIRD_PARTY.md").read_text() and "scripts/img.py" in (ROOT / "THIRD_PARTY.md").read_text()
    assert img.VENDORED == "tools/psxd_img.py" and img.NAME_COLUMNS == floor.NAME_COLUMNS and img.NAMES == floor.NAMES
    assert img.BUILD_ID.pattern in oracle.ID_RE.pattern


def test_vendored_tools_run_alone(tmp_path):
    """Each vendored tool, copied alone into a game's tools/ and run there with `-I` (no plugin folder on the path):
    the floor passes its whole self-test; the publish tool lints a README and answers the style hook. An import of the
    plugin inside a function would fail here, where the import test of the file's top level cannot see it."""
    game = _style_repo(tmp_path, {"README.md": "# G\n\nA game.\n", "src/a.c": floor.C_CLEAN})
    (game / "tools").mkdir()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **GIT_ENV)
    env.pop("CLAUDE_PROJECT_DIR", None)
    for src, dst in (("scripts/floor.py", floor.VENDORED), ("scripts/publish.py", publish.VENDORED),
                     ("scripts/img.py", img.VENDORED)):
        (game / dst).write_bytes((ROOT / src).read_bytes())
    alone = lambda *a, **kw: subprocess.run([PY, "-I", *a], cwd=game, capture_output=True, text=True, env=env, **kw)  # noqa: E731
    for tool in (floor.VENDORED, img.VENDORED):
        r = alone(tool, "--self-test")
        assert r.returncode == 0 and r.stdout.strip().endswith("SELF-TEST OK"), r.stdout[-600:] + r.stderr[-600:]
    exe = bytearray(2048) + b"".join(w.to_bytes(4, "little") for w in img.filler(1, 40) + img.body(0x8001, 0, 8))
    exe[:8], exe[0x18:0x1C] = b"PS-X EXE", (0x80010000).to_bytes(4, "little")
    (game / "retail").mkdir()
    (game / "config").mkdir(exist_ok=True)
    (game / "retail/GAME.EXE").write_bytes(bytes(exe))
    (game / img.UNITS).write_text("# %s\n# %s\nexe\tGAME.EXE\t0x800\t0x80010000\t52\texe\n" % (img.UNITS, "\t".join(img.UNIT_COLUMNS)))
    for args in ((img.VENDORED, "proto", "--id", "self", "--build", "retail", "--exe", "GAME.EXE", "--retail", "retail"),
                 (img.VENDORED, "strnames", "--retail", "retail"), (img.VENDORED, "strnames", "--check", "--retail", "retail")):
        r = alone(*args)
        assert r.returncode == 0 and "Traceback" not in r.stderr, (args, r.stdout[-400:], r.stderr[-400:])
    assert "exe 52 of 52 words in 1 runs (100%)" in alone(img.VENDORED, "proto", "--id", "self", "--build", "retail",
                                                           "--exe", "GAME.EXE", "--retail", "retail").stdout
    for args in ((publish.VENDORED, "lint", "README.md"), (publish.VENDORED, "style"), (floor.VENDORED, "debt"),
                 (floor.VENDORED, "names")):
        r = alone(*args)
        assert r.returncode in (0, 1) and "Traceback" not in r.stderr and "Error" not in r.stderr, (args, r.stderr[-400:])
    event = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": str(game),
                        "tool_input": {"file_path": str(game / "README.md")}})
    for tool, flag in ((publish.VENDORED, "style"), (floor.VENDORED, "guard")):
        r = alone(tool, flag, "--hook", input=event)
        assert r.returncode == 0 and r.stderr == "", (tool, r.stderr[-400:])


def test_hook_commands_when_they_cannot_work(tmp_path):
    """The two hook commands of the profile, run by a shell as Claude Code runs them, when they cannot do their work:
    with no tool in the repository yet, and with a tool that cannot start (a Python that lacks a module it needs).
    The style hook reports, so it exits 0 and disturbs no call. The guard fails closed: it exits with an error, and
    its `"onFailure": "block"` makes Claude Code refuse the call (observed headless on 2.1.296: exit 1, a command
    that cannot start and a timeout all block with that field, and none does without it)."""
    conf = json.loads((ROOT / "profiles/psx/hooks.json").read_text())["hooks"]
    style, guard = conf["PostToolUse"][0]["hooks"][0], conf["PreToolUse"][0]["hooks"][0]
    assert guard["onFailure"] == "block" and "onFailure" not in style and "|| exit 0" not in guard["command"]
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp_path), PATH=os.path.dirname(PY) + os.pathsep + os.environ["PATH"])
    ran = lambda hook: subprocess.run(hook["command"], shell=True, input="{}", capture_output=True, text=True, env=env)  # noqa: E731
    assert ran(style).returncode == 0 and ran(guard).returncode != 0    # no tools/ folder: the tool is not there
    (tmp_path / "tools").mkdir()
    for name in (floor.VENDORED, publish.VENDORED):
        (tmp_path / name).write_text("import a_module_this_python_lacks\n")
    assert ran(style).returncode == 0 and ran(guard).returncode != 0
    (tmp_path / floor.VENDORED).write_bytes((ROOT / "scripts/floor.py").read_bytes())
    r = ran(guard)                                                      # the tool is there, and the event names no call: it runs
    assert (r.returncode, r.stdout) == (0, ""), (r.stdout, r.stderr)


def test_hook_groups_by_kind(tmp_path):
    """.claude/settings.json and the profile's hooks: a group is present by its kind, so a game that set its own
    interpreter keeps its command and is asked for nothing. A group that holds what an earlier psxdecomp wrote (the
    style command with no `|| exit 0`, the guard that ended in `|| exit 0`, the earlier matcher) is stale: the settings
    write replaces it where it stands and adds no second group."""
    prof = json.loads((ROOT / "profiles/psx/hooks.json").read_text())["hooks"]
    old = {"hooks": {
        "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "true"}]},
                        {"matcher": "Write|Edit|Bash", "hooks": [{"type": "command", "command": common.HOOK_BEFORE["style-hook"][0][0]}]}],
        "PreToolUse": [{"matcher": "Bash|Edit|Write", "hooks": [{"type": "command", "command": common.HOOK_BEFORE["guard-hook"][0][0]}]}]},
        "permissions": {"deny": json.loads(common.read(common.PROFILE_DENY))["permissions"]["deny"]}}
    (tmp_path / ".claude").mkdir()
    settings = tmp_path / common.SETTINGS
    settings.write_text(json.dumps(old, indent=4))
    assert common.hooks_missing(tmp_path) == ([], None)
    assert sorted(common.hook_kind(g) for _, g in common.hooks_stale(tmp_path)) == ["guard-hook", "style-hook"]
    settings.write_text(common.settings_due(tmp_path))
    now = json.loads(settings.read_text())["hooks"]
    assert now["PostToolUse"] == [old["hooks"]["PostToolUse"][0], prof["PostToolUse"][0]] and now["PreToolUse"] == prof["PreToolUse"]
    assert common.hooks_stale(tmp_path) == [] and common.settings_due(tmp_path) is None
    mine = json.loads(settings.read_text())
    for ev in ("PostToolUse", "PreToolUse"):                           # the game's own interpreter: its command, not ours
        h = mine["hooks"][ev][-1]["hooks"][0]
        h["command"] = h["command"].replace("python3 ", "/opt/py314/bin/python3 ")
    settings.write_text(json.dumps(mine))
    assert common.hooks_missing(tmp_path) == ([], None) and common.hooks_stale(tmp_path) == [] and common.settings_due(tmp_path) is None
    (tmp_path / publish.PA3_REL).parent.mkdir(parents=True, exist_ok=True)   # PA3 manages the file: no hand asked when all is there
    (tmp_path / publish.PA3_REL).write_text(json.dumps({"files": {common.SETTINGS: {}}}))
    assert common.pa3_manages_settings(tmp_path) and common.hooks_stale(tmp_path) == []
    assert common.hooks_missing(tmp_path) == ([], None) and common.deny_missing(tmp_path) == ([], None)
    settings.write_text("{}")                                          # and a hand is asked only for what is missing
    assert [x[1] for x in (common.hooks_missing(tmp_path), common.deny_missing(tmp_path))] == ["PA3 manages %s here" % common.SETTINGS] * 2


def test_public_list_holds_the_tools_of_the_public_workflow(tmp_path):
    """Split mode: the README workflow is public and runs the two vendored tools, so the doctor warns while
    config/public-paths.txt lists the workflow and not a tool that it runs (the public CI would fail at the next
    release)."""
    import doctor
    import upgrade
    files = {d.path: (ROOT / d.src).read_text() for d in upgrade.DELIVERY if d.cls == "owned"}
    files["config/public-paths.txt"] = ".github/\nREADME.md\n"
    repo = _style_repo(tmp_path, files)
    st, detail = doctor.publish_tool_row(repo)
    assert st == "WARN" and "does not list" in detail and floor.VENDORED in detail and publish.VENDORED in detail, detail
    (repo / "config/public-paths.txt").write_text(".github/\nREADME.md\ntools/psxd_*.py\n")
    assert doctor.publish_tool_row(repo)[0] == "OK", doctor.publish_tool_row(repo)


def test_release_gate_runs_the_debt_check(tmp_path):
    """publish.debt_gate: the release gate refuses a tree whose debt baseline is missing or not equal to its source,
    with the command that updates it. An equal baseline passes, and so does a public tree whose totals count a file
    that it does not publish. A tree without the floor's tool has no such check in its public CI, and passes."""
    tree = _style_repo(tmp_path, {"src/a.c": floor.C_DEBT["goto"][0], floor.VENDORED: (ROOT / "scripts/floor.py").read_text()})
    assert (publish.FLOOR_TOOL, publish.DEBT_BASELINE) == (floor.VENDORED, floor.BASELINE)
    got = publish.debt_gate(tree)
    assert len(got) == 1 and "no %s" % floor.BASELINE in got[0] and publish.PUBLIC_PATHS_REL in got[0], got
    base = floor.first_baseline(tree)
    (tree / floor.BASELINE).parent.mkdir()
    (tree / floor.BASELINE).write_text(base.replace("1 goto\n", ""))
    got = publish.debt_gate(tree)
    assert len(got) == 1 and "DEBT CHECK FAIL (1 rise(s)" in got[0] and "`debt --update` rewrites the rows" in got[0], got
    (tree / floor.BASELINE).write_text(base)
    assert publish.debt_gate(tree) == []
    (tree / floor.BASELINE).write_text(base.replace("1 goto", "2 goto"))         # a stale row fails too
    assert len(publish.debt_gate(tree)) == 1 and "stale goto: 1, its row is 2" in publish.debt_gate(tree)[0]
    # a public list that names each source file makes the tree public: its row may count a file that it does not hold
    (tree / publish.PUBLIC_PATHS_REL).write_text("src/a.c\nconfig/\ntools/\n")
    run(["git", "-C", tree, "add", publish.PUBLIC_PATHS_REL])
    assert publish.debt_gate(tree) == []
    (tree / floor.BASELINE).write_text("mode admit\n1 goto src/a.c\n")           # the file of an earlier psxdecomp
    assert "version 1 file" in publish.debt_gate(tree)[0]
    (tree / floor.VENDORED).unlink()
    assert publish.debt_gate(tree) == []
    text = (ROOT / "scripts/publish.py").read_text()
    assert 'g["paths"] + g["readme"] + g["debt"]' in text and 'out["debt"] = debt_gate(x)' in text


def test_delivered_texts_hold_no_exemplar_string():
    """The two exemplar repositories with no licence give ideas only. This is a tripwire for the strings that the
    0.6.0 audit found shared with their hooks: none is in a file that a game receives."""
    recorded = ("(^|[;&|]\\s*)make", "python3?\\s+-m\\s+splat\\s+split")       # snowboardkids2-decomp .claude/hooks, 3b1bd5d
    for rel in ("profiles/psx/guard.tsv", "profiles/psx/floor.md", "profiles/psx/campaign.md", "profiles/psx/hooks.json",
                "profiles/psx/rules/FIN1.md", "profiles/psx/rules/NAME1.md", "scripts/floor.py"):
        text = (ROOT / rel).read_text()
        assert not [s for s in recorded if s in text], rel


def test_floor_doc_commands_exist():
    """The commands that the floor's reference gives a developer: the plan correction names the plan file (PA3's
    plan_edit.py writes the phase plan without it), and each `/psxdecomp:upgrade <verb>` is a verb of upgrade.py that
    the upgrade skill explains."""
    import upgrade
    doc = (ROOT / "profiles/psx/floor.md").read_text()
    line = next(l for l in doc.splitlines() if "plan_edit.py" in l)
    assert "--file GENERATION_PLAN.md append-change --by developer" in line, line
    skill = (ROOT / "skills/upgrade/SKILL.md").read_text()
    verbs = set(re.findall(r"/psxdecomp:upgrade (\w+)", doc + (ROOT / "docs/HARVEST.md").read_text()))
    assert verbs and all('"$PSXD" upgrade %s ' % v in skill for v in verbs), verbs
    choices = re.search(r'choices=\[([^\]]+)\]', (ROOT / "scripts/upgrade.py").read_text())[1]
    assert all('"%s"' % v in choices for v in verbs), (verbs, choices)
    assert upgrade.OWN_KEYS == tuple(re.findall(r"`(\w+)`", skill.split("The key is one of", 1)[1].split(".", 1)[0]))


def test_tier1_fails_on_a_pin_it_cannot_resolve():
    """tests/conftest.py: a pin that cannot be resolved fails tier 1 and never skips it, unless the developer allowed
    the skip. A green tier 1 then means that tier 1 ran (release.yml drafts a release on it)."""
    import conftest
    saved = os.environ.pop("PSXDECOMP_ALLOW_SKIP", None)
    try:
        def outcome(*args):                       # the exception's own type: a skip raised here must not skip this test
            try:
                conftest.unresolved(*args)
            except BaseException as e:            # noqa: BLE001 — pytest's outcomes are BaseException
                return type(e)
            return None
        assert outcome("kit", "digest sha256:000 is not the tested one") is pytest.fail.Exception
        os.environ["PSXDECOMP_ALLOW_SKIP"] = "1"
        assert outcome("kit", "no network") is pytest.skip.Exception
    finally:
        os.environ.pop("PSXDECOMP_ALLOW_SKIP", None)
        if saved is not None:
            os.environ["PSXDECOMP_ALLOW_SKIP"] = saved
    text = (ROOT / "tests/conftest.py").read_text()
    assert text.count("unresolved(") == 3 and "pytest.skip(\"pinned" not in text


def test_golden_interpreter_token():
    """The interpreter path of a golden file is one token on every host: Homebrew, a GitHub runner, a virtualenv,
    manylinux. A pattern that stops at the first folder named python would leave a tail in the golden text."""
    import conftest
    for path in ("/opt/hostedtoolcache/Python/3.12.7/x64/bin/python", "/home/u/venv/bin/python",
                 "/opt/homebrew/opt/python@3.14/bin/python3.14", "/opt/python/cp312-cp312/bin/python",
                 "/usr/bin/python3", "/Users/u/.pyenv/versions/3.14.1/bin/python3.14"):
        for tail in (" (3.14.7)", "", '"'):
            got = re.sub(conftest.PY_TOKEN, "<PY>", "- Python: %s%s" % (path, tail))
            assert got == "- Python: <PY>" + ('"' if tail == '"' else ""), (path, tail, got)


def test_release_workflow_refuses_a_tag_off_main():
    """release.yml drafts a release only for a tag whose commit is on main: the squash merge comes first, then the tag
    on main's tip (docs/RELEASING.md step 6). ci.yml has a job that the default-branch ruleset can require."""
    rel = (ROOT / ".github/workflows/release.yml").read_text()
    assert "fetch-depth: 0" in rel and 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' in rel
    steps = (ROOT / "docs/RELEASING.md").read_text()
    assert "squash-merge" in steps and "tag the tip of `main`" in steps
    import doctor
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    names = re.findall(r"(?m)^  ([\w-]+):\n(?:    name: (.*)\n)?", ci.split("\njobs:\n", 1)[1])
    assert any(doctor.NO_ROM_CHECK.search(job + " " + name) for job, name in names), names


def test_plan_grammar_cases(tmp_path):
    """`plan.py` on synthetic plans: the ladder as written passes; a slice stands for its phase; a merge with a
    `## Changes` line passes; a dropped phase exits 1 with a `ladder` FAIL; a generation-2 plan reads the ladder from
    the closed generation's record; a line with a lost key exits 1 with a `grammar` FAIL."""
    repo = _style_repo(tmp_path, {"GENERATION_PLAN.md": plan.self_plan(closed=0)})
    plan_md = repo / "GENERATION_PLAN.md"
    r = _plan("--repo", repo)
    assert r.returncode == 0 and r.stdout.endswith("PLAN OK (0 fail, 0 warn)\n"), r.stdout
    assert "PLAN INFO state: generation 1; ladder phases open 0; pending 1,2,3,4,5,6,7,8,9,10\n" in r.stdout, r.stdout
    slices = [plan._phase("1.8.1", "The campaign, slice 1", milestone="0 stubs", depends="1.7"),
              plan._phase("1.8.2", "The campaign, slice 2", depends="1.8.1")]
    plan_md.write_text(plan.self_plan(closed=0, drop=(8,), extra=slices).replace("depends: 1.8 |", "depends: 1.8.2 |"))
    assert _plan("--repo", repo).returncode == 0
    dropped = plan.self_plan(closed=0, drop=(6,)).replace("depends: 1.6 |", "depends: 1.5 |")
    plan_md.write_text(dropped)
    r = _plan("--repo", repo)
    assert r.returncode == 1 and "PLAN FAIL ladder: no line 1.6 (The multipliers)" in r.stdout, r.stdout
    assert r.stdout.endswith("PLAN FAIL (1 fail, 0 warn)\n"), r.stdout
    plan_md.write_text(dropped + "- 2026-01-02 developer: phases 1.5 and 1.6 merged into 1.5 — a small game\n")
    assert _plan("--repo", repo).returncode == 0
    plan_md.write_text(plan.self_plan(closed=0).replace(" | scope: s", "", 1))
    r = _plan("--repo", repo)
    assert r.returncode == 1 and "PLAN FAIL grammar: line 11 (1.0): no `scope:`" in r.stdout, r.stdout
    plan_md.write_text("# Generation 2 — next\n\nGoal: g\nDone-criteria: d\n\n## Phases\n\n%s\n\n## Changes\n"
                    % plan._phase("2.1", "The round-trip disc"))
    r = _plan("--repo", repo)
    assert r.returncode == 0 and "PLAN WARN ladder: generation 2 and no phase-ends/GenerationEnd_1.md" in r.stdout
    (repo / "phase-ends").mkdir()
    (repo / "phase-ends/GenerationEnd_1.md").write_text("# GenerationEnd\n\n## Phases\n" + "".join(
        "- 1.%d | %s | milestone: m\n" % (n, name) for n, name, _, _ in plan.LADDER))
    r = _plan("--repo", repo)
    assert r.returncode == 0 and r.stdout.endswith("PLAN OK (0 fail, 0 warn)\n"), r.stdout
    plan_md.unlink()
    r = _plan("--repo", repo)
    assert r.returncode == 0 and r.stdout.startswith("PLAN INFO plan: no GENERATION_PLAN.md"), r.stdout
    assert _plan("ladder", ROOT / "fixtures/PROJECT_CONTEXT.fixture.md").returncode == 1      # the fixture names two


def test_debt_kinds(tmp_path):
    """One planted file per debt kind and one clean control in a git repository: the first baseline holds exactly the
    planted counts, and `debt` passes against it."""
    files = {"src/clean.c": floor.C_CLEAN}
    files.update({"src/%s.c" % kind: text for kind, (text, _) in floor.C_DEBT.items()})
    repo = _style_repo(tmp_path, files)
    bl = floor.parse_baseline(floor.first_baseline(repo))
    want = {(k, "src/%s.c" % kind): n for kind, (_, got) in floor.C_DEBT.items() for k, n in got.items()}
    assert bl.totals == {k: n for k, n in floor._kind_totals(want).items() if n} and bl.skip == [] and len(bl.head) == len(floor.BASELINE_HEAD), bl.totals   # no stub header here: no skip line
    assert set(bl.totals) == set(floor.KINDS) - {"filename"} and not bl.lacks() and not bl.by_file
    assert bl.summary() == "down: pin-unmarked, goto-unmarked, barrier-unmarked, asm; count: pin, goto, barrier, " \
                           "offset, address, cast, field, placeholder, placeholder-use, struct, extern, filename"
    (repo / "config").mkdir()
    (repo / floor.BASELINE).write_text(floor.first_baseline(repo))
    r = _floor("debt", "--repo", repo)
    assert r.returncode == 0 and "DEBT CHECK OK (0 rise(s), 0 stale row(s); down: pin-unmarked" in r.stdout, r.stdout


def test_debt_bodies():
    """The counts by function body: on every C fixture of this repository the sum of a file's bodies is its count,
    each file of the corpus is one body, and a pin, a goto and an offset read never fall outside a body."""
    files = sorted((ROOT / "fixtures").glob("**/*.c")) + sorted((ROOT / "fixtures").glob("**/*.h"))
    assert len(files) > 100
    for f in files:
        text, total = f.read_text(), {}
        bodies = floor.file_bodies("src/t.c", text)
        for got in bodies.values():
            for kind, n in got.items():
                total[kind] = total.get(kind, 0) + n
        assert total == floor.file_debt("src/t.c", text), f
        assert not set(bodies.get(floor.SCOPE, {})) & {"pin", "pin-unmarked", "goto", "offset", "asm"}, (f, bodies)
        if f.suffix == ".c":
            assert len([n for n in bodies if n != floor.SCOPE]) == 1, (f, sorted(bodies))


def _stubs(*names):
    """A C file of INCLUDE_ASM lines."""
    return "".join('INCLUDE_ASM("asm/nonmatchings/a", %s);\n' % n for n in names) or "// every function is in C\n"


def _gate_repo(tmp_path):
    """A committed game with the two vendored tools, a version 2 baseline, one prose file and a commit hook that runs
    `gate --staged` with this checkout's floor.py."""
    repo = _style_repo(tmp_path, {"src/a.c": floor.C_DEBT["goto"][0], "docs/a.md": "Clean.\n", "tools/x": "x\n",
                                  "src/stubs.c": _stubs("Run"), "src/more.c": _stubs("Jump")})
    for src, dst in (("scripts/floor.py", floor.VENDORED), ("scripts/publish.py", publish.VENDORED)):
        (repo / dst).write_bytes((ROOT / src).read_bytes())
    assert _floor("debt", "--recount", "--repo", repo).returncode == 0
    hook = pathlib.Path(run(["git", "-C", repo, "rev-parse", "--path-format=absolute", "--git-path", "hooks/pre-commit"]).stdout.strip())
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexec '%s' '%s' gate --staged\n" % (PY, ROOT / "scripts/floor.py"))
    hook.chmod(0o755)
    run(["git", "-C", repo, "add", "-A"])
    run(["git", "-C", repo, "-c", "commit.gpgsign=false", "commit", "-qm", "the floor"])
    return repo


def test_gate_modes(tmp_path):
    """`gate --staged` as a commit hook. `git commit -a` and `git commit -- <path>` give the hook an index of their
    own: the gate reads that one, also for the style check of the other tool. A linked worktree is judged against its
    own HEAD. A merge is judged against HEAD: it passes when no kind in mode `down` rose. A first commit has nothing
    to be judged against. `gate --ci` judges the two ends of the same history afterwards."""
    repo = _gate_repo(tmp_path)
    git = lambda *a, cwd=repo, check=True: run(["git", "-C", cwd, "-c", "commit.gpgsign=false", *a], check=check)  # noqa: E731
    worse = floor.C_DEBT["goto-unmarked"][0]                                    # the same function, its goto with no reason
    refusal = "goto-unmarked is `down` and its total rose: 0 -> 1 (src/a.c 0 -> 1)"
    start = git("rev-parse", "HEAD").stdout.strip()
    (repo / "src/a.c").write_text(worse)                                        # never staged: `commit -a` stages it
    for form in (("commit", "-qam", "worse"), ("commit", "-qm", "worse", "--", "src/a.c")):
        r = git(*form, check=False)
        assert r.returncode != 0 and "GATE FAIL debt: " + refusal in r.stdout + r.stderr, form
    git("checkout", "--", "src/a.c")
    (repo / "docs/a.md").write_text("One; two.\n")
    r = git("commit", "-qam", "prose", check=False)
    assert r.returncode != 0 and "GATE FAIL style: docs/a.md: 1 finding(s), its row is 0" in r.stdout + r.stderr, r.stdout + r.stderr
    git("checkout", "--", "docs/a.md")
    assert git("rev-parse", "HEAD").stdout.strip() == start
    # a linked worktree: its own index, its own HEAD, the hooks of the repository
    side = tmp_path / "side"
    git("worktree", "add", "-q", "-b", "side", side)
    (side / "src/a.c").write_text(worse)
    r = git("commit", "-qam", "worse", cwd=side, check=False)
    assert r.returncode != 0 and refusal in r.stdout + r.stderr, r.stdout + r.stderr
    git("checkout", "--", "src/a.c", cwd=side)
    (side / "src/b.c").write_text(floor.C_DEBT["goto"][0].replace("Walk", "Run"))
    (side / "src/stubs.c").write_text(_stubs())
    git("add", "-A", cwd=side)
    r = _floor("gate", "--bank", "--repo", side)                                 # the bank writes the rows of the new file
    assert r.returncode == 0 and "2 goto\n" in (side / floor.BASELINE).read_text(), r.stdout
    git("commit", "-qam", "a new body on the side", cwd=side)
    # a merge: both sides added a body and a row
    (repo / "src/c.c").write_text(floor.C_DEBT["goto"][0].replace("Walk", "Jump"))
    (repo / "src/more.c").write_text(_stubs())
    assert _floor("gate", "--bank", "--repo", repo).returncode == 0
    git("add", "-A")
    git("commit", "-qm", "a new body on main")
    r = git("merge", "-q", "--no-ff", "--no-commit", "side", check=False)
    (repo / floor.BASELINE).write_bytes(run(["git", "-C", repo, "show", "HEAD:" + floor.BASELINE]).stdout.encode())
    (repo / "src/a.c").write_text(worse)                                        # and the merge itself brings an unmarked goto
    assert _floor("debt", "--update", "--repo", repo).returncode == 1
    git("add", "-A")
    r = git("commit", "-qm", "an evil merge", check=False)
    assert r.returncode != 0 and refusal in r.stdout + r.stderr, r.stdout + r.stderr
    (repo / "src/a.c").write_text(floor.C_DEBT["goto"][0])
    r = _floor("debt", "--update", "--repo", repo)
    assert r.returncode == 0 and "3 goto\n" in (repo / floor.BASELINE).read_text(), r.stdout
    git("add", "-A")
    git("commit", "-qm", "the merge")
    assert len(git("rev-list", "--parents", "-n", "1", "HEAD").stdout.split()) == 3
    r = _floor("gate", "--ci", "%s..HEAD" % start, "--repo", repo)
    assert (r.returncode, r.stdout) == (0, "GATE OK (ci; 3 commit(s))\n"), r.stdout
    assert _floor("gate", "--push", "--repo", repo).stdout == "GATE OK (push; 0 commit(s); no base: the tree of the head only)\n"
    # a first commit: nothing to judge it against, and its tree is checked as it stands
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    run(["git", "init", "-q", fresh])
    (fresh / "src").mkdir()
    (fresh / "src/a.c").write_text(floor.C_DEBT["goto"][0])
    run(["git", "-C", fresh, "add", "-A"])
    r = _floor("gate", "--staged", "--repo", fresh)
    assert r.returncode == 1 and "GATE FAIL debt: no %s" % floor.BASELINE in r.stdout and "no commit yet" in r.stdout, r.stdout
    assert _floor("debt", "--recount", "--repo", fresh).returncode == 0
    run(["git", "-C", fresh, "add", "-A"])
    assert _floor("gate", "--staged", "--repo", fresh).returncode == 0
    run(["git", "-C", fresh, "-c", "commit.gpgsign=false", "commit", "-qm", "first"])
    r = _floor("gate", "--ci", "%s..HEAD" % ("0" * 40), "--repo", fresh)
    assert r.returncode == 0 and "no base: the tree of the head only" in r.stdout, r.stdout
    r = _floor("gate", "--repo", fresh)
    assert r.returncode == 2 and "one of --staged, --bank" in r.stderr


HONEST_FORMS = {
    # each is a change that an honest bank makes and that an earlier build of the floor refused (the ids are those of
    # the attack reports of 2026-10-13): {path: text, or None to delete}
    "a helper folded into its caller, with its marked goto (f-01, a160)": {
        "src/a.c": "s32 Walk(s32 n) {\nloop:\n    // !FAKE: the loop of the original\n    if (--n) goto loop;\nagain:\n"
                   "    // !FAKE: the helper's loop\n    if (n > 4) goto again;\n    return n;\n}\n"},
    "a version conditional around an `if (...) {` (f-02, p2-60e)": {
        "src/b.c": "s32 Run(s32 n) {\n#ifdef VERSION_JP\n    if (n > 2) {\n#else\n    if (n > 3) {\n#endif\n        n--;\n    }\n    return n;\n}\n",
        "src/stubs.c": "// every function is in C\n"},
    "a header with the `extern \"C\" {` guard (f-03)": {
        "include/api.h": "#ifdef __cplusplus\nextern \"C\" {\n#endif\ns32 Run(s32 n);\n#ifdef __cplusplus\n}\n#endif\n"},
    "a stub banked under a new name into another file that exists, with an offset (f-04, a162)": {
        "src/a.c": floor.C_DEBT["goto"][0] + "s32 InitHeap(s32 *p) {\n    return *(s32 *)(p + 4);\n}\n", "src/stubs.c": "// every function is in C\n"},
    "a NON_MATCHING body beside its stub (f-05, f-13)": {
        "src/stubs.c": "#ifndef NON_MATCHING\nINCLUDE_ASM(\"asm/nonmatchings/a\", Run);\n#else\ns32 Run(s32 *p) {\nx:\n    if (*(s32 *)(p + 4)) goto x;\n"
                       "    return 0;\n}\n#endif\n"},
    "a function that returns a function pointer (f-08, p2-60b)": {
        "src/pick.c": "s32 Step(s32 n);\ns32 (*PickStep(s32 kind))(s32) {\n    if (kind) {\n        return Step;\n    }\n    return 0;\n}\n"},
    "a `static inline` helper with debt in a new header (f-12)": {
        "include/heap.h": "static inline s32 HeapWord(s32 *p) {\n    return *(s32 *)(p + 4);\n}\n"},
    "a new C file with a body beside an unrelated body that left (a161)": {
        "src/a.c": "s32 g_Walk;\n", "src/carved.c": "s32 func_80012344(s32 *p) {\n    return *(s32 *)(p + 8) + D_800A1234;\n}\n"},
    "a decompiled function named main (p2-60a)": {"src/main.c": "s32 main(void) {\n    return 0;\n}\n"},
    "plain lines that a pattern reads as debt (p2-60c)": {
        "src/a.c": floor.C_DEBT["goto"][0] + "s32 Bits(s32 n, Obj *o) {\n    n &= 0xA0000000;\n    return (sizeof(s32) & 3) + o->field_a + n;\n}\n"},
    "the stub macro's header, included (p2-60d)": {
        "include/include_asm.h": "#define INCLUDE_ASM(FOLDER, NAME) __asm__(\".section .text\\n\\t.include \\\"\" FOLDER \"/\" #NAME \".s\\\"\\n\")\n",
        "src/stubs.c": "#include \"include_asm.h\"\nINCLUDE_ASM(\"asm/nonmatchings/a\", Run);\n"},
    "a bank with a pin and a goto that the match needs, each with its reason": {
        "src/b.c": "s32 Run(s32 n) {\n    // !FAKE: the counter must stay in $16\n    register s32 i asm(\"$16\") = n;\nx:\n"
                   "    if (--i) goto x; // !FAKE: the loop of the original\n    return i;\n}\n", "src/stubs.c": "// every function is in C\n"},
    "an address name, a guessed name and a provisional row (the owner's rule of 2026-10-13)": {
        "src/names.c": "s32 func_80012344(s32 n) {\n    return n + 1;\n}\ns32 Enemy_Think(s32 n) {\n    return n + 2;\n}\ns32 Enemy_Walk(s32 n) {\n    return n + 3;\n}\n",
        floor.NAMES: "\t".join(floor.NAME_COLUMNS) + "\nfunction\tmain\t\tfunc_80012400\tEnemy_Walk\tprovisional\thuman:src/names.c:7\tone source\n"},
}


DRAFT = "a NON_MATCHING body beside its stub (f-05, f-13)"      # its goto is in a branch that the compiler does not get


@pytest.mark.parametrize("view", ["raw", "cpp"])
def test_honest_forms_pass_the_gate(tmp_path, view):
    """Each honest form of a decompilation commit passes the commit hook once its rows are written: a file split, a
    carved function, a folded helper, a conditional, a NON_MATCHING attempt, any name. Once in raw text and once in
    the view of a real preprocessor (`[floor] cpp`, where the machine has `cc`). The raw text also reads the branch
    of a conditional that is not compiled, so there an unmarked goto of a NON_MATCHING draft is refused: the limit of
    the view with no `[floor] cpp`. The control is one unmarked goto in compiled code, which the same hook refuses."""
    if view == "cpp" and not shutil.which("cc"):
        pytest.skip("no cc on this machine")
    repo = _gate_repo(tmp_path)
    git = lambda *a, check=True: run(["git", "-C", repo, "-c", "commit.gpgsign=false", *a], check=check)  # noqa: E731
    if view == "cpp":
        (repo / floor.RECORD).parent.mkdir(exist_ok=True)
        (repo / floor.RECORD).write_text("[psxdecomp]\nversion = \"0.6.0\"\n\n[floor]\ncpp = \"cc -E -nostdinc -undef -Iinclude {file}\"\n")
        git("add", "-A")
        git("commit", "-qm", "the preprocess command of the game", "--no-verify")
    start = git("rev-parse", "HEAD").stdout.strip()
    for name, files in HONEST_FORMS.items():
        for rel, text in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text)
        git("add", "-A")
        r = _floor("debt", "--update", "--repo", repo)
        if view == "raw" and name == DRAFT:
            assert r.returncode == 1 and "goto-unmarked is `down` and its total rose: 0 -> 1 (src/stubs.c 0 -> 1)" in r.stdout, r.stdout
        else:
            assert r.returncode == 0, (name, r.stdout)
            r = git("commit", "-qam", name, check=False)
            assert r.returncode == 0 and "GATE FAIL" not in r.stdout + r.stderr, (name, r.stdout + r.stderr)
            r = _floor("gate", "--ci", "%s..HEAD" % start, "--repo", repo)
            assert r.returncode == 0 and r.stdout.endswith("GATE OK (ci; 1 commit(s))\n"), (name, r.stdout)
        git("reset", "-q", "--hard", start)
        git("clean", "-q", "-fd")
    (repo / "src/a.c").write_text(floor.C_DEBT["goto-unmarked"][0])
    git("add", "-A")
    assert _floor("debt", "--update", "--repo", repo).returncode == 1
    r = git("commit", "-qam", "the control: a goto with no reason", check=False)
    assert r.returncode != 0 and "goto-unmarked is `down` and its total rose: 0 -> 1" in r.stdout + r.stderr, r.stdout + r.stderr


def test_debt_against_rev(tmp_path):
    """The tree reader: the work tree, the index and a revision give one count, on an LF checkout and on a CRLF one.
    `debt --against` prints what differs from a revision. `style --against` judges the prose by the ratchet, the
    `skip` lines and the public list of the revision: a raised row, a new `skip` line and a file that left the public
    list change nothing."""
    files = {"src/a.c": floor.C_DEBT["goto"][0], "src/m.c": floor.C_DEBT["struct"][0],
             "src/o.c": "s32 Walk(void *p) {\n    return HP(p);\n}\n",
             "include/h.h": "#define HP(p) \\\n    (*(s16 *)((u8 *)(p) + 0x10))\n",
             "README.md": "# G\n\nOne; two.\n", "docs/a.md": "Clean.\n",
             publish.STYLE_RATCHET_REL: "1 README.md\n", publish.PUBLIC_PATHS_REL: "README.md\ndocs/\n"}
    repo = _style_repo(tmp_path, files)
    debt = lambda *a: _floor("debt", "--repo", repo, *a)  # noqa: E731
    totals = lambda r: re.search(r"totals: ([^(]+) \(", r.stdout)[1]  # noqa: E731
    want = "goto 1, offset 2, struct 1"
    assert [totals(debt()), totals(debt("--staged")), totals(debt("--rev", "HEAD"))] == [want] * 3
    assert "counted in the index" in debt("--staged").stdout and "counted in HEAD" in debt("--rev", "HEAD").stdout
    run(["git", "-C", repo, "config", "core.autocrlf", "true"])                 # a Windows checkout of the same commit
    for rel in files:
        (repo / rel).write_bytes((repo / rel).read_bytes().replace(b"\n", b"\r\n"))
    run(["git", "-C", repo, "add", "-A"])                                       # the index takes the same blobs again
    assert run(["git", "-C", repo, "status", "--porcelain"]).stdout == ""
    assert b"\r\n" in (repo / "src/m.c").read_bytes()
    assert [totals(debt()), totals(debt("--staged")), totals(debt("--rev", "HEAD"))] == [want] * 3
    style = lambda *a: run([PY, ROOT / "scripts/publish.py", "style", "--repo", repo, *a], check=False)  # noqa: E731
    counts = [style(*a).stdout for a in ((), ("--staged",), ("--rev", "HEAD"), ("--against", "HEAD"))]
    assert counts == ["STYLE CHECK OK (2 file(s), 1 finding(s), 0 over their row)\n"] * 4, counts
    (repo / "src/a.c").write_text(floor.C_DEBT["goto"][0] * 2)
    r = debt("--against", "HEAD")                                               # no baseline in HEAD: no kind is `down` there
    assert "0 finding(s) against HEAD" in r.stdout, r.stdout
    assert totals(debt("--staged")) == want                                     # not added yet
    run(["git", "-C", repo, "add", "src/a.c"])
    assert totals(debt("--staged")) == "goto 2, offset 2, struct 1" and totals(debt("--rev", "HEAD")) == want
    assert debt("--staged", "--update").returncode == 1 and debt("--rev", "nowhere").returncode == 1
    # the ratchet of the change cannot admit what the base's ratchet refuses
    (repo / "README.md").write_text("# G\n\nOne; two; three.\n")
    (repo / publish.STYLE_RATCHET_REL).write_text("2 README.md\n")
    assert style().returncode == 0
    r = style("--against", "HEAD")
    assert r.returncode == 1 and "STYLE FAIL policy: the row of README.md is 2 and was 1 in HEAD" in r.stdout
    assert "STYLE FAIL README.md: 2 finding(s), its row in HEAD is 1\n" in r.stdout, r.stdout
    (repo / publish.STYLE_RATCHET_REL).write_text("skip README.md\n")
    r = style("--against", "HEAD")
    assert r.returncode == 1 and "policy: a new `skip` line (README.md)" in r.stdout and "README.md: 2 finding(s)" in r.stdout
    (repo / publish.STYLE_RATCHET_REL).unlink()
    assert "policy: %s is gone" % publish.STYLE_RATCHET_REL in style("--against", "HEAD").stdout
    run(["git", "-C", repo, "checkout", "--", "README.md", publish.STYLE_RATCHET_REL])
    (repo / "docs/a.md").write_text("One; two.\n")
    (repo / publish.PUBLIC_PATHS_REL).write_text("README.md\n")
    assert style().returncode == 0                                              # docs/ is not public any more
    r = style("--against", "HEAD")
    assert r.returncode == 1 and "docs/a.md: policy: it left the public list with 1 finding(s)" in r.stdout, r.stdout
    run(["git", "-C", repo, "add", "-A"])
    assert style("--staged", "--against", "HEAD").returncode == 1 and style("--rev", "HEAD", "--against", "HEAD").returncode == 0
    run(["git", "-C", repo, "rm", "-q", publish.STYLE_RATCHET_REL])
    run(["git", "-C", repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "no ratchet"])
    r = style("--against", "HEAD")                                              # the base holds no ratchet: no judge
    assert "STYLE INFO HEAD holds no %s" % publish.STYLE_RATCHET_REL in r.stdout, r.stdout


def test_tools_find_each_other(tmp_path):
    """Each vendored tool runs the other one from its own folder: `floor.py` beside `publish.py` in the plugin,
    `psxd_floor.py` beside `psxd_publish.py` in a game. The release gate's debt check is run by that copy, so a
    floor tool that the checked tree rewrote decides nothing."""
    assert floor.sibling() == ROOT / "scripts/publish.py" and publish.sibling() == ROOT / "scripts/floor.py"
    (tmp_path / "copy").mkdir()
    for src, dst in (("scripts/floor.py", floor.VENDORED), ("scripts/publish.py", publish.VENDORED)):
        (tmp_path / "copy" / pathlib.Path(dst).name).write_bytes((ROOT / src).read_bytes())
    code = "import psxd_floor, psxd_publish; print(psxd_floor.sibling().name, psxd_publish.sibling().name)"
    r = run([PY, "-c", code], cwd=tmp_path / "copy")
    assert r.stdout.split() == ["psxd_publish.py", "psxd_floor.py"], r.stdout
    tree = _style_repo(tmp_path, {"src/a.c": floor.C_DEBT["goto"][0], floor.BASELINE: "mode admit\n",
                                  floor.VENDORED: "import sys\nsys.exit(0)\n"})
    got = publish.debt_gate(tree)
    assert len(got) == 1 and "DEBT CHECK FAIL" in got[0] and "version 1 file" in got[0], got


def test_debt_baseline_command(tmp_path):
    """The baseline through the command line. There is no `--admit`: the flag exits 2. A kind in mode `count` rises
    with its row. `--update` exits 1 on a rise of a kind in mode `down`. A deleted baseline exits 1. A row written by
    hand passes the row check and fails `--against`. A weaker mode, a new `skip` line and a missing policy line fail
    as `policy`. `--raise` is refused in an agent session. `--down` is one way."""
    repo = _style_repo(tmp_path, {"src/a.c": floor.C_DEBT["goto"][0], "src/stubs.c": _stubs("Run")})
    debt = lambda *a, **kw: _floor("debt", "--repo", repo, *a, **kw)  # noqa: E731
    base, more = repo / floor.BASELINE, floor.C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;")
    refusal = "DEBT FAIL debt: goto-unmarked is `down` and its total rose: 0 -> 1 (src/a.c 0 -> 1)\n"
    r = debt()
    assert r.returncode == 1 and "DEBT FAIL no %s" % floor.BASELINE in r.stdout, r.stdout
    assert debt("--update").returncode == 1 and not base.exists()
    r = debt("--recount")
    assert r.returncode == 0 and "DEBT RECOUNT written" in r.stdout and base.read_text().endswith("1 goto\n")
    first = base.read_text()
    assert "mode pin-unmarked down\n" in first and "mode pin count\n" in first and "mode filename count\n" in first
    assert debt().returncode == 0
    run(["git", "-C", repo, "add", "-A"])
    run(["git", "-C", repo, "-c", "commit.gpgsign=false", "commit", "-qm", "the baseline"])
    (repo / "src/a.c").write_text(more)
    r = debt()
    assert r.returncode == 1 and "DEBT FAIL rise goto: 2, its row is 1\n" in r.stdout, r.stdout
    r = debt("--update", "--admit")
    assert r.returncode == 2 and "unrecognized arguments: --admit" in r.stderr and base.read_text() == first, r.stderr
    r = debt("--update")                                                        # a counted kind: the row follows the tree
    assert r.returncode == 0 and "DEBT INFO goto: 1 -> 2\n" in r.stdout and debt("--against", "HEAD").returncode == 0, r.stdout
    base.write_text(first)
    (repo / "src/a.c").write_text(floor.C_DEBT["goto-unmarked"][0])
    r = debt("--update")
    assert r.returncode == 1 and refusal in r.stdout and "DEBT UPDATE refused" in r.stdout and base.read_text() == first, r.stdout
    base.write_text(first.replace("1 goto\n", "1 goto\n1 goto-unmarked\n"))   # the row written by hand
    assert debt().returncode == 0
    r = debt("--against", "HEAD")
    assert r.returncode == 1 and refusal in r.stdout, r.stdout
    (repo / "src/a.c").write_text(more)
    for text, want in ((first.replace("mode pin-unmarked down\n", ""), "DEBT FAIL policy: the policy line of pin-unmarked is gone"),
                       (first.replace("mode asm down", "mode asm count"), "DEBT FAIL policy: asm went from down to count"),
                       (first.replace("1 goto", "skip src/\n1 goto"), "DEBT FAIL policy: a new `skip` line (src/)")):
        base.write_text(text)
        r = debt("--against", "HEAD")
        assert r.returncode == 1 and want in r.stdout, (want, r.stdout)
    base.unlink()
    r = debt("--against", "HEAD")
    assert r.returncode == 1 and "DEBT FAIL policy: %s is gone" % floor.BASELINE in r.stdout, r.stdout
    base.write_text(first)
    assert debt("--update").returncode == 0 and debt("--against", "HEAD").returncode == 0
    r = debt("--raise", "goto-unmarked", "3", "--reason", "x", env={"CLAUDECODE": "1"})
    assert r.returncode == 1 and "the developer's act" in r.stdout and "raise goto" not in base.read_text()
    r = debt("--raise", "goto-unmarked", "3", "--reason", "the stage loader")
    assert r.returncode == 0 and re.search(r"^raise goto-unmarked 3 \d{4}-\d\d-\d\d the stage loader$", base.read_text(), re.M)
    (repo / "src/a.c").write_text(floor.C_DEBT["goto-unmarked"][0])
    r = debt("--update")                                                        # the raise line of the change allows it
    assert r.returncode == 0 and "goto-unmarked is over by 1: the change's `raise` line(s) allow 3" in r.stdout, r.stdout
    (repo / "src/a.c").write_text(floor.C_CLEAN)
    r = debt()
    assert r.returncode == 1 and "DEBT FAIL stale goto: 0, its row is 1" in r.stdout, r.stdout
    assert debt("--down", "goto").returncode == 1 and debt("--update").returncode == 0 and debt("--down", "goto").returncode == 0
    assert "mode goto down\n" in base.read_text()


def test_debt_agrees_with_the_corpus_lint():
    """The debt kinds reuse the definitions of fixtures/c-corpus/lint.py (which the tier 5a container runs alone): every
    twin that the lint flags, `floor.file_debt` flags as the same kind, and a truth has none of the five."""
    sys.path.insert(0, str(ROOT / "fixtures/c-corpus"))
    import lint
    same = {"register-pin": "pin", "goto": "goto", "offset-cast": "offset", "abs-address": "address", "struct-def": "struct"}
    assert set(same) == set(lint.KINDS)
    twins = 0
    for d in sorted((ROOT / "fixtures/c-corpus/truth").iterdir()):
        assert not set(floor.file_debt("src/t.c", (d / "truth.c").read_text())) & set(same.values()), d.name
        for twin in d.glob("twin.*.c"):
            got = floor.file_debt("src/t.c", twin.read_text())
            for kind in {f[0] for f in lint.findings(twin.read_text())}:
                assert same[kind] in got, (twin, kind, got)
                twins += 1
    assert twins >= 15, twins


def test_guard_hook_output(tmp_path):
    """`floor.py guard --hook` as a PreToolUse hook: a denied call is one JSON object on stdout with the rule's text,
    exit code 0. An allowed call and a repository with no rules file print nothing, exit code 0. An event that the
    guard cannot read (bad JSON, no event) is refused: the guard fails closed."""
    rules = "action\ttool\tpattern\tsay\ndeny\tpath\tasm/\tasm/ is generated\ndeny\tbash\tmake +expected\task first\n"
    repo = _style_repo(tmp_path, {"config/guard.tsv": rules, "src/a.c": "x\n"})
    ev = lambda tool, **inp: json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": inp,  # noqa: E731
                                         "cwd": str(repo)})
    for stdin, want in ((ev("Edit", file_path=str(repo / "asm/a.s")), "asm/ is generated"),
                        (ev("Bash", command="make  expected"), "ask first")):
        r = _floor("guard", "--hook", cwd=tmp_path, stdin=stdin)
        assert r.returncode == 0 and r.stderr == "" and len(r.stdout.splitlines()) == 1, (r.stdout, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "deny", out
        assert want in out["permissionDecisionReason"] and "config/guard.tsv" in out["permissionDecisionReason"], out
    silent = {"an allowed edit": ev("Edit", file_path=str(repo / "src/a.c")), "an allowed command": ev("Bash", command="ls")}
    for name, stdin in silent.items():
        r = _floor("guard", "--hook", cwd=tmp_path, stdin=stdin)
        assert (r.returncode, r.stdout) == (0, ""), (name, r.stdout, r.stderr)
    for name, stdin in {"bad JSON": "{not json", "no event": ""}.items():      # an event it cannot read: the guard fails closed
        r = _floor("guard", "--hook", cwd=tmp_path, stdin=stdin)
        assert r.returncode == 0 and '"permissionDecision": "deny"' in r.stdout and "the guard failed on this call" in r.stdout, (name, r.stdout)
    (repo / "config/guard.tsv").unlink()
    r = _floor("guard", "--hook", cwd=tmp_path, stdin=ev("Edit", file_path=str(repo / "asm/a.s")))
    assert (r.returncode, r.stdout) == (0, ""), r.stdout


def test_delivery_table():
    """scripts/upgrade.py DELIVERY is the one table of what psxdecomp delivers and how: each row has a known class and
    a source that exists, each class is described in the script's docstring, and docs/HARVEST.md names every path
    that proposes an `[own]` key."""
    import upgrade
    assert {d.cls for d in upgrade.DELIVERY} <= set(upgrade.CLASSES)
    for d in upgrade.DELIVERY:
        assert d.src is None or (ROOT / d.src).is_file(), d
        assert d.own is None or d.own in upgrade.OWN_KEYS, d
    assert all("`%s`" % c in upgrade.__doc__ for c in upgrade.CLASSES)
    harvest = (ROOT / "docs/HARVEST.md").read_text()
    for key, (path, _) in upgrade.OWN_DETECT.items():
        assert "| `%s` | `%s` |" % (key, path) in harvest, key
    assert set(upgrade.OWN_KEYS) - set(upgrade.OWN_DETECT) == {"gate"} and '`/psxdecomp:upgrade own gate "<command>"`' in harvest


def test_guard_profile_files():
    """The guard as the profile ships it. hooks.json: one PreToolUse group for Bash, Edit and Write whose command runs
    the vendored `guard --hook` and fails closed (`"onFailure": "block"`, no `|| exit 0`). guard.tsv: the header line,
    five default `path` rules, two more for the record of the other builds, and two `bash` rules for the commit hook
    that parse, two examples as comments. deny.json: one `Edit(/...)` rule for each of the first five paths, in Claude
    Code's rule syntax (a leading `/` is the project root), and the rules that keep a session from a commit with no
    hook. The record of the other builds has the guard's two rows and no deny rule."""
    conf = json.loads((ROOT / "profiles/psx/hooks.json").read_text())["hooks"]["PreToolUse"]
    assert len(conf) == 1 and len(conf[0]["hooks"]) == 1, conf
    assert set(conf[0]["matcher"].split("|")) == {"Bash"} | set(floor.PATH_TOOLS), conf[0]["matcher"]   # every tool the guard reads
    assert 0 < conf[0]["hooks"][0]["timeout"] <= 30 and floor.GUARD_SECONDS < conf[0]["hooks"][0]["timeout"], conf
    cmd = conf[0]["hooks"][0]["command"]
    assert cmd == 'python3 "$CLAUDE_PROJECT_DIR/%s" guard --hook' % floor.VENDORED and conf[0]["hooks"][0]["onFailure"] == "block", cmd
    assert common.hook_kind(conf[0]) == "guard-hook"
    post = json.loads((ROOT / "profiles/psx/hooks.json").read_text())["hooks"]["PostToolUse"][0]
    assert common.hook_kind(post) == "style-hook"
    text = common.PROFILE_GUARD.read_text()
    rules = floor.parse_guard(text)
    assert floor.guard_errors(text) == [] and "\t".join(floor.GUARD_COLUMNS) in text.splitlines()
    assert [r[:2] for r in rules] == [("deny", "path")] * 7 + [("deny", "bash")] * 2 and all(r[3] for r in rules), rules
    assert len([l for l in text.splitlines() if l.startswith("# deny\tbash\t")]) == 2
    said = lambda cmd: floor.guard_decision({"tool_name": "Bash", "tool_input": {"command": cmd}}, rules, ROOT)  # noqa: E731
    for cmd in ("git commit -n -m x", "git commit -anm x", "git -C . commit --no-verify -m x", "git commit -m x -n",
                "git config core.hooksPath /tmp/h", "git -c core.hookspath=/dev/null commit -m x"):
        assert said(cmd), cmd                                           # a commit that skips the hook, and a move of the hooks
    for cmd in ("git commit -m 'the bank'", "git commit --amend --no-edit", "git commit -am x", "git log -n 3", "git commit -S -m x"):
        assert said(cmd) is None, cmd
    paths = [r[2] for r in rules if r[1] == "path"]
    assert paths == ["asm/", "config/check.*.sha", "config/medium.sha1", floor.BASELINE, publish.STYLE_RATCHET_REL,
                     oracle.BUILDS, oracle.HASH_GLOB]
    assert all("`psxd oracle add` writes this file" in r[3] for r in rules[5:7])
    deny = json.loads((ROOT / "profiles/psx/deny.json").read_text())["permissions"]["deny"]
    edits = [r for r in deny if r.startswith("Edit(")]
    assert edits == ["Edit(/%s)" % (p + "**" if p.endswith("/") else p) for p in paths[:5]], edits   # the two last: the guard's alone
    assert {"Bash(git commit -n *)", "Bash(git commit * -n)", "Bash(* --no-verify *)", "Bash(*core.hooksPath*)"} <= set(deny)


def test_floor_doc_names_the_ladder():
    """profiles/psx/floor.md is the one home of the numbering: its table holds plan.LADDER row for row (the id 1.n,
    the kit's name, the words the milestone keeps), it starts with "After the bootstrap", and it documents every plan
    check and every guard column."""
    doc = (ROOT / "profiles/psx/floor.md").read_text()
    for n, name, _, must in plan.LADDER:
        assert "| 1.%d | %s | %s|" % (n, name, "`%s` " % must if must else "") in doc, n
    heads = [l[3:] for l in doc.splitlines() if l.startswith("## ")]
    assert heads[:2] == ["After the bootstrap", "Numbering"], heads
    for check in ("grammar", "ladder", "numbering", "frozen", "criteria", "paths", "markers"):
        assert "| `%s` | " % check in doc and "  %s " % check in plan.__doc__, check
    assert all("| `%s` |" % c in doc for c in floor.GUARD_COLUMNS)
    import upgrade
    assert all("| `%s` |" % k in doc for k in upgrade.OWN_KEYS)


def test_readability_rule_files():
    """profiles/psx/rules/FIN1.md and NAME1.md are rule bodies with no title line (the game's rules_add.py writes the
    title, common.PROFILE_RULES holds it). FIN1 states the two states and its six conditions; NAME1 lists every
    evidence class the ledger accepts. The floor's reference documents every debt kind, both ledgers and every
    doctor row of the floor."""
    import doctor
    assert list(common.PROFILE_RULES) == ["STE1", "FIN1", "NAME1"]
    assert [r[3] for r in common.PROFILE_RULES.values()] == ["ste-rule", "fin-rule", "name-rule"]
    for rid, row in common.PROFILE_RULES.items():
        rel, body = common.rule_paths(rid)
        text = body.read_text()
        assert not text.startswith("#") and text.splitlines()[0].strip() and "\n" not in row[2], rid
        assert "`%s`" % rel in row[2], rid                              # the headline names the file to read
    fin = (ROOT / "profiles/psx/rules/FIN1.md").read_text()
    assert "call it matched and name its debt" in fin and re.findall(r"(?m)^(\d)\. ", fin) == list("123456")
    for rid, row in common.PROFILE_RULES.items():   # the title line and the index row that the game's rules tool writes
        assert publish.lint_style("# %s — %s\n" % (rid, row[2])) == [], (rid, publish.lint_style("# %s — %s\n" % (rid, row[2])))
    assert "`python3 %s debt`" % floor.VENDORED in fin and floor.BASELINE in fin
    name = (ROOT / "profiles/psx/rules/NAME1.md").read_text()
    assert floor.NAMES in name and "| `oracle` | another build of the game, after a byte check of the function at both addresses" in name
    assert "| `debug-symbol` | a symbol of a debug file of the target build itself |" in name
    doc = (ROOT / "profiles/psx/floor.md").read_text()
    assert all("| `%s` |" % k in doc for k in floor.KINDS)
    assert "`%s`" % " ".join(floor.NAME_COLUMNS) in doc and "`%s`" % " ".join(floor.ASM_COLUMNS) in doc
    assert "`%s`" % " ".join(floor.TOOL_COLUMNS) in doc and all("`%s`" % c in doc for c in floor.ASM_CLASSES)
    for row in ("roadmap", "guard", "gate", "toolchain", "names", "debt", "cpp", "progress"):
        assert "| `%s` | " % row in doc and row in doctor.ROWS, row
    assert "`VERIFY OK`" in doc and "`VERIFY FAIL: <the command to run>`" in doc and "`make verify`" in doc


# ---- the one published number (publish.py lint `numbers`, validate) -------------------------------------------------

def test_readme_numbers_lint(tmp_path):
    """The decomp.dev report is the one published number. `lint` fails a percent or an `N of M` count typed under
    `## Progress`; the generated block says in one sentence what the number counts. A numbers block of the game's own
    that a tool generated is a WARN, also at --release (a game's next ship is not blocked); one with no `generated by`
    line fails."""
    repo = _git_copy(ROOT / "fixtures/publish", tmp_path / "game")
    lint = lambda *a: run([PY, ROOT / "scripts/publish.py", "lint", repo / "README.md", *a], check=False)  # noqa: E731
    readme, end = (repo / "README.md").read_text(), publish.marker("progress", True) + "\n"
    assert publish.PROGRESS_NOTE in readme and readme.count(end) == 1
    (repo / "README.md").write_text(readme.replace(end, end + "\nWe are 22.1% done: 1689 of 7647 functions.\n"))
    r = lint()
    assert r.returncode == 1 and r.stdout.count("README FAIL numbers: line ") == 2, r.stdout
    assert "`22.1%`" in r.stdout and "`1689 of 7647`" in r.stdout, r.stdout
    block = "%s\n<!-- generated by tools/progress.py write -->\n**Progress:** 5 of 9 (55.5%%).\n%s\n" % publish.GAME_BLOCK
    (repo / "README.md").write_text(readme.replace(end, end + "\n" + block))
    for args in ((), ("--release",)):
        r = lint(*args)
        assert r.returncode == 0 and "README WARN numbers: line " in r.stdout and "LINT OK (1 warn)" in r.stdout, r.stdout
    (repo / "README.md").write_text(readme.replace(end, end + "\n" + block.replace(
        "<!-- generated by tools/progress.py write -->\n", "")))
    r = lint()
    assert r.returncode == 1 and "has no `<!-- generated by … -->` line" in r.stdout, r.stdout


def test_report_honesty(tmp_path):
    """`validate` on the synthetic report: every unit names a C source. A unit whose source is assembly and that
    reports matched code is an error. The matched functions of 8 bytes or less are counted per top-level category,
    as INFO lines that never fail."""
    units = json.loads((ROOT / "fixtures/publish/units.json").read_text())
    assert all(u["metadata"]["source_path"].endswith(".c") for u in units["units"])
    cats = ROOT / "fixtures/publish/config/categories.tsv"

    def validate(doc):
        (tmp_path / "units.json").write_text(json.dumps(doc))
        run([PY, ROOT / "scripts/publish.py", "categorize", tmp_path / "units.json", "--categories", cats, "-o",
             tmp_path / "report.json"])
        return run([PY, ROOT / "scripts/publish.py", "validate", tmp_path / "report.json", "--categories", cats],
                   check=False)

    r = validate(units)
    assert r.returncode == 0 and "REPORT OK" in r.stdout and "REPORT INFO" not in r.stdout, r.stdout
    units["units"][0]["functions"] = [{"name": "a", "size": "8", "fuzzy_match_percent": 100.0},
                                      {"name": "b", "size": "64", "fuzzy_match_percent": 100.0},
                                      {"name": "c", "size": "4", "fuzzy_match_percent": 50.0}]
    r = validate(units)
    assert r.returncode == 0 and "REPORT INFO game: 1 of 2 matched functions are 8 bytes or less\n" in r.stdout, r.stdout
    units["units"][0]["metadata"]["source_path"] = "asm/main/boot.s"
    r = validate(units)
    assert r.returncode == 1 and "REPORT ERROR units[0] (main/boot): its source 'asm/main/boot.s' is not a C file" in r.stdout


def test_readme_workflow_names_the_ladder():
    """The README's Workflow section follows the kit's eleven phases: six stages whose ranges cover 1.0 to 1.10 with no
    gap, the link to the one home of the numbering, and the sentence that keeps matched apart from finished."""
    readme = (ROOT / "README.md").read_text()
    section = readme.split("\n## Workflow\n", 1)[1].split("\n## ", 1)[0]
    stages = re.findall(r"(?m)^\d\. \*\*(\w+) \(1\.(\d+)(?: to 1\.(\d+))?\)\.\*\*", section)
    assert [s[0] for s in stages] == ["Foundation", "Compiler", "Instruments", "Campaign", "Publication", "Readability"]
    covered = [n for _, a, b in stages for n in range(int(a), int(b or a) + 1)]
    assert covered == [n for n, _, _, _ in plan.LADDER], covered
    assert "(profiles/psx/floor.md#numbering)" in section and "## Numbering" in (ROOT / "profiles/psx/floor.md").read_text()
    assert "A matched function is not a finished one." in section and "```mermaid" in section


def test_exemplar_credit():
    """The three exemplar projects are credited where a reader looks: the README's Thanks, a row of the ecosystem
    ledger with the commit and the licence read, and a `link` row of the profile's reference library. The reuse rules
    say what a repository without a licence gives."""
    readme = (ROOT / "README.md").read_text().split("\n## Thanks\n", 1)[1].split("\n## ", 1)[0]
    eco = (ROOT / "docs/ECOSYSTEM.md").read_text()
    rows = {r["name"]: r for r in fetch_refs.load_rows(ROOT / "profiles/psx/refs.toml")}
    for owner, repo, licence in (("khasinski", "parasite-eve-decomp", "none selected"),
                                 ("sushi-shi", "kings-field-decomp", "CC0-1.0"),
                                 ("cdlewis", "snowboardkids2-decomp", "none")):
        url = "https://github.com/%s/%s" % (owner, repo)
        assert "(%s) by %s" % (url, owner) in readme or "(%s) and its sibling projects by %s" % (url, owner) in readme
        line = next(l for l in eco.splitlines() if l.startswith("| [%s/%s](%s) |" % (owner, repo, url)))
        cells = [c.strip() for c in line.strip("|").split("|")]
        assert re.fullmatch(r"`[0-9a-f]{7}`", cells[1]) and cells[2] == "2026-10-12" and cells[4].startswith(licence), cells
        row = rows[repo]
        assert row["class"] == "link" and row["url"] == url and "exemplar" in row["topics"], row
        assert cells[1].strip("`") in row["licence"] and "psxdecomp 0.6.0" in row["used_by"], row
    assert "gives ideas only" in eco.split("## Rules for reuse", 1)[1]


def test_campaign_templates():
    """profiles/psx/campaign.md (delivered as docs/ops/psxdecomp-campaign.md): the columns of the bank and wave ledgers,
    the two budgets, the sandbox path, the give-up report with its blockers in triage order, and a "Matcher workflow"
    section of at most 30 lines (PA3's skill_add.py captures no more). The matcher is offered as a manual line of
    upgrade, never installed."""
    import upgrade
    doc = (ROOT / "profiles/psx/campaign.md").read_text()
    sec = lambda h: doc.split("\n## %s\n" % h, 1)[1].split("\n## ", 1)[0]  # noqa: E731
    for col in ("binary", "address", "symbol", "words", "state", "best", "attempts", "wave", "commit", "blocker"):
        assert "| `%s` | " % col in sec("The bank ledger"), col
    waves = sec("The wave ledger")
    for col in ("wave", "opened", "closed", "task", "drawn", "banked", "set_aside", "no_verdict", "tokens_k", "gate"):
        assert "`%s`" % col in waves, col
    assert "20 minutes" in sec("Budgets") and "ten attempts" in sec("Budgets")
    assert "`.run/sandbox/<symbol>/attempt-NN.c`" in sec("The sandbox")
    report = sec("The give-up report")
    assert all("| `%s` | " % f in report for f in ("symbol", "best", "attempts", "tried", "blocker", "next"))
    assert re.findall(r"(?m)^\d\. `([a-z-]+)`\.", report) == ["referent", "call-set", "cfg", "types", "unknown"]
    matcher = sec("Matcher workflow").strip("\n").split("\n")
    assert 8 <= len(matcher) <= 30 and all(re.match(r"\d+\. ", l) for l in matcher), len(matcher)
    assert upgrade.MATCHER_LINE.startswith("PY tools/skill_add.py matcher --from %s#Matcher " % upgrade.CAMPAIGN_DOC)
    d = next(d for d in upgrade.DELIVERY if d.path == upgrade.CAMPAIGN_DOC)
    assert (d.cls, d.own, d.src) == ("owned", "campaign", "profiles/psx/campaign.md")
    assert not [d for d in upgrade.DELIVERY if d.path.startswith(upgrade.MATCHER_SKILL)]


def test_prompt_examples():
    """Each of the five prompts that asks a model for a shaped output shows one: an `<example>` block whose body is one
    fenced block (a fence is exempt from the style, scope and copy lints, so an example never counts as the repo's own
    claim). The examples name invented games only."""
    for rel in ("agents/scout-web.md", "agents/scout-repo.md", "skills/new/reference/investigate.md",
                "skills/new/reference/gate.md", "skills/upgrade/SKILL.md"):
        text = (ROOT / rel).read_text()
        blocks = re.findall(r"<example>\n\n```\n(.*?)\n```\n\n</example>", text, re.S)
        assert len(blocks) == 1 and text.count("<example>") == text.count("</example>") == 1, rel
        assert 3 <= len(blocks[0].splitlines()) <= 14 and "```" not in blocks[0], rel
        assert not re.search(r"mmx\d|Mega Man|Dino Crisis|BFM|SLUS-0[1-9]", blocks[0]), rel
