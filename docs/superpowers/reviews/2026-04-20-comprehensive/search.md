# Search — Code Review (UI-parity deep-dive)

## Scope

Commit reviewed: `5a58091670e458fda33d3b9fbe3f1b37ef52a04c`

Files read (Python adapter, review-only):

- `src/picsure/_services/search.py`
- `src/picsure/_models/facet.py`
- `src/picsure/_models/dictionary.py`

Supporting Python files consulted (for context, no modifications):

- `src/picsure/_transport/client.py` — `PicSureClient.post_json` wire behavior, default headers
- `src/picsure/_models/session.py` — `Session.search`, `Session.facets`, `Session.showAllFacets` public surface

Contract sources consulted:

- picsure-dictionary (Java backend):
  - `src/main/java/.../concept/ConceptController.java`
  - `src/main/java/.../facet/FacetController.java`
  - `src/main/java/.../filter/Filter.java`
  - `src/main/java/.../facet/Facet.java`
  - `src/main/java/.../facet/FacetCategory.java`
  - `src/main/java/.../concept/model/Concept.java`,
    `CategoricalConcept.java`, `ContinuousConcept.java`
  - `src/main/resources/application*.properties` (to confirm no Jackson override)
- PIC-SURE-Frontend (TypeScript):
  - `src/lib/paths.ts`
  - `src/lib/stores/Dictionary.ts` (`searchDictionary`, `updateFacetsFromSearch`,
    `getConceptCount`, `addConsents`)
  - `src/lib/models/Search.ts`, `src/lib/models/api/Dictionary.ts`

Artifacts consulted (outside git):

- `artifacts/ui-search-request.har` (5 entries; entry 0 used)
- `artifacts/ui-search-response.json`

## Captured UI request (verbatim from HAR entry 0)

Normalized JSON:

```json
{
  "method": "POST",
  "url_path": "/picsure/proxy/dictionary-api/concepts",
  "query_string": {"page_number": "0", "page_size": "10"},
  "headers": {
    ":authority": "predev.picsure.biodatacatalyst.nhlbi.nih.gov",
    ":method": "POST",
    ":path": "/picsure/proxy/dictionary-api/concepts?page_number=0&page_size=10",
    ":scheme": "https",
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "content-length": "406",
    "content-type": "application/json",
    "origin": "https://predev.picsure.biodatacatalyst.nhlbi.nih.gov",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://predev.picsure.biodatacatalyst.nhlbi.nih.gov/discover",
    "request-source": "Open",
    "sec-ch-ua": "\"Chromium\";v=\"147\", \"Not.A/Brand\";v=\"8\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"macOS\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
  },
  "body": {
    "facets": [
      {
        "name": "tutorial-biolincc_framingham",
        "display": "biolincc_framingham (tutorial-biolincc_framingham)",
        "description": "Framingham Heart Study : Dataset for Teaching Purposes",
        "fullName": null,
        "count": 1,
        "children": [],
        "category": "dataset_id",
        "meta": null,
        "categoryRef": {
          "name": "dataset_id",
          "display": "Dataset",
          "description": "First node of concept path"
        }
      }
    ],
    "search": "Current cigarette smoking at exam"
  }
}
```

HAR entry 0 is the first of the three `concepts` searches and is the request
made immediately after the user both typed a search term and selected a Dataset
facet. The entry was observed unauthenticated (`request-source: Open`, no
`Authorization`) because it was captured on the public `/discover` surface.

## Python-equivalent request (derived from search.py)

For a Session whose `fetch_total_concepts` probe returned 29316 (matches the
captured response's `totalElements`), the equivalent call:

```python
fs = session.facets()                    # loads FacetCategory list
fs.add("dataset_id", "tutorial-biolincc_framingham")
session.search("Current cigarette smoking at exam", facets=fs)
```

produces, per `_build_concepts_body` (search.py:214-225) +
`FacetSet.to_request_facets` (facet.py:132-168) + `PicSureClient`
(client.py:20-46):

```json
{
  "method": "POST",
  "url_path": "/picsure/proxy/dictionary-api/concepts",
  "query_string": {"page_number": "0", "page_size": "29316"},
  "headers": {
    "Content-Type": "application/json",
    "request-source": "Authorized",
    "Authorization": "Bearer <redacted>",
    "host": "<base_url host>",
    "accept": "*/*",
    "accept-encoding": "gzip, deflate",
    "connection": "keep-alive",
    "user-agent": "python-httpx/<version>"
  },
  "body": {
    "search": "Current cigarette smoking at exam",
    "facets": [
      {
        "name": "tutorial-biolincc_framingham",
        "display": "biolincc_framingham (tutorial-biolincc_framingham)",
        "description": "Framingham Heart Study : Dataset for Teaching Purposes",
        "fullName": null,
        "count": 1,
        "children": [],
        "category": "dataset_id",
        "meta": null,
        "categoryRef": {
          "name": "dataset_id",
          "display": "Dataset",
          "description": "First node of concept path"
        }
      }
    ]
  }
}
```

Note on `page_size`: `Session.search` passes `self._total_concepts` (set at
connect time by `fetch_total_concepts`). When the total-concepts probe was run
against this deployment's Open surface the count is 29316 (the captured
response's `totalElements`). That's the "one big page" that `search.py`
deliberately requests so the whole result set returns in one POST
(`search.py:82-98`).

## Divergence table

| field | UI value | Python value | divergent? | likely impact |
|---|---|---|---|---|
| HTTP method | POST | POST | no | — |
| URL path | `/picsure/proxy/dictionary-api/concepts` | `/picsure/proxy/dictionary-api/concepts` | no | — |
| Query param `page_number` | `0` | `0` | no | — |
| Query param `page_size` | `10` (UI pagination) | `29316` (total) | cosmetic | Python requests whole page; backend supports both — see classification |
| Header `content-type` | `application/json` | `application/json` | no | — |
| Header `request-source` | `Open` | `Authorized` (when Bearer token present) | cosmetic | Different auth surface; BDC gateway expects Authorized for tokens (intentional in client.py:21-29) |
| Header `Authorization` | (absent; /discover is public) | `Bearer <token>` | cosmetic | Authenticated API vs public UI path |
| Header `referer` / browser headers | present | absent | cosmetic | Backend doesn't gate on these |
| Body top-level keys | `facets`, `search` | `search`, `facets` (and `consents` if set) | cosmetic | JSON object ordering irrelevant; `consents` accepted by `Filter` record |
| Body `facets[0].name` | `"tutorial-biolincc_framingham"` | `"tutorial-biolincc_framingham"` | no | — |
| Body `facets[0].display` | present | present (pulled from cached FacetCategory) | no | — |
| Body `facets[0].description` | present | present (pulled from cached FacetCategory) | no | — |
| Body `facets[0].fullName` | `null` | `null` (hardcoded in `to_request_facets`) | no | — |
| Body `facets[0].count` | `1` | `1` (pulled from cached Facet) | no | — |
| Body `facets[0].children` | `[]` | `[]` (hardcoded; descendant selections are flattened, not nested) | cosmetic-to-important | Only matters if the backend needs nested hierarchy to interpret a selection — see notes |
| Body `facets[0].category` | `"dataset_id"` | `"dataset_id"` | no | — |
| Body `facets[0].meta` | `null` | `null` (hardcoded) | no | — |
| Body `facets[0].categoryRef.name` | `"dataset_id"` | `"dataset_id"` | no | — |
| Body `facets[0].categoryRef.display` | `"Dataset"` | from cached FacetCategory.display | no | — |
| Body `facets[0].categoryRef.description` | `"First node of concept path"` | from cached FacetCategory.description | no | — |
| Body `facets[0].parentRef` | absent | absent | no | See Frontend `processFacetResults` — `parentRef` is only set on children; Python flattens so this row is the leaf selection |
| Body `search` | `"Current cigarette smoking at exam"` | `"Current cigarette smoking at exam"` | no | — |
| Body `consents` | absent (Discover path) | absent when `_consents` empty, list otherwise | cosmetic | Backend record (`Filter`) accepts nullable `consents` |

No wire-level "wrong-on-the-wire" divergence was found.

## Classification notes per divergence

### `page_size=10` (UI) vs `page_size=29316` (Python) — (a) backend accepts both

The controller accepts any int page size:

- `picsure-dictionary/src/main/java/.../concept/ConceptController.java:38-50`
  signature is
  `@RequestParam(name = "page_size", defaultValue = "10", required = false) int size`
  and calls `PageRequest.of(page, size)` unconditionally.

Python's strategy of "size = total elements so the one response carries
everything" is a deliberate choice (documented in `search.py:82-98` and executed
via `fetch_total_concepts` in `search.py:36-70`). It is functionally equivalent
to fetching all UI pages and concatenating, and the Spring controller has no
guard. The adapter already strips duplicates defensively in
`search.py:228-235`.

One risk: if total concepts >> tens of thousands, the Python approach issues a
single large request and holds the full response in memory. That's a design
tradeoff rather than a correctness issue; called out as Important below.

### `request-source` header: `Open` (UI) vs `Authorized` (Python) — (a) cosmetic

The difference is intentional and documented in
`src/picsure/_transport/client.py:20-29`. The BDC API gateway uses this header
to route to the correct upstream. The captured HAR was taken from the
unauthenticated `/discover` surface, where the UI issues `Open`. A Python
session with a Bearer token represents a different (authenticated) user journey
and must use `Authorized` — a Python session without a token would send `Open`
(client.py:28).

### `consents` key presence — (a) cosmetic

`Filter` is a record with `@Nullable List<String> consents`:
`picsure-dictionary/src/main/java/.../filter/Filter.java:10`. Both omission and
explicit list are accepted.

Note: the Frontend sends `consents: []` in `getConceptCount`
(`PIC-SURE-Frontend/src/lib/stores/Dictionary.ts:175`) and omits the key in
`searchDictionary` when on `/discover` (line 44). The Python adapter omits
`consents` when the list is empty/None (`search.py:222-225`), matching UI
behavior on the Discover surface exactly.

### `facets[0].children: []` — (a) cosmetic

The Java `Facet` record allows `@Nullable List<Facet> children`:
`picsure-dictionary/src/main/java/.../facet/Facet.java:9`. The empty list is
semantically the same as `null`. The concern worth noting: for hierarchical
facet categories (e.g. Consortium_Curated_Facets → Parent → Leaf), when the UI
user clicks a leaf it sends `facets: [{leafFacet, category: "parent's
category"}, categoryRef: {...}]`. The Python `FacetSet.to_request_facets`
(facet.py:132-168) uses `_flatten_options_by_value` (facet.py:179-187), which
flattens the whole tree into a leaf-by-value dict. Selecting the leaf by value
from `FacetSet.add(category, value)` produces an identically-shaped leaf entry.
That lines up with the UI's output, so no bug.

The Frontend's `processFacetResults` additionally sets `parentRef` on children
(`PIC-SURE-Frontend/src/lib/stores/Dictionary.ts:100-124`), but the UI sends
`parentRef` only when the user selects a child facet directly. Nothing in the
Java DTO requires `parentRef`, and in the HAR entry 0 the user selected a
top-level dataset facet so no `parentRef` appears. This is consistent.

### Unknown-field handling in Jackson — general

- `Filter` is annotated `@JsonIgnoreProperties(ignoreUnknown = true)`
  (Filter.java:9) so extra body keys at the top level (e.g. `consents`,
  unexpected keys) are silently ignored.
- `Facet` record is **not** annotated, but the deployment has no Spring Boot
  Jackson override (no `spring.jackson.*` in
  `picsure-dictionary/src/main/resources/application*.properties`) and Spring
  Boot's default is `FAIL_ON_UNKNOWN_PROPERTIES = false`. So extra fields on
  each facet object — the UI routinely sends `categoryRef`, `parentRef`, `meta`
  — are silently ignored at the backend. The backend only reads `name`,
  `display`, `description`, `fullName`, `count`, `children`, `category`, `meta`
  from each Facet. The Python adapter sends exactly these plus `categoryRef`,
  which Jackson ignores. **No divergence.**

### Which Facet fields actually matter to the backend?

`ConceptFilterQueryGenerator` in the Java repo consumes `category` and `name`
to build the WHERE clause
(`picsure-dictionary/src/main/java/.../concept/ConceptFilterQueryGenerator.java`).
That means the only load-bearing fields per submitted facet are `category` and
`name`. Python always sends both correctly populated, sourced from the
per-category `FacetCategory.name` and user-supplied value.

## Response-parsing analysis

Captured response shape (single line, entry 0 response;
`artifacts/ui-search-response.json`):

```json
{
  "content": [ /* 10 Concept objects */ ],
  "pageable": {"pageNumber":0, "pageSize":10, "sort":{...},
               "offset":0, "unpaged":false, "paged":true},
  "totalPages": 2932,
  "totalElements": 29316,
  "last": false,
  "numberOfElements": 10,
  "size": 10,
  "number": 0,
  "sort": {"unsorted":true, "sorted":false, "empty":true},
  "first": true,
  "empty": false
}
```

This is standard Spring `PageImpl` serialization, produced by
`ConceptController.listConcepts`
(`picsure-dictionary/src/main/java/.../concept/ConceptController.java:38-50`).

Python parsing (`search.py:114-123`):

- Reads `data.get("content", [])` — correct, matches the Spring key.
- Reads `data.get("totalElements", 0)` in `fetch_total_concepts`
  (search.py:66) — correct.
- Ignores `pageable`, `totalPages`, `last`, `numberOfElements`, `size`,
  `number`, `sort`, `first`, `empty`. Fine for the "one big page" strategy
  since Python requests `page_size = totalElements` and assumes it got
  everything. **But no guard/assert that `numberOfElements == totalElements` or
  `last is true`**, so if the server silently caps page size the adapter will
  return a truncated result without warning. Called out as Important.

Per-row `DictionaryEntry.from_dict` (`dictionary.py:18-34`):

- `conceptPath` — matches captured key.
- `name` — matches.
- `display` — matches.
- `description` — matches.
- `dataType = data.get("type", data.get("dataType", ""))` — captured key is
  `type` (set as JSON type discriminator by `@JsonProperty("type")` on
  `ContinuousConcept.type()` /
  `CategoricalConcept.type()`). Python picks the right key.
- `studyId = data.get("dataset", data.get("studyId", ""))` — captured key is
  `dataset`. Python picks the right key (and the `studyId` fallback is dead
  legacy compatibility but harmless).
- `values = data.get("values", [])` — matches `CategoricalConcept.values`.
  **Continuous concepts have no `values`** (they have `min`/`max`, see
  `ContinuousConcept.java:11-19`). The captured response is all Continuous
  entries, every row therefore yields an empty `values: []`. Python silently
  drops `min`/`max`, `allowFiltering`, `studyAcronym`, `meta`, `table`,
  `study`, and `children`. That is a deliberate simplification — documented in
  the DataFrame column list at `search.py:16-33` — but it means users cannot
  see Continuous-range information. Called out as Important.

### Dedup logic (`_deduplicate`, search.py:228-235)

Dedups by `concept_path` alone. The backend's `Concept.conceptEquals`
(`picsure-dictionary/src/main/java/.../concept/model/Concept.java:73-78`) dedups
by `(dataset, conceptPath)`. In practice `conceptPath` is already prefixed with
the dataset (e.g. `\phs000007\pht...\...\`) so path-only dedup is effectively
equivalent, but on deployments that reuse path fragments across datasets the
Python version could collapse distinct rows. Called out as Minor given current
BDC concept-path convention.

The UI has no client-side dedup; it trusts Spring's page contents as-is. So
Python is stricter than UI on this point.

### Facet vs result separation

`/concepts` returns only concepts (no facet counts embedded). The UI computes
per-facet counts by calling `/facets` separately
(`PIC-SURE-Frontend/src/lib/stores/Dictionary.ts:75-97`). Python mirrors this:
results come from `/concepts` (`search` → `fetch_total_concepts` +
`_services.search.search`) and facets come from `/facets`
(`fetch_facets`, `show_all_facets`). The separation is correct.

## Facet-loading endpoint comparison (facets / showAllFacets vs UI)

| aspect | UI (`updateFacetsFromSearch`) | Python (`fetch_facets` → `Session.facets`/`showAllFacets`) | divergent? |
|---|---|---|---|
| HTTP method | POST | POST | no |
| URL | `/picsure/proxy/dictionary-api/facets` | `/picsure/proxy/dictionary-api/facets` | no |
| Body | `{facets: currentSelections, search: currentSearchTerm, consents?}` | `{search: "", facets: [], consents?}` | yes (behavior-level) |
| Response | `FacetCategory[]` (list of categories, each with `facets: Facet[]`) | list of `FacetCategory` — same shape parsed by `FacetCategory.from_dict` (facet.py:78-91) | no |
| Handling | UI hides facet options with count 0, decorates with `categoryRef`/`parentRef` client-side | Python captures counts verbatim, includes 0-count options in `show_all_facets` | yes (UX-level) |

Key behavioral difference, classified:

### Python always POSTs `{facets: [], search: ""}` — (c) subtle semantic difference

`fetch_facets` calls `_build_concepts_body(term="", facets=None,
consents=consents)` (search.py:136) — always empty term, always no facets. The
UI sends the **current** search term and current selected facets so that
per-option counts reflect what's still available under the current filter
(`PIC-SURE-Frontend/src/lib/stores/Dictionary.ts:75-97`). That's the point of
the facet sidebar: it shows "if I add this one more filter to what I have,
there are N more concepts." Python only ever asks "show me all categories with
their global counts."

Consequence: `Session.showAllFacets` and `Session.facets()` return global
counts, not counts contextual to an in-progress search. Users comparing
adapter output to the UI may see different numbers. This is not wrong on the
wire — the backend accepts both — but semantically Python cannot be used to
preview "how much would adding this facet narrow my results." Called out as
Important.

The Facet/FacetSet API surface doesn't currently even let a user express
"recompute facet counts under this selection"; `FacetSet.to_request_facets` is
only used for `/concepts`, and `fetch_facets` is private to the module and
never re-called mid-session. If this is a deliberate scope decision, docstring
should say so; if not, refactoring `fetch_facets` to accept `term` and `facets`
is a small change.

### Zero-count facet options — (a) cosmetic

The UI hides options whose `count == 0`
(`PIC-SURE-Frontend/src/lib/stores/Dictionary.ts:53-73`). `show_all_facets`
(search.py:161-196) returns every option regardless of count. For notebook
use this is probably desirable (users want to know "nothing matches here"
explicitly), but `showAllFacets`'s docstring
(session.py:169-177 / search.py:161-179) says nothing about this. Documenting
it would be kind.

## Strengths

- **Endpoint and body match the UI contract.** Both `Session.search`
  (→ `/concepts`) and `Session.facets`/`showAllFacets` (→ `/facets`) POST to
  the correct paths with the correct body shape (`{search, facets, consents?}`
  against the Spring `Filter` record).
- **Facet object shape is a faithful reproduction.** `to_request_facets` emits
  every field the UI emits (`name`, `display`, `description`, `fullName`,
  `count`, `children`, `category`, `meta`, `categoryRef`), with correct
  defaults where FacetSet doesn't carry state (`fullName: null`,
  `children: []`, `meta: null`).
- **Defense-in-depth against Jackson surprises.** Even fields the backend
  ignores (`categoryRef`, `meta`) are populated — so a future backend that
  starts *using* those fields (e.g. a newer Filter record) won't break the
  adapter.
- **Iterative facet tree construction avoids stack overflow** on arbitrarily
  nested facet hierarchies (facet.py:27-66). Good defensive engineering given
  the BDC Consortium_Curated_Facets tree.
- **Single-POST pagination strategy is deliberate and documented.**
  `fetch_total_concepts` probes `totalElements` then `search` asks for exactly
  that page size. Correctly handled non-integer responses
  (search.py:67-70).
- **Facet-selection flattening matches how backend interprets selections.**
  `_flatten_options_by_value` means `FacetSet.add("category", "leaf_name")`
  works regardless of tree depth — user doesn't need to know the parent chain.
- **Transport retry & error mapping.** `PicSureClient._request` retries 5xx /
  connection errors once, translates 401/403 to `TransportAuthenticationError`,
  and `search.py` wraps `TransportError` → `PicSureConnectionError` with a
  user-friendly message.
- **Dedup** by `concept_path` (search.py:228-235) protects against duplicate
  rows from the server (rare but has happened historically with some
  deployments joining via aggregate).

## Issues

### Critical

None. The wire-level contract matches the UI.

### Important

1. **`fetch_facets` ignores the current search term and selection, so
   `Session.showAllFacets` counts are "global", not contextual.** The UI uses
   `/facets` to drive the sidebar that tells users "if you add this filter,
   you'll get N more concepts." Python always sends
   `{search: "", facets: []}` to `/facets`, so counts are the unfiltered
   totals. This means users cannot reproduce the UI's sidebar counts
   programmatically, and it's easy to mislead someone who is iterating on a
   query.
   - Pointer: `src/picsure/_services/search.py:126-148`
   - Fix: plumb `term` and `facets: FacetSet | None` into `fetch_facets` and
     into `Session.facets()`/`showAllFacets`, OR update the docstring to state
     clearly that counts are global.
2. **Continuous-concept fields (`min`, `max`, `allowFiltering`, `meta`,
   `studyAcronym`) are silently dropped from the DataFrame.** All 10 rows in
   the captured response are Continuous; the DataFrame exposes `values: []`
   for every one, which is misleading. A user would reasonably expect at
   least `min`/`max` to survive.
   - Pointer: `src/picsure/_models/dictionary.py:18-34` and
     `src/picsure/_services/search.py:16-33,238-255`
   - Fix: extend `DictionaryEntry` with the missing fields (or document the
     drop).
3. **No sanity check that the "one big page" request returned the full
   dataset.** `search.py` asks for `page_size = self._total_concepts` and
   returns `data["content"]` as if complete. If the server caps page size,
   or if `_total_concepts` was stale (two sessions, one study added
   mid-session, etc.), the user silently gets truncated results.
   - Pointer: `src/picsure/_services/search.py:103-123`
   - Fix: check `data.get("last")` and `data.get("totalElements")`; on
     mismatch either fetch additional pages or emit a warning.
4. **Memory: for a 29k-row probe the single request and DataFrame build are
   O(totalElements).** On deployments with very large dictionaries this could
   be a silent memory spike. Not a correctness bug, but worth pagination
   support as a knob.
   - Pointer: `src/picsure/_services/search.py:73-123`
5. **Duck-typing on `fetch_facets`'s response shape.** The code uses
   `data if isinstance(data, list) else data.get("facets", [])`
   (search.py:145-147). `PicSureClient.post_json` is typed `-> dict` but the
   `/facets` endpoint returns a JSON array at the top level; the call works
   because httpx returns `list` regardless of the type annotation. This is
   brittle (a strict type checker would complain) and relies on the
   non-standard return. Consider changing the client's `post_json` return
   type to `dict | list` or giving it a `post_json_list` helper.
   - Pointer: `src/picsure/_services/search.py:139-148`,
     `src/picsure/_transport/client.py:43-46`

### Minor

1. **Dedup uses `concept_path` only, but backend defines equality as
   `(dataset, conceptPath)`.** With BDC's path convention they're
   equivalent, but if a future deployment reuses path fragments across
   datasets, `_deduplicate` could collapse distinct rows.
   - Pointer: `src/picsure/_services/search.py:228-235` vs
     `picsure-dictionary/.../concept/model/Concept.java:73-78`.
2. **`show_all_facets` docstring claims four columns, code emits six.** The
   function docstring (session.py:172-173) says "category, display, value,
   count", but `_SHOW_ALL_FACETS_COLUMNS` is
   `[category, Category Display, display, description, value, count]`.
   - Pointer: `src/picsure/_models/session.py:169-177` and
     `src/picsure/_services/search.py:151-158`.
3. **`_walk_options` has a misleading type signature and comment.** Declared
   as `list[FacetCategory] -> list[FacetCategory]`, but it actually walks
   `list[Facet] -> list[Facet]`. The docstring + inline comment
   (search.py:199-211) acknowledges this but keeps the wrong types "to avoid
   a circular import."  That's a weak reason; moving the type into the
   function body as `TYPE_CHECKING`-only, or using a `TypeVar`, would let
   mypy/pyright help instead of actively misleading.
4. **Minor inconsistency: `_build_concepts_body` puts `search` before
   `facets` (search.py:219-222), but UI JSON puts `facets` first.** JSON key
   order is semantically irrelevant, but if any integration test compares
   request bytes literally, this would trip them.
5. **`show_all_facets` includes facet options with `count == 0`.** Matches
   `Session.facets()`-compatible input (users may want to select a
   zero-count option to see why), but diverges from UI which hides them.
   Worth documenting.
6. **Docstring on `fetch_facets` (search.py:129-135) says "same body shape as
   `search`"**, which is true in shape but not in content — the term and
   selections are always empty. Consider noting that.

## Verification evidence

- HAR parse: entry 0 has method POST, URL
  `https://predev.picsure.biodatacatalyst.nhlbi.nih.gov/picsure/proxy/dictionary-api/concepts?page_number=0&page_size=10`,
  `postData.text` = `{"facets":[{"name":"tutorial-biolincc_framingham",...
  "categoryRef":{"name":"dataset_id","display":"Dataset","description":"First node of concept path"}}],"search":"Current cigarette smoking at exam"}`
  (HAR lines 213-322).
- Response HAR entry 0 + `artifacts/ui-search-response.json`:
  `totalElements: 29316`, `totalPages: 2932`, `content` length 10, all rows
  have `type: "Continuous"` and no `values` field (aligns with
  `ContinuousConcept.java:11-19`).
- Python body derivation: walked `FacetSet.to_request_facets`
  (facet.py:132-168) with a one-value selection on `dataset_id` and
  confirmed the output matches the HAR facet object byte-for-byte modulo JSON
  key ordering. The cached `FacetCategory` for `dataset_id` must carry
  `display="Dataset"` and `description="First node of concept path"` — these
  come from the server's `/facets` response and are preserved verbatim.
- Backend DTO acceptance: `Filter.java:9-11` is
  `@JsonIgnoreProperties(ignoreUnknown = true)` and accepts
  `facets`, `search`, `consents` (all `@Nullable`). `Facet.java` (no explicit
  `JsonIgnoreProperties`) is deserialized via Spring Boot default
  (`FAIL_ON_UNKNOWN = false`, confirmed no `spring.jackson.*` override in
  `application*.properties`). Unknown body fields are ignored at all levels.
- Controller method: `ConceptController.java:36-50` —
  `@PostMapping("/concepts")` with `@RequestParam page_number`, `page_size`
  and `@RequestBody Filter`. Returns `ResponseEntity<Page<Concept>>`, i.e.
  the Spring paginated shape observed in the response.
- Python parses `content` correctly (`search.py:114`) and
  `totalElements` correctly (`search.py:66`). It does not parse `last`,
  `totalPages`, `numberOfElements`, `pageable`, etc. — this is safe under the
  "one huge page" strategy but unguarded against truncation.
- Frontend reference: `searchDictionary` at
  `PIC-SURE-Frontend/src/lib/stores/Dictionary.ts:38-51` issues
  `api.post(${Picsure.Concepts}?page_number=X&page_size=Y, {facets, search, consents?})`,
  matching Python's request exactly up to `page_size` choice and auth
  headers.

**Verdict on search-vs-UI mismatch: PARTIAL.** Wire format is correct —
nothing divergent on the POST bytes that the backend sees (and the backend
would silently ignore any extra fields anyway). But two behavior-level
mismatches matter: (1) `/facets` is called with empty term/facets so
`showAllFacets` counts are global rather than contextual to an in-progress
search, and (2) Continuous-concept `min`/`max` and several other fields are
dropped from the returned DataFrame. Both are fixable without changing the
public API surface.
