# Host recipe — macOS arm64 + Docker Desktop

Proven on mmx6 and DC2 (2026-10-01). Claude Code, PA3 and the oracles run on the Mac; the build runs in an amd64
container with the source in a named volume.

- **Claude Code + PA3** on the Mac; the repository on the Mac's disk. Python >= 3.12 for the hooks (the installer
  resolves the interpreter per machine and writes it into `.claude/pa.json`).
- **Docker Desktop**, context `desktop-linux`, amd64 emulation on (`--platform linux/amd64`): the old cc1 builds are
  static i386 ELF binaries.
- **One tree, a disposable copy:** a named volume holds a copy of the tracked + untracked-non-ignored files, refreshed
  by a `sync` before each run; outputs come back by name only; no bind mount of a host path; firewall paths never leave
  the container. (mmx6's `tools/docker/mx.sh build|sync|pull|disc|run` is the reference shape as of 2026-10-01; phase 1.0 builds it.)
- **The dump** is loaded once into its own read-only volume (`disc`), top-level `*.cue`/`*.bin` only.
- **Oracles on the host:** Ghidra + ghidra_psx_ldr + an MCP server (static); PCSX-Redux with Lua (runtime).
