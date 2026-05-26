# Docker development environment

A pre-configured container that lets contributors run picsure, its
tests, and a JupyterLab sandbox without installing `uv`, Python, or
project dependencies locally. The only host requirement is Docker.

## Quick start

```bash
cp .env.example .env                # if you don't have one
docker compose run --rm dev         # interactive shell (tests/lint/git)
docker compose up notebook          # JupyterLab on http://localhost:8888
```

First start runs `uv sync` once into a named volume; subsequent starts
reuse it. The sync repeats automatically when `pyproject.toml` or
`uv.lock` change.

## Two services, one image

| Service    | What it's for                                            | Port  |
|------------|----------------------------------------------------------|-------|
| `dev`      | Interactive shell — `uv run pytest`, `ruff`, `mypy`, git | —     |
| `notebook` | JupyterLab with `picsure` preinstalled for experiments   | 8888  |

Both services use the same image and share the same `/opt/venv`, so
anything you install via `uv add` in the dev shell is immediately
available in the notebook.

The notebook service includes `jupyterlab-lsp` and `python-lsp-server`,
which give you inline as-you-type completion, hover types,
jump-to-definition, and live diagnostics in every cell — not just the
Tab completion the IPython kernel provides out of the box.

### Where notebooks live

JupyterLab opens with **File → New Notebook** defaulting to
`/workspace/notebooks/`. That directory is the only place where
`*.ipynb` files are tracked by git — see
[`notebooks/README.md`](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/notebooks/README.md) for the convention.
Scratch notebooks created anywhere else (the repo root, inside `src/`,
etc.) are gitignored automatically, so you can experiment freely
without polluting commits.

## What's mounted

| Host path           | Container path             | Why                                                |
|---------------------|----------------------------|----------------------------------------------------|
| `./`                | `/workspace`               | Repo. Live edits in either direction.              |
| `picsure-venv` vol. | `/opt/venv`                | Linux venv, isolated from the host's macOS venv.   |
| `uv-cache` vol.     | `/home/dev/.cache/uv`      | Persistent uv download cache.                      |
| `~/.gitconfig`      | `/home/dev/.gitconfig`     | Your git identity, so commits inside are signed by you. |
| `~/.ssh`            | `/home/dev/.ssh`           | SSH keys for `git push`.                           |
| `./.env`            | (via `env_file`)           | Integration-test tokens.                           |

The venv lives at `/opt/venv` (set via `UV_PROJECT_ENVIRONMENT`) so the
host's macOS `.venv/` never conflicts with the container's Linux venv.

## IDE setup — using the container's Python from your editor

The container's interpreter lives at `/opt/venv/bin/python`. Both VS
Code and PyCharm can attach to it so you get autocomplete, type
checking, test running, and debugging against the same environment
that runs your tests in CI — without installing Python on your host.

### VS Code (Dev Containers)

The repo ships a `.devcontainer/devcontainer.json` that targets the
`dev` compose service.

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   and the [**Dev Containers**](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
   extension (`ms-vscode-remote.remote-containers`).
2. Open the repo folder in VS Code.
3. Either click the **"Reopen in Container"** prompt VS Code shows, or
   run `Dev Containers: Reopen in Container` from the command palette
   (`Cmd/Ctrl + Shift + P`).
4. VS Code builds the image (first time only), starts the `dev`
   service, and reopens itself attached to the container. The Python,
   Ruff, and mypy extensions auto-install with their paths preset to
   the container's venv.
5. Open a terminal (`` Ctrl + ` ``) — you're now in a bash shell inside
   `/workspace`, same as `docker compose run --rm dev`. Tests, lint,
   and git all run here.

The notebook service is unaffected — start it independently with
`docker compose up notebook` whenever you want JupyterLab. VS Code can
also forward port `8888` automatically if you open notebook URLs from
inside the container.

To pick the interpreter manually (e.g. for a workspace that didn't
auto-detect): `Cmd/Ctrl + Shift + P` → **Python: Select Interpreter**
→ enter `/opt/venv/bin/python`.

### PyCharm (Professional only)

Remote interpreters require PyCharm **Professional**. Community does
not support Docker Compose interpreters.

1. Make sure the image is built at least once on the command line so
   PyCharm doesn't time out during introspection:
   ```bash
   docker compose build dev
   docker compose run --rm dev true   # triggers the first uv sync
   ```
2. **Settings** → **Project: pic-sure-python-adapter-hpds** →
   **Python Interpreter** → gear icon → **Add Interpreter** →
   **On Docker Compose…**
3. Fill in:
   - **Server:** Docker (your local daemon — usually picked
     automatically)
   - **Configuration file(s):** `./docker-compose.yml`
   - **Service:** `dev`
   - **Environment variables:** leave default
   - Click **Next**
4. PyCharm introspects the container. When prompted for the
   interpreter path, enter:
   ```
   /opt/venv/bin/python
   ```
5. **Sync folders:** PyCharm proposes `<project root> → /workspace`.
   Keep that mapping — it matches the bind mount and means PyCharm
   doesn't have to copy files around.
6. Click **Create**. PyCharm indexes the container's site-packages.
   First index takes a few minutes; afterwards autocomplete, jump-to-
   definition, type checking, and the debugger all work against the
   container's environment.

**Running tests:** right-click `tests/` → **Run 'pytest in tests'**.
PyCharm spins up the `dev` service to execute the test process and
streams output back to the IDE. The same works for individual test
files and functions.

**Debugger:** set breakpoints normally and click the bug icon.
PyCharm attaches `pydevd` over the compose service. No extra
configuration needed.

**Linters and formatters:** install the **Ruff** plugin (JetBrains
Marketplace) and point its binary path at `/opt/venv/bin/ruff` under
**Settings** → **Tools** → **Ruff**. mypy: **Settings** → **Tools** →
**Mypy** (third-party plugin) → executable `/opt/venv/bin/mypy`.

**Refreshing after dependency changes:** when `pyproject.toml` or
`uv.lock` change, the container's entrypoint re-runs `uv sync` on the
next start. After it finishes, trigger **File** → **Invalidate Caches
/ Reindex** so PyCharm picks up the new packages.

### Editor without Python plugin support

You don't need an IDE integration at all. Edit files in any editor on
the host; run everything in the container shell:

```bash
docker compose run --rm dev          # one shell session
# ... edit files in your editor of choice ...
# ... commands run in the docker shell ...
```

This is the minimal-friction path and works for any editor that can
edit text. You lose IDE-driven completion and debugging, but the test
loop is unchanged.

## Running checks inside the container

```bash
docker compose run --rm dev bash -lc '
  uv run ruff check src/ tests/ &&
  uv run ruff format --check src/ tests/ &&
  uv run mypy src/ &&
  uv run pytest tests/unit/ -v
'
```

Integration tests run the same way — they pick up `.env` automatically:

```bash
docker compose run --rm dev uv run pytest tests/integration/ -v
```

## Adding AI coding agents

The container is agent-agnostic. To use an agent that runs as a CLI
inside the container, drop a `docker-compose.override.yml` next to
`docker-compose.yml` with the mounts and env it needs. Compose merges
override files automatically; they're git-ignored as a class-of-file
in `.gitignore` if you add them, so credentials don't leak.

The agent's CLI needs to be on `PATH` inside the container. Two ways:

1. **Install at container start.** Add an `install.sh` to your override
   that runs in your shell session (`pipx install ...`, `npm i -g ...`).
2. **Bake into a personal image.** Create a `docker/Dockerfile.local`
   that `FROM picsure-dev:latest` and installs the agent globally,
   then point the override at it via `build: dockerfile:`.

### Example: mounting agent config and credentials

```yaml
# docker-compose.override.yml
services:
  dev:
    volumes:
      # Claude Code
      - ${HOME}/.claude:/home/dev/.claude
      - ${HOME}/.config/claude-code:/home/dev/.config/claude-code
      # GitHub CLI (gh, gh-copilot)
      - ${HOME}/.config/gh:/home/dev/.config/gh
      # Generic: any tool that reads ~/.config/<tool>
      # - ${HOME}/.config/<tool>:/home/dev/.config/<tool>
    environment:
      # Pass through API keys from the host shell
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      OPENAI_API_KEY:    ${OPENAI_API_KEY:-}
```

Then either install the agent inside the container session, or build a
personal image on top:

```dockerfile
# docker/Dockerfile.local
FROM picsure-dev:latest
USER root
RUN curl -fsSL https://claude.ai/install.sh | sh   # example
USER dev
```

```yaml
# docker-compose.override.yml — using a personal image
services:
  dev:
    build:
      context: .
      dockerfile: docker/Dockerfile.local
```

### A note on credentials

The default mounts (`~/.gitconfig`, `~/.ssh`) are **read-write**. A
process in the container can modify your host git config or
known_hosts. This is intentional — it makes `git push`, `ssh`, and
agent-driven workflows just work — but only mount agent credentials
you're willing to expose to anything running in the container.

## Rebuilding

The image rebuilds automatically when `docker/Dockerfile` changes. To
force a rebuild (e.g. after editing the Dockerfile):

```bash
docker compose build --no-cache
```

To wipe the venv and start fresh:

```bash
docker compose down -v   # removes named volumes including picsure-venv
docker compose run --rm dev   # triggers a fresh uv sync
```

## Apple Silicon / linux/arm64

The base image (`python:3.12-slim-bookworm`) is multi-arch; the build
runs natively on Apple Silicon with no emulation. If you need x86_64
explicitly (e.g. to match a CI image), add `platform: linux/amd64` to
the service in `docker-compose.override.yml`.
