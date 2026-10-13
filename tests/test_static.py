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
            "s7-ladder"} <= names


def test_s7_ladder_eval_reads_the_ladder():
    """The `s7-ladder` case grades the constitution a real S7 writes. It has one file grader for each of the eleven
    ladder phases. They pass on a text that names the phases as floor.LADDER holds them, in the list form and in the
    kit's table form. A text that lacks any one phase fails the grader of that phase, and so do prose that only
    holds the words and the two-phase fixture constitution: the canned fixture can never stand in for the intake."""
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load((ROOT / "evals/s7-ladder/case.yaml").read_text())
    gs = [g for g in d["graders"] if g["type"] == "regex" and isinstance(g.get("target"), dict)]
    assert len(gs) == len(floor.LADDER) and all(g["target"] == {"source": "file", "path": floor.CONTEXT} for g in gs), gs
    lines = ["- **Phase 1.%d %s** — milestone: m" % (n, name) for n, name, _, _ in floor.LADDER]
    rows = ["| %d | **%s** | m |" % (n, name) for n, name, _, _ in floor.LADDER]
    for full in ("\n".join(lines), "\n".join(rows)):
        assert floor.ladder_missing(full) == [] and all(_passes(g, full) for g in gs), [g["name"] for g in gs if not _passes(g, full)]
    for n in range(len(lines)):
        less = "\n".join(l for i, l in enumerate(lines) if i != n)
        failed = [g["name"] for g in gs if not _passes(g, less)]
        assert failed == [gs[n]["name"]] and floor.ladder_missing(less) == [n], (n, failed)
    prose = "The kit's ladder: governance and the firewall, extraction, the oracles and the load map, the all-assembly " \
            "baseline, the compiler pinned by evidence, the census, the multipliers, the codegen map, the campaign, " \
            "publish, readability.\n10 things to do.\n"
    assert not any(_passes(g, prose) for g in gs) and floor.ladder_missing(prose) == list(range(11))
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
    assert "tools/psxd_publish.py lint README.md" in wf and "--history" in wf and "fetch-depth: 0" in wf


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
    assert cmd.startswith("python3 ") and cmd.endswith(" style --hook || exit 0"), cmd
    for groups in conf["hooks"].values():           # every hook of the profile: one that cannot start never disturbs a call
        assert all(h["command"].endswith(" || exit 0") for g in groups for h in g["hooks"]), groups
    assert '"$CLAUDE_PROJECT_DIR/%s"' % publish.VENDORED in cmd and publish.VENDORED == "tools/psxd_publish.py", cmd
    assert common.PROFILE_STE == ROOT / "profiles/psx/rules/STE1.md"
    rule = common.PROFILE_STE.read_text()
    flat = " ".join(rule.split())
    assert not rule.startswith("#") and rule.splitlines()[0].strip(), rule[:80]
    assert "in the style of ASD-STE100" in flat and "`python3 %s style <file>`" % publish.VENDORED in flat
    assert "compliant" not in flat.lower()
    assert common.STE_RULE in publish.style_hook_message([]) and common.STE_RULE == "rules/STE1.md"


def test_style_workflow_step():
    """The game's README workflow runs `style` (every public prose file against the ratchet), in a step of its own
    after the README lint step."""
    lines = [l.strip() for l in (ROOT / "profiles/psx/psxdecomp-readme.yml").read_text().splitlines()]
    runs = [l for l in lines if l.startswith("run: ")]
    lint, style = "run: python3 %s lint README.md" % publish.VENDORED, "run: python3 %s style" % publish.VENDORED
    assert runs.count(lint) == 1 and runs.count(style) == 1 and runs.index(lint) < runs.index(style), runs
    assert lines[lines.index(style) - 1].startswith("- name: ") and "style" in lines[lines.index(style) - 1]
    debt = "run: python3 %s debt" % floor.VENDORED                      # the debt of the source, after the style step
    assert runs.count(debt) == 1 and runs.index(style) < runs.index(debt), runs
    assert lines[lines.index(debt) - 1].startswith("- name: ") and floor.BASELINE in lines[lines.index(debt) - 1]


# ---- the floor (scripts/floor.py, vendored into a game as tools/psxd_floor.py) --------------------------------------

def _floor(*args, cwd=None, stdin=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **GIT_ENV)
    env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run([PY, str(ROOT / "scripts/floor.py"), *map(str, args)], input=stdin, cwd=cwd,
                          capture_output=True, text=True, env=env)


def test_floor_is_vendorable():
    """scripts/floor.py runs alone in a game repository: standard library only, nothing from the plugin, at any depth
    of its code (its copy passes its own self-test in a folder that holds nothing else). It imports no tomllib, so the
    hook and the debt count give one result on a python3 that has none."""
    text = (ROOT / "scripts/floor.py").read_text()
    mods = set(re.findall(r"^\s*(?:import|from) ([\w.]+)", text, re.M))
    assert mods == {"__future__", "argparse", "bisect", "contextlib", "fnmatch", "hashlib", "io", "json", "os", "pathlib", "re", "signal",
                    "subprocess", "sys", "tempfile", "time"}, mods
    assert floor.VENDORED == "tools/psxd_floor.py"
    assert len(floor.LADDER) == 11 and [r[0] for r in floor.LADDER] == list(range(11))


def test_vendored_tools_run_alone(tmp_path):
    """Each vendored tool, copied alone into a game's tools/ and run there with `-I` (no plugin folder on the path):
    the floor passes its whole self-test; the publish tool lints a README and answers the style hook. An import of the
    plugin inside a function would fail here, where the import test of the file's top level cannot see it."""
    game = _style_repo(tmp_path, {"README.md": "# G\n\nA game.\n", "src/a.c": floor.C_CLEAN})
    (game / "tools").mkdir()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **GIT_ENV)
    env.pop("CLAUDE_PROJECT_DIR", None)
    for src, dst in (("scripts/floor.py", floor.VENDORED), ("scripts/publish.py", publish.VENDORED)):
        (game / dst).write_bytes((ROOT / src).read_bytes())
    alone = lambda *a, **kw: subprocess.run([PY, "-I", *a], cwd=game, capture_output=True, text=True, env=env, **kw)  # noqa: E731
    r = alone(floor.VENDORED, "--self-test")
    assert r.returncode == 0 and r.stdout.strip().endswith("SELF-TEST OK"), r.stdout[-600:] + r.stderr[-600:]
    for args in ((publish.VENDORED, "lint", "README.md"), (publish.VENDORED, "style"), (floor.VENDORED, "debt"),
                 (floor.VENDORED, "plan"), (floor.VENDORED, "names")):
        r = alone(*args)
        assert r.returncode in (0, 1) and "Traceback" not in r.stderr and "Error" not in r.stderr, (args, r.stderr[-400:])
    event = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": str(game),
                        "tool_input": {"file_path": str(game / "README.md")}})
    for tool, flag in ((publish.VENDORED, "style"), (floor.VENDORED, "guard")):
        r = alone(tool, flag, "--hook", input=event)
        assert r.returncode == 0 and r.stderr == "", (tool, r.stderr[-400:])


def test_hook_commands_never_fail(tmp_path):
    """Each hook command of the profile, run by a shell as Claude Code runs it, exits 0 when it cannot do its work:
    with no tool in the repository yet, and with a tool that cannot start (a Python that lacks a module it needs)."""
    conf = json.loads((ROOT / "profiles/psx/hooks.json").read_text())["hooks"]
    cmds = [h["command"] for groups in conf.values() for g in groups for h in g["hooks"]]
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp_path), PATH=os.path.dirname(PY) + os.pathsep + os.environ["PATH"])
    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, input="{}", capture_output=True, text=True, env=env)
        assert r.returncode == 0, (cmd, r.stderr)                       # no tools/ folder: the tool is not there
    (tmp_path / "tools").mkdir()
    for name in (floor.VENDORED, publish.VENDORED):
        (tmp_path / name).write_text("import a_module_this_python_lacks\n")
    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, input="{}", capture_output=True, text=True, env=env)
        assert r.returncode == 0, (cmd, r.stderr)


def test_hook_groups_by_kind(tmp_path):
    """.claude/settings.json and the profile's hooks: a group is present by its kind, so a game that set its own
    interpreter keeps its command and is asked for nothing. A group that holds what an earlier psxdecomp wrote (the
    style command with no `|| exit 0`, the guard with no time limit and the earlier matcher) is stale: the settings
    write replaces it where it stands and adds no second group."""
    prof = json.loads((ROOT / "profiles/psx/hooks.json").read_text())["hooks"]
    old = {"hooks": {
        "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "true"}]},
                        {"matcher": "Write|Edit|Bash", "hooks": [{"type": "command", "command": common.HOOK_BEFORE["style-hook"][0][0]}]}],
        "PreToolUse": [{"matcher": "Bash|Edit|Write", "hooks": [{"type": "command", "command": prof["PreToolUse"][0]["hooks"][0]["command"]}]}]},
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
    """publish.debt_gate: the release gate refuses a tree whose debt baseline is not equal to its source, with the
    command that updates it. An equal baseline passes. A tree without the floor's tool or without a baseline has no
    such check in its public CI, and passes."""
    tree = _style_repo(tmp_path, {"src/a.c": floor.C_DEBT["goto"][0], floor.BASELINE: "mode admit\n",
                                  floor.VENDORED: (ROOT / "scripts/floor.py").read_text()})
    assert (publish.FLOOR_TOOL, publish.DEBT_BASELINE) == (floor.VENDORED, floor.BASELINE)
    got = publish.debt_gate(tree)
    assert len(got) == 1 and "DEBT CHECK FAIL (1 rise(s)" in got[0] and "debt --update --admit" in got[0], got
    (tree / floor.BASELINE).write_text("mode admit\n1 goto src/a.c\n")
    assert publish.debt_gate(tree) == []
    (tree / floor.BASELINE).write_text("mode admit\n2 goto src/a.c\n")           # a stale row fails too
    assert len(publish.debt_gate(tree)) == 1 and "debt --update --admit" in publish.debt_gate(tree)[0]
    (tree / floor.BASELINE).write_text("mode admit\n1 goto src/a.c\n1 goto src/private.c\n")   # a row of a file that is not published
    got = publish.debt_gate(tree)
    assert len(got) == 1 and "src/private.c" in got[0] and "public-paths.txt" in got[0] and "--update" not in got[0], got
    (tree / floor.BASELINE).unlink()
    assert publish.debt_gate(tree) == []
    (tree / floor.BASELINE).write_text("mode admit\n")
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
    """`floor.py plan` on synthetic plans: the ladder as written passes; a slice stands for its phase; a merge with a
    `## Changes` line passes; a dropped phase exits 1 with a `ladder` FAIL; a generation-2 plan reads the ladder from
    the closed generation's record; a line with a lost key exits 1 with a `grammar` FAIL."""
    repo = _style_repo(tmp_path, {"GENERATION_PLAN.md": floor.self_plan(closed=0)})
    plan = repo / "GENERATION_PLAN.md"
    r = _floor("plan", "--repo", repo)
    assert r.returncode == 0 and r.stdout.endswith("PLAN OK (0 fail, 0 warn)\n"), r.stdout
    assert "PLAN INFO state: generation 1; ladder phases open 0; pending 1,2,3,4,5,6,7,8,9,10\n" in r.stdout, r.stdout
    slices = [floor._phase("1.8.1", "The campaign, slice 1", milestone="0 stubs", depends="1.7"),
              floor._phase("1.8.2", "The campaign, slice 2", depends="1.8.1")]
    plan.write_text(floor.self_plan(closed=0, drop=(8,), extra=slices).replace("depends: 1.8 |", "depends: 1.8.2 |"))
    assert _floor("plan", "--repo", repo).returncode == 0
    dropped = floor.self_plan(closed=0, drop=(6,)).replace("depends: 1.6 |", "depends: 1.5 |")
    plan.write_text(dropped)
    r = _floor("plan", "--repo", repo)
    assert r.returncode == 1 and "PLAN FAIL ladder: no line 1.6 (The multipliers)" in r.stdout, r.stdout
    assert r.stdout.endswith("PLAN FAIL (1 fail, 0 warn)\n"), r.stdout
    plan.write_text(dropped + "- 2026-01-02 developer: phases 1.5 and 1.6 merged into 1.5 — a small game\n")
    assert _floor("plan", "--repo", repo).returncode == 0
    plan.write_text(floor.self_plan(closed=0).replace(" | scope: s", "", 1))
    r = _floor("plan", "--repo", repo)
    assert r.returncode == 1 and "PLAN FAIL grammar: line 11 (1.0): no `scope:`" in r.stdout, r.stdout
    plan.write_text("# Generation 2 — next\n\nGoal: g\nDone-criteria: d\n\n## Phases\n\n%s\n\n## Changes\n"
                    % floor._phase("2.1", "The round-trip disc"))
    r = _floor("plan", "--repo", repo)
    assert r.returncode == 0 and "PLAN WARN ladder: generation 2 and no phase-ends/GenerationEnd_1.md" in r.stdout
    (repo / "phase-ends").mkdir()
    (repo / "phase-ends/GenerationEnd_1.md").write_text("# GenerationEnd\n\n## Phases\n" + "".join(
        "- 1.%d | %s | milestone: m\n" % (n, name) for n, name, _, _ in floor.LADDER))
    r = _floor("plan", "--repo", repo)
    assert r.returncode == 0 and r.stdout.endswith("PLAN OK (0 fail, 0 warn)\n"), r.stdout
    plan.unlink()
    r = _floor("plan", "--repo", repo)
    assert r.returncode == 0 and r.stdout.startswith("PLAN INFO plan: no GENERATION_PLAN.md"), r.stdout
    assert _floor("ladder", ROOT / "fixtures/PROJECT_CONTEXT.fixture.md").returncode == 1      # the fixture names two


def test_debt_kinds(tmp_path):
    """One planted file per debt kind and one clean control in a git repository: the first baseline holds exactly the
    planted counts, and `debt` passes against it."""
    files = {"src/clean.c": floor.C_CLEAN}
    files.update({"src/%s.c" % kind: text for kind, (text, _) in floor.C_DEBT.items()})
    repo = _style_repo(tmp_path, files)
    rows, skip, mode, head = floor.parse_baseline(floor.first_baseline(repo))
    want = {(k, "src/%s.c" % kind): n for kind, (_, got) in floor.C_DEBT.items() for k, n in got.items()}
    assert rows == want and mode == "admit" and skip == [] and len(head) == 5, rows      # no stub header here: no skip line
    assert {k for k, _ in rows} == set(floor.KINDS) - {"unbased"}
    (repo / "config").mkdir()
    (repo / floor.BASELINE).write_text(floor.first_baseline(repo))
    r = _floor("debt", "--repo", repo)
    assert r.returncode == 0 and r.stdout.endswith("DEBT CHECK OK (0 rise(s), 0 stale row(s); mode admit)\n"), r.stdout
    _floor("names", "--init", "--repo", repo)                           # the ledger exists: every other name is unbased
    r = _floor("debt", "--repo", repo)
    assert r.returncode == 1 and "DEBT FAIL rise unbased src/clean.c: 1, its row is 0\n" in r.stdout, r.stdout


def test_debt_bodies(tmp_path):
    """The counts by function body: on every C fixture of this repository the sum of a file's bodies is its count,
    each file of the corpus is one body, and a pin, a goto and an offset read never fall outside a body.
    `debt --bodies` prints the buckets of a revision as well."""
    files = sorted((ROOT / "fixtures").glob("**/*.c")) + sorted((ROOT / "fixtures").glob("**/*.h"))
    assert len(files) > 100
    for f in files:
        text, total = f.read_text(), {}
        bodies = floor.file_bodies("src/t.c", text, based=set())
        for got in bodies.values():
            for kind, n in got.items():
                total[kind] = total.get(kind, 0) + n
        assert total == floor.file_debt("src/t.c", text, based=set()), f
        assert not set(bodies.get(floor.SCOPE, {})) & {"pin", "pin-unmarked", "goto", "offset", "asm"}, (f, bodies)
        if f.suffix == ".c":
            assert len([n for n in bodies if n != floor.SCOPE]) == 1, (f, sorted(bodies))
    repo = _style_repo(tmp_path, {"src/a.c": floor.C_BODIES["two plain bodies"][0]})
    (repo / "src/a.c").write_text(floor.C_CLEAN)
    r = _floor("debt", "--bodies", "--rev", "HEAD", "--repo", repo)
    assert r.returncode == 0 and "DEBT BODY src/a.c A: offset 1\nDEBT BODY src/a.c B: goto 1\n" in r.stdout, r.stdout
    assert "DEBT BODIES 1 file(s), 2 function bodies, 2 with debt, 0 count(s) at file scope" in r.stdout
    assert "DEBT BODIES 1 file(s), 1 function bodies, 0 with debt" in _floor("debt", "--bodies", "--repo", repo).stdout


def test_debt_against_rev(tmp_path):
    """The tree reader: the work tree, the index and a revision give one count, on an LF checkout and on a CRLF one.
    `debt --against` prints what differs from a revision. `style --against` judges the prose by the ratchet, the
    `skip` lines and the public list of the revision: a raised row, a new `skip` line and a file that left the public
    list change nothing."""
    files = {"src/a.c": floor.C_DEBT["goto"][0], "src/m.c": floor.C_DEBT["macro"][0],
             "src/o.c": "s32 Walk(void *p) {\n    return HP(p);\n}\n",
             "include/h.h": "#define HP(p) \\\n    (*(s16 *)((u8 *)(p) + 0x10))\n",
             "README.md": "# G\n\nOne; two.\n", "docs/a.md": "Clean.\n",
             publish.STYLE_RATCHET_REL: "1 README.md\n", publish.PUBLIC_PATHS_REL: "README.md\ndocs/\n"}
    repo = _style_repo(tmp_path, files)
    debt = lambda *a: _floor("debt", "--repo", repo, *a)  # noqa: E731
    totals = lambda r: re.search(r"totals: ([^(]+) \(", r.stdout)[1]  # noqa: E731
    want = "goto 1, offset 2, macro 3"
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
    r = debt("--against", "HEAD")
    assert "DEBT INFO against HEAD: goto src/a.c: 1 -> 2\n" in r.stdout and "(1 count(s) rose, 0 fell)" in r.stdout
    assert totals(debt("--staged")) == want                                     # not added yet
    run(["git", "-C", repo, "add", "src/a.c"])
    assert totals(debt("--staged")) == "goto 2, offset 2, macro 3" and totals(debt("--rev", "HEAD")) == want
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
    assert len(got) == 1 and "DEBT CHECK FAIL (1 rise(s)" in got[0], got


def test_debt_baseline_command(tmp_path):
    """The equal-baseline rule through the command line: a rise exits 1, `--update` refuses it without `--admit`,
    `--admit` prints it, a stale row exits 1, `--down` is one way and then no rise is admitted."""
    repo = _style_repo(tmp_path, {"src/a.c": floor.C_DEBT["goto"][0], "config/debt-baseline.txt": "mode admit\n"})
    debt = lambda *a: _floor("debt", "--repo", repo, *a)  # noqa: E731
    r = debt()
    assert r.returncode == 1 and "DEBT FAIL rise goto src/a.c: 1, its row is 0\n" in r.stdout, r.stdout
    assert debt("--update").returncode == 1 and (repo / floor.BASELINE).read_text() == "mode admit\n"
    r = debt("--update", "--admit")
    assert r.returncode == 0 and "DEBT ADMIT goto src/a.c: 0 -> 1\n" in r.stdout, r.stdout
    assert (repo / floor.BASELINE).read_text().endswith("mode admit\n1 goto src/a.c\n") and debt().returncode == 0
    (repo / "src/a.c").write_text(floor.C_CLEAN)
    r = debt()
    assert r.returncode == 1 and "DEBT FAIL stale goto src/a.c: 0, its row is 1" in r.stdout, r.stdout
    assert debt("--down").returncode == 1 and debt("--update").returncode == 0 and debt("--down").returncode == 0
    assert "mode down\n" in (repo / floor.BASELINE).read_text()
    (repo / "src/a.c").write_text(floor.C_DEBT["goto"][0])
    r = debt("--update", "--admit")
    assert r.returncode == 1 and "`mode down` admits none" in r.stdout, r.stdout


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
    exit code 0. An allowed call, bad JSON, no event, and a repository with no rules file print nothing, exit code 0:
    the guard never stops a session by failing."""
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
    silent = {"an allowed edit": ev("Edit", file_path=str(repo / "src/a.c")), "an allowed command": ev("Bash", command="ls"),
              "bad JSON": "{not json", "no event": ""}
    for name, stdin in silent.items():
        r = _floor("guard", "--hook", cwd=tmp_path, stdin=stdin)
        assert (r.returncode, r.stdout) == (0, ""), (name, r.stdout, r.stderr)
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
    the vendored `guard --hook` and ends in `|| exit 0`, so a hook that cannot start never blocks a call. guard.tsv:
    the header line, five default `path` rules that parse, two examples as comments. deny.json: one `Edit(/...)` rule
    per default path, in Claude Code's rule syntax (a leading `/` is the project root)."""
    conf = json.loads((ROOT / "profiles/psx/hooks.json").read_text())["hooks"]["PreToolUse"]
    assert len(conf) == 1 and len(conf[0]["hooks"]) == 1, conf
    assert set(conf[0]["matcher"].split("|")) == {"Bash"} | set(floor.PATH_TOOLS), conf[0]["matcher"]   # every tool the guard reads
    assert 0 < conf[0]["hooks"][0]["timeout"] <= 30 and floor.GUARD_SECONDS < conf[0]["hooks"][0]["timeout"], conf
    cmd = conf[0]["hooks"][0]["command"]
    assert cmd == 'python3 "$CLAUDE_PROJECT_DIR/%s" guard --hook || exit 0' % floor.VENDORED, cmd
    assert common.hook_kind(conf[0]) == "guard-hook"
    post = json.loads((ROOT / "profiles/psx/hooks.json").read_text())["hooks"]["PostToolUse"][0]
    assert common.hook_kind(post) == "style-hook"
    text = common.PROFILE_GUARD.read_text()
    rules = floor.parse_guard(text)
    assert floor.guard_errors(text) == [] and "\t".join(floor.GUARD_COLUMNS) in text.splitlines()
    assert [r[:2] for r in rules] == [("deny", "path")] * 5 and all(r[3] for r in rules), rules
    assert len([l for l in text.splitlines() if l.startswith("# deny\tbash\t")]) == 2
    paths = [r[2] for r in rules]
    assert paths == ["asm/", "config/check.*.sha", "config/medium.sha1", floor.BASELINE, publish.STYLE_RATCHET_REL]
    deny = json.loads((ROOT / "profiles/psx/deny.json").read_text())["permissions"]["deny"]
    edits = [r for r in deny if r.startswith("Edit(")]
    assert edits == ["Edit(/%s)" % (p + "**" if p.endswith("/") else p) for p in paths], edits


def test_floor_doc_names_the_ladder():
    """profiles/psx/floor.md is the one home of the numbering: its table holds floor.LADDER row for row (the id 1.n,
    the kit's name, the words the milestone keeps), it starts with "After the bootstrap", and it documents every plan
    check and every guard column."""
    doc = (ROOT / "profiles/psx/floor.md").read_text()
    for n, name, _, must in floor.LADDER:
        assert "| 1.%d | %s | %s|" % (n, name, "`%s` " % must if must else "") in doc, n
    heads = [l[3:] for l in doc.splitlines() if l.startswith("## ")]
    assert heads[:2] == ["After the bootstrap", "Numbering"], heads
    for check in ("grammar", "ladder", "numbering", "frozen", "criteria", "paths", "markers"):
        assert "| `%s` | " % check in doc and "  %s " % check in floor.__doc__, check
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
    assert all("| `%s` |" % c in name for c in floor.EVIDENCE) and floor.NAMES in name
    doc = (ROOT / "profiles/psx/floor.md").read_text()
    assert all("| `%s` |" % k in doc for k in floor.KINDS)
    assert "`%s`" % " ".join(floor.NAME_COLUMNS) in doc and "`%s`" % " ".join(floor.ASM_COLUMNS) in doc
    assert "`%s`" % " ".join(floor.TOOL_COLUMNS) in doc and all("`%s`" % c in doc for c in floor.ASM_CLASSES)
    for row in ("roadmap", "guard", "gate", "toolchain", "names", "debt", "progress"):
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
    assert covered == [n for n, _, _, _ in floor.LADDER], covered
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
