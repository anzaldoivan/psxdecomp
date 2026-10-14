# Tier 5a's image: the profile image plus ONE fixture-owned layer holding two candidate compilers, so the corpus can
# compile C and compare bytes. The profile image itself still pins no compiler, and no game repo inherits this layer.
# cc1 builds: decompals/old-gcc release 0.17, by sha256 (statically linked i386 ELF; only cc1 is kept).
#   2.95.2-psx = PsyQ 4.6's compiler; 2.7.2-psx = PsyQ 4.0's (profiles/psx/psyq.toml).
ARG BASE=psxdecomp-profile
FROM ${BASE}
RUN set -e; base=https://github.com/decompals/old-gcc/releases/download/0.17; \
    for spec in \
      2.95.2-psx:932ed3669710a82b12570c29c46ff42989b6505b2af10db84d4551d55dfc0b1c \
      2.7.2-psx:500a459b3485e885a8d302cac23c2a4632f3900e03a09153f6190699fd723571; do \
      name=${spec%%:*}; sha=${spec#*:}; \
      curl -fsSL -o /tmp/cc.tar.gz "$base/gcc-$name.tar.gz"; \
      echo "$sha  /tmp/cc.tar.gz" | sha256sum -c -; \
      mkdir -p "/opt/cc/$name"; tar -xzf /tmp/cc.tar.gz -C "/opt/cc/$name" cc1; chmod 0755 "/opt/cc/$name/cc1"; \
    done; rm -f /tmp/cc.tar.gz
WORKDIR /work
