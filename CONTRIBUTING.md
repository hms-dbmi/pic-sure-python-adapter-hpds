# Contributing

## Development Setup

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

These mirror the CI lint gate, which runs `ruff check` and `ruff format
--check` over both `src/` and `tests/`. Skipping `tests/` locally will
let contributor-written test files pass the local check but fail CI.

## Running Integration Tests

Integration tests hit a live PIC-SURE instance and require credentials:

```bash
PICSURE_INTEGRATION=1 \
PICSURE_TEST_TOKEN="your-token" \
PICSURE_TEST_PLATFORM="Demo" \
uv run pytest tests/integration/ -v
```

## Code Style

- `ruff` handles linting and formatting.
- `mypy --strict` enforces type annotations on all code.
- Google-style docstrings on all public functions.
- camelCase for public API method names (matches the product spec).
