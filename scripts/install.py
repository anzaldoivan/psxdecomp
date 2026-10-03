#!/usr/bin/env python3
"""install.py — the deterministic stages of /psxdecomp:new, and the whole pipeline for canned answers.

    install.py stage S5|S6|S7|S8|S9|S10 --target DIR [options]     one stage (the skill calls these)
    install.py run --target DIR --answers FILE --dump CUE [options]  S0, S2, S5-S10 unattended (tier 1, CI)
    install.py plan [--target DIR]                                   the stage table and each stage's state
    install.py --self-test                                           the pipeline on the homebrew fixture

Options: --dry-run · --force-untested (recorded as a deviation) · --kit DIR · --pa3-source URL|PATH ·
--config-dir DIR / --pa3-dir DIR (PA3's own flags, passed through) · --python EXE · --no-fetch (S9 writes the index
only) · --intake-fixture (S7 writes the canned constitution: tests only, recorded) · --until SID.

Stage contract (skills/new/reference/stages.md): every stage reads only the target's .run/bootstrap/ and the pins,
writes only what its row names, marks .run/bootstrap/state.json, and is safe to re-run (a second run writes nothing).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import answers as answers_mod  # noqa: E402
import common  # noqa: E402
import fetch_refs  # noqa: E402

BOOT = ".run/bootstrap"
KIT_ANSWERS = ".run/decomp-architect/answers.txt"
RECORD = "config/psxdecomp.toml"
PSX_MARK = "# ---- psxdecomp"
SPDX_GH = {"MIT": "mit", "AGPL-3.0": "agpl-3.0", "GPL-3.0": "gpl-3.0", "GPL-2.0": "gpl-2.0", "Apache-2.0": "apache-2.0",
           "BSD-3-Clause": "bsd-3-clause", "BSD-2-Clause": "bsd-2-clause", "MPL-2.0": "mpl-2.0", "CC0-1.0": "cc0-1.0",
           "Unlicense": "unlicense"}
REFS_RULE = ("- **References:** `refs/` holds pinned upstream clones (index: `docs/ops/refs.md`, by licence class). "
             "Grep it or dispatch `retriever-code`; never Read a `refs/` tree whole; web only for what it lacks.")


class Ctx:
    def __init__(self, a):
        self.a = a
        self.target = pathlib.Path(a.target).resolve()
        self.dry = a.dry_run
        self.state = common.State(self.target)
        self.devs: list[str] = list(self.state.get("deviations", []))
        self.written: list[str] = []
        self.vals: dict | None = None          # `run` hands its parsed answers over (a dry run writes no file)

    def p(self, rel) -> pathlib.Path:
        return self.target / rel

    def boot(self, rel) -> pathlib.Path:
        return self.target / BOOT / rel

    def write(self, rel, text, mode=None):
        st = common.write(self.p(rel), text, dry=self.dry, mode=mode)
        if st != "unchanged":
            self.written.append("%s %s" % ("would be " + st if self.dry else st, rel))
        return st

    def deviation(self, text):
        if text not in self.devs:
            self.devs.append(text)
            if not self.dry:
                self.state.set("deviations", self.devs)

    def answers(self) -> dict:
        if self.vals is not None:
            return self.vals
        f = self.boot("answers.txt")
        if not f.is_file():
            raise common.Fail("no %s/answers.txt — S4 (the gate) writes it; or pass --answers to `run`" % BOOT)
        return answers_mod.scope_candidate(answers_mod.parse(common.read(f))[0])

    def git(self, *a, check=True):
        return common.git(self.target, *a, check=check)

    def commit(self, paths, msg):
        if self.dry:
            return "dry-run"
        paths = [p for p in paths if self.p(p).exists() or self.git("ls-files", "--error-unmatch", p,
                                                                    check=False).returncode == 0]
        if not paths:
            return "nothing"
        self.git("add", "--", *paths)
        if self.git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return "nothing"
        self.git("commit", "--quiet", "-m", msg, "--", *paths)
        return self.git("rev-parse", "--short", "HEAD").stdout.strip()

    def python(self) -> str:
        py = common.find_python((3, 12), self.a.python or os.environ.get("CLAUDE_PLUGIN_OPTION_PYTHON_PATH"))
        if not py:
            raise common.Fail("no Python >= 3.12 on this machine (PA3's hooks need one)")
        return py


# ---- S5 repo --------------------------------------------------------------------------------------------------

def s5_repo(c: Ctx) -> str:
    """git init, the licence, and the kit's ROM firewall pack as the FIRST commit, after its negative control."""
    ans = c.answers()
    kit, devs = common.resolve_kit(c.a.force_untested, c.a.kit)
    for d in devs:
        c.deviation(d)
    tpl = kit / "templates"
    if not c.dry:
        c.target.mkdir(parents=True, exist_ok=True)
        if not c.p(".git").exists():
            common.run(["git", "init", "--quiet", "-b", "main", str(c.target)])
    # .gitignore: our own block first (the bootstrap's scratch and refs/ are never tracked), then the kit's block,
    # byte for byte as the kit's S2 appends it (so the kit later reports it present and leaves it alone).
    gi = c.p(".gitignore")
    text = common.read(gi) if gi.is_file() else ""
    if PSX_MARK not in text:
        text += ("" if not text or text.endswith("\n") else "\n") + (
            "%s (the bootstrap's scratch and the reference library; never tracked) ----\n/.run/*\n!/.run/README.md\n"
            "/refs/\n" % PSX_MARK)
    kit_mark = "# ROM firewall — in force from the FIRST commit"
    if kit_mark not in text:
        text += "\n# ---- decomp-architect, installed %s ----\n" % common.today() + common.read(tpl / "gitignore.decomp")
    c.write(".gitignore", text)
    # each file exactly as the kit's S2 writes it; an existing one is left alone (the kit's own rule: "present")
    for rel, body, mode in (
            ("config/firewall.txt", common.read(tpl / "firewall.txt").replace("{{TARGET_BINARY}}",
                                                                             ans["TARGET_BINARY"]), None),
            ("config/firewall-fixture.sha1", common.read(tpl / "firewall-fixture" / "blob.sha1"), None),
            ("tools/audit_public.py", common.read(tpl / "audit_public.template.py"), 0o755),
            (".github/workflows/no-rom.yml", common.read(tpl / "no-rom.template.yml"), None)):
        if not c.p(rel).exists():
            c.write(rel, body, mode=mode)
    lic = licence_text(c, ans)
    if lic:
        c.write("LICENSE", lic)
    if c.dry:
        return "would init git, write the firewall pack, run the negative control, commit"
    planted = c.p(".run/firewall-control/planted.bin")
    planted.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tpl / "firewall-fixture" / "blob.bin", planted)
    py = c.python()
    r = common.run([py, "tools/audit_public.py", "--paths", ".run/firewall-control/planted.bin"], cwd=c.target,
                   check=False)
    planted.unlink()
    if r.returncode != 1 or "OFFENDER" not in r.stdout:
        raise common.Fail("the negative control PASSED the planted blob (rc %d): the audit cannot fail, so it proves "
                          "nothing" % r.returncode)
    paths = [".gitignore", "config/firewall.txt", "config/firewall-fixture.sha1", "tools/audit_public.py",
             ".github/workflows/no-rom.yml"] + (["LICENSE"] if lic else [])
    c.git("add", "--", *paths)
    r = common.run([py, "tools/audit_public.py"], cwd=c.target, check=False)
    if r.returncode != 0:
        raise common.Fail("the ROM audit fails on the first commit's tree: %s" % r.stdout.strip()[-300:])
    sha = c.commit(paths, "Firewall first: the ROM firewall pack and its audit (negative control failed on the planted "
                          "blob, passed on the tree)")
    return "negative control: failed on the planted blob, passed on the tree; commit %s" % sha


def licence_text(c: Ctx, ans: dict) -> str | None:
    if c.p("LICENSE").exists():
        return None
    spdx = ans.get("LICENSE_CHOICE", "").split()[0] if ans.get("LICENSE_CHOICE") else ""
    key = SPDX_GH.get(spdx)
    if not key or not shutil.which("gh"):
        return None            # the kit's S9 writes its LICENSE skeleton instead
    r = common.run(["gh", "api", "licenses/%s" % key, "--jq", ".body"], check=False, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    who = c.git("config", "user.name", check=False).stdout.strip() or "the authors"
    return r.stdout.replace("[year]", common.today()[:4]).replace("[fullname]", who)


# ---- S6 PA3 ---------------------------------------------------------------------------------------------------

def s6_pa3(c: Ctx) -> str:
    """PA3 at the pinned tag, per repository, from its own unattended path (`--project --yes`)."""
    ans = c.answers()
    pkg, devs = common.resolve_pa3(c.a.force_untested, c.a.pa3_source, dry=c.dry)
    for d in devs:
        c.deviation(d)
    pa = c.p(".claude/pa.json")
    if pa.is_file():
        ver = json.loads(common.read(pa)).get("pa_version")
        return "PA3 %s already installed here%s. %s" % (ver, upgrade_ask(c), RESTART)
    conf = pathlib.Path(c.a.config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"))
    pa3_dir = pathlib.Path(c.a.pa3_dir) if c.a.pa3_dir else conf / "pa3"
    py = c.python()
    if not (pa3_dir / "VERSION").is_file():
        # --no-clone: install from the pinned cache clone; without it PA3 clones its upstream's default branch into
        # <config>/pa3-src and follows it (pull --ff-only), so the machine drifts off the pin.
        raise common.Fail("PA3 is not installed on this machine. Run it once yourself (it edits %s/settings.json, "
                          "after a backup):\n    %s %s --root --no-clone\nthen re-run with --resume"
                          % (conf, py, pkg / "pa_install.py"))
    name = ans.get("PSXDECOMP_PROJECT_NAME") or common.slug(ans["GAME_TITLE"])
    cmd = [py, pkg / "pa_install.py", "--project", c.target, "--yes", "--name", name,
           "--tagline", "%s — a matching decompilation" % ans["GAME_TITLE"], "--python", py]
    if c.a.config_dir:
        cmd += ["--config-dir", c.a.config_dir]
    if c.a.pa3_dir:
        cmd += ["--pa3-dir", c.a.pa3_dir]
    if c.dry:
        cmd.append("--dry-run")
    r = common.run(cmd, check=False, timeout=600)
    common.write(c.boot("pa3-install.txt"), r.stdout + r.stderr, dry=c.dry)
    if r.returncode != 0:
        raise common.Fail("PA3's installer failed (rc %d): %s" % (r.returncode, (r.stdout + r.stderr).strip()[-600:]))
    if c.dry:
        return "PA3 dry run OK (%s)" % r.stdout.strip().splitlines()[-1]
    gi = common.read(c.p(".gitignore"))
    fixed = pa3_block_first(gi)
    if fixed != gi:
        # S5 wrote the firewall before PA3 existed, so PA3 appended its block (with `/.run/*`) after the kit's
        # `!/.run/README.md`. Restore the kit's tested order: PA3's block first, the firewall block after it.
        common.write(c.p(".gitignore"), fixed)
        c.commit([".gitignore"], "Order .gitignore as the kit's tested install does: PA3's block first, then the "
                                 "ROM firewall block")
    got = json.loads(common.read(pa)).get("pa_version")
    if got != common.compat()["pa3"]["version"] and not c.a.force_untested:
        raise common.Fail("PA3 installed version %s, compat.toml pins %s" % (got, common.compat()["pa3"]["version"]))
    up = upgrade_ask(c)
    dirty = c.git("status", "--porcelain").stdout.strip()
    if dirty:
        # PA3 commits its own install; anything left is its intentionally-uncommitted local state
        c.deviation("PA3 left uncommitted paths after its install: %s" % ", ".join(
            l[3:] for l in dirty.splitlines()[:5]))
    return "PA3 %s installed (%s)%s. %s" % (got, name, up, RESTART)


RESTART = "Exit, then run `claude --agent plain` here and type `/psxdecomp:new --resume`."
UPGRADE_RE = re.compile(r'("pa_version"\s*:\s*"[^"]*",)')


def with_upgrade_ask(text: str) -> str:
    """pa.json text with `"upgrade": "ask"` (after pa_version, PA3's layout kept); unchanged when already ask."""
    if json.loads(text).get("upgrade") == "ask":
        return text
    if '"upgrade"' in text:
        new = re.sub(r'("upgrade"\s*:\s*)("[^"]*"|null)', r'\1"ask"', text, count=1)
    else:
        new = UPGRADE_RE.sub(lambda m: m.group(1) + '\n  "upgrade": "ask",', text, count=1)
    if json.loads(new).get("upgrade") != "ask":
        raise common.Fail(".claude/pa.json: could not set \"upgrade\": \"ask\" (no pa_version line)")
    return new


def upgrade_ask(c: Ctx) -> str:
    """`"upgrade": "ask"` in .claude/pa.json, committed. PA3 reads a missing key as auto: its router would upgrade
    before the first task, off the pin. Text-level, so PA3's own layout stays; returns a note for the DONE line."""
    pa = c.p(".claude/pa.json")
    if c.dry or not pa.is_file():
        return ""
    text = common.read(pa)
    new = with_upgrade_ask(text)
    if new == text:
        return ""
    common.write(pa, new)
    sha = c.commit([".claude/pa.json"], "PA3 upgrades ask first: .claude/pa.json \"upgrade\": \"ask\" (psxdecomp pins PA3 "
                                        "%s)" % common.compat()["pa3"]["version"])
    return "; pa.json upgrade: ask (commit %s)" % sha


PA3_GI_HEAD = "# Project Architect 3.0"


def pa3_block_first(text: str) -> str:
    """Move PA3's .gitignore block (its heading to the next blank line) to the top of the file."""
    lines = text.split("\n")
    if PA3_GI_HEAD not in lines:
        return text
    i = lines.index(PA3_GI_HEAD)
    if i == 0:
        return text
    j = i + 1
    while j < len(lines) and lines[j].strip():
        j += 1
    block = lines[i:j]
    rest = lines[:i] + lines[j:]
    while rest and rest[-1] == "" and len(rest) > 1 and rest[-2] == "":
        rest.pop()
    while rest and not rest[0].strip():
        rest.pop(0)
    return "\n".join(block + [""] + rest)


# ---- S7 intake (fixture only; the real intake is the skill's, in a plain session) -------------------------------

def s7_intake(c: Ctx) -> str:
    if c.p("PROJECT_CONTEXT.md").is_file():
        return "PROJECT_CONTEXT.md present (the intake ran)"
    if not c.a.intake_fixture:
        raise common.Fail("the intake is a model stage: open `claude --agent plain` in this repository and run "
                          "`/psxdecomp:new --resume` (it hands PA3's intake the kit's intake.decomp.md)")
    ans = c.answers()
    text = common.read(common.PLUGIN_ROOT / "fixtures" / "PROJECT_CONTEXT.fixture.md").replace(
        "{{GAME_TITLE}}", ans["GAME_TITLE"])
    c.write("PROJECT_CONTEXT.md", text)
    c.deviation("S7 used the canned fixture constitution (--intake-fixture): a test install, not a project")
    sha = c.commit(["PROJECT_CONTEXT.md"], "Intake (fixture): the canned constitution for a test install")
    return "fixture constitution committed %s" % sha


# ---- S8 kit ---------------------------------------------------------------------------------------------------

WOULD_RE = re.compile(r"^\s+would (created|edited|appended|changed) (\S+)")
WROTE_RE = re.compile(r"^- (created|changed|edited|appended) `([^`]+)`")


def s8_kit(c: Ctx) -> str:
    """The pinned decomp-architect installer: its dry run first, then the run; the two path lists are compared."""
    kit, devs = common.resolve_kit(c.a.force_untested, c.a.kit)
    for d in devs:
        c.deviation(d)
    record = c.p("docs/decomp-architect-install.md")
    if record.is_file():
        return "kit already installed (docs/decomp-architect-install.md)%s" % readme_policy(c)
    ans = c.answers()
    kit_vals, _ = answers_mod.split(ans)
    if not kit_vals.get("DUMP_PATH"):
        raise common.Fail("DUMP_PATH is empty; the kit needs the absolute path of your dump (it is never copied)")
    note = ["# Drafted by psxdecomp %s from the interview, the disc probe (S2) and the research (S3); confirmed by "
            "the developer at the gate (S4)." % common.plugin_version()]
    c.write(KIT_ANSWERS, answers_mod.render(kit_vals, note))
    if c.dry:
        return "would run the kit's dry run and install"
    py = c.python()
    base = [py, kit / "install.py", "--project", c.target, "--answers", c.p(KIT_ANSWERS)]
    r = common.run(base + ["--dry-run"], check=False, timeout=600)
    common.write(c.p(".run/decomp-architect/dryrun.txt"), r.stdout + r.stderr)
    if r.returncode != 0:
        raise common.Fail("the kit's dry run failed: %s" % (r.stdout + r.stderr).strip()[-600:])
    would = {m.group(2) for m in map(WOULD_RE.match, r.stdout.splitlines()) if m}
    r = common.run(base, check=False, timeout=900)
    common.write(c.p(".run/decomp-architect/install.txt"), r.stdout + r.stderr)
    if r.returncode != 0:
        raise common.Fail("the kit's installer failed: %s" % (r.stdout + r.stderr).strip()[-600:])
    wrote = {m.group(2) for m in map(WROTE_RE.match, common.read(record).splitlines()) if m}
    extra = sorted(would - wrote)
    if extra:
        c.deviation("the kit's dry run named paths its run did not write: %s" % ", ".join(extra[:6]))
    last = [l for l in r.stdout.splitlines() if l.startswith("summary:")]
    return "%s; dry run listed %d of the %d written paths%s" % (last[0] if last else "kit installed",
                                                               len(would & wrote), len(wrote), readme_policy(c))


def readme_policy(c: Ctx) -> str:
    """The AI policy block in README.md under its lead, in place of the kit's disclosure paragraph, committed. The
    kit writes the README (its S9 skeleton; an existing README would make it write README.decomp-skeleton.md for a
    hand merge), so this runs right after it. Idempotent; S10 calls it again for a repo whose S8 predates it."""
    readme = c.p("README.md")
    if c.dry or not readme.is_file():
        return ""
    old = common.read(readme)
    try:
        disc = c.answers().get("AI_DISCLOSURE")
    except common.Fail:
        disc = None
    new = common.with_ai_policy(old, replace=disc)
    if new == old:
        return ""
    c.write("README.md", new)
    sha = c.commit(["README.md"], "README: the AI policy block under the lead%s" % (
        ", in place of the kit's disclosure paragraph" if common.swappable_disclosure(disc) else ""))
    return "; README AI policy (commit %s)" % sha


# ---- S9 refs --------------------------------------------------------------------------------------------------

def s9_refs(c: Ctx) -> str:
    src = c.boot("refs.toml")
    if not src.is_file():
        src = common.PLUGIN_ROOT / "profiles" / "psx" / "refs.toml"
    rows = fetch_refs.load_rows(src)
    errs = fetch_refs.lint_doc(fetch_refs.load_doc(src))
    if errs:
        raise common.Fail("refs.toml: %s" % "; ".join(errs[:4]))
    c.write("config/refs.toml", common.read(src))
    gi = common.read(c.p(".gitignore"))
    if "/refs/" not in gi.splitlines():
        c.write(".gitignore", gi + ("" if gi.endswith("\n") else "\n") + "%s ----\n/refs/\n" % PSX_MARK)
    # Claude's content search (ripgrep) honours .gitignore inside a git repository, so a root search would skip refs/.
    # ripgrep's .ignore outranks .gitignore: `!/refs/` re-includes it for search only; git still ignores it.
    ig = common.read(c.p(".ignore")) if c.p(".ignore").is_file() else ""
    if "!/refs/" not in ig.splitlines():
        c.write(".ignore", ig + ("" if not ig or ig.endswith("\n") else "\n") + "%s: search refs/ though git ignores "
                "it ----\n!/refs/\n" % PSX_MARK)
    fw = c.p("config/firewall.txt")
    if fw.is_file() and "purge: refs/" not in common.read(fw):
        c.write("config/firewall.txt", common.read(fw).rstrip("\n") +
                "\n\n%s: the reference library (upstream clones; never tracked) ----\npurge: refs/\n" % PSX_MARK)
    how = c.p("HOW_WE_WORK.md")
    if how.is_file() and REFS_RULE not in common.read(how):
        c.write("HOW_WE_WORK.md", insert_in_section(common.read(how), "## Docs map", REFS_RULE))
    ops = c.p("docs/ops/INDEX.md")
    if ops.is_file() and "refs.md" not in common.read(ops):
        c.write("docs/ops/INDEX.md", common.read(ops).rstrip("\n") +
                "\n- [refs.md](refs.md) — the reference library: pinned upstream sources by licence class (generated "
                "by psxdecomp's fetch_refs.py)\n")
    if c.dry:
        return "would write config/refs.toml and fetch %d core rows" % sum(fetch_refs.wanted(r, [], False) for r in rows)
    args = ["--repo", str(c.target)] + (["--index-only"] if c.a.no_fetch else [])
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fetch_refs.main(args)
    common.write(c.boot("refs-fetch.txt"), buf.getvalue())
    if rc != 0:
        raise common.Fail("fetch_refs failed: %s" % buf.getvalue().strip()[-400:])
    card_check(c)
    py = c.python()
    if c.p("tools/audit_public.py").is_file():
        r = common.run([py, "tools/audit_public.py"], cwd=c.target, check=False)
        if r.returncode != 0:
            raise common.Fail("the ROM audit fails after the refs change: %s" % r.stdout.strip()[-300:])
    sha = c.commit(["config/refs.toml", ".gitignore", ".ignore", "config/firewall.txt", "HOW_WE_WORK.md",
                    "docs/ops/INDEX.md", "docs/ops/refs.md"],
                   "Reference library: config/refs.toml pinned, docs/ops/refs.md index, refs/ ignored (searchable "
                   "through .ignore) and purged")
    last = buf.getvalue().strip().splitlines()[-1]
    return "%s; commit %s" % (last, sha)


def card_check(c: Ctx):
    """PA3's card check over HOW_WE_WORK.md (S9's refs rule, S10's scope line): its size cap and placeholders."""
    card = c.p("tools/card.py")
    if card.is_file():
        r = common.run([c.python(), card, "check"], cwd=c.target, check=False)
        if r.returncode != 0:
            raise common.Fail("PA3's card check refused the HOW_WE_WORK line: %s" % (r.stdout + r.stderr).strip()[-300:])


def insert_in_section(text: str, heading: str, line: str) -> str:
    """Append `line` at the end of the `heading` section (before the next `## `), or at the end of the file."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith(heading)), None)
    if start is None:
        return text.rstrip("\n") + "\n" + line + "\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, line)
    return "\n".join(lines)


# ---- S10 handoff ----------------------------------------------------------------------------------------------

SCOPE_MARK = "- **This repo:**"


def psyq_record(medium: dict | None) -> tuple[list[str], str]:
    """The game's one psyq.toml row as config/psxdecomp.toml [psyq] lines, and the version for the scope line."""
    if not medium:
        return [], "unknown (S2 did not run)"
    p = medium.get("psyq", {})
    v = p.get("version")
    cat = common.load_toml(common.PLUGIN_ROOT / "profiles" / "psx" / "psyq.toml")
    row = next((r for r in cat["version"] if r["id"] == v), None)
    out = ["# [psyq]: the PsyQ release the game links, from psxdecomp's psyq.toml (seen %s). A lead for phase 1.4;"
           % cat["meta"]["seen"], "# the pin is phase 1.4's finding and lives in the repo's compiler-pin record.", "[psyq]"]
    q = lambda s: json.dumps(s, ensure_ascii=False)  # noqa: E731
    if row:
        out += ["stamp = %s" % q(row["stamp"]), "version = %s" % q(row["id"])]
        out += ["%s = %s" % (k, q(row[k])) for k in ("ships_compiler", "cc1_banner", "aspsx", "old_gcc", "confidence")]
    else:
        out += ["version = %s" % q(v or "none"), 'confidence = "unknown"',
                "note = %s" % q(p.get("note") or "no psyq.toml row for these stamps: read each version's row")]
    out += ['status = "lead — never the pin"', ""]
    return out, (v or "unstamped")


def s10_handoff(c: Ctx) -> str:
    ans = c.answers()
    comp = common.compat()
    prof = common.load_toml(common.PLUGIN_ROOT / "profiles" / "psx" / "profile.toml")
    pre = c.boot("preflight.json")
    recipe = "macos-arm64"
    if pre.is_file():
        for row in json.loads(common.read(pre))["checks"]:
            if row["name"] == "host":
                recipe = row.get("recipe", recipe)
    recipe = os.environ.get("CLAUDE_PLUGIN_OPTION_DOCKER_HOST") or recipe
    devs = c.devs or ["none"]
    rec = ["# config/psxdecomp.toml — how this repository was bootstrapped. Read by /psxdecomp:doctor and :upgrade;",
           "# the repository works without the plugin. Written once by psxdecomp's S10; upgrades rewrite it.", "",
           "[psxdecomp]", 'version = "%s"' % common.plugin_version(), 'profile = "%s"' % prof["console"]["id"],
           'bootstrapped = "%s"' % common.today(), "", "[pa3]",
           'tag = "%s"' % comp["pa3"]["tag"], 'sha = "%s"' % comp["pa3"]["sha"], 'version = "%s"' % comp["pa3"]["version"],
           'upgrade = "%s"  # .claude/pa.json: S6 sets "ask" so PA3 never upgrades off the pin unasked' % pa_upgrade(c),
           "", "[kit]", 'digest = "%s"' % comp["kit"]["digest"], 'repo = "%s"' % comp["kit"]["repo"],
           'sha = "%s"' % comp["kit"]["sha"], "", "[refs]", 'file = "config/refs.toml"', 'index = "docs/ops/refs.md"',
           "", "[host]", 'recipe = "%s"' % recipe, "", "[deviations]",
           "list = [%s]" % ", ".join(json.dumps(d) for d in devs), ""]
    med = c.boot("medium.json")
    medium = json.loads(common.read(med)) if med.is_file() else None
    psyq_lines, psyq_v = psyq_record(medium)
    rec += psyq_lines
    # written once: a re-run on a later day leaves the record alone (/psxdecomp:upgrade is what rewrites it)
    for rel, body in ((RECORD, "\n".join(rec)),
                      ("config/psxdecomp.profile.toml", common.read(common.PLUGIN_ROOT / "profiles/psx/profile.toml")),
                      ("docs/ops/host-recipe.md", common.read(common.PLUGIN_ROOT / ("profiles/psx/hosts/%s.md" % recipe)))):
        if not c.p(rel).exists():
            c.write(rel, body)
    paths = [RECORD, "config/psxdecomp.profile.toml", "docs/ops/host-recipe.md"]
    pa_src = c.boot("prior-art.md")
    if pa_src.is_file() and not c.p("docs/prior-art.md").exists():
        c.write("docs/prior-art.md", common.read(pa_src))
        paths.append("docs/prior-art.md")
    readme_policy(c)                              # S8 did it; a repo whose S8 predates it gets it here
    how = c.p("HOW_WE_WORK.md")
    if how.is_file() and SCOPE_MARK not in common.read(how):
        c.write("HOW_WE_WORK.md", insert_in_section(common.read(how), "## Docs map", scope_line(ans, psyq_v)))
        paths.append("HOW_WE_WORK.md")
    seeds = c.boot("seeds.txt")
    if c.dry:
        return "would write the record, the profile, the host recipe and docs/prior-art.md"
    import doctor
    rows = doctor.check(c.target)
    bad = [r for r in rows if r[1] == "FAIL"]
    for r in rows:
        print("     doctor %-12s %-4s %s" % r)
    if bad:
        raise common.Fail("doctor: %s" % "; ".join("%s: %s" % (r[0], r[2]) for r in bad))
    card_check(c)
    sha = c.commit(paths, "psxdecomp handoff: the bootstrap record (pins, profile, host recipe) and the prior-art "
                          "table")
    nxt = ("Next: a bare `claude` in this repository; PA3's planner drafts GENERATION_PLAN.md from the ladder."
           + (" Phase 1.2 leads: %s." % (BOOT + "/seeds.txt") if seeds.is_file() else ""))
    return "record %s, commit %s. %s" % (RECORD, sha, nxt)


def pa_upgrade(c: Ctx) -> str:
    pa = c.p(".claude/pa.json")
    return (json.loads(common.read(pa)).get("upgrade") or "auto") if pa.is_file() else "none"


def scope_line(ans: dict, psyq_v: str, date: str | None = None) -> str:
    """S10's one HOW_WE_WORK line: which game this repo is, where the compiler pin lives (dated, so it never goes
    stale after the pin), and how to read the kit's calibration text. At most 300 characters."""
    line = ('%s %s (%s), PsyQ %s (lead: config/psxdecomp.toml [psyq]); compiler: docs/ops/compiler-pin.md once phase '
            '1.4 pins it (unpinned at bootstrap, ' + (date or common.today()) + '). Kit text under "provenance: BFM …" '
            'is calibration from gcc 2.7.2; its G/R/P ids are BFM\'s, not this repo\'s rules.')
    title = ans.get("GAME_TITLE", "?")
    out = line % (SCOPE_MARK, title, ans.get("GAME_SERIAL", "?"), psyq_v)
    if len(out) <= 300:
        return out
    short = line.replace(" (%s)", "", 1)
    room = 300 - len(short % (SCOPE_MARK, "", psyq_v))
    return short % (SCOPE_MARK, title[:max(room, 1)], psyq_v)


STAGE_FN = {"S5": s5_repo, "S6": s6_pa3, "S7": s7_intake, "S8": s8_kit, "S9": s9_refs, "S10": s10_handoff}
NAMES = {s[0]: s[1] for s in common.STAGES}


def run_stage(c: Ctx, sid: str) -> int:
    if c.state.status(sid) == "done" and not c.dry:
        common.emit(sid, NAMES[sid], "SKIP", "done earlier")
        return 0
    try:
        note = STAGE_FN[sid](c)
    except common.Fail as e:
        common.emit(sid, NAMES[sid], "FAIL", str(e))
        c.state.mark(sid, "failed", str(e)[:300], dry=c.dry)
        return 1
    for w in c.written:
        print("      %s" % w)
    c.written.clear()
    common.emit(sid, NAMES[sid], "DONE" if not c.dry else "DRY", note)
    c.state.mark(sid, "done", note[:300], dry=c.dry)
    return 0


def cmd_run(a) -> int:
    """S0, S2, S5-S10 from canned answers (S1/S3/S4 are model stages: the answers file stands in for them)."""
    import identify
    import preflight
    c = Ctx(a)
    until = a.until or "S10"
    if c.state.status("S0") != "done":
        if preflight.main(["--target", str(c.target)] + (["--dry-run"] if c.dry else [])
                          + (["--resume"] if c.state.path.is_file() else [])) != 0:
            return 1
        c.state.mark("S0", "done", "preflight OK", dry=c.dry)
    if until == "S0":
        return 0
    vals, note = answers_mod.parse(common.read(resolve_answers(a.answers)))
    if a.dump:
        vals["DUMP_PATH"] = os.path.abspath(a.dump)
    errs = answers_mod.check(vals, allow_no_dump=False)
    if errs:
        for e in errs:
            print("REFUSE %s" % e)
        return 1
    vals = answers_mod.scope_candidate(vals)
    if not c.dry:
        common.write(c.boot("answers.txt"), answers_mod.render(vals, note, extras=True))
        c.state.mark("S1", "skipped", "answers file given (--answers)")
    if c.state.status("S2") != "done":
        if identify.main([vals["DUMP_PATH"], "--target", str(c.target)] + (["--dry-run"] if c.dry else [])) != 0:
            return 1
        c.state.mark("S2", "done", "medium.json written", dry=c.dry)
    c.vals = vals
    for sid in ("S3", "S4"):
        c.state.mark(sid, "skipped", "answers file given (--answers)", dry=c.dry)
    for sid in ("S5", "S6", "S7", "S8", "S9", "S10"):
        if common.STAGE_IDS.index(sid) > common.STAGE_IDS.index(until):
            break
        if run_stage(c, sid):
            return 1
    print("BOOTSTRAP %s through %s" % ("DRY RUN OK" if c.dry else "OK", until))
    return 0


def resolve_answers(arg: str) -> pathlib.Path:
    """`fixture:<name>` names a canned answers file shipped with the plugin (evals, backtests)."""
    if arg.startswith("fixture:"):
        name = arg.split(":", 1)[1]
        for cand in (common.PLUGIN_ROOT / "fixtures" / ("answers.%s.txt" % name),
                     common.PLUGIN_ROOT / "fixtures" / "backtest" / ("%s.answers.txt" % name)):
            if cand.is_file():
                return cand
        raise common.Fail("no fixture answers named %r" % name)
    return pathlib.Path(arg).expanduser().resolve()


def cmd_answers(a) -> int:
    """--answers mode's S1: check the file and copy it to .run/bootstrap/answers.txt (refuses a non-PS1 console)."""
    try:
        src = resolve_answers(a.answers or "")
        vals, note = answers_mod.parse(common.read(src))
    except (common.Fail, OSError) as e:
        print("FAIL %s" % e)
        return 1
    errs = answers_mod.check(vals, allow_no_dump=True)
    if errs:
        for e in errs:
            print("REFUSE %s" % e)
        print("ANSWERS FAIL — nothing installed")
        return 1
    st = common.State(a.target)
    if not a.dry_run:
        common.write(pathlib.Path(a.target).resolve() / BOOT / "answers.txt",
                     answers_mod.render(answers_mod.scope_candidate(vals), note, extras=True))
        st.mark("S1", "skipped", "answers file given (%s)" % src.name)
    print("ANSWERS OK %s: %s, dump %s" % (src.name, vals["GAME_TITLE"], "given" if vals.get("DUMP_PATH") else
                                          "not given (S2 skipped)"))
    return 0


def cmd_plan(a) -> int:
    st = common.State(a.target)
    for sid, name, kind in common.STAGES:
        common.emit(sid, name, st.status(sid).upper(), kind)
    nxt = st.first_open()
    print("NEXT %s" % (nxt or "none (bootstrap complete)"))
    return 0


def parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["stage", "run", "plan", "where", "answers", "mark"])
    ap.add_argument("sid", nargs="?")
    ap.add_argument("--target", default=".")
    ap.add_argument("--answers")
    ap.add_argument("--dump")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-untested", action="store_true")
    ap.add_argument("--kit")
    ap.add_argument("--pa3-source")
    ap.add_argument("--config-dir")
    ap.add_argument("--pa3-dir")
    ap.add_argument("--python")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--intake-fixture", action="store_true")
    ap.add_argument("--until", choices=common.STAGE_IDS)
    ap.add_argument("--status", choices=["done", "skipped", "failed"], default="done")
    ap.add_argument("--note", default="")
    ap.add_argument("--self-test", action="store_true")
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    if a.self_test:
        return self_test()
    if a.cmd == "plan":
        return cmd_plan(a)
    if a.cmd == "where":
        try:
            kit, _ = common.resolve_kit(a.force_untested, a.kit)
            pkg, _ = common.resolve_pa3(a.force_untested, a.pa3_source, dry=True)
        except common.Fail as e:
            print("FAIL %s" % e)
            return 1
        print("KIT %s\nINTAKE %s\nPA3 %s" % (kit, kit / "intake.decomp.md", pkg))
        return 0
    if a.cmd == "answers":
        return cmd_answers(a)
    if a.cmd == "mark":
        if a.sid not in common.STAGE_IDS:
            print("FAIL mark needs a stage id (%s)" % ", ".join(common.STAGE_IDS))
            return 1
        common.State(a.target).mark(a.sid, a.status, a.note, dry=a.dry_run)
        common.emit(a.sid, NAMES[a.sid], a.status.upper(), a.note)
        return 0
    if a.cmd == "run":
        if not a.answers:
            print("FAIL run needs --answers")
            return 1
        return cmd_run(a)
    if a.cmd == "stage":
        if a.sid not in STAGE_FN:
            print("FAIL stage must be one of %s (S0 preflight.py, S2 identify.py; S1/S3/S4 are the skill's)"
                  % ", ".join(STAGE_FN))
            return 1
        return run_stage(Ctx(a), a.sid)
    parser().print_help()
    return 2


def self_test() -> int:
    """Tier 1 in one process: tests/test_pipeline.py is the full version (golden tree, idempotence, refusals)."""
    print("install: the pipeline self-test lives in tests/test_pipeline.py (it needs PA3 and the kit); "
          "running the stage-free checks here")
    ok = insert_in_section("# A\n## Docs map\n- x\n\n## Next\n", "## Docs map", "- y") == "# A\n## Docs map\n- x\n- y\n\n## Next\n"
    ok &= insert_in_section("# A\n", "## Docs map", "- y") == "# A\n- y\n"
    lines, v = psyq_record({"psyq": {"version": "4.7"}})
    ok &= v == "4.7" and 'ships_compiler = "no"' in lines and 'status = "lead — never the pin"' in lines
    ok &= psyq_record({"psyq": {"version": None, "note": "x"}})[1] == "unstamped" and psyq_record(None)[0] == []
    ok &= all(len(scope_line({"GAME_TITLE": "T" * n, "GAME_SERIAL": "SLUS-01395"}, "4.7")) <= 300 for n in (10, 250))
    ok &= "compiler-pin.md" in scope_line({"GAME_TITLE": "T" * 250}, "unstamped") and "unpinned until" not in \
        scope_line({"GAME_TITLE": "T"}, "4.7", "2026-10-01")
    ok &= pa3_block_first("# fw\n/.run/*\n!/.run/README.md\n\n# Project Architect 3.0\n/.run/*\n__pycache__/\n") == \
        "# Project Architect 3.0\n/.run/*\n__pycache__/\n\n# fw\n/.run/*\n!/.run/README.md\n"
    pa = '{\n  "pa_version": "3.14.2",\n  "project": "x"\n}\n'
    asked = with_upgrade_ask(pa)
    ok &= json.loads(asked)["upgrade"] == "ask" and with_upgrade_ask(asked) == asked
    ok &= asked.count("\n") == pa.count("\n") + 1
    ok &= json.loads(with_upgrade_ask(pa.replace('"x"', '"x", "upgrade": "auto"')))["upgrade"] == "ask"
    ok &= "--resume" in RESTART and "--agent plain" in RESTART
    readme = "# G\n\nLead.\n\n## How this project is made\n\n%s\n\nThe standard.\n" % common.OLD_DISCLOSURE
    swapped = common.with_ai_policy(readme, replace=common.OLD_DISCLOSURE)
    ok &= common.OLD_DISCLOSURE not in swapped and swapped.count(common.AI_POLICY_MARK) == 1
    ok &= "made\n\nThe standard." in swapped and common.with_ai_policy(swapped, common.OLD_DISCLOSURE) == swapped
    own = readme.replace(common.OLD_DISCLOSURE, "We disclose AI use per pull request.")
    ok &= "We disclose AI use" in common.with_ai_policy(own, replace="We disclose AI use per pull request.")
    with tempfile.TemporaryDirectory() as td:
        st = common.State(td)
        st.mark("S0", "done")
        ok &= st.first_open() == "S1"
    return common.self_test_banner("install", ok)


if __name__ == "__main__":
    sys.exit(main())
