#!/bin/sh
# Writes a synthetic game repository into the current folder for the hygiene evals: build.sh labelled|raw|unpinned.
# Modelled on a real PA3 + kit game repo after its compiler pin, anonymised (project demo6, no game bytes). The stale
# and foreign text is deliberate and lives only here, never in a tracked .md: PROJECT_CONTEXT keeps the bootstrap
# candidate ladder (a constitution is never edited), docs/kit/ carries BFM's calibration under bare ids.
#   labelled  today's psxdecomp output: the "Candidate (S4 …)" label and the HOW_WE_WORK scope line
#   raw       the same text as it was before the label and the scope line
#   unpinned  labelled, before phase 1.4: no compiler-pin.md, no Makefile triple
set -eu
v=${1:?usage: build.sh labelled|raw|unpinned}
case $v in labelled|raw|unpinned) ;; *) echo "unknown variant $v" >&2; exit 2;; esac
mkdir -p docs/ops docs/kit rules config src

cat > PROJECT_CONTEXT.md <<'EOF'
# Project context — demo6

A matching decompilation of demo6 (PlayStation, USA SLUS-99999): byte-identical C, verified by the build.

## Lineage

demo6 shares its engine lineage with its predecessor demo4, which has an active matching decompilation.
demo4's pin (gcc 2.6.3 cc1 + aspsx 2.63) is the first candidate, a lead, not a fact.

## Decisions

| Area | Decision | Rejected | Why |
|---|---|---|---|
| Compiler | A PsyQ-era cc1 candidate ladder, gcc 2.6.3 + aspsx 2.63 first, then gcc 2.7.2 builds; pinned in phase 1.4 | Guessing one compiler | The predecessor's pin is the strongest lead |
| Splitter | splat with per-binary configs | A bespoke splitter | The community standard |
EOF

if [ "$v" = raw ]; then cand="PsyQ-era cc1 ladder: gcc 2.6.3 + aspsx 2.63 first, then gcc 2.7.2"
else cand="Candidate (S4 2026-06-02; superseded by the pinned toolchain triple once phase 1.4 pins it): PsyQ-era cc1 ladder: gcc 2.6.3 + aspsx 2.63 first, then gcc 2.7.2"; fi
if [ "$v" = unpinned ]; then pin="not yet pinned (phase 1.4 measures the ladder)"
else pin="gcc2.95.2-psx-aspsx2.86 (docs/ops/compiler-pin.md)"; fi
cat > docs/ops/decomp-environment.md <<EOF
# Decomp environment

| Item | Value |
|---|---|
| Host | macOS arm64, Docker build container |
| Pinned toolchain triple | $pin |
| Candidate compiler family | $cand |
| Splitter | splat 0.27 |
EOF

if [ "$v" != unpinned ]; then
cat > docs/ops/compiler-pin.md <<'EOF'
# Compiler pin — demo6

## Pin (phase 1.4 T7, 2026-09-14)

- Triple: `gcc2.95.2-psx-aspsx2.86` = cc1 gcc 2.95.2-psx (old-gcc 0.17) `-O2 -G0 -msoft-float -funsigned-char`
  then maspsx `--aspsx-version=2.86 --expand-div`, then GNU as. The Makefile default `TRIPLE`, used by every C unit.
- Evidence: 3 probe functions match byte for byte under this triple and under no gcc 2.6.3 or 2.7.2 rung.

## Ladder (phase 1.4, 2026-09-12)

| Triple | probe A | probe B | probe C |
|---|---|---|---|
| gcc2.6.3-psx-aspsx2.63 | FAIL 9/13 | FAIL 25/29 | FAIL 8/79 |
| gcc2.7.2-psx-aspsx2.56 | FAIL 9/13 | FAIL 25/29 | FAIL 9/79 |
| gcc2.95.2-psx-aspsx2.86 | OK | OK | OK |
EOF
cat > Makefile <<'EOF'
TRIPLE ?= gcc2.95.2-psx-aspsx2.86
CC1 := /opt/cc/2.95.2-psx/cc1
MASPSX_FLAGS := --aspsx-version=2.86 --expand-div
CFLAGS := -O2 -G0 -msoft-float -funsigned-char -quiet
EOF
fi

cat > docs/kit/calibration.md <<'EOF'
# Calibration: the matching loop

provenance: BFM phase-ends/PhaseEnd_Phase2.3.md, G6, R12

The kit was calibrated on a gcc 2.7.2 project. Build every unit through maspsx with
`--aspsx-version=2.56 --expand-div`; a unit that only matches with another assembler version is a finding.

G6: a function is never marked matched until the whole-binary hash is green from a clean rebuild.
EOF
cat > docs/kit/build-flags.md <<'EOF'
# Build flags

provenance: BFM docs/ops/toolchain.md, G6

maspsx is invoked as `maspsx --aspsx-version=2.56 --expand-div -G0`, and cc1 as gcc 2.7.2 with `-O2 -G0`.
EOF

cat > rules/G6.md <<'EOF'
# G6 — Bank before match

Every C unit is split into its bank file with its include_asm siblings planted before the first function of the
bank is decompiled; a match in an unplanted bank does not count.
EOF
cat > rules/INDEX.md <<'EOF'
# Rules

- [G6](G6.md) — bank before match.
EOF

cat > config/psxdecomp.toml <<'EOF'
# [psyq]: the PsyQ release the game links, from psxdecomp's psyq.toml (seen 2026-06-02). A lead for phase 1.4;
# the pin is phase 1.4's finding and lives in the repo's compiler-pin record.
[psyq]
stamp = "470"
version = "4.7"
ships_compiler = "no"
confidence = "measured"
status = "lead — never the pin"
EOF

{
  echo "# How we work — demo6"
  echo
  echo "## Docs map"
  echo
  echo "- Plan: phase-ends/current/PHASE_PLAN.md. Constitution: PROJECT_CONTEXT.md (never edited)."
  if [ "$v" = unpinned ]; then echo "- Environment: docs/ops/decomp-environment.md. Compiler pin: docs/ops/compiler-pin.md, once phase 1.4 writes it."
  else echo "- Environment: docs/ops/decomp-environment.md. Compiler pin: docs/ops/compiler-pin.md (phase 1.4)."; fi
  echo "- Kit calibration: docs/kit/. Rules: rules/INDEX.md."
  if [ "$v" != raw ]; then
    echo "- **This repo:** demo6 (SLUS-99999), PsyQ 4.7 (lead: config/psxdecomp.toml [psyq]); compiler: docs/ops/compiler-pin.md once phase 1.4 pins it (unpinned at bootstrap, 2026-06-02). Kit text under \"provenance: BFM …\" is calibration from gcc 2.7.2; its G/R/P ids are BFM's, not this repo's rules."
  fi
} > HOW_WE_WORK.md

printf 'void main_loop(void) {}\n' > src/main.c
