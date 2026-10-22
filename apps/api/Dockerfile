# OpenSolve Pipe API: production image for Google Cloud Run (TSD §11.2).
#
#   docker build -t opensolve-pipe-api apps/api
#   docker run --rm -p 8080:8080 -e CORS_ORIGINS=http://localhost:5173 opensolve-pipe-api
#
# Both base images are pinned by version and digest, so a rebuild installs the same bytes;
# to take updates, change the tag and its digest together (TSD §11.2).

FROM ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c AS uv

# --- Build: the locked runtime dependencies and the app, into a virtual environment ----------
FROM python:3.12.15-slim-trixie@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2 AS build
COPY --from=uv /uv /usr/local/bin/uv
# The base image's Python, compiled bytecode (faster cold starts), no uv cache in the layers.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1
WORKDIR /app
# Dependencies first, as their own layer: exactly uv.lock (--locked fails if it is stale),
# without the dev group (pytest, mypy, WNTR, ...).
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
# Then the app itself, installed as a regular (non-editable) package with its data files.
COPY LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

# --- Runtime: the virtual environment only, run by an unprivileged user --------------------
FROM python:3.12.15-slim-trixie@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin app
# Owned by root: the app user can run the code but not change it.
COPY --from=build /app/.venv /app/.venv
# PORT: Cloud Run sets it (8080 unless configured); the default serves `docker run` alike.
# FORWARDED_ALLOW_IPS (read by uvicorn): the proxy addresses whose X-Forwarded-For is trusted.
# These are the address blocks IANA's special-purpose registries mark as not globally
# reachable (loopback, link-local, private-use, shared and unique-local; RFC 1122, 3927,
# 1918, 6598, 4291, 4193), so no client on the internet can connect from one of them: on
# Cloud Run every request arrives through Google's front end, which puts the client's address
# last in X-Forwarded-For (observed, not documented by Google), and uvicorn takes the
# right-most untrusted entry. Never "*": uvicorn then takes the left-most entry, which the
# client writes itself. TSD §11.2 has the sources and how to diagnose a shared bucket; §11.4
# the check to run after deploying. The app keys an IPv6 client by its /64 (middleware.py).
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FORWARDED_ALLOW_IPS="127.0.0.0/8,::1,169.254.0.0/16,fe80::/10,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7"
USER app
WORKDIR /app
EXPOSE 8080
# One uvicorn process per instance: the rate limit and the solve pool (workers.py) are
# in-process state. exec makes uvicorn PID 1, so it receives Cloud Run's SIGTERM. Default log
# level: the app's filter drops client addresses and query strings from the access log
# (logging_privacy.py).
CMD ["sh", "-c", "exec uvicorn opensolve_pipe.main:app --host 0.0.0.0 --port \"${PORT}\" --proxy-headers"]
