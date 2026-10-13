A name is a claim about what the code does. A byte-identical build proves the behaviour of the code. It proves no name.

1. Keep the placeholder name until there is evidence. An unnamed function is better than a wrong name. A function
   that matches is banked and pushed under the name it has: no check asks for a name. A wrong name is debt.
2. Record the name in `config/names.tsv` in the commit that uses it. `python3 tools/psxd_floor.py names` checks the file.
3. Give the evidence as `<class>:<path>:<line>`. The line must show the fact to a reader who opens the file.
4. Use `provisional` for a name that one source supports. Use `accepted` when a person or a second source agrees.
5. Mark a name that proved wrong as `rejected`, and write the reason. Do not use that name again.
6. Give an SDK function the exact name of its library signature. Do not invent a name for it.
7. Take a game term from a source in `config/refs.toml`, such as a manual or a wiki. Cite that row as the evidence.

| Evidence class | The fact that it cites |
|---|---|
| `psyq-sig` | a library signature that matches the function |
| `string` | a string that the code prints or compares |
| `xref` | a caller or a callee with an accepted name |
| `loadmap` | a load address or an overlay table entry |
| `exe-header` | a field of the executable header |
| `prior-art` | a name in a project that `docs/prior-art.md` lists, with its commit |
| `debug-symbol` | a symbol in a debug build or in another release of the game |
| `refs` | a row of `config/refs.toml`: a manual, a wiki or a symbol file that gives the game's own word |
| `human` | a decision that a person wrote down, in a file of the repository |
| `test` | a test or a script whose result shows what the code does |
| `oracle` | another build of the game, such as a debug build or a port, that holds the same code |
| `debugger` | a note of a debugger or emulator session that shows the behaviour |

This rule is the default. When `docs/prior-art.md` records the conventions of an upstream project, those conventions
replace the form of the names. They do not replace the evidence.
