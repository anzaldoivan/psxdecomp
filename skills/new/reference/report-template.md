# Prior art — leads, their status, and their credit

*Drafted by psxdecomp S3 on <date>; confirmed at the S4 gate. The shape is mmx6's `docs/prior-art.md` (2026-10-01).*

Every fact this project takes from outside its own bytes is a row here, with its source, licence and status.
Status ladder: `lead` → `consistent-with-bytes` (checked against our dump or an oracle; cite the check) →
`proven-at-gate` (a green byte gate, or a runtime proof). Nothing below `proven-at-gate` is banked on, recorded as
fact, or used as a name. `rejected` keeps a lead the developer turned down, with the reason.

## Sources

| Source | Licence | Class | Use allowed |
|---|---|---|---|
| [owner/repo](https://…) — one line on what it is | MIT | adapt | adapt code with attribution in THIRD_PARTY.md |
| … | none | facts | facts only, never copied |

Classes: `adapt` · `copyleft` (adapt only into a licence-compatible repo) · `facts` · `public` · `byo` · `link`
(`docs/ops/refs.md` after S9).

## Leads

| # | Lead | Source | Status | Evidence / how to verify | Phase |
|---|---|---|---|---|---|
| L1 | Compiler: <triple> (a sibling's pin) | owner/repo@<sha> | lead | Verify: the 1.4 ladder runs it first; a probe matches or refutes | 1.4 |
| L2 | SDK: PsyQ <v> — <n> `Ps` stamps | own bytes (S2) | consistent-with-bytes | `medium.json psyq`; ghidra_psx_ldr's detection at import is the final word | 1.2 |

## Upstream revisions read

`owner/repo` `<short sha>` (<date>) · …
