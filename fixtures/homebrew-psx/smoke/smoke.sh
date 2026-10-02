#!/bin/sh
# Tier 1b, inside the profile container: synthetic disc -> extract -> splat split -> all-asm build -> hash.
# Also assembles hello.s and checks its words equal make_disc.py's pre-encoded ones (the tier-1 fixture is honest).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
W=${SMOKE_DIR:-/tmp/smoke}
rm -rf "$W" && mkdir -p "$W"
python3 "$here/../make_disc.py" "$W/disc" >/dev/null
python3 "$here/extract.py" "$W/disc/HOMEBREW.cue" "$W/HELLO.EXE"
sha=$(sha1sum "$W/HELLO.EXE" | cut -d' ' -f1)
sed "s/@SHA1@/$sha/" "$here/hello.yaml" > "$W/hello.yaml"
cd "$W"
python3 -m splat split hello.yaml >split.log 2>&1 || { tail -30 split.log; exit 1; }
AS="mipsel-linux-gnu-as -EL -march=r3000 -mtune=r3000 -mabi=32 -no-pad-sections -Iinclude -I."
for s in $(find asm -name '*.s' | sort); do          # splat's linker script names each object build/<source>.o
  mkdir -p "build/$(dirname "$s")"
  $AS -o "build/$s.o" "$s"
done
touch undefined_syms_auto.txt undefined_funcs_auto.txt
mipsel-linux-gnu-ld -T build/hello.ld -T undefined_syms_auto.txt -T undefined_funcs_auto.txt -Map build/hello.map \
  --no-check-sections -o build/hello.elf
mipsel-linux-gnu-objcopy -O binary build/hello.elf build/HELLO.EXE
got=$(sha1sum build/HELLO.EXE | cut -d' ' -f1)
echo "SMOKE extracted $sha"
echo "SMOKE rebuilt   $got"
# the source recipe: hello.s assembles to make_disc.py's words
$AS -o build/src.o "$here/../hello.s"
mipsel-linux-gnu-objcopy -O binary -j .text build/src.o build/src.text
python3 - "$here/../make_disc.py" build/src.text <<'PY'
import importlib.util, struct, sys
spec = importlib.util.spec_from_file_location("m", sys.argv[1]); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
words = list(struct.unpack("<%dI" % len(m.WORDS), open(sys.argv[2], "rb").read()[:4 * len(m.WORDS)]))
assert words == m.WORDS, "hello.s does not assemble to make_disc.py's WORDS: %s" % [hex(w) for w in words]
print("SMOKE hello.s == make_disc.WORDS (%d words)" % len(words))
PY
[ "$sha" = "$got" ] && echo "SMOKE OK" || { echo "SMOKE FAIL: the rebuilt exe differs"; exit 1; }
