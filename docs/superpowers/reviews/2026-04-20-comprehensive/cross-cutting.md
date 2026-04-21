# Cross-cutting — Code Review

## Scope

Tests, CI, docs, packaging, CHANGELOG, and public surface of the
`picsure` library at commit `5a58091670e458fda33d3b9fbe3f1b37ef52a04c`.
Files read:

- `tests/` (all unit + integration + fixtures + conftest).
- `.github/workflows/ci.yml`, `.github/workflows/docs.yml`.
- `docs/` (guides + reference + index; `docs/superpowers/reviews/`
  explicitly excluded from this review; `docs/rewrite/` is excluded
  from the mkdocs build via `mkdocs.yml`).
- `pyproject.toml`, `mkdocs.yml`, `CHANGELOG.md`, `README.md`,
  `CONTRIBUTING.md`.
- `src/picsure/__init__.py` (for public-surface cross-ref only — no
  source under `src/` was modified).

Source under `src/` was read only where needed to confirm whether a
claim in docs/CHANGELOG matches the code. The connection/transport
and search behavior issues already captured in
`connection-transport.md` and `search.md` are not re-flagged here;
I only assess their cross-cutting footprint (tests, docs, CHANGELOG).

## Strengths

- **Unit-test breadth is very good.** One test module per service /
  model (`test_client.py`, `test_connect.py`, `test_session.py`,
  `test_search.py`, `test_facets.py`, `test_count_result.py`,
  `test_query_run.py`, `test_query_build.py`, `test_clause*.py`,
  `test_platforms.py`, `test_consents.py`, `test_dictionary.py`,
  `test_export.py`, `test_errors.py`, `test_facade.py`,
  `test_resource.py`, `test_query.py`). Every service module under
  `src/picsure/_services/` and every model under `src/picsure/_models/`
  has a corresponding test file. Fixtures
  (`tests/fixtures/dictionary_search.json`,
  `tests/fixtures/facets_response.json`, `profile.json`,
  `resources.json`, `query_participant.csv`) keep the respx mocks
  grounded in realistic wire shapes rather than canned one-liners.
- **Transport + parsing edge cases are explicitly covered.**
  `test_client.py` asserts the stripped-token / whitespace-token /
  empty-token branches plus the 401/403 → `TransportAuthenticationError`
  mapping, 500 retry + eventual raise, 500-then-200 recovery, connection
  errors, timeouts, and `close()` (`tests/unit/test_client.py:18-210`).
  `test_count_result.py` covers the exact/noisy/suppressed value
  shapes and the `frozen` + `obfuscated` invariants, and
  `test_query_run.py` round-trips every parse branch (`COUNT_EXACT`,
  `COUNT_NOISY`, `COUNT_SUPPRESSED`, `no-space` variants, malformed
  margin, empty body, cross_count variants including each count
  shape) against the wire-level mock.
- **Clause validation is well-tested.** `test_clause.py` and
  `test_query_build.py` enforce every `PicSureValidationError` path
  (ANYRECORD + categories / min / max, FILTER without criteria,
  SELECT raising on `to_query_json`, empty clause-group list).
  `test_query_run.py` also exercises SELECT-lifting, empty-phenotypic
  groups, single-SELECT clauses, and the "never send
  `authorizationFilters`" invariant.
- **Integration tests are correctly gated.**
  `tests/integration/conftest.py:31-41` skips integration tests unless
  `PICSURE_INTEGRATION=1` is set; credentials load from a repo-root
  `.env` via `python-dotenv`. CI does not run them, which is the right
  default. `test_concept_path` skips (not fails) when unconfigured —
  saves first-time contributors a confusing 401.
- **CI matrix is correctly wired.** `.github/workflows/ci.yml:22-34`
  runs Python 3.10/3.11/3.12 via `astral-sh/setup-uv` with
  `--frozen`; the `lint` job runs `ruff check`, `ruff format --check`,
  and `mypy` (under `[tool.mypy] strict = true` from pyproject). The
  `test` job enforces `--cov-fail-under=80`, which is real
  coverage pressure.
- **Docs CI is well-designed.** `.github/workflows/docs.yml:21-29`
  builds `mkdocs build --strict` on every PR (so broken references or
  mkdocstrings failures block merge) and only deploys to GitHub Pages
  on `push` to `main`. This is the right split.
- **Public facade is sound.** `src/picsure/__init__.py:3-28` exports
  only the user-facing types (`connect`, `createClause`,
  `buildClauseGroup`, `Clause`, `ClauseGroup`, `ClauseType`,
  `GroupOperator`, `CountResult`, `FacetSet`, `Platform`, `Query`,
  `Session`, `PicSureError`) and keeps everything else private behind
  `_models`/`_services`/`_transport` prefixes. `test_facade.py`
  exists specifically to guard this contract.
- **CHANGELOG is accurate in most places.** Every symbol named under
  `## [Unreleased]` maps to a real export / method. The v3 wire-format
  change, the `Clause.to_query_json()` raising on SELECT, and the
  `runQuery` return-type shift are all honestly described as breaking.
  `CountResult` matches the dataclass's actual fields (`value`, `margin`,
  `cap`, `raw`, `obfuscated`).

## Issues

### Critical

_None._

### Important

- **Non-standard 4xx (400, 404, 422, 429) are unmapped _and_ untested** — `src/picsure/_transport/client.py:73-81` — The transport maps only 401/403 and ≥500; anything else falls through to `return response`, so a 400 / 404 / 422 / 429 results in the downstream caller invoking `response.json()` (or `response.content`) on an error body. The user gets a `json.JSONDecodeError`, not a `PicSureError`. No test in `tests/unit/test_client.py` exercises these status codes, and no service-level test covers a 404 or 422 response path either. At minimum this needs (a) an explicit mapping in the transport (PicSureValidationError for 400/422, PicSureQueryError for 404, a bounded retry-with-backoff or friendly error for 429) and (b) respx tests at the transport layer for each.
- **Whitespace-token stripping has transport tests but no connect-level test that the `request-source: Open` swap propagates** — `tests/unit/test_client.py:187-210` covers the client, but there is no `test_connect.py` case that uses `token="   "` and asserts the resulting `Session` comes back in anonymous mode with `email == "anonymous"`. This is the user-observable form of the behavior and worth a test because it protects against someone wiring the profile-fetch branch around `if token:` instead of `if token.strip():`.
- **Public surface exports `Platform` and `CountResult`, but API reference documents neither** — `docs/reference/api.md:1-75` lists `connect`, `createClause`, `buildClauseGroup`, `ClauseType`, `GroupOperator`, `Clause`, `ClauseGroup`, `Query`, `FacetSet`, `Session`, and `PicSureError` — but no `::: picsure.Platform` and no `::: picsure.CountResult`. Both are part of `__all__` (`src/picsure/__init__.py:14-28`) and appear in user code examples in the guides (e.g. `docs/guides/running-and-exporting.md:15-19` explains `CountResult.value` / `.cap`; getting-started discusses `platform="BDC Authorized"` enum-string dispatch). Users reading the reference can't see the list of valid `Platform` members (`BDC_AUTHORIZED`, `BDC_OPEN`, `BDC_DEV_*`, `BDC_PREDEV_*`, `AIM_AHEAD`, `NHANES_*`, `DEMO` — total 9 members per `test_platforms.py`) or the `CountResult` field list and `.obfuscated` property. Add `::: picsure.Platform` with `members: true` and `::: picsure.CountResult` with the relevant members.
- **Error-class subclasses are not part of the public surface** — `src/picsure/__init__.py:14-28` re-exports only `PicSureError`; callers who want to catch just authentication failures must write `from picsure.errors import PicSureAuthError`, bypassing the facade. The CHANGELOG advertises "Actionable error messages via `PicSureError`" but the subclasses that make these errors actionable (`PicSureAuthError`, `PicSureConnectionError`, `PicSureQueryError`, `PicSureValidationError`) are only reachable via the private-looking `picsure.errors` path. Either re-export them from the top-level package (and list them in `docs/reference/api.md`) or document that `picsure.errors` is stable and user-facing.
- **Facet category names in guide code examples don't match the real server** — `docs/getting-started.md:53` and `docs/guides/search-and-facets.md:57,60,73,87` use `"study_ids"` as the facet category. But the fixture (`tests/fixtures/facets_response.json`) and `test_search.py:87-129` / `test_session.py:285-295` use `"dataset_id"`, `"data_type"`, and `"Consortium_Curated_Facets"` — matching the live backend. A user copy-pasting the getting-started example will get `PicSureValidationError: 'study_ids' is not a valid facet category`. Either the fixture is wrong or the guides are wrong; the wire-level review (search.md in this set) confirms the backend returns `dataset_id`. Update the guides.
- **`showAllFacets` DataFrame columns in the guide don't match what the code returns** — `docs/guides/search-and-facets.md:47-48` claims `"category, display, value, count"`. The actual columns (per `src/picsure/_services/search.py` and `tests/unit/test_search.py:339-346`) are `category, Category Display, display, description, value, count`. "display" means two different things in the two lists (the user's category display vs. the facet value display). Users inspecting the DataFrame won't find `display` where they expect it.
- **Getting-started suggests repeated `picsure.connect()` without mentioning cleanup** — `docs/getting-started.md:13-21` and `README.md:19-41` both show a single `session = picsure.connect(...)` call. `PicSureClient` owns an `httpx.Client` (`src/picsure/_transport/client.py:32-36`) and `Session` has no `close()` / `__enter__` / `__exit__` (the transport review already flags the absence on the code side). For a notebook user who re-runs the connect cell repeatedly, each invocation leaks the old httpx connection pool. The docs should either (a) show a recommended idiom once `Session.close()` exists, or (b) explicitly note the limitation and recommend restarting the kernel. Right now the user has no way to know.
- **`Session` properties `consents` and `total_concepts` are not documented** — `docs/reference/api.md:59-72` lists only the method members under `Session`. The `@property`s defined at `src/picsure/_models/session.py:44-61` are part of the public surface (used in the connect-time printout example and exercised by `test_session.py:78-103`) but don't appear in the reference at all. Add them to the `members:` list.
- **No test for HTTP 429 retry-after semantics** — the transport does not handle 429 at all (see the first Important bullet), so there is no backoff on rate-limit. For a CLI that might hit the PSAMA profile + resources + concepts-prefetch on every connect, plus per-search + per-query calls, a rate-limited server will surface raw 429s to users as stray `JSONDecodeError`. Flagged here because the test gap is the visible symptom; the fix is code-side.

### Minor

- **`CHANGELOG` claim "GitHub Actions CI with Python 3.10/3.11/3.12 matrix" is accurate, but the same bullet list is missing a claim about lint+mypy gating** — `.github/workflows/ci.yml:10-20` runs `ruff check`, `ruff format --check`, and `mypy src/` in a separate `lint` job. The CHANGELOG line could read "GitHub Actions CI with lint + mypy + Python 3.10/3.11/3.12 test matrix" for completeness.
- **`pyproject.toml` dependencies are lower-bound only** — `pyproject.toml:8-11` pins `httpx>=0.27` and `pandas>=2.0`. A major-version bump to httpx 1.x or pandas 3.x could silently break things. Consider `httpx>=0.27,<1` and `pandas>=2,<3` for the 0.1.0 release, or state the drift risk in CONTRIBUTING.
- **No `[project.urls]` table in `pyproject.toml`** — PyPI discovery would benefit from `Homepage`, `Documentation`, `Source`, `Issues` URLs. Minor.
- **`mkdocs.yml:4-8` uses `exclude_docs:` as a block scalar** — correct, but the `rewrite/` and `superpowers/` lines rely on whitespace-sensitive YAML. A safer form is the list syntax `exclude_docs: ["rewrite/**", "superpowers/**"]`. Minor stylistic.
- **Integration test `test_query_live.py:39-43` catches `PicSureError` rather than the specific `PicSureValidationError`** — broad catch is fine for an integration smoke test, but the unit-level `test_query_run.py:368-376` already covers the specific subclass, so the integration test could be tightened for free.
- **`tests/integration/conftest.py:17-19` defaults `PICSURE_TEST_PLATFORM` to `"DEMO"`** — `DEMO` appears in the `test_platforms.py` sweep (`test_all_members_have_url` iterates `Platform`) but is not named as a valid external platform in the user-facing docs (`docs/getting-started.md:30-33` lists `BDC Authorized`, `BDC Open`, `Demo`, `AIM-AHEAD`). The casing inconsistency (`Demo` vs `DEMO`) is resolved by `.upper()` at conftest.py:56, but it's worth noting the docs list user-friendly strings that conftest won't accept unchanged.
- **`CONTRIBUTING.md:18` runs `ruff format --check src/` but CI checks `src/ tests/`** — `.github/workflows/ci.yml:19` includes `tests/`. A contributor could pass the local check and fail CI. Align the two.
- **`README.md:19-50` quickstart snippet uses `r"\phs1\sex\"` as a raw string ending in a backslash** — this is a `SyntaxError` in Python (`\"` escapes the closing quote in a raw string, producing an unterminated string literal). Every guide page has the same issue (`docs/guides/building-queries.md`, `docs/getting-started.md`, etc.). The strings work in docs because they're untested prose, but a user copy-pasting will get `SyntaxError: EOL while scanning string literal`. Use `"\\phs1\\sex\\"` or put the backslash-heavy paths on their own line. This is technically a docs-correctness bug, but is marked Minor since the semantics are clear and it's a surface-level copy-paste problem.
- **`test_platforms.py:40-41` hardcodes "N/A" semantics for NHANES open** — it asserts `NHANES_OPEN.include_consents is False` and `requires_auth is False`; not a bug, just worth noting the combinatorial coverage is complete. Not actionable.

## Verification evidence

- **Pyproject.** `pyproject.toml:2-11` — `version = "0.1.0"`, `requires-python = ">=3.10"`, `dependencies = ["httpx>=0.27", "pandas>=2.0"]`. Extras: `pfb = ["pypfb>=0.5"]`. Dev group includes `pytest`, `respx`, `ruff`, `mypy`, `pytest-cov`, `pandas-stubs`, `python-dotenv`. Packages: `src/picsure` (hatchling). `mypy strict = true`. `ruff` targets py310 with `E, F, I, UP, B, SIM` rules.
- **CI matrix confirmed.** `.github/workflows/ci.yml:22-34` runs
  `pytest tests/unit/ -v --cov=picsure --cov-fail-under=80` on
  Python 3.10 / 3.11 / 3.12. Lint job runs separately on Python-
  agnostic ubuntu-latest.
- **Docs gating confirmed.** `.github/workflows/docs.yml:21-29` —
  `mkdocs build --strict` runs on every push+PR to `main`;
  deploy step guarded by
  `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`.
- **Public surface.** `src/picsure/__init__.py:14-28` exports exactly:
  `buildClauseGroup, connect, createClause, Clause, ClauseGroup,
  ClauseType, CountResult, FacetSet, GroupOperator, PicSureError,
  Platform, Query, Session`. Reference documents all except
  `CountResult` and `Platform` (and the `PicSureError` subclasses
  that are not exported to begin with).
- **`test_facade.py:14-29`** asserts 12 of these 13 exports explicitly;
  `CountResult` is covered separately at
  `tests/unit/test_count_result.py:35-38`.
- **Count parsing edges covered.** `tests/unit/test_query_run.py:30-156`
  tests exact/noisy/suppressed/no-space/malformed/empty bodies and
  the same cross-count variants at
  `tests/unit/test_query_run.py:216-285`.
- **Clause validation edges covered.**
  `tests/unit/test_query_build.py:90-129` enforces every
  `createClause` validation branch; `tests/unit/test_clause.py:135-138`
  enforces `SELECT.to_query_json()` raising.
- **HTTP error mapping gaps.** `tests/unit/test_client.py` covers 401,
  403, 500, connect error, timeout, but _not_ 400 / 404 / 422 / 429.
  `src/picsure/_transport/client.py:73-81` only branches on 401/403
  and ≥500, confirming the test gap reflects a real code gap.
- **Facet column drift.** `tests/unit/test_session.py:308-317` and
  `tests/unit/test_search.py:339-346` both expect columns
  `["category", "Category Display", "display", "description",
  "value", "count"]`; guide at `docs/guides/search-and-facets.md:47-48`
  claims `category, display, value, count`.
- **Facet category drift.** `tests/fixtures/facets_response.json:1-26`
  and `tests/unit/test_search.py:99-128` use `"dataset_id"`;
  `docs/getting-started.md:53` and
  `docs/guides/search-and-facets.md:57,60,73,87` use `"study_ids"`.
- **CHANGELOG cross-check.** Every `### Added` / `### Changed` line
  resolves to a real symbol or behavior: `connect` at
  `_services/connect.py:24`, `Session.getResourceID` at
  `_models/session.py:63`, `Platform` at `_transport/platforms.py`,
  `Session.search/facets/showAllFacets` at
  `_models/session.py:120-177`, `createClause/buildClauseGroup` at
  `_services/query_build.py`, `ClauseType/GroupOperator` at
  `_models/clause.py`/`_models/clause_group.py`, `CountResult` at
  `_models/count_result.py`, `Session.runQuery` at
  `_models/session.py:179-217`, `Session.exportPFB/CSV/TSV` at
  `_models/session.py:219-267`, `PicSureClient.post_raw` at
  `_transport/client.py:48-54`. The v3 endpoint claim matches
  `tests/unit/test_query_run.py:19` and
  `tests/unit/test_session.py:323-324`.
- **Whitespace-token in CHANGELOG.** `CHANGELOG.md:46` matches
  `src/picsure/_transport/client.py:25-31` (`token.strip()` +
  `request-source: "Open" if empty else "Authorized"`) and
  `tests/unit/test_client.py:187-210`.
- **`docs/rewrite/`** is excluded from the mkdocs build via
  `mkdocs.yml:4-8`. It contains one informal spec txt and does not
  ship to the site.
