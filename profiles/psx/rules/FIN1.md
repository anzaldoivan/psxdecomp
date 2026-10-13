A source file has two states. It is matched when the build is byte-identical with every function of the file in C.
It is finished when it is matched and it has no readability debt. Until then, call it matched and name its debt.

A finished file meets six conditions:

1. Matched. The hash check of the build passes with the file in C.
2. No forced code. No register pin without a trial and a `// !FAKE:` reason, and no `goto` that copies the assembly.
3. Typed. No field read by its offset, and no address without a symbol. Each type has one definition, in a header.
4. Named. No placeholder name. Each other name has an accepted row in `config/names.tsv`.
5. Plain C. No macro that hides a body. No assembly without a row in `config/asm-evidence.tsv`.
6. Formatted. The formatter of the repository makes no change.

`python3 tools/psxd_floor.py debt` counts conditions 2 to 5 for each file against `config/debt-baseline.txt`.

- Run `python3 tools/psxd_floor.py debt --update` in the commit that changes a count. A row that is not equal fails.
- New debt arrives only with a new function body. The tool refuses a rise in a body that exists.
- A kind in `down` never rises. Only the developer raises a count, with `debt --raise`.
- Never report a matched file as finished, and never report a debt count from memory. Run the tool.
- `python3 tools/psxd_floor.py debt --files` prints the state of each file. Only the README block of the tool counts finished files.
- The published progress number counts matched code. It says nothing about finished files.
