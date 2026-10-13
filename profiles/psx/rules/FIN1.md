A source file has two states. It is matched when the build is byte-identical with every function of the file in C.
It is finished when it is matched and it has no readability debt. Until then, call it matched and name its debt.

A finished file meets six conditions:

1. Matched. The hash check of the build passes with the file in C.
2. No forced code. No register pin and no `goto` that copies the assembly. One that the match needs has a `// !FAKE:` reason.
3. Typed. No field read by its offset, and no address without a symbol. Each type has one definition, in a header.
4. Named. No placeholder name. Each other name has an accepted row in `config/names.tsv`.
5. Plain C. No macro that hides a body. No assembly without a row in `config/asm-evidence.tsv`.
6. Formatted. The formatter of the repository makes no change.

`python3 tools/psxd_floor.py debt` counts conditions 2 to 5 for each file against `config/debt-baseline.txt`.

- Run `python3 tools/psxd_floor.py debt --update` in the commit that changes a count. A row that is not equal fails.
- Bank a function when it matches. Its cleanup is separate work after the bank, and a later commit lowers the count.
- The gate refuses a pin, a `goto` or an empty assembly statement with no `// !FAKE: <reason>` comment.
- The gate also refuses assembly with no row in `config/asm-evidence.tsv`. Each other kind is counted and shown.
- A kind in `down` never rises. Only the developer raises a count, with `debt --raise`.
- Never report a matched file as finished, and never report a debt count from memory. Run the tool.
- `python3 tools/psxd_floor.py debt --files` prints the state of each file. Only the README block of the tool counts finished files.
- The published progress number counts matched code. It says nothing about finished files.
