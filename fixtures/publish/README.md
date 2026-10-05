# psxdecomp-synthetic-game

## Description

The synthetic game is psxdecomp's stand-in for a real title: a README that follows the standard, with records shaped
like a real repository's and hashes that belong to no disc. psxdecomp's tier 0 lints it and plants faults in copies.

<!-- psxdecomp: ai-policy -->
> [!IMPORTANT]
> **AI policy:** LLMs produce negligible decompilation results without good guidance. Investigate and familiarize yourself with the console's architecture and the game you are decompiling, and always use your own judgment. Humans drive the decisions; AI reads and writes the code.

<!-- psxdecomp:disc:begin -->
| Disc | Serial | Executable | SHA-1 of the data track |
|---|---|---|---|
| Disc 1 | PSXD-00001 | `PSXD_000.01` | `0123456789abcdef0123456789abcdef01234567` |

The target `PSXD_000.01` has SHA-1 `89abcdef0123456789abcdef0123456789abcdef` (`config/check.PSXD_000.01.sha`); every build checks its rebuild against it.
<!-- psxdecomp:disc:end -->

> [!IMPORTANT]
> Like every game repository, this fixture holds no game data: only names, sizes and hashes.

## Progress

<!-- psxdecomp:progress:begin -->
[![Code][psxd-code]][psxd-progress] [![Functions][psxd-functions]][psxd-progress]

| Category | Name | Status |
|---|---|---|
| `main` | PSXD_000.01, the boot executable | [![Code](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Code&measure=code&category=main)](https://decomp.dev/example/synthetic-decomp?category=main) [![Functions](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Functions&measure=functions&category=main)](https://decomp.dev/example/synthetic-decomp?category=main) |
| `ovl` | OVL/ overlays on the disc | [![Code](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Code&measure=code&category=ovl)](https://decomp.dev/example/synthetic-decomp?category=ovl) [![Functions](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Functions&measure=functions&category=ovl)](https://decomp.dev/example/synthetic-decomp?category=ovl) |
| `sdk` | PsyQ libraries | [![Code](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Code&measure=code&category=sdk)](https://decomp.dev/example/synthetic-decomp?category=sdk) [![Functions](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Functions&measure=functions&category=sdk)](https://decomp.dev/example/synthetic-decomp?category=sdk) |

<details><summary><code>ovl</code>: 2 overlays</summary>

| Category | Name | Status |
|---|---|---|
| `ovl.title` | Title screen | [![Code](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Code&measure=code&category=ovl.title)](https://decomp.dev/example/synthetic-decomp?category=ovl.title) [![Functions](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Functions&measure=functions&category=ovl.title)](https://decomp.dev/example/synthetic-decomp?category=ovl.title) |
| `ovl.stage1` | Stage 1 | [![Code](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Code&measure=code&category=ovl.stage1)](https://decomp.dev/example/synthetic-decomp?category=ovl.stage1) [![Functions](https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Functions&measure=functions&category=ovl.stage1)](https://decomp.dev/example/synthetic-decomp?category=ovl.stage1) |

</details>

Progress bars powered by [decomp.dev][psxd-progress].

[psxd-code]: https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Code&measure=code&category=game
[psxd-functions]: https://decomp.dev/example/synthetic-decomp.svg?mode=shield&label=Functions&measure=functions&category=game
[psxd-progress]: https://decomp.dev/example/synthetic-decomp
<!-- psxdecomp:progress:end -->

## Building the decompilation

Requirements: Python 3.12 and your own dump under `disks/`.

```sh
make extract
make -C . build
```

A green build prints `build/PSXD_000.01: OK`.

## Repository layout

| Path | Contents |
|---|---|
| `config/` | the categories, the disc rows and the hash records |
| `docs/` | the setup guide and the decompilation reference |
| `disks/` | your own dump (ignored by git) |

## Getting started

### Setting up

The first-time setup is in [docs/INSTALL.md](docs/INSTALL.md).

### Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before a first pull request.

### Reference

Common code patterns are in [docs/DECOMPILATION.md](docs/DECOMPILATION.md).

## Acknowledgements

The reference decompilations whose README shapes the standard follows.

## License

CC0 1.0, as the homebrew fixture.
