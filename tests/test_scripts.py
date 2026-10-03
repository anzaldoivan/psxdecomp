"""Every script's --self-test (each carries its own negative controls)."""
import subprocess

import pytest

from conftest import PY, ROOT, run


@pytest.mark.parametrize("script", ["answers", "fetch_refs", "identify", "preflight", "doctor", "upgrade", "install",
                                    "decompdev", "resume_hint"])
def test_self_test(script):
    r = run([PY, ROOT / "scripts" / ("%s.py" % script), "--self-test"], check=False)
    assert r.returncode == 0 and "SELF-TEST OK" in r.stdout, r.stdout + r.stderr


def test_launcher_runs_a_script():
    r = run([ROOT / "scripts" / "psxd", "fetch_refs", "--lint", "--refs", ROOT / "profiles/psx/refs.toml"])
    assert "REFS LINT OK" in r.stdout


def test_fixture_disc_is_deterministic(tmp_path):
    for d in ("a", "b"):
        run([PY, ROOT / "fixtures/homebrew-psx/make_disc.py", tmp_path / d])
    for f in ("HOMEBREW.cue", "HOMEBREW (Track 1).bin", "hello.exe"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()


def test_answers_n64_refused_installs_nothing(tmp_path):
    r = run([PY, ROOT / "scripts/install.py", "answers", "--answers", "fixture:n64", "--target", tmp_path], check=False)
    assert r.returncode == 1 and "not yet supported" in r.stdout
    assert list(tmp_path.iterdir()) == []


def test_ab_score_self_test():
    """The AGENTS.md A/B scorer (tools/, not installed): good and bad canned answers, the +20% cost rule."""
    r = run([PY, ROOT / "tools/ab_score.py", "--self-test"], check=False)
    assert r.returncode == 0 and "SELF-TEST OK" in r.stdout, r.stdout + r.stderr


def test_resume_hook(tmp_path):
    """hooks/hooks.json runs resume_hint at SessionStart: silent without a bootstrap, the restart line at NEXT S7."""
    import json
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["SessionStart"][0]["hooks"][0]
    assert hooks["type"] == "command" and hooks["command"].endswith("scripts/psxd\" resume_hint")
    feed = lambda agent: json.dumps({"cwd": str(tmp_path), "agent_type": agent})  # noqa: E731
    r = subprocess.run([str(ROOT / "scripts/psxd"), "resume_hint"], input=feed(None), capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""
    for sid in ("S0", "S1", "S2", "S3", "S4", "S5", "S6"):
        run([PY, ROOT / "scripts/install.py", "mark", sid, "--target", tmp_path])
    r = subprocess.run([str(ROOT / "scripts/psxd"), "resume_hint"], input=feed(None), capture_output=True, text=True)
    out = json.loads(r.stdout)
    assert "`claude --agent plain`" in out["systemMessage"] and "`/psxdecomp:new --resume`" in out["systemMessage"]
    r = subprocess.run([str(ROOT / "scripts/psxd"), "resume_hint"], input="not json", capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""                        # a bad payload: no hint, never a failure


def test_answers_policy_is_the_ai_policy():
    import common
    r = run([PY, ROOT / "scripts/answers.py", "policy"])
    assert r.stdout.strip() == common.AI_POLICY
