"""The scenarios of the floor tool (scripts/floor.py, tools/psxd_floor.py in a game). The tool keeps a short smoke
test. Each scenario is one test: the first check that fails names itself in the assertion."""
import contextlib
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import pytest

import doctor
import floor


def self_test_debt(check) -> None:
    check("a clean file has no debt", floor.file_debt("src/a.c", floor.C_CLEAN) == {}, floor.file_debt("src/a.c", floor.C_CLEAN))
    for kind, (text, want) in floor.C_DEBT.items():
        check("one planted file: " + kind, floor.file_debt("src/a.c", text) == want, floor.file_debt("src/a.c", text))
    check("a struct in include/ is no debt", floor.file_debt("include/a.h", floor.C_DEBT["struct"][0]) == {})
    check("the address header may hold addresses", floor.file_debt("include/addr.h", floor.C_DEBT["address"][0]) == {})
    plumbing = '__asm__(".include \\"macro.inc\\"\\n");\nstatic inline void Nop(void) {\n    __asm__("nop");\n}\n'
    check("a file-scope asm statement of directives is no debt, an instruction in a function is", floor.file_debt("include/common.h", plumbing) == {"asm": 1}
          and floor.file_debt("src/a.c", plumbing) == {"asm": 1}, floor.file_debt("include/common.h", plumbing))
    shared = floor._macros(floor.strip("#define HP(p) (*(s16 *)((u8 *)(p) + 0x10))\n"))
    check("a header's offset macro counts at each use", floor.file_debt("src/a.c", "s32 Walk(void *p) {\n    return HP(p);\n}\n", shared)
          == {"offset": 1})
    old = floor.parse_baseline("mode macro count\n2 macro src/a.c\n1 flag src/a.c\nraise flag 1 2026-01-02 r\n")
    check("the baseline: the lines of a retired kind are dropped", (old.modes, old.totals, old.raises, old.other) == ({}, {}, [], []))
    bl = floor.parse_baseline("# top\nmode goto down\nmode pin count\nmode shift down\n3 shift src/a.c\n"
                        "raise goto 2 2026-01-02 the first wave\nskip src/vendor/\n1 goto src/a.c\n# a note below a row\n")
    check("the baseline: its lines, and the lines of a kind this tool does not know", bl.version == 2
          and bl.head == ["# top", "# a note below a row"] and bl.policy("goto") == "down"
          and bl.policy("pin") == "count" and bl.other == ["mode shift down", "3 shift src/a.c"]
          and bl.raises == [("goto", 2, "2026-01-02", "the first wave")] and bl.lacks()[:2] == ["pin-unmarked", "goto-unmarked"], vars(bl))
    check("the baseline is written as totals: a row of a file adds to the total of its kind", bl.by_file and floor.baseline_text(bl)
          == "# top\n# a note below a row\nskip src/vendor/\nmode pin count\nmode goto down\nmode shift down\n3 shift src/a.c\n"
          "raise goto 2 2026-01-02 the first wave\n1 goto\n", floor.baseline_text(bl))
    two = floor.parse_baseline("2 goto src/a.c\n3 goto src/b.c\n4 pin\n")
    check("the baseline: rows of files are summed, a total is read as it is", (two.totals, two.by_file) == ({"goto": 5, "pin": 4}, True)
          and floor.parse_baseline(floor.baseline_text(two)).totals == two.totals and not floor.parse_baseline(floor.baseline_text(two)).by_file, vars(two))
    early = floor.parse_baseline("mode offset admit-new\nbudget pin 30 base 4 10 20\nmode asm down\n")
    check("the baseline: the lines of an unreleased build are read as `count`", (early.policy("offset"), early.policy("pin"),
          early.policy("asm")) == ("count", "count", "down"), early.modes)
    for name, text, want in (("two rows of one pair", "1 goto src/a.c\n1 goto src/a.c\n", "has two rows"),
                             ("two rows of one kind", "1 goto\n2 goto\n", "goto has two rows"),
                             ("a total beside the rows of its kind", "1 goto src/a.c\n1 goto\n", "goto has two rows"),
                             ("two policy lines of one kind", "mode goto down\nmode goto count\n", "two policy lines"),
                             ("a second mode line of version 1", "mode down\nmode admit\n", "a second `mode` line"),
                             ("the two versions in one file", "mode admit\nmode goto down\n", "of version 1 beside"),
                             ("a count too long to be a number", "%s goto src/a.c\n" % ("9" * 5000), ":1: not `<count> <kind>`"),
                             ("a line that is no line", "mode sideways\n", ":1: not `<count> <kind>`")):
        try:
            floor.parse_baseline(text)
            check("the baseline: %s is refused" % name, False)
        except floor.Fail as e:
            check("the baseline: %s is refused" % name, want in str(e), str(e))
    with tempfile.TemporaryDirectory() as td:
        repo = floor._repo(td)
        (repo / "src").mkdir()
        (repo / "include").mkdir()
        (repo / "config").mkdir()
        (repo / "src" / "clean.c").write_text(floor.C_CLEAN)
        (repo / "src" / "walk.c").write_text(floor.C_DEBT["goto"][0])
        (repo / "src" / "stubs.c").write_text('INCLUDE_ASM("asm/nonmatchings/a", Run);\nINCLUDE_ASM("asm/nonmatchings/a", Jump);\n')
        (repo / "src" / "boot.s").write_text("nop\n")
        (repo / "include" / "include_asm.h").write_text("#define INCLUDE_ASM(d, n) __asm__(\".include \\\"n\\\"\");\n")
        floor._git(repo, "add", "src", "include")
        run = lambda *a, **kw: floor._capture(floor.cmd_debt, repo, *a, **kw)  # noqa: E731
        judge = lambda base, head=None: floor.admission(repo, floor.Tree(repo, base), floor.Tree(repo, head))[0]  # noqa: E731
        walk, base_file = repo / "src" / "walk.c", repo / floor.BASELINE
        again = floor.C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;")
        rc, out = run()
        check("no baseline: the totals, and a failure", rc == 1 and "totals: goto 1, asm 1 " in out
              and "DEBT FAIL no config/debt-baseline.txt: `python3 tools/psxd_floor.py debt --recount` writes it" in out, out)
        rc, out = run(update=True)
        check("--update writes no first baseline", rc == 1 and not base_file.exists(), out)
        text = floor.first_baseline(repo)
        check("the first baseline: a policy line per kind and the rows; the stub macro's header is read, and holds no debt", text.startswith(
            "# config/debt-baseline.txt: ") and text.endswith(
            "mode pin count\nmode pin-unmarked down\nmode goto count\nmode goto-unmarked down\nmode barrier count\n"
            "mode barrier-unmarked down\nmode offset count\nmode address count\nmode cast count\nmode field count\n"
            "mode asm down\nmode gte count\nmode placeholder count\nmode placeholder-use count\n"
            "mode struct count\nmode extern count\nmode filename count\n1 goto\n1 asm\n"), text)
        rc, out = run(recount=True)
        check("--recount writes it", rc == 0 and base_file.read_text() == text and "DEBT RECOUNT written" in out
              and "DEBT INFO policy written: pin: count\n" in out, out)
        rc, out = run()
        check("an equal baseline passes", rc == 0 and "DEBT CHECK OK (0 rise(s), 0 stale row(s); down: pin-unmarked, goto-unmarked, "
              "barrier-unmarked, asm; count: pin, goto, barrier, offset, address, cast, field, gte, placeholder, "
              "placeholder-use, struct, extern, filename)" in out, out)
        floor._git(repo, "add", "config")
        floor._commit(repo, "the floor")
        # a kind in mode `count` is counted and shown: the rows follow the tree, and nothing is refused
        walk.write_text(again)
        rc, out = run()
        check("a rise fails the equality of rows and counts, and names the command", rc == 1
              and "DEBT FAIL rise goto: 2, its row is 1\n" in out
              and "debt --update`, then commit config/debt-baseline.txt" in out, out)
        check("a counted kind is never refused", not judge("HEAD"), judge("HEAD"))
        rc, out = run(update=True)
        check("--update writes the total of a counted kind", rc == 0 and "DEBT INFO goto: 1 -> 2\n" in out
              and "2 goto\n" in base_file.read_text() and run()[0] == 0, out)
        try:
            with open(os.devnull, "w") as null, contextlib.redirect_stderr(null):
                floor.main(["debt", "--update", "--admit", "--repo", str(repo)])
            check("--admit is no flag", False)
        except SystemExit as e:
            check("--admit is no flag: exit 2", e.code == 2, e.code)
        base_file.write_text(text)
        walk.write_text(floor.C_DEBT["goto"][0])
        # a `down` kind: the total of the tree never rises, wherever the construct stands and whatever the rows say
        unmarked = floor.C_DEBT["pin-unmarked"][0].replace("Walk", "Run")
        walk.write_text(floor.C_DEBT["goto"][0] + unmarked)
        base_file.write_text(text + "1 pin\n1 pin-unmarked\n")
        rc, out = run()
        check("a row written by hand is equal to the tree", rc == 0, out)
        rc, out = run(against="HEAD")
        check("and the change is refused all the same", rc == 1 and "DEBT FAIL debt: pin-unmarked is `down` and its total rose: "
              "0 -> 1 (src/walk.c 0 -> 1)\n" in out and "1 finding(s) against HEAD" in out, out)
        base_file.write_text(text)
        rc, out = run(update=True)
        check("--update refuses a rise of a `down` kind", rc == 1 and base_file.read_text() == text and "DEBT UPDATE refused" in out, out)
        (repo / "src" / "far.c").write_text(unmarked.replace("Run", "Far"))
        floor._git(repo, "add", "src/far.c")
        check("a rise in two files names both", [f[1] for f in judge("HEAD")] == [
            "pin-unmarked is `down` and its total rose: 0 -> 2 (src/far.c 0 -> 1, src/walk.c 0 -> 1)"], judge("HEAD"))
        walk.write_text(floor.C_DEBT["goto"][0] + floor.C_DEBT["pin"][0].replace("Walk", "Run"))
        check("a marked pin is counted, not refused", [f[1] for f in judge("HEAD")] == [
            "pin-unmarked is `down` and its total rose: 0 -> 1 (src/far.c 0 -> 1)"], judge("HEAD"))
        floor._git(repo, "rm", "-q", "-f", "--cached", "src/far.c")
        (repo / "src" / "far.c").unlink()
        check("with a reason on each pin the change passes", not judge("HEAD"), judge("HEAD"))
        # a `raise` line is the developer's
        walk.write_text(floor.C_DEBT["goto"][0] + unmarked)
        os.environ["CLAUDECODE"] = "1"
        rc, out = run(raise_=("pin-unmarked", "1"), reason="the trial is pending")
        check("--raise is refused in an agent session", rc == 1 and "the developer's act" in out and base_file.read_text() == text, out)
        del os.environ["CLAUDECODE"]
        rc, out = run(raise_=("pin-unmarked", "0"), reason="x")
        check("--raise needs a number above zero", rc == 1, out)
        rc, out = run(raise_=("pin-unmarked", "1"), reason="the trial\nis pending")
        raised = re.search(r"^raise pin-unmarked 1 \d{4}-\d\d-\d\d the trial is pending$", base_file.read_text(), re.M)
        check("--raise writes one dated line", rc == 0 and raised is not None, out)
        rc, out = run(update=True)
        check("--update takes what a `raise` line allows, and says so", rc == 0 and "DEBT INFO pin-unmarked is over by 1: the "
              "change's `raise` line(s) allow 1\n" in out and "DEBT INFO a new `raise` line: pin-unmarked 1 " in out, out)
        floor._git(repo, "add", "-u")
        floor._commit(repo, "a raise")
        walk.write_text(walk.read_text() + unmarked.replace("Run", "Jump"))
        check("a `raise` line admits one change, not the next", len(judge("HEAD")) == 1, judge("HEAD"))
        walk.write_text(floor.C_DEBT["goto"][0] + unmarked.replace("Run", "Jump").replace("s32 i", "s32 j"))
        check("one unmarked pin in the place of another: the total did not rise", not judge("HEAD"), judge("HEAD"))
        walk.write_text(floor.C_DEBT["goto"][0] + unmarked)
        # the policy that judges a change is the one it starts from
        mine = base_file.read_text()
        for name, text2, want in (
                ("a policy line taken out", mine.replace("mode pin-unmarked down\n", ""), "the policy line of pin-unmarked is gone (it was down)"),
                ("a weaker mode", mine.replace("mode pin-unmarked down", "mode pin-unmarked count"),
                 "pin-unmarked went from down to count: a mode only gets stronger"),
                ("a new skip line", mine + "skip src/\n", "a new `skip` line (src/)")):
            base_file.write_text(text2)
            got = judge("HEAD")
            check("policy: " + name, ("policy", want) in got, got)
        base_file.unlink()
        check("policy: a deleted baseline", judge("HEAD") == [("policy", "config/debt-baseline.txt is gone")], judge("HEAD"))
        base_file.write_text(mine.replace("mode offset count", "mode offset down"))
        check("policy: a stronger mode passes", not judge("HEAD"), judge("HEAD"))
        base_file.write_text(mine)
        rc, out = run(down="goto")
        check("--down switches one kind", rc == 0 and "mode goto down\n" in base_file.read_text()
              and "mode pin count" in base_file.read_text(), out)
        rc, out = run(down="all")
        check("--down switches every kind", rc == 0 and floor.parse_baseline(base_file.read_text()).summary() == "down: " + ", ".join(floor.KINDS), out)
        check("--down of a kind that is no kind", run(down="gotos")[0] == 1)
        base_file.write_text(mine)
        # a recount writes rows and policy lines; it admits nothing that a `down` kind refuses
        walk.write_text(walk.read_text() + unmarked.replace("Run", "Jump"))
        rc, out = run(recount=True)
        check("--recount admits no rise of a `down` kind", rc == 1 and "DEBT RECOUNT refused" in out and base_file.read_text() == mine, out)
        walk.write_text(again)
        base_file.write_text("mode admit\nskip include/include_asm.h\n1 asm src/boot.s\n# a note of the game\n")
        floor._git(repo, "add", "-A")
        floor._commit(repo, "the baseline of an older psxdecomp")
        rc, out = run()
        check("a version 1 baseline fails and names the command", rc == 1 and "is a version 1 file (`mode admit`): run "
              "`python3 tools/psxd_floor.py debt --recount`" in out, out)
        rc, out = run(recount=True)
        new = base_file.read_text()
        check("--recount makes it version 2 and keeps the game's own lines", rc == 0 and "# a note of the game\n" in new
              and "mode goto count\n" in new and "skip include/include_asm.h\n" in new and "mode admit\n" not in new
              and new.count("# ") == len(floor.BASELINE_HEAD) + 1 and run()[0] == 0, out + new)
        base_file.write_text(new.replace("mode goto count", "budget goto 12 base 1 2 11").replace("mode offset count", "mode offset admit-new")
                             .replace(floor.BASELINE_HEAD[3], "A policy line gives each kind its mode: `down` (never rises), `admit-new` (debt arrives only with a new function"))
        rc, out = run(recount=True)
        check("--recount writes the lines of an unreleased build as `count`, and the head of now", rc == 0 and base_file.read_text() == new, base_file.read_text())
        floor._git(repo, "add", "-A")
        floor._commit(repo, "version 2")
        # the two ends of a range decide: a body that leaves and comes back with more debt is counted, and not refused
        walk.write_text('INCLUDE_ASM("asm/nonmatchings/a", Walk);\n')
        run(update=True)
        floor._git(repo, "add", "-A")
        floor._commit(repo, "the body leaves")
        walk.write_text(again + unmarked)
        check("a `down` kind that rose over a range is refused at its ends", [f[1] for f in judge("HEAD~1")] == [
            "pin-unmarked is `down` and its total rose: 0 -> 1 (src/walk.c 0 -> 1)"], judge("HEAD~1"))
        walk.write_text(again)
        rc, out = run(update=True)
        floor._git(repo, "add", "-A")
        floor._commit(repo, "the body is back")
        check("a counted kind over a range passes", rc == 0 and not judge("HEAD~2", "HEAD"), out)
        # version 1 in `mode down`: every kind is `down`
        base_file.write_text("mode down\n2 goto src/walk.c\n1 asm src/boot.s\n")
        floor._git(repo, "add", "-A")
        floor._commit(repo, "an older baseline in mode down")
        rc, out = run(recount=True)
        check("--recount after `mode down`: every kind is `down`", rc == 0 and floor.parse_baseline(base_file.read_text()).summary()
              == "down: " + ", ".join(floor.KINDS), out)
        base_file.write_text("mode admit\n2 goto src/walk.c\n1 asm src/boot.s\n")
        check("policy: `mode down` of version 1 does not become `mode admit`", ("policy", "`mode down` became `mode admit`") in judge("HEAD"))
        base_file.write_text("mode down\n2 goto src/walk.c\n1 asm src/boot.s\n")
        # the public tree of a game in split mode holds the totals of the files it does not publish too
        run(recount=True)
        base_file.write_text(base_file.read_text() + "3 offset\n")
        rc, out = run()
        check("a total over the tree is stale", rc == 1 and "DEBT FAIL stale offset: 0, its row is 3" in out, out)
        (repo / floor.PUBLIC_PATHS).write_text("# the list\nsrc/\ninclude/\nconfig/\n")
        floor._git(repo, "add", floor.PUBLIC_PATHS)
        check("and not in a public tree, where the list names each file", run()[0] == 0, run()[1])
        (repo / floor.PUBLIC_PATHS).write_text("src/walk.c\nsrc/boot.s\ninclude/\nconfig/\n")
        check("a tree with a file that the list does not name is dev's: stale", run()[0] == 1)
        (repo / floor.PUBLIC_PATHS).write_text("src/\ninclude/\nconfig/\n")
        (repo / "CLAUDE.md").write_text("never public\n")
        floor._git(repo, "add", "CLAUDE.md")
        check("dev's tree that publishes all of src/ still holds a file that is never public: stale", run()[0] == 1)
        floor._git(repo, "rm", "-q", "-f", "--cached", "CLAUDE.md")
        (repo / "CLAUDE.md").unlink()
        floor._git(repo, "rm", "-q", "-f", "--cached", floor.PUBLIC_PATHS)
        (repo / floor.PUBLIC_PATHS).unlink()
        run(recount=True)
        walk.write_text(floor.C_CLEAN.replace("Player_Hp", "Walk"))
        rc, out = run()
        check("a stale row fails", rc == 1 and "DEBT FAIL stale goto: 0, its row is 2\n" in out, out)
        rc, out = run(down="goto")
        check("--down needs an equal baseline", rc == 1 and "not equal" in out, out)
        rc, out = run(update=True)
        check("--update lowers a row", rc == 0 and "DEBT INFO goto: 2 -> 0\n" in out and
              " goto\n" not in base_file.read_text(), out)
        (repo / "src" / "walk.c").write_text(floor.C_CLEAN)
        (repo / "src" / "untracked.c").write_text(floor.C_DEBT["goto"][0])        # never added: a count reads tracked files
        check("an untracked file under src/ is not counted", not any(p == "src/untracked.c" for _, p in floor.debt_counts(repo)))
        (repo / "src" / "boot.s").write_text("glabel boot\n    nop\n")
        (repo / "docs").mkdir()
        (repo / "docs" / "boot.md").write_text("# The boot code\n\nThe vendor wrote it in assembly.\n")
        floor._git(repo, "add", "docs")
        (repo / floor.ASM_EVIDENCE).write_text("\t".join(floor.ASM_COLUMNS) + "\nmain\tboot\tsrc/boot.s\thand-asm\tdocs/boot.md:3\t2026-01-02\tdeveloper\n")
        rc, out = run()
        check("an evidence row clears an assembly file", rc == 1 and "DEBT FAIL stale asm: 0, its row is 1" in out, out)
        (repo / floor.BASELINE).write_text("mode sideways\n")
        rc, out = run()
        check("a baseline line that is no row", rc == 1 and "config/debt-baseline.txt:1: not " in out, out)
        # the record's address header is read without tomllib; a run from a folder of the repository finds its root
        (repo / floor.RECORD).write_text('[psxdecomp]\nversion = "0.0.0"\n\n[debt]  # ours\naddress_header = "include/hw.h"\n')
        check("the record's address header", floor.address_header(repo) == "include/hw.h" and floor.address_header(repo / "src") == floor.ADDRESS_HEADER)
        (repo / floor.RECORD).unlink()
        (repo / floor.BASELINE).unlink()
        (repo / floor.BASELINE).write_text(floor.first_baseline(repo))
        cwd = os.getcwd()
        try:
            os.chdir(repo / "src")
            rc, out = floor._capture(floor.main, ["debt"])
        finally:
            os.chdir(cwd)
        check("a run from a folder of the repository reads the repository", rc == 0 and "DEBT CHECK OK (0 rise(s)" in out
              and not (repo / "src" / "config").exists(), out)
        # the ledgers
        (repo / floor.BASELINE).unlink()
        (repo / floor.ASM_EVIDENCE).unlink()
        rc, out = floor._capture(floor.cmd_names, repo)
        check("names: no ledger is not a failure", rc == 0 and out.count("NAMES INFO no config/") == 2, out)
        rc, out = floor._capture(floor.cmd_names, repo, init=True)
        check("names --init writes the two header lines", rc == 0 and (repo / floor.NAMES).read_text() == "\t".join(floor.NAME_COLUMNS) + "\n"
              and (repo / floor.ASM_EVIDENCE).read_text() == "\t".join(floor.ASM_COLUMNS) + "\n", out)
        row = "function\tmain\t\tfunc_80010000\tPlayer_Hp\taccepted\tstring:src/gone.c:4\tthe string it prints\n"
        (repo / floor.NAMES).write_text("\ufeff" + "\t".join(floor.NAME_COLUMNS) + "\n" + row.replace("\tthe string it prints", "\t"))
        rc, out = floor._capture(floor.cmd_names, repo)
        check("names: a row is the game's record: its evidence is not opened; a trimmed last cell and a BOM are read",
              rc == 0 and "config/names.tsv: 1 row(s)" in out and "NAMES OK (0 finding(s))" in out, out)
        (repo / floor.NAMES).write_text("\t".join(floor.NAME_COLUMNS) + "\n" + row + row.replace("\n", "\tmore\n"))
        rc, out = floor._capture(floor.cmd_names, repo)
        check("names: a row with more cells than the header fails", rc == 1 and "NAMES FAIL config/names.tsv: line 3: 9 cell(s), not 8" in out, out)
        (repo / floor.NAMES).write_text("\t".join(floor.NAME_COLUMNS) + "\n" + row)
        floor._git(repo, "add", "config")
        # an assembly row names one function of a C file, never the file
        two = 'void A(void) {\n    __asm__("nop");\n}\nvoid B(void) {\n    __asm__("nop");\n}\n'
        (repo / "src" / "two.c").write_text(two)
        floor._git(repo, "add", "src/two.c")
        asm_row = lambda sym, ev="docs/boot.md:3", who="developer": "\t".join(floor.ASM_COLUMNS) + "\nmain\t%s\tsrc/two.c\thand-asm\t%s\t2026-01-02\t%s\n" % (sym, ev, who)  # noqa: E731
        (repo / floor.ASM_EVIDENCE).write_text(asm_row("A"))
        check("an assembly row clears the function it names, and no other", floor._capture(floor.cmd_names, repo)[0] == 0
              and floor.debt_bodies(repo)["src/two.c"] == {"A": {}, "B": {"asm": 1}}, floor.debt_bodies(repo)["src/two.c"])
        for name, text, want in (("a row for a whole C file", asm_row(""), "src/two.c defines no function ''"),
                                 ("a row for a function that the file lacks", asm_row("C"), "src/two.c defines no function 'C'"),
                                 ("evidence that is no path and line", asm_row("A", "the vendor said so"), "'the vendor said so' is not `<path>:<line>`"),
                                 ("evidence in a file that the tree lacks", asm_row("A", "docs/gone.md:1"), "docs/gone.md is no file of this tree"),
                                 ("no verified_by", asm_row("A", who=""), "no verified_by: who read the evidence of A"),
                                 ("a label that the assembly file lacks", asm_row("start").replace("src/two.c", "src/boot.s"), "src/boot.s holds no label start")):
            (repo / floor.ASM_EVIDENCE).write_text(text)
            rc, out = floor._capture(floor.cmd_names, repo)
            check("names: an assembly row: " + name, rc == 1 and want in out, out)
        (repo / floor.ASM_EVIDENCE).write_text("\t".join(floor.ASM_COLUMNS_OLD) + "\nmain\tA\tsrc/two.c\thand-asm\tdocs/boot.md:3\t2026-01-02\n")
        rc, out = floor._capture(floor.cmd_names, repo)
        check("names: the header of psxdecomp 0.6.0 is read, and said", rc == 0 and "no `verified_by` column (/psxdecomp:upgrade adds it)" in out, out)
        (repo / "src" / "two.c").unlink()
        floor._git(repo, "rm", "-q", "--cached", "src/two.c")
        (repo / floor.ASM_EVIDENCE).write_text("\t".join(floor.ASM_COLUMNS) + "\n")
        row = "function\tmain\t\tfunc_80010000\tPlayer_Hp\taccepted\tstring:src/clean.c:4\tthe string it prints\n"
        (repo / floor.NAMES).write_text("\t".join(floor.NAME_COLUMNS) + "\n" + row.replace("accepted", "sure").replace("string:", "guess:"))
        rc, out = floor._capture(floor.cmd_names, repo)
        check("names: the cells of a row are not judged", rc == 0, out)
        (repo / floor.NAMES).write_text("\t".join(floor.NAME_COLUMNS) + "\n" + row)
        (repo / floor.ASM_EVIDENCE).write_text("\t".join(floor.ASM_COLUMNS) + "\nmain\tboot\tsrc/boot.s\tguess\tdocs/boot.md:3\tyesterday\tdeveloper\n")
        rc, out = floor._capture(floor.cmd_names, repo)
        check("names: an assembly row with a class that is no class and a date that is no date",
              rc == 1 and "class 'guess'" in out and "date 'yesterday'" in out, out)
        (repo / floor.ASM_EVIDENCE).write_text("\t".join(floor.ASM_COLUMNS) + "\n")
        (repo / floor.NAMES).write_text("kind\tname\n")
        check("names: a wrong header", floor._capture(floor.cmd_names, repo)[0] == 1)


C_BODIES = {
    "two plain bodies": ("s32 A(void *p) {\n    return *(s32 *)(p + 4);\n}\n\nvoid B(void) {\nx:\n    goto x; // !FAKE: the loop\n}\n",
                         {"A": {"offset": 1}, "B": {"goto": 1}}),
    "a K&R definition is file scope": ("s32 A(p)\nvoid *p;\n{\n    return *(s32 *)(p + 4);\n}\nvoid B(void) {\n}\n",
                                        {floor.SCOPE: {"offset": 1}, "B": {}}),
    "a definition by a macro is file scope": ("HANDLER(A) {\nx:\n    goto x; // !FAKE: the loop\n}\nvoid B(void) {\n}\n",
                                               {floor.SCOPE: {"goto": 1}, "B": {}}),
    "an #if with two heads is one body": (
        "#ifdef VERSION_JP\ns32 A(s32 a) {\n#else\ns32 A(void) {\n#endif\nx:\n"
        "    goto x; // !FAKE: the loop\n}\nvoid B(void) {\ny:\n    goto y; // !FAKE: the loop\n}\n", {"A": {"goto": 1}, "B": {"goto": 1}}),
    "an #if with two heads and the brace behind its #endif": (
        "#ifdef VERSION_JP\ns32 A(s32 a)\n#else\ns32 A(void)\n#endif\n{\nx:\n"
        "    goto x; // !FAKE: the loop\n}\nvoid B(void) {\ny:\n    goto y; // !FAKE: the loop\n}\n", {"A": {"goto": 1}, "B": {"goto": 1}}),
    "an `else if` in column 0 opens no body": ("void A(s32 a) {\n    if (a) {\n    }\nelse if (a == 2) {\nx:\n    goto x; // !FAKE: the loop\n"
                                               "    }\n}\n", {"A": {"goto": 1}}),
    "a body beside its stub": ("#ifndef NON_MATCHING\nINCLUDE_ASM(\"asm/nonmatchings/a\", func_80012344);\n#else\n"
                               "s32 func_80012344(s32 a) {\nx:\n    goto x; // !FAKE: the loop\n}\n#endif\n", {"func_80012344": {"goto": 1, "placeholder": 1}}),
    "braces that never close end at the next definition": (
        "void A(s32 a) {\n#ifdef X\n    if (a) {\n#else\n    if (!a) {\n#endif\nx:\n        goto x; // !FAKE: the loop\n    }\n}\n"
        "void B(void) {\ny:\n    goto y; // !FAKE: the loop\n}\n", {"A": {"goto": 1}, "B": {"goto": 1}}),
    "two bodies of one name are one entry": ("void A(void) {\nx:\n    goto x; // !FAKE: the loop\n}\nstruct S {\n    s32 a;\n};\n"
                                             "void A(s32 b) {\ny:\n    goto y; // !FAKE: the loop\n}\n", {"A": {"goto": 2}, floor.SCOPE: {"struct": 1}}),
    "data and a struct are file scope": ("s32 D_800A1234 = 4;\nstruct S {\n    s32 a;\n};\n", {floor.SCOPE: {"placeholder": 1, "struct": 1}}),
}


def self_test_bodies(check) -> None:
    for name, (text, want) in C_BODIES.items():
        got = floor.file_bodies("src/a.c", text)
        check("bodies: " + name, got == want, got)
    stubs = floor.scan_file("src/a.c", C_BODIES["a body beside its stub"][0])["stubs"]
    check("bodies: the stub lines of a file are counted", stubs == 1, stubs)
    for name, text in [(k, t) for k, (t, _) in floor.C_DEBT.items()] + [(k, t) for k, (t, _) in C_BODIES.items()] + [("clean", floor.C_CLEAN)]:
        for rel in ("src/a.c", "include/a.h"):
            total: dict[str, int] = {}
            for got in floor.file_bodies(rel, text).values():
                for kind, n in got.items():
                    total[kind] = total.get(kind, 0) + n
            check("bodies: the sum of a file's bodies is its count: %s (%s)" % (name, rel), total == floor.file_debt(rel, text), total)
    with tempfile.TemporaryDirectory() as td:
        repo = floor._repo(td)
        (repo / "src").mkdir()
        for rel in ("src/one.c", "src/two.c"):         # one name in two files: two bodies
            (repo / rel).write_text("static void Step(void) {\nx:\n    goto x; // !FAKE: the loop\n}\n")
        (repo / "src" / "boot.s").write_text("nop\n")
        floor._git(repo, "add", "src")
        got = floor.debt_bodies(repo)
        check("bodies: one name in two files is two bodies; an assembly file is file scope", got == {
            "src/one.c": {"Step": {"goto": 1}}, "src/two.c": {"Step": {"goto": 1}}, "src/boot.s": {floor.SCOPE: {"asm": 1}}}, got)
        (repo / "src" / "half.c").write_text('INCLUDE_ASM("asm/nonmatchings/half", Later);\nvoid Now(void) {\n}\n')
        (repo / "src" / "done.c").write_text("void Done(void) {\n}\n")
        (repo / "src" / "table.c").write_text("s32 g_Table[4];\n")
        floor._git(repo, "add", "src")
        rc, out = floor._capture(floor.cmd_files, repo)
        check("debt --files: a file with no debt of any kind is finished, with no names ledger", rc == 0
              and "DEBT FILE finished src/done.c\n" in out and "DEBT FILE stubs    src/half.c\n" in out
              and "DEBT FILE matched  src/one.c: goto 1\n" in out and "table.c" not in out
              and out.endswith("DEBT FILES 4 C file(s): 1 finished, 2 matched, 1 with stubs\n"), out)
        (repo / "config").mkdir()
        (repo / floor.PUBLIC_PATHS).write_text("src/one.c\nsrc/half.c\n")
        floor._git(repo, "add", "config")
        rc, out = floor._capture(floor.cmd_files, repo, public=True)
        check("debt --files --public: the files that the repository publishes, as its public tree counts them", out.endswith(
            "DEBT FILES 2 C file(s): 0 finished, 1 matched, 1 with stubs\n") and "src/one.c: goto 1\n" in out, out)
        floor._git(repo, "rm", "-q", "-f", "--cached", floor.PUBLIC_PATHS)
        (repo / floor.PUBLIC_PATHS).unlink()


def self_test_files(check) -> None:
    """Which files count, the kinds that a file's text alone does not decide, and the keyword kinds in the view of the
    game's preprocessor."""
    for path, want in (("src/a.c", True), ("include/a.h", True), ("lib/libgte/a.c", True), ("Src/A.C", True), ("game/a.cpp", True),
                       ("src/body.inc", True), ("src/boot.S", True), ("src/boot.asm", True), ("asm/main/a.s", False),
                       ("tools/host.c", False), ("build/a.c", False), ("refs/x/a.c", False), (".run/a.c", False),
                       ("src/.cache/a.c", False), ("docs/a.md", False), ("src/a.txt", False)):
        check("a counted file: %s" % path, floor.is_source(path) == want)
    plumbing = '__asm__(".include \\"macro.inc\\"\\n");\n__asm__(".macro glabel label\\n.global \\\\label\\n\\\\label:\\n.endm\\n");\n'
    stub = '__asm__(".pushsection .text\\n\\t.align\\t2\\n\\t.set noreorder\\n\\t.set noat\\n.include \\"asm/a/Run.s\\"\\n\\t.set reorder\\n\\t.set at\\n.popsection");\n'
    for name, text, want in (
            ("a file-scope asm statement of assembler directives is the stub's plumbing, in a header and in a C file", plumbing, {}),
            ("an expanded stub is no debt", stub, {}),
            ("an instruction in a file-scope asm statement is assembly", '__asm__(".text\\nFast:\\n    jr $ra\\n nop\\n");\n', {"asm": 1}),
            ("data in a file-scope asm statement is assembly", '__asm__(".section .text\\n.word 0x03E00008\\n");\n', {"asm": 1}),
            ("a file pulled in as bytes is assembly", '__asm__(".incbin \\"blob.bin\\"");\n', {"asm": 1}),
            ("an instruction behind a separator spelled as an escape is assembly",
             '__asm__(".set noat\\x3b j $ra\\x3b nop");\n__asm__(".section .text\\012\\t.word 0x3c1a8003");\n__asm__(".set reorder\\073 jr $ra");\n', {"asm": 3}),
            ("the use of an assembler macro is an instruction", '__asm__(".macro ret\\n jr $ra\\n.endm\\nret\\n");\n', {"asm": 1}),
            ("an asm statement that is no string is assembly", "__asm__(TEXT);\n", {"asm": 1}),
            ("assembler directives inside a function force the compiler: a barrier", 'void A(void) {\n    __asm__(".set noreorder");\n}\n',
             {"barrier": 1, "barrier-unmarked": 1}),
            ("an empty asm statement with another volatile spelling is a barrier", 'void A(void) {\n    __asm__ __volatile("");\n}\n',
             {"barrier": 1, "barrier-unmarked": 1}),
            ("a goto as an argument", "void A(s32 n) {\nl:\n    DO(goto, l);\n}\n", {"goto": 1, "goto-unmarked": 1}),
            ("a computed goto", "void A(void *p) {\n    goto *p;\n}\n", {"goto": 1, "goto-unmarked": 1}),
            ("a goto with a reason", "void A(void *p) {\n    // !FAKE: the jump table of the original\n    goto *p;\n}\n", {"goto": 1}),
            ("offsets with a minus and a negative index",
             "s32 A(u8 *p) {\n    return *(s32 *)(p - 4) + *(s32 *)((u8 *)p - 8) + ((s32 *)p)[-2];\n}\n", {"offset": 3}),
            ("the integer types of the SDK in a cast of a pointer",
             "u_long A(void *p) {\n    return (u_long)&p + (u_int)(s32 *)p + *(s32 *)(ulong)p + *((u_char *)p + 4);\n}\n", {"cast": 3, "offset": 1})):
        for rel in ("src/a.c", "include/a.h"):
            got = floor.file_debt(rel, text)
            check("%s (%s)" % (name, rel), got == want, got)
    import time
    t0 = time.time()
    floor.file_debt("src/slow.c", "s32 A(void) {\n    return *(" + "a " * 4000 + ");\n}\n" + "".join("#define M%d M%d\n" % (i, i + 1) for i in range(400)))
    check("a long run of words and a long chain of macros cost no more than a second", time.time() - t0 < 1.0, time.time() - t0)
    with tempfile.TemporaryDirectory() as td:
        repo = floor._repo(td)
        put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
        unmarked = floor.C_DEBT["goto-unmarked"][0]
        named = ("src/func_80012344.c", "src/misc12.c", "src/func_800EFE70_ovl02.c", "src/D_800EEC60_ovl00.c",
                 "src/shared/func_80023E04.inc.c")
        for rel in ("src/walk.c", "src/funcs.c", "lib/walk.c", "asm/walk.c", "tools/walk.c") + named:
            put(rel, unmarked.replace("Walk", "W_" + re.sub(r"\W", "_", rel)))
        put("src/hand.asm", "nop\n")
        floor._git(repo, "add", "-A")
        got = floor.debt_bodies(repo)
        check("code in any folder counts; the splitter's and the tools' folders do not", sorted(got) == sorted(
            ("lib/walk.c", "src/funcs.c", "src/hand.asm", "src/walk.c") + named), sorted(got))
        check("a file named by an address or a number, also with a suffix after a placeholder name",
              all(got[p].get(floor.SCOPE) == {"filename": 1} for p in named)
              and floor.SCOPE not in got["src/walk.c"] and floor.SCOPE not in got["src/funcs.c"],
              {p: got[p].get(floor.SCOPE) for p in named + ("src/funcs.c",)})
        check("an assembly file by another suffix", got["src/hand.asm"] == {floor.SCOPE: {"asm": 1}}, got["src/hand.asm"])
        floor._commit(repo, "the tree")
        check("a revision and the index hold the same files", floor.debt_bodies(repo, tree=floor.Tree(repo, "HEAD")) == got
              and floor.debt_bodies(repo, tree=floor.Tree(repo, floor.INDEX)) == got)
        # a macro of a header and of an included C file that hides an offset counts where it is used
        put("src/shared/mac.c", "#define FIELD4(p) (*(s32 *)((p) + 4))\n")
        put("src/id.c", '#include "shared/mac.c"\ns32 Kept(s32 n) {\n    return FIELD4(n);\n}\n')
        got = floor.debt_bodies(repo, tree=floor.Tree(repo, None, untracked=True))["src/id.c"]
        check("a macro of an included C file that hides an offset counts where it is used", got["Kept"] == {"offset": 1}, got)


def self_test_view(check) -> None:
    """The keyword kinds in the view of the game's preprocessor: what a macro, an include of any file and a second
    unit do to the count, the three sources of a tree, a unit that cannot be read, and what one change costs."""
    out = '# 1 "src/u.c"\nvoid A(void) {\n# 1 "src/frag.def" 1\n    goto x;\n# 3 "src/u.c" 2\n    go\\\nto y; register int r\n# 1 "include/pin.h" 1\n asm("$4");\n# 5 "src/u.c" 2\n}\n'
    hits, files = floor.unit_view(out, "src/u.c", "/nowhere")
    check("the view: each hit has the file and the line of its first character", hits == {
        ("goto", "src/frag.def", 0): 1, ("pin", "src/u.c", 3): 1} and files == {"src/u.c", "src/frag.def", "include/pin.h"}, (hits, files))
    twice = '# 1 "src/u.c"\n# 1 "src/t.c" 1\ngoto a; goto b;\n# 2 "src/u.c" 2\n# 1 "src/t.c" 1\ngoto a; goto b;\n# 3 "src/u.c" 2\n'
    check("the view: a file that a unit includes twice is read once", floor.unit_view(twice, "src/u.c", "/nowhere")[0] == {("goto", "src/t.c", 0): 2})
    check("the view: marks cover one construct each, on the line or alone above it", floor.marked(
        [("goto", 3), ("goto", 3), ("pin", 5), ("asm", 7)], {2: ("the loop", True), 5: ("", False)}) == [
        ("goto", 3), ("goto", 3), ("goto-unmarked", 3), ("pin", 5), ("pin-unmarked", 5), ("asm", 7)])
    saved = os.environ.get("PSXD_SELF_CPP_LOG")
    with tempfile.TemporaryDirectory() as td:
        repo = floor._repo(td)
        put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
        log = pathlib.Path(td + ".cpp.log")
        os.environ["PSXD_SELF_CPP_LOG"] = str(log)

        def ran() -> list[str]:
            got = sorted(log.read_text().split()) if log.is_file() else []
            log.unlink(missing_ok=True)
            return got

        cpp = "[psxdecomp]\nversion = \"0.6.0\"\n\n[floor]\ncpp = '%s tools/cpp.py {file}'\n" % sys.executable
        put("tools/cpp.py", doctor.CPP_SELF)
        put("include/m.h", "#define AGAIN goto again\n")
        put("src/unit.c", '#include "m.h"\n#include "shared/body.c"\ns32 Two(s32 n) {\n#include "pins.def"\n    return n;\n}\n')
        put("src/shared/body.c", "s32 One(s32 n) {\nagain:\n    if (n--) AGAIN;\n    return n;\n}\n")
        put("src/pins.def", '    register s32 t asm("$17");\n')
        put("src/other.c", '#include "m.h"\n#include "shared/body.c"\n')
        put("src/alone.c", "s32 Alone(s32 n) {\n    return n;\n}\n")
        floor._git(repo, "add", "-A")
        raw = floor.debt_counts(repo)
        check("no [floor] cpp: the raw text shows the macro's goto at its definition, and no file of another suffix", raw == {
            ("goto", "include/m.h"): 1, ("goto-unmarked", "include/m.h"): 1}, raw)
        put(floor.RECORD, cpp)
        floor._git(repo, "add", "-A")
        want = {("goto", "src/shared/body.c"): 1, ("goto-unmarked", "src/shared/body.c"): 1,
                ("pin", "src/pins.def"): 1, ("pin-unmarked", "src/pins.def"): 1}
        got = floor.debt_counts(repo)
        check("[floor] cpp: a goto behind a macro counts where it is used, a pin in a file of any suffix where it stands, "
              "and a file that two units read once", got == want, got)
        check("the view: every C file is a unit, also one that another unit includes", ran() == [
            "src/alone.c", "src/other.c", "src/shared/body.c", "src/unit.c"])
        floor._commit(repo, "the tree")
        for name, src in (("the index", floor.INDEX), ("a revision", "HEAD"), ("the work tree with the files git does not track", None)):
            tree = floor.Tree(repo, src, untracked=src is None)
            check("the view: %s gives the same count" % name, floor.debt_counts(repo, tree=tree) == want, floor.debt_counts(repo, tree=tree))
        check("the view: no unit ran again, each result was kept beside the files it read", ran() == [], "ran")
        put("src/shared/body.c", "s32 One(s32 n) {\nagain:\n    // !FAKE: the loop of the original\n    if (n--) AGAIN;\n    return n;\n}\n")
        got = floor.debt_bodies(repo)
        check("the view: a marker in the file that holds the line covers the construct", got["src/shared/body.c"] == {"One": {"goto": 1}}
              and got["src/pins.def"] == {floor.SCOPE: {"pin": 1, "pin-unmarked": 1}}, got)
        check("the view: one changed file costs the units that read it", ran() == ["src/other.c", "src/shared/body.c", "src/unit.c"])
        put("src/alone.c", 's32 Alone(s32 n) {\n    __asm__("nop");\n    return n;\n}\n')
        check("the view: an asm statement in a function", floor.debt_counts(repo).get(("asm", "src/alone.c")) == 1 and ran() == ["src/alone.c"])
        put(floor.ASM_EVIDENCE, "\t".join(floor.ASM_COLUMNS) + "\nmain\tAlone\tsrc/alone.c\thand-asm\tsrc/alone.c:2\t2026-01-02\tdeveloper\n")
        check("the view: an assembly row clears the function that holds the line", ("asm", "src/alone.c") not in floor.debt_counts(repo))
        (repo / floor.ASM_EVIDENCE).unlink()
        floor._cpp_cache_on = False
        floor.debt_counts(repo)
        check("the view: a push and CI run every unit again", ran() == ["src/alone.c", "src/other.c", "src/shared/body.c", "src/unit.c"])
        floor._cpp_cache_on = True
        # a judge that cannot read passes nothing
        put("src/alone.c", '#include "gone.h"\ns32 Alone(s32 n) {\n    return n;\n}\n')
        try:
            floor.debt_counts(repo)
            check("the view: a unit that the command cannot preprocess is a refusal", False)
        except floor.Fail as e:
            check("the view: a unit that the command cannot preprocess is a refusal", "cannot preprocess 1 unit(s) of the work tree: "
                  "src/alone.c: src/alone.c:1: fatal error: gone.h" in str(e), str(e))
        rc, out = floor._capture(floor.cmd_debt, repo)
        check("debt: and it says so", rc == 1 and "DEBT FAIL `[floor] cpp`" in out, out)
        for name, text in (("#line", '#line 3 "src/shared/body.c"\n'), ("a number behind a digraph, a comment and a splice", "/* x */ %: \\\n 3 \"src/shared/body.c\"\n")):
            put("src/alone.c", "s32 Alone(s32 n) {\nagain:\n%s    if (n--) goto again;\n    return n;\n}\n" % text)
            try:
                floor.debt_counts(repo)
                check("the view: a source with a line directive (%s) is a refusal" % name, False)
            except floor.Fail as e:
                check("the view: a source with a line directive (%s) is a refusal" % name, "src/alone.c holds a line directive" in str(e), str(e))
        put("src/alone.c", "s32 Alone(s32 n) {\n    return n; /* # 3 and #line in a comment, and a baseline of 3 */\n}\n")
        check("the view: the words in a comment are no directive", floor.debt_counts(repo) is not None)
        put("src/alone.c", "s32 Alone(s32 n) {\n    return n;\n}\n")
        put(floor.RECORD, cpp.replace(sys.executable, "/nowhere/psxd-no-such-cpp"))
        try:
            floor.debt_counts(repo)
            check("the view: a program that the machine lacks is a refusal", False)
        except floor.Fail as e:
            check("the view: a program that the machine lacks is a refusal", "names a program that this machine lacks (`/nowhere/psxd-no-such-cpp`)" in str(e), str(e))
        # the command of the tree a change starts from judges it
        put(floor.RECORD, cpp)
        put("src/shared/body.c", "s32 One(s32 n) {\nagain:\n    if (n--) AGAIN;\n    return n;\n}\n")
        floor._git(repo, "add", "-A")
        put(floor.BASELINE, floor.first_baseline(repo))
        floor._commit(repo, "the floor, with its rows in the compiler's view")
        check("the first baseline holds the totals of the view", "1 pin-unmarked\n" in (repo / floor.BASELINE).read_text()
              and "1 goto-unmarked\n" in (repo / floor.BASELINE).read_text() and floor._capture(floor.cmd_debt, repo)[0] == 0, (repo / floor.BASELINE).read_text())
        put("include/m.h", "#define AGAIN goto again\n#define HIDDEN goto again\n")
        put("src/alone.c", '#include "m.h"\ns32 Alone(s32 n) {\nagain:\n    if (n--) HIDDEN;\n    return n;\n}\n')
        put(floor.RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[floor]\ncpp = '%s -c pass {file}'\n" % sys.executable)
        floor._git(repo, "add", "-A")
        got = floor.admission(repo, floor.Tree(repo, "HEAD"), floor.Tree(repo, floor.INDEX))[0]
        check("a change that swaps the preprocessor for one that prints nothing is judged by the command it started from", got == [
            ("debt", "goto-unmarked is `down` and its total rose: 1 -> 2 (src/alone.c 0 -> 1)")], got)
        found = floor.protected_findings(floor.Tree(repo, "HEAD"), floor.Tree(repo, floor.INDEX))[0]
        check("and the command itself is a protected value", any("[floor] cpp changed" in f for f in found), found)
    if saved is None:
        os.environ.pop("PSXD_SELF_CPP_LOG", None)
    else:
        os.environ["PSXD_SELF_CPP_LOG"] = saved
    import shutil
    cc = shutil.which("cc")
    if cc:                                             # a real preprocessor, where the machine has one: text that a pattern cannot read
        with tempfile.TemporaryDirectory() as td:
            repo = floor._repo(td)
            put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
            put(floor.RECORD, "[psxdecomp]\nversion = \"0.6.0\"\n\n[floor]\ncpp = 'cc -E -nostdinc -undef -Iinclude {file}'\n")
            put("include/common.h", '#define INCLUDE_ASM(FOLDER, NAME) __asm__(".section .text\\n\\t.include \\"" FOLDER "/" #NAME ".s\\"\\n")\n'
                "#define GLUE(a, b) a##b\n#define JUMP(l) GLUE(go, to) l\n#define REG(t, v, r) register t v GLUE(as, m)(r)\n")
            put("src/a.c", '#include "common.h"\nINCLUDE_ASM("asm/a", Run);\nint Walk(int n) <%\n    REG(int, i, "$16");\nloop:\n    if (--n) JUMP(loop);\n'
                "    if (n) go\\\nto loop;\n#if 0\n    goto loop;\n#endif\n    return i;\n%>\n")
            floor._git(repo, "add", "-A")
            try:
                got = {k: n for k, n in floor.debt_counts(repo).items() if k[0].split("-")[0] in ("pin", "goto", "barrier", "asm")}
            except floor.Fail as e:
                got = str(e)
            check("a real preprocessor: a paste, a splice, a digraph, a stub and a branch that is not compiled", got == {
                ("pin", "src/a.c"): 1, ("pin-unmarked", "src/a.c"): 1, ("goto", "src/a.c"): 2, ("goto-unmarked", "src/a.c"): 2}, got)
            put("src/b.c", '#include "common.h"\n#ifndef HIDE_B\nint Bfunc(int n) {\nagain:\n    if (--n) goto again;\n    return n;\n}\n#endif\n')
            put("src/c.c", '#include "common.h"\n#define HIDE_B 1\n#define IN_UNIT 1\n#include "b.c"\nint Cfunc(void) {\n#include "tail.c"\n}\n')
            put("src/tail.c", "#ifndef IN_UNIT\n#error this fragment stands inside a unit\n#endif\n    return 0;\n")
            floor._git(repo, "add", "-A")
            try:
                got = floor.debt_counts(repo).get(("goto-unmarked", "src/b.c"))
            except floor.Fail as e:
                got = str(e)
            check("a real preprocessor: a file is read alone as well, so the macros of a unit that includes it hide nothing", got == 1, got)
            (repo / "src/c.c").unlink()
            floor._git(repo, "add", "-A")
            try:
                floor.debt_counts(repo)
                check("a real preprocessor: a fragment that fails alone and that no unit reads is a refusal", False)
            except floor.Fail as e:
                check("a real preprocessor: a fragment that fails alone and that no unit reads is a refusal", "src/tail.c" in str(e), str(e))


def self_test_tree(check) -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = floor._repo(td)
        (repo / "src").mkdir()
        (repo / "src" / "walk.c").write_text(floor.C_DEBT["goto"][0])
        (repo / "src" / "two.c").write_bytes(floor.C_DEBT["struct"][0].replace("\n", "\r\n").encode())
        os.symlink("walk.c", repo / "src" / "link.c")
        floor._git(repo, "add", "-A")
        (repo / "config").mkdir()
        (repo / floor.BASELINE).write_text(floor.first_baseline(repo))
        floor._commit(repo, "one")
        (repo / "src" / "walk.c").write_text(floor.C_DEBT["goto"][0] * 2)
        floor._git(repo, "add", "src/walk.c")
        (repo / "src" / "walk.c").write_text(floor.C_DEBT["goto"][0] * 2 + floor.C_DEBT["goto-unmarked"][0])
        (repo / "src" / "new.c").write_text(floor.C_DEBT["goto"][0])
        got = [floor.debt_counts(repo, tree=floor.Tree(repo, src)).get(("goto", "src/walk.c")) for src in ("HEAD", floor.INDEX, None)]
        check("tree: a revision, the index and the work tree are three sources", got == [1, 2, 3], got)
        check("tree: CRLF is read as LF, from the disk and from a blob", all(
            floor.debt_counts(repo, tree=floor.Tree(repo, src)).get(("struct", "src/two.c")) == 1 for src in ("HEAD", floor.INDEX, None)))
        check("tree: a symbolic link is no file of the tree", all(
            floor.Tree(repo, src).read("src/link.c") is None for src in ("HEAD", floor.INDEX, None)))
        check("tree: an untracked file counts only when asked for", "src/new.c" not in floor.Tree(repo).paths
              and "src/new.c" in floor.Tree(repo, untracked=True).paths and not floor.Tree(repo, "HEAD").has("src/new.c"))
        try:
            floor.Tree(repo, "no-such-revision")
            check("tree: a revision git cannot read is a refusal", False)
        except floor.Fail:
            pass
        rc, out = floor._capture(floor.cmd_debt, repo, against="HEAD")
        check("debt --against: the change since a revision is judged", rc == 1 and "DEBT FAIL debt: goto-unmarked is `down` and its "
              "total rose: 0 -> 1 (src/walk.c 0 -> 1)\n" in out and "1 finding(s) against HEAD" in out, out)
        rc, out = floor._capture(floor.cmd_debt, repo, source=floor.INDEX, update=True)
        check("debt --staged takes no --update", rc == 1 and "takes no --staged" in out, out)
    check("the two tools stand side by side", floor.sibling().name == pathlib.Path(floor.__file__).name.replace("floor", "publish"))


def self_test_markers(check) -> None:
    check("markers: a reason is a text", floor.reason_ok("the loop counter") and not floor.reason_ok("") and not floor.reason_ok("-- ?") and not floor.reason_ok(None))
    one = 'void A(void) {\n    // !FAKE: both\n    register s32 a asm("$4");\n    register s32 b asm("$5");\n}\n'
    check("markers: one marker covers one pin", floor.file_debt("src/a.c", one) == {"pin": 2, "pin-unmarked": 1}, floor.file_debt("src/a.c", one))
    tail = 'void A(void) {\n    register s32 a asm("$4"); // !FAKE: the first one\n    register s32 b asm("$5");\n}\n'
    check("markers: a marker behind a pin does not cover the pin below", floor.file_debt("src/a.c", tail) == {"pin": 2, "pin-unmarked": 1})
    bare = 'void A(void) {\n    // !FAKE:\n    register s32 a asm("$4");\n    register s32 b asm("$5"); /* !FAKE: */\n}\n'
    check("markers: a marker with no reason covers nothing", floor.file_debt("src/a.c", bare) == {"pin": 2, "pin-unmarked": 2})
    quoted = 'void A(void) {\n    register s32 a asm("$4"); Log("!FAKE: the first one");\n}\n'
    check("markers: a marker in a string is no marker", floor.file_debt("src/a.c", quoted) == {"pin": 1, "pin-unmarked": 1})


GATE_SETTINGS = {"permissions": {"deny": ["Bash(git push *)", "Edit(/config/debt-baseline.txt)"]}, "hooks": {"PreToolUse": [
    {"matcher": "Bash|Edit|Write", "hooks": [{"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/tools/psxd_floor.py" guard --hook'}]},
    {"matcher": "Bash", "hooks": [{"type": "command", "command": "the game's own hook"}]}]}}


def self_test_gate(check) -> None:
    keep = floor._sibling_run
    if not floor.sibling().is_file():                        # this file alone: the checks of the other tool are not its to test
        floor._sibling_run = lambda repo, *args: (0, [])  # noqa: E731
    try:
        with tempfile.TemporaryDirectory() as td:
            repo = floor._repo(td)
            put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
            gate = lambda mode, rng=None: floor._capture(floor.cmd_gate, repo, mode, rng)  # noqa: E731
            mine = pathlib.Path(floor.__file__).read_text(encoding="utf-8")
            put("src/walk.c", floor.C_DEBT["goto"][0])
            put(floor.VENDORED, mine)
            put(floor.TOOLS[1], floor.sibling().read_text(encoding="utf-8") if floor.sibling().is_file() else "VERSION = \"0.6.0\"\n")
            put(floor.SETTINGS, json.dumps(GATE_SETTINGS, indent=2) + "\n")
            put(floor.GUARD, "deny\tpath\tasm/\tasm/ is generated\n")
            put(floor.RECORD, '[psxdecomp]\nversion = "0.6.0"\n\n[own]\nnames = "config/names.basis.tsv"\ndebt = "python3 tools/scan.py --all"\n'
                '\n[floor]\ngate = "sh tools/check.sh"\n')
            put("tools/check.sh", 'test -z "$PSXD_SELF_RED" || { echo the build is red; exit 3; }\n')
            put("src/vendor/lib.c", "void Lib(void) {\n}\n")
            put("config/names.basis.tsv", "name\tbasis\nWalk\tthe string it prints\n")
            put("tools/scan.py", "import os, sys\nprint('SCAN %s' % ('FAIL' if os.environ.get('PSXD_SELF_SCAN') else 'OK'))\n"
                "sys.exit(1 if os.environ.get('PSXD_SELF_SCAN') else 0)\n")
            put("src/stubs.c", 'INCLUDE_ASM("asm/nonmatchings/a", Run);\n')
            put(floor.WORKFLOWS + "no-rom.yml", "name: no-rom\n")
            floor._git(repo, "add", "-A")
            put(floor.BASELINE, floor.first_baseline(repo) + "skip src/vendor/\n")
            floor._git(repo, "add", "-A")
            rc, out = gate("staged")
            check("gate --staged before the first commit: the tree as it stands", rc == 0 and "no commit yet" in out
                  and out.endswith("GATE OK (staged)\n"), out)
            floor._commit(repo, "the floor")
            start = floor._rev(repo, "HEAD")
            rc, out = gate("staged")
            check("gate --staged with nothing staged", (rc, out) == (0, "GATE OK (staged)\n"), out)
            base_text = (repo / floor.BASELINE).read_text()
            staged = lambda: (floor._git(repo, "add", "-A"), gate("staged"))[1]  # noqa: E731
            undo = lambda: (floor._git(repo, "reset", "-q", "--hard", "HEAD"), floor._git(repo, "clean", "-q", "-fd"))  # noqa: E731
            # a name is never required: an address name, a guessed name and a provisional row with no evidence all pass
            put("src/guess.c", "s32 func_80012344(s32 n) {\n    return n;\n}\ns32 Enemy_Think(s32 n) {\n    return n;\n}\n")
            put(floor.NAMES, "\t".join(floor.NAME_COLUMNS) + "\nfunction\tmain\t\tfunc_80010000\tEnemy_Walk\tprovisional\tstring:src/gone.c:4\ta guess\n")
            floor._git(repo, "add", "-A")
            floor._capture(floor.cmd_debt, repo, update=True)
            rc, out = staged()
            check("gate: an address name, a guessed name and a provisional row with no evidence pass", rc == 0
                  and "GATE WARN" not in out and "1 placeholder\n" in (repo / floor.BASELINE).read_text() and out.endswith("GATE OK (staged)\n"), out)
            put(floor.NAMES, "kind\tname\n")
            rc, out = staged()
            check("gate: a names ledger that cannot be read fails", rc == 1 and "GATE FAIL names: config/names.tsv: line 1: the header is not" in out, out)
            undo()
            # the baseline: a row written by hand, a policy line taken out, a new skip line
            put("src/walk.c", floor.C_DEBT["goto"][0] + floor.C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            put(floor.BASELINE, base_text.replace("1 goto\n", "1 pin\n1 pin-unmarked\n1 goto\n"))
            rc, out = staged()
            check("gate: a row written by hand admits nothing", rc == 1 and "GATE FAIL debt: pin-unmarked is `down` and its total "
                  "rose: 0 -> 1 (src/walk.c 0 -> 1)\n" in out and out.endswith("GATE FAIL (staged; 1 finding(s))\n"), out)
            undo()
            put("src/walk.c", floor.C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
            put(floor.BASELINE, base_text.replace("1 goto\n", "2 goto\n"))
            check("gate: a counted kind rises with its row", staged() == (0, "GATE OK (staged)\n"), staged())
            undo()
            for name, text, want in (("a policy line taken out", base_text.replace("mode pin-unmarked down\n", ""),
                                      "GATE FAIL policy: the policy line of pin-unmarked is gone"),
                                     ("a weaker mode", base_text.replace("mode asm down", "mode asm count"),
                                      "GATE FAIL policy: asm went from down to count"),
                                     ("a new skip line", base_text + "skip src/\n", "GATE FAIL policy: a new `skip` line (src/)")):
                put(floor.BASELINE, text)
                rc, out = staged()
                check("gate: " + name, rc == 1 and want in out, out)
            undo()
            (repo / floor.BASELINE).unlink()
            rc, out = staged()
            check("gate: a deleted baseline", rc == 1 and "GATE FAIL policy: config/debt-baseline.txt is gone" in out
                  and "GATE FAIL debt: no config/debt-baseline.txt" in out, out)
            undo()
            # the files that carry the floor: each is valid against HEAD
            hooks = json.loads(json.dumps(GATE_SETTINGS))
            for name, change, want in (
                    ("a tool that changed", lambda: put(floor.VENDORED, mine + "# a change\n"), "tools/psxd_floor.py changed and its version did not"),
                    ("a tool with a lower version", lambda: put(floor.VENDORED, mine.replace('VERSION = "%s"' % floor.VERSION, 'VERSION = "0.5.9"')),
                     "tools/psxd_floor.py went from version %s back to 0.5.9" % floor.VERSION),
                    ("a tool that is gone", lambda: (repo / floor.TOOLS[1]).unlink(), "tools/psxd_publish.py is gone"),
                    ("a workflow that changed", lambda: put(floor.WORKFLOWS + "no-rom.yml", "name: nothing\n"), "no-rom.yml changed"),
                    ("a hook that is gone", lambda: put(floor.SETTINGS, json.dumps(dict(hooks, hooks={}))), "lost a hook of PreToolUse"),
                    ("a hook with a narrower matcher", lambda: put(floor.SETTINGS, json.dumps(GATE_SETTINGS).replace("Bash|Edit|Write", "Edit|Write")),
                     "lost a hook of PreToolUse (or a tool of its matcher)"),
                    ("a hook command made empty", lambda: put(floor.SETTINGS, json.dumps(GATE_SETTINGS).replace("guard --hook", "guard --hook || true")),
                     "lost a hook of PreToolUse"),
                    ("a deny rule that is gone", lambda: put(floor.SETTINGS, json.dumps(GATE_SETTINGS).replace('"Bash(git push *)", ', "")),
                     "lost 1 deny rule(s): Bash(git push *)"),
                    ("disableAllHooks", lambda: put(floor.SETTINGS, json.dumps(dict(hooks, disableAllHooks=True))), "sets disableAllHooks"),
                    ("a guard row that is gone", lambda: put(floor.GUARD, "deny\tpath\tbuild/\tx\n"), "lost the row `deny path asm/`"),
                    ("a new allow row", lambda: put(floor.GUARD, "allow\tpath\tasm/x.s\t\ndeny\tpath\tasm/\tasm/ is generated\n"), "a new `allow` row (path asm/x.s)"),
                    ("the game's own scanner, edited", lambda: put("tools/scan.py", "print('SCAN OK')\n"),
                     "tools/scan.py changed (the record names it"),
                    ("the game's own ledger, a row changed", lambda: put("config/names.basis.tsv", "name\tbasis\nWalk\tnone\n"),
                     "config/names.basis.tsv lost or changed 1 line(s)"),
                    ("the record's own check, replaced", lambda: put(floor.RECORD, (repo / floor.RECORD).read_text().replace("python3 tools/scan.py --all", "true")),
                     "config/psxdecomp.toml [own] debt changed"),
                    ("a new key that moves what a check reads", lambda: put(floor.RECORD, (repo / floor.RECORD).read_text() + '\n[debt]\naddress_header = "src/walk.c"\n'),
                     "config/psxdecomp.toml [debt] address_header is new ('src/walk.c')"),
                    ("a file that a skip line covers", lambda: put("src/vendor/lib.c", floor.C_DEBT["goto"][0]),
                     "src/vendor/lib.c changed, and a `skip` line covers it"),
                    ("a new file under a skip line", lambda: put("src/vendor/more.c", floor.C_DEBT["goto"][0]), "src/vendor/more.c changed, and a `skip` line"),
                    ("the settings of one machine, tracked", lambda: (put(floor.SETTINGS.replace(".json", ".local.json"), '{"disableAllHooks": true}\n'),
                                                                      floor._git(repo, "add", "-f", floor.SETTINGS.replace(".json", ".local.json"))),
                     ".claude/settings.local.json is tracked and changed"),
                    ("the project folder of the hooks, moved", lambda: put(floor.SETTINGS, json.dumps(dict(hooks, env={"CLAUDE_PROJECT_DIR": "/nowhere"}))),
                     "changes CLAUDE_PROJECT_DIR in `env`"),
                    ("a variable that stills a check, set for every session", lambda: put(floor.SETTINGS, json.dumps(dict(hooks, env={"PSXD_GATE": "1"}))),
                     "changes PSXD_GATE in `env`")):
                change()
                rc, out = staged()
                check("gate: " + name, rc == 1 and "GATE FAIL protected: " in out and want in out, out)
                undo()
            for name, text in (("deny rules that are no list", '{"permissions": {"deny": 5}}'), ("hooks that are no table", '{"hooks": 5}'),
                               ("a hook group that is no list", '{"hooks": {"PreToolUse": 5}}'), ("settings nested too deep", "[" * 200000)):
                put(floor.SETTINGS, text)
                try:
                    rc, out = staged()
                except Exception as e:                 # the control: a crash is no answer
                    rc, out = -1, "%s: %s" % (type(e).__name__, str(e)[:80])
                check("gate: %s: a FAIL, never a crash" % name, rc == 1 and "GATE FAIL " in out and out.endswith(" finding(s))\n"), out[-200:])
                undo()
            rules = GATE_SETTINGS["permissions"]["deny"]
            for name, value in (("deny rules as one string", " ".join(rules)), ("deny rules as the keys of a table", dict.fromkeys(rules, False)),
                                ("deny rules inside another list", [rules])):
                put(floor.SETTINGS, json.dumps(dict(hooks, permissions={"deny": value})))
                rc, out = staged()
                check("gate: %s are no deny rules" % name, rc == 1 and "GATE FAIL protected: " in out and "deny" in out, out[-300:])
                undo()
            for name, matcher in (("a matcher that is a character class of the old one", "[^|Bash|Edit|Write|]"),
                                  ("a matcher with one more token that is no tool name", "NoSuchTool(|Bash|Edit|Write|)")):
                put(floor.SETTINGS, json.dumps(GATE_SETTINGS).replace('"Bash|Edit|Write"', json.dumps(matcher)))
                rc, out = staged()
                check("gate: %s loses the hook" % name, rc == 1 and "lost a hook of PreToolUse" in out, out[-300:])
                undo()
            put("config/names.basis.tsv", "name\tbasis\nWalk\tthe string it prints\nRun\tits caller\n")
            put(floor.WORKFLOWS + "extra.yml", "name: extra\n")
            put(floor.GUARD, "deny\tpath\tasm/\tasm/ is generated\ndeny\tpath\tbuild/\tthe build writes it\n")
            put(floor.SETTINGS, json.dumps(GATE_SETTINGS).replace('"Bash|Edit|Write"', '"Bash|Edit|Write|MultiEdit"'))
            rc, out = staged()
            check("gate: a new ledger row, a new workflow, a new deny row and a wider matcher pass", (rc, out) == (0, "GATE OK (staged)\n"), out)
            undo()
            put(floor.WORKFLOWS + "no-rom.yml", "name: nothing\n")
            put(floor.BASELINE, base_text.replace("skip ", "raise protected 1 2026-01-02 the runner changed\nskip ") if "skip " in base_text
                else base_text.replace("1 goto\n", "raise protected 1 2026-01-02 the runner changed\n1 goto\n"))
            rc, out = staged()
            check("gate: a `raise protected` line of the developer allows one such change", rc == 0 and
                  "GATE INFO protected, and a `raise protected` line of the change allows it: .github/workflows/no-rom.yml changed" in out
                  and "GATE INFO the developer's act, new in this change: `raise protected 1 2026-01-02 the runner changed`" in out, out)
            os.environ["CLAUDECODE"] = "1"
            rc, out = staged()
            check("gate: a `raise` line in an agent session is refused", rc == 1 and "GATE FAIL raise: `raise protected 1 2026-01-02 the "
                  "runner changed` in config/debt-baseline.txt is new, and this is an agent session" in out, out)
            undo()
            put(floor.ASM_EVIDENCE, "\t".join(floor.ASM_COLUMNS) + "\nmain\tWalk\tsrc/walk.c\thand-asm\tsrc/walk.c:1\t2026-01-02\tdeveloper\n")
            rc, out = staged()
            check("gate: a new assembly row in an agent session is refused", rc == 1 and "GATE FAIL raise: the row of Walk src/walk.c in "
                  "config/asm-evidence.tsv is new" in out, out)
            del os.environ["CLAUDECODE"]
            check("gate: and it is the developer's to add", staged()[0] == 0)
            undo()
            # a tool of a later version judges the tree, after the tool of HEAD accepted the change
            later = mine.replace('VERSION = "%s"' % floor.VERSION, 'VERSION = "99.0.0"').replace('"GATE %s (%s%s)"', '"GATE %s by the later tool (%s%s)"')
            put(floor.VENDORED, later)
            rc, out = staged()
            check("gate: a later tool is accepted, and it judges the tree", rc == 0 and "GATE INFO tools/psxd_floor.py: version "
                  "%s -> 99.0.0" % floor.VERSION in out and out.endswith("GATE OK by the later tool (staged)\n"), out)
            floor._git(repo, "add", "-A")
            floor._commit(repo, "a later tool, as an upgrade commits it")
            digests = pathlib.Path(td + ".digests.json")
            sha = lambda rel: hashlib.sha256((repo / rel).read_bytes()).hexdigest()  # noqa: E731
            digests.write_text(json.dumps({"version": "99.0.0", "files": {floor.VENDORED: sha(floor.VENDORED)}}))
            os.environ[floor.DIGESTS_ENV] = str(digests)
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: a later tool with the released digest is accepted, and it judges from there", rc == 0 and
                  "version %s -> 99.0.0, the released file" % floor.VERSION in out and out.endswith("GATE OK by the later tool (ci; 1 commit(s))\n"), out)
            digests.write_text(json.dumps({"version": "99.0.0", "files": {floor.VENDORED: "0" * 64}}))
            floor._DIGESTS.clear()
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: a later version with other bytes is no released tool", rc == 1 and "by the later tool" not in out and
                  "GATE FAIL protected: " in out and "tools/psxd_floor.py changed: it is not the file that psxdecomp 99.0.0 released" in out, out)
            os.environ[floor.DIGESTS_ENV] = str(digests) + ".gone"
            floor._DIGESTS.clear()
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: digests that cannot be read accept nothing", rc == 1 and "cannot read the digests of psxdecomp 99.0.0" in out, out)
            del os.environ[floor.DIGESTS_ENV]
            floor._DIGESTS.clear()
            digests.unlink()
            floor._git(repo, "reset", "-q", "--hard", "HEAD~1")
            put(floor.VENDORED, later)
            put("src/walk.c", floor.C_DEBT["goto"][0] + floor.C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            rc, out = staged()
            check("gate: a later tool beside a refused change does not take over", rc == 1 and "by the later tool" not in out
                  and "pin-unmarked is `down` and its total rose" in out, out)
            undo()
            os.environ["PSXD_SELF_SCAN"] = "1"         # the game's own scanner is one more check, beside the count
            rc, out = staged()
            check("gate: the game's own debt scanner runs beside the count", rc == 1 and "GATE FAIL own-debt: the game's own scanner" in out
                  and "exited 1: SCAN FAIL" in out, out)
            del os.environ["PSXD_SELF_SCAN"]
            # the bank: the files git does not track yet count, and the rows of an admitted change are written
            put("src/new.c", floor.C_DEBT["goto"][0].replace("Walk", "Run"))
            rc, out = gate("bank")
            check("gate --bank counts a file that is not tracked yet and writes the totals", rc == 0 and "2 goto\n" in (repo / floor.BASELINE).read_text()
                  and "GATE INFO config/debt-baseline.txt: the totals of now written (1 rose, 0 fell)" in out
                  and out.endswith("GATE OK (bank)\n"), out)
            put("src/new.c", floor.C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            before = (repo / floor.BASELINE).read_text()
            rc, out = gate("bank")
            check("gate --bank refuses an unmarked pin in a file that is not tracked yet", rc == 1 and
                  "GATE FAIL debt: pin-unmarked is `down` and its total rose: 0 -> 1 (src/new.c 0 -> 1)" in out and (repo / floor.BASELINE).read_text() == before, out)
            put("src/new.c", floor.C_DEBT["goto"][0].replace("Walk", "Run"))
            os.environ["PSXD_SELF_RED"] = "1"
            rc, out = gate("bank")
            check("gate --bank runs the game's own check", rc == 1 and "GATE FAIL game: `sh tools/check.sh` exited 3: "
                  "the build is red" in out, out)
            os.environ[floor.GATE_ENV] = "1"
            check("a gate inside the game's own check does not run it again", gate("bank")[0] == 0)
            del os.environ[floor.GATE_ENV], os.environ["PSXD_SELF_RED"]
            floor._git(repo, "add", "-A")
            floor._commit(repo, "a bank")
            # CI: the head of the range against its base
            rc, out = gate("ci", "%s..HEAD" % start)
            check("gate --ci: an admitted commit", (rc, out) == (0, "GATE OK (ci; 1 commit(s))\n"), out)
            put("src/walk.c", 'INCLUDE_ASM("asm/nonmatchings/a", Walk);\n')
            floor._capture(floor.cmd_debt, repo, update=True)
            floor._git(repo, "add", "-A")
            floor._commit(repo, "the body leaves")
            put("src/walk.c", floor.C_DEBT["goto"][0].replace("goto loop;", "goto loop;\n    // !FAKE: again\n    goto loop;"))
            floor._capture(floor.cmd_debt, repo, update=True)
            floor._git(repo, "add", "-A")
            floor._commit(repo, "the body is back, with one more marked goto")
            rc, out = gate("ci", "HEAD~2..HEAD")
            check("gate --ci: a counted kind over a range passes", (rc, out) == (0, "GATE OK (ci; 2 commit(s))\n"), out)
            put("src/walk.c", (repo / "src/walk.c").read_text() + floor.C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            put(floor.BASELINE, ((repo / floor.BASELINE).read_text() + "1 pin\n1 pin-unmarked\n"))
            floor._git(repo, "add", "-A")
            floor._commit(repo, "a commit that no hook saw")
            rc, out = gate("ci", "HEAD~1..HEAD")
            check("gate --ci: a commit that skipped the hook fails", rc == 1 and
                  "GATE FAIL debt: pin-unmarked is `down` and its total rose: 0 -> 1 (src/walk.c 0 -> 1)" in out, out)
            rc, out = gate("ci", "HEAD~3..HEAD")
            check("gate --ci: and so does every range that ends there", rc == 1 and "pin-unmarked is `down` and its total rose" in out, out)
            rc, out = gate("ci", "0000000000000000000000000000000000000000..HEAD")
            check("gate --ci with no base: the tree of the head", rc == 0 and "no base: the tree of the head only" in out, out)
            rc, out = gate("ci", "HEAD..nowhere")
            check("gate --ci: a range that names no commit", rc == 1 and "GATE FAIL gate: HEAD..nowhere names no commit" in out, out)
            rc, out = gate("ci", "nowhere..HEAD")
            check("gate --ci: a base that names no commit judges nothing, so it fails", rc == 1 and "GATE FAIL gate: the base nowhere "
                  "names no commit of this repository" in out, out)
            rc, out = gate("push", "HEAD~1..HEAD")
            check("gate --push: the range, as --ci", rc == 1 and "pin-unmarked is `down` and its total rose" in out, out)
            cwd = os.getcwd()
            try:
                os.chdir(repo.parent)
                rc, out = floor._capture(floor.cmd_gate, repo.name, "ci", "HEAD~2..HEAD~1")
            finally:
                os.chdir(cwd)
            check("gate: a relative --repo reads the same repository", rc == 0 and out.startswith("GATE INFO the work tree is not at")
                  and out.endswith("GATE OK (ci; 1 commit(s))\n"), out)
            # a commit with no parent, put in the place of the history: the base judges it
            undo()
            good = floor._rev(repo, "HEAD~1")
            floor._git(repo, "checkout", "-q", "--orphan", "fresh", good)
            put("src/walk.c", (repo / "src/walk.c").read_text() + floor.C_DEBT["pin-unmarked"][0].replace("Walk", "Run"))
            put(floor.BASELINE, ((repo / floor.BASELINE).read_text() + "1 pin\n1 pin-unmarked\n")
                .replace("mode asm down", "mode asm count"))
            floor._git(repo, "add", "-A")
            floor._commit(repo, "a history of one commit")
            rc, out = gate("ci", "%s..HEAD" % good)
            check("gate --ci: a commit with no parent is judged against the base", rc == 1 and "pin-unmarked is `down` and its total rose: 0 -> 1"
                  in out and "GATE FAIL policy: asm went from down to count" in out, out)
    finally:
        floor._sibling_run = keep


def self_test_judge(check) -> None:
    """What decides, and what a change cannot move: a merge is judged by its two ends, a file has one reader of its
    lines, and the standard library is the interpreter's."""
    keep = floor._sibling_run
    if not floor.sibling().is_file():
        floor._sibling_run = lambda repo, *args: (0, [])  # noqa: E731
    policy = "".join("mode %s down\n" % k for k in floor.KINDS)
    feed = floor.parse_baseline(policy + "# a note\x0craise goto 5 2026-01-02 behind a form feed\n# a note raise pin 5 2026-01-02 behind a separator\n")
    check("a line ends at a newline and at nothing else", feed.raises == [] and len(feed.head) == 2, feed.raises)
    rows, errs = floor.read_tsv("x.tsv", ("a", "b"), tree=type("T", (), {"read": lambda self, p: "a\tb\n1\t2\x0c3\n"})())
    check("a ledger row holds a form feed, it does not end at one", [(r["a"], r["b"]) for r in rows] == [("1", "2\x0c3")] and not errs, (rows, errs))
    try:
        with tempfile.TemporaryDirectory() as td:
            repo = floor._repo(td)
            put = lambda rel, text: ((repo / rel).parent.mkdir(parents=True, exist_ok=True), (repo / rel).write_text(text))  # noqa: E731
            gate = lambda mode, rng=None: floor._capture(floor.cmd_gate, repo, mode, rng)  # noqa: E731
            body = lambda name, n: "s32 %s(s32 n) {\n%s    return n;\n}\n" % (name, "    n += *(s32 *)(n + 4);\n" * n)  # noqa: E731

            def rows_of_now():
                bl = floor.parse_baseline((repo / floor.BASELINE).read_text())
                put(floor.BASELINE, floor.baseline_text(bl, floor._kind_totals(floor.debt_counts(repo, bl.skip, floor.Tree(repo, None, untracked=True)))))

            def merge(first, second, msg):
                floor._git(repo, "add", "-A")
                made = floor._git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit-tree", floor._git(repo, "write-tree").stdout.strip(),
                            "-p", first, "-p", second, "-m", msg).stdout.strip()
                floor._git(repo, "reset", "-q", "--hard", made)
                return made

            put("src/a.c", 'INCLUDE_ASM("asm/nonmatchings/a", Run);\n')
            put("src/b.c", 'INCLUDE_ASM("asm/nonmatchings/b", Jump);\n')
            floor._git(repo, "add", "-A")
            put(floor.BASELINE, floor.first_baseline(repo))
            floor._commit(repo, "the floor")
            base = floor._rev(repo, "HEAD")
            put("src/a.c", body("Run", 1))
            rows_of_now()
            floor._commit(repo, "Run, with one offset")
            left = floor._rev(repo, "HEAD")
            floor._git(repo, "reset", "-q", "--hard", base)
            put("src/b.c", body("Jump", 1))
            rows_of_now()
            floor._commit(repo, "Jump, with one offset")
            right = floor._rev(repo, "HEAD")
            put("src/a.c", body("Run", 1))
            rows_of_now()
            merge(left, right, "a merge of two banks")
            rc, out = gate("ci", "%s..HEAD" % base)
            check("gate --ci: a merge of two admitted branches passes", (rc, out) == (0, "GATE OK (ci; 3 commit(s))\n"), out)
            floor._git(repo, "reset", "-q", "--hard", left)
            (repo / ".git" / "MERGE_HEAD").write_text(right + "\n")
            put("src/b.c", body("Jump", 1) + floor.C_DEBT["pin-unmarked"][0])
            rows_of_now()
            floor._git(repo, "add", "-A")
            rc, out = gate("staged")
            check("gate --staged: a merge in progress is judged against HEAD", rc == 1 and "pin-unmarked is `down` and its total rose: 0 -> 1" in out, out)
            (repo / ".git" / "MERGE_HEAD").unlink()
            floor._git(repo, "reset", "-q", "--hard", left)
            row = "main\tRun\tsrc/a.c\thand-asm\tsrc/a.c:1\t2026-01-02\tdeveloper\n"
            put(floor.ASM_EVIDENCE, "\t".join(floor.ASM_COLUMNS) + "\n" + row)
            floor._commit(repo, "the developer's assembly row")
            put(floor.ASM_EVIDENCE, "\t".join(floor.ASM_COLUMNS) + "\n" + row + row)
            floor._git(repo, "add", "-A")
            acts = floor.developer_acts(floor.Tree(repo, "HEAD"), floor.Tree(repo, floor.INDEX))
            check("a second copy of a ledger row is a new act", len(acts) == 1 and "the row of Run src/a.c" in acts[0], acts)
            floor._git(repo, "reset", "-q", "--hard", left)
            # the developer's acts are read by the reader of the baseline, line for line and one for one
            line = "raise offset 1 2026-01-02 the first one\n"
            put(floor.BASELINE, (repo / floor.BASELINE).read_text() + line)
            floor._commit(repo, "the developer's raise")
            put(floor.BASELINE, (repo / floor.BASELINE).read_text() + line)
            floor._git(repo, "add", "-A")
            acts = floor.developer_acts(floor.Tree(repo, "HEAD"), floor.Tree(repo, floor.INDEX))
            check("a second copy of a `raise` line is a new act", acts == ["`raise offset 1 2026-01-02 the first one` in config/debt-baseline.txt"], acts)
            floor._git(repo, "reset", "-q", "--hard", "HEAD")
            put(floor.BASELINE, (repo / floor.BASELINE).read_text() + "# a note\x0craise offset 9 2026-01-02 behind a form feed\n")
            floor._git(repo, "add", "-A")
            bl = floor.parse_baseline(floor.Tree(repo, floor.INDEX).read(floor.BASELINE))
            check("a `raise` behind a form feed raises nothing and is no act", len(bl.raises) == 1 and
                  floor.developer_acts(floor.Tree(repo, "HEAD"), floor.Tree(repo, floor.INDEX)) == [], bl.raises)
            # a module of the checkout beside the tool is not the standard library
            put(floor.VENDORED, pathlib.Path(floor.__file__).read_text(encoding="utf-8"))
            put("tools/bisect.py", "import os\nprint('GATE OK (a module of the checkout)')\nos._exit(0)\n")
            r = subprocess.run([sys.executable, str(repo / floor.VENDORED), "--version"], capture_output=True, text=True, cwd=str(repo),
                               env=dict(os.environ, PYTHONPATH=str(repo / "tools")))
            check("a module of the checkout does not stand in for the standard library", (r.returncode, r.stdout.strip()) == (0, floor.VERSION),
                  r.stdout + r.stderr[-200:])
    finally:
        floor._sibling_run = keep


def self_test_toolchain(check) -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = floor._repo(td)
        (repo / "config").mkdir()
        check("toolchain: no file", floor.toolchain_rows(repo) is None and cmd_toolchain_quiet(repo) == 0)
        (repo / "refs-tool").mkdir()
        tool = floor._repo(repo / "refs-tool")
        (tool / "a.py").write_text("x = 1\n")
        floor._commit(tool, "tool")
        head = floor._git(tool, "rev-parse", "HEAD").stdout.strip()
        (repo / "cc1.bin").write_bytes(b"cc1")
        digest = hashlib.sha256(b"cc1").hexdigest()
        rows = "\t".join(floor.TOOL_COLUMNS) + "\nsplitter\tgit\t%s\trefs-tool\ncc1\tsha256\t%s\tcc1.bin\nlost\tgit\t%s\tnowhere\n" % (
            head, digest, head)
        (repo / floor.TOOLCHAIN).write_text(rows)
        check("toolchain: at the pin, clean", [r[0] for r in floor.toolchain_rows(repo)] == ["OK", "OK", "MISSING"], floor.toolchain_rows(repo))
        check("toolchain: a missing path is not a failure", cmd_toolchain_quiet(repo) == 0)
        (tool / "a.py").write_text("x = 2\n")
        got = floor.toolchain_rows(repo)
        check("toolchain: a dirty checkout fails", got[0][0] == "FAIL" and "local changes" in got[0][2], got)
        (tool / "a.py").write_text("x = 1\n")
        (repo / floor.TOOLCHAIN).write_text(rows.replace(head, "0" * 40, 1).replace(digest, "0" * 64))
        got = floor.toolchain_rows(repo)
        check("toolchain: off the pin, off the hash", [r[0] for r in got[:2]] == ["FAIL", "FAIL"] and cmd_toolchain_quiet(repo) == 1, got)
        (repo / floor.TOOLCHAIN).write_text("\t".join(floor.TOOL_COLUMNS) + "\nx\tdocker\ty\tz\n")
        check("toolchain: a kind that is no kind", floor.toolchain_rows(repo)[0][0] == "FAIL")
        (tool / "a.out").write_text("built in place\n")
        (repo / "plain").mkdir()                       # a folder of the game, not a checkout of the tool
        (repo / "README.md").write_text("x\n")          # the game has a HEAD of its own, which is not the tool's
        floor._commit(repo, "the game")
        (repo / floor.TOOLCHAIN).write_text("\t".join(floor.TOOL_COLUMNS) + "\nshort\tgit\t%s\trefs-tool\nupper\tgit\t%s\trefs-tool\n"
                                      "tag\tgit\tv1.0\trefs-tool\nplain\tgit\t%s\tplain\n" % (head[:12], head.upper(), head))
        got = floor.toolchain_rows(repo)
        check("toolchain: a short pin, an upper-case pin, a tag, a folder that is no checkout",
              [r[0] for r in got] == ["OK", "OK", "FAIL", "MISSING"] and "tag can move" in got[2][2], got)


def cmd_toolchain_quiet(repo) -> int:
    return floor._capture(floor.cmd_toolchain, repo)[0]


def self_test_guard(check) -> None:
    rules = floor.parse_guard(floor.GUARD_SELF)
    check("guard: the rules, in order", [r[:2] for r in rules] == [("allow", "path"), ("deny", "path"), ("deny", "path"),
                                                                    ("deny", "bash"), ("deny", "bash")], rules)
    check("guard: the doctor's view of a bad file", len(floor.guard_errors(floor.GUARD_SELF)) == 2, floor.guard_errors(floor.GUARD_SELF))
    check("guard: an allow row with no say cell is a rule; a pattern that matches every command is an error",
          floor.guard_errors("allow\tpath\tasm/README.md\ndeny\tbash\t\\bmake\\s+expected|\tAsk.\n")
          == ["line 2: the pattern matches the empty command, so it matches every command"])
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td).resolve()
        ev = lambda tool, **inp: {"tool_name": tool, "tool_input": inp, "cwd": str(root)}  # noqa: E731
        cases = [
            ("an Edit under a denied folder", ev("Edit", file_path=str(root / "asm/main/a.s")), "asm/ is generated"),
            ("a Write by a relative path", ev("Write", file_path="config/check.main.sha"), "the build writes"),
            ("the first matching row wins", ev("Edit", file_path=str(root / "asm/README.md")), None),
            ("a file no rule names", ev("Edit", file_path=str(root / "src/a.c")), None),
            ("a file outside the repository", ev("Edit", file_path="/somewhere/asm/a.s"), None),
            ("a Bash command a rule names", ev("Bash", command="cd x && make expected"), "ask the developer"),
            ("a Bash command no rule names", ev("Bash", command="make build"), None),
            ("a path rule does not read a command", ev("Bash", command="cat asm/main/a.s"), None),
            ("another tool", ev("Read", file_path=str(root / "asm/a.s")), None),
        ]
        for name, event, want in cases:
            got = floor.guard_decision(event, rules, root)
            check("guard: " + name, (got is None) if want is None else (got or "").startswith(want), got)
        floor._git(root, "init", "--quiet")
        (root / "config").mkdir()
        (root / floor.GUARD).write_text(floor.GUARD_SELF)
        import io
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        rc, out = floor._capture(floor.guard_hook, io.StringIO(json.dumps(cases[0][1])))
        answer = json.loads(out)["hookSpecificOutput"] if out else {}
        check("guard --hook: a denial is one JSON object, exit 0", rc == 0 and answer.get("permissionDecision") == "deny"
              and answer.get("hookEventName") == "PreToolUse" and "asm/ is generated" in answer.get("permissionDecisionReason", ""), out)
        for name, stdin in (("an allowed call", json.dumps(cases[3][1])), ("an event with no cwd", json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})),
                            ("another tool", json.dumps({"tool_name": "Read", "tool_input": {"file_path": "asm/a.s"}, "cwd": str(root)}))):
            check("guard --hook: %s prints nothing, exit 0" % name, floor._capture(floor.guard_hook, io.StringIO(stdin)) == (0, ""))
        for name, stdin in (("bad JSON", "{not json"), ("no event", ""), ("a list", "[1]"), ("null", "null"),
                            ("an input that is no object", json.dumps({"tool_name": "Edit", "tool_input": "x"})),
                            ("a path that is a number", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": 7}, "cwd": str(root)})),
                            ("a path with a NUL", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "asm/a\0.s"}, "cwd": str(root)}))):
            rc, out = floor._capture(floor.guard_hook, io.StringIO(stdin))
            check("guard --hook: %s is refused: the guard fails closed" % name, rc == 0 and '"permissionDecision": "deny"' in out
                  and ("the guard failed on this call" in out or "asm/ is generated" in out), out)
        # a linked worktree is guarded by its own rules, also while the session's project is the main checkout
        (root / "README.md").write_text("x\n")
        floor._commit(root, "rules")
        with tempfile.TemporaryDirectory() as other:
            tree = pathlib.Path(other).resolve() / "wt"
            floor._git(root, "worktree", "add", "--quiet", "--detach", str(tree))
            os.environ["CLAUDE_PROJECT_DIR"] = str(root)
            edit = {"tool_name": "Edit", "tool_input": {"file_path": str(tree / "asm/main/a.s")}, "cwd": str(tree)}
            rc, out = floor._capture(floor.guard_hook, io.StringIO(json.dumps(edit)))
            check("guard --hook: an edit in a linked worktree is refused", rc == 0 and '"deny"' in out, out)
            bash = {"tool_name": "Bash", "tool_input": {"command": "make expected"}, "cwd": other}
            rc, out = floor._capture(floor.guard_hook, io.StringIO(json.dumps(bash)))
            check("guard --hook: a call from outside a checkout falls back to the project", rc == 0 and '"deny"' in out, out)
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            floor._git(root, "worktree", "remove", "--force", str(tree))
        # a pattern that backtracks without end: the hook gives up and refuses the call
        keep, floor.GUARD_SECONDS = floor.GUARD_SECONDS, 1
        (root / floor.GUARD).write_text("deny\tbash\t(\\w+\\s*)+$\tNo.\n")
        slow = {"tool_name": "Bash", "tool_input": {"command": "echo " + "word " * 40 + "!"}, "cwd": str(root)}
        import time
        t0 = time.time()
        got = floor._capture(floor.guard_hook, io.StringIO(json.dumps(slow)))
        floor.GUARD_SECONDS = keep
        check("guard --hook: a pattern that hangs is cut off, and the call is refused", got[0] == 0 and '"deny"' in got[1]
              and "a rule ran for 1 seconds" in got[1] and time.time() - t0 < 4, (got, time.time() - t0))
        check("guard: a path through `..` is the file it reaches", floor.guard_decision(
            ev("Edit", file_path=str(root / "src/../asm/main/a.s")), rules, root) is not None)
        check("guard: no flag, and a flag that is no flag, exit 0", floor._capture(floor.main, ["guard"])[0] == 0
              and floor._capture(floor.main, ["guard", "--bogus"])[0] == 0)
        (root / floor.GUARD).unlink()
        check("guard --hook: no rules file allows the call", floor._capture(floor.guard_hook, io.StringIO(json.dumps(cases[0][1]))) == (0, ""))


def _check(name, ok, detail=None):
    assert ok, name if detail is None else "%s — %r" % (name, detail)


@pytest.fixture(autouse=True)
def _project_dir():
    saved = os.environ.get("CLAUDE_PROJECT_DIR")
    yield
    if saved is not None:
        os.environ["CLAUDE_PROJECT_DIR"] = saved


def test_debt():
    self_test_debt(_check)


def test_bodies():
    self_test_bodies(_check)


def test_files():
    self_test_files(_check)


def test_view():
    self_test_view(_check)


def test_tree():
    self_test_tree(_check)


def test_markers():
    self_test_markers(_check)


def test_gate():
    self_test_gate(_check)


def test_judge():
    self_test_judge(_check)


def test_toolchain():
    self_test_toolchain(_check)


def test_guard():
    self_test_guard(_check)
