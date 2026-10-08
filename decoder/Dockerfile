# syntax=docker/dockerfile:1.7
# ghost.js8 decoder: native JS8Call, headless, fed by a PulseAudio null sink.
# See docs/decoder-container.md.

ARG UBUNTU_IMAGE=ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55

# ---------------------------------------------------------------------------
# fetch: download the pinned JS8Call AppImage, verify it, extract it.
# Nothing from this stage except the extracted tree reaches the final image.
# ---------------------------------------------------------------------------
FROM ${UBUNTU_IMAGE} AS fetch
ARG JS8CALL_VERSION=3.0.3
ARG JS8CALL_SHA256=3f89bd821f281c59a9384c08a3ad783ea3b9ac6abf319ce6c0d881c2ecc6e6cd
ARG JS8CALL_URL=https://github.com/JS8Call-improved/js8call-improved/releases/download/v${JS8CALL_VERSION}/JS8Call-v${JS8CALL_VERSION}-x86_64.AppImage
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# Optional secret "extra_ca": a full CA bundle for builds behind a TLS-intercepting
# proxy. Used for this download only; never copied into the image. Integrity is
# guaranteed by the SHA-256 check, not by TLS.
RUN --mount=type=secret,id=extra_ca,required=false \
    set -eu; \
    cacert=""; [ -s /run/secrets/extra_ca ] && cacert="--cacert /run/secrets/extra_ca"; \
    curl -fsSL --retry 4 --retry-delay 2 $cacert -o /tmp/js8call.AppImage "${JS8CALL_URL}"; \
    echo "${JS8CALL_SHA256}  /tmp/js8call.AppImage" | sha256sum -c -; \
    chmod +x /tmp/js8call.AppImage; \
    cd /opt && /tmp/js8call.AppImage --appimage-extract >/dev/null; \
    mv /opt/squashfs-root /opt/js8call; \
    rm /tmp/js8call.AppImage

# ---------------------------------------------------------------------------
# runtime
# ---------------------------------------------------------------------------
FROM ${UBUNTU_IMAGE} AS runtime
ARG JS8CALL_VERSION=3.0.3
LABEL org.opencontainers.image.title="ghost.js8 decoder" \
      org.opencontainers.image.source="https://github.com/d3mocide/ghost.js8" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      io.d3frag.ghostjs8.js8call.version="${JS8CALL_VERSION}"

# Libraries the AppImage does not bundle (found with ldd against the extracted
# tree), plus Xvfb, PulseAudio, supervisord and Python for the decoder-agent.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      xvfb x11-utils xauth \
      pulseaudio pulseaudio-utils \
      supervisor python3 python3-venv \
      libgl1 libegl1 libusb-1.0-0 libfontconfig1 libfreetype6 libharfbuzz0b \
      libx11-6 libx11-xcb1 libxcb1 libxkbcommon0 libxkbcommon-x11-0 \
      libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
      libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 libxcb-shm0 \
      libxcb-sync1 libxcb-render0 libsm6 libice6 fonts-dejavu-core \
      procps tini \
 && rm -rf /var/lib/apt/lists/*

COPY --from=fetch /opt/js8call /opt/js8call

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin ghost \
 && install -d -o ghost -g ghost -m 0700 /run/ghost

COPY rootfs/ /
RUN chmod 0755 /usr/local/bin/ghost-*

USER ghost
ENV HOME=/home/ghost \
    XDG_RUNTIME_DIR=/run/ghost \
    DISPLAY=:99 \
    PULSE_SERVER=unix:/run/ghost/pulse/native \
    QT_X11_NO_MITSHM=1 \
    QT_QPA_PLATFORM=xcb \
    GHOSTJS8_UDP_PORT=2242

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
  CMD ["/usr/local/bin/ghost-healthcheck"]

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/ghost-supervise"]
