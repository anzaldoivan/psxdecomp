# The PS1 profile container for psxdecomp's tier 1b smoke (and the shape a game repo's phase-1.0 image starts from).
# Pins: splat64 / spimdisasm / rabbitizer as mmx6 pinned them on 2026-10-01; binutils from Debian bookworm.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends binutils-mipsel-linux-gnu make \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "splat64[mips]==0.50.0" "spimdisasm==1.42.4" "rabbitizer==1.16.2"
WORKDIR /work
COPY scripts/ scripts/
COPY profiles/ profiles/
COPY fixtures/homebrew-psx/ fixtures/homebrew-psx/
CMD ["sh", "fixtures/homebrew-psx/smoke/smoke.sh"]
