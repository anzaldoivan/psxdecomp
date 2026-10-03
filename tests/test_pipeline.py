"""Tier 1: the deterministic installer on the homebrew fixture (S0, S2, S5-S10 from canned answers)."""
import json
import os
import shutil

import pytest

from conftest import PY, ROOT, bootstrap, run, tree

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


def test_clean_tree_and_commits(game):
    assert run(["git", "-C", game, "status", "--porcelain"]).stdout == ""
    log = run(["git", "-C", game, "log", "--format=%s"]).stdout.splitlines()[::-1]
    assert log[0].startswith("Firewall first") and len(log) == 9, log
    assert any(l.startswith("PA3 upgrades ask first") for l in log) and any(l.startswith("README: the AI policy")
                                                                           for l in log), log


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


def test_s6_root_hint_pins_the_clone(toolchain, tmp_path):
    """No PA3 on the machine: S6 prints the --root command with --no-clone (the pinned copy, not upstream's branch)."""
    target = tmp_path / "noroot"
    bootstrap(toolchain, target, "--until", "S5")
    r = run([PY, ROOT / "scripts/install.py", "stage", "S6", "--target", target, "--pa3-dir", tmp_path / "nopa3",
             "--config-dir", toolchain["cfg"]], env=toolchain["env"], check=False)
    assert r.returncode == 1 and "--root --no-clone" in r.stdout, r.stdout


def test_readme_policy_replaces_disclosure(game):
    """S8 puts the AI policy block under the README's lead and drops the kit's old disclosure paragraph."""
    readme = (game / "README.md").read_text()
    assert common.OLD_DISCLOSURE not in readme
    made = readme.split("## How this project is made", 1)[1].split("\n## ", 1)[0]
    assert made.strip().startswith("The standard it holds itself to"), made[:120]


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
    readme = (game / "README.md").read_text()                               # the AI policy, once, under the lead
    assert readme.count(common.AI_POLICY) == 1 and readme.index(common.AI_POLICY_MARK) < readme.index("\n## ")
    recipe = (game / "docs/ops/host-recipe.md").read_text()
    assert "brew install" in recipe


def test_scoped_outputs(game):
    """D2/D3/D6/D8: the SDK lead, the candidate label, the scope line, and no unscoped claim in what S9/S10 write."""
    import tomllib

    import fetch_refs
    rec = tomllib.loads((game / "config/psxdecomp.toml").read_text())
    assert rec["psyq"]["version"] == "4.7" and rec["psyq"]["status"].startswith("lead")
    assert "compiler_ladder" not in (game / "config/psxdecomp.profile.toml").read_text()
    how = (game / "HOW_WE_WORK.md").read_text()
    line = next(l for l in how.splitlines() if l.startswith("- **This repo:**"))
    assert "PsyQ 4.7" in line and len(line) <= 300
    env = next(l for l in (game / "docs/ops/decomp-environment.md").read_text().splitlines()
               if l.startswith("| Candidate compiler family"))
    assert env.split("|")[2].strip().startswith("Candidate (S4"), env
    for rel in ("docs/ops/refs.md", "docs/prior-art.md", "config/psxdecomp.toml", "config/psxdecomp.profile.toml",
                "config/refs.toml"):
        if (game / rel).is_file():
            assert fetch_refs.lint_file(game / rel) == [], rel
    # one home: no sentence psxdecomp writes (the index, its config records, its HOW_WE_WORK lines) is copied elsewhere
    import install
    ours = ("docs/ops/refs.md", "config/psxdecomp.toml", "config/psxdecomp.profile.toml", "config/refs.toml")
    mine = lambda l: l.startswith((install.SCOPE_MARK, install.REFS_RULE[:20]))  # noqa: E731
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
