# Connection & Transport — Code Review

## Scope

Commit: 5a58091670e458fda33d3b9fbe3f1b37ef52a04c.

Files read (Python adapter, review-only, no modifications):
- `src/picsure/_services/connect.py`
- `src/picsure/_services/consents.py`
- `src/picsure/_transport/client.py`
- `src/picsure/_transport/platforms.py`
- `src/picsure/_transport/errors.py`
- `src/picsure/errors.py`
- `src/picsure/_models/session.py` (touched to assess public surface)

Contracts consulted (sibling repos):
- `/Users/george/code_workspaces/bdc/pic-sure/pic-sure-api-war/src/main/java/edu/harvard/dbmi/avillach/security/JWTFilter.java`
- `/Users/george/code_workspaces/bdc/pic-sure/pic-sure-api-war/src/main/java/edu/harvard/dbmi/avillach/service/PicsureQueryV3Service.java`
- `/Users/george/code_workspaces/bdc/pic-sure/pic-sure-api-war/src/main/java/edu/harvard/dbmi/avillach/service/PicsureInfoService.java`
- `/Users/george/code_workspaces/bdc/pic-sure/pic-sure-util/src/main/java/edu/harvard/dbmi/avillach/util/Utilities.java` (getRequestSourceFromHeader)
- `/Users/george/code_workspaces/bdc/pic-sure/pic-sure-resources/pic-sure-resource-api/src/main/java/edu/harvard/dbmi/avillach/service/ResourceWebClient.java` (querySync forwarding)
- `/Users/george/code_workspaces/bdc/pic-sure/pic-sure-resources/pic-sure-resource-api/src/main/java/edu/harvard/dbmi/avillach/service/ProxyWebClient.java` (the `/picsure/proxy/{container}` path used for dictionary-api)
- `/Users/george/code_workspaces/bdc/pic-sure/pic-sure-resources/pic-sure-visualization-resource/src/main/java/edu/harvard/hms/dbmi/avillach/resource/visualization/model/domain/AccessType.java`

Module responsibilities (one line each):
- `_services/connect.py` — orchestrates connect: resolve platform, build client, fetch profile/resources/consents/total-concepts, and return a populated `Session`.
- `_services/consents.py` — fetches the PSAMA queryTemplate, extracts the `\_consents\` list from the embedded JSON.
- `_transport/client.py` — thin httpx wrapper adding Bearer auth, `request-source`, retry-on-5xx, and mapping transport exceptions.
- `_transport/platforms.py` — enum + URL resolver for known BDC/NHANES/AIM-AHEAD deployments, with policy flags (`include_consents`, `requires_auth`).
- `_transport/errors.py` — internal transport exception hierarchy (auth / server / connection).
- `errors.py` — public `PicSureError` hierarchy surfaced to users.

Outbound HTTP call inventory (headers attached by `PicSureClient`):
- All requests carry `Content-Type: application/json`, `request-source: Authorized|Open`, and `Authorization: Bearer <token>` only when `token.strip()` is non-empty.
- No `Accept` header; no `User-Agent` override; no `X-Request-Id`; no `X-Session-Id`.
- Auth classification is correct: whitespace-only token → empty after `.strip()` → anonymous mode with `request-source: Open` and no Authorization header (client.py:25-31).
- Error mapping: `ConnectError` → `TransportConnectionError`; `TimeoutException` → `TransportConnectionError`; HTTP 401/403 → `TransportAuthenticationError`; HTTP ≥500 → `TransportServerError` after a single retry. **Any other 4xx (400, 404, 409, 422, 429) is returned verbatim**, i.e. not mapped to a transport exception — downstream `.json()` calls will then raise a generic `JSONDecodeError`.

## Strengths

- The `request-source` header is correctly derived from token presence and matches the BDC contract. The comment in `client.py:21-24` accurately explains the BDC gateway routing behavior; the values (`Authorized` / `Open`) match `AccessType.java`'s enum and `ResourceWebClient.querySync`'s forwarded header.
- `PlatformConfig` is frozen-dataclass-in-enum. The separation between `Platform.include_consents`/`requires_auth` policy flags and `PlatformInfo` resolution overrides is clean, and the override semantics (custom URLs default to `requires_auth=True`, known platforms default to their own flag) are documented.
- `_fetch_profile` and `_fetch_resources` translate every internal transport exception into a `PicSureAuthError` or `PicSureConnectionError` with an actionable message that names the platform and URL. The degraded-to-empty-list behavior in `_fetch_resources` when an open-access deployment gates `/info/resources` is a nice pragmatic concession.
- `fetch_consents` correctly handles the "JSON-in-a-JSON-string" wire format, short-circuits on a missing template/filters, and raises `PicSureConnectionError` on malformed JSON with a message that suggests contacting the admin.
- `TransportAuthenticationError` and `TransportServerError` truncate the body to 200 chars — sensible guard against spilling large HTML error pages into stack traces.
- `connect()`'s resource-selection UX (printing available resources when the caller didn't pass `resource_uuid` and no Platform default applies) is genuinely helpful.

## Issues

### Critical

- **AIM-AHEAD platform enum ships with a placeholder UUID** — `src/picsure/_transport/platforms.py:103` — `resource_uuid="REPLACE-ME-aim-ahead-resource-uuid"` is hard-coded into a public enum member. Any user doing `picsure.connect(Platform.AIM_AHEAD, token=...)` will be handed a `Session` with `resource_uuid` set to that string; the first query that flows to `/picsure/v3/query/sync` will fail (the API war validates `queryRequest.getResourceUUID()` and looks it up in `resourceRepo` — see `PicsureQueryV3Service.java:456-463`). Either remove the enum member until a real UUID is available, raise on construction, or document the caller must pass `resource_uuid=` explicitly.

### Important

- **Non-401/403 4xx responses are silently returned, not mapped** — `src/picsure/_transport/client.py:73-81` — Only 401/403 and ≥500 are branched. A 400 (malformed query), 404 (wrong path after a platform upgrade), 422, or 429 (rate limit) falls through; callers then invoke `.json()` on a response whose body is typically `application/problem+json` or a plain-text stack trace, and surface a `json.JSONDecodeError`. The user sees a useless traceback instead of a `PicSureQueryError`/`PicSureConnectionError`. `429` in particular deserves its own path because the BDC gateway can throttle, and Retry-After is never honored.
- **POST requests retry on 5xx, which can double-execute non-idempotent calls** — `src/picsure/_transport/client.py:59-79` — `_MAX_RETRIES = 1` applies uniformly in `_request`, called by both `get_json` and `post_json`/`post_raw`. A transient 502 during `POST /picsure/v3/query/sync` will retry, and the API war persists a `Query` entity and starts downstream HPDS work before it knows whether the first attempt actually failed on the server side (see `PicsureQueryV3Service.querySync` at lines 259-285 — the entity is persisted before `resourceWebClient.querySync` returns). Restrict retries to GET (and to `ConnectError`/timeouts for all methods), or at minimum document the hazard. Same concern for `post_raw` (PFB exports).
- **`Session` does not expose a public close / context-manager** — `src/picsure/_models/session.py:18` and `src/picsure/_transport/client.py:85` — `PicSureClient.close()` exists, but `Session` has no `close()`, `__enter__`, or `__exit__`. Long-running notebook kernels leak the httpx `Client` (and its connection pool) on every `picsure.connect()`. Add `Session.close()` and `__enter__`/`__exit__` that delegate to `self._client.close()`.
- **`connect()` calls `_fetch_profile` even when a whitespace-only token strips to empty** — `src/picsure/_services/connect.py:79-82`, `src/picsure/_transport/client.py:25` — If a caller passes `token="   "` (or forgets to strip a copy-pasted token) and the platform has `requires_auth=True`, the transport silently downgrades to anonymous (no Authorization header, `request-source: Open`), then the PSAMA `/psama/user/me` call fails with a 401 and we report "Your token is invalid or expired." The root cause — "you forgot the token" — is hidden. Detect the empty-after-strip case in `connect()` and raise a `PicSureValidationError` like "Platform X requires a token but none was provided."
- **Dictionary-api `request-source` is never seen by the downstream service** — `src/picsure/_transport/client.py:21-29` plus `ProxyWebClient.java:106-117` — The comment in `client.py` implies `request-source` matters for all authorized endpoints, but `ProxyWebClient` (which serves `/picsure/proxy/dictionary-api/*`) only forwards `authorization, x-api-key, x-request-id` by default. The `request-source` header is consumed/logged by the API war but not forwarded to dictionary-api. This isn't wrong-on-the-wire (the gateway still logs correctly and audits the call), but the comment overstates the contract. Tighten the comment to "BDC's API gateway and HPDS route auth based on a `request-source` header", and note that dictionary-api sees only the Authorization header.
- **`PicSureClient.get_json` / `post_json` type-annotated `-> dict` but `/picsure/proxy/dictionary-api/facets` returns a JSON array** — `src/picsure/_transport/client.py:38-46` — `search.py:145` has a comment acknowledging the body is actually a list, yet `post_json` declares `dict`. When mypy runs on downstream code, the return type will mislead readers. Either parametrize as `object` / `Any` / `dict | list` or split the helper. Minor type-correctness hazard; becomes important when a consumer indexes by `data["…"]` and gets a `TypeError` they can't predict from the signature.
- **`PlatformConfig.url` for NHANES has a trailing slash; custom URLs get `rstrip("/")`** — `src/picsure/_transport/platforms.py:88,95,174` — `NHANES_AUTHORIZED.url = "https://nhanes.hms.harvard.edu/"` but custom URLs are stripped. httpx tolerates this with base_url+leading-slash paths, but the inconsistency will surface if anyone ever string-builds off `info.url`. Normalize in `Platform.url` (or in `PlatformInfo.__post_init__`).
- **No test coverage assertion possible from this review, but** the whitespace-stripping, 5xx retry, and 401/403 mapping have no visible tests in scope. Recommend unit coverage of `_request` across at least {200, 401, 500, 429, ConnectError, Timeout} and a `post_raw` path that verifies retry semantics.

### Minor

- **`TransportAuthenticationError.body` truncates to 200 chars in `__str__` but exposes full body via `.body`** — `src/picsure/_transport/errors.py:11` — Fine, just noting the split.
- **`connect.py:90` calls `fetch_total_concepts(client, consents=consents)` unconditionally** — Even on open-access connections where the dictionary-api call is free, this is one extra round-trip on connect. Cached on `Session.total_concepts` and used for search paging; acceptable, but a `fetch_total_concepts` failure would propagate through `connect()` and users get a confusing error — out of scope for this review but adjacent.
- **`TransportConnectionError` has no `status_code` / no structured payload** — `src/picsure/_transport/errors.py:23` — That's consistent with "no wire state to capture," but it means consumers can't distinguish DNS failure from TLS handshake failure from read timeout programmatically. Low priority.
- **`PicSureError` class hierarchy lacks `__init_subclass__` or tagging** — `src/picsure/errors.py` — Callers that catch `PicSureError` can't tell retry vs fatal without `isinstance` chains. OK for now.
- **The PSAMA profile path has no trailing slash; `queryTemplate` does** — `src/picsure/_services/connect.py:17` (`/psama/user/me`) vs `src/picsure/_services/consents.py:9` (`/psama/user/me/queryTemplate/`). Both work server-side, but consistency helps readers spot typos.
- **`connect.py:78` computes `display_name = platform.label if isinstance(platform, Platform) else platform`** — When `platform` is a URL string, `display_name` is the URL itself, which then appears in the success print. That's probably intentional but looks odd ("connected to https://my-host.example.com/ as user …"). Consider deriving a short label.
- **`PicSureClient.__init__` sets `base_url=base_url` without rstrip** — `src/picsure/_transport/client.py:33` — See platforms.py trailing-slash note above.
- **Enum naming inconsistency**: `Platform.NHANES_AUTHORIZED.label = "Nhanes Authorized"` vs `Platform.BDC_AUTHORIZED.label = "BDC Authorized"` — "Nhanes" should be "NHANES" to match the acronym convention.

## Verification evidence

- Header-matrix verified by reading `PicSureClient.__init__` (client.py:20-36) end-to-end and cross-referencing with:
  - `Utilities.getRequestSourceFromHeader(HttpHeaders headers)` in `pic-sure-util/src/main/java/.../Utilities.java:39-41` — confirms the API war reads the literal string `"request-source"`.
  - `ResourceWebClient.querySync(..., String requestSource)` at `pic-sure-resources/pic-sure-resource-api/.../ResourceWebClient.java:348-356` — confirms HPDS receives `request-source` forwarded verbatim.
  - `AccessType.java:5-7` — confirms the `Open` / `Authorized` values are the canonical tokens the downstream visualization and HPDS services compare against.
  - `ProxyWebClient.forwardHeaders` at `.../ProxyWebClient.java:106-129` — shows dictionary-api (`/picsure/proxy/{container}`) only forwards `authorization, x-api-key, x-request-id` by default.
- Auth-mode verification: ran mental traces of `PicSureClient(base_url=..., token="")`, `token="   "`, `token="abc"`, `token="\tabc\n"`. After `.strip()`, only the first two produce `request-source: Open` and no `Authorization` — this matches the documented rule. See client.py:25-31.
- Error-mapping verification: walked `_request` on responses `{200, 401, 403, 429, 500, 502}` and on `httpx.ConnectError`, `httpx.ReadTimeout`. 400/404/429 confirmed to slip through at client.py:73-81.
- JWTFilter contract: read `JWTFilter.java:102-190` in full. The filter's auth decision uses `HttpHeaders.AUTHORIZATION` (the Java constant for `"Authorization"`). It does not examine `request-source` — that header's role begins downstream of the filter. The Python client therefore satisfies the filter by sending `Authorization: Bearer <token>` for authorized calls. In open-access mode, the filter allows blank/short Authorization headers and consults `callOpenAccessValidationEndpoint`, so the Python client's "no Authorization header when token is empty" is correctly accepted by the filter. No required header the Python client omits, and no rejected header the Python client sends (headers are case-insensitive in HTTP; `request-source` vs `Request-Source` doesn't matter to Java `HttpHeaders`).
- Session-close verification: grep `__enter__|__exit__|def close|__del__` across `src/picsure/**` returns only `PicSureClient.close` at client.py:85 — no leak guard elsewhere.
- Platform resolution verification: read `Platform` enum + `resolve_platform` flow. Placeholder UUID at platforms.py:103 is a string literal, not a guarded sentinel. No runtime validator catches it.
