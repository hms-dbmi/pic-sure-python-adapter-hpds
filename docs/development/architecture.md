# Architecture

This page is a map of the `picsure` package for contributors. It
covers the layering, what each module owns, and the conventions that
hold the public surface stable while leaving the internals free to
move.

## End-to-end overview

`picsure` is a thin Python client over the PIC-SURE HTTP API. A
typical session flows:

1. **Connect.** `picsure.connect(platform, token)` resolves a
   :class:`Platform` (or custom URL) to connection details, builds an
   authenticated `PicSureClient`, reads the display email and expiry
   from the token, and fetches the consent list on consent-gated
   deployments — then returns a :class:`Session`.
2. **Search / build.** `session.searchDictionary(...)` and
   `session.facets(...)` go through the search service; users build
   filters with the standalone helpers `picsure.buildClause(...)` and
   `picsure.buildClauseGroup(...)`, then optionally wrap a filter with
   the output concepts to return via `picsure.buildQuery(...)`.
3. **Run.** `session.runQuery(query, type=...)` calls the query-run
   service, which splits the `Query` (or bare `Clause` / `ClauseGroup`)
   into a phenotypic filter tree and the output `select` — the filter's own
   variables folded together with any `includeConcepts` — serializes to the
   query wire format, POSTs to `/picsure/hpds/auth/v3/query/sync` (or
   `/picsure/hpds/open/v3/query/sync` on open sessions), and parses the response
   into a `CountResult`, a `dict[str, CountResult]`, or a
   `DataFrame`. The gateway selects the HPDS backend by path (`auth` vs
   `open`), so no `resourceUUID` is sent in the body.
4. **Export.** `session.exportAsPFB(...)` uses the async flow
   (`/picsure/hpds/auth/v3/query` → poll status → fetch result), streaming the
   bytes to disk; `session.exportCSV` / `exportTSV` write a DataFrame
   in memory to disk.

## Tracing a query

```
user
  │  session.runQuery(query, type="count")
  ▼
picsure._models.session.Session.runQuery
  │  (decorated with @timed for dev-mode events)
  ▼
picsure._services.query_run.run_query
  │  build_query_body(query, query_type)
  │      ├─ Clause.to_query_json()  /  ClauseGroup.to_query_json()
  │      └─ wraps in envelope { query: { ... } }  (no resourceUUID)
  │
  │  client.post_raw(query_prefix(backend, v3=...) + "/query/sync", body)
  ▼
picsure._transport.client.PicSureClient._request
  │  httpx.Client.request("POST", "/picsure/hpds/auth/v3/query/sync", ...)
  │  4xx → _raise_for_status → TransportAuthenticationError /
  │        TransportValidationError / TransportNotFoundError /
  │        TransportRateLimitError
  │  5xx + connection errors → retried once, then TransportServerError /
  │        TransportConnectionError
  ▼
picsure._services.query_run.run_query (response handling)
  │  parse "COUNT" / "CROSS_COUNT" / "DATAFRAME" / "DATAFRAME_TIMESERIES"
  │  TransportError → PicSureAuthError / PicSureQueryError /
  │                   PicSureConnectionError / PicSureValidationError
  ▼
result returned to caller (CountResult | dict | DataFrame)
```

Every other entrypoint follows the same shape: a `Session` method
delegates to a `_services/*` function, which uses the transport
client and translates `TransportError` subclasses to the public
`PicSure*` hierarchy.

## Package layout

```
src/picsure/
├── __init__.py            # public API surface (re-exports)
├── errors.py              # public PicSureError hierarchy
├── py.typed               # PEP 561 marker
├── _models/               # data classes and enums
├── _services/             # one module per high-level operation
├── _transport/            # HTTP client, error mapping, platforms
└── _dev/                  # dev-mode instrumentation (opt-in)
```

### `_models/` — types

| Module             | What it owns                                                                 |
|--------------------|------------------------------------------------------------------------------|
| `session.py`       | `Session` class. Holds the HTTP client, the consent list, the HPDS backend selection, and the dev-mode config. Public methods (`searchDictionary`, `runQuery`, `runQueryByID`, `loadQueryByID`, `saveQueryByName`, `exportAsPFB`, `exportCSV`, `exportTSV`, `facets`, `showAllFacets`, …) delegate to `_services/*`. |
| `clause.py`        | `Clause` dataclass + `PhenotypicFilterType` enum (`FILTER`, `ANYRECORD`, `REQUIRE`). Each `Clause.to_query_json()` emits the v3 `PhenotypicClause` shape. Frozen with tuple fields (`keys`, `categories`), so a clause is hashable and usable as a dict key; the constructor accepts any iterable of strings and stores a tuple. |
| `clause_group.py`  | `ClauseGroup` dataclass + `GroupOperator` enum (`AND`, `OR`). Recursively serializes to a v3 `PhenotypicSubquery`. Frozen with a `tuple` of children, so a group — nested groups included — is hashable. |
| `query.py`         | `Query` dataclass: a `phenotypicFilter` (`Clause | ClauseGroup | None`), `includeConcepts` (output concept paths), and `genomicFilters` (a `tuple[GenomicFilter, ...]`, applied conjunctively alongside the phenotypic filter). `runQuery` also accepts a bare `Clause` / `ClauseGroup` (filter; its variables are returned as output columns). `concept_paths()` on each collects the filter's variables to fold into `select`. |
| `query_type.py`    | `QueryType` enum (`COUNT`, `PARTICIPANT`, `TIMESTAMP`, `CROSS_COUNT`, `VARIANT_COUNT`, `VARIANT_LIST`, `VCF_EXCERPT`, `AGGREGATE_VCF_EXCERPT`). Public API also accepts equivalent lowercase strings. |
| `count_result.py`  | `CountResult` dataclass — preserves `value`, `margin`, `cap`, `raw`. Encodes exact / noisy / suppressed shapes from open-access backends. `obfuscated` property is a convenience. |
| `dictionary.py`    | `DictionaryEntry` dataclass — one row of `searchDictionary` output, mapped from the backend `Concept` payload. |
| `facet.py`         | `Facet`, `FacetCategory`, and the public `FacetSet`. Iterative `from_dict` build so deep hierarchical facets don't blow Python's recursion limit. |
| `genomic_filter.py`| `GenomicFilter` dataclass plus the `GenomicFilterKey`, `VariantFrequency`, and `VariantSeverity` enums (all public). `VariantSeverity` buckets expand into `Variant_consequence_calculated` values; the backend's own `Variant_severity` impact values (`HIGH`, `MODERATE`, `LOW`, `MODIFIER`) pass through on that key unchanged. |

### `_services/` — operations

| Module           | What it owns                                                                 |
|------------------|------------------------------------------------------------------------------|
| `connect.py`     | `connect(platform, token, …)`. Resolves the platform, fetches consents on consent-gated deployments, and constructs the `Session` with its HPDS `backend` (`auth`/`open`). There is no resource-registry round trip — the gateway routes by path. Reads the token expiry from the JWT's `exp` claim, and with `validate=True` (the default) sends one `GET /psama/user/me` to prove the server accepts the token — the email that request returns wins over the JWT's own claim, because it names the account requests will actually run as. Also handles the dev-mode toggle and the success/expiration banner. |
| `search.py`      | `searchDictionary`, `fetch_facets`, `show_all_facets`, plus the smaller helpers that build dictionary request bodies, dedupe entries, and turn results into DataFrames. Dictionary searches page in bounded chunks of `_DEFAULT_PAGE_SIZE` (500): an unpaged call walks pages until the server says there are no more, refusing to accumulate past `_MAX_UNPAGED_ROWS` (100,000). `_SERVER_MAX_PAGE_SIZE` (Java `Integer.MAX_VALUE`) is only the validation ceiling on a caller-supplied `page_size` — it is never the size actually requested. |
| `query_build.py` | `buildClause`, `buildClauseGroup`, and `buildQuery` — the public constructors for `Clause`, `ClauseGroup`, and `Query` with input validation (rejects mutually-exclusive arguments before they reach the wire). |
| `query_edit.py`  | `removeSubQuery(query, target)` and `replaceClause(query, target, replacement)`. Pure local tree edits — no network calls. Matching is structural (frozen-dataclass equality). Removals that empty a `ClauseGroup` prune the parent; removing the whole tree raises `PicSureValidationError`, and so does a `target` that does not occur in the query — an edit never silently returns an unchanged copy. |
| `query_run.py`   | `run_query(client, query, type, *, backend)`. Serializes via `build_query_body`, posts to `/picsure/hpds/{backend}/v3/query/sync` — both backends use the v3 routes — and parses each response shape. Also `_parse_count_string` for the obfuscated-count regexes. HPDS route helpers live in `_hpds_paths.py`. |
| `query_load.py`  | `load_query(client, query_id, *, backend)`. Hits `/picsure/hpds/{backend}/v3/query/{id}/metadata` — the read itself does not touch HPDS, but only the `/v3` route is mapped on the current gateway — and reconstructs a `Query` (or the bare `Clause` / `ClauseGroup` it reduces to) so it can be re-run via `runQueryByID`. |
| `query_save.py`  | `save_query_by_name(client, query, name, *, backend, overwrite)`. Submits the query via `POST /picsure/hpds/auth/v3/query`, then `POST`s a new record to `/picsure/operations/dataset/named` (or `PUT`-updates an existing one at `/picsure/operations/dataset/named/{id}` when `overwrite=True`). No trailing slash: Spring 6 answers one with a 404. Validates `name` against the backend `NamedDataset` pattern client-side. Refused on open-access (`open` backend) deployments. |
| `_hpds_paths.py` | `query_prefix(backend, *, v3)` and `search_values_path(backend)` — the single place the `/picsure/hpds/{auth,open}[/v3]/…` route shape is built. The `/picsure` context prefix is part of the path the client sends: the gateway routes `/hpds/**` verbatim without stripping it. The registry-era `{resourceId}` path segment is gone from both. |
| `export.py`      | `export_pfb` — the async PFB flow (submit → poll with exponential backoff capped at 60s, 10-minute total deadline → stream result to a `.part` file → atomic rename). Plus `export_csv` and `export_tsv` for in-memory DataFrames, which translate a local write failure to `PicSureConnectionError` and a non-DataFrame argument to `PicSureValidationError` rather than leaking `OSError` / `AttributeError`. |
| `genomic_search.py` | `search_genomic_values(client, ...)` backing `Session.searchGenomicValues`. GETs `/picsure/hpds/{backend}/search/values` with the annotation key and a page/size, and returns a one-column DataFrame of values with the server's paging in `df.attrs`. A 200 with an empty body means the key is not a genomic annotation on this deployment. |
| `genomic_data.py`  | `genomicConsequences()` — reads the bundled `_data/variant_consequences.json` into a DataFrame of `severity` / `consequence` rows. No network call. |
| `consents.py`    | `fetch_consents(client)`. Reads `/psama/user/me/consents` and pulls the `\\_consents\\` study-consent list sent in `/picsure/dictionary/*` request bodies on authorized deployments. |

### `_transport/` — HTTP

| Module         | What it owns                                                                  |
|----------------|-------------------------------------------------------------------------------|
| `client.py`    | `PicSureClient`. Wraps `httpx.Client` with Bearer-token auth, the `request-source: Authorized|Open` gateway header, a ten-minute default request timeout (`DATA_TIMEOUT_SECONDS`, overridable via `connect(timeout=...)`) alongside the short `VALIDATION_TIMEOUT_SECONDS` the connect-time credential check uses, one retry on connection errors and 5xx for GETs (POSTs are not retried on 5xx because they are non-idempotent), and a streaming variant `post_raw_stream` for binary payloads, plus `put_json` for the `saveQueryByName` overwrite path. `_raise_for_status` translates 4xx into the `Transport*Error` set. |
| `errors.py`    | Internal `TransportError` hierarchy: `TransportAuthenticationError` (401/403), `TransportValidationError` (400/422/other 4xx), `TransportNotFoundError` (404), `TransportRateLimitError` (429, parses `Retry-After`), `TransportServerError` (5xx), `TransportConnectionError` (DNS / timeout / refused). |
| `platforms.py` | `Platform` enum (`BDC_AUTHORIZED`, `BDC_OPEN`, `BDC_DEV_*`, `BDC_PREDEV_*`, `NHANES_AUTHORIZED`, `NHANES_OPEN`) and `resolve_platform()`. A `Platform` member carries URL, display label, whether dictionary calls need consents, whether the platform requires a token, and whether it serves genomic data; `resolve_platform` also accepts a raw `http(s)://` URL for unlisted deployments. |

### `errors.py` (top level)

The public, user-facing error hierarchy. Everything user code might
want to catch is here:

```
PicSureError
├── PicSureAuthError         # bad/expired token, missing permissions
├── PicSureConnectionError   # cannot reach the server
├── PicSureQueryError        # server rejected the query
└── PicSureValidationError   # invalid input to a picsure function
```

`PicSureError` is the catch-all. Services translate
`TransportError` subclasses into these per-call (the mapping is not
1:1 — context matters; e.g. a 404 from `runQuery` becomes
`PicSureQueryError`, while a 404 from a dictionary lookup becomes
`PicSureValidationError`).

### `_dev/` — dev-mode internals

Off by default. Enable per-process with the `PICSURE_DEV_MODE`
environment variable (`1`/`true`/`yes`) or per-call with the
`dev_mode=True` keyword argument to `picsure.connect`. Modules:

| Module          | What it owns                                                                |
|-----------------|-----------------------------------------------------------------------------|
| `config.py`     | `DevConfig` — reads `PICSURE_DEV_MODE` and `PICSURE_DEV_MAX_EVENTS`, attaches a stderr handler to the `picsure` logger when on, and owns the `EventBuffer`. |
| `buffer.py`     | `EventBuffer` — thread-safe FIFO of `Event`s with a fixed cap (oldest drops on overflow). |
| `events.py`     | `Event` dataclass — one record per HTTP call, public method, connect, or error. Captures timestamp, kind, name, duration, and a small structured payload. |
| `timing.py`     | `@timed` decorator. Public `Session` methods wear this; emits an event on success and (tagged) on failure. |
| `redaction.py`  | Strips secrets before logging or buffering (PSAMA `token`, dataframe-shaped result bodies, etc.). |
| `reporting.py`  | Helpers that turn the buffered events into DataFrames for inspection. |

Dev-mode adds observability; it does not change behaviour. Production
users should leave it off.

`picsure.set_dev_mode(enabled)` is the public toggle — it is part of
`__all__` and lets a caller flip the mode on or off after `connect`
without restarting the process.

## Public vs. internal API

The rule is purely syntactic:

- **Public:** anything attached to the `picsure` package itself —
  i.e. anything re-exported from
  [`src/picsure/__init__.py`](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/src/picsure/__init__.py) (the
  `__all__` list). Treat these as load-bearing. Renaming, removing,
  or changing the signature of one of these is a breaking change and
  requires a major version bump under SemVer.
- **Internal:** every subpackage with a leading underscore
  (`_models/`, `_services/`, `_transport/`, `_dev/`). Imports across
  these are fine inside the library, but external users who reach
  past the underscore are on their own — internal modules can be
  renamed, split, merged, or rewritten in any release.

Adding a name to `__init__.py.__all__` is the act that makes
something public. Reviewers should flag any PR that grows that list
without a corresponding CHANGELOG entry.

## Error model

A call site's error contract is whatever subclass of `PicSureError`
it documents in its docstring (typically all four). The transport
layer never raises `PicSureError` directly — it raises the internal
`TransportError` subclasses, and each service translates those into
the user-facing type that makes sense in context.

The mapping for `_transport/errors.py`:

| HTTP status / event       | Transport exception              | Typical translation                |
|---------------------------|----------------------------------|------------------------------------|
| 401, 403                  | `TransportAuthenticationError`   | `PicSureAuthError`                 |
| 400, 422, other 4xx       | `TransportValidationError`       | `PicSureQueryError` or `PicSureValidationError` depending on whose input was wrong |
| 404                       | `TransportNotFoundError`         | usually `PicSureQueryError` (path missing) |
| 429                       | `TransportRateLimitError`        | `PicSureConnectionError` with a `retry_after` note  |
| 5xx (after one retry)     | `TransportServerError`           | `PicSureConnectionError`           |
| DNS / timeout / refused   | `TransportConnectionError`       | `PicSureConnectionError`           |

`_transport/client.py::_raise_for_status` is the single 4xx mapper
shared by `_request` and `post_raw_stream`, so both code paths agree.

## What a Session carries

`Session` is the user-facing handle, but the data it carries is
small:

- `_client` — the authenticated `PicSureClient` (the only thing that
  knows the base URL and token).
- `_user_email`, `_token_expiration` — surfaced in the connect
  banner and readable as the `Session.user_email` /
  `Session.token_expiration` properties; `"anonymous"` and `"N/A"`
  respectively on open-access deployments. Neither exposes the token.
- `_consents` — `list[str]` of study-consent identifiers, readable as
  the `Session.consents` property. Empty on open-access; required in
  `/picsure/dictionary/*` request bodies on authorized deployments.
- `_dev_config` — opt-in `DevConfig` (off by default).
- `_backend` — `"auth"` or `"open"`, set during connect. Selects the
  HPDS backend by URL path (`/picsure/hpds/auth` vs
  `/picsure/hpds/open`). Both
  backends use the v3 query routes; the path, not the token and not a
  resource UUID, decides which HPDS answers.

There is no resource-ID surface. The registry endpoint that used to
populate one was removed with the v3 rewrite, and routing is now
entirely path-based — see the changelog entry for the removal of
`connect(resource_uuid=…)` and the `Session` resource methods.

Platform labels like `BDC Authorized` and `BDC Open` are display-only
(printed on connect, returned by `Platform.label`); `resolve_platform` accepts **only** a
`Platform` enum member or a full `http(s)` URL. Passing a label string
raises `PicSureValidationError` whose message lists the valid
`Platform.<NAME>` access forms — so connect examples must use enum
members (`Platform.BDC_AUTHORIZED`) or a URL, never the label.
