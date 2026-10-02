## What this changes

<!-- One paragraph, written by a person. -->

## Checklist

- [ ] **No game or SDK bytes.** No disc image, executable, extracted data, PsyQ file or pasted disassembly;
      `python3 tools/audit_public.py` exits 0.
- [ ] **Tiers 0 and 1 green locally** (`pytest -q`, with `PSXDECOMP_KIT` set for tier 1).
- [ ] **One home per fact.** A changed fact is edited where it lives, and other docs link to it.
- [ ] **Pins.** A PA3 or kit bump changes `compat.toml` and `docs/ECOSYSTEM.md` together (docs/RELEASING.md).
- [ ] **AI use disclosed:** <!-- none / assisted / generated, and where -->
