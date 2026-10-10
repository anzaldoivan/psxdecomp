"""Tier 1, split mode end to end: the bootstrapped fixture as `<game>-dev`, a bare repository standing in for the
public `<game>` on GitHub (merges done the way GitHub squashes them), a contributor's fork, and a fake agent that keeps
committing through tools/commit_task.sh while releases and imports run. Every scenario runs under a POSIX git config
and a Windows-like one (autocrlf, no filemode, no symlinks). Nothing leaves the temporary directory."""
import fcntl
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time

import pytest

from conftest import ROOT, bootstrap, run

PROFILES = {
    "posix": "[core]\n\tautocrlf = false\n",
    "windows-like": "[core]\n\tautocrlf = true\n\tfilemode = false\n\tsymlinks = false\n\tignorecase = true\n",
}
DEV = "Dev <dev@example.invalid>"
CON = "Con Tributor <con@example.invalid>"
OWNER = "Owner <owner@example.invalid>"
PUBLIC_LIST = """# What a release publishes (default deny). Itself public.
.clang-format
.gitignore
.github/
LICENSE
README.md
CONTRIBUTING.md
Makefile
src/
cookbook/
config/public-paths.txt
config/psxdecomp.toml
config/firewall.txt
config/firewall-fixture.sha1
config/categories.tsv
config/discs.tsv
config/medium.sha1
config/check.*.sha
tools/audit_public.py
tools/psxd_publish.py
"""
LAND_CHECK = """import pathlib, sys
tree = pathlib.Path(sys.argv[1])
bad = [str(p) for p in tree.rglob("*") if p.is_file() and b"<<<<<<<" in p.read_bytes()]
sys.exit("conflict markers: %s" % bad if bad else 0)
"""
GITATTRIBUTES = "* text=auto\n*.sh text eol=lf\n"
AGENT_PATHS = ("src/agent_log.c", "src/units.tsv", "src/pulled/", "phase-ends/current/", ".claude-state/memory/")
UNITS = "# units: one row per carve, appended by the agents and by contributors\n# alias\tstart\tunit\n"
FAKE_DOCKER = r"""#!/usr/bin/env python3
# A fake `docker` for ship's ci-sim stage: the image build passes; a job run checks what ci-sim mounts at /src (the
# projection, with no-rom.yml and what its jobs call) and at /sim (the job script) instead of running it.
import pathlib, sys
a = sys.argv[1:]
if a[:1] == ["build"]:
    print("sha256:" + "0" * 64)
    sys.exit(0)
if a[:1] != ["run"]:
    sys.exit("fake docker: unexpected " + " ".join(a))
mounts = dict(reversed(v.split(":")[:2]) for k, v in zip(a, a[1:]) if k == "-v")
tree, sim = pathlib.Path(mounts["/src"]), pathlib.Path(mounts["/sim"])
need = [".github/workflows/no-rom.yml", "Makefile", "tools/audit_public.py", "tools/psxd_publish.py"]
missing = [n for n in need if not (tree / n).is_file()] + ([] if (sim / "job.sh").is_file() else ["job.sh"])
leaked = [n for n in ("CLAUDE.md", ".claude", "phase-ends") if (tree / n).exists()]
print("fake job on %s: missing %s, private %s" % (tree.name, missing, leaked))
sys.exit(1 if missing or leaked else 0)
"""
FAKE_GH = r"""#!/usr/bin/env python3
# A fake `gh` for ship: open release PRs in a JSON file, every check green, and `pr merge` as GitHub's squash merge
# of the PR into the bare public repository (PR_TITLE (#n) + PR_BODY), authored by the developer.
import json, os, pathlib, subprocess, sys
state = pathlib.Path(os.environ["FAKE_GH_STATE"])
st = json.loads(state.read_text()) if state.exists() else {"prs": {}, "n": 100}
pub, R, DEVR = os.environ["FAKE_GH_PUB"], "repos/" + os.environ["FAKE_GH_REPO"], os.environ["FAKE_GH_DEV"]
CHECKS = json.loads(os.environ["FAKE_GH_CHECKS"])
a = sys.argv[1:]


def git(*args):
    return subprocess.run(["git", "-c", "commit.gpgsign=false"] + [str(x) for x in args], capture_output=True,
                          text=True, check=True).stdout.strip()


def opt(k):
    return a[a.index(k) + 1]


def api(path):
    head = lambda n: st["prs"][n]["sha"]  # noqa: E731
    if path.startswith("repos/%s/actions/runs?head_sha=" % DEVR):
        return {"workflow_runs": [{"id": 1, "workflow_id": 1, "name": "no-rom", "event": "push",
                                   "status": "completed", "conclusion": "success"}]}
    for n in st["prs"]:
        if path == "%s/pulls/%s" % (R, n):
            p = st["prs"][n]
            return {"state": p["state"], "base": {"ref": "main"}, "title": p["title"], "body": p["body"],
                    "head": {"sha": p["sha"], "ref": p["br"], "repo": {"full_name": R[6:]}}}
        if path == "%s/pulls/%s/files?per_page=100" % (R, n):
            return [{"filename": f} for f in git("-C", pub, "diff", "--name-only", head(n) + "^", head(n)).split()]
    if path.startswith("%s/commits/" % R) and path.endswith("/check-runs?per_page=100"):
        return {"check_runs": [{"name": c, "status": "completed", "conclusion": "success", "app": {"id": 15368},
                                "check_suite": {"id": 100 + i}} for i, c in enumerate(CHECKS)]}
    if path.startswith("%s/actions/runs?head_sha=" % R) and "&event=push" in path:
        return {"workflow_runs": [{"id": 70, "name": "build", "path": ".github/workflows/build.yml",
                                   "status": "completed", "conclusion": "success"}]}
    if path.startswith("%s/actions/runs?head_sha=" % R):
        h = path.split("=")[1].split("&")[0]
        return {"workflow_runs": [{"id": 900 + i, "check_suite_id": 100 + i, "head_sha": h,
                                   "path": ".github/workflows/build.yml" if c.startswith("build ") else
                                   ".github/workflows/no-rom.yml",
                                   "event": "pull_request_target" if c.startswith("build ") else "pull_request"}
                                  for i, c in enumerate(CHECKS)]}
    if path == "%s/actions/runs/70/artifacts?per_page=100" % R:
        return {"artifacts": [{"name": c[len("build "):] + "_report"} for c in CHECKS if c.startswith("build ")]}
    sys.exit("HTTP 404: " + path)


out = ""
if a[:2] == ["pr", "list"]:
    out = json.dumps([{"number": int(n), "headRefName": p["br"], "url": p["url"]} for n, p in st["prs"].items()
                      if p["state"] == "open"])
elif a[:2] == ["pr", "create"]:
    st["n"] += 1
    br = opt("--head")
    st["prs"][str(st["n"])] = {"br": br, "sha": git("-C", pub, "rev-parse", "refs/heads/" + br), "state": "open",
                               "title": opt("--title"), "body": pathlib.Path(opt("--body-file")).read_text(),
                               "url": "https://github.com/%s/pull/%d" % (R[6:], st["n"])}
    out = st["prs"][str(st["n"])]["url"]
elif a[:2] == ["pr", "merge"]:
    p = st["prs"][a[2]]
    if opt("--match-head-commit") != p["sha"] or "--admin" not in a:
        sys.exit("the head moved, or no --admin")
    wc = state.parent / "gh-merge"
    if not wc.exists():
        git("clone", "-q", pub, wc)
    git("-C", wc, "fetch", "-q", "origin")
    git("-C", wc, "checkout", "-q", "-f", "-B", "main", "origin/main")
    git("-C", wc, "fetch", "-q", "origin", "refs/heads/" + p["br"])
    git("-C", wc, "merge", "--squash", "-q", "FETCH_HEAD")
    git("-C", wc, "-c", "user.name=Dev", "-c", "user.email=dev@example.invalid", "commit", "-q", "-m",
        "%s (#%s)\n\n%s" % (p["title"], a[2], p["body"]))
    git("-C", wc, "push", "-q", "origin", "HEAD:main")
    p["state"] = "merged"
elif a[:1] == ["api"]:
    out = json.dumps(api(a[3]))
else:
    sys.exit("fake gh: unexpected " + " ".join(a))
state.write_text(json.dumps(st))
print(out)
"""


@pytest.fixture(scope="module")
def fixture_game(toolchain, tmp_path_factory):
    """The bootstrapped fixture plus a .gitattributes keeping shell scripts LF (ECOSYSTEM.md K9): without one, an
    autocrlf checkout gives tools/commit_task.sh CRLF line ends and bash refuses it before split mode is reached."""
    target = tmp_path_factory.mktemp("split") / "homebrew-fixture"
    bootstrap(toolchain, target)
    (target / ".gitattributes").write_text(GITATTRIBUTES)
    run(["git", "-C", target, "add", ".gitattributes"])
    run(["git", "-C", target, "-c", "commit.gpgsign=false", "commit", "-qm", "K9: .gitattributes"])
    return target


class World:
    def __init__(self, root: pathlib.Path, game: pathlib.Path, profile: str):
        self.root = root
        cfg = root / "gitconfig"
        cfg.write_text(PROFILES[profile])
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "CLAUDECODE"}
        self.env.update(GIT_CONFIG_GLOBAL=str(cfg), GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
        self.dev, self.pub, self.maint = root / "dev", root / "pub.git", root / "maint"
        self.fork, self.wc = root / "fork.git", root / "contrib"
        self.n = 0                                     # PR numbers
        self.git(root, "clone", "-q", "--no-local", game, self.dev)
        self.git(self.dev, "remote", "set-url", "origin", "https://github.com/example/homebrew-fixture-dev.git")
        self.ident(self.dev, DEV)
        self.git(root, "init", "-q", "--bare", self.pub)
        self.git(self.pub, "symbolic-ref", "HEAD", "refs/heads/main")
        self.cache = self.dev / ".git/psxdecomp/public.git"
        (root / "land_check.py").write_text(LAND_CHECK)

    # ---- plumbing
    def git(self, repo, *args, env=None, check=True, strip=True):
        r = subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false"] + [str(a) for a in args],
                           env=dict(self.env, **(env or {})), capture_output=True, text=True)
        if check and r.returncode:
            raise AssertionError("git %s -> %d\n%s%s" % (" ".join(map(str, args)), r.returncode, r.stdout, r.stderr))
        return r.stdout.strip() if strip else r.stdout                  # str.strip() also eats \x1c-\x1f

    def ident(self, repo, who):
        name, email = re.match(r"(.*) <(.*)>", who).groups()
        self.git(repo, "config", "user.name", name)
        self.git(repo, "config", "user.email", email)

    def tool(self, *args, agent=False):
        """tools/psxd_publish.py in dev, as the developer (or, agent=True, from an agent session's shell)."""
        env = dict(self.env, CLAUDECODE="1") if agent else self.env
        r = subprocess.run([sys.executable, "tools/psxd_publish.py"] + list(args), cwd=self.dev, env=env,
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def put(self, repo, files):
        for rel, body in files.items():
            f = pathlib.Path(repo) / rel
            if body is None:
                f.unlink()
            else:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(body)

    def router(self, msg, files, *paths):
        """A developer or router commit in dev, through the agents' own commit_task.sh (agent paused)."""
        self.put(self.dev, files)
        r = subprocess.run(["bash", "tools/commit_task.sh", "router", msg] + list(paths or files), cwd=self.dev,
                           env=self.env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        return self.git(self.dev, "rev-parse", "HEAD")

    def tree(self, repo, rev):
        out = self.git(repo, "ls-tree", "-r", "--full-tree", rev)
        return {l.split("\t", 1)[1]: tuple(l.split("\t")[0].split()[::2]) for l in out.splitlines() if l}

    # ---- GitHub
    def sync_maint(self):
        if not self.maint.exists():
            self.git(self.root, "clone", "-q", self.pub, self.maint)
            self.ident(self.maint, OWNER)
        self.git(self.maint, "fetch", "-q", "origin")
        self.git(self.maint, "checkout", "-q", "-f", "-B", "main", "origin/main")
        self.git(self.maint, "clean", "-qfd")

    def merge(self, src, ref, title, body, author):
        """GitHub's squash merge (PR_TITLE + PR_BODY), authored by the PR's author."""
        self.n += 1
        self.sync_maint()
        self.git(self.maint, "fetch", "-q", src, ref)
        self.git(self.maint, "merge", "--squash", "-q", "FETCH_HEAD")
        msg = "%s (#%d)\n\n%s" % (title, self.n, body)
        self.git(self.maint, "commit", "-q", "--author", author, "-m", msg)
        self.git(self.maint, "push", "-q", "origin", "HEAD:main")
        return self.git(self.maint, "rev-parse", "HEAD")

    def direct(self, files, msg):
        """The owner's commit straight to public main (a hotfix in the web editor)."""
        self.sync_maint()
        self.put(self.maint, files)
        self.git(self.maint, "add", "-A")
        self.git(self.maint, "commit", "-qm", msg)
        self.git(self.maint, "push", "-q", "origin", "HEAD:main")
        return self.git(self.maint, "rev-parse", "HEAD")

    def revert(self, sha):
        """GitHub's Revert button: a branch with the revert, then a squash-merged PR."""
        self.sync_maint()
        subj = self.git(self.maint, "log", "-1", "--format=%s", sha)
        self.git(self.maint, "revert", "--no-edit", sha)
        self.git(self.maint, "push", "-q", "-f", "origin", "HEAD:refs/heads/revert-%s" % sha[:7])
        return self.merge(self.pub, "refs/heads/revert-%s" % sha[:7], 'Revert "%s"' % subj,
                          "Reverts example/homebrew-fixture#%d" % self.n, OWNER)

    def update_branch(self, branch):
        """GitHub's Update branch on a same-repository PR: main merged into it."""
        self.sync_maint()
        self.git(self.maint, "fetch", "-q", "origin", branch)
        self.git(self.maint, "checkout", "-q", "-B", "upd", "FETCH_HEAD")
        self.git(self.maint, "merge", "-q", "--no-edit", "origin/main")
        self.git(self.maint, "push", "-q", "origin", "upd:refs/heads/" + branch)

    def contribute(self, title, files=None, mut=None, body="", author=CON):
        """A contributor's PR from the fork, squash-merged by the owner."""
        if not self.wc.exists():
            self.git(self.root, "clone", "-q", "--bare", self.pub, self.fork)
            self.git(self.root, "clone", "-q", self.fork, self.wc)
            self.git(self.wc, "remote", "add", "upstream", self.pub)
            self.ident(self.wc, author)
        self.git(self.wc, "fetch", "-q", "upstream")
        self.git(self.wc, "checkout", "-q", "-f", "-B", "topic", "upstream/main")
        self.put(self.wc, files or {})
        if mut:
            mut(self.wc)
        self.git(self.wc, "add", "-A")
        self.git(self.wc, "commit", "-qm", title, "--author", author)
        self.git(self.wc, "push", "-q", "-f", "origin", "topic")
        return self.merge(self.fork, "refs/heads/topic", title, body, author)

    # ---- the developer's commands
    def release(self, summary, *extra):
        """A release the developer has reviewed: --ack-new is passed (the agents' new sources are new paths)."""
        rc, out = self.tool("release", "--summary", summary, "--ack-new", *extra)
        assert rc == 0 and "RELEASE release/" in out, out
        br, sha = re.search(r"RELEASE (release/\w+) (\w+):", out).groups()
        self.git(self.cache, "push", "-q", self.pub, "refs/heads/%s:refs/heads/%s" % (br, br))
        return br, sha, out

    def merge_release(self, br, summary):
        body = (self.cache / ("PR_BODY-%s.md" % br.split("/")[1])).read_text()
        return self.merge(self.pub, "refs/heads/" + br, "Release: " + summary, body, DEV)

    def ship(self, summary, *extra):
        br, _, out = self.release(summary, *extra)
        return self.merge_release(br, summary), out

    def importer(self, *extra):
        rc, out = self.tool("import", *extra)
        assert rc == 0, out
        return out

    def land(self):
        return self.tool("land")

    def landed(self):
        rc, out = self.tool("land")
        assert rc == 0 and "LAND OK" in out, out
        return True


class Agent(threading.Thread):
    """The router and its coders: each step marks .run/status.json busy, writes the AUTO areas, appends to a listed
    source, pulls a file back from the 'volume' under the gate's apply.lock, and commits through commit_task.sh."""

    def __init__(self, w: World):
        super().__init__(daemon=True)
        self.w, self.n, self.errors = w, 0, []
        self.go, self.idle, self.done = threading.Event(), threading.Event(), threading.Event()
        self.idle.set()

    def status(self, task):
        st = {"task": task, "kind": "code" if task else None, "waiting": None, "router_session": "s1"}
        self.w.put(self.w.dev, {".run/status.json": json.dumps(st)})

    def step(self):
        self.n += 1
        t, d = "T%d" % self.n, self.w.dev
        self.status(t)
        self.w.put(d, {"phase-ends/current/tasks/%s.md" % t: "# %s\n" % t,
                       "phase-ends/current/logs/%s.log" % t: "log %s\n" % t})
        with open(d / "src/agent_log.c", "a") as f:
            f.write("/* %s */\n" % t)
        units = ["src/units.tsv"] if (d / "src/units.tsv").exists() else []
        if units:
            with open(d / "src/units.tsv", "a") as f:
                f.write("agent\t0x%08x\tfn_%d\n" % (0x80020000 + 4 * self.n, self.n))
        lock = d / ".run/gate/apply.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with open(lock, "w") as fd:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self.w.put(d, {"src/pulled/fn_%d.c" % self.n: "int fn_%d(void) { return %d; }\n" % (self.n, self.n)})
            fcntl.flock(fd, fcntl.LOCK_UN)
        r = subprocess.run(["bash", "tools/commit_task.sh", t, "agent step %d" % self.n, "src/agent_log.c",
                            "src/pulled"] + units, cwd=d, env=self.w.env, capture_output=True, text=True)
        if r.returncode:
            self.errors.append(r.stdout + r.stderr)
        self.status(None)

    def run(self):
        while not self.done.is_set():
            if not self.go.is_set():
                self.idle.set()
                time.sleep(0.02)
                continue
            self.idle.clear()
            try:
                self.step()
            except Exception as e:                          # noqa: BLE001 — reported by the test
                self.errors.append(repr(e))
            time.sleep(0.02)
        self.idle.set()

    def pause(self):
        self.go.clear()
        time.sleep(0.05)
        assert self.idle.wait(60)

    def resume(self, steps=1):
        """Run, and wait until at least `steps` more agent commits exist."""
        want = self.n + steps
        self.go.set()
        deadline = time.time() + 60
        while self.n < want and time.time() < deadline:
            time.sleep(0.02)
        assert self.n >= want, self.errors


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_split_story(fixture_game, tmp_path, profile):
    w = World(tmp_path, fixture_game, profile)
    d = w.dev
    assert w.git(d, "show", "HEAD:tools/psxd_publish.py", strip=False) == (ROOT / "scripts/publish.py").read_text()
    w.put(d, {"src/agent_log.c": "/* agent log */\n",                  # an emptied inbox: PA3's template, placeholder
              "phase-ends/current/INBOX.md": (d / "templates/INBOX.template.md").read_text()})
    w.router("agent log file; the inbox", {}, "src/agent_log.c", "phase-ends/current/INBOX.md")
    agent = Agent(w)
    agent.start()
    try:
        _story(w, agent)
    finally:
        agent.done.set()
        agent.join(30)
    assert not agent.errors, agent.errors
    _invariants(w, agent)


def _story(w: World, agent: Agent):
    d = w.dev
    toml = (d / "config/psxdecomp.toml").read_text()
    w.router("split mode: the public list and [public]", {
        "config/public-paths.txt": PUBLIC_LIST,
        "config/psxdecomp.toml": toml + '\n[public]\nrepo = "example/homebrew-fixture"\nurl = "%s"\n'
        'dev_branch = "main"\nchecks = ["build PSXD_000.01", "public-clean audit (no game bytes)"]\n'
        'land_check = [%s, %s, "{tree}"]\nassisted_by = "Claude Code (test)"\nkeyed = {"src/units.tsv" = 2}\n' % (
            w.pub, json.dumps(sys.executable), json.dumps(str(w.root / "land_check.py")))})

    # the stock README links agent-only paths; the preflight refuses it before any ref exists
    rc, out = w.tool("release", "--summary", "first", "--ack-new")
    assert rc == 1 and "docs/ops/host-recipe.md" in out and not w.git(w.cache, "for-each-ref", "refs/heads"), out
    sys.path.insert(0, str(d / "tools"))
    import psxd_publish as P
    sys.path.pop(0)
    readme = (d / "README.md").read_text()
    readme = re.sub(r"\| `(docs|rules|phase-ends)/` \|[^\n]*\n", "", readme)
    readme = readme.replace("is in [docs/ops/host-recipe.md](docs/ops/host-recipe.md).", "needs Docker and Python.")
    readme = re.sub(r"(## Building the decompilation\n\n)[^\n]*\n[^\n]*\n", r"\1```sh\nmake extract && make build\n```\n",
                    readme)
    files = {"config/categories.tsv": P.SELF_TSV, "config/discs.tsv": P.SELF_DISCS, "config/medium.sha1": P.SELF_MEDIUM,
             "config/check.PSXD_000.01.sha": P.SELF_CHECK, "README.md": readme,
             "Makefile": (d / "Makefile").read_text() + "\n.PHONY: build check extract\nbuild:\n\t@echo build\n"
                                                       "check extract: build\n\t@echo ok\n",
             "src/conflict.c": "a\nb\nc\nd\n", "src/run.sh": "echo run\n", "src/units.tsv": UNITS}
    w.put(d, files)
    assert subprocess.run([sys.executable, "tools/psxd_publish.py", "render", "--write"], cwd=d, env=w.env,
                          capture_output=True).returncode == 0
    w.router("a public-shaped README", {}, *files)
    assert "decomp.dev/example/homebrew-fixture?" in (d / "README.md").read_text()      # [public].repo

    # release 1, with the agents running: public has no main, so the release commit itself becomes main (no PR);
    # the same inputs give the same commit (racing releases)
    agent.resume(2)
    rc, out = w.tool("release", "--summary", "first", "--ack-new", agent=True)
    assert rc == 1 and "CLAUDECODE" in out, out                                       # an agent never releases
    agent.pause()
    rc, out = w.tool("release", "--summary", "first", "--ack-new")
    sha = re.search(r"RELEASE release/\w+ (\w+):", out)[1]
    assert rc == 0 and re.search(r"push \S+ %s\w{30}:refs/heads/main" % sha, out) and "gh pr" not in out, out
    rc, out = w.tool("release", "--summary", "first", "--ack-new", "--push")
    assert rc == 0 and "as public main (release 1)" in out and re.search(r"RELEASE release/\w+ (\w+):", out)[1] == sha
    r1 = w.git(w.pub, "rev-parse", "main")
    assert r1.startswith(sha) and not w.git(w.pub, "for-each-ref", "refs/heads/release/"), out
    agent.resume(2)
    pub = w.tree(w.pub, "main")
    assert "CLAUDE.md" not in pub and not any(p.startswith((".claude/", "phase-ends/", "docs/")) for p in pub)
    assert "src/agent_log.c" in pub and "Assisted-by: Claude Code (test)" in w.git(w.pub, "log", "-1", "--format=%B")
    chk = w.root / "pubclone"
    w.git(w.root, "clone", "-q", w.pub, chk)
    assert subprocess.run([sys.executable, "tools/psxd_publish.py", "check-public"], cwd=chk, env=w.env,
                          capture_output=True).returncode == 0

    # steady state: a contributor PR (with a co-author) imported while the agents commit, landed at the phase end
    c1 = w.contribute("Add contrib1", {"src/contrib1.c": "/* CONTRIB-1 */\n"},
                      body="Matches contrib1.\n\nCo-authored-by: Pair <pair@example.invalid>")
    out = w.importer()
    assert "IMPORT ready" in out, out
    agent.resume(2)
    agent.pause()
    rc, out = w.land()
    assert rc == 1 and "import again" in out, out                                     # dev moved since import
    w.importer()
    agent.status("T-busy")
    rc, out = w.land()
    assert rc == 1 and "router is busy" in out, out
    agent.status(None)
    for name, make, word in _blockers(w):
        undo = make()
        rc, out = w.land()
        undo()
        assert rc == 1 and word in out, (name, out)
    rc, out = w.land()
    assert rc == 0 and "LAND OK" in out, out
    imp = w.git(d, "log", "-1", "--format=%an%n%B")
    assert imp.startswith("Con Tributor\nImport ") and "Imported-From: %s" % c1 in imp
    assert "Co-authored-by: Pair <pair@example.invalid>" in imp
    assert "CONTRIB-1" in (d / "src/contrib1.c").read_text()

    # the round trip: release 2 carries the agents' work and the contributor's file unchanged
    agent.resume(2)
    agent.pause()
    r2, out = w.ship("second")
    assert "M src/agent_log.c" in out and "src/contrib1.c" not in out, out

    # a conflicting PR: refused whole, nothing written; --skip records it and the next release restores dev's line
    w.router("dev edits conflict.c", {"src/conflict.c": "a\nDEV\nc\nd\n"})
    agent.resume(1)
    c2 = w.contribute("Edit conflict", {"src/conflict.c": "a\nCONTRIB-2\nc\nd\n"})
    before = w.git(w.cache, "rev-parse", "-q", "--verify", "refs/psxdecomp/import", check=False)
    rc, out = w.tool("import")
    assert rc == 1 and "conflict" in out.lower() and "nothing written" in out, out
    assert w.git(w.cache, "rev-parse", "-q", "--verify", "refs/psxdecomp/import", check=False) == before
    rc, out = w.tool("release", "--summary", "x")
    assert rc == 1 and c2[:10] in out, out                                            # sync by commit
    agent.pause()
    w.importer("--skip", c2[:10])
    assert w.landed()
    assert "Import-Skipped" in w.git(d, "log", "-1", "--format=%B")
    r3, out = w.ship("third")
    assert "M src/conflict.c" in out and "DEV" in w.git(w.pub, "show", "main:src/conflict.c")

    # [public].keyed: a contributor's carve row and the agents' rows, appended in one import window, merge by key
    agent.resume(1)
    carve = w.git(w.pub, "show", "main:src/units.tsv", strip=False) + "contrib\t0x80010000\tKEYED-C\n"
    w.contribute("Carve 0x80010000", {"src/units.tsv": carve})
    agent.resume(2)
    agent.pause()
    ours = w.git(d, "show", "HEAD:src/units.tsv", strip=False)
    assert ours.count("\nagent\t") > carve.count("\nagent\t"), "the agents appended since the release"
    assert "IMPORT ready" in w.importer()
    assert w.landed()
    assert w.git(d, "show", "HEAD:src/units.tsv", strip=False) == ours + "contrib\t0x80010000\tKEYED-C\n"

    # a PR merged while a release PR is open: Update branch, squash; the release is still recognized
    agent.resume(2)
    agent.pause()
    br, _, _ = w.release("fourth")
    c3 = w.contribute("Add contrib3", {"src/contrib3.c": "/* CONTRIB-3 */\n"})
    w.update_branch(br)
    r4 = w.merge_release(br, "fourth")
    assert "CONTRIB-3" in w.git(w.pub, "show", "main:src/contrib3.c")
    rc, out = w.tool("release", "--summary", "x")
    assert rc == 1 and c3[:10] in out and r4[:10] not in out, out
    w.importer()
    assert w.landed()

    # a hotfix straight on public main is a contributor commit like any other
    h = w.direct({"CONTRIBUTING.md": (d / "CONTRIBUTING.md").read_text() + "\nCONTRIB-H\n"}, "Fix a typo")
    rc, out = w.tool("import")
    assert rc == 1 and "CONTRIBUTING.md: a governance path" in out, out
    w.importer("--accept-governance")
    assert w.landed() and "CONTRIB-H" in (d / "CONTRIBUTING.md").read_text()
    assert "Imported-From: %s" % h in w.git(d, "log", "-1", "--format=%B")

    # the Revert button on a release: import refuses it; skipped, the next release restores the files
    rv = w.revert(r4)
    rc, out = w.tool("import")
    assert rc == 1 and "revert" in out.lower(), out
    w.importer("--skip", rv[:10])
    assert w.landed()
    agent.resume(1)
    agent.pause()
    w.ship("fifth")
    assert w.tree(w.pub, "main")["src/agent_log.c"] == w.tree(d, "HEAD")["src/agent_log.c"]

    # the list shrinks (deleted on public, no --ack-new) and grows (--ack-new)
    lst = (d / "config/public-paths.txt").read_text()
    w.router("cookbook stays private", {"config/public-paths.txt": lst.replace("cookbook/\n", "")})
    rc, out = w.tool("release", "--summary", "sixth")
    assert rc == 1 and "README links" in out and "cookbook/INDEX.md" in out, out    # a link left the list
    readme = (d / "README.md").read_text()
    readme = re.sub(r"\| `cookbook/` \|[^\n]*\n", "", readme)
    readme = re.sub(r"The \[cookbook\]\(cookbook/INDEX.md\)[^\n]*\n", "", readme)
    w.router("README: the cookbook is private", {"README.md": readme})
    _, out = w.ship("sixth")
    assert "D cookbook/INDEX.md" in out and not any(p.startswith("cookbook/") for p in w.tree(w.pub, "main"))
    w.router("publish the wave playbook", {"config/public-paths.txt": lst.replace("cookbook/\n", "")
                                           + "docs/wave-playbook.md\n"})
    rc, out = w.tool("release", "--summary", "seventh")
    assert rc == 1 and "--ack-new" in out, out
    w.ship("seventh")
    assert "docs/wave-playbook.md" in w.tree(w.pub, "main")

    # renames both ways; a mode change both ways (plumbing modes, whatever core.filemode says)
    def mv_and_chmod(wc):
        w.git(wc, "mv", "src/contrib1.c", "src/contrib_renamed.c")
        os.chmod(wc / "src/run.sh", 0o755)                    # core.filemode=true: add -A reads the disk mode
        w.git(wc, "update-index", "--chmod=+x", "src/run.sh")  # core.filemode=false: only the index carries it
    w.contribute("Rename contrib1, run.sh executable", mut=mv_and_chmod)
    w.importer()
    assert w.landed()
    t = w.tree(d, "HEAD")
    assert "src/contrib_renamed.c" in t and "src/contrib1.c" not in t and t["src/run.sh"][0] == "100755"
    w.git(d, "mv", "src/conflict.c", "src/conflict2.c")
    os.chmod(d / "src/pulled/fn_1.c", 0o755)
    w.git(d, "update-index", "--chmod=+x", "src/pulled/fn_1.c")
    w.git(d, "commit", "-qm", "router: rename conflict.c; fn_1.c executable")
    _, out = w.ship("eighth")
    assert "D src/conflict.c" in out and "A src/conflict2.c" in out, out
    assert w.tree(w.pub, "main")["src/pulled/fn_1.c"][0] == "100755"

    # governance and denied paths from a contributor
    w.contribute("Tweak the Makefile", {"Makefile": (d / "Makefile").read_text() + "# CONTRIB-G\n"})
    rc, out = w.tool("import")
    assert rc == 1 and "--accept-governance" in out, out
    w.importer("--accept-governance")
    assert w.landed()
    bad = w.contribute("Add agent notes", {"CLAUDE.md": "CONTRIB-D\n"})
    rc, out = w.tool("import")
    assert rc == 1 and "CLAUDE.md" in out, out
    w.importer("--skip", bad[:10])
    assert w.landed() and "CONTRIB-D" not in (d / "CLAUDE.md").read_text()

    # the end state converges: one more release, then nothing to release and nothing to import
    agent.resume(2)
    agent.pause()
    w.ship("ninth")
    rc, out = w.tool("release", "--summary", "x")
    assert rc == 0 and "nothing to release" in out, out
    assert "nothing to import" in w.importer()

    # the pre-push hook through real pushes: dev goes to its own remote, never to public, never rewritten
    assert w.tool("hook")[0] == 1 and w.tool("hook", "--install")[0] == 0 and w.tool("hook")[0] == 0
    devremote = w.root / "dev-remote.git"
    w.git(w.root, "init", "-q", "--bare", devremote)
    w.git(d, "remote", "add", "backup", devremote)

    def push(*args, agent=False):
        env = {"CLAUDECODE": "1"} if agent else None
        r = subprocess.run(["git", "-C", str(d), "push", "-q"] + [str(a) for a in args], capture_output=True,
                           text=True, env=dict(w.env, **(env or {})))
        return r.returncode, r.stdout + r.stderr
    assert push("backup", "main")[0] == 0
    rc, out = push(w.pub, "main:refs/heads/dev-history")
    assert rc and "public repository" in out, out
    rc, out = push("--force", "backup", "main~1:main")
    assert rc and "force-push" in out, out
    rc, out = push("backup", ":main")
    assert rc and "deleting" in out, out
    rc, out = push("backup", "main", agent=True)
    assert rc and "CLAUDECODE" in out, out
    assert w.git(devremote, "rev-parse", "main") == w.git(d, "rev-parse", "main")
    assert "dev-history" not in w.git(w.pub, "for-each-ref")

    # a push from a linked worktree (dc2's checkout is one): git exports GIT_DIR to the hook, and the gate's commands
    # in its temporary tree must not reach the worktree's index or the repository's config
    wt = w.root / "dev-wt"
    w.git(d, "worktree", "add", "-q", "-b", "wt", wt)
    w.git(wt, "commit", "-q", "--allow-empty", "-m", "router: from a linked worktree")
    r = subprocess.run(["git", "-C", str(wt), "push", "-q", "backup", "wt:main"], capture_output=True, text=True,
                       env=w.env)
    assert r.returncode == 0 and "PRE-PUSH" in r.stdout + r.stderr, r.stdout + r.stderr
    assert w.git(devremote, "rev-parse", "main") == w.git(wt, "rev-parse", "HEAD")
    assert w.git(d, "config", "core.bare") == "false"
    for repo in (d, wt):
        assert sorted(w.git(repo, "ls-files").splitlines()) == sorted(w.tree(repo, "HEAD")), repo
    w.git(d, "worktree", "remove", "--force", wt)

    # the phase-end push through the gate, then ship end to end: origin (-dev) is a local bare repository for pushes,
    # GitHub a fake gh on PATH that squash-merges into the bare public repository
    origin = w.root / "origin.git"
    w.git(w.root, "init", "-q", "--bare", origin)
    w.git(d, "config", "url.%s.pushInsteadOf" % origin, "https://github.com/example/homebrew-fixture-dev.git")
    fake = w.root / "bin"
    fake.mkdir()
    for name, text in (("gh", FAKE_GH), ("docker", FAKE_DOCKER)):
        (fake / name).write_text(text)
        (fake / name).chmod(0o755)
    w.env.update(PATH=str(fake) + os.pathsep + w.env["PATH"], FAKE_GH_STATE=str(w.root / "gh.json"),
                 FAKE_GH_PUB=str(w.pub), FAKE_GH_REPO="example/homebrew-fixture",
                 FAKE_GH_DEV="example/homebrew-fixture-dev",
                 FAKE_GH_CHECKS=json.dumps(["build PSXD_000.01", "public-clean audit (no game bytes)"]))
    agent.resume(1)
    agent.pause()
    rc, out = w.tool("ship", "--summary", "tenth", "--ack-new")
    assert rc == 1 and "push first" in out, out                                       # -dev lacks the commit
    lst = w.git(d, "show", "HEAD:config/public-paths.txt", strip=False) + "CLAUDE.md\n"
    idx = {"GIT_INDEX_FILE": str(w.root / "planted.index")}
    w.git(d, "read-tree", "HEAD", env=idx)
    blob = subprocess.run(["git", "-C", str(d), "hash-object", "-w", "--stdin"], input=lst, capture_output=True,
                          text=True, env=w.env).stdout.strip()
    w.git(d, "update-index", "--cacheinfo", "100644,%s,config/public-paths.txt" % blob, env=idx)
    planted = w.git(d, "commit-tree", w.git(d, "write-tree", env=idx), "-p", "HEAD", "-m", "plant CLAUDE.md")
    rc, out = push("origin", "%s:refs/heads/main" % planted)
    assert rc and "PRE-PUSH FAIL" in out and "CLAUDE.md" in out, out                  # the gate blocks the leak
    assert not w.git(origin, "for-each-ref")
    rc, out = push("origin", "main")
    assert rc == 0 and "PRE-PUSH WARN" in out and "new public path" in out, out       # the agents' new files
    rc, out = w.tool("ship", "--summary", "tenth", agent=True)
    assert rc == 1 and "CLAUDECODE" in out, out
    refs = w.git(w.pub, "for-each-ref")
    rc, out = w.tool("ship", "--summary", "tenth", "--ack-new", "--dry-run")
    assert rc == 0 and "SHIP ci      OK CI-SIM OK .github/workflows/no-rom.yml on the projection" in out, out
    assert "would push" in out and w.git(w.pub, "for-each-ref") == refs, out
    rc, out = w.tool("ship", "--summary", "tenth", "--ack-new")
    head = w.git(d, "rev-parse", "HEAD")
    assert rc == 0 and "SHIP OK" in out and "SHIP merge   OK" in out, out
    msg = w.git(w.pub, "log", "-1", "--format=%B")
    assert msg.startswith("Release: tenth (#101)") and "Release-Of: %s" % head in msg, msg
    assert w.tree(w.pub, "main")["src/agent_log.c"] == w.tree(d, "HEAD")["src/agent_log.c"]
    ledger = (d / ".git/psxdecomp/ships.tsv").read_text().splitlines()
    assert ledger[1:] and ledger[-1].split("\t")[1:3] == [head, w.git(w.pub, "rev-parse", "main")], ledger
    rc, out = w.tool("ship", "--summary", "tenth")
    assert rc == 0 and "already released" in out and "SHIP OK" in out, out
    assert (d / ".git/psxdecomp/ships.tsv").read_text().splitlines() == ledger


def _blockers(w: World):
    """Each land blocker of the land predicate, set up and undone (the agents are paused)."""
    d = w.dev

    def inbox():
        f = d / "phase-ends/current/INBOX.md"
        old = f.read_text() if f.exists() else None
        f.write_text((old or "") + "\n- a pending note\n")
        return lambda: f.write_text(old) if old is not None else f.unlink()

    def review():
        f = d / "phase-ends/current/REVIEW.md"
        f.write_text("x\n")
        return f.unlink

    def flock():
        lock = d / ".run/gate/apply.lock"
        fd = open(lock, "w")
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd.close

    def warmer():
        f = d / ".run/warmer/s1.pid"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("%d\n" % os.getpid())
        return f.unlink

    def dirty():
        f = d / "src/agent_log.c"
        old = f.read_bytes()
        f.write_bytes(old + b"/* pulled back, not committed */\n")
        return lambda: f.write_bytes(old)

    return [("INBOX", inbox, "INBOX.md has a pending bullet"), ("REVIEW", review, "REVIEW.md exists"),
            ("gate lock", flock, "flock held"), ("warmer", warmer, "warmer s1 is alive"),
            ("dirty", dirty, "uncommitted changes")]


def _invariants(w: World, agent: Agent):
    d = w.dev
    assert agent.n >= 15, agent.n
    assert not w.git(d, "rev-list", "--merges", "main"), "first-parent history is linear"
    pub_shas = set(w.git(w.pub, "rev-list", "--first-parent", "main").split())
    log = w.git(d, "log", "--format=%H%x1f%an%x1f%s%x1f%(trailers:key=Imported-From,valueonly)%x1e", "main",
                strip=False)
    agent_commits = imports = 0
    for rec in filter(str.strip, log.split("\x1e")):
        sha, author, subj, frm = [x.strip() for x in rec.split("\x1f")]
        if re.match(r"T\d+: ", subj):
            agent_commits += 1
            paths = w.git(d, "show", "--format=", "--name-only", sha).split()
            assert all(p.startswith(AGENT_PATHS) or p == "src/agent_log.c" for p in paths), (subj, paths)
            assert "CONTRIB-" not in w.git(d, "show", "--format=", sha), subj
        if frm:
            imports += 1
            assert frm in pub_shas and subj.startswith("Import "), subj
    assert agent_commits == agent.n and imports == 9, (agent_commits, imports)
    for line in w.git(d, "reflog", "--format=%gs", "refs/heads/main").splitlines():
        assert line.startswith(("commit", "merge ", "clone")), line            # import and release never move dev
    private = set()
    for path in ("CLAUDE.md", "PROJECT_CONTEXT.md", "HOW_WE_WORK.md", "phase-ends", "docs/ops", ".claude", "rules"):
        out = w.git(d, "log", "--format=", "--raw", "--no-abbrev", "main", "--", path)
        private |= {l.split()[3] for l in out.splitlines() if l.startswith(":")}
    blobs = set(w.git(w.pub, "rev-list", "--objects", "--all").split())
    leaked = private & blobs - {"0" * 40, "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"}
    assert not leaked, "dev-private blobs on public: %s" % sorted(leaked)[:5]
