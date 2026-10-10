#!/usr/bin/env bash
# build.sh — build the toolchain image twice from scratch and require the same image both times (psxdecomp's
# docs/PUBLISHING.md, Cutover order, step 4). It pushes nothing.
#
#   build.sh ghcr.io/<owner>/<game>-toolchain:<date> [--build-arg MASPSX=<sha> ...]     # the game's own pins
#
# Each build: --no-cache, no provenance or SBOM attestation (they carry the build's time), SOURCE_DATE_EPOCH with
# rewrite-timestamp (every file's and layer's time is that second; default: the Dockerfile's apt snapshot day), written
# as an OCI archive. The two archives must name the same manifest (so the same config and layers). Then the image is
# loaded under its tag and the next commands are printed. Needs `docker buildx` (BuildKit 0.13 or newer) and the
# containerd image store, which keeps the manifest's digest through `docker push`.
# OUT=<dir> keeps the archives there (default: a new temporary directory); layer_audit.py reads $OUT/a.tar.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
tag=${1:?usage: build.sh ghcr.io/<owner>/<game>-toolchain:<date> [docker build options]}
shift
docker buildx version > /dev/null 2>&1 || { echo "IMAGE FAIL docker buildx is not installed (Ubuntu: apt install docker-buildx)" >&2; exit 1; }
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
  snap=$(sed -n 's/^ARG APT_SNAPSHOT=//p' "$here/Dockerfile")
  SOURCE_DATE_EPOCH=$(date -u -d "${snap:0:4}-${snap:4:2}-${snap:6:2}" +%s)
fi
export SOURCE_DATE_EPOCH
out=${OUT:-$(mktemp -d)}
mkdir -p "$out"
manifest() { tar -xOf "$1" index.json | python3 -c 'import json, sys; print(json.load(sys.stdin)["manifests"][0]["digest"])'; }
for n in a b; do
  docker buildx build --platform linux/amd64 --no-cache --pull --provenance=false --sbom=false \
    --build-arg "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH" \
    --output "type=oci,dest=$out/$n.tar,name=$tag,rewrite-timestamp=true" -f "$here/Dockerfile" "$@" "$here"
done
a=$(manifest "$out/a.tar"); b=$(manifest "$out/b.tar")
if [ "$a" != "$b" ]; then
  echo "IMAGE FAIL two builds differ: $a and $b" >&2
  for n in a b; do d=$(manifest "$out/$n.tar"); tar -xOf "$out/$n.tar" "blobs/sha256/${d#sha256:}" > "$out/$n.json"; done
  diff "$out/a.json" "$out/b.json" >&2 || true                  # the config or the layer that moved
  exit 1
fi
docker load -q -i "$out/a.tar" > /dev/null
echo "IMAGE OK $tag $a (two builds, SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH); archives in $out"
echo "next: python3 $here/layer_audit.py $out/a.tar --private <the local <game>-private>"
echo "then, the developer's: docker push $tag, make the package public, and [public].image = \"${tag%%:*}@$a\""
