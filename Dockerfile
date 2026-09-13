# Stage 1: build the web dashboard (React + Vite) into /web/../app/static.
# Builds offline from the lockfile; fonts and icons are bundled, no CDN at runtime.
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# vite.config.ts writes to ../app/static, i.e. /app/static in this stage.
RUN npm run build

# Stage 2: the Python server.
FROM python:3.12-slim

WORKDIR /srv/plaud-bridge

COPY requirements.txt requirements-stt.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-stt.txt

# DeepFilterNet 3 standalone binary (static, CPU): denoises a copy of noisy
# recordings so the speech can be located when the raw noise floor hides it
# from the VAD (see app/engines/enhance.py). Pinned release + checksum.
ARG DEEP_FILTER_URL=https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-unknown-linux-musl
ARG DEEP_FILTER_SHA256=70775e251eee44c0f2451a1e833326cf8bcbbe304d3e7cd12851e6fce72ef7da
RUN python3 -c "import hashlib, sys, urllib.request; \
    data = urllib.request.urlopen('${DEEP_FILTER_URL}').read(); \
    assert hashlib.sha256(data).hexdigest() == '${DEEP_FILTER_SHA256}', 'deep-filter checksum mismatch'; \
    open('/usr/local/bin/deep-filter', 'wb').write(data)" \
    && chmod 0755 /usr/local/bin/deep-filter

COPY app ./app
COPY --from=web /app/static ./app/static
# Optional: drop a built APK + manifest.json here (or bake via CI) and a fresh
# server auto-hosts it for the Android app's self-update check.
COPY bundled-apk/ ./bundled-apk/

RUN useradd -u 1000 -m appuser && mkdir -p /data && chown appuser /data
USER appuser

# Keep downloaded models inside the data volume so they survive rebuilds.
ENV PB_DATA_DIR=/data \
    HF_HOME=/data/models
VOLUME /data
EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
