# Profile schema

A console profile is a folder `profiles/<id>/` holding `profile.toml`, `refs.toml`, `probes/` and `hosts/`. v1 ships
`psx` only; the structure is per-console so that a second profile is data plus one probe module, not a fork.

The keys a profile must fill (`tests/test_static.py` reads this table and checks every profile against it). Where an
answer is console-specific, the decomp-architect kit marks it `TODO(platform)`; those markers are the checklist for a
new profile.

| Key | What it holds |
|---|---|
| `console.id` | the profile id (the folder name) |
| `console.name` | the console's name |
| `console.cpu` | the CPU and endianness |
| `console.platform` | the kit's `PLATFORM` answer, verbatim |
| `console.supported` | `true` once tier 1 passes for this profile; `/psxdecomp:new` refuses an unsupported one |
| `medium.kinds` | dump file kinds `identify` accepts |
| `medium.probe` | the probe module (relative path) exposing `identify(dump) -> (medium, seeds)` and `match_dat(dat, sha1)` |
| `medium.boot_record` | the file that names the boot executable |
| `sdk.family` | the SDK family whose stamps the probe detects |
| `sdk.detector` | how the probe detects the SDK version |
| `sdk.authority` | which later tool's detection is the final word |
| `tools.splitter` | the splitter/disassembler the ladder's phase 1 uses |
| `tools.assembler` | the assembler/linker |
| `tools.compilers` | where candidate compilers come from |
| `tools.loader` | the RE database loader |
| `tools.oracle` | the static and runtime oracles |
| `hosts.recipes` | host recipe ids, each a `hosts/<id>.md` |
| `hosts.container_platform` | the build container's platform |
| `research.search_seeds` | S3's search templates (`{title}`, `{serial}` filled) |

Optional: an SDK catalogue (`psx/psyq.toml`; fields in its header). S10 copies the game's row into
`config/psxdecomp.toml [psyq]`: a lead, never the pin.

## The probe's output (`medium.json`)

Facts only: `console`, `volume_id`, `files`, `file_list` (path, size), `system_cnf` (or the console's boot record),
`boot_exe`, `serial`, `exe` (header fields, size, sha1), `track01` (sha1, sha256, bytes, mode), `toc` (tracks, line,
fingerprint), `psyq` (or the SDK's stamps: count, version, libnums, first, last; `note` when there is no stamp), `sdk_strings`, `seeds` (method,
count, entry). Never a byte of the medium; never the dump's path.

## Adding a profile

1. Copy `profiles/psx/`, rename, fill every key above; write the probe and its `--self-test` fixture (a synthetic
   medium built at test time, never committed).
2. Default `refs.toml` for that console: each row's licence read from the source itself, with the date.
3. `console.supported = true` only when tier 1 passes on the new fixture. Record the profile in `docs/PROFILES.md`.
