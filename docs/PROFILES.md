# Profiles

v1 is PS1 only, with the structure built around per-console profiles (`profiles/<id>/`). The keys a profile fills
are in [profiles/SCHEMA.md](../profiles/SCHEMA.md); tier 0 checks every profile against that table.

| Profile | Supported | Probe | Fixture | Host recipes | Notes |
|---|---|---|---|---|---|
| `psx` | yes (v1) | `probes/psx.py`: CUE, raw/cooked tracks, ISO9660, SYSTEM.CNF, PS-X EXE, PsyQ `Ps` stamps, prologue seeds, Redump DAT | `fixtures/homebrew-psx` (synthetic, CC0) | macos-arm64, linux-amd64 | checked on X6 USA v1.1 (2026-10-01): 11 stamps, PsyQ 4.7, track 01 SHA-1 equal to Redump's |

## The PS1 probe, checked on a real disc

On mmx6's own dump (Mega Man X6 USA v1.1, read in place, 2026-10-01) the probe reported what mmx6's T0 probes recorded
by hand: `SLUS_013.95` booted by `SYSTEM.CNF`, entry `0x80054AD8`, load `0x80010000`, text `0x7F000`; 11 PsyQ
stamps, version 4.7, libnums 0 1 3 4 6 7 9 12 14 16 17, first `0x80065AB4`, last `0x8008E9F4`; track 01 SHA-1 equal to
Redump's. That is the acceptance check for any change to `probes/psx.py` (run it on your own dump; never commit the
output).

## Next consoles

The kit's `TODO(platform)` markers are the checklist. A profile is `supported = true` only when tier 1 passes on its
own synthetic fixture. Until then `/psxdecomp:new` answers "not yet supported" and installs nothing.
