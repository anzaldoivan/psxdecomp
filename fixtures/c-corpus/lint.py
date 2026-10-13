#!/usr/bin/env python3
"""lint.py: the constructs that make a matching draft a fake or an unreadable match, found in its text.

  lint.py FILE...     -> one `LINT <kind> <file>:<line> <what to do>` per finding; exit 1 when there is any
  lint.py --self-test

Kinds (a finding says what the reader should doubt, not that the draft is wrong):
  register-pin   `register T x asm("$n")`: a register forced by hand
  goto           a `goto`: control flow copied from the assembly
  offset-cast    `*(T *)((u8 *)p + 0x10)`, `M2C_FIELD(...)`, or a macro whose body is one: a field read by its offset
  abs-address    `*(T *)0x1F800020`, in the body or behind a `#define`: an address with no symbol
  struct-def     a struct, union or enum body in a draft: types belong in a header, one definition each

Comments and string bodies are ignored; `#define` bodies are read, because a macro is where an address or an offset
hides from a check that blanks preprocessor lines. stdlib only.
"""
import re
import sys

NUM = r"(?:0[xX][0-9A-Fa-f]+|\d+)"
OFFX = rf"(?:\([^()]*\)|{NUM}|[A-Za-z_]\w*)(?:\s*[-+*]\s*(?:\([^()]*\)|{NUM}|[A-Za-z_]\w*))*"
OPND = r"\(?\s*&?\s*\w+\s*\)?"
PTR = r"\(\s*[\w ]+?\s*\*+\s*\)"
CHR_T = r"(?:const\s+)?(?:(?:unsigned|signed)\s+)?(?:char|[su]8)"
OFFSET_CAST = re.compile(rf"\*\s*{PTR}\s*\(\s*{PTR}\s*{OPND}\s*\+\s*{OFFX}\s*\)|\(\s*{CHR_T}\s*\*+\s*\)\s*{OPND}\s*\+\s*{OFFX}"
                         r"|\bM2C_FIELD\s*\(")
ABS_ADDRESS = re.compile(r"\(\s*[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*\s*(?:\*\s*)+\)\s*0[xX][0-9A-Fa-f]{5,}")
DEFINE = re.compile(r"^[ \t]*#[ \t]*define[ \t]+(\w+)((?:\\\n|[^\n])*)", re.M)
KINDS = {
    "register-pin": (re.compile(r'\bregister\b[^;{}]*?\b(?:asm|__asm__|__asm)\s*\(\s*"'),
                     "a pinned register: find the C that allocates it, or mark the line `// !FAKE:` with the reason"),
    "goto": (re.compile(r"\bgoto\s+\w+\s*;"), "a goto: write the loop or the branch it stands for"),
    "offset-cast": (OFFSET_CAST, "a field read by its offset: use the struct's field, or propose the field"),
    "abs-address": (ABS_ADDRESS, "an address with no symbol: declare the symbol"),
    "struct-def": (re.compile(r"\b(?:struct|union|enum)\b\s*\w*\s*\{"), "a type defined in a draft: it belongs in a header"),
}


def strip(text):
    """Comments -> spaces and string bodies -> spaces, newlines kept, so offsets and line numbers still fit."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(c + " " * (j - i - 2) + c if j - i >= 2 else text[i:j])
        else:
            j = i + 1
            out.append(c)
        i = j
    return "".join(out)


def findings(text):
    """[(kind, line, advice)] in file order. A macro whose body holds an offset cast or an address is reported where it
    is defined and at every use."""
    body = strip(text)
    out = []
    macros = {}
    for m in DEFINE.finditer(body):
        for kind in ("offset-cast", "abs-address"):
            if KINDS[kind][0].search(m.group(2)) and m.group(1) != "M2C_FIELD":
                macros[m.group(1)] = kind
    no_pp = re.sub(r"^[ \t]*#(?:\\\n|[^\n])*", lambda m: re.sub(r"[^\n]", " ", m.group(0)), body, flags=re.M)
    for kind, (rx, advice) in KINDS.items():
        for m in rx.finditer(body if kind in ("offset-cast", "abs-address") else no_pp):
            out.append((kind, body.count("\n", 0, m.start()) + 1, advice))
    for name, kind in macros.items():
        for m in re.finditer(r"\b%s\b" % re.escape(name), no_pp):
            out.append((kind, body.count("\n", 0, m.start()) + 1, "through the macro %s: %s" % (name, KINDS[kind][1])))
    return sorted(set(out), key=lambda f: (f[1], f[0]))


def counts(text):
    got = {k: 0 for k in KINDS}
    for kind, _, _ in findings(text):
        got[kind] += 1
    return got


GOOD = """#include "common.h"
// a goto in a comment, and M2C_FIELD(p, 4) too
s32 func_80010000(Entity *self) {
    const char *s = "goto here; *(s32 *)0x1F800020";
    if (self->hp < 0) {
        return self->pos.x + g_State.mode;
    }
    return (u8)self->flags + 0x10;
}
"""
BAD = {
    "register-pin": 'void f(void) {\n    register s32 x asm("$16");\n    x = 1;\n}\n',
    "goto": "void f(s32 n) {\nloop:\n    if (--n) goto loop;\n}\n",
    "offset-cast": "s32 f(void *p) {\n    return *(s16 *)((u8 *)p + 0x10);\n}\n",
    "abs-address": "void f(void) {\n    *(volatile u32 *)0x1F801070 = 0;\n}\n",
    "struct-def": "struct Entity {\n    s32 hp;\n};\ns32 f(struct Entity *e) {\n    return e->hp;\n}\n",
}


def self_test():
    assert findings(GOOD) == [], findings(GOOD)
    for kind, text in BAD.items():
        got = findings(text)
        assert [f[0] for f in got] == [kind], (kind, got)
    # the #define blind spot: an address or an offset behind a macro is found at the macro and at each use
    hid = "#define SPAD20 (*(s32 **)0x1F800020)\n#define HP(p) (*(s16 *)((u8 *)(p) + 0x10))\ns32 f(void *p) {\n    return *SPAD20 + HP(p) + HP(p);\n}\n"
    got = findings(hid)
    assert [(k, n) for k, n, _ in got] == [("abs-address", 1), ("offset-cast", 2), ("abs-address", 4), ("offset-cast", 4)], got
    assert counts(hid) == {"register-pin": 0, "goto": 0, "offset-cast": 2, "abs-address": 2, "struct-def": 0}
    assert findings("s32 f(void *p) {\n    return M2C_FIELD(p, s32 *, 8);\n}\n")[0][0] == "offset-cast"
    assert findings("s32 f(s32 a) {\n    return (s32)a + 4;\n}\nextern struct S g;\nstruct S *h(void);\n") == []
    print("SELF-TEST OK")


def main():
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    n = 0
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8", errors="replace") as f:
            for kind, line, advice in findings(f.read()):
                print("LINT %s %s:%d %s" % (kind, path, line, advice))
                n += 1
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
