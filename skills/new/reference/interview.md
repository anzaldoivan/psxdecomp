# S1 — the interview

AskUserQuestion, **rounds of at most 4 questions**, recommended option first. If AskUserQuestion is not available
(a headless or eval run), put the round's questions in your reply as a numbered list with the options, and stop there:
the developer answers and resumes with `/psxdecomp:new --resume`. Ask only what the probe and the research
cannot answer. Write the result to `.run/bootstrap/interview.json` (keys below), then
`"$PSXD" install mark S1 --target . --note "<title>, <region/version>, dump given|not given"`.

## Round 1 — the target (always first; the first question is the console)

1. **Console** — options: `PlayStation (PS1)` (recommended), `PlayStation 2`, `Nintendo 64`, `Other`. Anything but
   PS1: reply "<console> is not yet supported by psxdecomp (v1 is PS1 only)" and stop. Write nothing.
2. **Title** — free text through "Other" (offer the folder name as the first option when it looks like a title).
3. **Region and version** — `USA`, `Japan`, `Europe`, `Other`; the version (v1.0, v1.1, a revision) in the notes.
4. **Dump path** — the absolute path of the developer's own `.cue` (preferred: Redump, one file per track) or
   `.bin`/`.iso`. It must lie **outside** this folder. Options: `I'll paste the path` and `I don't have a dump yet`
   (S2 is then skipped and the kit's `DUMP_PATH` must be supplied before S8).

## Round 2 — the project

1. **Goals** — default: "Every code binary on the disc rebuilt byte-identical from readable, evidenced C, with the hash
   check inside the build, reproducible by anyone with their own dump from the README alone."
2. **Licence** for the project's own tools and docs, plus the statement over the decompiled source — options:
   `MIT` (recommended for a new project), `AGPL-3.0` (needed to adapt AGPL sources such as sotn-decomp or mmx4),
   `GPL-3.0`, `Other`. Name the licence-compatibility consequence for any `copyleft` lead S3 may find.
3. **Visibility** on day one — `private` / `public` (the firewall applies either way).
4. **AI disclosure** — default sentence: "This project is developed with substantial AI assistance; every change is
   justifiable from recorded evidence, a person reviews each phase gate, and contributors disclose AI-generated
   submissions."

## Round 3 — optional

1. **Your own PsyQ SDK** (`byo`) — a local folder path, or `none`. Never fetched, never committed; the repository's
   firewall purges `tools/psyq/`. Record only that a path was given (the path stays in `.run/`).

## interview.json

```json
{"console": "psx", "title": "...", "region_version": "USA v1.1", "dump_path": "/abs/path.cue or empty",
 "goals": "...", "licence": "MIT ...", "visibility": "private", "ai_disclosure": "...", "byo_psyq_path": "",
 "project_name": "<slug of the title>-decomp"}
```
