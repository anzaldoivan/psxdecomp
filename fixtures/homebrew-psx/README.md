# The homebrew fixture (synthetic PS1 target)

CC0 1.0. `hello.s` is a two-function MIPS program with two PsyQ-shaped library stamps; `make_disc.py` builds, at test
time and into a temp folder, its PS-X EXE, an ISO9660 volume with `SYSTEM.CNF`, written as raw MODE2/2352 sectors plus
a short audio track, and a Redump-style CUE. Nothing it writes is committed; the repository's audit refuses disc
images and executables.

- Tier 1 uses `make_disc.py`'s pre-encoded words (no assembler needed).
- Tier 1b (`smoke/run.sh`, weekly) extracts the exe, splits it with splat, rebuilds it from assembly, checks the
  sha1, and checks that `hello.s` assembles to the same words.
