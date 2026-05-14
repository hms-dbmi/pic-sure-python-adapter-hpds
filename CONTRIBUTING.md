# Contributing

Welcome. This document is the entry point for working on `picsure`
itself — both new contributors getting set up and maintainers handling
day-to-day reviews, tests, and releases. User-facing usage docs live
under [`docs/`](docs/) and on the published site; this file and the
[`docs/development/`](docs/development/) folder are for people
**changing the library**.

## Where to find things

| Topic                                  | Where                                                  |
|----------------------------------------|--------------------------------------------------------|
| Containerized dev environment + IDEs   | [docs/development/docker.md](docs/development/docker.md) |
| Package layout and internals           | [docs/development/architecture.md](docs/development/architecture.md) |
| Test layout, running, debugging CI     | [docs/development/testing.md](docs/development/testing.md) |
| Versioning, tagging, publishing        | [docs/development/releasing.md](docs/development/releasing.md) |

## Local development setup

Prefer a container? See
[docs/development/docker.md](docs/development/docker.md) for a
pre-configured Docker dev environment (no local `uv` or Python
required, JupyterLab included). That guide also covers
[IDE setup for VS Code and PyCharm](docs/development/docker.md#ide-setup--using-the-containers-python-from-your-editor).

For a host-native setup:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).

2. Clone the repo and install dependencies:

   ```bash
   git clone https://github.com/hms-dbmi/pic-sure-python-adapter-hpds.git
   cd pic-sure-python-adapter-hpds
   uv sync
   ```

3. Run the checks:

   ```bash
   uv run ruff check src/ tests/            # lint
   uv run ruff format --check src/ tests/   # format check (both src and tests)
   uv run mypy src/                         # type check
   uv run pytest tests/unit/ -v             # unit tests
   ```

These four commands mirror the CI lint gate, which runs `ruff check`
and `ruff format --check` over **both** `src/` and `tests/`. Skipping
`tests/` locally will let contributor-written test files pass the
local check but fail CI.

## Branching and pull requests

- Branch from `main`. Use short, descriptive branch names.
- Write descriptive commit messages. The existing history follows a
  loose conventional-commits style (`feat(query):`, `fix(client):`,
  `chore(deps):`, `refactor(session):`, `docs(...)`). Match it when
  it's natural; don't fight the linter if it isn't.
- Open the PR against `main`. CI must pass before merge:
  - **Lint job** — `ruff check src/ tests/`, `ruff format --check
    src/ tests/`, `mypy src/`.
  - **Test matrix** — `pytest tests/unit/` on Python 3.10, 3.11, 3.12
    with `--cov-fail-under=80`.
  - **Docs** — `mkdocs build --strict` (broken cross-references fail
    the build).
- If you touched the public API surface (anything re-exported from
  `picsure/__init__.py`), update `CHANGELOG.md` under `[Unreleased]`.

## Code style

- `ruff` handles linting and formatting. Config lives in
  `pyproject.toml` under `[tool.ruff]`.
- `mypy --strict` enforces type annotations on all code in `src/`.
- Google-style docstrings on all public functions.
- camelCase for public API method names (matches the product spec);
  snake_case for everything internal.

## Where to file issues

GitHub Issues on the repo:
<https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/issues>.

For security-sensitive reports, please coordinate with the
maintainers privately before opening a public issue.
