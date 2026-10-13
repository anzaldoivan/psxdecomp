#!/bin/bash
# Tier 5a: build the corpus image (the profile image plus the fixture's compiler layer) and run the corpus check in
# it, with no network and the fixture mounted read-only. Exit 0 only on `SELF-TEST OK` and `CORPUS OK`.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
docker build --platform linux/amd64 -q -t psxdecomp-profile -f "$root/profiles/psx/image/Dockerfile" "$root/profiles/psx/image" >/dev/null
docker build --platform linux/amd64 -q -t psxdecomp-c-corpus -f "$root/fixtures/c-corpus/Dockerfile" "$root/fixtures/c-corpus" >/dev/null
docker run --rm --platform linux/amd64 --network none -v "$root/fixtures/c-corpus:/work/fixtures/c-corpus:ro" \
  -v "$root/scripts/floor.py:/work/scripts/floor.py:ro" \
  psxdecomp-c-corpus sh -c 'python3 fixtures/c-corpus/probe.py --self-test && python3 fixtures/c-corpus/corpus.py check'
