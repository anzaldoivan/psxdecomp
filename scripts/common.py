"""Shared helpers for the psxdecomp scripts: paths, TOML, the stage state file, pins, the PA3/kit sources.

Standard library only (Python >= 3.11 for tomllib). Every script that writes has --dry-run and --self-test.
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


# ---- the AI policy (one home: psxdecomp's README carries it verbatim, tier 0 checks; S10 puts it in every game
# README) --------------------------------------------------------------------------------------------------------
AI_POLICY = ("LLMs produce negligible decompilation results without good guidance. Investigate and familiarize "
             "yourself with the console's architecture and the game you are decompiling, and always use your own "
             "judgment. Humans drive the decisions; AI reads and writes the code.")
AI_POLICY_MARK = "<!-- psxdecomp: ai-policy -->"


def ai_policy_block() -> str:
    return "%s\n> [!IMPORTANT]\n> **AI policy:** %s\n" % (AI_POLICY_MARK, AI_POLICY)


def with_ai_policy(readme: str) -> str:
    """The README with the AI policy block after its title and lead paragraph (before the first `## `); unchanged when
    the block is already there."""
    if AI_POLICY_MARK in readme:
        return readme
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
