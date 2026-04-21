# Comprehensive Review Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Resolve the Critical and Important findings from `docs/superpowers/reviews/2026-04-20-comprehensive/` in the order the user approved: transport → export → search → query-build → query-run → docs.

**Architecture:** Six batches, each a self-contained implementer subagent task with two-stage review (spec compliance + code quality). Tests use TDD (red → green → refactor) where behavior changes. All changes land on branch `worktree-fix-code-review-items`. Sub-agents stage only their own files (not the pre-existing worktree formatting reflows).

**Tech Stack:** Python 3.10+, `httpx`, `pandas`, `pytest`, `respx`, `ruff`, `mypy`. Dependency manager: `uv`.

**Spec inputs:** The six review files under `docs/superpowers/reviews/2026-04-20-comprehensive/`. They include `file:line` citations for every finding.

**Baseline SHA:** `29c51a1c544d202c2d62c3e763f3ea97a43e4c13` (review commit — HEAD before fixes begin).

**User decisions (lock in):**
- **export_pfb**: Rewrite to async flow (`POST /query` → poll `/query/{id}/status` → `POST /query/{id}/result`). Exponential backoff starting at 1s, 2× per poll, per-poll cap 60s, total timeout 600s (fail if >10 min elapsed).
- **Negation (`not`)**: Not supported. Remove "`not`" mentions from `Clause` / `ClauseGroup` docstrings. No `negated` field. Future work.

**Out of scope (deferred):**
- Memory pagination for very-large searches (`search.py` "one big page" — design tradeoff, not a bug today).
- Forwarding `request-source` in dictionary-api proxy (backend-side concern).
- Dedup key change from `concept_path` to `(dataset, conceptPath)` (equivalent on BDC today).
- Enum-casing normalization (cosmetic).

---

## File structure

**Created:**
- (none new — all work modifies existing files, except new tests)

**Modified (major):**
- `src/picsure/_transport/client.py` — 4xx mapping, GET-only retry, better connection errors.
- `src/picsure/_transport/platforms.py` — remove AIM_AHEAD placeholder enum member.
- `src/picsure/_transport/errors.py` — possibly add `TransportValidationError` / `TransportNotFoundError` / `TransportRateLimitError`.
- `src/picsure/errors.py` — no new subclasses needed; existing `PicSureValidationError`, `PicSureQueryError`, `PicSureConnectionError` cover the mapping.
- `src/picsure/_models/session.py` — add `close()`, `__enter__`, `__exit__`.
- `src/picsure/_services/connect.py` — actionable error for whitespace token on `requires_auth=True` platform.
- `src/picsure/_services/export.py` — rewrite `export_pfb` to async flow with backoff; atomic write; 4xx body check; OSError wrapping.
- `src/picsure/_services/search.py` — `fetch_facets` plumbing; truncation guard.
- `src/picsure/_models/dictionary.py` — add `min`, `max`, `allow_filtering`, `meta`, `study_acronym` fields to `DictionaryEntry`.
- `src/picsure/_services/query_build.py` — FILTER+both, REQUIRE+extras, SELECT+extras validation; defensive list copies.
- `src/picsure/_models/clause.py` — remove `not` mention from docstring.
- `src/picsure/_models/clause_group.py` — raise on SELECT children; remove `not` mention from docstring.
- `src/picsure/_services/query_run.py` — wrap pandas errors; cross_count int support; document tab-joined multi-values.
- `src/picsure/__init__.py` — re-export `PicSureError` subclasses.
- `CHANGELOG.md` — new `[Unreleased]` entries under `### Added`, `### Changed`, `### Fixed`, `### Removed`.
- `docs/reference/api.md` — add `Platform`, `CountResult`, `PicSureError` subclasses, `Session` properties.
- `docs/getting-started.md`, `docs/guides/search-and-facets.md`, `README.md` — fix `study_ids` → `dataset_id`; fix raw-string-ending-in-backslash examples; fix `showAllFacets` column list; note `Session.close()` usage.
- `pyproject.toml` — upper bounds on `httpx`, `pandas`.
- `CONTRIBUTING.md` — align `ruff format --check` path with CI (`src/ tests/`).
- New tests under `tests/unit/` per batch.

---

## Task 1 — Transport batch

**Fixes (per review files):**
- Remove `Platform.AIM_AHEAD` placeholder (Critical in `connection-transport.md#critical`).
- Map 4xx in `client.py` (Critical in `query-run.md#critical`; root cause in `connection-transport.md#important`):
  - 400 / 422 → `TransportError` that `_services` map to `PicSureValidationError`.
  - 404 → `TransportError` mapping to `PicSureQueryError`.
  - 429 → `TransportError` mapping to `PicSureConnectionError` with `Retry-After` echoed in the message.
- Restrict retry to GET and to connection/timeout errors only (no POST 5xx retry).
- Add `Session.close()`, `Session.__enter__`, `Session.__exit__` that delegate to `self._client.close()`.
- Strip-check: if `Platform(requires_auth=True)` and token strips to empty, raise `PicSureValidationError("Platform X requires a token but none was provided.")` inside `connect()` before the transport gets built.
- Improve the generic POST 5xx error path's message.

**Tests (new):**
- `tests/unit/test_client.py` — 400, 404, 422, 429 branches; retry no-longer-happens on POST 5xx; retry DOES happen on GET + ConnectError / Timeout.
- `tests/unit/test_connect.py` — whitespace token on `requires_auth=True` raises `PicSureValidationError` with the right message.
- `tests/unit/test_session.py` — `with picsure.connect(...) as s:` closes client on exit; `s.close()` idempotent.
- `tests/unit/test_platforms.py` — enum sweep no longer includes `AIM_AHEAD`.

**TDD:** Red → green per sub-fix. The implementer writes failing tests first, runs them, implements, runs again.

**Files to stage (and ONLY these):** the files modified above + `CHANGELOG.md` fragment.

**Commit message:** `fix(transport): map 4xx responses, restrict POST retry, add Session.close(), remove AIM_AHEAD placeholder`.

---

## Task 2 — Export rewrite

**Fixes:**
- Rewrite `export_pfb` to the async flow:
  1. `POST /picsure/v3/query` with the same body shape as `query_run` but `expectedResultType="DATAFRAME_PFB"`. Expect `202 Accepted` + a JSON body whose `picsureResultId` / `resourceResultId` / `queryId` (whichever the gateway emits — check `PicsureRSv3`) is the polling handle.
  2. Poll `GET /picsure/v3/query/{id}/status` (or whatever the v3 status endpoint is — check `PicSureV3Service.java:256-271` referenced in `export.md`) with exponential backoff: `1, 2, 4, 8, 16, 32, 60, 60, ...` (each poll capped at 60s). Fail with `PicSureConnectionError` if the cumulative wait exceeds 600s.
  3. Once status is `AVAILABLE` / `COMPLETE`, `POST /picsure/v3/query/{id}/result`. Stream the response body to disk via `httpx.Client.stream("POST", ...)` with `response.iter_bytes()`.
- Atomic write: write to `path.with_suffix(path.suffix + ".part")`, then `os.replace()`.
- Wrap `OSError` / `PermissionError` / disk-full in a new `PicSureError` subclass or reuse `PicSureConnectionError` with a clear message.
- On any non-2xx status during poll or result, raise with the real HTTP status surfaced (4xx → `PicSureQueryError`, 5xx → `PicSureConnectionError`).

**Tests:**
- `tests/unit/test_export.py` — respx fixture for the full async flow: `POST /query` → 202; `GET /query/{id}/status` → first call pending, second AVAILABLE; `POST /query/{id}/result` → 200 with bytes. Assert file written, streamed, `.part` suffix cleaned up.
- Backoff timing test: mock `time.sleep` and assert call sequence `[1, 2, 4, 8, 16, 32, 60, 60, ...]`.
- Total timeout test: fixture where status is never AVAILABLE; assert `PicSureConnectionError("PFB export did not complete within 10 minutes")` after 600s simulated.
- 4xx branch: `GET /status` returns 400; assert `PicSureValidationError` surfaced.
- Atomic-write test: simulate a write failure mid-stream; assert the `.part` file is cleaned up and the target path is not partially written.

**Files:** `src/picsure/_services/export.py`, `tests/unit/test_export.py`, `CHANGELOG.md`.

**Commit message:** `fix(export): rewrite export_pfb to async flow with exponential backoff and atomic write`.

---

## Task 3 — Search behavioral fixes

**Fixes:**
- `fetch_facets(client, consents, term="", facets=None)` now accepts optional `term` and `facets`. Wire them into the `/facets` body so counts match the current search selection (contextual).
- `Session.facets(term="", facets=None)` and `Session.showAllFacets(term="", facets=None)` pass them through.
- Expand `DictionaryEntry` with `min: float | None`, `max: float | None`, `allow_filtering: bool`, `meta: dict | None`, `study_acronym: str | None`. Parse from the concept dict in `from_dict`. Add to the DataFrame column list in `search.py`.
- Truncation guard: after `/concepts` returns, assert `data["last"] is True` and `len(data["content"]) == data["totalElements"]`. If not, raise `PicSureQueryError("Search returned a truncated page...")` with the counts in the message.
- Docstring notes:
  - `showAllFacets`: "Returns every facet option including those with count 0. UI hides count=0 options."
  - Dedup: note that keys are `concept_path` only.

**Tests:**
- `tests/unit/test_search.py` / `tests/unit/test_facets.py` — contextual-facets branch (facets + term flow through to the wire body).
- `tests/unit/test_dictionary.py` — `DictionaryEntry.from_dict` populates new Continuous fields.
- `tests/unit/test_search.py` — truncation guard raises when `last=False`.

**Files:** `src/picsure/_services/search.py`, `src/picsure/_models/dictionary.py`, `src/picsure/_models/session.py`, `tests/unit/test_search.py`, `tests/unit/test_dictionary.py`, `tests/unit/test_facets.py` (if exists), `CHANGELOG.md`.

**Commit message:** `fix(search): plumb contextual facets, expand DictionaryEntry with Continuous fields, guard truncation`.

---

## Task 4 — Query build validation symmetry

**Fixes:**
- In `createClause`:
  - FILTER with both `categories` and (`min` or `max`) → `PicSureValidationError("FILTER clauses cannot have both categories and min/max.")`.
  - REQUIRE with `categories` / `min` / `max` → `PicSureValidationError("REQUIRE clauses cannot have categories, min, or max.")`.
  - SELECT with `categories` / `min` / `max` → `PicSureValidationError("SELECT clauses cannot have categories, min, or max.")`.
  - Empty keys list → `PicSureValidationError("Clause must have at least one concept path.")`.
- In `ClauseGroup.to_query_json`: raise `PicSureValidationError("ClauseGroup cannot contain a SELECT clause; use Clause.select_paths() or buildClauseGroup select handling.")` on SELECT children (symmetric with `Clause.to_query_json`).
- Defensive `list(...)` copies for `keys` and `categories` in `createClause` so caller mutation is isolated.
- Remove `not` mentions from `Clause` and `ClauseGroup` docstrings (user decision: not supported).

**Tests:**
- `tests/unit/test_query_build.py` — new failing tests for each of the four rejection branches; ensure they pass after fix.
- `tests/unit/test_clause_group.py` — SELECT-in-group now raises.
- `tests/unit/test_clause.py` — caller-mutation-of-keys-does-not-affect-Clause round-trip.

**Files:** `src/picsure/_services/query_build.py`, `src/picsure/_models/clause.py`, `src/picsure/_models/clause_group.py`, `tests/unit/test_query_build.py`, `tests/unit/test_clause.py`, `tests/unit/test_clause_group.py`, `CHANGELOG.md`.

**Commit message:** `fix(query-build): symmetric validation for FILTER/REQUIRE/SELECT + SELECT-in-group raises`.

---

## Task 5 — Query execution fixes

**Fixes:**
- `_parse_dataframe` wraps `pd.errors.ParserError`, `UnicodeDecodeError`, `EmptyDataError` in `PicSureQueryError("Server returned a malformed CSV response: ...")`.
- `_parse_cross_count` explicitly handles integer values (no longer relies on `str(int)` accident); update docstring + add test fixture with `{"\\path\\": 42}`.
- `run_query` docstring: document that DATAFRAME cells can contain tab-separated multi-values and callers should `.str.split("\t")` where relevant.

**Tests:**
- `tests/unit/test_query_run.py` — malformed-CSV branch; integer cross_count fixture; docstring smoke-test for multi-value note (mention in a comment is enough).

**Files:** `src/picsure/_services/query_run.py`, `tests/unit/test_query_run.py`, `CHANGELOG.md`.

**Commit message:** `fix(query-run): wrap pandas errors, support integer cross_count values`.

---

## Task 6 — Docs & cross-cutting

**Fixes:**
- `docs/getting-started.md`: replace every `study_ids` with `dataset_id` for facet category examples.
- `docs/guides/search-and-facets.md`: replace `study_ids` with `dataset_id`; correct `showAllFacets` column list to `category, Category Display, display, description, value, count`.
- `docs/reference/api.md`: add `::: picsure.Platform` with `members: true`, `::: picsure.CountResult`, `::: picsure.PicSureAuthError`, `::: picsure.PicSureQueryError`, `::: picsure.PicSureConnectionError`, `::: picsure.PicSureValidationError`, and `Session.consents` / `Session.total_concepts` property members.
- `src/picsure/__init__.py`: re-export `PicSureAuthError`, `PicSureConnectionError`, `PicSureQueryError`, `PicSureValidationError` from `picsure.errors`.
- `README.md` + guides: fix every raw string ending in a backslash (`r"\phs1\sex\"` → `"\\phs1\\sex\\"`).
- `docs/getting-started.md`: add a note about `with picsure.connect(...) as session:` idiom (now that Task 1 added `Session.close`).
- `CONTRIBUTING.md`: align `ruff format --check` to also cover `tests/`.
- `pyproject.toml`: `httpx>=0.27,<1`, `pandas>=2,<3`.
- `CHANGELOG.md`: `[Unreleased]` entries consolidating all of the above under `### Added` / `### Changed` / `### Fixed` / `### Removed`.
- `test_facade.py`: add assertions for the newly re-exported error subclasses.

**Tests:**
- `tests/unit/test_facade.py` — new exports present.

**Files:** All docs listed above + `src/picsure/__init__.py` + `tests/unit/test_facade.py` + `CHANGELOG.md` + `pyproject.toml` + `CONTRIBUTING.md`.

**Commit message:** `docs: fix facet-category examples, expand reference, re-export error subclasses; chore: add dependency upper bounds`.

---

## Execution order

1. Task 1 — Transport batch (unblocks 4xx mapping for everything downstream).
2. Task 2 — Export rewrite.
3. Task 3 — Search behavioral fixes.
4. Task 4 — Query build validation symmetry.
5. Task 5 — Query execution fixes.
6. Task 6 — Docs & cross-cutting.

After each task: run `uv run pytest tests/unit/ -q --cov=picsure --cov-fail-under=80` and `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/` before commit. Dispatch spec-compliance review (did you implement exactly what Task N specifies?) and code-quality review. Fix issues, re-review. Commit. Move on.

After all tasks: final review reading the whole diff; update `index.md` of the review directory with a "Resolution status" footer linking to each fix commit.
