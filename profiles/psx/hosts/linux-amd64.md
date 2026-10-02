# Host recipe — Linux amd64

The BFM arrangement (provenance: BFM-decomp's host, 2026-10-01; WSL2 Ubuntu counts): one clone on a native filesystem (ext4, never a Windows mount); Claude Code,
Ghidra and the build toolchain on the same host. Docker is optional here: the old cc1 builds run natively when the
i386 runtime is installed (`dpkg --add-architecture i386`), but a container keeps the toolchain pinned and is the
recommended default so the CI and the host build agree.

- Python >= 3.12 for the PA3 hooks (resolved per machine).
- binutils-mipsel-linux-gnu, cpp-mipsel-linux-gnu, splat64 in a venv; or the profile container.
- The dump stays outside the repository; the repository's firewall ignores and audits every derived path.
