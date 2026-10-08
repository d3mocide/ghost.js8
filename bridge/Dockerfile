# syntax=docker/dockerfile:1.7
# ghost.js8 bridge (also runs fake-kiwi and the acceptance client in tests).
ARG PYTHON_IMAGE=python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# uv verifies every artifact against the hashes in uv.lock (--locked).
# Optional secret "extra_ca": CA bundle for builds behind a TLS-intercepting proxy.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca UV_NATIVE_TLS=1; fi; \
    uv sync --locked --no-dev --extra bridge --no-editable

FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="ghost.js8 bridge" \
      org.opencontainers.image.source="https://github.com/d3mocide/ghost.js8" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin ghost \
 && install -d -o ghost -g ghost -m 0750 /data
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
USER ghost
VOLUME /data
EXPOSE 8073
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8073/healthz', timeout=2).status == 200 else 1)"]
CMD ["python", "-m", "ghostjs8", "bridge"]
