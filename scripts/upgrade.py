#!/usr/bin/env python3
"""upgrade.py — bring an existing game repository to the current psxdecomp pins: audit -> plan -> apply --dry-run ->
apply. psxrecomp's migrate shape, our own code.

    upgrade.py audit [--repo DIR]                 doctor's rows plus what differs from the current kit
    upgrade.py plan  [--repo DIR]                 numbered actions; each is `psxdecomp` (apply does it) or `manual`
    upgrade.py apply --dry-run [--repo DIR]       the exact writes, nothing written
    upgrade.py apply [--repo DIR] [--fetch]       the psxdecomp-owned writes only; never commits, never touches PA3's
                                                  or the kit's files; its last line is the commit command
    upgrade.py --self-test

psxdecomp owns: config/psxdecomp.toml (apply sets its [psxdecomp].version to this plugin's), config/refs.toml, docs/ops/refs.md, its .gitignore block, its firewall purge
line, the one HOW_WE_WORK references line and its C-conventions pointer line (`card-conv`: written when the card has
room under PA3's cap, else a `manual` action naming the characters to free), the docs/ops/INDEX.md row, tools/psxd_publish.py,
.github/workflows/psxdecomp-readme.yml (the README standard's lint and its CI) and the agents' deny rules
(profiles/psx/deny.json, added to .claude/settings.json `permissions.deny`, never removed; the bootstrap's S10 writes
them first, this adds any that are missing later). The README's prose is
the developer's: its migration to the standard is a `manual` action listing the lint findings. PA3 and kit upgrades
are printed as commands for the developer (their own installers, their own gates).

psxdecomp also owns the writing rule of the public files, in four actions: `ai-policy` (the three lines of the README's
AI policy block, when they hold an older text), `ste-rule` (rules/STE1.md and its row of rules/INDEX.md, written by
the game's own tools/rules_add.py from profiles/psx/rules/STE1.md; `manual` without that tool), `style-hook`
(profiles/psx/hooks.json, added to .claude/settings.json `hooks`, never removed, in the one write of the deny rules)
and `style-ratchet` (config/style-ratchet.txt, written once, after the other writes of the run; from then on it is
the game's).

Opt-in, only in a repository with config/public-paths.txt (split mode, docs/PUBLISHING.md): .github/workflows/build.yml,
the public repository's byte check (written only when absent: it carries the game's own values; what upgrade cannot
read stays a {{PLACEHOLDER}} and a `manual` action), and docs/ops/psxdecomp-split.md, the release operator's card
(profiles/psx/split-mode.md, owned: rewritten whenever it differs; never public, docs/ops/ is denied).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import re
import shlex
import sys
import tomllib
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import doctor  # noqa: E402
import fetch_refs  # noqa: E402
import install  # noqa: E402
import publish  # noqa: E402

PROFILE_REFS = common.PLUGIN_ROOT / "profiles" / "psx" / "refs.toml"
OWNED = {publish.VENDORED: common.PLUGIN_ROOT / "scripts" / "publish.py",
         publish.WORKFLOW: common.PLUGIN_ROOT / "profiles" / "psx" / "psxdecomp-readme.yml"}
SPLIT_OWNED = {"docs/ops/psxdecomp-split.md": common.PLUGIN_ROOT / "profiles" / "psx" / "split-mode.md"}
PUBLIC_LIST = "config/public-paths.txt"
BUILD_WF = ".github/workflows/build.yml"
PROFILE_BUILD = common.PLUGIN_ROOT / "profiles" / "psx" / "build.yml"
def build_values(repo: pathlib.Path) -> dict[str, str]:
    """The build.yml placeholders this repository can answer: the public repository (`[public].repo` in
    config/psxdecomp.toml) and the executables (config/discs.tsv, one required check `build <EXE>` each)."""
    vals = {}
    toml = repo / "config" / "psxdecomp.toml"
    pub = tomllib.loads(common.read(toml)).get("public", {}) if toml.is_file() else {}
    if re.fullmatch(r"[\w.-]+/[\w.-]+", str(pub.get("repo", ""))):
        vals["REPO"] = pub["repo"]
    rows = publish.load_discs(repo / publish.DISCS_REL)[0]
    if rows:
        vals["EXES"] = ", ".join('"%s"' % e for e in dict.fromkeys(r["executable"] for r in rows))
    return vals


def fill_known(text: str, vals: dict[str, str]) -> str:
    return install.PH_RE.sub(lambda m: vals.get(m[1], m[0]), text)


def plan(repo: pathlib.Path) -> list[dict]:
    acts = []
    add = lambda owner, what, why, key: acts.append(dict(owner=owner, what=what, why=why, key=key))  # noqa: E731
    comp = common.compat()
    if not (repo / ".claude" / "pa.json").is_file():
        add("manual", "PA3: not a PA3 project; install PA3 first (psxdecomp adopts PA3 repositories only)", "no PA3",
            "pa3")
        if not (repo / "docs" / "decomp-architect-install.md").is_file():
            add("manual", "kit: then the decomp-architect kit, with its own installer", "no kit", "kit")
        return acts
    if not (repo / install.RECORD).is_file():
        add("psxdecomp", "adopt: write %s (pins as found, profile psx, `adopted`)" % install.RECORD,
            "the repository was not bootstrapped by psxdecomp", "adopt")
    elif record_version(common.read(repo / install.RECORD)) not in (None, common.plugin_version()):
        add("psxdecomp", "record: [psxdecomp].version %s -> %s in %s" % (
            record_version(common.read(repo / install.RECORD)), common.plugin_version(), install.RECORD),
            "the record names the psxdecomp whose tools the repository carries", "version")
    refs = repo / "config" / "refs.toml"
    default = {r["name"]: r for r in fetch_refs.load_rows(PROFILE_REFS)}
    if not refs.is_file():
        add("psxdecomp", "refs: add config/refs.toml (the profile's %d rows), docs/ops/refs.md, the refs/ ignore and "
            "purge lines, the HOW_WE_WORK references line" % len(default), "no reference library", "refs-add")
    else:
        mine = {r["name"]: r for r in fetch_refs.load_rows(refs)}
        new = sorted(set(default) - set(mine))
        if new:
            add("psxdecomp", "refs: add rows %s" % ", ".join(new), "the profile gained rows", "refs-rows")
        doc = fetch_refs.load_doc(refs)
        if not doc["authority"] or not doc["traps"]:
            add("psxdecomp", "refs: add the profile's [[authority]] and [[trap]] tables", "which source wins per topic, "
                "and the contradictions already paid for", "refs-meta")
        gone = sorted(set(mine) - set(default))
        if gone:
            add("manual", "refs: rows not in the profile any more: %s (dropped by the curation audit, or your own "
                "additions); keep or remove each" % ", ".join(gone), "curation", "refs-gone")
        for n in sorted(set(default) & set(mine)):
            if default[n].get("ref") != mine[n].get("ref") or default[n]["class"] != mine[n]["class"]:
                add("manual", "refs: %s is %s/%s here, %s/%s in the profile" % (
                    n, mine[n]["class"], str(mine[n].get("ref", ""))[:12], default[n]["class"],
                    str(default[n].get("ref", ""))[:12]), "a pin or a class differs; decide per source", "refs-diff")
    stale = [rel for rel, src in OWNED.items() if not (repo / rel).is_file() or
             (repo / rel).read_bytes() != src.read_bytes()]
    if stale:
        add("psxdecomp", "publish: write %s (the README standard's lint and its CI)" % " and ".join(stale),
            "missing or older than psxdecomp %s's" % common.plugin_version(), "publish")
    if (repo / PUBLIC_LIST).is_file():
        card = [rel for rel, src in SPLIT_OWNED.items() if not (repo / rel).is_file() or
                (repo / rel).read_bytes() != src.read_bytes()]
        if card:
            add("psxdecomp", "split: write %s (the release operator's card: ship, the push gate, contributor PRs)"
                % " and ".join(card), "missing or older than psxdecomp %s's" % common.plugin_version(), "split-doc")
        bw = repo / BUILD_WF
        if not bw.is_file():
            add("psxdecomp", "build: write %s from the template, once (the public repo's byte-check CI)" % BUILD_WF,
                "the repository lists public paths (%s)" % PUBLIC_LIST, "build")
        left = sorted(set(install.PH_RE.findall(common.read(bw if bw.is_file() else PROFILE_BUILD)))
                      - (set() if bw.is_file() else set(build_values(repo))))
        if left:
            add("manual", "build: fill %s in %s by hand (the game's own values; psxdecomp's docs/PUBLISHING.md)"
                % (", ".join("{{%s}}" % k for k in left), BUILD_WF), "upgrade cannot read them", "build-fill")
    conv = conv_card(repo)
    if conv:
        over = len(conv[1]) - doctor.card_chars(repo)[1]
        if over <= 0:
            add("psxdecomp", "card-conv: write the C-conventions line of %s (pointers to CONTRIBUTING.md and the "
                "prior-art decision)" % doctor.CARD, "missing or older than psxdecomp %s's" % common.plugin_version(), "card-conv")
        else:
            add("manual", "card-conv: free %d character(s) in %s, then apply again; the C-conventions line needs %d and "
                "PA3's cap is %d" % (over, doctor.CARD, len(conv[1]) - len(conv[0]), doctor.card_chars(repo)[1]),
                "the card is full; which line moves to docs/ops/ is the game's choice", "card-conv")
    missing, why = common.deny_missing(repo)
    if missing:
        add("manual" if why else "psxdecomp", "deny: add %d rule(s) to %s permissions.deny from psxdecomp's "
            "profiles/psx/deny.json%s" % (len(missing), common.SETTINGS, " by hand (%s)" % why if why else " (add-only)"),
            "PA3's own deny stops `git push` alone; these forms also reach a push, a PR or a release", "deny")
    hooks, why = common.hooks_missing(repo)
    if hooks:
        add("manual" if why else "psxdecomp", "style-hook: add %d hook group(s) to %s hooks from psxdecomp's "
            "profiles/psx/hooks.json%s" % (len(hooks), common.SETTINGS, " by hand (%s)" % why if why else " (add-only)"),
            "an agent session reads the writing findings of a public file right after it writes one", "style-hook")
    rule = common.ste_rule_state(repo)
    if rule == "manual":
        add("manual", "ste-rule: write %s with PA3's rules_add.py (this repository has no %s); the rule's body is %s"
            % (common.STE_RULE, common.STE_TOOL, common.PROFILE_STE), "the writing rule of the public files", "ste-rule")
    elif rule:
        add("psxdecomp", "ste-rule: %s %s with the game's %s (the body of psxdecomp's profiles/psx/rules/STE1.md; "
            "never promoted)" % (rule, common.STE_RULE, common.STE_TOOL), "the writing rule of the public files: "
            "missing, or its body is not psxdecomp %s's" % common.plugin_version(), "ste-rule")
    readme = repo / "README.md"
    if readme.is_file():
        text = common.read(readme)
        if common.AI_POLICY_MARK in text and common.with_ai_policy(text) != text:
            add("psxdecomp", "ai-policy: write the current AI policy block in README.md (the block's three lines, "
                "nothing else)", "the block holds an older text of the policy", "ai-policy")
            text = common.with_ai_policy(text)           # the lint below reads the README as this action leaves it
        found = [f for f in publish.lint(text, publish.Ctx(repo)) if f[0] == "FAIL"]
        if found:
            add("manual", "README: %d lint failure(s) against the README standard (docs/PUBLISHING.md; the prose is "
                "yours, the two generated blocks are `python3 tools/psxd_publish.py render README.md --write`): %s"
                % (len(found), "; ".join("%s: %s" % f[1:] for f in found[:8])), "the README standard", "readme")
    if not (repo / publish.STYLE_RATCHET_REL).is_file():
        add("psxdecomp", "style-ratchet: write %s, once (the count of writing findings of each public prose file, the "
            "kit's %d files skipped)" % (publish.STYLE_RATCHET_REL, len(common.KIT_PROSE)),
            "`style` fails when a count rises; a count may only fall", "style-ratchet")
    if (repo / PUBLIC_LIST).is_file() and not publish.is_listed(
            publish.parse_public_paths(common.read(repo / PUBLIC_LIST)), publish.STYLE_RATCHET_REL):
        add("manual", "style-public: add %s to %s" % (publish.STYLE_RATCHET_REL, PUBLIC_LIST),
            "the public repository's CI runs `style` and needs the file", "style-public")
    gi = repo / ".gitignore"
    if gi.is_file() and "/refs/" not in common.read(gi).splitlines():
        add("psxdecomp", "ignore: add the /refs/ line in a psxdecomp block", "refs/ must never be tracked", "ignore")
    pa = repo / ".claude" / "pa.json"
    if pa.is_file():
        conf = json.loads(common.read(pa))
        if conf.get("pa_version") != comp["pa3"]["version"]:
            add("manual", "PA3: the repository is at %s, psxdecomp is tested on %s; update with PA3's own installer "
                "(`<python> <pa3>/pa_install.py --project %s`), then /psxdecomp:doctor"
                % (conf.get("pa_version"), comp["pa3"]["version"], repo), "PA3 version", "pa3")
        if conf.get("python") and not os.path.exists(conf["python"]):
            add("manual", "python: pa.json names %s, missing on this machine; re-run PA3's --project install here"
                % conf["python"], "portability", "python")
    else:
        add("manual", "PA3: not a PA3 project; install PA3 first (psxdecomp adopts PA3 repositories only)", "no PA3",
            "pa3")
    if not (repo / "docs" / "decomp-architect-install.md").is_file():
        add("manual", "kit: no decomp-architect install record; the kit installs on PA3 repositories with its own "
            "installer", "no kit", "kit")
    return acts


def conv_card(repo: pathlib.Path) -> tuple[str, str] | None:
    """(the card, the card with the current C-conventions line), or None when it has that line or there is no card."""
    how = repo / doctor.CARD
    if not how.is_file():
        return None
    old = common.read(how)
    new = install.with_conventions(old, install.conventions_line((repo / "docs/prior-art.md").is_file()))
    return None if new == old else (old, new)


def commit_command(repo: pathlib.Path, paths: list[str]) -> str:
    """One command that commits exactly what apply wrote: PA3's own commit path when the repository has it."""
    msg = "upgrade to psxdecomp %s" % common.plugin_version()
    args = " ".join(shlex.quote(p) for p in dict.fromkeys(paths))
    if (repo / "tools/commit_task.sh").is_file():
        return "bash tools/commit_task.sh psxdecomp %s %s" % (shlex.quote(msg), args)
    return "git add -- %s && git commit -m %s -- %s" % (args, shlex.quote("psxdecomp: " + msg), args)


VERSION_RE = re.compile(r'(\[psxdecomp\][^\[]*?^version = ")([^"]*)"', re.M | re.S)


def record_version(text: str) -> str | None:
    m = VERSION_RE.search(text)
    return m[2] if m else None


def toml_table(kind: str, d: dict) -> str:
    """One [[kind]] table; strings and string lists as JSON literals (valid TOML basic strings)."""
    lines = ["[[%s]]" % kind]
    for k, v in d.items():
        lines.append("%s = %s" % (k, json.dumps(v, ensure_ascii=False)))
    return "\n".join(lines) + "\n"


def written_paths(written: list[str]) -> list[str]:
    """The repository paths in apply's lines (`created <path>`, `changed <path>`, `index <path> (...)`)."""
    return [m[1] for x in written for m in [re.match(r"(?:created|changed|index) (\S+)", x)] if m]


def apply(repo: pathlib.Path, dry: bool, fetch: bool) -> list[str]:
    acts = {a["key"] for a in plan(repo) if a["owner"] == "psxdecomp"}
    written = []

    def w(rel, text):
        st = common.write(repo / rel, text, dry=dry)
        if st != "unchanged":
            written.append("%s%s %s" % ("would be " if dry else "", st, rel))

    if "adopt" in acts:
        conf = json.loads(common.read(repo / ".claude/pa.json")) if (repo / ".claude/pa.json").is_file() else {}
        w(install.RECORD, "\n".join([
            "# config/psxdecomp.toml — adopted by /psxdecomp:upgrade (the repository predates psxdecomp).", "",
            "[psxdecomp]", 'version = "%s"' % common.plugin_version(), 'profile = "psx"',
            'bootstrapped = "adopted %s"' % common.today(), "", "[pa3]", 'version = "%s"' % conf.get("pa_version", ""),
            "", "[refs]", 'file = "config/refs.toml"', 'index = "docs/ops/refs.md"', "", "[deviations]",
            'list = ["adopted: not bootstrapped by psxdecomp; pins recorded as found"]', ""]))
    if "version" in acts:
        w(install.RECORD, VERSION_RE.sub(lambda m: '%s%s"' % (m[1], common.plugin_version()),
                                         common.read(repo / install.RECORD), count=1))
    if "refs-add" in acts:
        w("config/refs.toml", common.read(PROFILE_REFS))
    elif "refs-rows" in acts or "refs-meta" in acts:
        cur = common.read(repo / "config/refs.toml")
        mine = {r["name"] for r in fetch_refs.load_rows(repo / "config/refs.toml")}
        prof = fetch_refs.load_doc(PROFILE_REFS)
        extra = []
        if "refs-rows" in acts:
            extra += [toml_table("ref", r) for r in prof["rows"] if r["name"] not in mine]
        if "refs-meta" in acts:
            have = fetch_refs.load_doc(repo / "config/refs.toml")
            if not have["authority"]:
                extra += [toml_table("authority", a) for a in prof["authority"]]
            if not have["traps"]:
                extra += [toml_table("trap", t) for t in prof["traps"]]
        w("config/refs.toml", cur.rstrip("\n") + "\n\n# ---- added by /psxdecomp:upgrade %s ----\n" % common.today()
          + "\n".join(extra))
    if "publish" in acts:
        for rel, src in OWNED.items():
            st = common.write(repo / rel, common.read(src), dry=dry, mode=0o755 if rel.endswith(".py") else None)
            if st != "unchanged":
                written.append("%s%s %s" % ("would be " if dry else "", st, rel))
    if "ai-policy" in acts:
        w("README.md", common.with_ai_policy(common.read(repo / "README.md")))
    if "ste-rule" in acts:
        written += common.ste_rule_write(repo, common.find_python((3, 11)) or sys.executable, dry)
    if "split-doc" in acts:
        for rel, src in SPLIT_OWNED.items():
            w(rel, common.read(src))
    if "build" in acts:
        w(BUILD_WF, fill_known(common.read(PROFILE_BUILD), build_values(repo)))
    if {"deny", "style-hook"} & acts:                # one write of the file when both are due
        w(common.SETTINGS, common.settings_due(repo))
    if "card-conv" in acts:
        w(doctor.CARD, conv_card(repo)[1])
    if "refs-add" in acts or "ignore" in acts:
        gi = common.read(repo / ".gitignore") if (repo / ".gitignore").is_file() else ""
        if "/refs/" not in gi.splitlines():
            w(".gitignore", gi + ("" if not gi or gi.endswith("\n") else "\n") + "%s ----\n/refs/\n" % install.PSX_MARK)
        fw = repo / "config/firewall.txt"
        if fw.is_file() and "purge: refs/" not in common.read(fw):
            w("config/firewall.txt", common.read(fw).rstrip("\n") + "\n\n%s: the reference library ----\npurge: refs/\n"
              % install.PSX_MARK)
        how = repo / "HOW_WE_WORK.md"
        if how.is_file() and install.REFS_RULE not in common.read(how):
            w("HOW_WE_WORK.md", install.insert_in_section(common.read(how), "## Docs map", install.REFS_RULE))
    if not dry and any(x.endswith(" HOW_WE_WORK.md") for x in written) and (repo / "tools/card.py").is_file():
        py = common.find_python((3, 11)) or sys.executable
        r = common.run([py, "tools/card.py", "check"], cwd=repo, check=False)
        written.append("card check rc %d: %s" % (r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:]))
    refs_file = repo / "config/refs.toml"
    if not dry and refs_file.is_file():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fetch_refs.main(["--repo", str(repo)] + ([] if fetch else ["--index-only"]))
        fresh = " unchanged" in next((l for l in buf.getvalue().splitlines() if l.startswith("INDEX ")), "")
        written.append("%s docs/ops/refs.md (%s)" % ("unchanged index" if fresh else "index",
                                                     buf.getvalue().strip().splitlines()[-1]))
    elif dry and ("refs-add" in acts or "refs-rows" in acts):
        written.append("would write docs/ops/refs.md (the index)")
    if "style-ratchet" in acts:                      # last: each write above can change a count (a dry run counts none)
        w(publish.STYLE_RATCHET_REL, "" if dry else common.first_ratchet(repo))
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["audit", "plan", "apply"])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    repo = pathlib.Path(a.repo).resolve()
    if a.cmd == "audit":
        for r in doctor.check(repo):
            print("AUDIT %-*s %-4s %s" % (doctor.WIDTH, *r))
        acts = plan(repo)
        print("AUDIT %d action(s): %d psxdecomp, %d manual" % (len(acts), sum(x["owner"] == "psxdecomp" for x in acts),
                                                              sum(x["owner"] == "manual" for x in acts)))
        return 0
    if a.cmd == "plan":
        acts = plan(repo)
        for i, x in enumerate(acts, 1):
            print("PLAN %d [%s] %s — %s" % (i, x["owner"], x["what"], x["why"]))
        print("PLAN %d action(s)%s" % (len(acts), "" if acts else " — up to date"))
        return 0
    if a.cmd == "apply":
        try:
            written = apply(repo, a.dry_run, a.fetch)
        except common.Fail as e:                     # a game tool refused: what was written before it stays
            print("APPLY FAIL %s" % e)
            return 1
        for x in written:
            print("APPLY %s" % x)
        manual = [x for x in plan(repo) if x["owner"] == "manual"] if not a.dry_run else []
        for x in manual:
            print("MANUAL %s" % x["what"])
        paths = written_paths(written)
        print("APPLY %s %d write(s); nothing committed" % (
            "DRY RUN" if a.dry_run else "OK", sum(x.startswith("would be ") for x in written) if a.dry_run else len(paths)))
        if paths and not a.dry_run:
            print("COMMIT %s" % commit_command(repo, paths))
        return 0
    ap.print_help()
    return 2


def self_test_card(repo: pathlib.Path) -> bool:
    """card-conv on a card with room, on a full card (manual, the exact characters to free) and on an older line; the
    commit command. The card is put back as apply left it."""
    how = repo / doctor.CARD
    line = install.conventions_line(False)
    done = how.read_text()
    ok = done.count(line) == 1 and "card-conv" not in {x["key"] for x in plan(repo)}
    bare = done.replace(line + "\n", "")
    # two characters short of the room the line needs; the filler is not ASCII: PA3's cap counts characters, not bytes
    how.write_text(bare + "\u00e9" * (7000 - len(bare) - len(line)) + "\n", encoding="utf-8")
    act = next(x for x in plan(repo) if x["key"] == "card-conv")
    ok &= act["owner"] == "manual" and "free 2 character(s)" in act["what"] and apply(repo, True, False) == []
    how.write_text(common.read(how).replace("\u00e9\u00e9\n", "\n"), encoding="utf-8")     # two freed: it fits, to the character
    ok &= next(x for x in plan(repo) if x["key"] == "card-conv")["owner"] == "psxdecomp"
    out = apply(repo, False, False)
    ok &= len(common.read(how)) == 7000 and line in common.read(how) and "changed %s" % doctor.CARD in out
    ok &= written_paths(out) == [doctor.CARD] and written_paths(["would be changed x", "card check rc 0: []"]) == []
    how.write_text(done.replace(line, "%s an older pointer." % install.CONV_MARK))
    ok &= next(x for x in plan(repo) if x["key"] == "card-conv")["owner"] == "psxdecomp"
    apply(repo, False, False)
    ok &= how.read_text() == done                                            # an older line: replaced where it stood
    cmd = commit_command(repo, ["a b", "c", "c"])
    ok &= cmd == "git add -- 'a b' c && git commit -m 'psxdecomp: upgrade to psxdecomp %s' -- 'a b' c" % common.plugin_version()
    (repo / "tools/commit_task.sh").write_text("")
    ok &= commit_command(repo, ["c"]) == "bash tools/commit_task.sh psxdecomp 'upgrade to psxdecomp %s' c" % common.plugin_version()
    (repo / "tools/commit_task.sh").unlink()
    how.write_text(bare)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["apply", "--repo", str(repo)])
    last = buf.getvalue().strip().splitlines()[-1]
    ok &= "APPLY OK 1 write(s); nothing committed" in buf.getvalue()         # the card; the unchanged index is no write
    print("  card-conv: %s; last line: %s" % (act["what"][:44], last[:60]))
    return ok and how.read_text() == done and last.startswith("COMMIT git add -- %s && git commit -m " % doctor.CARD)


# A stand-in for PA3's tools/rules_add.py in the self-test: `add` alone, the real tool's two files and their format.
RULES_STUB = r"""import argparse, datetime, os, pathlib, sys
ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["add"])
for k in ("--id", "--title", "--group", "--tags", "--origin", "--file"):
    ap.add_argument(k, required=True)
ap.add_argument("--force", action="store_true")
a = ap.parse_args()
root = pathlib.Path(os.environ.get("PA_PROJECT_ROOT") or sys.exit("refused: no PA_PROJECT_ROOT"))
rule, index = root / "rules" / (a.id + ".md"), root / "rules" / "INDEX.md"
if rule.is_file() and not a.force:
    sys.exit("refused: rules/%s already exists (--force to overwrite)" % rule.name)
rule.parent.mkdir(exist_ok=True)
body = pathlib.Path(a.file).read_text(encoding="utf-8").rstrip("\n")
rule.write_text("# %s — %s\nid: %s · group: %s · status: active · tags: %s · origin: %s · added: %s\n\n%s\n" % (
    a.id, a.title, a.id, a.group, a.tags, a.origin, datetime.date.today().isoformat(), body), encoding="utf-8")
rows = index.read_text(encoding="utf-8").splitlines() if index.is_file() else [
    "# Rules -- full texts in rules/<id>.md", "# id | headline | tags | active|superseded-by:<id>|sunset | origin"]
row = "%s | %s | %s | active | %s" % (a.id, a.title, a.tags, a.origin)
if not any(r.startswith(a.id + " |") for r in rows):
    rows.append(row)
index.write_text("\n".join(row if r.startswith(a.id + " |") else r for r in rows) + "\n", encoding="utf-8")
print(row)
"""


def self_test_style(repo: pathlib.Path) -> bool:
    """The writing rule's actions: style-hook, ste-rule, ai-policy, style-ratchet and the manual style-public. On entry
    the settings hold the deny rules alone, the first apply wrote the ratchet and there is no rules_add.py. On return
    the four are present and the README is gone."""
    acts = lambda: {x["key"]: x for x in plan(repo)}  # noqa: E731
    settings, rule, rat = repo / common.SETTINGS, repo / common.STE_RULE, repo / publish.STYLE_RATCHET_REL
    # style-hook: beside the game's own group, which stays first; every other key and event stays, in place
    own = {"matcher": "Bash", "hooks": [{"type": "command", "command": "true"}]}
    want = json.loads(common.read(common.PROFILE_HOOKS))["hooks"]["PostToolUse"]
    mine = dict(json.loads(settings.read_text()), hooks={"Stop": [own], "PostToolUse": [own]}, model="m")
    settings.write_text(json.dumps(mine, indent=2) + "\n")
    ok = rat.is_file() and acts()["style-hook"]["owner"] == "psxdecomp"
    apply(repo, False, False)
    got = json.loads(settings.read_text())
    ok &= got == dict(mine, hooks={"Stop": [own], "PostToolUse": [own] + want}) and list(got) == list(mine)
    ok &= "style-hook" not in acts()
    settings.write_text("{}\n")                                          # an empty file: one write, with the deny rules
    out = apply(repo, False, False)
    full = json.loads(settings.read_text())
    ok &= out.count("changed %s" % common.SETTINGS) == 1 and full["hooks"] == {"PostToolUse": want}
    ok &= full["permissions"] == mine["permissions"] and not {"deny", "style-hook"} & set(acts())
    (repo / publish.PA3_REL).write_text(json.dumps({"files": {common.SETTINGS: "h"}}))
    settings.write_text("{}\n")
    ok &= acts()["style-hook"]["owner"] == "manual" and apply(repo, True, False) == []   # PA3's file: never written
    (repo / publish.PA3_REL).unlink()
    settings.write_text("[]\n")
    ok &= acts()["style-hook"]["owner"] == "manual"                           # not a JSON object
    settings.write_text(json.dumps(full, indent=2) + "\n")
    # ste-rule: manual without the game's tool; with it added, present whatever its date line, rewritten on another body
    act, tool = acts()["ste-rule"], repo / common.STE_TOOL
    ok &= act["owner"] == "manual" and str(common.PROFILE_STE) in act["what"]
    tool.write_text(RULES_STUB, encoding="utf-8")
    ok &= acts()["ste-rule"]["owner"] == "psxdecomp" and not rule.exists()
    ok &= apply(repo, True, False) == ["would be created %s" % x for x in (common.STE_RULE, common.STE_INDEX)]
    ok &= not rule.exists() and {common.STE_RULE, common.STE_INDEX} <= set(written_paths(apply(repo, False, False)))
    text = common.read(rule)
    ok &= text.startswith("# STE1 — %s\nid: STE1 · group: STE · status: active · tags: writing,public · origin: psxdecomp"
                          % common.STE_TITLE) and text.endswith("\n\n" + common.read(common.PROFILE_STE))
    ok &= "\nSTE1 | %s | writing,public | active | psxdecomp\n" % common.STE_TITLE in common.read(repo / common.STE_INDEX)
    ok &= "ste-rule" not in acts()
    rule.write_text(re.sub(r"added: \S+", "added: 2001-01-01", text), encoding="utf-8")
    ok &= "added: 2001" in common.read(rule) and "ste-rule" not in acts()     # the date line is never compared
    rule.write_text(text + "\nAn edit.\n", encoding="utf-8")
    ok &= "ste-rule: rewrite " in acts()["ste-rule"]["what"]
    ok &= apply(repo, True, False) == ["would be changed %s" % x for x in (common.STE_RULE, common.STE_INDEX)]
    tool.write_text("import sys\nsys.exit('refused: not today')\n")      # the tool's refusal is a failure, with its text
    try:
        apply(repo, False, False)
        ok = False
    except common.Fail as e:
        ok &= "refused: not today" in str(e)
    tool.write_text(RULES_STUB, encoding="utf-8")
    ok &= written_paths(apply(repo, False, False)) == [common.STE_RULE] and common.read(rule) == text   # the index: as is
    # ai-policy: the block's three lines, the rest byte for byte; the ratchet is written after it, once
    readme, block, aged = repo / "README.md", common.ai_policy_block(), "# G\n\nLead.\n\n%s\n## Status\n\nOurs; kept.\n"
    old = block.replace("decisions. AI reads", "decisions; AI reads")
    readme.write_text(aged % old)
    rat.unlink()
    for rel in ("docs/a.md", common.KIT_PROSE[0]):
        common.write(repo / rel, "Run it; then stop.\n")
    act = acts()
    ok &= "Humans drive the decisions; AI reads and writes the code." in old and act["ai-policy"]["owner"] == "psxdecomp"
    fails = sum(f[0] == "FAIL" for f in publish.lint(aged % block, publish.Ctx(repo)))   # the README as ai-policy leaves it
    ok &= "README: %d lint failure(s)" % fails in act["readme"]["what"] and act["style-ratchet"]["owner"] == "psxdecomp"
    ok &= apply(repo, True, False) == ["would be changed README.md", "would be created %s" % publish.STYLE_RATCHET_REL]
    ok &= written_paths(apply(repo, False, False)) == ["README.md", publish.STYLE_RATCHET_REL]
    rows, skip, head = publish.parse_ratchet(rat.read_text())
    ok &= readme.read_text() == aged % block and not {"ai-policy", "style-ratchet"} & set(acts())
    ok &= rows == {"README.md": 1, "docs/a.md": 1} and skip == list(common.KIT_PROSE)   # the README as ai-policy left it
    ok &= len(head) == 3 and "python3 tools/psxd_publish.py style --update" in head[1]
    kept = rat.read_text()
    (repo / "docs/a.md").write_text("Run it; then stop; then go.\n")     # a count changes later: the file is the game's
    ok &= "style-ratchet" not in acts() and written_paths(apply(repo, False, False)) == [] and rat.read_text() == kept
    readme.write_text("# G\n")                                                # no block: the README lint's action alone
    ok &= "ai-policy" not in acts() and "readme" in acts()
    readme.unlink()
    pub = repo / PUBLIC_LIST                                             # split mode: the public CI needs the ratchet
    pub.write_text("README.md\n")
    ok &= acts()["style-public"]["owner"] == "manual"
    pub.write_text("README.md\nconfig/style-*.txt\n")
    ok &= "style-public" not in acts()
    pub.unlink()
    left = {"ai-policy", "ste-rule", "style-hook", "style-ratchet", "style-public"} & set(acts())
    return ok and not left and apply(repo, True, False) == []


def self_test() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td)
        common.git(repo, "init", "--quiet")
        (repo / "HOW_WE_WORK.md").write_text("# card\n## Docs map\n- a\n\n## Next\n")
        (repo / ".gitignore").write_text("/.run/*\n")
        ok &= {x["key"] for x in plan(repo)} == {"pa3", "kit"}          # not PA3: only manual steps
        (repo / ".claude").mkdir()
        (repo / ".claude/pa.json").write_text(json.dumps({"pa_version": "3.14.1", "python": "/nonexistent/python"}))
        keys = {x["key"] for x in plan(repo)}
        ok &= {"adopt", "refs-add", "ignore", "pa3", "python", "kit", "publish", "card-conv"} <= keys
        before = sorted(p.name for p in repo.rglob("*") if ".git" not in p.parts)
        dry = apply(repo, True, False)
        ok &= sorted(p.name for p in repo.rglob("*") if ".git" not in p.parts) == before and len(dry) >= 4
        first = apply(repo, False, False)
        ok &= (repo / "config/refs.toml").is_file() and (repo / "docs/ops/refs.md").is_file()
        ok &= "docs/ops/refs.md" in written_paths(first)                  # a new index is a path to commit
        ok &= install.REFS_RULE in (repo / "HOW_WE_WORK.md").read_text()
        ok &= self_test_card(repo)
        keys2 = {x["key"] for x in plan(repo)}
        ok &= "deny" in keys and not ({"adopt", "refs-add", "ignore", "publish", "deny"} & keys2)
        want = json.loads(common.read(common.PROFILE_DENY))["permissions"]["deny"]
        ok &= json.loads((repo / common.SETTINGS).read_text())["permissions"]["deny"] == want
        # add-only: the game's own rules and keys stay, in place; only the missing rules are appended
        mine = {"model": "m", "permissions": {"allow": ["Bash(git add:*)"], "deny": ["Bash(git push:*)", want[3]]}}
        (repo / common.SETTINGS).write_text(json.dumps(mine, indent=2) + "\n")
        ok &= next(x for x in plan(repo) if x["key"] == "deny")["owner"] == "psxdecomp"
        apply(repo, False, False)
        got = json.loads((repo / common.SETTINGS).read_text())
        ok &= got["model"] == "m" and got["permissions"]["allow"] == ["Bash(git add:*)"] and got["permissions"][
            "deny"] == ["Bash(git push:*)", want[3]] + [r for r in want if r != want[3]]
        ok &= "deny" not in {x["key"] for x in plan(repo)}
        (repo / publish.PA3_REL).write_text(json.dumps({"files": {common.SETTINGS: "h"}}))
        (repo / common.SETTINGS).write_text("{}\n")
        ok &= next(x for x in plan(repo) if x["key"] == "deny")["owner"] == "manual"   # PA3's file: never written
        (repo / publish.PA3_REL).unlink()
        (repo / common.SETTINGS).write_text(json.dumps({"permissions": {"deny": want}}, indent=2) + "\n")
        ok &= (repo / publish.VENDORED).read_bytes() == OWNED[publish.VENDORED].read_bytes()
        (repo / "README.md").write_text("# G\n\n%s\n## Status\n" % common.ai_policy_block())
        readme = next((x for x in plan(repo) if x["key"] == "readme"), None)
        ok &= readme is not None and readme["owner"] == "manual" and "missing ## Description" in readme["what"]
        (repo / "README.md").unlink()
        ok &= self_test_style(repo)
        ok &= apply(repo, True, False) == []                     # a second apply has nothing to do
        rec = (repo / install.RECORD).read_text()                # an older record: apply bumps its version, only that
        old = rec.replace('version = "%s"' % common.plugin_version(), 'version = "0.1.0"', 1)
        (repo / install.RECORD).write_text(old)
        ok &= old != rec and "version" in {x["key"] for x in plan(repo)}
        apply(repo, False, False)
        ok &= (repo / install.RECORD).read_text() == rec and "version" not in {x["key"] for x in plan(repo)}
        # the public list is opt-in: without it nothing new; with it build.yml, once, with what upgrade can read
        ok &= "build" not in {x["key"] for x in plan(repo)}
        (repo / "config/public-paths.txt").write_text("config/public-paths.txt\n")
        (repo / "config/discs.tsv").write_text(publish.SELF_DISCS)
        toml = repo / "config/psxdecomp.toml"
        saved = toml.read_text() if toml.is_file() else None
        toml.write_text((saved or "") + '\n[public]\nrepo = "Example/Game"\n')
        ok &= {"build", "build-fill", "split-doc"} <= {x["key"] for x in plan(repo)}
        apply(repo, False, False)
        card = repo / "docs/ops/psxdecomp-split.md"
        ok &= card.read_bytes() == SPLIT_OWNED["docs/ops/psxdecomp-split.md"].read_bytes()
        card.write_text("an edited copy\n")
        ok &= "split-doc" in {x["key"] for x in plan(repo)}                # owned: an edited copy is rewritten
        apply(repo, False, False)
        ok &= "split-doc" not in {x["key"] for x in plan(repo)} and card.read_text() != "an edited copy\n"
        built = (repo / ".github/workflows/build.yml").read_text()
        ok &= ("if: github.repository == 'Example/Game'" in built and 'exe: ["PSXD_000.01"]' in built
               and "{{BUILD_COMMAND}}" in built)
        (repo / ".github/workflows/build.yml").write_text("# the game's own\n")
        apply(repo, False, False)
        ok &= (repo / ".github/workflows/build.yml").read_text() == "# the game's own\n"   # never overwritten
        ok &= "build" not in {x["key"] for x in plan(repo)}
        for rel in ("config/public-paths.txt", "config/discs.tsv", ".github/workflows/build.yml",
                    "docs/ops/psxdecomp-split.md"):
            (repo / rel).unlink()
        ok &= "split-doc" not in {x["key"] for x in plan(repo)}            # split mode only
        if saved is None:
            toml.unlink()
        else:
            toml.write_text(saved)
        # an older refs.toml (a dropped row, no authority/traps) gains the new rows and tables; the dropped row is manual
        old = fetch_refs.load_rows(PROFILE_REFS)[:2] + [dict(fetch_refs.load_rows(PROFILE_REFS)[0], name="psn00bsdk")]
        (repo / "config/refs.toml").write_text("".join(toml_table("ref", r) for r in old))
        keys3 = {x["key"] for x in plan(repo)}
        ok &= {"refs-rows", "refs-meta", "refs-gone"} <= keys3
        apply(repo, False, False)
        doc = fetch_refs.load_doc(repo / "config/refs.toml")
        ok &= fetch_refs.lint_doc(doc) == [] and bool(doc["authority"]) and bool(doc["traps"])
        ok &= {x["key"] for x in plan(repo)} == {"refs-gone", "pa3", "python", "kit"}
    return common.self_test_banner("upgrade", ok)


if __name__ == "__main__":
    sys.exit(main())
