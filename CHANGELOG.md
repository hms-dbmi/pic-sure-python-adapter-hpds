# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Changed
- **BREAKING:** `PicSureConsentDeniedError` now inherits from `PicSureAuthError` (via the new `PicSureAuthorizationError`) instead of directly from `PicSureError`. An `except PicSureAuthError` handler that previously let consent denials through now catches them, and an `except PicSureConsentDeniedError` clause placed *after* `except PicSureAuthError` becomes unreachable. Order consent-specific handlers before the general one.
- **BREAKING:** `PicSureConsentLookupError` now inherits from the new `PicSureServerError` rather than directly from `PicSureConnectionError`. It remains catchable as `PicSureConnectionError`, so retry logic keyed on that class is unaffected; code that distinguished it by exact parent must be updated.
- HTTP 401 and 403 are now classified by status before the response body is read. Previously a 403 carrying `errorType: consent_denied` bypassed the 401/403 mapping entirely while the same status without that field did not. Every 401 and 403 now raises an instance of `PicSureAuthError`.
- A TLS certificate that cannot be verified now raises `PicSureTLSError` naming the host and the `verify` argument / `PICSURE_SSL_VERIFY` env var, instead of a generic "temporarily unavailable" connection error. Certificate failures are no longer retried.
- A CA bundle that exists but cannot be loaded, because it is not PEM, is empty, or cannot be read, now raises `PicSureTLSError` naming the path and where it came from (the `verify` argument or `PICSURE_SSL_VERIFY`), instead of a bare `ssl.SSLError`.
- A `verify` path that does not exist now raises `PicSureValidationError` naming the path and where it came from (the argument or `PICSURE_SSL_VERIFY`), instead of a bare `FileNotFoundError` naming nothing.
- A CA bundle passed as `verify="/path/to/ca.pem"` (or `PICSURE_SSL_VERIFY`) is loaded into an `ssl.SSLContext` rather than handed to httpx as a string. httpx 0.28 deprecates `verify=<str>`, so the documented argument would have stopped working on a future httpx. What `verify` accepts is unchanged.
- Error messages are rewritten to name the operation grammatically. The old two-part template produced text such as "Could not fetch consents PSAMA."
- The default request timeout is raised from 30 seconds to ten minutes, because a large dataset legitimately takes minutes to assemble server-side. `PicSureClient(timeout=...)` overrides it.
- The token no longer reaches rendered tracebacks. Python prints the arguments and locals of *every* frame on a traceback, not only the frame that raised, so a crash anywhere below `connect()` published the bearer token into the user's notebook: measured at 118 contiguous characters of a 510-character token by default and the entire token under `--showlocals`. `connect(token=...)` still takes a plain string, but wraps it in an internal `SecretToken` that renders as a fixed placeholder and yields its value only through `reveal()`, and the raw parameter is deleted so it drops out of the frame. The same measurement now reports 2 to 3 characters, which is incidental overlap with ordinary source text rather than token material. This is the library-side counterpart of the integration-fixture change above. The wire format is unchanged: the `Authorization` header still carries the exact stripped token.
- `connect()` accepts a `SecretToken` as `token` as well as a plain `str`, so a caller or test fixture that already holds the wrapped form passes it through unchanged.
- `connect()` now sources the user's consent list from PSAMA's `/psama/user/me/consents` instead of `/psama/user/me/queryTemplate/`. The consent endpoint returns the identifiers directly, so the adapter no longer parses a doubly-encoded query template. The resulting `Session.consents` value is unchanged. Requires a backend that serves `/user/me/consents`.
- The integration `test_token` fixture returns a `SecretToken` instead of a plain `str`, and `connect()` accepts it directly. pytest prints the arguments of every frame in a traceback, so the plain string exposed up to 118 contiguous characters of the bearer token on any failure in any test that took the fixture. The integration `conftest.py` also scrubs token runs from failure output and captured stdout/stderr/log sections. Tests only; no library behaviour changes.
- The integration suite now prints an `integration tests skipped` section listing each skipped live test with its reason and naming any unset `PICSURE_TEST_*` variable, so a missing variable is visible in the run summary instead of reading as a pass. `PICSURE_TEST_GENE` was undocumented and silently skipped all four genomic live tests; it is now in `.env.example` and the testing docs.
- Developer-mode events rename `bytes_in` / `bytes_out` to `bytes_sent` / `bytes_received`, which read as the reverse of what they held. The DataFrames returned by the dev-mode reporting helpers use the new column names.
- `runQuery(..., "variant_count")` now parses the JSON object the server returns (`{"count": 1, "message": "Query ran successfully"}`). The parser expected a bare count string, so every successful variant count raised `PicSureQueryError` reporting the JSON body as a malformed count. A `count` sent as a JSON string is also accepted, obfuscated values included, and a bare count string still works for any deployment that sends one. `CountResult.raw` carries the whole response body for this result type, so the server's `message` is preserved without a field of its own.
- A variant-count response reporting that no variant filters were supplied now raises `PicSureQueryError` pointing at `buildGenomicFilter`, instead of returning `CountResult(value=0)`. The server does not evaluate a variant query without a genomic filter, so the zero read as "no matching variants" when nothing had been queried.
- `buildGenomicFilter(GenomicFilterKey.VARIANT_SEVERITY, ...)` now accepts the backend's own `Variant_severity` impact values (`HIGH`, `MODERATE`, `LOW`, `MODIFIER`) and sends them on the `Variant_severity` key unchanged. These are what `searchGenomicValues("Variant_severity")` returns, and all four were previously rejected, so the library's discovery call handed back values its own builder refused. `VariantSeverity` bucket labels keep expanding into `Variant_consequence_calculated` values; a single filter may not mix the two vocabularies. Values are matched exactly apart from surrounding whitespace, and a near miss is rejected with the accepted spelling in the message (`High` points at `HIGH`, `MEDIUM` at `MODERATE`). `MODIFIER` has no bucket equivalent and was previously unreachable.
- An empty response body where a count was expected now reports that the server answered HTTP 200 with an empty body, names what the request carried (the phenotypic concepts and genomic filter keys, or the select paths when there were no filters), and gives guidance that fits: with filters, check that each filter's shape matches its concept's type; without them, check the select paths. It previously reported a malformed count response. A `variant_count` query with an empty body carries the same request summary and names both possible causes, an unsupported deployment or a filter that could not be applied.
- `Session.searchGenomicValues` on a concept that is not a genomic annotation now raises `PicSureQueryError` naming the concept. The server answers HTTP 200 with an empty body for that case, which left nothing to decode and leaked a raw `json.decoder.JSONDecodeError` out of the library. Only the empty body is read that way; a body that is present but not JSON raises `PicSureQueryError` with the decoder's own message.
- A negative integer count in a `variant_count` or `cross_count` response is rejected with `PicSureQueryError`, matching what a negative count string already did.

### Added
- `picsure.PicSureAuthenticationError` (HTTP 401: the token itself) and `picsure.PicSureAuthorizationError` (HTTP 403: the account's permissions), both subclasses of `PicSureAuthError`.
- `picsure.PicSureServerError` (HTTP 5xx: the server answered but failed) and `picsure.PicSureTLSError` (certificate verification failed), both subclasses of `PicSureConnectionError`.
- `VariantFrequency` gains `LOW_FREQUENCY` (`"Low_frequency"`) and `ULTRA_RARE` (`"Ultra_rare"`), which are present in deployed annotation sets but were missing from the enum. `NOVEL` is deprecated rather than removed: it appears in no observed annotation set or backend fixture. The buckets are per-deployment data, so `searchGenomicValues("Variant_frequency_as_text")` is the authoritative source and this key still accepts any string.

## [2.0.0] - 2026-06-15

### Changed
- **BREAKING:** The query builders are renamed to a `build*` triplet whose names match their return types: `createSubQuery` → `buildClause` (returns `Clause`), the clause-combining `buildQuery` → `buildClauseGroup` (returns `ClauseGroup`). The name `buildQuery` is now the query *assembler* `buildQuery(phenotypicFilter=None, includeConcepts=())` and returns a `Query`.
- **BREAKING:** `Query` is now a dataclass (`phenotypicFilter`, `includeConcepts`) rather than a `Clause | ClauseGroup` type alias. `runQuery`/`exportAsPFB`/`saveQueryByName` accept a `Query` or a bare `Clause`/`ClauseGroup`. A saved query that selects output concepts now loads as a `Query` (previously a `ClauseGroup` of `SELECT` clauses).

### Removed
- **BREAKING:** `PhenotypicFilterType.SELECT` is removed. To include concept paths in the output without filtering, pass them to `buildQuery(includeConcepts=...)` instead of building a `SELECT` clause.

### Added
- `picsure.buildGenomicFilter(key, *, values)` builds a single categorical genomic filter. `values` is required (string or list of strings); `VariantFrequency` members are accepted and coerced. Variant-spec and SNP keys are rejected with an actionable error.
- `picsure.genomicConsequences()` returns an offline DataFrame of all variant consequences with a `severity` and `consequence` column. Available on any platform; no network call.
- `picsure.buildQuery(genomicFilters=None)` - `buildQuery` now accepts an optional `genomicFilters` list. Genomic filters are AND-combined with the phenotypic filter; a genomic-only query (no `phenotypicFilter`) is valid.
- `picsure.connect(supports_genomic=None)` - `connect` accepts an optional `supports_genomic` flag for platforms that do not auto-detect genomic capability. Genomic operations are available on BDC_AUTHORIZED, BDC_DEV_AUTHORIZED, BDC_PREDEV_AUTHORIZED, and NHANES_AUTHORIZED; all `*_OPEN` platforms are not genomic-capable.
- `Session.searchGenomicValues(genomicConceptPath, *, query="", page=1, size=50)` performs a paginated server lookup of valid values for any genomic key (genes, consequences). Returns a pandas DataFrame; pagination metadata is on `df.attrs`. Available on authorized platforms only.
- `GenomicFilter` dataclass representing a single categorical genomic filter (`key`, `values`).
- `VariantFrequency` enum with members `RARE`, `COMMON`, and `NOVEL` for use with the `Variant_frequency_as_text` genomic key.
- Variant result types for `runQuery`: `variant_count` (returns `CountResult`), `variant_list` (returns `list[str]`), `vcf_excerpt` (returns DataFrame), and `aggregate_vcf_excerpt` (returns DataFrame). These types are not served by BDC primary environments yet; the adapter raises `PicSureQueryError` with a clear message on an empty or 5xx response.
- `picsure.buildQuery(phenotypicFilter=None, includeConcepts=())` assembles a `Query` from a filter tree plus the concept paths to return as output columns. `includeConcepts` preserves order and de-duplicates.
- `picsure.removeSubQuery(query, target)` returns a copy of `query` with every structurally-equal occurrence of `target` removed, recursively through nested groups. Emptied `ClauseGroup`s are dropped. Raises `PicSureValidationError` if the whole tree would be removed.
- `picsure.replaceClause(query, target, replacement)` returns a copy of `query` with every structurally-equal occurrence of `target` swapped for `replacement`.
- `Session.saveQueryByName(query, name, *, overwrite=False)` submits the query via `POST /picsure/v3/query` and associates `name` with it via `POST /dataset/named/`. With `overwrite=True`, an existing record with the same name is `PUT`-updated to point at the freshly-submitted query. The backend's `NamedDataset` constraints (`name` max 255 chars, allowed: letters, digits, spaces, ``- _ \ / ? + = [ ] . ( ) : " '``) are validated client-side. Refused on open-access deployments. Returns the new query ID — pass it to `loadQueryByID` / `runQueryByID` later.
- `PicSureClient.put_json()` on the transport client (used by the `saveQueryByName` overwrite path).
- `picsure.PicSureAuthError`, `picsure.PicSureConnectionError`, `picsure.PicSureQueryError`, and `picsure.PicSureValidationError` are now re-exported from the top-level package, so `from picsure import PicSureQueryError` works (previously required `from picsure.errors import ...`).
- `Session.facets(term="", *, facets=None)` and `Session.showAllFacets(term="", *, facets=None)` now accept optional search term and facet selections. Counts returned are contextual to the provided search when term/facets are supplied; passing no arguments preserves the previous "global counts" behaviour.
- `DictionaryEntry` exposes `min`, `max`, `allow_filtering`, `meta`, and `study_acronym` fields. The corresponding columns (`min`, `max`, `allowFiltering`, `meta`, `studyAcronym`) are added to the `Session.searchDictionary` DataFrame result.
- `picsure.connect()` to authenticate and connect to a PIC-SURE instance.
- `Session.getResourceID()` to list available resources as a DataFrame.
- Platform name resolution for BDC Authorized, BDC Open, and Demo.
- Actionable error messages via `PicSureError`.
- Unit test suite with mocked HTTP via respx.
- Integration test scaffold gated by `PICSURE_INTEGRATION` env var.
- GitHub Actions CI with Python 3.10/3.11/3.12 matrix.
- `Session.searchDictionary()` to search the data dictionary with optional facet filtering.
- `Session.facets()` to retrieve available facet categories as a `FacetSet`.
- `Session.showAllFacets()` to display all facet categories and values as a DataFrame.
- `FacetSet` for building facet selections with validation.
- Search result deduplication by concept path.
- Zero-result searches return empty DataFrames with a stderr note.
- `picsure.createSubQuery()` to build individual filter clauses (FILTER, ANYRECORD, SELECT, REQUIRE).
- `picsure.buildQuery()` to combine clauses with AND/OR logic, supporting arbitrary nesting.
- `PhenotypicFilterType` and `GroupOperator` enums for type-safe clause and group construction.
- `Clause`, `ClauseGroup`, and `Query` types with `to_query_json()` serialization.
- `CountResult` dataclass exposing `value`, `margin`, `cap`, `raw`, and an `obfuscated` property for count query responses.
- Input validation with actionable error messages for invalid clause configurations.
- `Session.runQuery()` to execute queries and return a `CountResult`, a `dict[str, CountResult]` (cross-count), or a `DataFrame` (participant / timestamp).
- `Session.runQueryByID(query_id, type="count")` to load a saved query by ID and execute it in one call, returning the same result types as `runQuery`.
- `Session.exportAsPFB()` to export query results as PFB files.
- `Session.exportCSV()` and `Session.exportTSV()` to save DataFrames to disk.
- `PicSureClient.post_raw()` for non-JSON response handling.
- Query type validation with actionable error messages ("count", "participant", "timestamp").
- Documentation site with MkDocs + Material theme.
- Auto-generated API reference from docstrings via mkdocstrings.
- User guides: search, facets, query building, running, and exporting.
- Migration guide from PicSureHpdsLib with side-by-side examples.
- Docs CI workflow: build on PR, deploy to GitHub Pages on push to main.

### Changed
- `Session.runQuery` docstring now documents that ``participant`` / ``timestamp``
  DataFrame cells may contain tab-joined multi-values; callers should use
  ``df[col].str.split("\t")`` when they need individual observations.
- Query endpoint changed from `/picsure/query/sync` to `/picsure/v3/query/sync`.
- `Clause.to_query_json()` / `ClauseGroup.to_query_json()` now emit the v3 `PhenotypicClause` / `PhenotypicSubquery` schema (`operator` / `phenotypicClauses` / `not` for groups; `phenotypicFilterType` / `conceptPath` / `values` / `min` / `max` / `not` for leaves). The previous wire format is no longer produced.
- `Clause.to_query_json()` now raises `PicSureValidationError` for `SELECT` clauses. Use `Clause.select_paths()` / `ClauseGroup.select_paths()` to retrieve output paths instead.
- `Session.runQuery(..., type="count")` now returns a `CountResult` dataclass instead of a plain `int`. Access the integer count via `result.value`; check `result.cap` for suppressed small-count responses (`result.value` is `None` in that case) and `result.margin` for noisy responses.
- `Session.runQuery(..., type="cross_count")` now returns a `dict[str, CountResult]` keyed by concept path instead of a DataFrame.
- `PicSureClient` now strips leading/trailing whitespace from the bearer token; a whitespace-only token is treated as anonymous (no `Authorization` header, `request-source: Open`).
- `Session.exportAsPFB()` / `picsure._services.export.export_pfb` now use the async flow (`POST /picsure/v3/query` → poll `/query/{id}/status` → `POST /query/{id}/result`) rather than `/query/sync`. Response bytes are streamed directly to disk. Polling uses exponential backoff (1s, 2s, 4s, … capped at 60s per poll) and fails with `PicSureConnectionError` after 10 minutes of cumulative waiting. The output file is written atomically (`.part` staging file + rename on success).
- `createSubQuery` now raises `PicSureValidationError` for additional invalid combinations:
  FILTER clauses with both `categories` and `min`/`max`; REQUIRE or SELECT clauses
  with any of `categories`/`min`/`max`; empty keys lists. These were previously
  silently accepted and the extra arguments discarded (or rejected downstream by
  the server with a less actionable error).
- `ClauseGroup.to_query_json()` now raises `PicSureValidationError` if any nested
  child is a SELECT clause (previously it silently stripped them). This is
  symmetric with `Clause.to_query_json()`, which has always raised on SELECT.
  `ClauseGroup.select_paths()` and `build_query_body()` continue to handle SELECT
  extraction at the top level; inline SELECTs inside a group are the error case.
- `createSubQuery` now defensively copies list arguments (`keys`, `categories`), so
  mutating the caller's lists after construction does not affect the resulting
  `Clause`.
- Dependency ranges tightened to upper-bounded majors (`httpx>=0.27,<1`, `pandas>=2,<3`) to avoid silent breakage on major releases.
- `CONTRIBUTING.md` lint instructions now cover both `src/` and `tests/`, matching the CI gate.

### Removed
- Wire-format docstrings on `Clause` and `ClauseGroup` no longer advertise the
  `not` / negation field. The adapter still emits `"not": False` on the wire, but
  negation is not supported by the public API; support will return in a later
  release.

### Fixed
- `Session.runQuery(..., type="participant")` and `type="timestamp"` now surface
  malformed-CSV responses as `PicSureQueryError` with a body preview (previously
  leaked raw pandas `ParserError` / `EmptyDataError` / `UnicodeDecodeError`).
- `Session.runQuery(..., type="cross_count")` explicitly handles the direct-HPDS
  response shape (`{concept_path: integer}`), not only the aggregate-obfuscation
  response shape (`{concept_path: count_string}`).
- `Session.runQuery` now validates the query argument at body construction so
  that passing a plain `dict` raises `PicSureValidationError` ("Query must be a
  Clause or ClauseGroup") rather than a confusing `AttributeError` from an
  internal accessor.
- `Session.searchDictionary` now raises `PicSureQueryError` when the server's paginated response indicates the result set was truncated (`last != True` or `content` length doesn't match `totalElements`). Previously the adapter silently returned the partial page.
- PFB export against v3 PIC-SURE was silently broken: the previous implementation posted `DATAFRAME_PFB` to `/query/sync`, which v3 HPDS has no handler for. Unit tests passed only because `respx` served a canned 200 body at the wrong URL.
- 4xx responses during PFB submission / status / result are now surfaced as `PicSureValidationError` / `PicSureQueryError` (previously the 4xx body bytes would be written to disk as if they were PFB).
- `OSError` / `PermissionError` during disk writes in `export_pfb` are now wrapped in `PicSureConnectionError` with the target path in the message (previously leaked raw).
- Getting-started and search-and-facets guide examples used ``"study_ids"`` as the facet category; the server returns ``"dataset_id"``. Guides updated to match. Users copy-pasting the earlier examples would have seen ``PicSureValidationError``.
- ``showAllFacets`` DataFrame column list in the user guide was outdated. Now correctly documents the six columns (``category``, ``Category Display``, ``display``, ``description``, ``value``, ``count``).
- Raw-string code snippets ending in a backslash (e.g. ``r"\phs1\sex\"``) were unterminated string literals and would ``SyntaxError`` on copy-paste. Replaced with doubled-backslash non-raw strings across ``README.md`` and the guides.
- API reference now documents `Platform`, `CountResult`, the `PicSureError` subclasses, and `Session.consents` / `Session.total_concepts` properties, which were exported but missing from the reference.
