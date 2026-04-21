# Export — Code Review

Commit reviewed: `5a58091670e458fda33d3b9fbe3f1b37ef52a04c`
Files in scope: `src/picsure/_services/export.py`
Contract refs consulted:
- `pic-sure-hpds/service/.../PicSureService.java` (v1 `_querySync`)
- `pic-sure-hpds/service/.../PicSureV3Service.java` (v3 `_querySync`)
- `pic-sure-hpds/service/.../QueryV3Service.java` (result-type dispatch)
- `pic-sure-hpds/client-api/.../ResultType.java`
- `pic-sure-hpds/processing/.../PfbWriter.java`
- `pic-sure/pic-sure-api-war/.../PicsureRSv3.java` (gateway `/query/sync`)
- `pic-sure/pic-sure-api-war/.../PicsureQueryV3Service.java` (gateway pass-through)

## Scope

Three exported entry points (all public, re-exported through the Facade):

- `export_pfb(client, resource_uuid, query, path)` — POSTs to `/picsure/v3/query/sync` with `expectedResultType="DATAFRAME_PFB"` and writes the response body verbatim to disk.
- `export_csv(data, path)` — `DataFrame.to_csv(path, index=False)`.
- `export_tsv(data, path)` — `DataFrame.to_csv(path, sep="\t", index=False)`.

CSV/TSV are pure local-side serialisers; only PFB touches the wire. Transport concerns (client retries, 4xx handling, session lifecycle) are owned by connection-transport.md and only assessed here through how they surface in export.

## Strengths

- Thin, stateless, no hidden global state. Each function is a single clear job.
- `export_csv` / `export_tsv` correctly set `index=False`, which matches the expected "server-returned dataframe, write as-is" semantics.
- `Path(path).write_bytes(raw)` auto-closes the file handle and overwrites atomically enough for typical CLI use. `to_csv` likewise opens/closes its own handle.
- `TransportError -> PicSureConnectionError` translation at the service boundary keeps the public error hierarchy clean, and the message ("Could not export PFB...") is user-oriented rather than stack-oriented.
- Accepts both `str` and `pathlib.Path`, with tests covering both.
- Endpoint path and result-type constant (`DATAFRAME_PFB`) match the HPDS `ResultType` enum (`ResultType.java:65`).

## Issues

### Critical

- **PFB wire contract is probably broken against the v3 sync endpoint** — `src/picsure/_services/export.py:13,33,36` — `export_pfb` POSTs `expectedResultType="DATAFRAME_PFB"` to `/picsure/v3/query/sync`. In `pic-sure-hpds/service/.../PicSureV3Service.java:397-452`, the `_querySync` switch only covers `DATAFRAME`, `SECRET_ADMIN_DATAFRAME`, `DATAFRAME_TIMESERIES`, `PATIENTS`, the cross-counts, variant queries, and `COUNT`. `DATAFRAME_PFB` falls through to `default -> ResponseEntity.status(500).build()`. Even the v1 handler (`PicSureService.java:417-472`), which does route `DATAFRAME_PFB` through its async initializer (`QueryService.java:154,164`), returns the result by stringifying it with `new String(bytes, UTF-8)` — that lossily mangles Avro-binary PFB. There is no PFB code path through `/query/sync` that preserves bytes. In production against v3, `export_pfb` will receive a 500 body and then `client._request` will raise `TransportServerError` after retrying once — which is translated to `PicSureConnectionError("Could not export PFB...")`, a message that misrepresents the actual cause (server does not serve PFB on this endpoint). The PFB flow that HPDS actually implements is async: `POST /query` → poll `/query/{id}/status` → `POST /query/{id}/result` returns the Avro stream via `InputStreamResource` (`PicSureV3Service.java:256-271`). Either the implementation must switch to that flow, or a PFB-specific sync route must be added server-side and confirmed before this method ships. The current unit tests pass only because `respx` mocks an arbitrary 200 body at the sync path.

### Important

- **Non-idempotent retry can double-execute PFB work server-side** — `src/picsure/_services/export.py:36`, transport at `src/picsure/_transport/client.py:59-79` — a 5xx mid-stream or the first-attempt timeout causes `_request` to retry POST `/picsure/v3/query/sync`. For PFB the server-side work is expensive (full dataframe materialisation + Avro encode). Export is the worst kind of endpoint to blind-retry POSTs on. Wave-1 already flagged this generally, noted here because PFB amplifies the cost.

- **4xx response bodies are written to disk as if they were PFB** — `src/picsure/_services/export.py:36,42` — `client._request` only translates 401/403 and ≥500 into exceptions; any other 4xx (400 malformed, 404 resource-not-found, 409, 413, 429) falls through and returns the `httpx.Response`. `post_raw` then returns `response.content` — for a 400 JSON error body, `Path(path).write_bytes(raw)` will happily write `{"error":"..."}` into `my_cohort.pfb`. Users will not discover this until a downstream PFB reader fails. There is no status-code check in `export_pfb`.

- **Response is read fully into memory, then written to disk** — `src/picsure/_services/export.py:36,42` — `post_raw` returns `response.content` (full buffer); `Path.write_bytes(raw)` then re-writes it. For a large cohort, a multi-GB PFB doubles the memory pressure (httpx buffer + bytes object) before hitting disk. `httpx.Client.stream("POST", ...)` with `response.iter_bytes()` writing to an open file would halve peak memory and let partial content flush during the transfer. Not a correctness bug, but an obvious one for an "export large result" API.

- **Disk / permission errors surface as raw `OSError`, not `PicSureError`** — `src/picsure/_services/export.py:42,52,62` — `Path(path).write_bytes` and `DataFrame.to_csv` raise `PermissionError`, `IsADirectoryError`, `FileNotFoundError` (bad parent dir), `OSError` (disk full). None are caught or wrapped. The docstring promises only `PicSureConnectionError`, so users writing `except PicSureError:` will see unrelated `OSError`s leak through. At minimum, wrap the write in try/except and raise a `PicSureError` subclass (`PicSureIOError` or similar); at best, document which OS errors pass through.

- **Network interruption mid-download can leave a partial/empty file** — `src/picsure/_services/export.py:36,42` — if the connection drops after `post_raw` succeeds but before `write_bytes` completes (e.g. disk full partway), the caller is left with a truncated PFB at the target path with no indication. Writing to `path.with_suffix(path.suffix + ".part")` then `os.replace` at the end is the standard atomic-write pattern and avoids leaving corrupt files next to the user's good data. (Applies equally to `export_csv` / `export_tsv`.)

- **No extension / filename enforcement or warning** — `src/picsure/_services/export.py:42,52,62` — the caller's extension is trusted fully. `export_pfb(..., "out.csv")` will write PFB bytes to `out.csv`; `export_csv(df, "out.pfb")` will write CSV text to `out.pfb`. A sanity-check that warns when the extension is wildly wrong (or auto-appends the canonical extension when the path has none) would prevent a class of user error that is trivially common. Minimum bar: document the expected extension in the docstring.

- **Docstrings under-document failure modes** — `src/picsure/_services/export.py:22-32,46-50,58-61` — `export_pfb`'s "Raises" section lists only `PicSureConnectionError`. It omits: `PicSureAuthenticationError` (bubbles up from transport on 401/403), any `OSError` subclass, and the silent "4xx written to disk" behaviour above. `export_csv` / `export_tsv` have no "Raises" block at all. For a user-facing API this is a documentation gap that will generate support tickets.

### Minor

- **`_PICSURE_QUERY_SYNC_PATH` duplicated across modules** — `src/picsure/_services/export.py:13`, `src/picsure/_services/query_run.py:21` — same string constant defined in two files. If the endpoint ever changes (or gets versioned), both must be updated in lockstep. Belongs in a shared `_transport.paths` or similar.

- **`body: dict | None = None` signature on `post_raw` is misleading for export** — `src/picsure/_transport/client.py:48` — `export_pfb` always supplies a body; accepting `None` here is dead surface for this call site. Not export's bug, but worth flagging when the wave-2 refactor touches transport.

- **Type annotation `path: str | Path` accepts but doesn't normalise early** — `src/picsure/_services/export.py:20,45,55` — `export_pfb` wraps to `Path(path)` at write time; `export_csv` / `export_tsv` pass straight through to pandas. Consistent `path = Path(path)` at the top of each function would make error messages uniform and centralise any future validation.

- **No test coverage for 4xx responses, OS errors, or extension mismatch** — `tests/unit/test_export.py` — the present tests cover only success paths and a single 500. Given the critical/important findings above, those gaps match exactly where the real bugs live.

- **`export_csv` / `export_tsv` don't re-use a common helper** — `src/picsure/_services/export.py:52,62` — two one-liners differing only by `sep`. A shared `_write_delimited(data, path, sep)` is cosmetic but kills the temptation to have them drift apart (e.g. someone adding `index=False` handling only to one).

## Verification evidence

1. **Endpoint / result-type lookup**
   - Python constant: `src/picsure/_services/export.py:13` — `_PICSURE_QUERY_SYNC_PATH = "/picsure/v3/query/sync"`.
   - Gateway route: `pic-sure/pic-sure-api-war/src/main/java/edu/harvard/dbmi/avillach/PicsureRSv3.java:188-204` — `@POST @Path("/query/sync")` → `queryService.querySync(...)` → pass-through to HPDS via `resourceWebClient.querySync(...)` (`PicsureQueryV3Service.java:285`).
   - HPDS v3 endpoint: `pic-sure-hpds/service/.../PicSureV3Service.java:361-374` — `@PostMapping(value = "/query/sync", produces = MediaType.TEXT_PLAIN_VALUE) public ResponseEntity querySync(...)`.
   - `DATAFRAME_PFB` enum: `pic-sure-hpds/client-api/.../ResultType.java:65`.
   - v3 `_querySync` switch cases (lines `397-452` of `PicSureV3Service.java`): `INFO_COLUMN_LISTING`, `DATAFRAME | SECRET_ADMIN_DATAFRAME | DATAFRAME_TIMESERIES | PATIENTS`, `CROSS_COUNT`, `CATEGORICAL_CROSS_COUNT`, `CONTINUOUS_CROSS_COUNT`, `OBSERVATION_CROSS_COUNT`, `VARIANT_COUNT_FOR_QUERY`, `VARIANT_LIST_FOR_QUERY`, `VCF_EXCERPT`, `AGGREGATE_VCF_EXCERPT`, `COUNT`, `default -> 500`. **No `DATAFRAME_PFB` branch.**
   - PFB writer is only wired into the async writer pipeline: `QueryV3Service.java:133-134` creates a `PfbWriter` for `DATAFRAME_PFB`; the result is read back by clients via `/query/{resourceQueryId}/result` which returns `new InputStreamResource(result.getStream())` with the writer's own content-type (`PicSureV3Service.java:256-271`). This is the async `POST /query` → poll → `POST /query/{id}/result` path, not `/query/sync`.
   - Even in the v1 handler (`PicSureService.java:417-472`), where `DATAFRAME` runs through the async initializer that can create a `PfbWriter` (`QueryService.java:154,164`), the response body is `new String(result.getStream().readAllBytes(), StandardCharsets.UTF_8)` — inappropriate for Avro PFB.

2. **Streaming / IO semantics**
   - `client.post_raw` (`src/picsure/_transport/client.py:48-54`) reads the full response into memory via `response.content` and returns it as `bytes`. No streaming.
   - `Path(path).write_bytes(raw)` (`export.py:42`) opens in `wb`, writes, and closes via the context manager pandas/pathlib use internally. Handles are closed on error paths. No partial-write recovery.

3. **CSV / TSV defaults**
   - `export.py:52` — `data.to_csv(path, index=False)`. Header defaults to `True` (pandas default). Separator defaults to `,`.
   - `export.py:62` — `data.to_csv(path, sep="\t", index=False)`. Header default `True`.
   - Neither forces quoting, encoding (`utf-8` is pandas default), newline style, or na_rep. These are reasonable defaults but undocumented.

4. **Extension / filename handling**
   - None. Caller's path is written verbatim by all three functions (`:42`, `:52`, `:62`).

5. **Error-handling surface**
   - Only `TransportError -> PicSureConnectionError` is wrapped (`export.py:37-40`).
   - Unwrapped paths: `TransportAuthenticationError` (subclass of `TransportError`, so actually caught — but the generic message "server may be temporarily unavailable" misrepresents 401/403), any `OSError`, any pandas `IOError`, and — most importantly — silent success on 4xx responses where the error body is written to the output file.

6. **Test coverage**
   - `tests/unit/test_export.py` — 10 tests. Success paths, one 500 path, string vs `Path`. No 4xx, no auth failure, no OSError, no extension mismatch, no byte-exactness check beyond the happy path.

7. **Wave 1 context manifestation**
   - 4xx fall-through (flagged in connection-transport): manifests here as the "4xx body written to disk as PFB" bug above.
   - Non-idempotent POST retry (flagged in connection-transport): manifests as duplicate PFB export work server-side.
   - Missing `Session.close()`: doesn't directly surface in export (functions don't own lifecycle), so not flagged here.
