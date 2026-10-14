A public file is a prose file that `config/public-paths.txt` publishes. Write it in the style of ASD-STE100
Simplified Technical English. Plans, logs and summaries are not public files. They stay terse.

1. Classify each passage. An instruction tells the reader what to do. A description explains.
2. An instruction has at most 20 words. Use the imperative: "Run `make check`."
3. A sentence of a description has at most 25 words.
4. A paragraph has one topic and at most 6 sentences.
5. Write one instruction in one sentence.
6. Put the condition before the command, with a comma: "If the build fails, read the log."
7. Use the active voice and simple tenses. Name the actor: "The tool writes the index."
8. Use no semicolon. Write two sentences, or name the relation: "because", "but", "then".
9. Write complete sentences. Keep the articles. Use no contraction.
10. Use one word for one thing in the whole file. Do not change "check" to "verify".
11. Keep every fact: each code span, number, id and link target.
12. Keep each hedge. "It may fail" does not become "it fails".
13. In a warning, give the command first. Then give the risk.

```text
Before: The gate fails if the hash differs; run `make no-rom` first, which may leave stale objects.
After:  Run `make no-rom` first. It may leave stale objects. If the hash differs, the gate fails.
```

Before you finish, run `python3 tools/psxd_publish.py style <file>`. It must print no finding.

Adapted from SimpleEnglish and asd-ste100-skill (both MIT). This text is not the ASD-STE100 standard.
