# Testing

This page covers the test layout, the patterns each test type uses,
how to run the suite locally, and how to reproduce a CI failure.

## Layout

```
tests/
├── conftest.py                # shared fixtures (load JSON/CSV files in tests/fixtures/)
├── fixtures/                  # canned server responses
│   ├── profile.json
│   ├── resources.json
│   ├── dictionary_search.json
│   ├── facets_response.json
│   └── query_participant.csv
├── unit/                      # one test_<module>.py per src/picsure/ module
│   ├── test_client.py         # _transport/client.py
│   ├── test_connect.py        # _services/connect.py
│   ├── test_query_run.py      # _services/query_run.py
│   ├── test_search.py         # _services/search.py
│   ├── ...                    # one per module — keep the mapping 1:1
│   └── dev/                   # tests for the _dev/ instrumentation
└── integration/               # live tests; opt-in via env vars
    ├── conftest.py            # gates collection on PICSURE_INTEGRATION=1
    ├── test_connect_live.py
    ├── test_search_live.py
    ├── test_query_live.py
    ├── test_query_genomic_live.py
    └── test_export_live.py
```

Two rules keep the unit suite navigable:

1. **One test file per source module.** `src/picsure/_services/x.py`
   → `tests/unit/test_x.py`. When a new module lands, add the
   matching test file in the same PR.
2. **No network in unit tests.** Every HTTP call is mocked with
   `respx`. If you find yourself reaching for `monkeypatch` to fake
   `httpx`, use `respx` instead — it intercepts at the transport
   layer and exposes the recorded request for assertions.

## Unit test pattern

Unit tests mock the wire with `respx` and assert on both the
response handling and the outgoing request. The shape that recurs
throughout `tests/unit/`:

```python
import httpx
import respx

from picsure._services._hpds_paths import query_prefix
from picsure._services.query_run import run_query

BASE_URL = "https://test.example.com"
# Compose the route rather than hand-writing it: query_prefix supplies the
# /picsure context prefix, so a literal would silently stop matching.
QUERY_URL = f"{BASE_URL}{query_prefix('auth', v3=True)}/query/sync"


class TestRunQueryCount:
    @respx.mock
    def test_returns_count_result(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"1234")
        )
        client = _make_client()
        result = run_query(client, _simple_clause(), "count", backend="auth")
        assert result.value == 1234
```

Two idioms to copy:

- **Stub the route, then call the service.** Don't try to inject a
  pre-mocked `httpx.Client`; the `respx` decorator owns that.
- **Read `route.calls[0].request` to assert on what was sent.** Most
  bugs in this codebase have been "the wrong field on the wire," so
  assert the body shape, not just the response handling. See
  `tests/unit/test_query_run.py::TestRunQueryCount::test_sends_correct_body`
  for an example.

JSON fixtures (`tests/fixtures/*.json`) are exposed as `conftest.py`
fixtures and used by tests that need a realistic backend payload
without inlining ~500 lines of mock data.

## Running locally

```bash
# whole unit suite, verbose
uv run pytest tests/unit/ -v

# with coverage (the CI gate is --cov-fail-under=80)
uv run pytest tests/unit/ --cov=picsure --cov-report=term-missing

# one module
uv run pytest tests/unit/test_query_run.py -v

# one test
uv run pytest tests/unit/test_query_run.py::TestRunQueryCount::test_returns_count_result -v
```

`pyproject.toml` sets `testpaths = ["tests"]`, so plain `uv run
pytest` discovers everything. The integration suite skips itself
unless `PICSURE_INTEGRATION=1` is set, so the default run is safe.

## Integration tests

Integration tests hit a real PIC-SURE instance. They require:

| Env var                    | Purpose                                                            |
|----------------------------|--------------------------------------------------------------------|
| `PICSURE_INTEGRATION`      | Set to `1` to opt in. Without it, the suite skips at collection.   |
| `PICSURE_TEST_TOKEN`       | Bearer token for authorized platforms. Leave unset for open-access. |
| `PICSURE_TEST_PLATFORM`    | A `Platform` enum name (e.g. `BDC_AUTHORIZED`, `BDC_OPEN`, `NHANES_OPEN`) or a full `http(s)://` URL. There is no default. Unset, unrecognized, or naming an authorized platform with no `PICSURE_TEST_TOKEN`, the whole live suite skips at collection with one message naming what to set — it does not fail. |
| `PICSURE_TEST_CONCEPT_PATH`| Concept path used by query/export tests. Required — tests skip with a clear message if unset. |
| `PICSURE_TEST_SEARCH_TERM` | Search term for `test_search_live.py`. Defaults to `"age"`.        |
| `PICSURE_TEST_GENE`        | Gene symbol for `test_query_genomic_live.py`. Required — all four genomic tests skip without it. `CHD8` is verified on `BDC_PREDEV_AUTHORIZED`; genomic tests need an `*_AUTHORIZED` platform. |
| `PICSURE_SSL_VERIFY`       | Set to `false` only when targeting a local stack with a self-signed certificate. Leave unset against a real deployment. |

The integration `conftest.py` calls `dotenv` against the repo root,
so a `.env` file works as well as exported variables (exported vars
win on conflict).

What each `*_live.py` covers:

| File                       | Surface                                                                |
|----------------------------|------------------------------------------------------------------------|
| `test_connect_live.py`     | `picsure.connect`, the success banner, that `Session` has an email / resources. |
| `test_search_live.py`      | `searchDictionary`, `facets`, `showAllFacets` against a real dictionary-api. |
| `test_query_live.py`       | `runQuery` for `count`, `participant`, `timestamp`, `cross_count`. Some types skip on open-access. |
| `test_query_genomic_live.py` | `buildGenomicFilter` as a query constraint, `variant_count`, `variant_list`, `searchGenomicValues`. Requires `PICSURE_TEST_GENE` and an `*_AUTHORIZED` platform. |
| `test_export_live.py`      | `exportAsPFB`, `exportCSV`, `exportTSV` (the last two require an authorized platform — they need a participant-query DataFrame). |

```bash
PICSURE_INTEGRATION=1 \
PICSURE_TEST_TOKEN="your-token" \
PICSURE_TEST_PLATFORM="BDC_AUTHORIZED" \
PICSURE_TEST_CONCEPT_PATH='\phs000007\some\path\' \
PICSURE_TEST_GENE=CHD8 \
uv run pytest tests/integration/ -v
```

Copy `.env.example` to `.env` instead of assembling that command by hand —
it carries a working value and a comment for every variable above.

### The token fixture is opaque

`test_token` does not return a `str`. It returns an `OpaqueToken` whose
`__repr__`, `__str__` and `__format__` all render
`<PICSURE_TEST_TOKEN redacted>`. Unwrap it at the point the token is
handed to the library:

```python
session = picsure.connect(platform=test_platform, token=test_token.reveal())
```

This exists because pytest's default `--tb=long` prints the arguments of
every frame in a traceback, the failing test's frame included. A fixture
returning the token as a plain `str` therefore printed token material on
any failure in any test that took it.

Two rules follow:

- **Call `.reveal()` inline, in the call that consumes the token.** Binding
  it to a local (`raw = test_token.reveal()`) puts the raw string back into
  a frame that `--showlocals` will dump.
- **Do not interpolate `test_token` into a message.** It renders as the
  placeholder, so the message says nothing useful; assert on what the
  library did instead.

As a backstop, `conftest.py` scrubs any run of token characters out of
integration-test failure output and captured stdout/stderr/log sections,
which covers the frames the wrapper cannot reach — a library function
holding the unwrapped token as a local, for instance. The scrubber works
on captured output, so it cannot protect a run with `-s`, where output
bypasses capture and goes straight to the terminal.

### Skipped tests are reported in the summary

A live test that skips still counts as a pass at a glance, which is how the
genomic file once contributed no coverage for a whole release without
anyone noticing. The integration `conftest.py` prints an
`integration tests skipped` section at the end of the run, listing each
skipped test with its reason and naming any `PICSURE_TEST_*` variable that
is unset along with the coverage it silences.

The run still exits 0 — a skip is often legitimate (an open-access target
has no token, predev does not serve the variant result types), so failing
the run would punish a correct partial configuration. Visibility is the
lever: check that section before believing a green integration run.

### Gotchas

- **Counts on open-access platforms are obfuscated.** Expect noisy
  (`"N ± M"`) or suppressed (`"< N"`) responses. The
  `CountResult.value` is `None` when suppressed; tests assert "either
  exact-or-noisy OR suppressed," not a specific value.
- **Data drifts.** A concept path that worked yesterday can be
  retired or renamed. When a query/export test starts failing on a
  green branch, suspect the data first — verify the concept path
  with `searchDictionary` before assuming a code regression.
- **Rate limits.** Hitting integration repeatedly from CI is
  unfriendly to the live service. Run them locally before merging
  user-visible API changes; the unit suite is the gate for everyday
  CI.

## CI

Two workflows under `.github/workflows/`:

### `ci.yml`

Runs on every push to `main` and every PR targeting `main`. Two
jobs:

- **`lint`** — `uv sync --frozen`, then `ruff check src/ tests/`,
  `ruff format --check src/ tests/`, `mypy src/`.
- **`test`** — matrix on Python `3.10`, `3.11`, `3.12`. Each cell
  runs `uv sync --frozen --python <version>` and `pytest tests/unit/
  -v --cov=picsure --cov-fail-under=80`. A coverage regression below
  80 % fails the run.

Integration tests do **not** run in CI — they need credentials and
hit a live deployment.

### `docs.yml`

Runs on every push to `main` and every PR targeting `main`.

- Builds the site with `uv run mkdocs build --strict`. Strict mode
  fails on broken cross-references, unknown nav entries, and missing
  files — keep links relative and intact.
- On a push to `main` (not on PRs), deploys to GitHub Pages via
  `peaceiris/actions-gh-pages`.

## Debugging a CI failure locally

Reproduce the exact commands CI runs:

```bash
# CI does --frozen; you'll need a current lock locally
uv sync --frozen

# lint job
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/

# test job, pin the Python version that failed in the matrix
uv python install 3.10
uv sync --frozen --python 3.10
uv run pytest tests/unit/ -v --cov=picsure --cov-fail-under=80

# docs job
uv sync --frozen --group docs
uv run mkdocs build --strict
```

If a test passes on your machine but fails in CI:

- **Python version.** Default `uv run` uses the highest installed
  Python. CI runs three. Reproduce with `--python 3.10` first
  (oldest = most likely to expose missing back-compat).
- **Frozen lockfile.** Locally `uv sync` may resolve newer pins;
  CI's `--frozen` does not. Reproduce with `uv sync --frozen`.
- **Coverage gate.** Coverage failures only show up with the
  `--cov-fail-under=80` flag; running tests without it hides them.

To run tests inside the Docker dev container, see
[Docker dev environment](docker.md#running-checks-inside-the-container).
