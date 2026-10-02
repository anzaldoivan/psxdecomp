"""Every script's --self-test (each carries its own negative controls)."""
import pytest

from conftest import PY, ROOT, run


@pytest.mark.parametrize("script", ["answers", "fetch_refs", "identify", "preflight", "doctor", "upgrade", "install"])
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
