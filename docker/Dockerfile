# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        build-essential \
        curl \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Pinned uv from the official image — no curl-pipe-sh install. Bump
# this in lockstep with the host uv version so `uv.lock` doesn't churn
# between host syncs and container syncs (older uv strips `revision`
# and `upload-time` fields that newer uv writes).
COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /uvx /usr/local/bin/

# Non-root user. UID/GID configurable so files written through the
# bind mount land with host ownership on Linux hosts. On macOS Docker
# Desktop, the VM translates ownership anyway.
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid ${USER_GID} dev \
 && useradd  --uid ${USER_UID} --gid ${USER_GID} --create-home --shell /bin/bash dev

# Trust the bind-mounted workspace at /workspace for all users.
# Written to /etc/gitconfig so we don't mutate the host ~/.gitconfig
# (which is bind-mounted read-write into the container).
RUN git config --system --add safe.directory /workspace

# Venv lives outside the bind mount so the host's macOS .venv never
# collides with the container's Linux venv. Backed by a named volume
# in docker-compose.yml.
#
# UV_PYTHON_DOWNLOADS=never + UV_PYTHON=/usr/local/bin/python3.12 pins
# the venv to the system Python baked into this image. Without these,
# uv may download a managed interpreter into ~/.local/share/uv/python,
# which lives in the container's writable layer — not on a volume —
# so `--rm` destroys it and leaves the persistent venv with dangling
# shebangs pointing at a missing Python.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CACHE_DIR=/home/dev/.cache/uv \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:/home/dev/.local/bin:$PATH

RUN mkdir -p /opt/venv /home/dev/.cache/uv \
 && chown -R dev:dev /opt/venv /home/dev/.cache

USER dev
WORKDIR /workspace

COPY --chown=dev:dev docker/entrypoint.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
