"""Tier 1: the deterministic installer on the homebrew fixture (S0, S2, S5-S10 from canned answers)."""
import functools
import json
import os
import re
import shutil

import pytest

from conftest import PY, PY_TOKEN, ROOT, bootstrap, check_golden, hook_stdout, run, tree

import common

GOLDEN = ROOT / "tests" / "golden" / "fixture-tree.txt"


@pytest.fixture(scope="module")
def game(toolchain, tmp_path_factory):
    target = tmp_path_factory.mktemp("game") / "repo"
    r = bootstrap(toolchain, target)
    assert "BOOTSTRAP OK through S10" in r.stdout, r.stdout
    return target


def test_golden_tree(game):
    got = tree(game)
    if os.environ.get("PSXDECOMP_UPDATE_GOLDEN"):
        GOLDEN.write_text("\n".join(got) + "\n")
    want = GOLDEN.read_text().splitlines()
    assert got == want, "tree differs from tests/golden/fixture-tree.txt (PSXDECOMP_UPDATE_GOLDEN=1 after a pin bump)"


def test_always_loaded_bytes(game):
    """Tier 4a: the bytes a session in the bootstrapped repo loads first (CLAUDE.md, the card, settings, agents,
    skills, commands, rules without `paths:`, the hook's stdout) as a golden file; agent, command and skill files
    count whole, agents at any depth. Not covered: .mcp.json, hook events other than SessionStart, output styles. The
    interpreter path, its version, the host line and the bootstrap date are this machine's and this day's, so they
    count as tokens."""
    files = ["CLAUDE.md", "HOW_WE_WORK.md", ".claude/settings.json"]
    files += [p.relative_to(game).as_posix() for g in (".claude/agents/**/*.md", ".claude/commands/*.md",
                                                    ".claude/skills/*/SKILL.md")
              for p in game.glob(g)]
    files += [p.relative_to(game).as_posix() for p in game.glob(".claude/rules/*.md") if "\npaths:" not in p.read_text()]
    subs = ((PY_TOKEN, "<PY>"), (r"(?m)^- OS / shells: .*$", "- OS / shells: <HOST>"),
            (r"bootstrap, \d{4}-\d\d-\d\d", "bootstrap, <DATE>"))
    norm = lambda t: functools.reduce(lambda acc, s: re.sub(s[0], s[1], acc), subs, t)
    items = {f: norm((game / f).read_text()) for f in files}
    assert len((game / "CLAUDE.md").read_text().splitlines()) < 200
    items["hook:SessionStart"] = hook_stdout(game)
    check_golden(ROOT / "tests" / "golden" / "always-loaded-fixture.txt", items)


def test_clean_tree_and_commits(game):
    assert run(["git", "-C", game, "status", "--porcelain"]).stdout == ""
    log = run(["git", "-C", game, "log", "--format=%s"]).stdout.splitlines()[::-1]
    assert log[0].startswith("Firewall first") and len(log) == 9, log
    assert any(l.startswith("PA3 upgrades ask first") for l in log) and any(
        l.startswith("README: psxdecomp's README standard") for l in log), log


def test_s6_restart_line_and_upgrade_ask(toolchain, game):
    """S6's DONE line carries the whole restart line; pa.json says "upgrade": "ask", which PA3's own session hook
    reads as ask (no auto-upgrade off the pin), and the record says so."""
    import importlib
    import sys
    note = json.loads((game / ".run/bootstrap/state.json").read_text())["stages"]["S6"]["note"]
    assert "`claude --agent plain`" in note and "`/psxdecomp:new --resume`" in note, note
    assert json.loads((game / ".claude/pa.json").read_text())["upgrade"] == "ask"
    assert run(["git", "-C", game, "status", "--porcelain", ".claude/pa.json"]).stdout == ""
    sys.path.insert(0, str(toolchain["pkg"]))
    try:
        ss = importlib.import_module("pa.hooks.session_start")
        assert ss._upgrade_mode(str(game)) == "ask"
    finally:
        sys.path.remove(str(toolchain["pkg"]))
    assert 'upgrade = "ask"' in (game / "config/psxdecomp.toml").read_text()


def test_s10_writes_the_deny_rules_and_doctor_checks_them(game, tmp_path):
    """S10 puts every rule of profiles/psx/deny.json into the tracked .claude/settings.json beside PA3's own, in the
    handoff commit (still 9 commits); doctor's `deny` row is OK, and FAILs on a copy that lacks one rule."""
    want = json.loads((ROOT / "profiles/psx/deny.json").read_text())["permissions"]["deny"]
    have = json.loads((game / ".claude/settings.json").read_text())["permissions"]["deny"]
    assert set(want) <= set(have) and len(have) > len(want) and len(want) == 23, have
    assert run(["git", "-C", game, "status", "--porcelain", ".claude/settings.json"]).stdout == ""
    assert run(["git", "-C", game, "ls-files", ".claude/settings.json"]).stdout.strip()
    assert len(run(["git", "-C", game, "log", "--oneline"]).stdout.splitlines()) == 9
    ok = run([PY, ROOT / "scripts/doctor.py", "--repo", game, "--offline"], check=False)
    assert re.search(r"DOCTOR deny\s+OK", ok.stdout), ok.stdout
    import doctor
    names = re.findall(r"^DOCTOR (\S+) +(?:OK|WARN|FAIL|SKIP|WAIT) ", ok.stdout, re.M)
    assert len(names) >= 15 and set(names) <= set(doctor.ROWS), names        # --only knows every row a game prints
    assert re.search(r"DOCTOR card\s+OK\s+HOW_WE_WORK.md \d+ of 7000 characters", ok.stdout), ok.stdout
    bad = tmp_path / "copy"
    shutil.copytree(game, bad)
    conf = json.loads((bad / ".claude/settings.json").read_text())
    conf["permissions"]["deny"].remove(want[0])
    (bad / ".claude/settings.json").write_text(json.dumps(conf))
    r = run([PY, ROOT / "scripts/doctor.py", "--repo", bad, "--offline"], check=False)
    assert r.returncode == 1 and re.search(r"DOCTOR deny\s+FAIL\s+1 of 23", r.stdout), r.stdout


def test_ladder_matches_kit(kit):
    """floor.LADDER is the pinned kit's ladder: each phase's name is in row n of the ladder table of intake.decomp.md,
    its name words match that name, and each required milestone word is in row n of that table or of the
    `verified by` table. The kit's own table names all eleven phases."""
    import pathlib

    import floor
    part = (pathlib.Path(kit) / "intake.decomp.md").read_text().split("## Part B", 1)[1].split("\n## Part C", 1)[0]
    rows = {}
    for line in part.splitlines():
        m = re.match(r"^\| (\d+) \| (.*)$", line)
        if m:
            rows.setdefault(int(m[1]), []).append(m[2])
    assert sorted(rows) == list(range(11)) and all(len(v) == 2 for v in rows.values()), sorted(rows)
    for n, name, words, must in floor.LADDER:
        assert name in rows[n][0] and re.search(words, name, re.I), (n, name)
        assert not must or must in " ".join(rows[n]), (n, must)
    assert floor.ladder_missing(part) == []


def test_roadmap_row_waits_before_the_plan(game):
    """A fresh bootstrap has no GENERATION_PLAN.md: doctor's `roadmap` row says WAIT, which is no failure and is
    counted in the last line. S8 recorded that the fixture constitution names two of the eleven ladder phases."""
    r = run([PY, ROOT / "scripts/doctor.py", "--repo", game, "--offline"], check=False)
    assert r.returncode == 0, r.stdout
    assert re.search(r"^DOCTOR roadmap +WAIT no GENERATION_PLAN.md; PROJECT_CONTEXT.md names 2 of the 11 ladder phases; "
                     r"due when PA3's planner drafts the plan$", r.stdout, re.M), r.stdout
    assert re.search(r"^DOCTOR OK \(\d+ warn, \d+ not due(, \d+ not run)?\)$", r.stdout.splitlines()[-1]), r.stdout
    rec = (game / "config/psxdecomp.toml").read_text()
    assert "PROJECT_CONTEXT.md names 2 of the 11 ladder phases; not named: 1.2, 1.3" in rec, rec


def test_upgrade_has_nothing_to_do_after_the_bootstrap(game):
    """`upgrade plan` on the game S10 just handed off lists no action of psxdecomp's: S10 and upgrade deliver the same
    files, and the record holds the hash of each owned one."""
    import tomllib

    import upgrade
    r = run([PY, ROOT / "scripts/upgrade.py", "plan", "--repo", game])
    assert "[psxdecomp]" not in r.stdout and re.search(r"^PLAN \d+ action\(s\)", r.stdout, re.M), r.stdout
    rec = tomllib.loads((game / "config/psxdecomp.toml").read_text())
    rules = {common.rule_paths(rid)[0] for rid in common.PROFILE_RULES}      # a rule's body hash guards a later edit of it
    assert set(rec["delivered"]) == set(upgrade.OWNED) | rules and "own" not in rec, rec.get("delivered")
    assert all(len(v) == 64 for v in rec["delivered"].values())
    assert run([PY, ROOT / "scripts/upgrade.py", "apply", "--dry-run", "--repo", game]).stdout.startswith("APPLY DRY RUN 0 ")


def _headlines(game):
    """The lines of the project-architect skill's headline section: from the first heading that holds "headline" or
    "11" to the next heading (the section the game's `rules_add.py promote` writes to)."""
    lines = (game / ".claude/skills/project-architect/SKILL.md").read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("#") and ("headline" in l.lower()
                                                                           or re.search(r"[§#]\s?11\b", l)))
    end = next((j for j in range(start + 1, len(lines)) if lines[j].startswith("#")), len(lines))
    return lines[start + 1:end]


def _hook_group():
    groups = json.loads(common.read(common.PROFILE_HOOKS))["hooks"]["PostToolUse"]
    assert len(groups) == 1 and groups[0]["hooks"][0]["command"].endswith("style --hook || exit 0"), groups
    return groups[0]


def _ste_body(repo):
    """rules/STE1.md after its two header lines (the title line and the dated metadata line of rules_add.py)."""
    head, meta, body = (repo / common.STE_RULE).read_text().split("\n", 2)
    assert head == "# STE1 — %s" % common.STE_TITLE and meta.startswith("id: STE1 · group: STE · "), (head, meta)
    return body.strip()


def test_s10_writes_the_rule_and_does_not_promote_it(game):
    """S10 has the game's own rules_add.py write rules/STE1.md (the profile's body under the tool's two header lines)
    and its row of rules/INDEX.md. It never promotes the rule: the headline section of the project-architect skill,
    which every session loads, holds the kit's headlines and no STE1 line. Both files are in the handoff commit."""
    assert _ste_body(game) == common.read(common.PROFILE_STE).strip()
    index = (game / common.STE_INDEX).read_text().splitlines()
    assert index.count("STE1 | %s | writing,public | active | psxdecomp" % common.STE_TITLE) == 1, index[-3:]
    assert len([l for l in index if l.startswith("STE1 ")]) == 1
    heads = [l for l in _headlines(game) if l.startswith("- ")]
    assert any(re.match(r"- [A-Z]+\d+ — ", l) for l in heads), heads       # the section the kit promoted its rules to
    assert not [l for l in heads if l.startswith("- STE1")], heads
    assert "STE1" not in (game / ".claude/skills/project-architect/SKILL.md").read_text()
    assert common.ste_rule_state(game) is None
    handoff = run(["git", "-C", game, "show", "--name-only", "--format=", "HEAD"]).stdout.split()
    assert {common.STE_RULE, common.STE_INDEX} <= set(handoff), handoff


def test_s10_writes_the_first_ratchet_and_style_passes(game):
    """S10 writes config/style-ratchet.txt last, in the handoff commit: one `skip` line for each of the kit's five
    files and one row per other public prose file with a finding, at its count of now. The vendored `style` (the CI
    step of the README workflow) exits 0 in the game, and exits 1 when a public file gains one finding."""
    import publish
    rat = game / publish.STYLE_RATCHET_REL
    rows, skip, head = publish.parse_ratchet(rat.read_text())
    assert skip == list(common.KIT_PROSE) and len(skip) == 5 and all((game / k).is_file() for k in skip), skip
    lines = rat.read_text().splitlines()
    assert [l for l in lines if l.startswith("skip ")] == ["skip %s" % k for k in common.KIT_PROSE], lines
    assert head and all(l.startswith("#") for l in head) and "style --update" in "\n".join(head), head
    assert rows and rows == publish.style_counts(game, skip) and not set(rows) & set(skip), rows
    assert run(["git", "-C", game, "ls-files", publish.STYLE_RATCHET_REL]).stdout.strip() == publish.STYLE_RATCHET_REL
    assert publish.STYLE_RATCHET_REL in run(["git", "-C", game, "show", "--name-only", "--format=", "HEAD"]).stdout
    r = run([PY, publish.VENDORED, "style"], cwd=game, check=False)
    assert r.returncode == 0 and r.stdout.startswith("STYLE CHECK OK (") and "0 over their row" in r.stdout, r.stdout
    assert run(["git", "-C", game, "status", "--porcelain"]).stdout == ""
    readme, row = (game / "README.md").read_bytes(), rows.get("README.md", 0)
    try:                                                    # the negative control: one more semicolon in the README
        (game / "README.md").write_bytes(readme + b"\nOne part; two parts.\n")
        r = run([PY, publish.VENDORED, "style"], cwd=game, check=False)
        want = "STYLE FAIL README.md: %d finding(s), its row is %d\n" % (row + 1, row)
        assert r.returncode == 1 and want in r.stdout, r.stdout
    finally:
        (game / "README.md").write_bytes(readme)
    assert run(["git", "-C", game, "status", "--porcelain"]).stdout == ""


def test_s10_writes_the_style_hook_beside_the_deny_rules(game):
    """S10 puts the hook group of profiles/psx/hooks.json into the tracked .claude/settings.json in the same write as
    the deny rules: PA3's own keys stay, the file is tracked and clean, and the handoff is still one commit of 9."""
    conf = json.loads((game / common.SETTINGS).read_text())
    assert conf["hooks"]["PostToolUse"].count(_hook_group()) == 1, conf.get("hooks")
    want = json.loads((ROOT / "profiles/psx/deny.json").read_text())["permissions"]["deny"]
    assert set(want) <= set(conf["permissions"]["deny"]) and conf["agent"] == "pa-session", conf
    assert common.hooks_missing(game) == ([], None) and common.settings_due(game) is None
    assert run(["git", "-C", game, "status", "--porcelain", common.SETTINGS]).stdout == ""
    assert run(["git", "-C", game, "ls-files", common.SETTINGS]).stdout.strip() == common.SETTINGS
    assert json.loads(run(["git", "-C", game, "show", "HEAD:" + common.SETTINGS]).stdout) == conf
    log = run(["git", "-C", game, "log", "--format=%s"]).stdout.splitlines()
    assert len(log) == 9 and log[0].startswith("psxdecomp handoff:") and "STE1" in log[0], log
    assert common.SETTINGS in run(["git", "-C", game, "show", "--name-only", "--format=", "HEAD"]).stdout.split()


def test_s10_writes_the_guard_beside_the_style_hook(game, tmp_path):
    """S10 delivers the floor in the handoff commit: tools/psxd_floor.py (byte for byte, executable), its reference in
    docs/ops/ with a row of the ops index in PA3's grammar, config/guard.tsv, and the PreToolUse group beside the
    style hook. Doctor's `guard` row is OK. The hook, run as the settings register it, refuses an edit under asm/,
    allows an edit of a source file, and allows every call when the vendored tool is gone."""
    import subprocess

    import floor
    import upgrade
    conf = json.loads((game / common.SETTINGS).read_text())
    pre = json.loads(common.read(common.PROFILE_HOOKS))["hooks"]["PreToolUse"]
    assert conf["hooks"]["PreToolUse"] == pre and pre[0]["matcher"].startswith("Bash|Edit|Write|"), conf["hooks"]
    assert (game / floor.VENDORED).read_bytes() == (ROOT / "scripts/floor.py").read_bytes()
    assert os.access(game / floor.VENDORED, os.X_OK)
    assert (game / upgrade.FLOOR_DOC).read_bytes() == (ROOT / "profiles/psx/floor.md").read_bytes()
    assert (game / floor.GUARD).read_text() == common.read(common.PROFILE_GUARD)
    rows = [l for l in (game / upgrade.OPS_INDEX).read_text().splitlines() if l.startswith("psxdecomp-floor.md")]
    assert rows == ["psxdecomp-floor.md | The psxdecomp floor | %d" % len((game / upgrade.FLOOR_DOC).read_text().splitlines())]
    handoff = set(run(["git", "-C", game, "show", "--name-only", "--format=", "HEAD"]).stdout.split())
    assert {floor.VENDORED, upgrade.FLOOR_DOC, floor.GUARD, upgrade.OPS_INDEX, common.SETTINGS} <= handoff, handoff
    r = run([PY, ROOT / "scripts/doctor.py", "--repo", game, "--offline"], check=False)
    assert re.search(r"DOCTOR guard\s+OK\s+all 2 hook group\(s\)", r.stdout), r.stdout
    assert re.search(r"DOCTOR publish-tool\s+OK\s+5 owned file\(s\)", r.stdout), r.stdout
    assert (game / upgrade.CAMPAIGN_DOC).read_bytes() == (ROOT / "profiles/psx/campaign.md").read_bytes()
    assert not (game / upgrade.MATCHER_SKILL).exists() and not (game / "config/bank.tsv").exists()
    assert run([PY, floor.VENDORED, "plan"], cwd=game).stdout.startswith("PLAN INFO plan: no GENERATION_PLAN.md")

    def hook(repo, **inp):
        event = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": inp, "cwd": str(repo)}
        return subprocess.run(["sh", "-c", pre[0]["hooks"][0]["command"]], input=json.dumps(event), cwd=repo,
                              capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(repo)))

    r = hook(game, file_path=str(game / "asm/main/a.s"))
    assert r.returncode == 0 and json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny", r.stdout
    r = hook(game, file_path=str(game / "src/a.c"))
    assert (r.returncode, r.stdout) == (0, ""), (r.stdout, r.stderr)
    bare = tmp_path / "bare"                                    # no vendored tool: python3 fails, the command exits 0
    bare.mkdir()
    r = hook(bare, file_path=str(bare / "asm/a.s"))
    assert (r.returncode, r.stdout) == (0, ""), (r.returncode, r.stdout)
    assert run(["git", "-C", game, "status", "--porcelain"]).stdout == ""


def test_s10_writes_the_debt_baseline_and_debt_passes(game):
    """S10 writes the readability floor in the handoff commit: rules/FIN1.md and rules/NAME1.md (never promoted), the
    header lines of the two ledgers, and config/debt-baseline.txt last, in `mode admit` with no row (the game has no
    C file yet). The vendored `debt` and `names` (the CI step of the README workflow) exit 0, and `debt` exits 1 when
    a source file gains a `goto`."""
    import floor
    rows, skip, mode, head = floor.parse_baseline((game / floor.BASELINE).read_text())
    assert (rows, skip, mode) == ({}, [], "admit") and len(head) == 5, (rows, skip, mode)   # no stub header yet: no skip line
    assert (game / floor.NAMES).read_text() == "\t".join(floor.NAME_COLUMNS) + "\n"
    assert (game / floor.ASM_EVIDENCE).read_text() == "\t".join(floor.ASM_COLUMNS) + "\n"
    for rid in ("FIN1", "NAME1"):
        assert common.rule_state(game, rid) is None, rid
        assert rid not in (game / ".claude/skills/project-architect/SKILL.md").read_text()
        assert len([l for l in (game / common.STE_INDEX).read_text().splitlines() if l.startswith(rid + " | ")]) == 1
    assert "FIN1" not in (game / "HOW_WE_WORK.md").read_text() and "NAME1" not in (game / "HOW_WE_WORK.md").read_text()
    handoff = set(run(["git", "-C", game, "show", "--name-only", "--format=", "HEAD"]).stdout.split())
    assert {floor.BASELINE, floor.NAMES, floor.ASM_EVIDENCE, "rules/FIN1.md", "rules/NAME1.md"} <= handoff, handoff
    r = run([PY, floor.VENDORED, "debt"], cwd=game, check=False)
    assert r.returncode == 0 and "DEBT CHECK OK (0 rise(s), 0 stale row(s); mode admit)" in r.stdout, r.stdout
    assert run([PY, floor.VENDORED, "names"], cwd=game, check=False).returncode == 0
    wf = (game / ".github/workflows/psxdecomp-readme.yml").read_text()
    assert "run: python3 %s debt" % floor.VENDORED in wf
    src = game / "src/probe.c"
    try:                                                    # the negative control: a tracked C file with a goto
        src.write_text(floor.C_DEBT["goto"][0])
        run(["git", "-C", game, "add", "-f", "src/probe.c"])
        r = run([PY, floor.VENDORED, "debt"], cwd=game, check=False)
        assert r.returncode == 1 and "DEBT FAIL rise goto src/probe.c: 1, its row is 0\n" in r.stdout, r.stdout
        r = run([PY, floor.VENDORED, "debt"], cwd=game, check=False)
        assert "DEBT FAIL rise unbased src/probe.c: 1, its row is 0\n" in r.stdout, r.stdout   # the ledger exists
    finally:
        run(["git", "-C", game, "rm", "-q", "-f", "--cached", "src/probe.c"])
        src.unlink()
    assert run(["git", "-C", game, "status", "--porcelain"]).stdout == ""


def test_phase_rows_wait_at_bootstrap(game):
    """The phase-conditional rows of the floor at the handoff: gate, toolchain, names, debt and progress say WAIT with
    the phase that makes each due, and the doctor still exits 0 (S10 aborts on a FAIL)."""
    r = run([PY, ROOT / "scripts/doctor.py", "--repo", game, "--offline"], check=False)
    assert r.returncode == 0, r.stdout
    rows = dict(re.findall(r"^DOCTOR (\S+) +(OK|WARN|FAIL|SKIP|WAIT) ", r.stdout, re.M))
    waits = {k for k, v in rows.items() if v == "WAIT"}
    assert waits == {"roadmap", "gate", "toolchain", "names", "debt", "progress"}, rows
    for name, due in (("gate", "phase 1.3 closes"), ("toolchain", "phase 1.4 closes"), ("names", "phase 1.4 closes"),
                      ("debt", "the first C file under src/"), ("progress", "phase 1.9 opens")):
        assert re.search(r"^DOCTOR %s +WAIT due w\S+ %s" % (name, re.escape(due)), r.stdout, re.M), (name, r.stdout)
    assert r.stdout.splitlines()[-1].startswith("DOCTOR OK (") and ", 6 not due" in r.stdout.splitlines()[-1]


def test_second_pa3_install_keeps_the_rule_the_ratchet_and_the_hook(toolchain, game, tmp_path):
    """PA3's own `--project` install run again over a copy of the game (the command of S6, from the pinned clone of the
    toolchain fixture) keeps what S10 wrote for the public files: the rule file and its index row, the ratchet, the
    hook group and the deny rules. It promotes no STE1 headline."""
    import publish
    copy = tmp_path / "copy"
    shutil.copytree(game, copy, symlinks=True)
    pa = json.loads((copy / ".claude/pa.json").read_text())
    kept = {rel: (copy / rel).read_bytes() for rel in (common.STE_RULE, publish.STYLE_RATCHET_REL)}
    row = next(l for l in (copy / common.STE_INDEX).read_text().splitlines() if l.startswith("STE1 "))
    r = run([PY, toolchain["pkg"] / "pa_install.py", "--project", copy, "--yes", "--name", pa["project"], "--python",
             pa["python"], "--config-dir", toolchain["cfg"], "--pa3-dir", toolchain["cfg"] / "pa3"], check=False)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert json.loads((copy / ".claude/pa.json").read_text())["pa_version"] == pa["pa_version"]
    assert {rel: (copy / rel).read_bytes() for rel in kept} == kept, r.stdout[-3000:]
    assert common.ste_rule_state(copy) is None and _ste_body(copy) == common.read(common.PROFILE_STE).strip()
    assert (copy / common.STE_INDEX).read_text().splitlines().count(row) == 1
    conf = json.loads((copy / common.SETTINGS).read_text())
    assert conf["hooks"]["PostToolUse"].count(_hook_group()) == 1, conf.get("hooks")
    assert common.hooks_missing(copy) == ([], None) and common.deny_missing(copy) == ([], None)
    assert conf["hooks"]["PreToolUse"] == json.loads(common.read(common.PROFILE_HOOKS))["hooks"]["PreToolUse"]
    assert not [l for l in _headlines(copy) if l.startswith("- STE1")]
    r = run([PY, publish.VENDORED, "style"], cwd=copy, check=False)
    assert r.returncode == 0 and "STYLE CHECK OK" in r.stdout, r.stdout


def test_s6_root_hint_pins_the_clone(toolchain, tmp_path):
    """No PA3 on the machine: S6 prints the --root command with --no-clone (the pinned copy, not upstream's branch)."""
    target = tmp_path / "noroot"
    bootstrap(toolchain, target, "--until", "S5")
    r = run([PY, ROOT / "scripts/install.py", "stage", "S6", "--target", target, "--pa3-dir", tmp_path / "nopa3",
             "--config-dir", toolchain["cfg"]], env=toolchain["env"], check=False)
    assert r.returncode == 1 and "--root --no-clone" in r.stdout, r.stdout


def test_readme_standard(game):
    """S8 replaces the kit's skeleton with psxdecomp's README standard, filled with the kit's own values: no old
    disclosure, the AI policy block, both generated blocks; the vendored lint passes it (before phase 1.9 and with no
    Sony serial, the categories and the disc rows are INFO), and the game's CI runs that lint."""
    import publish
    readme = (game / "README.md").read_text()
    assert common.OLD_DISCLOSURE not in readme and "PSXDECOMP Homebrew Fixture" in readme and "{{" not in readme
    assert [l[3:] for l in readme.splitlines() if l.startswith("## ")] == publish.README_H2
    r = run([PY, "tools/psxd_publish.py", "lint", "README.md"], cwd=game, check=False)
    assert r.returncode == 0 and "README LINT OK (0 warn)" in r.stdout, r.stdout
    assert (game / publish.VENDORED).read_bytes() == (ROOT / "scripts/publish.py").read_bytes()
    assert (game / publish.WORKFLOW).is_file() and not (game / publish.DISCS_REL).exists()


def test_mmx6_install_list_present(game):
    """Every path mmx6's kit install record lists exists in the fixture tree (M1)."""
    import re
    rec = (game / "docs/decomp-architect-install.md").read_text()
    written = re.findall(r"^- (?:created|changed|edited|appended) `([^`]+)`", rec, re.M)
    s5 = ["config/firewall.txt", "config/firewall-fixture.sha1", "tools/audit_public.py", ".github/workflows/no-rom.yml"]
    for p in written + s5:
        assert (game / p).exists(), p
    assert len(written) + len(s5) >= 104


def test_second_run_changes_nothing(toolchain, game):
    head = run(["git", "-C", game, "rev-parse", "HEAD"]).stdout
    st = game / ".run/bootstrap/state.json"
    d = json.loads(st.read_text())
    for k in ("S5", "S6", "S7", "S8", "S9", "S10"):
        d["stages"].pop(k)
    st.write_text(json.dumps(d))
    bootstrap(toolchain, game)
    assert run(["git", "-C", game, "rev-parse", "HEAD"]).stdout == head
    assert run(["git", "-C", game, "status", "--porcelain"]).stdout == ""


def test_firewall_control_in_generated_repo(game, kit):
    planted = game / ".run/firewall-control/planted.bin"
    planted.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(os.path.join(kit, "templates/firewall-fixture/blob.bin"), planted)
    r = run([PY, "tools/audit_public.py", "--paths", ".run/firewall-control/planted.bin"], cwd=game, check=False)
    planted.unlink()
    assert r.returncode == 1 and "OFFENDER" in r.stdout
    assert run([PY, "tools/audit_public.py"], cwd=game, check=False).returncode == 0


def test_doctor_and_record(game):
    r = run([PY, ROOT / "scripts/doctor.py", "--repo", game], check=False)
    assert r.returncode == 0, r.stdout
    hyg = next(l for l in r.stdout.splitlines() if l.split()[1:2] == ["hygiene"])     # the kit's own text may WARN;
    assert hyg.split()[2] in {"OK", "WARN"} and not any(                                 # psxdecomp's never is named
        f in hyg for f in ("refs.md", "psxdecomp.toml", "psxdecomp.profile.toml", "config/refs.toml")), hyg
    rec = (game / "config/psxdecomp.toml").read_text()
    assert 'tag = "v3.14.2"' in rec and "--intake-fixture" in rec
    assert run(["git", "-C", game, "check-ignore", "-q", "refs/x"], check=False).returncode == 0
    assert "!/refs/" in (game / ".ignore").read_text().splitlines()       # searchable though git-ignored
    (game / "refs" / "probe").mkdir(parents=True, exist_ok=True)
    (game / "refs" / "probe" / "libspu.h").write_text("void SpuSetKey(long on_off, unsigned long voice_bit);\n")
    if shutil.which("rg"):                                                  # a root search reaches refs/ (gap 1)
        hits = run(["rg", "-l", "SpuSetKey"], cwd=game, check=False).stdout
        assert "refs/probe/libspu.h" in hits, hits
    shutil.rmtree(game / "refs" / "probe")
    assert "purge: refs/" in (game / "config/firewall.txt").read_text()
    assert "docs/ops/refs.md" in (game / "HOW_WE_WORK.md").read_text()
    readme = (game / "README.md").read_text()                     # the AI policy, once, under ## Description
    assert readme.count(common.AI_POLICY) == 1
    assert readme.index("\n## Description") < readme.index(common.AI_POLICY_MARK) < readme.index("\n## Progress")
    recipe = (game / "docs/ops/host-recipe.md").read_text()
    assert "brew install" in recipe


def test_scoped_outputs(game):
    """D2/D3/D6/D8: the SDK lead, the candidate label, the scope line, and no unscoped claim in what S9/S10 write."""
    import tomllib

    import fetch_refs
    rec = tomllib.loads((game / "config/psxdecomp.toml").read_text())
    assert rec["psyq"]["version"] == "4.7" and rec["psyq"]["status"].startswith("lead")
    assert "compiler_ladder" not in (game / "config/psxdecomp.profile.toml").read_text()
    import install
    how = (game / "HOW_WE_WORK.md").read_text()
    line = next(l for l in how.splitlines() if l.startswith("- **This repo:**"))
    assert "PsyQ 4.7" in line and len(line) <= 300
    conv = how[how.index("## Conventions"):].split("\n## ")[0]      # S10's line sits in the card's conventions section
    cline = [l for l in conv.splitlines() if l.startswith(install.CONV_MARK)]
    assert len(cline) == 1 and len(cline[0]) <= 120, cline
    assert "Fields by name" not in how              # M3: the measured drafting rule is not shipped (ECOSYSTEM K22, M15)
    assert "`CONTRIBUTING.md`" in cline[0] and "## Names, types and formatting" in (game / "CONTRIBUTING.md").read_text()
    assert ("docs/prior-art.md" in conv) == (game / "docs/prior-art.md").is_file()   # never a pointer to a missing file
    assert not (game / "docs/ops/drafting.md").exists()
    env = next(l for l in (game / "docs/ops/decomp-environment.md").read_text().splitlines()
               if l.startswith("| Candidate compiler family"))
    assert env.split("|")[2].strip().startswith("Candidate (S4"), env
    for rel in ("docs/ops/refs.md", "docs/prior-art.md", "config/psxdecomp.toml", "config/psxdecomp.profile.toml",
                "config/refs.toml"):
        if (game / rel).is_file():
            assert fetch_refs.lint_file(game / rel) == [], rel
    # one home: no sentence psxdecomp writes (the index, its config records, its HOW_WE_WORK lines) is copied elsewhere
    ours = ("docs/ops/refs.md", "config/psxdecomp.toml", "config/psxdecomp.profile.toml", "config/refs.toml")
    mine = lambda l: l.startswith((install.SCOPE_MARK, install.CONV_MARK, install.REFS_RULE[:20]))  # noqa: E731
    written = {s for rel in ours if (game / rel).is_file()
               for _, s in fetch_refs.sentences((game / rel).read_text(), toml=rel.endswith(".toml"))}
    written |= {s for _, s in fetch_refs.sentences("\n\n".join(l for l in how.splitlines() if mine(l)))}
    copies = []
    for rel in tree(game):
        if rel.endswith((".md", ".toml")) and rel not in ours:
            text = (game / rel).read_text()
            if rel == "HOW_WE_WORK.md":
                text = "\n".join("" if mine(l) else l for l in text.splitlines())
            copies += ["%s:%d: %s" % (rel, n, s[:60]) for n, s in fetch_refs.sentences(text, toml=rel.endswith(".toml"))
                       if s in written]
    assert not copies, copies


def test_dump_never_copied(game, toolchain):
    blob = toolchain["dump"].with_name("HOMEBREW (Track 1).bin").read_bytes()[:4096]
    for p in game.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            assert blob[2048:2400] not in p.read_bytes(), p
    medium = (game / ".run/bootstrap/medium.json").read_text()
    assert str(toolchain["dump"]) not in medium


def test_s5_dry_run_lists_what_s5_writes(toolchain, tmp_path):
    target = tmp_path / "dry"
    r = bootstrap(toolchain, target, "--until", "S5", "--dry-run")
    would = sorted(l.split()[-1] for l in r.stdout.splitlines() if l.strip().startswith("would be created"))
    assert not (target / ".git").exists()
    r = bootstrap(toolchain, target, "--until", "S5")
    did = sorted(l.split()[-1] for l in r.stdout.splitlines() if l.strip().startswith("created "))
    assert would == did and ".gitignore" in did


def test_wrong_pa3_refused(toolchain, tmp_path, monkeypatch):
    import common
    cache = tmp_path / "cache"
    clone = cache / ("pa3-" + common.compat()["pa3"]["tag"])
    run(["git", "clone", "--quiet", "--no-local", str(toolchain["pkg"].parent), clone])
    run(["git", "-C", clone, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "--quiet", "--allow-empty", "-m",
         "not the pin"])
    monkeypatch.setenv("PSXDECOMP_CACHE", str(cache))
    with pytest.raises(common.Fail, match="not the tested"):
        common.resolve_pa3()
    pkg, devs = common.resolve_pa3(force_untested=True)
    assert devs and "force-untested" in devs[0]


def test_wrong_kit_refused(tmp_path, kit):
    import common
    copy = tmp_path / "kit"
    shutil.copytree(kit, copy)
    (copy / "README.md").write_text("changed\n")
    with pytest.raises(common.Fail, match="digest"):
        common.resolve_kit(path=str(copy))


@pytest.mark.parametrize("until", ["S5", "S6", "S7", "S8", "S9"])
def test_resume_from_every_stage(toolchain, tmp_path, until):
    target = tmp_path / ("resume-" + until)
    bootstrap(toolchain, target, "--until", until)
    r = bootstrap(toolchain, target)
    assert "BOOTSTRAP OK through S10" in r.stdout
    assert tree(target) == GOLDEN.read_text().splitlines()


def test_resumed_s10_commits_the_card(toolchain, tmp_path):
    """An S10 that fails after its writes (here: doctor's fixture row) and is run again leaves nothing behind: the card
    with both of S10's lines is in the handoff commit, the tree is clean and equals the golden tree."""
    import install
    target = tmp_path / "resume-s10"
    bootstrap(toolchain, target, "--until", "S9")
    sha1 = target / "config/firewall-fixture.sha1"
    kept = sha1.read_bytes()
    sha1.unlink()
    r = bootstrap(toolchain, target, check=False)
    assert r.returncode == 1 and "fixture: planted-fixture hash missing" in r.stdout, r.stdout
    assert install.CONV_MARK in (target / "HOW_WE_WORK.md").read_text()          # the failed run wrote the card
    assert install.CONV_MARK not in run(["git", "-C", target, "show", "HEAD:HOW_WE_WORK.md"]).stdout
    sha1.write_bytes(kept)
    r = bootstrap(toolchain, target)
    assert "BOOTSTRAP OK through S10" in r.stdout
    assert run(["git", "-C", target, "status", "--porcelain"]).stdout == ""
    card = run(["git", "-C", target, "show", "HEAD:HOW_WE_WORK.md"]).stdout
    assert install.CONV_MARK in card and install.SCOPE_MARK in card
    assert tree(target) == GOLDEN.read_text().splitlines()
