# The C corpus (compile-and-compare ground truth)

CC0 1.0. Small C functions written for this repository, compiled with two PS1-era compilers and compared word for
word. No game byte, no SDK text: every target is built from `truth/<id>/truth.c` at test time and nothing built is
committed.

- `truth/<id>/truth.c` is the readable version of one function; `ctx.h` is what a drafter would be given; `hidden.h`
  (class `struct-absent`) holds types the drafter would not be given. `twin.<kind>.c` is a fake twin: the same bytes
  reached through a pinned register, a `goto`, an offset cast or a type of its own, or the same masked words through
  another symbol or a bare address.
- `trial/<id>/pinned.c` is one function that matches itself with two register pins. The match needs one of them.
  The trial tool of the floor (`scripts/floor.py trial`) must drop the other one, and keep and record the first.
- `probe.py` compiles and compares: words with relocated fields masked, and then the relocations themselves, which
  the mask hides. `lint.py` finds the constructs the twins are made of. `corpus.py check` is tier 5a: every truth
  matches itself, every mutant fails, every twin matches and is flagged, no truth is flagged.
- `Dockerfile` adds one layer over the profile image with two compilers from decompals/old-gcc, by sha256. The
  profile image and psxdecomp still pin no compiler: a game pins its own in its phase 1.4.
- Tier 5a (`run.sh`, weekly beside tier 1b) needs Docker; `lint.py --self-test` and `corpus.py --self-test` need
  only Python and run with tier 0.
