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
| L3 | Oracle build `<id>`: carries <names, boundaries, types> | <the page that describes it> (the build: `byo`, <no copy / byo path given>) | lead | Verify: <n> function bodies are byte-identical at the mapped addresses of both builds | 1.2 |

## Conventions and contribution rules seen

| Source@sha | What exists (path) | Enforced by | AI policy (path:line) | Decision |
|---|---|---|---|---|
| owner/repo@<sha> | `docs/STYLE.md`, `.clang-format` | CI on a pull request: format | `CONTRIBUTING.md:13` | adopt / adapt / not adopted, because … |

Paths and lines only, never the documents' text. A project's style is its own decision: projects state opposite
rules, so nothing here is adopted by default.

## For a person to read

| URL | Why the agent did not read it | What to look for |
|---|---|---|
| https://… | the site refused the agent (403) | a prototype's build date, and whether the page says it holds debugging symbols |

A row stays until a person reads the page. The answer then becomes a lead or a dead end, and the row goes.

## Upstream revisions read

`owner/repo` `<short sha>` (<date>) · …
