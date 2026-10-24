# The public toolchain image of a split-mode game (TEMPLATE; psxdecomp's docs/PUBLISHING.md, Split mode). Open-source
# tools only: no game file, no SDK file, no proprietary compiler. The image is published publicly and pulled by digest
# (`[public].image`); the compiler is downloaded at build time by the game's FETCH_COMMAND, pinned by sha256. Two tools,
# psyk and psyq-obj-parser, convert the developer's own (byo) PsyQ SDK at build time.
# The pins below are the profile's starting values; the game's own pins win, and psxdecomp pins no compiler.
# Reproducible: bases by digest, apt from a dated snapshot, every download by sha256 or commit, no .pyc (each one stamps
# its build time), and only two binaries of the rust stage in the image. Before publishing: two builds give the same
# image (build.sh, beside this file), and no layer holds a game file (layer_audit.py).
#   ./build.sh ghcr.io/<owner>/<game>-toolchain:<date> [--build-arg MASPSX=<the game's pin> ...]
#   python3 layer_audit.py <its a.tar> --private <the local <game>-private>
ARG PSYK=0.4.0
ARG PSYK_SHA256=531ff24380e23e7675e9610e33998e38fe575d14311ebaac5829822585017cfc
ARG PSYQ_OBJ_PARSER_XZ_SHA256=f2fb8aeb5fbb9047fbafb58191365d785f3461f2e363324dcee0b78a7841a8a6
ARG PSYQ_OBJ_PARSER_SHA256=f02ccb5f9849d7e96c82dbe86dadb867de4cd46623f07b2b8abc21975a561a81   # layer_audit.py ALLOW holds it too: change both

# The PsyQ SDK leg: psyk (ttkb-oss/psy-k, crates.io) splits a .LIB into OBJs, built from the sha256-pinned crate.
# psyq-obj-parser (Xeeynamo/psyz release `requirements`, static x86-64) converts an OBJ to ELF. Neither base has xz, so
# this stage also unpacks it. Only /opt/psyk/bin/psyk and /opt/psyq-obj-parser leave this stage.
FROM rust:1.99.1-slim@sha256:1a939748a7cbab172de91a014e3804a97af1394a8c844faa67fce9401c4e40fb AS sdkleg
ARG PSYK
ARG PSYK_SHA256
ARG PSYQ_OBJ_PARSER_XZ_SHA256
ARG PSYQ_OBJ_PARSER_SHA256
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates xz-utils \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/psy-k.crate "https://crates.io/api/v1/crates/psy-k/$PSYK/download" \
    && echo "$PSYK_SHA256  /tmp/psy-k.crate" | sha256sum -c - \
    && mkdir /tmp/psy-k && tar -xzf /tmp/psy-k.crate -C /tmp/psy-k --strip-components=1 \
    && cargo install --path /tmp/psy-k --locked --root /opt/psyk
RUN curl -fsSL -o /tmp/pop.xz https://github.com/Xeeynamo/psyz/releases/download/requirements/psyq-obj-parser.xz \
    && echo "$PSYQ_OBJ_PARSER_XZ_SHA256  /tmp/pop.xz" | sha256sum -c - \
    && xz -dc /tmp/pop.xz > /opt/psyq-obj-parser \
    && echo "$PSYQ_OBJ_PARSER_SHA256  /opt/psyq-obj-parser" | sha256sum -c - && chmod 0755 /opt/psyq-obj-parser

FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3

ARG APT_SNAPSHOT=20260901T000000Z
ARG SPLAT=0.50.0
ARG SPLAT_VENV=/opt/splat-venv
ARG SPIMDISASM=1.42.4
ARG RABBITIZER=1.16.2
ARG MASPSX=7686f845a181700534c83c0419183e38aeb3e49c
ARG OBJDIFF=3.8.1
ARG OBJDIFF_SHA256=c8290281e82114bcc1a06ff73061110d3902a177822e750337de2537188e358f
ARG PSYQ_OBJ_PARSER_SHA256

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

COPY --from=sdkleg /opt/psyk/bin/psyk /usr/local/bin/psyk
COPY --from=sdkleg /opt/psyq-obj-parser /usr/local/bin/psyq-obj-parser

# What the build job relies on, asserted at image build time
RUN ldd --version | head -1 && git --version && python3 --version && make --version | head -1 \
    && mipsel-linux-gnu-as --version | head -1 && objdiff-cli --version && psyk --version \
    && echo "$PSYQ_OBJ_PARSER_SHA256  /usr/local/bin/psyq-obj-parser" | sha256sum -c -
RUN git config --system --add safe.directory '*'
WORKDIR /work
