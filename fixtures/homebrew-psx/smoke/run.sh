#!/bin/bash
# Tier 1b: build the profile container and run the smoke in it. Exit 0 only on `SMOKE OK`.
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
docker build --platform linux/amd64 -q -f "$root/fixtures/homebrew-psx/smoke/Dockerfile" -t psxdecomp-smoke "$root" >/dev/null
docker run --rm --platform linux/amd64 psxdecomp-smoke
