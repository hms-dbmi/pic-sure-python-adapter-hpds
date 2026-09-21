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
   into a phenotypic filter tree and the output `select`, the filter's own
   variables folded together with any `includeConcepts`, and serializes to
   the query wire format. A count, cross-count or variant result POSTs to
   `/picsure/hpds/auth/v3/query/sync` (or `/picsure/hpds/open/v3/query/sync`
   on open sessions) and parses the response in place. A participant or
   timestamp result goes through the server's job flow instead
   (`/picsure/hpds/{backend}/v3/query` → poll `/status` → stream `/result`
   to a temporary file), because `/query/sync` refuses the DATAFRAME result
   types with HTTP 400. Either way the answer is parsed into a
   `CountResult`, a `dict[str, CountResult]`, or a `DataFrame`. The
   gateway selects the HPDS backend by path (`auth` vs `open`), so no
   `resourceUUID` is sent in the body.
4. **Export.** `session.exportAsPFB(...)` uses the same job flow
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
  │  (participant / timestamp results take run_async_query_to_file instead:
  │   client.post_json(".../query") submits, client.post_json(".../query/{id}/status")
  │   is polled until AVAILABLE, then client.post_raw_to_file(".../query/{id}/result")
  │   streams the CSV to a temporary file that pandas reads from disk)
  ▼
picsure._transport.client.PicSureClient._request
  │  httpx.Client.request("POST", "/picsure/hpds/auth/v3/query/sync", ...)
  │  4xx → _status_error → TransportAuthenticationError /
  │        TransportConsentDeniedError / TransportValidationError /
  │        TransportNotFoundError / TransportRateLimitError
  │  5xx → TransportServerError, never retried on a POST (only a GET is
  │        re-sent, since a POST the server already saw may have run)
  │  connection errors → retried once when the request provably never
  │        reached the server, otherwise on a GET only, then
  │        TransportConnectionError
  ▼
picsure._services.query_run.run_query (response handling)
  │  parse "COUNT" / "CROSS_COUNT" / "DATAFRAME" / "DATAFRAME_TIMESERIES" /
  │        "VARIANT_COUNT_FOR_QUERY" / "VARIANT_LIST_FOR_QUERY" /
  │        "VCF_EXCERPT" / "AGGREGATE_VCF_EXCERPT"
  │  TransportError → PicSureAuthError / PicSureQueryError /
  │                   PicSureConnectionError / PicSureValidationError
  ▼
result returned to caller (CountResult | dict | DataFrame | list[str])
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
| `clause_group.py`  | `ClauseGroup` dataclass + `GroupOperator` enum (`AND`, `OR`). Recursively serializes to a v3 `PhenotypicSubquery`. Frozen with a `tuple` of children, so a group is hashable, nested groups included. |
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
| `search.py`      | `searchDictionary`, `fetch_facets`, `show_all_facets`, plus the smaller helpers that build dictionary request bodies, dedupe entries, and turn results into DataFrames. Dictionary searches page in bounded chunks of `_DEFAULT_PAGE_SIZE` (500). An unpaged call walks pages until the server says there are no more and never returns more than `_MAX_UNPAGED_ROWS` (100,000) rows: it raises when the server reports a larger match count and truncates the final page when the server reports none. `Session.searchDictionary` forwards `page` and `page_size`. `_SERVER_MAX_PAGE_SIZE` (Java `Integer.MAX_VALUE`) is only the validation ceiling on a caller-supplied `page_size`. It is never the size actually requested. |
| `query_build.py` | `buildClause`, `buildClauseGroup`, and `buildQuery` — the public constructors for `Clause`, `ClauseGroup`, and `Query` with input validation (rejects mutually-exclusive arguments before they reach the wire). |
| `query_edit.py`  | `removeSubQuery(query, target)` and `replaceClause(query, target, replacement)`. Pure local tree edits, no network calls. Matching is structural (frozen-dataclass equality). Removals that empty a `ClauseGroup` prune the parent; removing the whole tree raises `PicSureValidationError`, and so does a `target` that does not occur in the query, so an edit never silently returns an unchanged copy. |
| `query_run.py`   | `run_query(client, query, type, *, backend)`. Serializes via `build_query_body`, then posts a count, cross-count or variant query to `/picsure/hpds/{backend}/v3/query/sync`, the v3 route both backends share, and parses each response shape. Participant and timestamp results are refused by `/query/sync`, so they take `run_async_query_to_file(client, backend, body, target, *, operation)`, the job flow this module also lends to `export.py`: submit to `/picsure/hpds/{backend}/v3/query`, poll `/query/{id}/status` (the first poll straight after the submit, then after sleeps of 1s, 2s, 4s, 8s and 10s from there on) until `AVAILABLE`, then stream `/query/{id}/result` into a temporary file with `post_raw_to_file` and parse it from disk, so peak memory is the DataFrame alone. A poll that is throttled, answered with a 5xx or lost to a network failure is sent again after the same sleep (a 429 waits its `Retry-After` when that is longer); a 401, 403, 404, a validation error or a rejected certificate on a poll raises at once, as does any failure on the submit or the download. The submit and the polls together, failed polls included, are bounded by `PicSureClient.timeout`, the value `connect(timeout=...)` sets, measured from just before the submit and read after each poll answers, with the last sleep clamped so the final poll is sent at the budget rather than after it; passing it raises `PicSureConnectionError`, naming the last poll's failure when it failed, and a terminal `ERROR` status raises `PicSureQueryError`. A local disk failure while staging the file is raised as `PicSureConnectionError`. Also `_parse_count_string` for the obfuscated-count regexes. HPDS route helpers live in `_hpds_paths.py`. |
| `query_load.py`  | `load_query(client, query_id, *, backend)`. Hits `/picsure/hpds/{backend}/v3/query/{id}/metadata`. The read itself does not touch HPDS, but only the `/v3` route is mapped on the current gateway. Reconstructs a `Query` (or the bare `Clause` / `ClauseGroup` it reduces to) so it can be re-run via `runQueryByID`. |
| `query_save.py`  | `save_query_by_name(client, query, name, *, backend, overwrite)`. Submits the query via `POST /picsure/hpds/auth/v3/query`, then `POST`s a new record to `/picsure/operations/dataset/named` (or `PUT`-updates an existing one at `/picsure/operations/dataset/named/{id}` when `overwrite=True`). No trailing slash: Spring 6 answers one with a 404. Validates `name` against the backend `NamedDataset` pattern client-side. Refused on open-access (`open` backend) deployments. |
| `_hpds_paths.py` | `query_prefix(backend, *, v3)`, `search_values_path(backend)`, the query-lifecycle builders (`query_submit_path`, `query_status_path`, `query_result_path`, `query_metadata_path`) and `named_dataset_item_path(id)`, the single place a route shape is built and the single place a value is percent-escaped into a path segment. `query_id_from_submit_response` and `canonical_server_id` check that an identifier the server chose is a UUID and return it in canonical form, unescaped, because the same id is also a request-body value and a public return value; the path builders escape it once on the way into a path, so a response cannot re-point an authenticated request at another route. `check_backend` refuses anything outside `BACKENDS` before `backend` is interpolated, and `Session` calls it rather than repeating the check, so both share one message and one error class. The `/picsure` context prefix is part of the path the client sends: the gateway routes `/hpds/**` verbatim without stripping it. The registry-era `{resourceId}` path segment is gone from both. |
| `export.py`      | `export_pfb` runs the PFB export through `query_run.run_async_query_to_file` (submit → poll with exponential backoff capped at 10s → stream result to a `.part` file → atomic rename), keeping only its own `DATAFRAME_PFB` body and the translation of a local write failure to `PicSureConnectionError` naming the destination. The submit and the polls together are bounded by `PicSureClient.timeout`, with transient poll failures retried inside it; the final poll and the download each carry the same value as their own per-request deadline, so the call as a whole can still run past it. Plus `export_csv` and `export_tsv` for in-memory DataFrames, which translate a local write failure to `PicSureConnectionError` and a non-DataFrame argument to `PicSureValidationError` rather than leaking `OSError` / `AttributeError`. |
| `genomic_search.py` | `search_genomic_values(client, ...)` backing `Session.searchGenomicValues`. GETs `/picsure/hpds/{backend}/search/values` with the annotation key and a page/size, and returns a one-column DataFrame of values with the server's paging in `df.attrs`. A 200 with an empty body means the key is not a genomic annotation on this deployment; any other bodiless status names itself instead, since an expired gateway session redirects with no body and the annotation key is not what failed. |
| `genomic_data.py`  | `genomicConsequences()` reads the bundled `_data/variant_consequences.json` into a DataFrame of `severity` / `consequence` rows. No network call. |
| `consents.py`    | `fetch_consents(client)`. Reads `/psama/user/me/consents` and pulls the `\\_consents\\` study-consent list sent in `/picsure/dictionary/*` request bodies on authorized deployments. |

### `_transport/` — HTTP

| Module         | What it owns                                                                  |
|----------------|-------------------------------------------------------------------------------|
| `client.py`    | `PicSureClient`. Wraps `httpx.Client` with Bearer-token auth, the `request-source: Authorized|Open` gateway header, a ten-minute default request timeout (`DATA_TIMEOUT_SECONDS`, overridable via `connect(timeout=...)`) alongside the short `VALIDATION_TIMEOUT_SECONDS` the connect-time credential check uses, one retry on connection errors and 5xx for GETs (POSTs are not retried on 5xx because they are non-idempotent), and a streaming variant `post_raw_stream` for binary payloads, `post_raw_to_file` to stream a response into a `.part` staging file promoted by `os.replace`, plus `put_json` for the `saveQueryByName` overwrite path. `_status_error` maps any 4xx or 5xx into the `Transport*Error` set; `_raise_for_status` is the buffered path's thin wrapper that raises what it returns. |
| `errors.py`    | Internal `TransportError` hierarchy: `TransportAuthenticationError` (401/403), `TransportValidationError` (400/422/other 4xx), `TransportNotFoundError` (404), `TransportRateLimitError` (429, parses `Retry-After`), `TransportServerError` (5xx), `TransportConnectionError` (DNS / timeout / refused), `TransportTLSError` (a certificate this machine will not trust, raised before the request is sent), and the structured pair `TransportConsentDeniedError` / `TransportConsentLookupError`, built from a response body carrying `errorType: consent_denied` or `consent_lookup_failed`. Also the credential redaction every class here applies to a response body before storing it or quoting it into a message, so a token the server echoed cannot reach a traceback through the cause chain. |
| `platforms.py` | `Platform` enum (`BDC_AUTHORIZED`, `BDC_OPEN`, `BDC_DEV_*`, `BDC_PREDEV_*`, `NHANES_AUTHORIZED`, `NHANES_OPEN`) and `resolve_platform()`. A `Platform` member carries URL, display label, whether dictionary calls need consents, whether the platform requires a token, and whether it serves genomic data; `resolve_platform` also accepts a raw `http(s)://` URL for unlisted deployments. |

### `errors.py` (top level)

The public, user-facing error hierarchy. Everything user code might
want to catch is here:

```
PicSureError
├── PicSureAuthError                    # the server answered and refused you
│   ├── PicSureAuthenticationError      # 401: the token itself is the problem
│   └── PicSureAuthorizationError       # 403: this account may not do it
│       └── PicSureConsentDeniedError   # 403 consent_denied: approvals do not cover it
├── PicSureConnectionError              # no usable response came back
│   ├── PicSureTLSError                 # the certificate was not trusted
│   └── PicSureServerError              # 5xx: the request arrived and failed
│       └── PicSureConsentLookupError   # 502 consent_lookup_failed
├── PicSureQueryError                   # server rejected the query
│   └── EmptyBodyError                  # any status under 400, zero-length body
└── PicSureValidationError              # invalid input to a picsure function
```

Every status below 400 reaches `EmptyBodyError`, not only a 200: the
client translates 4xx and 5xx and does not follow redirects, so a `302`
to an SSO login on an expired gateway session arrives as a bodiless
response too. `EmptyBodyError.status_code` is what tells the two apart,
and `_services/_errors.bodiless_response_succeeded` is where both
consumers ask.

`EmptyBodyError` is the one class here that `__init__.py.__all__` does
not export. It is raised by `_transport/client.py::_decode_json` and
caught by `_services/query_save.py` and `_services/genomic_search.py`,
so it is internal control flow that a caller sees only as the
`PicSureQueryError` it inherits from. Whether it becomes supported
public surface is an open question; until it is answered, catch
`PicSureQueryError`.

`PicSureError` is the catch-all, and the nesting is the contract: a
caller who wants every refusal catches `PicSureAuthError`, and one who
only cares about a denied consent catches `PicSureConsentDeniedError`.
Services do not each invent a mapping. They route every transport
failure through `_services/_errors.translate_transport_error`, so one
status produces one public type and one message everywhere. The table
under "Error model" below is that function.

### `_dev/` — dev-mode internals

Off by default. Enable per-process with the `PICSURE_DEV_MODE`
environment variable (`1`/`true`/`yes`) or per-call with the
`dev_mode=True` keyword argument to `picsure.connect`. Modules:

| Module          | What it owns                                                                |
|-----------------|-----------------------------------------------------------------------------|
| `config.py`     | `DevConfig`. Reads `PICSURE_DEV_MODE` and `PICSURE_DEV_MAX_EVENTS`, and owns the `EventBuffer`. It attaches no log handler: `_services/connect.py::_install_default_handler` is what puts the stderr handler on the `picsure` logger, and only when `connect()` finds dev mode on. |
| `buffer.py`     | `EventBuffer` — thread-safe FIFO of `Event`s with a fixed cap (oldest drops on overflow). |
| `events.py`     | `Event` dataclass — one record per HTTP call, public method, connect, or error. Captures timestamp, kind, name, duration, and a small structured payload. |
| `timing.py`     | `@timed` decorator. Public `Session` methods wear this; emits an event on success and (tagged) on failure. |
| `redaction.py`  | `body_is_sensitive` classifies a request body as participant-bearing (`DATAFRAME`, `DATAFRAME_TIMESERIES`, `DATAFRAME_PFB`, `VCF_EXCERPT`) so the `http` event for that call carries a `redacted: "participant"` label. Attaching the label is its whole effect: no request or response body is ever serialized into an event, so nothing here scrubs a secret out of anything. |
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
it documents in its docstring. An HTTP answer the adapter did not want
becomes an internal `TransportError` first, and
`_services/_errors.translate_transport_error` turns that into the
public type. Two paths skip the transport hierarchy and raise a
`PicSureError` from inside `_transport/` directly: `_decode_json` and
`json_object` raise `PicSureQueryError` (or its `EmptyBodyError`
subclass) for a body that is empty, not JSON, or not the shape the
route promised, and the CA-bundle resolution raises
`PicSureValidationError` for a `verify` path that does not exist and
`PicSureTLSError` for one OpenSSL cannot load. Everything else reaches
the user through the translator.

The mapping, which is one function and therefore the same for every
service:

| HTTP status / event                     | Transport exception             | Public exception             |
|-----------------------------------------|---------------------------------|------------------------------|
| 403 with `errorType: consent_denied`    | `TransportConsentDeniedError`   | `PicSureConsentDeniedError`  |
| 502 with `errorType: consent_lookup_failed` | `TransportConsentLookupError` | `PicSureConsentLookupError` |
| 401                                     | `TransportAuthenticationError`  | `PicSureAuthenticationError` |
| 403                                     | `TransportAuthenticationError`  | `PicSureAuthorizationError`  |
| 400, 422, other 4xx                     | `TransportValidationError`      | `PicSureValidationError`     |
| 404                                     | `TransportNotFoundError`        | `PicSureQueryError`          |
| 429                                     | `TransportRateLimitError`       | `PicSureConnectionError` carrying the `Retry-After` value |
| rejected certificate                    | `TransportTLSError`             | `PicSureTLSError`            |
| 5xx (after one retry)                   | `TransportServerError`          | `PicSureServerError`         |
| DNS / timeout / refused                 | `TransportConnectionError`      | `PicSureConnectionError`     |

The status is the whole input, so a 404 reads the same from `runQuery`
and from a dictionary lookup. A service that wants different wording
for a case of its own catches that transport class before the
translator sees it, as `genomic_search.py` does for the 404 and the
empty body, rather than mapping the status a second way.

`_transport/client.py::_status_error` is the single status mapper,
shared by `_request` and `post_raw_stream`, so both code paths agree
on the class, the message and the `Retry-After` value a status
produces. `_raise_for_status` raises what it returns, for the
buffered path's 4xx block. `_request` still handles 5xx itself,
because only it re-sends a 5xx on a GET.

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
