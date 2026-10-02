"""Tier 0: free, every push. Manifests, schemas, invocation-only skills, links, the repo's own firewall."""
import json
import pathlib
import re
import shutil
import sys
import tomllib

import pytest

from conftest import PY, ROOT, run

import answers
import fetch_refs


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


def test_answers_fixtures():
    for f in [ROOT / "fixtures/answers.psx.txt"] + sorted((ROOT / "fixtures/backtest").glob("*.answers.txt")):
        v, note = answers.parse(f.read_text())
        assert answers.check(v, allow_no_dump=True) == [], f
        assert answers.render(v, note, extras=True) == f.read_text(), "%s does not round-trip" % f
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
        sc = d.get("context", {}).get("scaffold_script")
        if sc:
            assert (case.parent / sc).is_file()
    assert {"no-autofire", "interview-first", "answers-path", "refs-grep", "refuse-nonpsx", "backtest-x6",
            "backtest-dc2", "backtest-bfm", "poisoned-grep", "poisoned-grep-raw", "unpinned-candidate",
            "kit-calibration-scope", "id-collision"} <= names


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
    """One home per fact: no prose sentence of 60+ characters appears in two of psxdecomp's docs (lint_dupes)."""
    dupes = fetch_refs.lint_dupes(list(_docs()), ROOT)
    assert not dupes, ["%s: %s" % (", ".join(w), t[:80]) for t, w in dupes]
