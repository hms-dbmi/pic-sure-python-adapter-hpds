# Query execution — Code Review

## Scope

Reviewed at commit `5a58091670e458fda33d3b9fbe3f1b37ef52a04c`:

- `src/picsure/_services/query_run.py` — `/picsure/v3/query/sync` orchestration,
  count-string parsing (`_COUNT_EXACT`/`_COUNT_NOISY`/`_COUNT_SUPPRESSED`),
  CROSS_COUNT JSON dispatch, CSV/DataFrame decoding, error translation.
- `src/picsure/_models/count_result.py` — the `CountResult` dataclass
  (value/margin/cap/raw + derived `obfuscated`).
- `tests/unit/test_query_run.py` — coverage context for findings.

Contract references consulted (not modified):

- `pic-sure-hpds/client-api/.../query/ResultType.java` — enum of accepted
  `expectedResultType` strings.
- `pic-sure-hpds/client-api/.../query/v3/Query.java` — request record; confirms
  `authorizationFilters` null-safe with `List.of()` default.
- `pic-sure-hpds/service/.../service/PicSureV3Service.java::_querySync` — actual
  wire-format router for the sync endpoint.
- `pic-sure-hpds/processing/.../v3/CountV3Processor.java` — `runCounts → int`,
  `runCrossCounts → Map<String, Integer>`.
- `pic-sure-hpds/processing/.../v3/MultiValueQueryV3Processor.java` — DATAFRAME
  header `[patient_id, <concept_path>...]`; multi-values tab-joined in cell.
- `pic-sure-hpds/processing/.../v3/TimeseriesV3Processor.java` — DATAFRAME_TIMESERIES
  header `[PATIENT_NUM, CONCEPT_PATH, NVAL_NUM, TVAL_CHAR, TIMESTAMP]`.
- `pic-sure-hpds/processing/.../io/CsvWriter.java` — fastcsv writer emitting
  standard comma-quoted CSV.
- `pic-sure/pic-sure-resources/.../AggregateDataSharingResourceRSV3.java` —
  obfuscation layer emitting the `"N ±M"` / `"< T"` count strings; fixtures in
  `.../src/test/resources/*_obfuscated_result.json` document the exact wire format.
- `pic-sure/pic-sure-api-war/.../PicsureQueryV3Service.java::querySync` —
  forwards request to the configured resource RS (HPDS direct, or the aggregate
  obfuscating proxy) verbatim.

## Strengths

- Count-string regexes exactly match the three shapes emitted by the aggregate
  obfuscation layer: `"42"` (int → `_COUNT_EXACT`), `"11305 ±3"` with a space
  before `±` and none after (matches `_COUNT_NOISY` via `\s*`), `"< 10"` with a
  space after `<` (matches `_COUNT_SUPPRESSED` via `\s*`). See
  `AggregateDataSharingResourceRSV3.java:725-727` (`randomize`) and
  `:746-756` (`aggregateCount`) plus the checked-in fixtures at
  `.../src/test/resources/*_obfuscated_open_access_cross_count_obfuscated_result.json`.
- `_COUNT_NOISY` tolerates both `"42 ±3"` and `"42±3"`; `_COUNT_SUPPRESSED`
  tolerates both `"< 10"` and `"<10"`. Defensive against minor formatting drift.
- `CountResult` cleanly separates exact / noisy / suppressed into three
  mutually-exclusive shapes and preserves `raw` for the caller. The
  `obfuscated` property has a useful, unambiguous definition.
- `_parse_count_string` raises `PicSureQueryError` loudly on unknown shapes
  rather than silently coercing.
- `build_query_body` correctly puts `resourceUUID` at the top level and all
  query fields under `query`, matching the Jackson deserialization of
  `QueryRequest` → `Query` in `PicSureV3Service.convertIncomingQuery`.
- Intentionally omits `authorizationFilters`: the `Query` record's getter
  returns `List.of()` when null (`Query.java:33-36`), so omission is safe by
  default (the server's `requireAuthorizationFilter` flag defaults to `false` —
  `QueryValidator.java:27`). The docstring is clear about the rationale.
- Query-type mapping (`count` → `COUNT`, `participant` → `DATAFRAME`,
  `timestamp` → `DATAFRAME_TIMESERIES`, `cross_count` → `CROSS_COUNT`) — every
  string matches a valid enum constant in `ResultType.java`.
- `_resolve_query_type` lowers/strips input, produces a clear error listing
  the valid types.
- Concept-path keys in CROSS_COUNT responses are passed through verbatim
  (`str(path)` is a no-op for JSON string keys); no normalization that would
  drop backslashes or escape sequences.
- Empty CSV → empty DataFrame (`_parse_dataframe` lines 190-194), not an error
  — sensible for queries that return zero rows.

## Issues

### Critical

- **4xx responses bypass transport mapping and produce misleading errors** —
  `src/picsure/_services/query_run.py:63-68, 168-187, 190-194` — Transport only
  maps 401/403 and ≥500 (`_transport/client.py:73-81`); a 400/404/422/429
  returns a non-empty response body straight to `post_raw`. For COUNT the body
  is parsed as a count string and the user sees `PicSureQueryError: Expected a
  count response... but got: '<first 200 bytes of HTML/JSON error>'` — the real
  HTTP status is never surfaced. For CROSS_COUNT, if the server emits a JSON
  error envelope (Spring's default `{"timestamp":..., "status":422,
  "error":..., "path":...}`) `_parse_cross_count` passes the `isinstance(data,
  dict)` guard and begins calling `_parse_count_string` on each field; the
  first non-numeric field raises `PicSureQueryError: Expected a count
  response... '2024-04-20T...'` — which is actively misleading (the user is
  told their count data is malformed when the server actually rejected the
  request). For DATAFRAME, `pd.read_csv` on an HTML/JSON body either returns a
  malformed frame or raises `pd.errors.ParserError` — uncaught, leaking a
  pandas exception through the `picsure` public surface. Fix must live in
  transport (map 4xx → a distinct error), but this file is the one that
  currently crashes or lies. Related: Wave 1 transport finding.

### Important

- **CROSS_COUNT values can legitimately be JSON integers, not only strings** —
  `src/picsure/_services/query_run.py:187` — When HPDS is queried directly
  (not through the aggregate obfuscating proxy), `CountV3Processor.runCrossCounts`
  returns `Map<String, Integer>`, which Jackson serializes with numeric values:
  `{"\\phs000001\\": 42}`. `_parse_cross_count` handles this by accident
  because `str(42) == "42"` matches `_COUNT_EXACT`, but the code and
  docstring both assert "each value is a count string," which is not always
  true on the wire. Either the comment should be updated or the parse should
  explicitly handle `int` values (and the associated test at
  `test_query_run.py:219-229` should include an integer-valued fixture from
  direct-HPDS).
- **`_parse_dataframe` does not wrap pandas parse errors** —
  `src/picsure/_services/query_run.py:190-194` — If the CSV is malformed
  (truncated transfer, HTML error page slipping past the status check, mixed
  line terminators in a field), `pd.read_csv` raises
  `pd.errors.ParserError`, `UnicodeDecodeError`, or `EmptyDataError`. These
  propagate as-is, violating the module's contract that malformed responses
  raise `PicSureQueryError`. A `try/except` around `pd.read_csv` similar to
  `_parse_cross_count`'s JSON handling would make the failure actionable.
- **DATAFRAME cells can contain tab-separated multi-values; adapter does not
  flag this** — `src/picsure/_services/query_run.py:190-194` — Per
  `CsvWriter.writeMultiValueEntity` and the export loop in
  `MultiValueQueryV3Processor.processColumn`, a patient with multiple
  observations for the same concept yields a single CSV cell containing all
  values joined by `\t`. `pd.read_csv` reads it as one string — the caller
  sees e.g. `"120\t130\t118"` instead of a list. The docstring promises "a
  DataFrame" with no caveat. At minimum a doc note belongs here so callers
  know to `.str.split("\t")` where relevant.
- **TRANSPORT retry on 5xx is non-idempotent on `/query/sync`** —
  `src/picsure/_services/query_run.py:64` — `post_raw` retries once on 502/503
  (per Wave 1's transport review). A transient 5xx during query execution can
  double-enqueue a heavy query on the server. This should be filed against
  transport but is listed here because `run_query` is the largest in-tree
  caller of `post_raw` and the one most visibly affected.
- **No test coverage for non-2xx non-(401/403/5xx) responses** —
  `tests/unit/test_query_run.py` — There is no test asserting adapter behavior
  on a 400/404/422/429. Adding one would both document current (poor)
  behavior and pin the fix for the Critical item above.
- **Noisy-count regex accepts negative-free counts only, but aggregate can
  emit `0 ±3`** — `src/picsure/_services/query_run.py:31` — The regex requires
  `^(\d+)` for the value. `AggregateDataSharingResourceRSV3.randomize` uses
  `Math.max(... , threshold)`, so the lowest value the wire can carry is
  `threshold` (e.g. `10 ±3`), not negative — so in practice this is fine.
  Confirming for completeness; no code change needed.

### Minor

- **Docstring example uses `'11309 ±3'` but message body uses `'11309 ±3'`
  (no narrow no-break space)** — `src/picsure/_services/query_run.py:158` —
  Consistent; just noting the character is `U+00B1` throughout.
- **`_phenotypic_clause` validation path** —
  `src/picsure/_services/query_run.py:113-117` — If a caller passes neither
  `Clause` nor `ClauseGroup`, the raised `PicSureValidationError` is raised
  *after* `_resolve_query_type` has already succeeded and `select_paths()` has
  been invoked — which would `AttributeError` first if `query` is e.g. a plain
  dict. Consider moving the type check to `build_query_body`'s entry point so
  the error message is produced before the `AttributeError`.
- **Typing** — `src/picsure/_services/query_run.py:40` — return annotation is
  `CountResult | dict[str, CountResult] | pd.DataFrame`, which is fine for
  users reading the signature but hard for callers relying on static
  narrowing. Consider `typing.overload` variants keyed on the literal
  `query_type`. Non-blocking.
- **`_parse_cross_count` coerces keys with `str(path)`** —
  `src/picsure/_services/query_run.py:187` — JSON object keys are always
  strings per the spec; the `str()` is defensive but slightly misleads the
  reader into thinking keys might be non-strings.
- **Duplicate `_COUNT_*` constants could be pulled into `_models/count_result.py`
  alongside a `CountResult.from_server(str)` classmethod** — keeps the wire
  contract colocated with the dataclass. Non-blocking stylistic.

## Verification evidence

- **Wire format of COUNT**:
  `PicSureV3Service.java:446-447` →
  `queryOkResponse(String.valueOf(countProcessor.runCounts(incomingQuery)), incomingQuery, MediaType.TEXT_PLAIN)`.
  Raw HPDS emits a bare decimal integer. Confirmed.
- **Wire format of CROSS_COUNT (HPDS direct)**:
  `PicSureV3Service.java:422-423` →
  `queryOkResponse(countProcessor.runCrossCounts(incomingQuery), incomingQuery, MediaType.APPLICATION_JSON)`.
  `CountV3Processor.java:88` returns `Map<String, Integer>` → Jackson
  serializes as `{"\\path\\": 42}`. Confirmed.
- **Wire format of COUNT/CROSS_COUNT (through aggregate layer)**:
  `AggregateDataSharingResourceRSV3.java:725-727` (`randomize`) and `:746-756`
  (`aggregateCount`) produce `"<n> ±<v>"` and `"< <t>"`. Test fixtures at
  `.../test/resources/large_open_access_cross_count_obfuscated_result.json`
  show actual JSON with `"22 ±3"` / `"< 10"` values. Regex coverage matches.
- **Accepted `expectedResultType` strings**:
  `ResultType.java:6-68` lists `COUNT`, `CROSS_COUNT`, `DATAFRAME`,
  `DATAFRAME_TIMESERIES` among others. All four emitted by the adapter are
  present. Confirmed.
- **`authorizationFilters` omission safe**: `Query.java:32-36` — getter
  returns `List.of()` on null. `QueryValidator.java:37-40` only rejects empty
  list when `hpds.requireAuthorizationFilter=true`, which defaults `false`
  (`:27`). Confirmed.
- **DATAFRAME header**: `MultiValueQueryV3Processor.getHeaderRow` lines
  43-49 — `[patient_id, <concept_path>...]`.
- **DATAFRAME_TIMESERIES header**: `TimeseriesV3Processor.getHeaderRow` lines
  55-58 — `[PATIENT_NUM, CONCEPT_PATH, NVAL_NUM, TVAL_CHAR, TIMESTAMP]`.
- **Multi-value CSV cells tab-joined**: `CsvWriter.java:53-68`
  (`writeMultiValueEntity` uses `Joiner.on('\t')`).
- **Sync endpoint request body shape**: `PicSureV3Service._querySync`
  receives a `QueryRequest` with `query` (deserialized to
  `edu.harvard.hms.dbmi.avillach.hpds.data.query.v3.Query`) and
  `resourceUUID`. Adapter's body matches this 1:1.
- **4xx fall-through confirmed**: `_transport/client.py:73-81` only handles
  401/403 and ≥500; 200-299 returns response; 4xx (not 401/403) also returns
  response, so `post_raw` returns the error body bytes to the parsers.
