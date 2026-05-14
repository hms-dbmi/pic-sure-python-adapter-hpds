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
   authenticated `PicSureClient`, fetches the user profile, the
   resource list, optional consents, and the dictionary size — then
   returns a :class:`Session`.
2. **Search / build.** `session.searchDictionary(...)` and
   `session.facets(...)` go through the search service; users build
   filters with the standalone helpers `picsure.createSubQuery(...)`
   and `picsure.buildQuery(...)`.
3. **Run.** `session.runQuery(query, type=...)` calls the query-run
   service, which serializes the `Clause` / `ClauseGroup` to v3 wire
   format, POSTs to `/picsure/v3/query/sync`, and parses the response
   into a `CountResult`, a `dict[str, CountResult]`, or a
   `DataFrame`.
4. **Export.** `session.exportAsPFB(...)` uses the async flow
   (`/picsure/v3/query` → poll status → fetch result), streaming the
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
  │  build_query_body(query, resource_uuid, query_type)
  │      ├─ Clause.to_query_json()  /  ClauseGroup.to_query_json()
  │      └─ wraps in v3 envelope { query: { ... }, resourceUUID }
  │
  │  client.post_json(_PICSURE_QUERY_SYNC_PATH, body)
  ▼
picsure._transport.client.PicSureClient._request
  │  httpx.Client.request("POST", "/picsure/v3/query/sync", ...)
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
| `session.py`       | `Session` class. Holds the HTTP client, resource list, consents, dictionary size, and the dev-mode config. Public methods (`searchDictionary`, `runQuery`, `runQueryByID`, `exportAsPFB`, `exportCSV`, `exportTSV`, `setResourceID`, `setResourceIDByName`, `getResourceID`, `facets`, `showAllFacets`, …) delegate to `_services/*`. |
| `resource.py`      | `Resource` dataclass (`uuid`, `name`, `description`) with a `from_dict` constructor for `/picsure/info/resources` payloads. |
| `clause.py`        | `Clause` dataclass + `ClauseType` enum (`FILTER`, `ANYRECORD`, `SELECT`, `REQUIRE`). Each `Clause.to_query_json()` emits the v3 `PhenotypicClause` shape; `SELECT` raises and is extracted separately via `select_paths()`. |
| `clause_group.py`  | `ClauseGroup` dataclass + `GroupOperator` enum (`AND`, `OR`). Recursively serializes to a v3 `PhenotypicSubquery`. Refuses to embed `SELECT` children inline (symmetry with `Clause`). |
| `query.py`         | `Query` type alias: `Clause | ClauseGroup`. The single type that runs through the query path. |
| `query_type.py`    | `QueryType` enum (`COUNT`, `PARTICIPANT`, `TIMESTAMP`, `CROSS_COUNT`). Public API also accepts equivalent lowercase strings. |
| `count_result.py`  | `CountResult` dataclass — preserves `value`, `margin`, `cap`, `raw`. Encodes exact / noisy / suppressed shapes from open-access backends. `obfuscated` property is a convenience. |
| `dictionary.py`    | `DictionaryEntry` dataclass — one row of `searchDictionary` output, mapped from the backend `Concept` payload. |
| `facet.py`         | `Facet`, `FacetCategory`, and the public `FacetSet`. Iterative `from_dict` build so deep hierarchical facets don't blow Python's recursion limit. |

### `_services/` — operations

| Module           | What it owns                                                                 |
|------------------|------------------------------------------------------------------------------|
| `connect.py`     | `connect(platform, token, …)`. Resolves the platform, hits `/psama/user/me` (skipped on open-access), fetches resources, consents, dictionary size, and constructs the `Session`. Also handles the dev-mode toggle and the success/expiration banner. |
| `search.py`      | `searchDictionary`, `fetch_facets`, `show_all_facets`, plus the smaller helpers that build dictionary-api request bodies, dedupe entries, and turn results into DataFrames. Also `fetch_total_concepts` (used by connect to pre-size search pages). |
| `query_build.py` | `createSubQuery` and `buildQuery` — the public constructors for `Clause` and `ClauseGroup` with input validation (rejects mutually-exclusive arguments before they reach the wire). |
| `query_run.py`   | `run_query(client, resource_uuid, query, type)`. Serializes via `build_query_body`, posts to the v3 sync endpoint (or the legacy path on open-only deployments), and parses each response shape. Also `parse_count_string` for the obfuscated-count regexes. |
| `query_load.py`  | `load_query(client, query_id)`. Hits the saved-query endpoint and reconstructs a `Clause` / `ClauseGroup` from the response so it can be re-run via `runQueryByID`. |
| `export.py`      | `export_pfb` — the async PFB flow (submit → poll with exponential backoff capped at 60s, 10-minute total deadline → stream result to a `.part` file → atomic rename). Plus `export_csv` and `export_tsv` for in-memory DataFrames. |
| `consents.py`    | `fetch_consents(client)`. Reads `/psama/user/me/queryTemplate/`, parses the doubly-encoded JSON, and pulls the `\\_consents\\` study-consent list used by dictionary-api requests on authorized deployments. |

### `_transport/` — HTTP

| Module         | What it owns                                                                  |
|----------------|-------------------------------------------------------------------------------|
| `client.py`    | `PicSureClient`. Wraps `httpx.Client` with Bearer-token auth, the `request-source: Authorized|Open` gateway header, a 30s timeout, one retry on connection errors and 5xx for GETs (POSTs are not retried on 5xx because they are non-idempotent), and a streaming variant `post_raw_stream` for binary payloads. `_raise_for_status` translates 4xx into the `Transport*Error` set. |
| `errors.py`    | Internal `TransportError` hierarchy: `TransportAuthenticationError` (401/403), `TransportValidationError` (400/422/other 4xx), `TransportNotFoundError` (404), `TransportRateLimitError` (429, parses `Retry-After`), `TransportServerError` (5xx), `TransportConnectionError` (DNS / timeout / refused). |
| `platforms.py` | `Platform` enum (`BDC_AUTHORIZED`, `BDC_OPEN`, `BDC_DEV_*`, `BDC_PREDEV_*`, `NHANES_AUTHORIZED`, `NHANES_OPEN`) and `resolve_platform()`. A `Platform` member carries URL, default resource UUID, whether dictionary calls need consents, and whether the platform requires a token; `resolve_platform` also accepts a raw `http(s)://` URL for unlisted deployments. |

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
  [`src/picsure/__init__.py`](../../src/picsure/__init__.py) (the
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
| 404                       | `TransportNotFoundError`         | usually `PicSureQueryError` (resource/path missing) |
| 429                       | `TransportRateLimitError`        | `PicSureConnectionError` with a `retry_after` note  |
| 5xx (after one retry)     | `TransportServerError`           | `PicSureConnectionError`           |
| DNS / timeout / refused   | `TransportConnectionError`       | `PicSureConnectionError`           |

`_transport/client.py::_raise_for_status` is the single 4xx mapper
shared by `_request` and `post_raw_stream`, so both code paths agree.

## Session and Resource resolution

`Session` is the user-facing handle, but the data it carries is
small:

- `_client` — the authenticated `PicSureClient` (the only thing that
  knows the base URL and token).
- `_user_email`, `_token_expiration` — surfaced in the connect
  banner; `_user_email == "anonymous"` on open-access deployments.
- `_resources` — `list[Resource]` from `/picsure/info/resources`.
- `_resource_uuid` — the currently active resource. Defaulted from
  the `Platform` member at connect time, or required to be set
  manually for custom URLs.
- `_consents` — `list[str]` of study-consent identifiers. Empty on
  open-access; required in dictionary-api request bodies on
  authorized deployments.
- `_total_concepts` — captured at connect time and used as the page
  size for searches so results come back in one page.
- `_dev_config` — opt-in `DevConfig` (off by default).
- `_use_legacy_query_path` — set during connect when the platform is
  open-only and must use `/picsure/query/sync` (BDC's API gateway
  rejects open traffic on the v3 endpoint with HTTP 401).

Resources are resolved by UUID by default. Two name-based helpers
exist for ergonomics: `setResourceIDByName(name)` looks up by the
backend's `name` field on `Resource`. Platform "names" like
`BDC Authorized`, `BDC Open`, and `Demo` are user-facing labels;
internally `Platform` enum members and custom URLs are the only
inputs `resolve_platform` accepts. (Confirm with maintainers whether
string aliases like `"BDC Authorized"` are intended to resolve to a
`Platform` member — they appear in user-facing examples but
`resolve_platform` only matches `Platform` instances or full URLs.)
