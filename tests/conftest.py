"""Shared fixtures. Tier 1 needs the pinned PA3 (cloned from GitHub, or $PSXDECOMP_PA3_SOURCE) and the kit:
$PSXDECOMP_KIT, else compat.toml [kit].repo + sha cloned by common.resolve_kit (digest-checked). Without either, the
pipeline tests skip with that reason."""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))

GIT_ENV = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_CONFIG_GLOBAL": "/dev/null"}


def run(cmd, cwd=None, env=None, check=True):
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **GIT_ENV)
    if env:
        e.update(env)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=e, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError("%s -> rc %d\n%s%s" % (" ".join(map(str, cmd)), r.returncode, r.stdout[-3000:],
                                                     r.stderr[-2000:]))
    return r


@pytest.fixture(scope="session")
def kit():
    """The kit folder: $PSXDECOMP_KIT, else the published pin (compat.toml [kit].repo + sha); else tier 1 skips."""
    path = os.environ.get("PSXDECOMP_KIT")
    if path and os.path.isfile(os.path.join(path, "install.py")):
        return path
    import common
    if not common.compat()["kit"].get("repo"):
        pytest.skip("no kit: PSXDECOMP_KIT is not set and compat.toml [kit].repo is empty")
    try:
        found, _ = common.resolve_kit()
    except common.Fail as e:
        pytest.skip("pinned kit unavailable: %s" % e)
    os.environ["PSXDECOMP_KIT"] = str(found)
    return str(found)


@pytest.fixture(scope="session")
def toolchain(tmp_path_factory, kit):
    """A PA3 per-machine install in a throwaway config dir, the pinned PA3 clone, the kit, the fixture disc."""
    base = tmp_path_factory.mktemp("toolchain")
    env = {"PSXDECOMP_CACHE": str(base / "cache"), "PSXDECOMP_KIT": kit}
    if os.environ.get("PSXDECOMP_PA3_SOURCE"):
        env["PSXDECOMP_PA3_SOURCE"] = os.environ["PSXDECOMP_PA3_SOURCE"]
    import common
    os.environ.update(env)
    try:
        pkg, _ = common.resolve_pa3()
    except common.Fail as e:
        pytest.skip("pinned PA3 unavailable: %s" % e)
    cfg = base / "cfg"
    run([PY, pkg / "pa_install.py", "--root", "--yes", "--no-clone", "--config-dir", cfg, "--pa3-dir", cfg / "pa3",
         "--no-statusline"])
    run([PY, ROOT / "fixtures/homebrew-psx/make_disc.py", base / "disc"])
    return {"env": env, "cfg": cfg, "pkg": pkg, "dump": base / "disc" / "HOMEBREW.cue", "base": base}


def bootstrap(tc, target, *extra, check=True):
    return run([PY, ROOT / "scripts/install.py", "run", "--target", target, "--answers",
                ROOT / "fixtures/answers.psx.txt", "--dump", tc["dump"], "--config-dir", tc["cfg"], "--pa3-dir",
                tc["cfg"] / "pa3", "--intake-fixture", "--no-fetch", *extra], env=tc["env"], check=check)


def tree(repo):
    return run(["git", "-C", repo, "ls-files"]).stdout.splitlines()
