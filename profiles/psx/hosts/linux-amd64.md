# Host recipe — Linux amd64

This is the BFM arrangement (provenance: BFM-decomp's host, 2026-10-01). WSL2 Ubuntu counts.

- One clone on a native filesystem (ext4, never a Windows mount).
- Claude Code, Ghidra and the build toolchain on the same host.
- Docker is optional. The old cc1 builds run natively with the i386 runtime (`dpkg --add-architecture i386`).
- Build in a container by default: it keeps the toolchain pinned, so the CI and the host build agree.

- Python >= 3.12 for the PA3 hooks (resolved per machine).
- binutils-mipsel-linux-gnu, cpp-mipsel-linux-gnu, splat64 in a venv. Or use the profile container.
- The dump stays outside the repository. The repository's firewall ignores and audits every derived path.

## Install

Checked 2026-10-02 against the distributions' own package indexes and the Homebrew formulae API. The indexes:
`apt-cache policy` in clean Ubuntu 22.04, 24.04 and 26.04 and Debian 12 and 13 images.

| Tool | Debian/Ubuntu (apt) | Homebrew on Linux | Notes |
|---|---|---|---|
| git | `git` | `git` | any supported release |
| Python ≥ 3.12 | `python3 python3-venv` | `python@3.14` | apt gives 3.12+ only on Ubuntu 24.04+ and Debian 13+. Ubuntu 22.04: `python3.12 python3.12-venv` from the deadsnakes PPA. Debian 12: Homebrew. |
| Claude Code | `claude-code` from Anthropic's apt repository | `--cask claude-code` | or the native installer, which updates itself |
| gh (optional) | `gh` from GitHub's apt repository | `gh` | the distributions' own `gh` (2.45, 2.46) is broken against current GitHub APIs |
| ripgrep | `ripgrep` | `ripgrep` | Claude Code bundles its own. This one is for your shell. |
| Docker | `docker.io` | — | or Docker's own apt repository. Homebrew does not provide the engine. |
| MIPS binutils | `binutils-mipsel-linux-gnu` | `mipsel-linux-gnu-binutils` | native builds only. The profile container has them. |
| MIPS preprocessor | `cpp-mipsel-linux-gnu` | — | native builds only. Absent from Ubuntu 26.04, so build in the container there. |
| i386 runtime | `libc6:i386` after `dpkg --add-architecture i386` | — | native builds only: the old cc1 binaries are static i386 ELF |
| JDK 21 (Ghidra) | `openjdk-21-jdk` | `openjdk@21` | Debian 12 has no JDK 21: Homebrew or Eclipse Temurin's apt repository |
| Ghidra | — | `ghidra` | or the release zip from github.com/NationalSecurityAgency/ghidra |
| PCSX-Redux | — | — | the AppImage from the project's download page |

```sh
# Ubuntu 24.04 / 26.04, Debian 13
sudo apt install git python3 python3-venv ripgrep docker.io openjdk-21-jdk
curl -fsSL https://claude.ai/install.sh | bash
# gh: follow https://github.com/cli/cli/blob/trunk/docs/install_linux.md (GitHub's apt repository)

# the same tools through Homebrew on Linux
brew install git python@3.14 gh ripgrep ghidra openjdk@21
brew install --cask claude-code
```

No package manager supplies PsyQ: `docs/ops/refs.md`, psyq-sdk row.

## WSL

Use **WSL 2** (Ubuntu from `wsl --install`). WSL 1 cannot run the toolchain:

- It has no 32-bit ELF support, and the old cc1 is i386.
- Docker Desktop and Homebrew need WSL 2.
- Claude Code on WSL 1 runs without its sandbox.

- **The repository lives in the Linux filesystem** (`~/…`), never under `/mnt/c`: bind mounts and file watching are far
  slower there (Docker's WSL guidance).
- **Docker:** use Docker Desktop for Windows with its WSL 2 backend, and turn WSL integration on for the distribution.
  Or use `docker.io` inside the distribution: it needs systemd, which Ubuntu from `wsl --install` has on. Otherwise
  set `[boot] systemd=true` in `/etc/wsl.conf`, then run `wsl --shutdown`.
- **Claude Code** installs and runs inside the WSL terminal (the Linux installer above), not from PowerShell.
- **Line endings:** `git config core.autocrlf false` in the clone. A game's `tools/psxd_publish.py` is the plugin's
  file byte for byte, and a CRLF conversion breaks that without a visible diff.
- **Split mode:** the developer's pushes, `release`, `land` and `settings --apply` run in a WSL terminal outside Claude
  Code. Deploy keys live in `~/.ssh/psxd/` inside WSL (mode 0600), never on the Windows side. `docker login ghcr.io`
  is the developer's, and the image tools need `docker buildx` (with `docker.io`: the `docker-buildx` package).
- **GUI tools** (Ghidra, PCSX-Redux) run under WSLg on Windows 11 or Windows 10 build 19044+, or use their Windows
  builds on the Windows side.
