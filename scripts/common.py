"""Shared helpers for the psxdecomp scripts: paths, TOML, the stage state file, pins, the PA3/kit sources.

Standard library only (Python >= 3.12). Every script that writes has --dry-run and --self-test.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import tomllib

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_REL = ".run/bootstrap/state.json"

# The stages of /psxdecomp:new, in order. (id, name, kind): kind "script" runs here, "model" is done by the skill,
# "restart" ends the session (the next one resumes).
STAGES = [
    ("S0", "preflight", "script"),
    ("S1", "interview", "model"),
    ("S2", "identify", "script"),
    ("S3", "investigate", "model"),
    ("S4", "gate", "model"),
    ("S5", "repo", "script"),
    ("S6", "pa3", "script"),
    ("S7", "intake", "model"),
    ("S8", "kit", "script"),
    ("S9", "refs", "script"),
    ("S10", "handoff", "script"),
]
STAGE_IDS = [s[0] for s in STAGES]


class Fail(Exception):
    """A refusal: printed as `FAIL <stage>: <reason>`, exit 1."""


def load_toml(path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def read(path) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def write(path, text: str, dry: bool = False, mode: int | None = None) -> str:
    """Write text; returns 'created' / 'changed' / 'unchanged' (dry runs report what they would do)."""
    p = pathlib.Path(path)
    old = p.read_text(encoding="utf-8") if p.is_file() else None
    status = "created" if old is None else ("unchanged" if old == text else "changed")
    if not dry and status != "unchanged":
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        if mode is not None:
            p.chmod(mode)
    return status


def sha256_file(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


SKIP_NAMES = {"__pycache__", ".DS_Store", ".git"}


def tree_digest(root) -> str:
    """A content digest of a folder (for an upstream that is not a git repository, such as the kit today):
    sha256 over sorted `<relpath>\\0<sha256>\\n` lines, skipping caches and .git."""
    root = pathlib.Path(root)
    lines = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_NAMES for part in rel.parts) or not p.is_file():
            continue
        lines.append("%s\0%s\n" % (rel.as_posix(), sha256_file(p)))
    return "sha256:" + hashlib.sha256("".join(lines).encode()).hexdigest()


# The PA3 names that 3.24 (PA 3.2: one session, the mod runs the plan) and 3.25 (no closing agent, no milestone
# verifier, one agent per role) removed. Text that names one tells an agent to use what is gone. One home: the doctor's
# pa3-retired row, the game test (tier 1), the static test over psxdecomp's delivered texts (tier 0). Tokens only, never plain words: `router`
# stays off the list, since 3.28.8 itself writes `--by router` and commits as `router`. (regex, retired in)
PA3_RETIRED = (
    (r"(?<![\w-])pa-session\b", "3.24"),
    (r"--agent plain\b", "3.24"),
    (r"\bexpert-opus55\b", "3.25"),
    (r"\bcoder-opus55\b", "3.25"),
    (r"\bdiscuss-high\b", "3.24"),
    (r"\bdiscuss-max\b", "3.24"),
    (r"(?<![\w.-])/discuss\b", "3.24"),
    (r"(?<![\w.-])/plangen\b", "3.24"),
    (r"(?<![\w.-])/planphase\b", "3.24"),
    (r"(?<![\w.-])/proceed\b", "3.24"),
    (r"(?<![\w.-])/thoughts\b", "3.24"),
    (r"\bplanner-gen\b", "3.24"),
    (r"\bplanner-phase\b", "3.24"),
    (r"phaseend_index\.py verify\b", "3.25"),
    (r"launch\.py --seed-only\b", "3.24"),
    (r"(?<![\w-])seed\.md\b", "3.24"),
    (r"PA3's closer\b", "3.25"),
)


def retired_hits(root, rels) -> list[tuple[str, int, str]]:
    """[(rel, line number, the retired pattern)] for each line of the text files `rels` under `root` that names a
    PA3_RETIRED token. Binary and unreadable files are skipped."""
    root = pathlib.Path(root)
    rxs = [(re.compile(pat), pat) for pat, _ in PA3_RETIRED]
    hits = []
    for rel in rels:
        try:
            data = (root / rel).read_bytes()
            text = data.decode("utf-8") if b"\0" not in data else None
        except (OSError, UnicodeDecodeError):
            text = None
        for n, line in enumerate((text or "").splitlines(), 1):
            hits += [(rel, n, pat) for rx, pat in rxs if rx.search(line)]
    return hits


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def today() -> str:
    return time.strftime("%Y-%m-%d")


def run(cmd, cwd=None, check=True, env=None, timeout=None) -> subprocess.CompletedProcess:
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if env:
        e.update(env)
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                       env=e, timeout=timeout)
    if check and r.returncode != 0:
        raise Fail("%s -> rc %d: %s" % (" ".join(map(str, cmd)), r.returncode, (r.stdout + r.stderr).strip()[-800:]))
    return r


def git(repo, *args, check=True) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(repo)] + list(args), check=check)


# ---- the state file ---------------------------------------------------------------------------------------------

class State:
    def __init__(self, target):
        self.target = pathlib.Path(target).resolve()
        self.path = self.target / STATE_REL
        self.data = {"version": 1, "stages": {}}
        if self.path.is_file():
            self.data = json.loads(read(self.path))

    def status(self, sid: str) -> str:
        return self.data["stages"].get(sid, {}).get("status", "todo")

    def mark(self, sid: str, status: str, note: str = "", dry: bool = False, **extra):
        if dry:
            return
        row = {"status": status, "at": now_iso(), "note": note}
        row.update(extra)
        self.data["stages"][sid] = row
        self.save()

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def first_open(self) -> str | None:
        for sid in STAGE_IDS:
            if self.status(sid) not in ("done", "skipped"):
                return sid
        return None


def emit(sid: str, name: str, status: str, note: str = ""):
    print("%-4s %-12s %-6s %s" % (sid, name, status, note), flush=True)


# ---- pins -------------------------------------------------------------------------------------------------------

def compat() -> dict:
    return load_toml(PLUGIN_ROOT / "compat.toml")


def plugin_version() -> str:
    return json.loads(read(PLUGIN_ROOT / ".claude-plugin" / "plugin.json"))["version"]


def cache_dir() -> pathlib.Path:
    """Where the pinned upstream clones live: never inside a game repository (PA3 treats a repo holding an
    `*-architect` folder as one to migrate)."""
    d = os.environ.get("PSXDECOMP_CACHE") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if not d:
        d = os.path.join(os.path.expanduser("~"), ".cache", "psxdecomp")
    p = pathlib.Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_pa3(force_untested=False, source=None, dry=False) -> tuple[pathlib.Path, list[str]]:
    """Return (the PA3 package folder at the pinned tag, deviations). Clones into the cache when needed and refuses a
    checkout whose commit is not the pinned one (unless --force-untested, which is recorded)."""
    c = compat()["pa3"]
    devs = []
    src = source or os.environ.get("PSXDECOMP_PA3_SOURCE") or c["repo"]
    clone = cache_dir() / ("pa3-" + c["tag"])
    if not clone.is_dir():
        if dry:
            return clone / c["subdir"], ["would clone %s at %s" % (src, c["tag"])]
        run(["git", "clone", "--quiet", "--depth", "1", "--branch", c["tag"], src, str(clone)], timeout=600)
    head = git(clone, "rev-parse", "HEAD").stdout.strip()
    if head != c["sha"]:
        if not force_untested:
            raise Fail("PA3 clone %s is at %s, not the tested %s (%s); re-run with --force-untested to use it anyway"
                       % (clone, head[:12], c["sha"][:12], c["tag"]))
        devs.append("PA3 at %s instead of the tested %s %s (--force-untested)" % (head[:12], c["tag"], c["sha"][:12]))
    pkg = clone / c["subdir"]
    ver = read(pkg / "VERSION").splitlines()[0].split(":", 1)[-1].strip()
    if ver != c["version"] and not force_untested:
        raise Fail("PA3 package says version %s, compat.toml pins %s" % (ver, c["version"]))
    return pkg, devs


def resolve_kit(force_untested=False, path=None) -> tuple[pathlib.Path, list[str]]:
    """Return (the decomp-architect kit folder, deviations): --kit, $PSXDECOMP_KIT or kit.default_path when given, else
    compat.toml kit.repo fetched at kit.sha into the cache; either way checked against kit.digest."""
    c = compat()["kit"]
    devs = []
    cand = path or os.environ.get("PSXDECOMP_KIT") or c.get("default_path", "")
    if c.get("repo") and not cand:
        clone = cache_dir() / ("kit-" + c["sha"][:12])
        sub = c.get("subdir", ".")
        if not (clone / sub / "install.py").is_file():          # shallow and sparse: the kit folder at the pin only
            if clone.exists():
                shutil.rmtree(clone)
            clone.mkdir(parents=True)
            git(clone, "init", "--quiet")
            git(clone, "remote", "add", "origin", c["repo"])
            if sub != ".":
                git(clone, "sparse-checkout", "set", "--no-cone", "/%s/" % sub.strip("/"))
            r = run(["git", "-C", str(clone), "fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin",
                     c["sha"]], check=False, timeout=900)
            if r.returncode != 0:
                shutil.rmtree(clone, ignore_errors=True)
                raise Fail("kit fetch of %s at %s failed: %s" % (c["repo"], c["sha"], (r.stdout + r.stderr)[-300:]))
            git(clone, "checkout", "--quiet", "FETCH_HEAD")
        cand = str(clone / sub)
    kit = pathlib.Path(os.path.expanduser(cand)) if cand else None
    if not kit or not (kit / "install.py").is_file():
        raise Fail("decomp-architect kit not found (looked at %r); pass --kit <folder> or set PSXDECOMP_KIT" % cand)
    dig = tree_digest(kit)
    if dig != c["digest"]:
        if not force_untested:
            raise Fail("kit at %s has digest %s, not the tested %s; re-run with --force-untested to use it anyway"
                       % (kit, dig[:19], c["digest"][:19]))
        devs.append("kit digest %s instead of the tested %s (--force-untested)" % (dig[:19], c["digest"][:19]))
    return kit, devs


# ---- the interpreter --------------------------------------------------------------------------------------------

def find_python(minimum=(3, 12), override=None) -> str | None:
    """The absolute path of an interpreter >= minimum: the override, then this one, then common names on PATH.
    This replaces the hard-coded `/opt/homebrew/...python3.14` that pa.json carried on one machine."""
    cands = [override] if override else []
    cands += [sys.executable] + ["python3.%d" % m for m in range(20, minimum[1] - 1, -1)] + ["python3", "python"]
    for c in cands:
        if not c:
            continue
        exe = c if os.path.isabs(c) else shutil.which(c)
        if not exe or not os.path.exists(exe):
            continue
        try:
            out = subprocess.run([exe, "-c", "import sys;print(sys.version_info[0], sys.version_info[1])"],
                                 capture_output=True, text=True, timeout=20).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            continue
        if len(out) == 2 and (int(out[0]), int(out[1])) >= minimum:
            return os.path.abspath(exe)        # unresolved: a stable symlink beats a version-pinned real path
    return None


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "game"


def self_test_banner(name: str, ok: bool):
    print("%s %s" % (name, "SELF-TEST OK" if ok else "SELF-TEST FAILED"))
    return 0 if ok else 1


def load_toml_str(text: str) -> dict:
    return tomllib.loads(text)


# ---- the AI policy: its one home is publish.py (the file game repositories vendor, whose README lint checks the
# block verbatim); re-exported here. psxdecomp's README carries it verbatim (tier 0 checks); S8 writes it into every
# game README (the README standard), or swaps it for the kit's disclosure paragraph in an older README ---------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish  # noqa: E402
from publish import AI_POLICY, AI_POLICY_MARK, OLD_DISCLOSURE, ai_policy_block  # noqa: E402,F401


# ---- the profile's deny rules (profiles/psx/deny.json): S10 writes them, upgrade adds any missing, doctor checks -----
PROFILE_DENY = PLUGIN_ROOT / "profiles" / "psx" / "deny.json"
SETTINGS = ".claude/settings.json"


def pa3_manages_settings(repo: pathlib.Path) -> bool:
    managed = publish._pa3_files(read(repo / publish.PA3_REL)) if (repo / publish.PA3_REL).is_file() else []
    return SETTINGS in managed


def deny_missing(repo: pathlib.Path) -> tuple[list[str], str | None]:
    """(the profile's deny rules the game's .claude/settings.json lacks, why psxdecomp cannot add them or None)."""
    want = json.loads(read(PROFILE_DENY))["permissions"]["deny"]
    managed = "PA3 manages %s here" % SETTINGS if pa3_manages_settings(repo) else None
    f = repo / SETTINGS
    try:
        conf = json.loads(read(f)) if f.is_file() else {}
        have = conf.get("permissions", {}).get("deny", [])
        assert isinstance(conf, dict) and isinstance(have, list)
    except (ValueError, AttributeError, AssertionError):
        return want, managed or "%s is not a JSON object with a permissions.deny list" % SETTINGS
    missing = [r for r in want if r not in have]
    return missing, managed if missing else None       # a file that holds every rule needs no hand


def with_denies(repo: pathlib.Path, missing: list[str]) -> str:
    f = repo / SETTINGS
    conf = json.loads(read(f)) if f.is_file() else {}
    conf.setdefault("permissions", {}).setdefault("deny", []).extend(missing)
    return json.dumps(conf, indent=2, ensure_ascii=False) + "\n"


# ---- the profile's hooks (profiles/psx/hooks.json: `style --hook` after a write, `guard --hook` before a call): S10
# writes them, upgrade adds any missing. A group is present when a group of the same event holds a hook of its kind:
# a command with the kind's words (HOOK_KINDS), whatever interpreter the game set for it. The style hook ends in
# `|| exit 0`: it reports, and a report that cannot start must never disturb a call. The guard fails closed: no
# `|| exit 0`, and `"onFailure": "block"` (Claude Code 2.1.295), so a guard that cannot start, that exits with an
# error or that runs out of time refuses the call it guards (observed on 2.1.296, headless).
# A group that holds a command psxdecomp wrote before (HOOK_BEFORE) is stale: upgrade writes the current one in place.
PROFILE_HOOKS = PLUGIN_ROOT / "profiles" / "psx" / "hooks.json"
PROFILE_GUARD = PLUGIN_ROOT / "profiles" / "psx" / "guard.tsv"
HOOK_KINDS = (("style-hook", "style --hook"), ("guard-hook", "guard --hook"))   # (upgrade's action, the command's words)
HOOK_BEFORE = {                                         # kind: (the commands, the matchers) of earlier versions
    "style-hook": (('python3 "$CLAUDE_PROJECT_DIR/tools/psxd_publish.py" style --hook',), ()),
    "guard-hook": (('python3 "$CLAUDE_PROJECT_DIR/tools/psxd_floor.py" guard --hook || exit 0',), ("Bash|Edit|Write",)),
}


def hook_kind(group: dict) -> str:
    """The upgrade action that adds a hook group of the profile: `style-hook` or `guard-hook`."""
    cmds = " ".join(h.get("command", "") for h in group.get("hooks", []))
    return next((key for key, words in HOOK_KINDS if words in cmds), HOOK_KINDS[0][0])


def ops_index_row(index: str, name: str, doc: str) -> str | None:
    """docs/ops/INDEX.md with the row of one docs/ops file, in PA3's ops grammar `<file> | <heading> | <line count>`;
    None when the index names the file already."""
    if re.search(r"(?m)^(?:- \[)?%s\b" % re.escape(name), index):
        return None
    head = next((l.lstrip("# ").strip() for l in doc.splitlines() if l.startswith("# ")), name)
    return "%s\n%s | %s | %d\n" % (index.rstrip("\n"), name, head, len(doc.splitlines()))


def hooks_missing(repo: pathlib.Path) -> tuple[list[tuple[str, dict]], str | None]:
    """(the profile's (event, hook group) pairs the game's .claude/settings.json lacks, why psxdecomp cannot add them
    or None)."""
    want = [(ev, g) for ev, groups in json.loads(read(PROFILE_HOOKS))["hooks"].items() for g in groups]
    managed = "PA3 manages %s here" % SETTINGS if pa3_manages_settings(repo) else None
    f = repo / SETTINGS
    try:
        have = (json.loads(read(f)) if f.is_file() else {}).get("hooks", {})
        cmds = {ev: " \n".join(str(h.get("command")) for g in have.get(ev, []) for h in g.get("hooks", [])) for ev, _ in want}
    except (ValueError, AttributeError, TypeError):
        return want, managed or "%s is not a JSON object with hook groups under `hooks`" % SETTINGS
    words = dict(HOOK_KINDS)
    missing = [(ev, g) for ev, g in want if words[hook_kind(g)] not in cmds[ev]]
    return missing, managed if missing else None


def hooks_stale(repo: pathlib.Path) -> list[tuple[str, dict]]:
    """The profile's (event, hook group) pairs whose group in .claude/settings.json holds what an earlier psxdecomp
    wrote (HOOK_BEFORE): the same command with another timeout, an earlier command, an earlier matcher. A command the
    game changed itself (another interpreter) is the game's and is never stale. [] where PA3 manages the file."""
    f = repo / SETTINGS
    if pa3_manages_settings(repo) or not f.is_file():
        return []
    try:
        have = json.loads(read(f)).get("hooks", {})
        out = []
        for ev, groups in json.loads(read(PROFILE_HOOKS))["hooks"].items():
            for g in groups:
                before, matchers = HOOK_BEFORE[hook_kind(g)]
                mine = g["hooks"][0]
                for old in have.get(ev, []):
                    for h in old.get("hooks", []):
                        ours = h.get("command") == mine["command"] or h.get("command") in before
                        if ours and (h != mine or old.get("matcher") in matchers):
                            out.append((ev, g))
        return [x for i, x in enumerate(out) if x not in out[:i]]
    except (ValueError, AttributeError, TypeError, KeyError, IndexError):
        return []


def with_hooks(repo: pathlib.Path, missing: list[tuple[str, dict]], base: str | None = None, stale=()) -> str:
    """The settings text with the missing groups, each at the end of its event's list, and with each stale group's
    hook (and its matcher, when it is an earlier psxdecomp matcher) replaced where it stands. `base`: the text to add
    to in place of the file's (with_denies' result, so that one write holds both)."""
    f = repo / SETTINGS
    conf = json.loads(base if base is not None else read(f) if f.is_file() else "{}")
    for ev, group in stale:
        before, matchers = HOOK_BEFORE[hook_kind(group)]
        mine = group["hooks"][0]
        for old in conf.get("hooks", {}).get(ev, []):
            for i, h in enumerate(old.get("hooks", [])):
                if h.get("command") == mine["command"] or h.get("command") in before:
                    old["hooks"][i] = dict(mine)
                    if old.get("matcher") in matchers:
                        old["matcher"] = group["matcher"]
    for ev, group in missing:
        conf.setdefault("hooks", {}).setdefault(ev, []).append(group)
    return json.dumps(conf, indent=2, ensure_ascii=False) + "\n"


def settings_due(repo: pathlib.Path) -> str | None:
    """The .claude/settings.json text with every deny rule and hook group psxdecomp may add here (add-only, one write
    for both), or None when none is due. S10 and upgrade both write through here."""
    text = None
    missing, why = deny_missing(repo)
    if missing and not why:
        text = with_denies(repo, missing)
    hooks, why = hooks_missing(repo)
    stale = hooks_stale(repo)
    if (hooks and not why) or stale:
        text = with_hooks(repo, [] if why else hooks, text, stale)
    return text


# ---- the firewall's block for a debug file of any build (config/firewall.txt): S9 writes it, upgrade's
# `firewall-debug` adds it. The kit's audit matches a `glob:` line with fnmatch.fnmatchcase, whose `*` crosses `/`, so
# each line refuses the extension in any folder and in any letter case ------------------------------------------------
FIREWALL = "config/firewall.txt"
FIREWALL_DEBUG_GLOBS = ("*.[Ss][Yy][Mm]", "*.[Cc][Pp][Ee]", "*.[Pp][Dd][Bb]", "*.[Dd][Bb][Gg]")
FIREWALL_DEBUG = ("# ---- psxdecomp: a debug file of any build (a symbol file, a linker's debug executable) ----\n"
                  "# A link map (.MAP) has no line here: a game tracks text files of that name. The checksum file\n"
                  "# (config/oracle.<id>.sha1, written by psxdecomp's `oracle add`) covers a supplied copy.\n"
                  + "".join("glob:  %s\n" % g for g in FIREWALL_DEBUG_GLOBS))


def firewall_lines(text: str, kind: str) -> list[str]:
    """The values of one rule kind in a firewall file, read as the kit's audit reads them (`#` starts a comment)."""
    rows = (l.split("#", 1)[0].partition(":") for l in text.splitlines())
    return [value.strip() for k, _, value in rows if k.strip() == kind]


def firewall_debug_due(text: str) -> bool:
    return not set(FIREWALL_DEBUG_GLOBS) <= set(firewall_lines(text, "glob"))


def with_firewall_debug(text: str) -> str:
    return text.rstrip("\n") + "\n\n" + FIREWALL_DEBUG if firewall_debug_due(text) else text


def firewall_debug_hits(repo: pathlib.Path) -> list[str]:
    """The tracked files that a line of the block refuses: with one of these, the block would break the audit."""
    import fnmatch
    r = git(repo, "ls-files", "-z", check=False)
    return sorted(p for p in r.stdout.split("\0") if p and any(fnmatch.fnmatchcase(p, g) for g in FIREWALL_DEBUG_GLOBS))


# ---- the local record: <git-common-dir>/psxdecomp/local.toml, the paths of this machine (`[dump] path`, and
# `[builds] <id>` for each other build of the game). Git cannot track a file of its own directory, and each worktree of
# the clone reads the same one (scripts/publish.py keeps psxdecomp/public.git in that folder) -------------------------
LOCAL_REL = "psxdecomp/local.toml"
LOCAL_HEAD = ("# psxdecomp: the paths of this machine (`psxd oracle add`, `link` and `record --dump` write them). The file\n"
              "# lies in the git directory: git cannot track it, and each worktree of this clone reads it.\n")


def local_path(repo) -> pathlib.Path | None:
    """The local record's path; None when `repo` is not the top folder of a git work tree."""
    r = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir", "--show-toplevel", check=False)
    out = r.stdout.splitlines()
    if r.returncode != 0 or len(out) != 2 or os.path.realpath(out[1]) != os.path.realpath(str(repo)):
        return None
    return pathlib.Path(out[0]) / LOCAL_REL


def local_read(repo) -> dict:
    """The local record as tables; {} when there is none."""
    p = local_path(repo)
    if p is None or not p.is_file():
        return {}
    try:
        doc = load_toml(p)
    except tomllib.TOMLDecodeError as e:
        raise Fail("%s is not TOML (%s): repair it or remove it" % (p, e))
    return {t: rows for t, rows in doc.items() if isinstance(rows, dict)}


def local_set(repo, table: str, key: str, value: str | None) -> pathlib.Path:
    """Write `key = "value"` into `[table]` of the local record (None removes the key). Returns the file's path."""
    p = local_path(repo)
    if p is None:
        raise Fail("%s is not the top folder of a git work tree: a path of this machine is kept in the git directory" % repo)
    doc = local_read(repo)
    rows = doc.setdefault(table, {})
    rows.pop(key, None)
    if value is not None:
        rows[key] = str(value)

    def k(name):
        return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name)

    write(p, LOCAL_HEAD + "".join("\n[%s]\n%s" % (k(t), "".join(
        "%s = %s\n" % (k(n), json.dumps(str(v), ensure_ascii=False)) for n, v in sorted(rows.items())))
        for t, rows in sorted(doc.items()) if rows))
    return p


# ---- the profile's rules (profiles/psx/rules/<id>.md, each a body with no title line): the game's own rules_add.py
# writes rules/<id>.md and its row of rules/INDEX.md. Never `promote`: a headline stays out of the project-architect
# skill, and no rule text goes in the card. S10 and upgrade's `<x>-rule` actions both go through here ----------------
PROFILE_STE = PLUGIN_ROOT / "profiles" / "psx" / "rules" / "STE1.md"
STE_RULE, STE_INDEX, STE_TOOL = "rules/STE1.md", "rules/INDEX.md", "tools/rules_add.py"
STE_TITLE = ("Public files (`config/public-paths.txt`) follow `rules/STE1.md`. Read it before you write one. An "
             "instruction has at most 20 words, a description at most 25. A paragraph has at most 6 sentences. Use no "
             "semicolon: write two sentences. Put the condition before the command.")
FIN_TITLE = ("A source file is finished only when it is matched and has no readability debt (`rules/FIN1.md`, "
             "`python3 tools/psxd_floor.py debt`). Until then, call it matched and say that it has readability debt.")
NAME_TITLE = ("A name needs recorded evidence (`rules/NAME1.md`, `config/names.tsv`). A byte-identical build proves "
              "behaviour, not a name. Keep the placeholder until there is evidence.")
# id: (group, tags, title, upgrade's action, what the rule is, the [own] key that replaces it)
PROFILE_RULES = {
    "STE1": ("STE", "writing,public", STE_TITLE, "ste-rule", "the writing rule of the public files", None),
    "FIN1": ("FIN", "readability,debt", FIN_TITLE, "fin-rule", "the finished-file rule: matched is not finished", "debt"),
    "NAME1": ("NAME", "readability,names", NAME_TITLE, "name-rule", "the naming rule: a name needs evidence", "names"),
}


def rule_paths(rid: str) -> tuple[str, pathlib.Path]:
    """(the rule's path in a game, its body in the profile)."""
    return "rules/%s.md" % rid, PLUGIN_ROOT / "profiles" / "psx" / "rules" / ("%s.md" % rid)


def rule_state(repo: pathlib.Path, rid: str) -> str | None:
    """None when rules/<id>.md holds the profile's body (its title line and its dated metadata line are not compared),
    else "add", "rewrite" (another body), or "manual" (the repository has no tools/rules_add.py)."""
    rel, body = rule_paths(rid)
    f = repo / rel
    if f.is_file() and "".join(read(f).split("\n", 2)[2:]).strip() == read(body).strip():
        return None
    if not (repo / STE_TOOL).is_file():
        return "manual"
    return "rewrite" if f.is_file() else "add"


def rule_write(repo: pathlib.Path, python: str, rid: str, dry: bool = False) -> list[str]:
    """Run the game's rules_add.py for a rule that is due; returns `created|changed <path>` per file it wrote. A dry
    run runs no tool and names both files."""
    state = rule_state(repo, rid)
    if state not in ("add", "rewrite"):
        return []
    group, tags, title = PROFILE_RULES[rid][:3]
    rel, body = rule_paths(rid)
    rels = (rel, STE_INDEX)
    old = [(repo / x).read_bytes() if (repo / x).is_file() else None for x in rels]
    status = ["created" if o is None else "changed" for o in old]
    if dry:
        return ["would be %s %s" % (st, x) for st, x in zip(status, rels)]
    r = run([python, STE_TOOL, "add", "--id", rid, "--title", title, "--group", group, "--tags", tags, "--origin",
             "psxdecomp", "--file", body] + (["--force"] if state == "rewrite" else []), cwd=repo, check=False,
            env={"PA_PROJECT_ROOT": str(repo)})
    if r.returncode != 0 or rule_state(repo, rid):
        raise Fail("%s did not write %s: %s" % (STE_TOOL, rel, (r.stdout + r.stderr).strip()[-300:]))
    return ["%s %s" % (st, x) for st, x, o in zip(status, rels, old)
            if (repo / x).is_file() and (repo / x).read_bytes() != o]


def ste_rule_state(repo: pathlib.Path) -> str | None:
    return rule_state(repo, "STE1")


def ste_rule_write(repo: pathlib.Path, python: str, dry: bool = False) -> list[str]:
    return rule_write(repo, python, "STE1", dry)


# ---- the first ratchet of the writing findings (config/style-ratchet.txt): S10 and upgrade write it once, after
# their other writes (each can change a count). After that it is the game's: `style --update` alone rewrites it ------
KIT_PROSE = ("docs/decomp-kernels.md", "docs/decomp-architect.md", "docs/decomp-architect-install.md",
             "docs/knowledge-corpus.md", "docs/tools-manifest.md")
RATCHET_HEAD = ("%s: the count of writing findings of each public prose file (rules/STE1.md)."
                % publish.STYLE_RATCHET_REL,
                "A count may only fall. After a fix, run `python3 %s style --update`." % publish.VENDORED,
                "The `skip` lines name files that the kit or a generator writes.")


def first_ratchet(repo: pathlib.Path) -> str:
    """The text of a game's first ratchet: the counts of now, the kit's five files skipped."""
    try:
        return publish.ratchet_text(publish.style_counts(repo, skip=KIT_PROSE), skip=KIT_PROSE, head=RATCHET_HEAD)
    except publish.Fail as e:
        raise Fail("%s: %s" % (publish.STYLE_RATCHET_REL, e))


def swappable_disclosure(text: str | None) -> bool:
    """A disclosure paragraph the block replaces: the old default sentence, or the policy itself (kept once)."""
    t = (text or "").strip()
    return bool(t) and (t.startswith(OLD_DISCLOSURE) or t == AI_POLICY)


POLICY_BLOCK_RE = re.compile(r"^%s[ \t]*\n> \[!IMPORTANT\][ \t]*\n> \*\*AI policy:\*\* .*$" % re.escape(AI_POLICY_MARK),
                             re.M)


def with_ai_policy(readme: str, replace: str | None = None) -> str:
    """The README with the AI policy block after its title and lead paragraph (before the first `## `). `replace`:
    the kit's disclosure paragraph (the AI_DISCLOSURE answer), removed when it is swappable — a developer's own
    sentence stays. A README that holds the block keeps it where it is: its three lines become the current block
    (an older text of the policy), nothing else changes. Idempotent."""
    if replace and swappable_disclosure(replace):
        para = "\n\n%s\n" % replace.strip()
        while para in readme:
            readme = readme.replace(para, "\n", 1)
    if AI_POLICY_MARK in readme:
        return POLICY_BLOCK_RE.sub(lambda m: ai_policy_block().rstrip("\n"), readme)
    lines = readme.splitlines(keepends=True)
    at = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    head = "".join(lines[:at]).rstrip("\n")
    return (head + "\n\n" if head else "") + ai_policy_block() + "\n" + "".join(lines[at:])


# ---- install hints: what to run when a tool is missing (macOS: Homebrew; Linux: apt, and the Homebrew formula when
# one exists; casks are macOS-only) -------------------------------------------------------------------------------
# Linux values checked 2026-10-02 (apt-cache in Ubuntu 22.04-26.04 and Debian 12-13 images; the Homebrew API);
# profiles/psx/hosts/linux-amd64.md holds the table and the WSL notes.
INSTALL = {   # tool: (macOS, Debian/Ubuntu, Homebrew on Linux or None)
    "git": ("brew install git", "sudo apt install git", "brew install git"),
    "gh": ("brew install gh", "GitHub's apt repository, https://github.com/cli/cli/blob/trunk/docs/install_linux.md "
           "(the distro gh 2.45/2.46 is broken)", "brew install gh"),
    "python": ("brew install python@3.14", "sudo apt install python3 python3-venv (3.12+ on Ubuntu 24.04+ and Debian "
               "13+ only)", "brew install python@3.14"),
    "docker": ("brew install --cask docker-desktop", "sudo apt install docker.io (WSL 2: Docker Desktop's WSL "
               "integration, or docker.io with systemd on)", None),
    "claude": ("brew install --cask claude-code", "curl -fsSL https://claude.ai/install.sh | bash",
               "brew install --cask claude-code"),
    "ripgrep": ("brew install ripgrep", "sudo apt install ripgrep", "brew install ripgrep"),
}


def install_hint(tool: str, system: str | None = None) -> str:
    """`install: brew install X` on macOS; `install: sudo apt install Y (or brew install X)` on Linux."""
    import platform
    mac, apt, linuxbrew = INSTALL[tool]
    if (system or platform.system()) == "Darwin":
        return "install: %s" % mac
    return "install: %s%s" % (apt, " (or %s)" % linuxbrew if linuxbrew else "")
