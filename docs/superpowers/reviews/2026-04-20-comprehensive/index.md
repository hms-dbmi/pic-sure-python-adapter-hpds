# Comprehensive Code Review — 2026-04-20

**Target:** `pic-sure-python-adapter-hpds`
**Commit reviewed:** `5a58091670e458fda33d3b9fbe3f1b37ef52a04c`
**Areas:** Connection & Transport • Search • Query building • Query execution • Export • Cross-cutting
**Trigger:** Search results produced by the Python adapter do not match `PIC-SURE-Frontend` for equivalent inputs.

---

## Executive summary

**The search-vs-UI mismatch is not a wire-level bug.** For a POST to `/picsure/proxy/dictionary-api/concepts`, the adapter sends the same URL, method, body keys, and facet-object shape (including `categoryRef`) as the UI does; the backend accepts either form. The observed difference is two behavioral divergences: (1) `fetch_facets` always POSTs `{search: "", facets: []}` to `/facets`, so `Session.showAllFacets` / `Session.facets()` return **global** counts rather than counts **contextual** to an in-progress search (the UI does the opposite); (2) Continuous-concept fields (`min`, `max`, `allowFiltering`, `meta`, `studyAcronym`) are silently dropped from `DictionaryEntry`, leaving Continuous rows with empty `values: []`.

Three other genuinely serious issues turned up outside the search area:

1. **`Platform.AIM_AHEAD` ships with a literal placeholder UUID** — any session created with it will fail at first query.
2. **PFB export is pointed at the wrong endpoint.** `export_pfb` POSTs `DATAFRAME_PFB` to `/picsure/v3/query/sync`, but v3 HPDS has no case for that result type on sync; the actual PFB path is the async `POST /query` → poll → `POST /query/{id}/result` flow. The tests pass only because respx mocks an arbitrary 200 body.
3. **Transport only maps 401/403 and ≥500.** Any other 4xx (400/404/422/429) falls through and crashes downstream callers with misleading `PicSureQueryError`, `json.JSONDecodeError`, or a 4xx response body written to disk as a PFB file. This root cause surfaces independently in four of the six review files.

---

## Findings by severity

### Critical

- **Placeholder AIM-AHEAD resource UUID in a public enum** — `src/picsure/_transport/platforms.py:103` — full entry in [connection-transport.md](connection-transport.md#critical).
- **PFB export likely wrong against v3 sync endpoint; test passes only because of mocks** — `src/picsure/_services/export.py:13,33,36` — full entry in [export.md](export.md#critical).
- **4xx responses bypass transport mapping → downstream parsers crash with misleading errors** — `src/picsure/_services/query_run.py:63-68, 168-187, 190-194` (manifestation) / `src/picsure/_transport/client.py:73-81` (root cause) — full entry in [query-run.md](query-run.md#critical). Also manifests in [export.md — "4xx response bodies are written to disk as PFB"](export.md#important) and is the test-coverage gap in [cross-cutting.md — "Non-standard 4xx (400, 404, 422, 429) are unmapped and untested"](cross-cutting.md#important). Upstream entry lives in [connection-transport.md — "Non-401/403 4xx responses are silently returned, not mapped"](connection-transport.md#important).

### Important

**Transport / lifecycle**
- **POST requests retry on 5xx (non-idempotent)** — `src/picsure/_transport/client.py:59-79` — double-executes `/query/sync` and PFB exports server-side on transient failures. Canonical: [connection-transport.md](connection-transport.md#important). Also re-stated for `run_query` in [query-run.md](query-run.md#important) and for `export_pfb` in [export.md](export.md#important).
- **`Session` has no `close()` / context manager** — `src/picsure/_models/session.py:18` + `src/picsure/_transport/client.py:85` — leaks httpx connection pools in notebook kernels. Canonical: [connection-transport.md](connection-transport.md#important). Docs footprint in [cross-cutting.md — "Getting-started suggests repeated `picsure.connect()` without mentioning cleanup"](cross-cutting.md#important).
- **`connect()` silently degrades whitespace-only token to anonymous mode** — `src/picsure/_services/connect.py:79-82` — user sees "token invalid or expired" on a `requires_auth=True` platform instead of "platform requires a token but none was provided." [connection-transport.md](connection-transport.md#important).
- **`post_json` typed `-> dict` but some endpoints return JSON arrays** — `src/picsure/_transport/client.py:38-46` — `/facets` returns a list at the top level; caller relies on this accidentally. [connection-transport.md](connection-transport.md#important) and [search.md — "Duck-typing on `fetch_facets`'s response shape"](search.md#important).

**Search (behavioral divergences the user observed)**
- **`fetch_facets` always sends `{search: "", facets: []}`; counts are global not contextual** — `src/picsure/_services/search.py:126-148`. Canonical: [search.md](search.md#important).
- **Continuous-concept `min`/`max`/`allowFiltering`/`meta`/`studyAcronym` dropped from `DictionaryEntry`** — `src/picsure/_models/dictionary.py:18-34` + `src/picsure/_services/search.py:16-33,238-255`. Canonical: [search.md](search.md#important).
- **No sanity check that the "one big page" returned the full dataset** — `src/picsure/_services/search.py:103-123` — silent truncation possible if server caps `page_size` or `total_concepts` is stale. [search.md](search.md#important).
- **Memory: single 29k-row request builds the whole DataFrame at once** — `src/picsure/_services/search.py:73-123` — design tradeoff; worth a pagination knob on large dictionaries. [search.md](search.md#important).

**Query building (silent-accept bugs)**
- **`createClause` does not reject FILTER with both `categories` and `min`/`max`** — `src/picsure/_services/query_build.py:65-70` — backend rejects; adapter should too. [query-build.md](query-build.md#important).
- **`createClause` does not reject REQUIRE with `categories`/`min`/`max`** — `src/picsure/_services/query_build.py:51-70` — silently discarded later; symmetric with the ANYRECORD check. [query-build.md](query-build.md#important).
- **`createClause` does not reject SELECT with `categories`/`min`/`max`** — same silent-discard pattern. [query-build.md](query-build.md#important).
- **`not` hard-coded to `False`; no public way to negate** — `src/picsure/_models/clause.py:80,91` + `src/picsure/_models/clause_group.py:54` — backend accepts `not` on both layers; adapter docstrings advertise it but no API surface exposes it. [query-build.md](query-build.md#important).
- **`ClauseGroup.to_query_json()` silently drops SELECT children** — `src/picsure/_models/clause_group.py:46-55` — asymmetric with `Clause.to_query_json()` which raises; an `OR` group with a SELECT branch does not do what the user wrote. [query-build.md](query-build.md#important).
- **`buildClauseGroup` accepts single-clause list and empty-of-SELECT groups** — `src/picsure/_services/query_build.py:106-109` — produces invalid-per-contract bodies if called directly. [query-build.md](query-build.md#important).
- **Frozen dataclasses expose mutable `list` fields** — `src/picsure/_models/clause.py:50-54` + `src/picsure/_models/clause_group.py:34` — `clause.keys.append(...)` still works post-construction. [query-build.md](query-build.md#important).

**Query execution**
- **CROSS_COUNT values may be JSON integers (HPDS direct), not only count strings** — `src/picsure/_services/query_run.py:187` — docstring and code both claim "string" but `str(int)` handles it by accident. [query-run.md](query-run.md#important).
- **`_parse_dataframe` does not wrap pandas parse errors in `PicSureQueryError`** — `src/picsure/_services/query_run.py:190-194` — pandas `ParserError` leaks through the public surface. [query-run.md](query-run.md#important).
- **DATAFRAME cells can contain tab-joined multi-values; undocumented** — `src/picsure/_services/query_run.py:190-194` — a multi-observation row appears as `"120\t130\t118"` in a single column. [query-run.md](query-run.md#important).
- **No test coverage for non-2xx non-(401/403/5xx) responses** — `tests/unit/test_query_run.py` — pins the 4xx Critical above. [query-run.md](query-run.md#important).

**Export**
- **Response read fully into memory before disk write** — `src/picsure/_services/export.py:36,42` — multi-GB PFB doubles peak memory. [export.md](export.md#important).
- **Disk / permission / disk-full errors surface as raw `OSError`, not `PicSureError`** — `src/picsure/_services/export.py:42,52,62` — breaks the documented error contract. [export.md](export.md#important).
- **Network interruption mid-download leaves truncated files at the target path** — `src/picsure/_services/export.py:36,42` — no `.part`-then-rename atomic-write. [export.md](export.md#important).
- **No extension / filename enforcement** — `src/picsure/_services/export.py:42,52,62` — `export_csv(df, "out.pfb")` silently writes CSV to `.pfb`. [export.md](export.md#important).
- **Docstrings under-document failure modes** — `src/picsure/_services/export.py:22-32,46-50,58-61` — `export_pfb` lists only `PicSureConnectionError`; CSV/TSV have no Raises block. [export.md](export.md#important).

**Docs / public surface / tests**
- **`Platform` and `CountResult` in `__all__` but absent from `docs/reference/api.md`** — [cross-cutting.md](cross-cutting.md#important).
- **`PicSureError` subclasses not re-exported from top-level package** — users must `from picsure.errors import PicSureAuthError`. [cross-cutting.md](cross-cutting.md#important).
- **Guide facet category is `"study_ids"` but live server / fixtures return `"dataset_id"`** — `docs/getting-started.md:53`, `docs/guides/search-and-facets.md:57,60,73,87`. Copy-pasting the guide will raise `PicSureValidationError`. [cross-cutting.md](cross-cutting.md#important).
- **`showAllFacets` DataFrame columns drift between guide (`category, display, value, count`) and code (`category, Category Display, display, description, value, count`)** — `docs/guides/search-and-facets.md:47-48`. [cross-cutting.md](cross-cutting.md#important).
- **`Session` properties `consents` and `total_concepts` undocumented** — `docs/reference/api.md:59-72`. [cross-cutting.md](cross-cutting.md#important).
- **No connect-level test that a whitespace-only token yields an anonymous Session** — [cross-cutting.md](cross-cutting.md#important).
- **No transport test for HTTP 429 retry-after semantics (and no code handling either)** — [cross-cutting.md](cross-cutting.md#important).

**Miscellaneous**
- **Dictionary-api `request-source` is not forwarded to the downstream service** — `src/picsure/_transport/client.py:21-29` comment overstates the contract; `ProxyWebClient` only forwards `authorization, x-api-key, x-request-id`. [connection-transport.md](connection-transport.md#important).
- **NHANES platform URL has trailing slash; custom URLs get stripped** — `src/picsure/_transport/platforms.py:88,95,174`. [connection-transport.md](connection-transport.md#important).
- **Search dedup keys on `concept_path` alone; backend equality is `(dataset, conceptPath)`** — equivalent today on BDC but brittle. [search.md](search.md#important).
- **No unit tests yet for transport 5xx retry, 401/403 mapping, whitespace-token stripping beyond the client layer** — [connection-transport.md](connection-transport.md#important) / [cross-cutting.md](cross-cutting.md#important).

### Minor

Collected across all area files; not re-listed here. Highlights:

- Enum-casing inconsistency (`ClauseType` values lowercase, `GroupOperator` uppercase) — [query-build.md](query-build.md#minor).
- `_PICSURE_QUERY_SYNC_PATH` duplicated between `export.py` and `query_run.py` — [export.md](export.md#minor).
- `README.md` and guide snippets use raw strings ending in a backslash (`r"\phs1\sex\"`) — Python `SyntaxError` on copy-paste — [cross-cutting.md](cross-cutting.md#minor).
- `pyproject.toml` dependencies are lower-bound only; consider upper bounds for the 0.1.0 release — [cross-cutting.md](cross-cutting.md#minor).
- `CONTRIBUTING.md` lint command checks only `src/`; CI checks `src/ tests/` — drift risk — [cross-cutting.md](cross-cutting.md#minor).
- `show_all_facets` docstring claims four columns; code emits six — [search.md](search.md#minor).
- `show_all_facets` emits facet options with `count == 0`; UI hides them — [search.md](search.md#minor).

See each area file's `### Minor` section for the complete list.

---

## Cross-links (same root cause reported in multiple files)

- **4xx fall-through in transport** — canonical entry: [connection-transport.md](connection-transport.md#important). Also appears as:
  - [query-run.md — Critical "4xx responses bypass transport mapping"](query-run.md#critical) (most severe manifestation)
  - [export.md — "4xx response bodies are written to disk as if they were PFB"](export.md#important)
  - [cross-cutting.md — "Non-standard 4xx (400, 404, 422, 429) are unmapped and untested"](cross-cutting.md#important) (test-coverage view)

- **Non-idempotent POST retry** — canonical: [connection-transport.md](connection-transport.md#important). Also in [query-run.md](query-run.md#important) and [export.md](export.md#important).

- **`Session` has no close/context-manager** — canonical: [connection-transport.md](connection-transport.md#important). Docs footprint in [cross-cutting.md](cross-cutting.md#important).

- **`post_json` return type drift (dict vs list)** — canonical: [connection-transport.md](connection-transport.md#important). Concrete manifestation in [search.md](search.md#important).

---

## Area summaries

- **[Connection & Transport](connection-transport.md)** — Wire shape and BDC gateway contract are correct (Bearer + `request-source`, whitespace-token → anonymous, JWTFilter accepts what's sent). One Critical (AIM-AHEAD placeholder UUID) and several Important lifecycle/error-handling gaps: 4xx fall-through, non-idempotent POST retry, missing `Session.close()`, silent token-degradation to anonymous, `post_json` type-drift. 87 lines.

- **[Search](search.md)** — Cross-stack deep-dive against the UI HAR and `picsure-dictionary`. No Critical findings; wire format matches the UI. Two behavioral divergences explain the user's observation: `fetch_facets` always requests global counts, and Continuous-concept fields are dropped from the DataFrame. Additional issues around truncation guards, memory, dedup semantics, and response-shape duck-typing. 570 lines (includes full captured-request / derived-request JSON and the divergence table).

- **[Query building](query-build.md)** — No Critical findings. Wire format (enum strings, `PhenotypicFilter` / `PhenotypicSubquery` / top-level `Query` shape) is correct byte-for-byte. The Important findings cluster around validation symmetry: `createClause` rejects ANYRECORD+extras but silently accepts bad combos for FILTER / REQUIRE / SELECT; `ClauseGroup.to_query_json` silently drops SELECTs (asymmetric with `Clause.to_query_json`, which raises); `not` is hard-coded to `False` without public negation; frozen dataclasses expose mutable lists. 115 lines.

- **[Query execution](query-run.md)** — One Critical (4xx manifestation, as above). Count-string regexes match the aggregate-obfuscation emitter exactly; request body and `expectedResultType` strings match `ResultType.java`; `authorizationFilters` omission is safe by default. Important gaps: CROSS_COUNT integer values not explicitly supported, pandas parse errors unwrapped, DATAFRAME multi-value tab-join undocumented. 202 lines.

- **[Export](export.md)** — One Critical (`export_pfb` probably wrong endpoint — PFB is served via the async `POST /query` → poll → `POST /query/{id}/result` flow, not `/query/sync`). Several Important: 4xx body written to disk, full-memory buffering, raw `OSError` leak, no atomic write, no extension enforcement, docstring failure-mode drift. 100 lines.

- **[Cross-cutting](cross-cutting.md)** — No Critical. Test suite is broad and well-grounded in realistic fixtures; CI matrix (Py 3.10/3.11/3.12 + ruff + mypy + `--cov-fail-under=80`) is correctly wired; docs CI builds in `--strict` on PRs and deploys only on main. Important gaps: `Platform`/`CountResult` missing from API reference, `PicSureError` subclasses not re-exported, guide facet category mismatches the server (`study_ids` vs `dataset_id`), `showAllFacets` column list drifts between guide and code, no 4xx / 429 tests, `Session` properties undocumented. 179 lines.

---

## Recommended next actions

These are decisions for the user to make — not a TODO list. Triage and prioritization happen after this document is read.

1. **Decide the PFB export contract before shipping.** Either switch `export_pfb` to the async flow (`POST /query` → poll → `POST /query/{id}/result`) or coordinate with HPDS to add a synchronous PFB route. The current sync call against v3 will return 500 in production; tests pass only because respx serves a canned body.
2. **Decide whether `showAllFacets` should mirror the UI (contextual counts) or keep its current "global counts" behavior.** If it keeps the current behavior, the docstring and the user guide must say so clearly — right now, users reasonably expect UI parity.
3. **Decide the 4xx mapping policy in transport.** A minimal version: 400/422 → `PicSureValidationError`, 404 → `PicSureQueryError`, 429 → a friendly `PicSureConnectionError` with a `Retry-After`-aware message. Whatever the final mapping, tests at the transport layer should pin every branch.
4. **Decide whether negation (`not`) is part of the v0.1 public API or explicitly deferred.** Either expose it on both `Clause` and `ClauseGroup` or remove the mentions from docstrings.
5. **Decide whether the adapter should surface Continuous-concept `min`/`max` in the search DataFrame.** If yes, extend `DictionaryEntry`; if no, document the drop.
6. **Decide whether `AIM_AHEAD` ships in v0.1.** If the UUID isn't available yet, remove the enum member (or guard construction) rather than ship a placeholder string.
7. **Align docs and code for facet category examples and `showAllFacets` columns before the first public release.** The copy-paste experience matters for the getting-started guide.

---

## Resolution status (2026-04-21)

All Critical findings and the vast majority of Important findings have been resolved on branch `worktree-fix-code-review-items`. Fixes landed as six focused commits:

| Area | Commit | Summary |
|---|---|---|
| Transport | [`30d8699`](../../../../.git) | 4xx → `PicSureValidationError` / `PicSureQueryError` / `PicSureConnectionError` mapping with `Retry-After` honored; POST retry restricted to GET and connection/timeout errors; `Session.close()` / `__enter__` / `__exit__`; `Platform.AIM_AHEAD` removed; actionable error when a `requires_auth=True` platform receives a whitespace-only token. |
| Export | [`57e9be1`](../../../../.git) | `export_pfb` rewritten to the async v3 flow (`POST /picsure/v3/query` → poll `/query/{id}/status` → stream `/query/{id}/result` to disk). Exponential backoff (1s, 2s, 4s, …, capped at 60s per poll; fail after 600s cumulative). Atomic `.part → os.replace`. 4xx mapped to actionable exceptions; `OSError` wrapped in `PicSureConnectionError`. |
| Search | [`cf94499`](../../../../.git) | `Session.facets(term=..., facets=...)` and `Session.showAllFacets(term=..., facets=...)` now return **contextual** counts (matching the UI) when term/facets are supplied; `DictionaryEntry` surfaces `min`/`max`/`allow_filtering`/`meta`/`study_acronym` and the search DataFrame gains matching columns; truncation guard raises `PicSureQueryError` when `last != True` or the row count disagrees with `totalElements`. |
| Query building | [`0cdfe01`](../../../../.git) | Symmetric `PicSureValidationError` for FILTER-with-both, REQUIRE/SELECT-with-extras, and empty keys lists; `ClauseGroup.to_query_json()` now raises on SELECT children (symmetric with `Clause.to_query_json()`); defensive list copies in `createClause`; `not` / negation removed from wire-format docstrings. |
| Query execution | [`e2116fa`](../../../../.git) | `_parse_dataframe` wraps pandas `ParserError` / `EmptyDataError` / `UnicodeDecodeError` in `PicSureQueryError` with body preview; `_parse_cross_count` explicitly supports direct-HPDS integer values; `run_query` docstring documents tab-joined multi-value cells; non-Clause/ClauseGroup queries now fail loudly up front rather than via `AttributeError`. |
| Docs & cross-cutting | [`b4068a7`](../../../../.git) | `Platform`, `CountResult`, `PicSureError` subclasses, and `Session.consents` / `Session.total_concepts` / `Session.close` surfaced in `docs/reference/api.md`; `PicSureError` subclasses re-exported from the top-level package; guides corrected (`study_ids` → `dataset_id`, `showAllFacets` column list, raw-string-ending-in-backslash examples); `CONTRIBUTING.md` lint path aligned with CI; `pyproject.toml` dependencies upper-bounded (`httpx<1`, `pandas<3`); `Session.close()` context-manager idiom documented in getting-started. |

**Final verification** at commit `b4068a7`:
- `pytest tests/unit/ -q --cov=picsure --cov-fail-under=80` → 388 passed, 94.71% coverage.
- `ruff check src/ tests/`, `ruff format --check src/ tests/`, `mypy src/` — all clean.
- `mkdocs build --strict` — clean.

**Intentionally deferred (not yet resolved):**
- **Memory pagination for very large searches** (Important in `search.md`). The "one big page" strategy is a deliberate design tradeoff; a `page_size`/pagination knob is future work when a deployment with a significantly larger dictionary shows up.
- **`request-source` forwarding by the dictionary-api proxy** (Important in `connection-transport.md`). Backend-side concern; the Python adapter's comment was tightened but the gateway behavior is unchanged.
- **Dedup by `(dataset, conceptPath)`** (Minor in `search.md`). Equivalent to path-only dedup on BDC today.
- **Enum value casing** on `ClauseType` (Minor in `query-build.md`). Cosmetic.
- **Negation (`not`) public API**. Per user decision on 2026-04-21: deferred to a future release. Docstring mentions have been removed so there is no implied support.
- Various other Minor items marked "non-actionable observations" in the area files.

Plan this was executed against: [`2026-04-21-comprehensive-review-fixes.md`](../../plans/2026-04-21-comprehensive-review-fixes.md).
