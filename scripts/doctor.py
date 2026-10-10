#!/usr/bin/env python3
"""doctor.py — is this game repository healthy against the current psxdecomp pins? Read-only.

    doctor.py [--repo DIR] [--json] [--only ROW[,ROW]] [--offline]
                                           one row per check: OK / WARN / FAIL; exit 1 on any FAIL
    doctor.py --self-test

Checks: the bootstrap record (config/psxdecomp.toml); PA3's version against compat.toml; pa3-drift (WARN only: the
machine's PA3 against the pin, and pa.json `"upgrade": "ask"`); the kit's install record; the README (FAIL without the
AI policy block; a README on the standard, docs/PUBLISHING.md, is linted and FAILs on a lint failure; an older one
WARNs); publish-tool (WARN only: tools/psxd_publish.py and its workflow are the plugin's); categories (when
config/categories.tsv exists: its rules, and no published id gone); split-guard (split mode only: origin is not the
public repository, the pre-push hook is in place, every workflow action is pinned to a full commit SHA); the
interpreter pa.json names exists on this machine; the firewall (ignore block, audit passes on the tree, the
planted-fixture hash present); the reference library (lint, pins, index current); refs/ ignored; the SDK (the
PsyQ release the game links, from the record's [psyq], and $PSXDECOMP_BYO_PSYQ_PATH: never inside the repository);
hygiene (WARN only: unscoped version or game claims and sentences copied between the tracked docs); progress (WARN only,
when a workflow builds a decomp.dev report: its safety lint, and whether decomp.dev lists the repo, in split mode the
public [public].repo); github (WARN only, through `gh api`, skipped offline or logged out: the repository's security
settings, each with the `gh api` command that fixes it; doctor never applies one). `--only github` runs just that row,
e.g. on psxdecomp itself. In split mode, github checks only that origin (the -dev) is private (FAIL otherwise), and two
rows join it through `gh api`: private-repo ([public].private_repo against its rules, FAIL on any drift) and
public-standard (WARN only: the public repository against the standard, the comparison `settings` prints).
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import decompdev  # noqa: E402
import fetch_refs  # noqa: E402
import publish  # noqa: E402

NETWORK_ROWS = ("progress", "github", "private-repo", "public-standard")
SPLIT_ROWS = ("private-repo", "public-standard")


def check(repo, only=None, offline=False) -> list[tuple[str, str, str]]:
    repo = pathlib.Path(repo).resolve()
    rows = []
    add = lambda n, s, d: rows.append((n, s, d))  # noqa: E731
    if not only or not set(only) <= set(NETWORK_ROWS):
        base_rows(repo, add)
    if not only or "progress" in only:
        prog = progress_row(repo, None if offline else decompdev.projects)
        if prog:
            add("progress", *prog)
    try:
        cfg = publish.load_public(repo)
    except publish.Fail:
        cfg = None                                                      # split-guard reports the malformed table
    if not only or "github" in only:
        if cfg:
            add("github", *dev_row(github_slug(repo), None if offline else gh_api, cfg))
        else:
            wf = repo / ".github" / "workflows"
            texts = {p.name: common.read(p) for p in sorted(wf.glob("*.y*ml"))} if wf.is_dir() else {}
            for st, detail in github_rows(github_slug(repo), None if offline else gh_api, texts):
                add("github", st, detail)
    if cfg and (not only or set(only) & set(SPLIT_ROWS)):
        api = None if offline else publish.gh_api
        priv = private_repo_row(cfg, api)
        if priv:
            add("private-repo", *priv)
        add("public-standard", *public_standard_row(cfg, api))
    return [r for r in rows if not only or r[0] in only]


def base_rows(repo: pathlib.Path, add):
    comp = common.compat()
    rec = repo / "config" / "psxdecomp.toml"
    if rec.is_file():
        r = common.load_toml(rec)
        add("record", "OK", "psxdecomp %s, profile %s, bootstrapped %s" % (
            r["psxdecomp"]["version"], r["psxdecomp"]["profile"], r["psxdecomp"]["bootstrapped"]))
        sdk = sdk_row(r.get("psyq"), repo, os.environ.get("PSXDECOMP_BYO_PSYQ_PATH"))
        if sdk:
            add("sdk", *sdk)
    else:
        add("record", "WARN", "no config/psxdecomp.toml (not bootstrapped by psxdecomp; /psxdecomp:upgrade adopts it)")
    pa = repo / ".claude" / "pa.json"
    if pa.is_file():
        conf = json.loads(common.read(pa))
        ver = conf.get("pa_version")
        add("pa3", "OK" if ver == comp["pa3"]["version"] else "WARN",
            "PA3 %s%s" % (ver, "" if ver == comp["pa3"]["version"] else " (tested %s)" % comp["pa3"]["version"]))
        add("pa3-drift", *pa3_drift_row(conf, machine_pa3_version(), comp["pa3"]["version"]))
        py = conf.get("python")
        add("python", "OK" if py and os.path.exists(py) else "FAIL",
            "%s %s" % (py, "exists" if py and os.path.exists(py) else "is missing on this machine (re-run PA3's "
                       "--project install here to re-resolve it)"))
    else:
        add("pa3", "FAIL", "no .claude/pa.json (not a PA3 project)")
    kit_rec = repo / "docs" / "decomp-architect-install.md"
    if kit_rec.is_file():
        head = common.read(kit_rec)[:400]
        add("kit", "OK", "install record present%s" % (
            "" if "ProjectArchitect %s" % comp["pa3"]["version"] in head else " (written against another PA3)"))
    else:
        add("kit", "FAIL", "no docs/decomp-architect-install.md (the kit is not installed)")
    readme = repo / "README.md"
    add("readme", *readme_row(common.read(readme) if readme.is_file() else None, repo))
    add("publish-tool", *publish_tool_row(repo))
    guard = split_guard_row(repo)
    if guard:
        add("split-guard", *guard)
    cats = categories_row(repo)
    if cats:
        add("categories", *cats)
    gi = repo / ".gitignore"
    gtext = common.read(gi) if gi.is_file() else ""
    add("ignore", "OK" if "# ROM firewall — in force from the FIRST commit" in gtext else "FAIL",
        "the kit's firewall block %s" % ("present" if "ROM firewall" in gtext else "missing from .gitignore"))
    audit = repo / "tools" / "audit_public.py"
    if audit.is_file():
        py = common.find_python((3, 11)) or sys.executable
        r = common.run([py, audit], cwd=repo, check=False, timeout=600)
        add("audit", "OK" if r.returncode == 0 else "FAIL",
            "tools/audit_public.py rc %d%s" % (r.returncode, "" if r.returncode == 0 else ": " + r.stdout.strip()[-200:]))
        add("fixture", "OK" if (repo / "config" / "firewall-fixture.sha1").is_file() else "FAIL",
            "planted-fixture hash %s" % ("present" if (repo / "config/firewall-fixture.sha1").is_file() else "missing"))
    else:
        add("audit", "FAIL", "no tools/audit_public.py")
    refs = repo / "config" / "refs.toml"
    if refs.is_file():
        errs = fetch_refs.lint_doc(fetch_refs.load_doc(refs))
        if errs:
            add("refs", "FAIL", "; ".join(errs[:3]))
        else:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = fetch_refs.main(["--repo", str(repo), "--check"])
            drift = [l for l in buf.getvalue().splitlines() if l.startswith(("DRIFT", "MISSING"))]
            add("refs", "OK" if rc == 0 else "WARN", buf.getvalue().strip().splitlines()[-1] +
                ("" if rc == 0 else " — %s (fetch_refs.py --repo . fixes it)" % "; ".join(drift[:3])))
        ignored = common.git(repo, "check-ignore", "-q", "refs/x", check=False).returncode == 0
        add("refs-ignored", "OK" if ignored else "FAIL", "refs/ %s" % ("ignored" if ignored else "is NOT ignored"))
    else:
        add("refs", "WARN", "no config/refs.toml (no reference library)")
    add("hygiene", *hygiene_row(repo))


def machine_pa3_version() -> str | None:
    """The PA3 installed on this machine (<config>/pa3/VERSION `version:` line), or None when it is not installed."""
    conf = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    f = pathlib.Path(conf) / "pa3" / "VERSION"
    if not f.is_file():
        return None
    for line in common.read(f).splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    return None


def pa3_drift_row(conf: dict, machine: str | None, pin: str) -> tuple[str, str]:
    """WARN when the machine's PA3 left the pin (an upstream clone it follows, or an upgrade) or when pa.json lets the
    router upgrade unasked (a missing `upgrade` key is PA3's auto). Never FAIL: the repo still builds."""
    warns = []
    if machine and machine != pin:
        warns.append("this machine runs PA3 %s, psxdecomp pins %s — fix: re-run the pinned installer with `--root "
                     "--no-clone` (`psxd install where` prints its folder)" % (machine, pin))
    if conf.get("upgrade") != "ask":
        warns.append('.claude/pa.json "upgrade" is %s (PA3 auto-upgrades off the pin) — fix: set "upgrade": "ask" '
                     "and commit it" % json.dumps(conf.get("upgrade", "absent")))
    if warns:
        return "WARN", "; ".join(warns)
    return "OK", "PA3 %s on this machine; upgrades ask first" % (machine or "not installed")


def readme_row(text: str | None, repo: pathlib.Path | None = None) -> tuple[str, str]:
    """The AI policy block (common.AI_POLICY_MARK) is in the README (FAIL without it). A README on the standard
    (docs/PUBLISHING.md: it carries the generated progress block) is linted, FAIL on any lint failure; an older one
    WARNs, and /psxdecomp:upgrade plan lists its migration."""
    if text is None:
        return "WARN", "no README.md (the kit writes it at S8)"
    if common.AI_POLICY_MARK not in text:
        return "FAIL", "README.md lacks the AI policy block — fix: `/psxdecomp:new --resume` re-runs S8, or paste " \
                       "common.ai_policy_block() under the lead"
    if publish.marker("progress") not in text:
        if common.OLD_DISCLOSURE in text:
            return "WARN", "README.md still carries the old disclosure paragraph (%r…): delete it, the AI policy " \
                           "block replaces it" % common.OLD_DISCLOSURE[:40]
        return "WARN", "README.md predates the README standard (docs/PUBLISHING.md): `/psxdecomp:upgrade plan` " \
                       "lists the lint findings to migrate it"
    if repo is None:
        return "OK", "README.md is on the README standard (not linted: no repository)"
    st, detail = publish.lint_summary(publish.lint(text, publish.Ctx(repo)))
    return st, "README.md %s%s" % (detail, "" if st == "OK" else " (tools/psxd_publish.py lint README.md)")


def publish_tool_row(repo: pathlib.Path) -> tuple[str, str]:
    """The vendored lint (tools/psxd_publish.py) and its workflow are psxdecomp's current ones. Never FAIL."""
    want = {publish.VENDORED: common.PLUGIN_ROOT / "scripts" / "publish.py",
            publish.WORKFLOW: common.PLUGIN_ROOT / "profiles" / "psx" / "psxdecomp-readme.yml"}
    off = []
    for rel, src in want.items():
        have = repo / rel
        if not have.is_file():
            off.append("%s missing" % rel)
        elif have.read_bytes() != src.read_bytes():
            off.append("%s differs from psxdecomp %s's" % (rel, common.plugin_version()))
    if off:
        return "WARN", "%s — /psxdecomp:upgrade apply writes them" % "; ".join(off)
    return "OK", "%s and %s are psxdecomp %s's" % (publish.VENDORED, publish.WORKFLOW, common.plugin_version())


def split_guard_row(repo: pathlib.Path) -> tuple[str, str] | None:
    """Split mode only: origin is not the public repository, and the pre-push hook is psxdecomp's."""
    try:
        cfg = publish.load_public(repo)
    except publish.Fail as e:
        return "FAIL", str(e)
    if cfg is None:
        return None
    bad = []
    if (github_slug(repo) or "").lower() == cfg["repo"].lower():
        bad.append("origin is the public %s: point it at the private -dev" % cfg["repo"])
    hook = publish.hook_path(repo)
    if publish._read(hook) != publish.PRE_PUSH or not os.access(hook, os.X_OK):
        bad.append("no psxdecomp pre-push hook (python3 %s hook --install)" % publish.VENDORED)
    loose = unpinned_actions(repo)
    if loose:
        bad.append("actions not pinned to a full commit SHA, so the public repository (which requires it) won't "
                   "start these jobs: %s" % ", ".join(loose[:4]))
    if bad:
        return "FAIL", "; ".join(bad)
    return "OK", "origin %s, not the public %s; pre-push hook in place" % (github_slug(repo), cfg["repo"])


def unpinned_actions(repo: pathlib.Path) -> list[str]:
    """`<workflow>: <action@ref>` for each `uses:` of a remote action not pinned to a 40-hex commit SHA."""
    wf = repo / ".github" / "workflows"
    out = []
    for f in sorted(wf.glob("*.y*ml")) if wf.is_dir() else []:
        for u in re.findall(r"^\s*(?:- )?uses:\s*['\"]?([^\s'\"#]+)", common.read(f), re.M):
            if not u.startswith(("./", "docker://")) and not re.search(r"@[0-9a-f]{40}$", u):
                out.append("%s: %s" % (f.name, u))
    return out


def categories_row(repo: pathlib.Path) -> tuple[str, str] | None:
    """config/categories.tsv's rules and its freeze (no committed id gone); None before the first publish."""
    rows, errs = publish.load_categories(repo / publish.CATEGORIES_REL)
    if rows is None:
        return None
    more, n = publish.history_errors(repo, rows)
    errs += more
    if errs:
        return "FAIL", "%d error(s): %s" % (len(errs), "; ".join(errs[:2]))
    return "OK", "%d ids (%d active); none lost over %d commit(s)" % (len(rows), len(publish.active(rows)), n)


# Not the repo's own current text: fetched sources, research, phase records (scoped by their phase), and the harness
# PA3 installs (.claude/, templates/: copies by design, refreshed by PA3, whose duplicates are PA3's to fix).
HYGIENE_SKIP = re.compile(r"^(?:refs/|research/|phase-ends/|\.claude/|templates/)|(?:^|/)\.run/")


def hygiene_row(repo: pathlib.Path) -> tuple[str, str]:
    """Unscoped claims (fetch_refs.lint_scope) and copied sentences (lint_dupes) over the tracked docs. Never FAIL."""
    r = common.git(repo, "ls-files", "-z", "--", "*.md", "*.toml", check=False)
    rels = [p for p in r.stdout.split("\0") if p and not HYGIENE_SKIP.search(p)] if r.returncode == 0 else []
    paths = [repo / p for p in rels if (repo / p).is_file()]
    per: dict[str, int] = {}
    scope = 0
    for p in paths:
        try:
            n = len(fetch_refs.lint_file(p))
        except (OSError, UnicodeDecodeError):
            continue
        scope += n
        if n:
            per[p.relative_to(repo).as_posix()] = per.get(p.relative_to(repo).as_posix(), 0) + n
    dupes = fetch_refs.lint_dupes(paths, repo)
    for _, where in dupes:
        for w in where:
            f = w.rsplit(":", 1)[0]
            per[f] = per.get(f, 0) + 1
    if not scope and not dupes:
        return "OK", "%d tracked docs: no unscoped claim, no copied sentence" % len(paths)
    top = sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return "WARN", "%d unscoped claim(s), %d copied sentence(s) over %d tracked docs; top: %s" % (
        scope, len(dupes), len(paths), ", ".join("%s (%d)" % kv for kv in top))


def sdk_row(psyq: dict | None, repo: pathlib.Path, byo: str | None) -> tuple[str, str] | None:
    """The PsyQ release the game links and what a byo SDK must be; a byo path inside the repo is a firewall FAIL."""
    if not psyq and not byo:
        return None
    v = (psyq or {}).get("version", "unknown")
    if not psyq:
        what = "no [psyq] in the record"
    elif psyq.get("ships_compiler") == "no":
        what = "game links PsyQ %s; it ships no compiler" % v
    else:
        what = "game links PsyQ %s; shipped cc1 %s" % (v, psyq.get("cc1_banner") or "unknown")
    what += "; byo must be %s (docs/ops/refs.md, psyq-sdk row)" % v
    if not byo:
        return "OK", what
    path = pathlib.Path(byo).expanduser().resolve()
    if path == repo or repo in path.parents:
        return "FAIL", what + "; $PSXDECOMP_BYO_PSYQ_PATH is inside the repository (firewall): move it outside"
    if not path.is_dir():
        return "WARN", what + "; $PSXDECOMP_BYO_PSYQ_PATH %s does not exist" % path
    return "OK", what + "; byo path given"


# ---- progress: a decomp.dev report workflow --------------------------------------------------------------------
# decomp.dev reads an objdiff report.json from an artifact named <version>_report. The safety lint is text-level (the
# scripts are stdlib only): a report job needs no ROM and no secret; a byte-match job that pulls a private ROM image
# (container.credentials) never uploads build output, and on fork PRs either runs gated to this repository's own
# branches, or pulls the image with GITHUB_TOKEN, which a fork PR has, under the repository's approval setting for
# external contributors (the github row checks it).
REPORT_HINT = re.compile(r"_report\b|objdiff-cli\s+report|report\.json")
FORK_GATE = re.compile(r"github\.event\.pull_request\.head\.repo\.full_name\s*==\s*github\.repository")
SHA256 = re.compile(r"\b[0-9a-f]{64}\b")
TOKEN_PASSWORD = re.compile(r"password:\s*\$\{\{\s*(secrets\.GITHUB_TOKEN|github\.token)\s*\}\}")
ON_PRS = re.compile(r"^\s*pull_request\s*:|^on:.*\bpull_request\b|^\s*-\s*pull_request\s*$", re.M)


def _blocks(lines: list[str], start: int, indent: int) -> int:
    """The end (exclusive) of the block opened at `start`: the next non-blank line indented <= indent."""
    for j in range(start + 1, len(lines)):
        if lines[j].strip() and not lines[j].lstrip().startswith("#") and \
                len(lines[j]) - len(lines[j].lstrip()) <= indent:
            return j
    return len(lines)


def _jobs(text: str) -> dict[str, str]:
    lines = text.splitlines()
    top = next((i for i, l in enumerate(lines) if re.match(r"^jobs:\s*$", l)), None)
    if top is None:
        return {}
    end = _blocks(lines, top, 0)
    keys = [i for i in range(top + 1, end) if re.match(r"^  [\w-]+:\s*(#.*)?$", lines[i])]
    return {lines[i].strip().rstrip(":").split(":")[0]: "\n".join(lines[i:_blocks(lines, i, 2)]) for i in keys}


def _uploads(job: str) -> list[tuple[str, str]]:
    """(artifact name, path) of each actions/upload-artifact step in a job, from the step's `with:` block."""
    lines, out = job.splitlines(), []
    for i, l in enumerate(lines):
        if "actions/upload-artifact" not in l:
            continue
        a = i
        while a > 0 and not re.match(r"^\s*- ", lines[a]):
            a -= 1
        step = lines[a:_blocks(lines, a, len(lines[a]) - len(lines[a].lstrip()))]
        w = next((j for j, x in enumerate(step) if re.match(r"^\s+with:\s*$", x)), None)
        args = step[w + 1:_blocks(step, w, len(step[w]) - len(step[w].lstrip()))] if w is not None else []
        name, path = "", ""
        for k, x in enumerate(args):
            m = re.match(r"^\s+(name|path):\s*(.*)$", x)
            if not m:
                continue
            v = m[2].strip()
            if v in ("|", ">", "|-", ">-"):
                v = " ".join(y.strip() for y in args[k + 1:_blocks(args, k, len(x) - len(x.lstrip()))] if y.strip())
            if m[1] == "name":
                name = v.strip("'\"")
            else:
                path = v.strip("'\"")
        out.append((name, path))
    return out


# Split mode's public build.yml (profiles/psx/build.yml): `pull_request_target` is its point, so it is held to the
# invariants that make it safe instead of being refused (docs/PUBLISHING.md, Split mode).
SPLIT_KEYS = {"ssh-key": "PRIVATE_DEPLOY_KEY", "token": "PRIVATE_REPO_TOKEN"}    # the deploy key, or a fine-grained PAT
GUARD = re.compile(r"^    if: github\.repository == '[^']+'\s*(#.*)?$", re.M)


def lint_split_build(text: str) -> list[str]:
    """Findings against the invariants of a split-mode public build.yml ([] when it holds every one)."""
    found = []
    on = text.split("\npermissions:", 1)[0].split("\non:", 1)[-1]
    events = re.findall(r"^  ([\w-]+):", on, re.M)
    if events != ["push", "pull_request_target"] or not re.search(r"^    branches: \[main\]$", on, re.M):
        found.append("triggers %s: exactly push (branches: [main]) and pull_request_target" % events)
    perms = re.findall(r"^permissions:\n((?:  .*\n)+)", text, re.M)
    if perms != ["  contents: read\n"] or re.search(r"^ +permissions:", text, re.M):
        found.append("permissions: only a top-level `contents: read`")
    if re.search(r"actions/cache|^\s+cache(-[\w-]+)?:", text, re.M):
        found.append("a cache: no cache of game files or build output, ever")
    for bad in ("always()", "failure()", "cancelled()", "continue-on-error"):
        if bad in text:
            found.append("%s: a failed or cancelled run must never go on" % bad)
    jobs = _jobs(text)
    for job, body in jobs.items():
        ifs = re.findall(r"^    if:.*$", body, re.M)
        if len(ifs) != 1 or not GUARD.match(ifs[0]):
            found.append("%s: the job's only condition is the repository guard (a skipped job passes a required "
                         "check)" % job)
        if not re.search(r"^    environment: .*'fork-review'", body, re.M):
            found.append("%s: fork PRs must wait in the fork-review environment" % job)
    secrets = re.findall(r"^(.*)\bsecrets\.(\w+)", text, re.M)
    m = re.match(r"^\s+([\w-]+): \$\{\{ $", secrets[0][0]) if len(secrets) == 1 else None
    if not m or SPLIT_KEYS.get(m.group(1)) != secrets[0][1]:
        found.append("secrets: only `ssh-key: ${{ secrets.PRIVATE_DEPLOY_KEY }}` (or `token: ${{ secrets.PRIVATE_REPO_TOKEN"
                     " }}`) in the private checkout")
    checkouts = len(re.findall(r"uses: actions/checkout@", text))
    if checkouts != len(re.findall(r"^\s+persist-credentials: false$", text, re.M)):
        found.append("every checkout sets persist-credentials: false")
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if re.match(r"^\s+(- )?run: ", l) or re.match(r"^\s+(- )?run: [|>]", l):
            block = lines[i:_blocks(lines, i, len(l) - len(l.lstrip()))]
            if any("${{" in x for x in block):
                found.append("line %d: an expression inside run: (script injection): pass it through env" % (i + 1))
    for l in re.findall(r"docker run[^\n]*", text):
        if " -d " in l and "--network none" not in l:
            found.append("a PR-code container with network after the game files are staged: --network none")
    if "merge_commit_sha" in text or "refs/pull/$PR/merge" not in text:
        found.append("the code under test: refs/pull/N/merge built from the PR's head, resolved at run time (the "
                     "payload's merge_commit_sha can be empty, and a fallback tests the base instead)")
    up = re.search(r"^      - name: Upload report\n        if: (.*)$", text, re.M)
    if not up or not up[1].startswith("success() && "):
        found.append("the report upload must be gated on success()")
    return found


def lint_workflows(texts: dict[str, str]) -> list[str]:
    """Safety findings over the workflows that build a decomp.dev report (empty when none does)."""
    found = []
    reporting = {n: t for n, t in texts.items() if REPORT_HINT.search(t)}
    for name, text in sorted(reporting.items()):
        if any(k in text for k in SPLIT_KEYS.values()):
            found += ["%s: %s" % (name, f) for f in lint_split_build(text)]
            continue
        if re.search(r"^\s*pull_request_target\s*:|\bpull_request_target\b", text, re.M):
            found.append("%s: pull_request_target runs fork code with secrets: use pull_request" % name)
        if re.search(r"write-all|:\s*write\b", text):
            found.append("%s: a write permission: the report needs `permissions: contents: read`" % name)
        elif not re.search(r"^permissions:", text, re.M):
            found.append("%s: no top-level `permissions:` (set `contents: read`)" % name)
        prs = ON_PRS.search(text)
        for job, body in _jobs(text).items():
            rom = re.search(r"^\s+container:", body, re.M) and re.search(r"^\s+credentials:", body, re.M)
            ups = _uploads(body)
            for art, path in ups:
                if rom and re.search(r"(^|[\s/])build(/|\b)", path):
                    found.append("%s/%s: uploads %s from the ROM job (build output holds game bytes)"
                                 % (name, job, path))
                if art.endswith("_report") or "report" in path:
                    if not re.search(r"_report$", art):
                        found.append("%s/%s: artifact %r: decomp.dev reads <version>_report" % (name, job, art))
                    if not path or any(not x.endswith("report.json") for x in path.split()):
                        found.append("%s/%s: the report artifact uploads %r: upload only report.json"
                                     % (name, job, path))
            if rom:
                if prs and not FORK_GATE.search(body) and not TOKEN_PASSWORD.search(body):
                    found.append("%s/%s: the ROM image job runs on fork PRs with a secret they never get (the job "
                                 "breaks for them): pull the image with GITHUB_TOKEN and `packages: read` (the "
                                 "package grants the repository access), or gate it with `if: "
                                 "github.event.pull_request.head.repo.full_name == github.repository`" % (name, job))
            elif re.search(r"secrets\.(?!GITHUB_TOKEN\b)\w+", body):
                found.append("%s/%s: a ROM-free job reads a secret (it needs none)" % (name, job))
        if "objdiff-cli" in text and not (re.search(r"objdiff[^\n]*v?\d+\.\d+\.\d+|OBJDIFF[\w]*:\s*['\"]?v?\d+\.\d+",
                                                    text) and SHA256.search(text)):
            found.append("%s: objdiff-cli is not pinned by version and sha256" % name)
    return found


def ungated_token_rom(texts: dict[str, str]) -> list[str]:
    """`workflow/job` of each ROM image job that runs on PRs, pulls with GITHUB_TOKEN and has no fork gate."""
    return ["%s/%s" % (name, job) for name, text in sorted(texts.items()) if ON_PRS.search(text)
            for job, body in _jobs(text).items()
            if re.search(r"^\s+container:", body, re.M) and TOKEN_PASSWORD.search(body)
            and not FORK_GATE.search(body)]


def github_slug(repo: pathlib.Path) -> str | None:
    r = common.git(repo, "remote", "get-url", "origin", check=False)
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return "%s/%s" % (m[1], m[2]) if m else None


def progress_row(repo: pathlib.Path, fetch) -> tuple[str, str] | None:
    """None without a report workflow; else WARN on any lint finding or when decomp.dev does not list the repo (in split
    mode the public [public].repo: decomp.dev registers the public repo, never the private `-dev` origin)."""
    wf = repo / ".github" / "workflows"
    texts = {p.name: common.read(p) for p in sorted(wf.glob("*.y*ml"))} if wf.is_dir() else {}
    if not any(REPORT_HINT.search(t) for t in texts.values()):
        return None
    found = lint_workflows(texts)
    slug = publish.readme_slug(repo)
    if not slug:
        listed, note = None, "no GitHub remote: decomp.dev status not checked"
    elif fetch is None:
        listed, note = None, "offline: decomp.dev status not checked"
    else:
        try:
            listed, note = decompdev.status(fetch(), slug)
        except Exception as e:                                          # noqa: BLE001 — a WARN row, never a crash
            listed, note = None, "decomp.dev unreachable (%s)" % str(e)[:80]
    detail = "; ".join(found + [note])
    return ("WARN" if found or listed is False else "OK"), detail


# ---- github: the repository's security settings (read through gh api; doctor never writes) -----------------------
NO_ROM_CHECK = re.compile(r"audit|no[- ]?rom|no game bytes|public-clean|firewall", re.I)


def gh_api(path: str):
    r = common.run(["gh", "api", path], check=False, timeout=30)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:120])
    return json.loads(r.stdout)


def github_rows(slug: str | None, api, texts: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """[(status, detail)]: one OK row, or one WARN per setting with the exact `gh api` fix; [] when skipped.
    `texts` (the repo's workflows) lets the fork-approval check demand the strict policy for an ungated GITHUB_TOKEN job."""
    if not slug:
        return []
    if api is None:
        return [("OK", "offline: %s settings not checked" % slug)]
    try:
        info = api("repos/%s" % slug)
    except Exception as e:                                              # noqa: BLE001 — logged out, no gh, no network
        return [("OK", "skipped: gh api unavailable (%s)" % str(e)[:80])]
    R = "repos/" + slug
    warns = []

    def get(path, default=None):
        try:
            return api("%s/%s" % (R, path))
        except Exception:                                               # noqa: BLE001
            return default
    if not (get("private-vulnerability-reporting") or {}).get("enabled"):
        warns.append("private vulnerability reporting is off — fix: gh api -X PUT "
                     "%s/private-vulnerability-reporting" % R)
    if (get("actions/permissions/workflow") or {}).get("default_workflow_permissions") != "read":
        warns.append("the default GITHUB_TOKEN can write — fix: gh api -X PUT %s/actions/permissions/workflow -f "
                     "default_workflow_permissions=read" % R)
    perms = get("actions/permissions") or {}
    if perms.get("sha_pinning_required") is not True:
        warns.append("actions are not required to be pinned to a full commit SHA — fix: gh api -X PUT "
                     "%s/actions/permissions -F enabled=true -f allowed_actions=%s -F sha_pinning_required=true"
                     % (R, perms.get("allowed_actions") or "all"))
    policy = (get("actions/permissions/fork-pr-contributor-approval") or {}).get("approval_policy")
    tww = ungated_token_rom(texts or {})
    if tww and policy != "all_external_contributors":
        warns.append("%s pull(s) the private image on fork PRs: approval must cover all external contributors — fix: "
                     "gh api -X PUT %s/actions/permissions/fork-pr-contributor-approval "
                     "-f approval_policy=all_external_contributors" % (", ".join(tww), R))
    elif policy in (None, "none"):
        warns.append("fork PRs run workflows without approval — fix: gh api -X PUT "
                     "%s/actions/permissions/fork-pr-contributor-approval "
                     "-f approval_policy=first_time_contributors" % R)
    sa = info.get("security_and_analysis") or {}
    off = [k for k in ("secret_scanning", "secret_scanning_push_protection")
           if (sa.get(k) or {}).get("status") != "enabled"]
    if off:
        warns.append("%s off — fix: gh api -X PATCH %s %s" % (" and ".join(off), R, " ".join(
            "-f 'security_and_analysis[%s][status]=enabled'" % k for k in off)))
    good = False
    for rs in get("rulesets", []) or []:
        full = get("rulesets/%s" % rs.get("id")) or {}
        inc = ((full.get("conditions") or {}).get("ref_name") or {}).get("include") or []
        if full.get("target") != "branch" or full.get("enforcement") != "active" or not (
                "~DEFAULT_BRANCH" in inc or "refs/heads/%s" % info.get("default_branch") in inc or "~ALL" in inc):
            continue
        types = {r.get("type"): r for r in full.get("rules") or []}
        params = (types.get("required_status_checks") or {}).get("parameters") or {}
        checks = params.get("required_status_checks") or []
        if "deletion" in types and "non_fast_forward" in types and any(NO_ROM_CHECK.search(c.get("context", ""))
                                                                       for c in checks):
            good = True
    if not good:
        body = json.dumps({"name": "main", "target": "branch", "enforcement": "active",
                           "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
                           "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                                     {"type": "required_status_checks", "parameters": {
                                         "strict_required_status_checks_policy": True,
                                         "required_status_checks": [{"context": "<your no-rom audit check>"}]}}]},
                          separators=(",", ":"))
        warns.append("no active default-branch ruleset blocks deletion and force-push and requires the no-rom "
                     "check — "
                     "fix: gh api -X POST %s/rulesets --input - <<< '%s'" % (R, body))
    return [("WARN", w) for w in warns] or [("OK", "%s: vulnerability reporting, read-only token, SHA-pinned actions, "
                                                  "fork approval, secret scanning + push protection, ruleset" % slug)]


# ---- split mode: the -private repository and the public standard (publish.gh_api: GETs only, None on a 404) ------

def dev_row(slug: str | None, api, cfg: dict) -> tuple[str, str]:
    """Split mode's github row. Origin is the private -dev: GitHub enforces no ruleset on a Free private repository, so
    github_rows' public hardening doesn't apply there (the pre-push hook guards dev; public-standard checks the public
    repository). FAIL only when -dev is not private: dev's history would be public."""
    if not slug:
        return "OK", "no GitHub origin"
    if api is None:
        return "OK", "offline: %s not checked" % slug
    try:
        info = api("repos/%s" % slug)
    except Exception as e:                                              # noqa: BLE001 — logged out, no gh, no network
        return "OK", "skipped: gh api unavailable (%s)" % str(e)[:80]
    if info.get("private") is not True:
        return "FAIL", ("%s is %s: dev's history is exposed — make it private at once (gh repo edit %s --visibility "
                        "private --accept-visibility-change-consequences), then SECURITY.md's purge path"
                        % (slug, info.get("visibility"), slug))
    return "OK", "%s is private (split mode: the hook guards dev; public-standard checks the public %s)" % (
        slug, cfg["repo"])


def private_repo_row(cfg: dict, api) -> tuple[str, str] | None:
    """[public].private_repo against its rules (profiles/psx/private/README.md): private, no fork, Actions off, the
    owner its only collaborator, deploy keys read-only and at most one, private_rev one of its commits, and forking
    off when GitHub allows it (an organization's repository). FAIL on any drift; None without a private_repo."""
    P = cfg.get("private_repo")
    if not P:
        return None
    if api is None:
        return "OK", "offline: %s not checked" % P
    R = "repos/" + P
    try:
        info = api("GET", R)
    except Exception as e:                                              # noqa: BLE001 — logged out, no gh, no network
        return "OK", "skipped: gh api unavailable (%s)" % str(e)[:80]
    if info is None:
        return "FAIL", "%s not found: create it (docs/PUBLISHING.md, Cutover order, step 2)" % P
    bad, notes = [], []
    try:
        if info.get("private") is not True:
            bad.append("it is %s: make it private at once, rotate the deploy key, and see SECURITY.md's purge path"
                       % info.get("visibility"))
        if info.get("forks_count"):
            bad.append("%d fork(s)" % info["forks_count"])
        if (info.get("owner") or {}).get("type") == "Organization":
            if info.get("allow_forking") is not False:
                bad.append("forking is on — fix: gh api -X PATCH %s -F allow_forking=false" % R)
        else:
            notes.append("forking: fixed on a personal account (only collaborators, the owner included, can fork)")
        if (api("GET", R + "/actions/permissions") or {}).get("enabled") is not False:
            bad.append("Actions are on — fix: gh api -X PUT %s/actions/permissions -F enabled=false" % R)
        owner = P.split("/")[0].lower()
        others = sorted(c.get("login") or "?" for c in api("GET", R + "/collaborators?affiliation=direct") or []
                        if (c.get("login") or "").lower() != owner)
        if others:
            bad.append("collaborators besides the owner: %s" % ", ".join(others))
        keys = api("GET", R + "/keys") or []
        rw = [k.get("title") or str(k.get("id")) for k in keys if k.get("read_only") is not True]
        if rw:
            bad.append("deploy key(s) with write access: %s (delete them; add a read-only one)" % ", ".join(rw))
        if len(keys) > 1:
            bad.append("%d deploy keys: keep the one the public CI holds" % len(keys))
        notes.append("%d read-only deploy key" % len(keys) if keys else
                     "no deploy key (right only with a PRIVATE_REPO_TOKEN in its place)")
        rev = cfg.get("private_rev")
        if rev:
            try:
                found = api("GET", "%s/commits/%s" % (R, rev)) is not None
            except publish.Fail:                                        # 422: no commit for that sha
                found = False
            if not found:
                bad.append("private_rev %s is not a commit of %s" % (rev[:10], P))
            else:
                notes.append("private_rev %s present" % rev[:10])
    except Exception as e:                                              # noqa: BLE001 — a partial read is no verdict
        return "WARN", "%s: could not read every setting (%s)" % (P, str(e)[:80])
    if bad:
        return "FAIL", "%s: %s" % (P, "; ".join(bad))
    return "OK", "%s: private, no fork, Actions off, the owner alone; %s" % (P, "; ".join(notes))


def public_standard_row(cfg: dict, api) -> tuple[str, str]:
    """The public repository against the standard, read-only (publish.settings_drift, the comparison `settings`
    prints). WARN only: before release 1 every row drifts; cutover step 5 ends with it OK."""
    if api is None:
        return "OK", "offline: %s settings not checked" % cfg["repo"]
    try:
        rows = publish.settings_drift(cfg, api)
    except Exception as e:                                              # noqa: BLE001 — logged out, no gh, no network
        return "OK", "skipped: gh api unavailable (%s)" % str(e)[:80]
    if not rows:
        return "OK", "%s is on the public-repo standard" % cfg["repo"]
    hand = [r["what"] for r in rows if not r["fix"]]
    return "WARN", "%s: %d drift(s): %s — fix: python3 %s settings --apply (the developer's)%s" % (
        cfg["repo"], len(rows), ", ".join(r["what"] for r in rows[:6]) + (", …" if len(rows) > 6 else ""),
        publish.VENDORED, "; by hand: %s" % ", ".join(hand) if hand else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", help="comma-separated row names (e.g. github, progress)")
    ap.add_argument("--offline", action="store_true", help="no network: the progress and github rows say skipped")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    rows = check(a.repo, only=a.only.split(",") if a.only else None, offline=a.offline)
    if a.json:
        print(json.dumps([dict(zip(("check", "status", "detail"), r)) for r in rows], indent=2))
    else:
        for r in rows:
            print("DOCTOR %-12s %-4s %s" % r)
    fails = sum(r[1] == "FAIL" for r in rows)
    print("DOCTOR %s (%d warn)" % ("OK" if not fails else "FAIL %d" % fails, sum(r[1] == "WARN" for r in rows)))
    return 1 if fails else 0


def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        common.git(td, "init", "--quiet")
        rows = dict((r[0], r[1]) for r in check(td))
    ok = rows.get("pa3") == "FAIL" and rows.get("record") == "WARN" and rows.get("audit") == "FAIL"
    ok &= rows.get("readme") == "WARN"
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td).resolve()
        q = {"version": "4.7", "ships_compiler": "no"}
        (repo / "tools" / "psyq").mkdir(parents=True)
        cases = [(sdk_row(q, repo, str(repo / "tools" / "psyq")), "FAIL"), (sdk_row(q, repo, td + "/../nope"), "WARN"),
                 (sdk_row(q, repo, None), "OK"), (sdk_row(None, repo, None), None)]
        for got, want in cases:
            ok &= (got[0] if got else None) == want
        print("  sdk row: %s" % cases[0][0][1])
    with tempfile.TemporaryDirectory() as td:                           # hygiene: clean tree OK, one planted line WARN
        repo = pathlib.Path(td).resolve()
        common.git(repo, "init", "--quiet")
        (repo / "docs").mkdir()
        (repo / "docs" / "a.md").write_text("# Toolchain (scope: 2026-10-01)\n\nThe pin is gcc 2.95.2.\n")
        (repo / "refs").mkdir()
        (repo / "refs" / "x.md").write_text("BFM used gcc 2.7.2.\n")      # refs/ is not the repo's own text
        common.git(repo, "add", "-A", "-f")
        clean = hygiene_row(repo)
        (repo / "PROJECT_CONTEXT.md").write_text("Try gcc 2.6.3 + aspsx 2.63 first.\n")
        common.git(repo, "add", "-A")
        planted = hygiene_row(repo)
        print("  hygiene: clean %s; planted %s" % (clean[0], planted[1]))
        ok &= clean[0] == "OK" and planted[0] == "WARN" and "PROJECT_CONTEXT.md (1)" in planted[1]
    pin = "3.14.2"
    drift = [pa3_drift_row({"upgrade": "ask"}, pin, pin), pa3_drift_row({"upgrade": "ask"}, None, pin),
             pa3_drift_row({}, pin, pin), pa3_drift_row({"upgrade": "ask"}, "3.15.2", pin)]
    print("  pa3-drift: %s" % "; ".join(d[0] for d in drift))
    ok &= [d[0] for d in drift] == ["OK", "OK", "WARN", "WARN"] and "--no-clone" in drift[3][1]
    good = "# G\n\nLead.\n\n%s\n## A\n" % common.ai_policy_block()
    rm = [readme_row(None), readme_row("# G\n\nLead.\n"), readme_row(good),
          readme_row(good + "\n%s; a person reviews each phase gate.\n" % common.OLD_DISCLOSURE)]
    with tempfile.TemporaryDirectory() as td:                           # a README on the standard is linted
        repo = publish._self_repo(td)
        std = publish.render(publish.SELF_README, publish.Ctx(repo))
        rm += [readme_row(std, repo), readme_row(std.replace("## Progress", "## Status"), repo)]
        tool = publish_tool_row(repo)
        guard = [split_guard_row(repo)]
        (repo / publish.CONFIG_REL).write_text('[public]\nrepo = "example/synthetic-decomp"\n')
        guard.append(split_guard_row(repo))
        common.git(repo, "remote", "set-url", "origin", "https://github.com/example/synthetic-decomp-dev.git")
        with contextlib.redirect_stdout(io.StringIO()):
            publish.cmd_hook(str(repo), install=True)
        guard.append(split_guard_row(repo))
        print("  split-guard: %s" % "; ".join("%s %s" % (g[0], g[1]) if g else "none" for g in guard))
        ok &= guard[0] is None and guard[1][0] == "FAIL" and "origin is the public" in guard[1][1] and "hook" in guard[1][1]
        ok &= guard[2][0] == "OK"
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / "no-rom.yml").write_text("jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
                                       "      - uses: ./local\n      - uses: actions/setup-python@%s # v5\n" % ("a" * 40))
        loose = split_guard_row(repo)
        print("  split-guard, an unpinned action: %s %s" % (loose[0], loose[1][-60:]))
        ok &= loose[0] == "FAIL" and "no-rom.yml: actions/checkout@v4" in loose[1] and "setup-python" not in loose[1]
        (wf / "no-rom.yml").unlink()
        (repo / publish.CONFIG_REL).unlink()
        cats = categories_row(repo)
        (repo / publish.CATEGORIES_REL).write_text(publish.SELF_TSV.replace("ovl.stage1\tovl\tStage 1\tactive\n", ""))
        cats_gone = categories_row(repo)
    print("  readme: %s; publish-tool %s; categories %s, an id removed %s" % (
        "; ".join(r[0] for r in rm), tool[0], cats[0], cats_gone[0]))
    ok &= [r[0] for r in rm] == ["WARN", "FAIL", "WARN", "WARN", "OK", "FAIL"] and "predates" in rm[2][1]
    ok &= tool[0] == "WARN" and cats[0] == "OK" and cats_gone[0] == "FAIL" and "'ovl.stage1'" in cats_gone[1]
    ok &= self_test_progress()
    ok &= self_test_github()
    ok &= self_test_split()
    return common.self_test_banner("doctor", ok)


GOOD_WORKFLOW = """name: progress
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
      - name: objdiff-cli
        env:
          OBJDIFF_VERSION: v3.0.0
          OBJDIFF_SHA256: %s
          OBJDIFF_URL: https://github.com/encounter/objdiff/releases/download
        run: |
          curl -sL -o objdiff-cli "$OBJDIFF_URL/$OBJDIFF_VERSION/objdiff-cli-linux-x86_64"
          echo "$OBJDIFF_SHA256  objdiff-cli" | sha256sum -c
      - run: ./objdiff-cli report generate -o report.json
      - uses: actions/upload-artifact@0000000000000000000000000000000000000000
        with:
          name: us_report
          path: report.json
  match:
    if: github.event_name == 'push' || github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    container:
      image: ghcr.io/example/game-rom:1
      credentials:
        username: ${{ github.actor }}
        password: ${{ secrets.ROM_IMAGE_TOKEN }}
    steps:
      - run: make check
""" % ("ab" * 32)


def self_test_progress() -> bool:
    good = GOOD_WORKFLOW
    upload_build = good + """      - uses: actions/upload-artifact@0000000000000000000000000000000000000000
        with:
          name: build
          path: build/
"""
    planted = {
        "good": (good, []),
        "pull_request_target": (good.replace("  pull_request:\n", "  pull_request_target:\n"), ["pull_request_target"]),
        "uploads build/": (upload_build, ["uploads build/"]),
        "ungated ROM image": (good.replace("    if: github.event_name == 'push' || github.event.pull_request.head.repo"
                                           ".full_name == github.repository\n", ""), ["runs on fork PRs"]),
        "ungated GITHUB_TOKEN ROM job": (good.replace("secrets.ROM_IMAGE_TOKEN", "secrets.GITHUB_TOKEN")
                                               .replace("    if: github.event_name == 'push' || github.event."
                                                        "pull_request.head.repo.full_name == github.repository\n", ""),
                                               []),
        "ungated PAT ROM job": (good.replace("    if: github.event_name == 'push' || github.event.pull_request.head.repo"
                                             ".full_name == github.repository\n", ""), ["a secret they never get"]),
        "secret in report job": (good.replace("      - run: ./objdiff-cli", "      - run: echo ${{ secrets.X }}\n"
                                              "      - run: ./objdiff-cli"), ["reads a secret"]),
        "artifact name": (good.replace("name: us_report", "name: progress"), ["decomp.dev reads <version>_report"]),
        "unpinned objdiff": (good.replace("ab" * 32, "TODO"), ["not pinned"]),
    }
    ok = True
    for name, (text, want) in planted.items():
        got = lint_workflows({"progress.yml": text})
        hit = all(any(w in f for f in got) for w in want) and (want or not got)
        print("  progress %-22s %s%s" % (name, "OK" if not got else "WARN: " + got[0][:70],
                                         "" if hit else "  <- WRONG"))
        ok &= bool(hit)
    with tempfile.TemporaryDirectory() as td:                         # the row: lint + the canned decomp.dev listing
        repo = pathlib.Path(td).resolve()
        common.git(repo, "init", "--quiet")
        common.git(repo, "remote", "add", "origin", "https://github.com/example/game-a-decomp.git")
        ok &= progress_row(repo, lambda: []) is None                  # no report workflow: no row
        (repo / ".github" / "workflows").mkdir(parents=True)
        (repo / ".github" / "workflows" / "progress.yml").write_text(good)
        listed = [{"owner": "example", "repo": "game-a-decomp", "commit": {"sha": "1234567abc"}, "measures": {}}]
        a, b = progress_row(repo, lambda: listed), progress_row(repo, lambda: [])
        c = progress_row(repo, None)
        print("  progress row: listed %s; unlisted %s; offline %s" % (a[0], b[0], c[0]))
        ok &= a[0] == "OK" and "commit 1234567" in a[1] and b[0] == "WARN" and "/manage/new" in b[1] and c[0] == "OK"
        common.git(repo, "remote", "set-url", "origin", "https://github.com/example/game-a-decomp-dev.git")
        d = progress_row(repo, lambda: listed)                         # split mode, [public] off: the -dev origin
        (repo / publish.CONFIG_REL).parent.mkdir(parents=True, exist_ok=True)
        (repo / publish.CONFIG_REL).write_text('[public]\nrepo = "example/game-a-decomp"\n')
        e = progress_row(repo, lambda: listed)                         # split mode on: the public repo is looked up
        print("  progress row: -dev origin %s; split mode %s" % (d[0], e[0]))
        ok &= d[0] == "WARN" and e[0] == "OK" and "commit 1234567" in e[1]
    return ok


def build_template() -> str:
    """profiles/psx/build.yml with sample values in its {{...}} placeholders."""
    vals = dict(REPO="example/game", EXES='"SLUS_000.00"', FETCH_COMMAND="make toolchain",
                BUILD_COMMAND="make split build", REPORT_COMMAND="python3 tools/progress_units.py > report.json")
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: vals[m[1]],
                  common.read(common.PLUGIN_ROOT / "profiles" / "psx" / "build.yml"))


def _dc2_like(sha_pinning: bool, policy: str = "first_time_contributors"):
    """Canned gh api responses shaped like DC2's real ones (read 2026-10-02)."""
    R = "repos/example/game"
    d = {R: {"default_branch": "main", "security_and_analysis": {
            "secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"}}},
         R + "/private-vulnerability-reporting": {"enabled": True},
         R + "/actions/permissions": {"enabled": True, "allowed_actions": "all", "sha_pinning_required": sha_pinning},
         R + "/actions/permissions/workflow": {"default_workflow_permissions": "read",
                                               "can_approve_pull_request_reviews": False},
         R + "/actions/permissions/fork-pr-contributor-approval": {"approval_policy": policy},
         R + "/rulesets": [{"id": 1, "name": "main", "target": "branch"}, {"id": 2, "name": "tags", "target": "tag"}],
         R + "/rulesets/1": {"id": 1, "target": "branch", "enforcement": "active",
                             "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
                             "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                                       {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
                                       {"type": "required_status_checks", "parameters": {"required_status_checks": [
                                           {"context": "public-clean audit (no game bytes)"}]}}]},
         R + "/rulesets/2": {"id": 2, "target": "tag", "enforcement": "active", "rules": []}}

    def api(path):
        if path not in d:
            raise RuntimeError("404 %s" % path)
        return d[path]
    return api


def self_test_github() -> bool:
    warn = github_rows("example/game", _dc2_like(False))
    clean = github_rows("example/game", _dc2_like(True))

    def down(path):
        raise RuntimeError("gh: not logged in")
    skipped = github_rows("example/game", down)
    tww = {"build.yml": GOOD_WORKFLOW.replace("secrets.ROM_IMAGE_TOKEN", "secrets.GITHUB_TOKEN").replace(
        "    if: github.event_name == 'push' || github.event.pull_request.head.repo.full_name == github.repository\n",
        "")}
    ok = ungated_token_rom(tww) == ["build.yml/match"] and ungated_token_rom({"p.yml": GOOD_WORKFLOW}) == []
    loose = github_rows("example/game", _dc2_like(True), tww)                   # first_time_contributors: too weak
    strict = github_rows("example/game", _dc2_like(True, "all_external_contributors"), tww)
    ok &= (len(loose) == 1 and loose[0][0] == "WARN" and "approval_policy=all_external_contributors" in loose[0][1]
           and "build.yml/match" in loose[0][1] and [s for s, _ in strict] == ["OK"])
    ok &= not lint_workflows({"build.yml": build_template()})               # the public CI template lints clean
    print("  github (DC2-shaped, sha pinning off): %s" % "; ".join("%s %s" % (s, d[:60]) for s, d in warn))
    return ok and (len(warn) == 1 and warn[0][0] == "WARN" and "sha_pinning_required=true" in warn[0][1]
            and "gh api -X PUT repos/example/game/actions/permissions" in warn[0][1]
            and [s for s, _ in clean] == ["OK"] and skipped[0][0] == "OK" and "skipped" in skipped[0][1]
            and github_rows(None, down) == [] and github_rows("example/game", None)[0][1].startswith("offline"))


REV = "ab" * 20


def _private_store(org: bool = False) -> dict:
    """Canned gh api responses shaped like dc2-private's real ones (read 2026-10-10): a personal repository."""
    R = "repos/example/game-private"
    return {R: {"private": True, "visibility": "private", "forks_count": 0, "allow_forking": True,
                "owner": {"login": "example", "type": "Organization" if org else "User"}},
            R + "/actions/permissions": {"enabled": False},
            R + "/collaborators?affiliation=direct": [{"login": "example"}],
            R + "/keys": [{"id": 1, "title": "public CI (read-only)", "read_only": True}],
            R + "/commits/" + REV: {"sha": REV}}


def _store_api(store: dict):
    def api(method, path, body=None):
        assert method == "GET", (method, path)                          # doctor never writes
        if "/commits/" in path and path not in store:
            raise publish.Fail("gh api GET %s: No commit found for SHA (HTTP 422)" % path)
        return copy.deepcopy(store.get(path))
    return api


def self_test_split() -> bool:
    cfg = {"repo": "example/game", "checks": ["build SLUS_000.00"], "private_repo": "example/game-private",
           "private_rev": REV}
    good = private_repo_row(cfg, _store_api(_private_store()))
    R = "repos/example/game-private"
    drifts = {"public": (R, "private", False), "forked": (R, "forks_count", 1),
              "actions": (R + "/actions/permissions", "enabled", True)}
    got = {}
    for name, (path, k, v) in drifts.items():
        s = _private_store()
        s[path][k] = v
        got[name] = private_repo_row(cfg, _store_api(s))
    s = _private_store()
    s[R + "/keys"] = [{"id": 1, "title": "rw", "read_only": False}, {"id": 2, "title": "ro", "read_only": True}]
    got["keys"] = private_repo_row(cfg, _store_api(s))
    s = _private_store()
    s[R + "/collaborators?affiliation=direct"].append({"login": "mallory"})
    got["collab"] = private_repo_row(cfg, _store_api(s))
    got["rev"] = private_repo_row(dict(cfg, private_rev="cd" * 20), _store_api(_private_store()))
    got["org-fork"] = private_repo_row(cfg, _store_api(_private_store(org=True)))
    s = _private_store(org=True)
    s[R]["allow_forking"] = False
    org_ok = private_repo_row(cfg, _store_api(s))
    gone = private_repo_row(cfg, _store_api({}))

    def down(method, path, body=None):
        raise publish.Fail("gh: not logged in")
    want = {"public": "make it private", "forked": "1 fork", "actions": "enabled=false", "keys": "write access: rw",
            "collab": "mallory", "rev": "not a commit", "org-fork": "allow_forking=false"}
    ok = good[0] == "OK" and "personal account" in good[1] and "private_rev abababab" in good[1]
    ok &= all(got[n][0] == "FAIL" and w in got[n][1] for n, w in want.items()) and "2 deploy keys" in got["keys"][1]
    ok &= org_ok[0] == "OK" and gone[0] == "FAIL" and "not found" in gone[1]
    ok &= private_repo_row(cfg, down)[1].startswith("skipped") and private_repo_row(cfg, None)[1].startswith("offline")
    ok &= private_repo_row(dict(cfg, private_repo=""), None) is None
    store = publish._fake_store(cfg)                                    # publish's compliant public repository
    std = public_standard_row(cfg, _store_api(store))
    del store["repos/example/game/contents/.github/CODEOWNERS"]
    store["repos/example/game"]["allow_forking"] = False
    drift = public_standard_row(cfg, _store_api(store))
    ok &= std[0] == "OK" and drift[0] == "WARN" and "2 drift(s)" in drift[1] and "settings --apply" in drift[1]
    ok &= "by hand: CODEOWNERS" in drift[1] and public_standard_row(cfg, down)[1].startswith("skipped")
    dev = [dev_row("example/game-dev", lambda p: {"private": True, "visibility": "private"}, cfg),
           dev_row("example/game-dev", lambda p: {"private": False, "visibility": "public"}, cfg),
           dev_row("example/game-dev", None, cfg), dev_row(None, None, cfg)]

    def logged_out(path):
        raise RuntimeError("gh: not logged in")
    dev.append(dev_row("example/game-dev", logged_out, cfg))
    ok &= [d[0] for d in dev] == ["OK", "FAIL", "OK", "OK", "OK"] and "exposed" in dev[1][1]
    ok &= dev[2][1].startswith("offline") and dev[4][1].startswith("skipped")
    with tempfile.TemporaryDirectory() as td:                           # check(): split mode swaps the github row
        repo = publish._self_repo(td)
        (repo / publish.CONFIG_REL).write_text('[public]\nrepo = "example/synthetic-decomp"\n')
        rows = check(repo, only=["github", "private-repo", "public-standard"], offline=True)
    ok &= [(r[0], r[1]) for r in rows] == [("github", "OK"), ("public-standard", "OK")]
    ok &= rows[0][2].startswith("offline: ") and "public-standard" not in rows[0][2]
    print("  github in split mode: %s" % "; ".join("%s %s" % (d[0], d[1][:50]) for d in dev[:2]))
    print("  private-repo: good %s; %s" % (good[0], "; ".join("%s %s" % (n, g[0]) for n, g in got.items())))
    print("  public-standard: compliant %s; drift %s" % (std[0], drift[1][:90]))
    return ok


if __name__ == "__main__":
    sys.exit(main())
