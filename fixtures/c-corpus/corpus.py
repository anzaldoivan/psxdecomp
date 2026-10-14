#!/usr/bin/env python3
"""corpus.py: tier 5a, inside the corpus image. Our own small C functions as a compile-and-compare ground truth.

  corpus.py check [ID ...]            every truth matches itself, every mutant fails, every fake twin matches and is
                                      flagged, no truth is flagged, and every trial case loses its spare pin and keeps
                                      the pin it needs; ends `CORPUS OK ...` (exit 0) or `CORPUS FAIL` (1)
  corpus.py list                      one line per truth: id, class, function, twins
  corpus.py pack ID DIR [--compiler]  what a drafter may see, written to DIR: target.json, target.s, ctx.h, common.h
  corpus.py --self-test               the mutation rule, on text (no compiler needed)

truth/<id>/truth.c   one function. Its first lines: `// class: <class>`, `// func: <name>`, `// canary: <token>`.
truth/<id>/ctx.h     the declarations a drafter is given. hidden.h (optional): types the drafter is not given.
truth/<id>/twin.<kind>.c   a fake twin: the same bytes through a lint kind (register-pin, goto, offset-cast,
                           struct-def), or the same masked words through another symbol (symbol, abs-address).
                           `// compilers: gcc2.95.2` on its first lines limits it to that compiler.
trial/<id>/pinned.c   one function that matches itself with two register pins. `// needs: <crutch>` names the pin
                      the match needs, `// spare: <crutch>` the pin it does not. The trial tool
                      (scripts/trial.py, with probe.py as its probe) must drop the spare one, and keep and mark the
                      needed one.
Targets are built here from truth.c and pinned.c at test time; no target is stored. stdlib only; probe.py and lint.py
beside it, and scripts/trial.py of this repository (with scripts/floor.py beside it) for the trial cases.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lint  # noqa: E402
import probe  # noqa: E402

TRUTH = os.path.join(HERE, "truth")
TRIAL = os.path.join(HERE, "trial")
TRIAL_PY = os.path.normpath(os.path.join(HERE, "..", "..", "scripts", "trial.py"))
INC = os.path.join(HERE, "include")
CLASSES = ("struct-fields", "struct-absent", "signedness", "loops", "switch", "globals", "divmul", "calls", "odd")
WORDS = (8, 40)                     # a truth's size under the first compiler, in words
RELOC_TWINS = ("symbol", "abs-address")   # twins whose words match and whose relocations do not
META = re.compile(r"^// (class|func|canary|compilers|twin|trial|needs|spare): *(.+?) *$", re.M)


def meta(path):
    with open(path) as f:
        text = f.read()
    return dict(META.findall(text.split("#include", 1)[0])), text


def truths(only=()):
    out = []
    for tid in sorted(os.listdir(TRUTH)):
        d = os.path.join(TRUTH, tid)
        if os.path.isfile(os.path.join(d, "truth.c")) and (not only or tid in only):
            m, text = meta(os.path.join(d, "truth.c"))
            twins = sorted(x for x in os.listdir(d) if re.fullmatch(r"twin\.[\w-]+\.c", x))
            out.append({"id": tid, "dir": d, "meta": m, "text": text, "twins": twins})
    return out


MUTATIONS = (  # (name, pattern, replacement): the first that changes the body and still compiles is the mutant
    ("constant+1", re.compile(r"(?<![\w.\[])(0[xX][0-9A-Fa-f]+|\d+)(?![\w.\]])"),
     lambda m: str(int(m.group(1), 0) + 1)),
    ("plus->minus", re.compile(r" \+ "), lambda m: " - "),
    ("less->less-equal", re.compile(r" < "), lambda m: " <= "),
    ("and->or", re.compile(r" & "), lambda m: " | "),
)


def mutants(text, func):
    """[(name, mutated text)]: each rule applied once, at its first hit inside the function's body."""
    m = re.search(r"\b%s\s*\([^;{]*\)\s*\{" % re.escape(func), text)
    if not m:
        return []
    head, body = text[: m.end()], text[m.end():]
    out = []
    for name, rx, rep in MUTATIONS:
        new, n = rx.subn(rep, body, count=1)
        if n and new != body:
            out.append((name, head + new))
    return out


def check_one(t, errors):
    tid, m, d = t["id"], t["meta"], t["dir"]
    func = m.get("func", "")
    stats = {"mutants": 0, "twins": 0}

    def bad(msg):
        errors.append("%s: %s" % (tid, msg))
    if m.get("class") not in CLASSES or not re.fullmatch(r"func_[0-9A-F]{8}", func) or not m.get("canary"):
        bad("needs `// class:` (one of %s), `// func: func_<8 hex>` and `// canary:` lines" % ", ".join(CLASSES))
        return stats
    if lint.findings(t["text"]):
        bad("the truth is flagged by the lint: %s" % lint.findings(t["text"])[0][:2])
    ctx = open(os.path.join(d, "ctx.h")).read()
    if m["canary"] in ctx or re.search(r"\b%s\s*\([^;{]*\)\s*\{" % func, ctx):
        bad("ctx.h holds the canary or the function's body")
    incs = (d, INC)
    with tempfile.TemporaryDirectory() as tmp:
        for ci, comp in enumerate(sorted(probe.COMPILERS, reverse=True)):       # gcc2.95.2 first: it sets the size
            obj = os.path.join(tmp, "t.o")
            err = probe.build(os.path.join(d, "truth.c"), obj, comp, incs)
            if err:
                bad("%s: the truth does not compile: %s" % (comp, err.strip().splitlines()[-1][:160]))
                continue
            tgt = probe.target_of(obj, func, comp)
            n = len(tgt["words"])
            if ci == 0 and not WORDS[0] <= n <= WORDS[1]:
                bad("%s: %d words, outside %d..%d" % (comp, n, *WORDS))
            r = probe.check(os.path.join(d, "truth.c"), func, tgt, incs=incs)
            if not r.get("match"):
                bad("%s: the truth does not match itself: %s" % (comp, r))
            compiled = 0
            for name, text in mutants(t["text"], func):
                src = os.path.join(tmp, "mutant.c")
                with open(src, "w") as f:
                    f.write(text)
                r = probe.check(src, func, tgt, incs=incs)
                if "nocompile" in r:
                    continue
                compiled += 1
                if r["match"]:
                    bad("%s: the mutant `%s` still matches" % (comp, name))
            if not compiled:
                bad("%s: no mutation rule gives a compiling mutant" % comp)
            stats["mutants"] += compiled
            for twin in t["twins"]:
                tm, ttext = meta(os.path.join(d, twin))
                if comp not in tm.get("compilers", comp).replace(",", " ").split():
                    continue
                kind = twin.split(".")[1]
                r = probe.check(os.path.join(d, twin), func, tgt, incs=incs)
                # a twin reaches the same words; RELOC_TWINS do it through another symbol or none, which only the
                # relocation comparison sees
                if "nocompile" in r or not r["words_ok"] or (kind not in RELOC_TWINS and not r["match"]):
                    bad("%s: %s does not match: %s" % (comp, twin, {k: v for k, v in r.items() if k != "nocompile"} or "nocompile"))
                elif kind in RELOC_TWINS and (r["match"] or not r["relocs"]):
                    bad("%s: %s must pass the masked words and fail on relocations" % (comp, twin))
                if kind != "symbol" and kind not in [f[0] for f in lint.findings(ttext)]:
                    bad("%s is not flagged as %s by the lint" % (twin, kind))
                stats["twins"] += 1
    return stats


def trials(only=()):
    out = []
    for tid in sorted(os.listdir(TRIAL)) if os.path.isdir(TRIAL) else ():
        d = os.path.join(TRIAL, tid)
        if os.path.isfile(os.path.join(d, "pinned.c")) and (not only or tid in only):
            m, text = meta(os.path.join(d, "pinned.c"))
            out.append({"id": tid, "dir": d, "meta": m, "text": text})
    return out


def trial_module():
    """scripts/trial.py of this repository as a module (stdlib only, as this file). It loads scripts/floor.py beside it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("trial", TRIAL_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_trial(t, errors):
    """One trial case under each compiler: the trial tool with probe.py as its probe. The spare pin goes and
    the needed pin stays with a reason."""
    trial = trial_module()
    func, needs, spare = (t["meta"].get(k) for k in ("func", "needs", "spare"))

    def bad(msg):
        errors.append("%s: %s" % (t["id"], msg))

    run = lambda repo, *a: subprocess.run([sys.executable, TRIAL_PY, *a, "--repo", repo], capture_output=True, text=True)  # noqa: E731
    for comp in probe.COMPILERS:
        with tempfile.TemporaryDirectory() as tmp:
            obj, repo = os.path.join(tmp, "t.o"), os.path.join(tmp, "game")
            err = probe.build(os.path.join(t["dir"], "pinned.c"), obj, comp, (t["dir"], INC))
            if err:
                bad("%s: pinned.c does not compile: %s" % (comp, err.strip().splitlines()[-1:]))
                continue
            with open(os.path.join(tmp, "target.json"), "w") as f:
                json.dump(probe.target_of(obj, func, comp), f)
            os.makedirs(os.path.join(repo, "src"))
            os.makedirs(os.path.join(repo, "config"))
            src = os.path.join(repo, "src", "pinned.c")
            with open(src, "w") as f:
                f.write(t["text"])
            with open(os.path.join(repo, trial.floor.RECORD), "w") as f:
                f.write("[trial]\nprobe = '%s %s check {file} {func} --target %s --compiler %s -I %s -I %s'\n" % (
                    sys.executable, os.path.join(HERE, "probe.py"), os.path.join(tmp, "target.json"), comp, t["dir"], INC))
            r = run(repo, "src/pinned.c")
            with open(src) as f:
                text = f.read()
            left = [c["id"] for c in trial.crutches("src/pinned.c", text)]
            if r.returncode != 0 or "2 tried, 1 removed, 1 kept" not in r.stdout or left != [needs]:
                bad("%s: the trial left %s, not %s alone: %s" % (comp, left, needs, (r.stdout + r.stderr).strip().splitlines()[-2:]))
                continue
            if "// !FAKE: %s: " % needs not in text:
                bad("%s: no reason above the kept pin" % comp)
    return 1


def check(only):
    ts, errors = truths(only), []
    canaries = [t["meta"].get("canary") for t in ts]
    funcs = [t["meta"].get("func") for t in ts]
    for name, vals in (("canary", canaries), ("func", funcs)):
        dup = sorted({v for v in vals if v and vals.count(v) > 1})
        if dup:
            errors.append("duplicate %s: %s" % (name, ", ".join(dup)))
    tot = {"mutants": 0, "twins": 0}
    for t in ts:
        s = check_one(t, errors)
        tot = {k: tot[k] + s[k] for k in tot}
        print("CORPUS %s %s %s" % (t["id"], t["meta"].get("class"), "ok" if not any(e.startswith(t["id"] + ":") for e in errors) else "FAIL"),
              flush=True)
    cases = trials(only)
    for t in cases:
        check_trial(t, errors)
        print("CORPUS %s trial %s" % (t["id"], "ok" if not any(e.startswith(t["id"] + ":") for e in errors) else "FAIL"), flush=True)
    for e in errors:
        print("CORPUS FAIL %s" % e)
    if errors or not ts + cases:
        print("CORPUS FAIL (%d error(s), %d truths, %d trial case(s))" % (len(errors), len(ts), len(cases)))
        return 1
    print("CORPUS OK %d truths, %d mutants failed, %d twins matched and flagged, %d trial case(s) lost the spare pin and "
          "kept the needed one, %d compilers" % (len(ts), tot["mutants"], tot["twins"], len(cases), len(probe.COMPILERS)))
    return 0


def pack(tid, out, compiler):
    t = truths([tid])[0]
    func = t["meta"]["func"]
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        obj = os.path.join(tmp, "t.o")
        err = probe.build(os.path.join(t["dir"], "truth.c"), obj, compiler, (t["dir"], INC))
        if err:
            sys.exit("corpus: %s does not compile\n%s" % (tid, err))
        tgt = probe.target_of(obj, func, compiler)
        asm = subprocess.run(["mipsel-linux-gnu-objdump", "-d", "-r", "-z", "--no-show-raw-insn",
                              "--disassemble=" + func, obj], capture_output=True, text=True, check=True).stdout
    with open(os.path.join(out, "target.json"), "w") as f:
        json.dump(tgt, f, sort_keys=True)
    with open(os.path.join(out, "target.s"), "w") as f:
        f.write(asm[asm.index("<%s>:" % func) - 9:] if "<%s>:" % func in asm else asm)
    for src, dst in ((os.path.join(t["dir"], "ctx.h"), "ctx.h"), (os.path.join(INC, "common.h"), "common.h")):
        with open(src) as f, open(os.path.join(out, dst), "w") as g:
            g.write(f.read())
    print("PACK %s %s %d words" % (tid, func, len(tgt["words"])))


def self_test():
    text = "// func: func_80010000\ns32 g(s32 a) { return a + 9; }\ns32 func_80010000(s32 a, s32 b) {\n    if (a < 4) {\n        return a + b;\n    }\n    return b & 3;\n}\n"
    got = dict(mutants(text, "func_80010000"))
    assert sorted(got) == ["and->or", "constant+1", "less->less-equal", "plus->minus"], sorted(got)
    assert "a < 5" in got["constant+1"] and "a + 9" in got["constant+1"]      # only the named function's body changes
    assert "a - b" in got["plus->minus"] and "a <= 4" in got["less->less-equal"] and "b | 3" in got["and->or"]
    assert mutants("s32 other(void) { return 1; }", "func_80010000") == []
    m, _ = meta(__file__)
    assert m == {}
    cases = trials()
    assert cases, "no trial case"
    for t in cases:                                  # the case is what its first lines say: two pins of one function
        got = trial_module().crutches("src/pinned.c", t["text"])
        assert sorted(c["id"] for c in got) == sorted((t["meta"]["needs"], t["meta"]["spare"])), (t["id"], got)
        assert {c["func"] for c in got} == {t["meta"]["func"]} and all(c["reason"] is None for c in got), t["id"]
        assert {f[0] for f in lint.findings(t["text"])} == {"register-pin"}, t["id"]
    print("SELF-TEST OK")


def main():
    a = sys.argv[1:]
    if a == ["--self-test"]:
        return self_test()
    if a[:1] == ["check"]:
        return check(a[1:])
    if a[:1] == ["list"]:
        for t in truths():
            print("%s\t%s\t%s\t%s" % (t["id"], t["meta"].get("class"), t["meta"].get("func"), ",".join(t["twins"])))
        return 0
    if a[:1] == ["pack"] and len(a) >= 3:
        return pack(a[1], a[2], a[4] if a[3:4] == ["--compiler"] else "gcc2.95.2")
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
