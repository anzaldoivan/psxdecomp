#!/usr/bin/env python3
"""doctor.py — is this game repository healthy against the current psxdecomp pins? Read-only.

    doctor.py [--repo DIR] [--json] [--only ROW[,ROW]] [--offline]
                                           one row per check: OK / WARN / FAIL; exit 1 on any FAIL
    doctor.py --self-test

Checks: the bootstrap record (config/psxdecomp.toml); PA3's version against compat.toml; pa3-drift (WARN only: the
machine's PA3 against the pin, and pa.json `"upgrade": "ask"`); the kit's install record; the README's AI policy block
(FAIL when missing; WARN when the old disclosure paragraph is still there); the interpreter pa.json names exists on
this machine; the firewall (ignore block, audit passes on the tree, the
planted-fixture hash present); the reference library (lint, pins, index current); refs/ ignored; the SDK (the
PsyQ release the game links, from the record's [psyq], and $PSXDECOMP_BYO_PSYQ_PATH: never inside the repository);
hygiene (WARN only: unscoped version or game claims and sentences copied between the tracked docs); progress (WARN
only, when a workflow builds a decomp.dev report: its safety lint, and whether decomp.dev lists the repo); github (WARN
only, through `gh api`, skipped offline or logged out: the repository's security settings, each with the `gh api`
command that fixes it; doctor never applies one). `--only github` runs just that row, e.g. on psxdecomp itself.
"""
from __future__ import annotations

import argparse
import contextlib
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

NETWORK_ROWS = ("progress", "github")


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
    if not only or "github" in only:
        for st, detail in github_rows(github_slug(repo), None if offline else gh_api):
            add("github", st, detail)
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
    add("readme", *readme_row(common.read(readme) if readme.is_file() else None))
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


def readme_row(text: str | None) -> tuple[str, str]:
    """The AI policy block (common.AI_POLICY_MARK) is in the README; the old disclosure paragraph is gone."""
    if text is None:
        return "WARN", "no README.md (the kit writes it at S8)"
    if common.AI_POLICY_MARK not in text:
        return "FAIL", "README.md lacks the AI policy block — fix: `/psxdecomp:new --resume` re-runs S8, or paste " \
                       "common.ai_policy_block() under the lead"
    if common.OLD_DISCLOSURE in text:
        return "WARN", "README.md still carries the old disclosure paragraph (%r…): delete it, the AI policy block " \
                       "replaces it" % common.OLD_DISCLOSURE[:40]
    return "OK", "README.md carries the AI policy block"


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
# (container.credentials) runs only for this repository's own branches and never uploads build output.
REPORT_HINT = re.compile(r"_report\b|objdiff-cli\s+report|report\.json")
FORK_GATE = re.compile(r"github\.event\.pull_request\.head\.repo\.full_name\s*==\s*github\.repository")
SHA256 = re.compile(r"\b[0-9a-f]{64}\b")


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


def lint_workflows(texts: dict[str, str]) -> list[str]:
    """Safety findings over the workflows that build a decomp.dev report (empty when none does)."""
    found = []
    reporting = {n: t for n, t in texts.items() if REPORT_HINT.search(t)}
    for name, text in sorted(reporting.items()):
        if re.search(r"^\s*pull_request_target\s*:|\bpull_request_target\b", text, re.M):
            found.append("%s: pull_request_target runs fork code with secrets: use pull_request" % name)
        if re.search(r"write-all|:\s*write\b", text):
            found.append("%s: a write permission: the report needs `permissions: contents: read`" % name)
        elif not re.search(r"^permissions:", text, re.M):
            found.append("%s: no top-level `permissions:` (set `contents: read`)" % name)
        prs = re.search(r"^\s*pull_request\s*:|^on:.*\bpull_request\b|^\s*-\s*pull_request\s*$", text, re.M)
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
                if prs and not FORK_GATE.search(body):
                    found.append("%s/%s: the ROM image job runs on fork PRs: gate it with `if: "
                                 "github.event.pull_request.head.repo.full_name == github.repository`" % (name, job))
            elif re.search(r"secrets\.(?!GITHUB_TOKEN\b)\w+", body):
                found.append("%s/%s: a ROM-free job reads a secret (it needs none)" % (name, job))
        if "objdiff-cli" in text and not (re.search(r"objdiff[^\n]*v?\d+\.\d+\.\d+|OBJDIFF[\w]*:\s*['\"]?v?\d+\.\d+",
                                                    text) and SHA256.search(text)):
            found.append("%s: objdiff-cli is not pinned by version and sha256" % name)
    return found


def github_slug(repo: pathlib.Path) -> str | None:
    r = common.git(repo, "remote", "get-url", "origin", check=False)
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return "%s/%s" % (m[1], m[2]) if m else None


def progress_row(repo: pathlib.Path, fetch) -> tuple[str, str] | None:
    """None without a report workflow; else WARN on any lint finding or when decomp.dev does not list the repo."""
    wf = repo / ".github" / "workflows"
    texts = {p.name: common.read(p) for p in sorted(wf.glob("*.y*ml"))} if wf.is_dir() else {}
    if not any(REPORT_HINT.search(t) for t in texts.values()):
        return None
    found = lint_workflows(texts)
    slug = github_slug(repo)
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


def github_rows(slug: str | None, api) -> list[tuple[str, str]]:
    """[(status, detail)]: one OK row, or one WARN per setting with the exact `gh api` fix; [] when skipped."""
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
    if (get("actions/permissions/fork-pr-contributor-approval") or {}).get("approval_policy") in (None, "none"):
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
    print("  readme: %s" % "; ".join(r[0] for r in rm))
    ok &= [r[0] for r in rm] == ["WARN", "FAIL", "OK", "WARN"]
    ok &= self_test_progress()
    ok &= self_test_github()
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
    return ok


def _dc2_like(sha_pinning: bool):
    """Canned gh api responses shaped like DC2's real ones (read 2026-10-02)."""
    R = "repos/example/game"
    d = {R: {"default_branch": "main", "security_and_analysis": {
            "secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"}}},
         R + "/private-vulnerability-reporting": {"enabled": True},
         R + "/actions/permissions": {"enabled": True, "allowed_actions": "all", "sha_pinning_required": sha_pinning},
         R + "/actions/permissions/workflow": {"default_workflow_permissions": "read",
                                               "can_approve_pull_request_reviews": False},
         R + "/actions/permissions/fork-pr-contributor-approval": {"approval_policy": "first_time_contributors"},
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
    print("  github (DC2-shaped, sha pinning off): %s" % "; ".join("%s %s" % (s, d[:60]) for s, d in warn))
    return (len(warn) == 1 and warn[0][0] == "WARN" and "sha_pinning_required=true" in warn[0][1]
            and "gh api -X PUT repos/example/game/actions/permissions" in warn[0][1]
            and [s for s, _ in clean] == ["OK"] and skipped[0][0] == "OK" and "skipped" in skipped[0][1]
            and github_rows(None, down) == [] and github_rows("example/game", None)[0][1].startswith("offline"))


if __name__ == "__main__":
    sys.exit(main())
