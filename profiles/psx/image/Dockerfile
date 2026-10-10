# The public toolchain image of a split-mode game (TEMPLATE; psxdecomp's docs/PUBLISHING.md, Split mode). Open-source
# tools only: no game file, no SDK file, no proprietary compiler. The image is published publicly and pulled by digest
# (`[public].image`); the compiler is downloaded at build time by the game's FETCH_COMMAND, pinned by sha256.
# The pins below are the profile's starting values; the game's own pins win, and psxdecomp pins no compiler.
# Reproducible: base by digest, apt from a dated snapshot, every download by sha256 or commit, no .pyc (each one stamps
# its build time). Before publishing: two builds give the same image (build.sh, beside this file), and no layer holds
# a game file (layer_audit.py).
#   ./build.sh ghcr.io/<owner>/<game>-toolchain:<date> [--build-arg MASPSX=<the game's pin> ...]
#   python3 layer_audit.py <its a.tar> --private <the local <game>-private>
FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3

ARG APT_SNAPSHOT=20260901T000000Z
ARG SPLAT=0.50.0
ARG SPLAT_VENV=/opt/splat-venv
ARG SPIMDISASM=1.42.4
ARG RABBITIZER=1.16.2
ARG MASPSX=7686f845a181700534c83c0419183e38aeb3e49c
ARG OBJDIFF=3.8.1
ARG OBJDIFF_SHA256=c8290281e82114bcc1a06ff73061110d3902a177822e750337de2537188e358f

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# The snapshot is https-only and the base image has no CA certificates yet: TLS peer checks are off for this one step.
# Integrity does not rest on TLS: apt verifies the snapshot's signed InRelease and every package's hash against it.
# The logs and caches apt and dpkg write are dropped so two builds give the same layer.
RUN apt-get -o Acquire::https::Verify-Peer=false update --snapshot "$APT_SNAPSHOT" \
    && apt-get -o Acquire::https::Verify-Peer=false install -y --no-install-recommends --snapshot "$APT_SNAPSHOT" \
      binutils-mipsel-linux-gnu cpp-mipsel-linux-gnu make python3 python3-venv git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* /var/log/apt /var/log/dpkg.log /var/log/alternatives.log \
       /var/cache/ldconfig/aux-cache /var/cache/debconf/*-old /var/lib/dpkg/*-old

RUN python3 -m venv "$SPLAT_VENV" \
    && "$SPLAT_VENV/bin/pip" install --no-cache-dir --no-compile "splat64[mips]==$SPLAT" "spimdisasm==$SPIMDISASM" \
       "rabbitizer==$RABBITIZER" \
    && find "$SPLAT_VENV" -name __pycache__ -type d -prune -exec rm -rf {} + \
    && rm -rf /root/.cache                       # ensurepip compiles pip's own .pyc; pip's HTTP cache dates itself
ENV PATH=$SPLAT_VENV/bin:$PATH

RUN git clone https://github.com/mkst/maspsx.git /opt/maspsx && git -C /opt/maspsx checkout "$MASPSX" \
    && rm -rf /opt/maspsx/.git \
    && printf '#!/bin/sh\nexec python3 /opt/maspsx/maspsx.py "$@"\n' > /usr/local/bin/maspsx && chmod 0755 /usr/local/bin/maspsx

RUN curl -fsSL -o /usr/local/bin/objdiff-cli \
      "https://github.com/encounter/objdiff/releases/download/v$OBJDIFF/objdiff-cli-linux-x86_64" \
    && echo "$OBJDIFF_SHA256  /usr/local/bin/objdiff-cli" | sha256sum -c - && chmod 0755 /usr/local/bin/objdiff-cli

# What the build job relies on, asserted at image build time
RUN ldd --version | head -1 && git --version && python3 --version && make --version | head -1 \
    && mipsel-linux-gnu-as --version | head -1 && objdiff-cli --version
RUN git config --system --add safe.directory '*'
WORKDIR /work
