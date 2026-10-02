#!/usr/bin/env python3
"""answers.py — the decomp-architect answers file (13 keys) and psxdecomp's own answers file (the same lines plus a
few PSXDECOMP_ keys).

    answers.py template                              the kit's empty template (equal to the kit's --answers-template)
    answers.py check FILE [--allow-no-dump]          every key present; DUMP_PATH absolute (or empty with the flag)
    answers.py split FILE --kit-out K [--extra-out E.json]
                                                     write the kit's 13-key file and psxdecomp's extras
    answers.py render IN.json --out FILE             render from a JSON object (S4 writes the confirmed values)
    answers.py --self-test                           round trips; mmx6's file byte for byte when $PSXDECOMP_MMX6_ANSWERS

Format: one `KEY: value` line each; `#` starts a comment. Line 1 is the kit's header; comment lines between it and the
first key's description are kept as the provenance note (round trips are byte-identical).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

HEADER = "# decomp-architect answers — one `KEY: value` line each; `#` starts a comment. INSTALL_DATE is optional."
KEYS = [
    ("GAME_TITLE", "the game's title"),
    ("PLATFORM", "the console or platform"),
    ("GAME_SERIAL", "region and serial printed on the medium"),
    ("TARGET_BINARY", "the main executable's file name on the medium"),
    ("DUMP_PATH", "ABSOLUTE path of your own dump, outside the repository (machine-local; never copied)"),
    ("CONTAINER_LAYOUT", "one line: how code is packaged on the medium (archives, overlays, compression)"),
    ("SDK_EVIDENCE", "the SDK/compiler-era evidence found (version stamps, strings, a loader's detection)"),
    ("COMPILER_FAMILY", "the candidate compiler family — a candidate set, not the pin"),
    ("COMMUNITY_WORK", "prior public work found, or 'none found on <date>'"),
    ("PROJECT_GOALS", "your goals, one paragraph"),
    ("LICENSE_CHOICE", "the license for tools and docs, and the statement made over the decompiled source"),
    ("AI_DISCLOSURE", "one project-level sentence disclosing how AI is used"),
    ("PUBLIC_OR_PRIVATE", "the day-one visibility (the firewall applies either way)"),
]
KEY_NAMES = [k for k, _ in KEYS]
OPTIONAL = {"INSTALL_DATE"}
# psxdecomp's extras: never passed to the kit.
EXTRAS = {
    "PSXDECOMP_CONSOLE": "the console profile (v1: psx)",
    "PSXDECOMP_PROJECT_NAME": "the repository / PA3 project name (a slug)",
    "PSXDECOMP_REGION_VERSION": "region and version to target, e.g. 'USA v1.1'",
    "PSXDECOMP_BYO_PSYQ_PATH": "optional local folder of your own PsyQ SDK (never fetched, never committed)",
}


CANDIDATE = "Candidate (S4 %s; superseded by the pinned toolchain triple once phase 1.4 pins it): "


def scope_candidate(values: dict, date: str | None = None) -> dict:
    """Label COMPILER_FAMILY as a dated candidate at write time: the kit copies the value word for word into
    docs/ops/decomp-environment.md and its install record, so the label travels with every copy. Idempotent."""
    v = dict(values)
    cf = v.get("COMPILER_FAMILY", "")
    if cf and not cf.startswith(CANDIDATE.split(" %s")[0]):
        v["COMPILER_FAMILY"] = CANDIDATE % (date or common.today()) + cf
    return v


def parse(text: str) -> tuple[dict, list[str]]:
    """Return (values in file order, provenance comment lines)."""
    values, note, seen_key = {}, [], False
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        line = raw.rstrip("\n")
        if line.startswith("#"):
            if i == 0 and line.strip() == HEADER:
                continue
            is_desc = any(line.startswith("# %s — " % k) for k in list(KEY_NAMES) + list(EXTRAS) + ["INSTALL_DATE"])
            if not seen_key and not is_desc and i > 0:
                note.append(line)
            continue
        if not line.strip():
            continue
        if ":" not in line:
            raise common.Fail("answers line %d is not `KEY: value`: %r" % (i + 1, line[:60]))
        k, v = line.split(":", 1)
        k = k.strip()
        if k in values:
            raise common.Fail("answers key %s appears twice" % k)
        values[k] = v.strip()
        seen_key = True
    return values, note


def render(values: dict, note: list[str] | None = None, extras: bool = False) -> str:
    out = [HEADER] + list(note or [])
    for k, d in KEYS:
        out += ["# %s — %s" % (k, d), "%s: %s" % (k, values.get(k, ""))]
    if values.get("INSTALL_DATE"):
        out += ["# INSTALL_DATE — optional; the install date to record", "INSTALL_DATE: %s" % values["INSTALL_DATE"]]
    if extras:
        for k, d in EXTRAS.items():
            if k in values:
                out += ["# %s — %s" % (k, d), "%s: %s" % (k, values[k])]
    return "\n".join(out) + "\n"


def template() -> str:
    return "\n".join([HEADER] + sum((["# %s — %s" % (k, d), "%s: " % k] for k, d in KEYS), [])) + "\n"


def check(values: dict, allow_no_dump: bool = False) -> list[str]:
    errs = []
    for k in KEY_NAMES:
        v = values.get(k, "")
        if k == "DUMP_PATH":
            if not v and allow_no_dump:
                continue
            if not v or not os.path.isabs(os.path.expanduser(v)):
                errs.append("DUMP_PATH must be an absolute path outside the repository")
        elif not v:
            errs.append("%s is empty" % k)
    unknown = [k for k in values if k not in KEY_NAMES and k not in EXTRAS and k not in OPTIONAL]
    errs += ["unknown key %s" % k for k in unknown]
    con = values.get("PSXDECOMP_CONSOLE", "psx")
    if con != "psx":
        errs.append("console %r is not yet supported (v1 is PS1 only)" % con)
    return errs


def split(values: dict) -> tuple[dict, dict]:
    kit = {k: values[k] for k in KEY_NAMES + list(OPTIONAL) if k in values}
    extra = {k: values[k] for k in EXTRAS if k in values}
    return kit, extra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["template", "check", "split", "render"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--allow-no-dump", action="store_true")
    ap.add_argument("--kit-out")
    ap.add_argument("--extra-out")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    try:
        if a.cmd == "template":
            sys.stdout.write(template())
            return 0
        if a.cmd == "render":
            data = json.loads(common.read(a.file))
            text = render(data.get("values", data), data.get("note"), extras=bool(data.get("extras")))
            if a.out:
                common.write(a.out, text)
            else:
                sys.stdout.write(text)
            return 0
        values, note = parse(common.read(a.file))
        if a.cmd == "check":
            errs = check(values, a.allow_no_dump)
            for e in errs:
                print("REFUSE %s" % e)
            print("ANSWERS %s %d keys" % ("OK" if not errs else "FAIL", sum(k in values for k in KEY_NAMES)))
            return 1 if errs else 0
        if a.cmd == "split":
            errs = check(values, a.allow_no_dump)
            if errs:
                for e in errs:
                    print("REFUSE %s" % e)
                return 1
            kit, extra = split(values)
            common.write(a.kit_out, render(kit, note))
            if a.extra_out:
                common.write(a.extra_out, json.dumps(extra, indent=2, sort_keys=True) + "\n")
            print("ANSWERS SPLIT kit %d keys, extras %d" % (len(kit), len(extra)))
            return 0
    except common.Fail as e:
        print("FAIL %s" % e)
        return 1
    ap.print_help()
    return 2


def self_test() -> int:
    ok = True
    fx = common.PLUGIN_ROOT / "fixtures" / "answers.psx.txt"
    text = common.read(fx)
    v, note = parse(text)
    ok &= render(v, note, extras=True) == text
    print("  fixture round trip: %s" % ("byte-identical" if render(v, note, extras=True) == text else "DIFFERS"))
    ok &= check(v, allow_no_dump=True) == []
    kit, extra = split(v)
    ok &= list(kit) == [k for k in KEY_NAMES if k in kit] and "PSXDECOMP_CONSOLE" in extra
    ok &= parse(template())[0] == {k: "" for k in KEY_NAMES}
    bad = dict(v, PSXDECOMP_CONSOLE="n64")
    ok &= any("not yet supported" in e for e in check(bad, True))
    ok &= any("DUMP_PATH" in e for e in check(dict(v, DUMP_PATH="relative/game.cue")))
    once = scope_candidate(v, "2026-10-01")
    ok &= once["COMPILER_FAMILY"] == CANDIDATE % "2026-10-01" + v["COMPILER_FAMILY"]
    ok &= scope_candidate(once, "2027-01-01") == once and scope_candidate({}) == {} and v == parse(text)[0]
    print("  scope_candidate: %s" % once["COMPILER_FAMILY"][:40])
    mmx6 = os.environ.get("PSXDECOMP_MMX6_ANSWERS")
    if mmx6 and os.path.isfile(mmx6):
        t = common.read(mmx6)
        mv, mn = parse(t)
        same = render(mv, mn) == t
        print("  mmx6 answers.txt: %s" % ("byte-identical" if same else "DIFFERS"))
        ok &= same
    kit_py = os.environ.get("PSXDECOMP_KIT")
    if kit_py and os.path.isfile(os.path.join(kit_py, "install.py")):
        r = common.run([sys.executable, os.path.join(kit_py, "install.py"), "--answers-template"], check=False)
        same = r.stdout == template()
        print("  kit --answers-template: %s" % ("equal" if same else "DIFFERS"))
        ok &= same
    return common.self_test_banner("answers", ok)


if __name__ == "__main__":
    sys.exit(main())
