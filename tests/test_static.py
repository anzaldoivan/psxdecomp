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
            "kit-calibration-scope", "id-collision", "id-collision-tool", "restart-handoff", "psyq-question"} <= names


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
              "profiles/psx/private/README.md", "profiles/psx/rules/")


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
    docs); CLAUDE.md only imports it."""
    text = (ROOT / "AGENTS.md").read_text()
    assert len(text.splitlines()) <= 50 and len(text.encode()) <= 4096, (len(text.splitlines()), len(text.encode()))
    assert (ROOT / "CLAUDE.md").read_text().strip() == "@AGENTS.md"


def test_always_loaded_bytes(tmp_path):
    """Tier 4a: the bytes a session loads before it does anything (AGENTS.md and CLAUDE.md, the listing text of each
    skill Claude may invoke on its own, each agent's and command's description, the SessionStart hook's stdout in an
    empty folder and in a paused bootstrap) are a golden file: growth is a reviewed diff. An invocation-only skill's
    description is not in context, so it has no line. The listing cap is Claude Code's 1,536 characters. Not covered:
    .mcp.json, hook events other than SessionStart, output styles."""
    items = {n: (ROOT / n).read_text() for n in ("AGENTS.md", "CLAUDE.md")}
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
                "profiles/psx/psxdecomp-readme.yml", "profiles/psx/split-mode.md"):
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
    `python3` from the project directory. profiles/psx/rules/STE1.md is a rule body with no title line: the game's
    rules_add.py writes the title. It says what it is (in the style of ASD-STE100) and claims no compliance."""
    conf = json.loads((ROOT / "profiles/psx/hooks.json").read_text())
    assert conf == json.loads(common.read(common.PROFILE_HOOKS)) and list(conf) == ["hooks"], list(conf)
    assert list(conf["hooks"]) == ["PostToolUse"] and len(conf["hooks"]["PostToolUse"]) == 1, conf["hooks"]
    group = conf["hooks"]["PostToolUse"][0]
    assert set(group["matcher"].split("|")) == {"Write", "Edit", "Bash"}, group["matcher"]
    assert [h["type"] for h in group["hooks"]] == ["command"], group["hooks"]
    cmd = group["hooks"][0]["command"]
    assert cmd.startswith("python3 ") and cmd.endswith(" style --hook"), cmd
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


# ---- the floor (scripts/floor.py, vendored into a game as tools/psxd_floor.py) --------------------------------------

def _floor(*args, cwd=None, stdin=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **GIT_ENV)
    env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run([PY, str(ROOT / "scripts/floor.py"), *map(str, args)], input=stdin, cwd=cwd,
                          capture_output=True, text=True, env=env)


def test_floor_is_vendorable():
    """scripts/floor.py runs alone in a game repository: standard library only, nothing from the plugin. It imports
    tomllib inside a function only, so `guard --hook` also runs on a python3 that has none."""
    text = (ROOT / "scripts/floor.py").read_text()
    mods = set(re.findall(r"^(?:import|from) ([\w.]+)", text, re.M))
    assert mods == {"__future__", "argparse", "fnmatch", "hashlib", "json", "os", "pathlib", "re", "subprocess", "sys",
                    "tempfile"}, mods
    assert re.search(r"^ +import tomllib$", text, re.M) and floor.VENDORED == "tools/psxd_floor.py"
    assert len(floor.LADDER) == 11 and [r[0] for r in floor.LADDER] == list(range(11))


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
    assert rows == want and mode == "admit" and skip == ["include/include_asm.h"] and len(head) == 5, rows
    assert {k for k, _ in rows} == set(floor.KINDS) - {"unbased"}
    (repo / "config").mkdir()
    (repo / floor.BASELINE).write_text(floor.first_baseline(repo))
    r = _floor("debt", "--repo", repo)
    assert r.returncode == 0 and r.stdout.endswith("DEBT CHECK OK (0 rise(s), 0 stale row(s); mode admit)\n"), r.stdout
    _floor("names", "--init", "--repo", repo)                           # the ledger exists: every other name is unbased
    r = _floor("debt", "--repo", repo)
    assert r.returncode == 1 and "DEBT FAIL rise unbased src/clean.c: 1, its row is 0\n" in r.stdout, r.stdout


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
