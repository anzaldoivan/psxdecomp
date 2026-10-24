# The public toolchain image of a split-mode game (TEMPLATE; psxdecomp's docs/PUBLISHING.md, Split mode). Open-source
# tools only: no game file, no SDK file, no proprietary compiler. The image is published publicly and pulled by digest
# (`[public].image`); the compiler is downloaded at build time by the game's FETCH_COMMAND, pinned by sha256. Two tools,
# psyk and psyq-obj-parser, convert the developer's own (byo) PsyQ SDK at build time.
# The pins below are the profile's starting values; the game's own pins win, and psxdecomp pins no compiler.
# Reproducible: bases by digest, apt from a dated snapshot, every download by sha256 or commit, no .pyc (each one stamps
# its build time), and only one binary from each build stage in the image. Before publishing: two builds give the same
# image (build.sh, beside this file), and no layer holds a game file (layer_audit.py).
#   ./build.sh ghcr.io/<owner>/<game>-toolchain:<date> [--build-arg MASPSX=<the game's pin> ...]
#   python3 layer_audit.py <its a.tar> --private <the local <game>-private>
ARG PSYK=0.4.0
ARG PSYK_SHA256=531ff24380e23e7675e9610e33998e38fe575d14311ebaac5829822585017cfc
ARG PCSX_REDUX=2bcbea9dc79a4cac81892c5979fee97458905985
ARG PSYQ_OBJ_PARSER_SHA256=56ea873e5e6a5b417e99fe19eaad6da224ca2b1d267c710ce8cd9e48a691a36a   # layer_audit.py ALLOW holds it too: change both

# The PsyQ SDK leg, part 1: psyk (ttkb-oss/psy-k, crates.io) splits a .LIB into OBJs, built from the sha256-pinned
# crate. Only /opt/psyk/bin/psyk leaves this stage.
FROM rust:1.99.1-slim@sha256:1a939748a7cbab172de91a014e3804a97af1394a8c844faa67fce9401c4e40fb AS psyk
ARG PSYK
ARG PSYK_SHA256
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/psy-k.crate "https://crates.io/api/v1/crates/psy-k/$PSYK/download" \
    && echo "$PSYK_SHA256  /tmp/psy-k.crate" | sha256sum -c - \
    && mkdir /tmp/psy-k && tar -xzf /tmp/psy-k.crate -C /tmp/psy-k --strip-components=1 \
    && cargo install --path /tmp/psy-k --locked --root /opt/psyk

# Part 2: psyq-obj-parser (pcsx-redux, GPL-2.0) converts an OBJ to ELF. It is built from source at the commit PCSX_REDUX,
# so the image names the source of the binary it ships. Only its three header submodules are fetched. Static, so it
# runs in the final stage. The compiler needs a later snapshot than the final stage: the base image's libc is newer
# than libc6-dev of 20260901. Only /opt/psyq-obj-parser leaves this stage.
FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3 AS psyq-obj-parser
ARG PCSX_REDUX
ARG PSYQ_OBJ_PARSER_SHA256
ARG PARSER_APT_SNAPSHOT=20261015T000000Z
RUN apt-get -o Acquire::https::Verify-Peer=false update --snapshot "$PARSER_APT_SNAPSHOT" \
    && apt-get -o Acquire::https::Verify-Peer=false install -y --no-install-recommends --snapshot "$PARSER_APT_SNAPSHOT" \
      g++ git ca-certificates zlib1g-dev
RUN git init -q /src && git -C /src remote add origin https://github.com/grumpycoders/pcsx-redux.git \
    && git -C /src fetch -q --depth 1 origin "$PCSX_REDUX" && git -C /src checkout -q FETCH_HEAD \
    && git -C /src submodule update -q --init --depth 1 third_party/ELFIO third_party/fmt third_party/magic_enum
RUN cd /src && g++ -std=c++2b -O2 -I. -Isrc -Ithird_party -Ithird_party/ELFIO -Ithird_party/fmt/include \
      -Ithird_party/magic_enum/include -o /opt/psyq-obj-parser tools/psyq-obj-parser/psyq-obj-parser.cc \
      src/support/file.cc third_party/fmt/src/os.cc third_party/fmt/src/format.cc -static -lz \
    && echo "$PSYQ_OBJ_PARSER_SHA256  /opt/psyq-obj-parser" | sha256sum -c -

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

COPY --from=psyk /opt/psyk/bin/psyk /usr/local/bin/psyk
COPY --from=psyq-obj-parser /opt/psyq-obj-parser /usr/local/bin/psyq-obj-parser

# What the build job relies on, asserted at image build time
RUN ldd --version | head -1 && git --version && python3 --version && make --version | head -1 \
    && mipsel-linux-gnu-as --version | head -1 && objdiff-cli --version && psyk --version \
    && echo "$PSYQ_OBJ_PARSER_SHA256  /usr/local/bin/psyq-obj-parser" | sha256sum -c -
RUN git config --system --add safe.directory '*'
WORKDIR /work
