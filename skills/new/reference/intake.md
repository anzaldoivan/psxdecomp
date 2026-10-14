# S7 — PA3's intake (in a `claude --agent plain` session)

This is PA3 3.14.2's tested path, unchanged. A plain session hands PA3's Mode 1 intake the kit's pre-answered intake.
psxdecomp supplies only the answers it already has. The intake then asks the developer only what is still open.

1. Confirm the session is a plain one. `.claude/pa.json` exists here, and `claude --agent plain` opened this session.
   If unsure, ask once with AskUserQuestion. If it is not plain, give the restart line and stop.
2. `"$PSXD" install where --target .` prints `INTAKE <path>` (the kit's `intake.decomp.md`, outside this repository).
3. Write `.run/bootstrap/intake-prompt.md`:

   > My intake answers are in `<INTAKE path>`; read it, ask me only the FILL items, and generate from it.
   > Pre-answered FILL items (confirmed at psxdecomp's gate; ask only what is missing): the 13 lines of
   > `.run/bootstrap/answers.txt`, the medium facts in `.run/bootstrap/medium.json`, the leads in
   > `.run/bootstrap/prior-art.md`.

4. Do what that prompt says, as PA3's intake (`docs/project-architect.md`, *Mode 1 intake*). The intake writes:
   - `PROJECT_CONTEXT.md`, which carries the kit's ladder (its Phase 0 is *Governance and the firewall*);
   - the Developer section of `HOW_WE_WORK.md`;
   - the files that section lists.

   Never write `GENERATION_PLAN.md`: the planner does, after S10.
5. Commit exactly the paths the intake wrote: `git add <paths> && git commit -m "Intake: the constitution from the
   kit's intake"` (no AI trailer).
6. `"$PSXD" install mark S7 --target . --note "PROJECT_CONTEXT.md committed <sha>"`, then continue with S8.
