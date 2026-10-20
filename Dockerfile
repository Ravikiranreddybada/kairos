# syntax=docker/dockerfile:1.7
# ---- build: compile wheels once, keep the runtime image small ------------------
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels ".[llm,mcp]"

# ---- runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime
# libgomp1: OpenMP runtime required by LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KAIROS_DATA_DIR=/data
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
RUN useradd --uid 10001 --create-home kairos && mkdir -p /data && chown kairos /data
USER kairos
WORKDIR /home/kairos
# Bake warehouse + a promoted champion into the image: free hosts have no persistent disk
# and too little RAM to train at boot. Set BAKE_DATA=0 to skip (compose trains in a job).
ARG BAKE_DATA=1
RUN if [ "$BAKE_DATA" = "1" ]; then kairos seed && kairos train; fi
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s CMD curl -fsS localhost:${PORT:-8000}/healthz || exit 1
CMD ["sh", "-c", "exec kairos serve --host 0.0.0.0 --port ${PORT:-8000}"]
