# Security policy

## Leaked game or SDK bytes

If you find game-derived bytes (a disc image, an executable, extracted data, pasted disassembly) or PsyQ SDK files in
this repository, its history, its CI logs or its eval workspaces, report it privately through GitHub's
**Report a vulnerability** form on this repository. Do not open a public issue and do not attach the files. The
offending paths are purged from history and the audit gains a rule that would have caught them.

## Other vulnerabilities

The plugin runs scripts on your machine (installers, git, an optional Docker host). Report anything that lets a crafted
answers file, disc or reference row run code or write outside the target folder through the same private form.
