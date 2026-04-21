# Query building — Code Review

## Scope

Files read:
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/src/picsure/_services/query_build.py`
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/src/picsure/_models/clause.py`
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/src/picsure/_models/clause_group.py`
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/src/picsure/_models/query.py`
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/src/picsure/_services/query_run.py` (SELECT extraction pipeline only)
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/tests/unit/test_clause.py`
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/tests/unit/test_clause_group.py`
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/tests/unit/test_query_build.py`

Contracts consulted:
- `/Users/george/code_workspaces/bdc/pic-sure-hpds/client-api/src/main/java/edu/harvard/hms/dbmi/avillach/hpds/data/query/v3/Query.java`
- `/Users/george/code_workspaces/bdc/pic-sure-hpds/client-api/src/main/java/edu/harvard/hms/dbmi/avillach/hpds/data/query/v3/PhenotypicClause.java`
- `/Users/george/code_workspaces/bdc/pic-sure-hpds/client-api/src/main/java/edu/harvard/hms/dbmi/avillach/hpds/data/query/v3/PhenotypicFilter.java`
- `/Users/george/code_workspaces/bdc/pic-sure-hpds/client-api/src/main/java/edu/harvard/hms/dbmi/avillach/hpds/data/query/v3/PhenotypicSubquery.java`
- `/Users/george/code_workspaces/bdc/pic-sure-hpds/client-api/src/main/java/edu/harvard/hms/dbmi/avillach/hpds/data/query/v3/PhenotypicFilterType.java`
- `/Users/george/code_workspaces/bdc/pic-sure-hpds/client-api/src/main/java/edu/harvard/hms/dbmi/avillach/hpds/data/query/v3/Operator.java`
- `/Users/george/code_workspaces/bdc/pic-sure-hpds/processing/src/main/java/edu/harvard/hms/dbmi/avillach/hpds/processing/v3/PhenotypicFilterValidator.java`
- `/Users/george/code_workspaces/bdc/pic-sure-hpds/processing/src/main/java/edu/harvard/hms/dbmi/avillach/hpds/processing/v3/QueryValidator.java`
- `/Users/george/code_workspaces/bdc/pic-sure/pic-sure-api-war/src/main/java/edu/harvard/dbmi/avillach/service/PicsureQueryV3Service.java`

Commit: `5a58091670e458fda33d3b9fbe3f1b37ef52a04c`.

## Strengths

- Wire-format fidelity for FILTER/REQUIRE/ANYRECORD leaves is correct: `phenotypicFilterType` / `conceptPath` / `values` / `min` / `max` / `not` and the enum values `FILTER` / `REQUIRED` / `ANY_RECORD_OF` match the Java `PhenotypicFilterType` enum byte-for-byte (case-sensitive).
- `GroupOperator.AND` / `GroupOperator.OR` values match the Java `Operator` enum exactly; serialized via `self.operator.value`, so Jackson will happily deserialize.
- `PhenotypicSubquery` body (`operator` / `phenotypicClauses` / `not`) matches the Java record precisely.
- Multi-key `Clause` is correctly lowered to an OR `PhenotypicSubquery` of single-key leaves — sensible semantics (match any of the keys).
- SELECT-clause handling is cleanly separated into a recursive `select_paths()` traversal and a `has_phenotypic()` guard that prevents emitting empty phenotypic subqueries. The top-level `build_query_body()` correctly hoists SELECTs to the `select` array.
- `Clause.to_query_json()` raises `PicSureValidationError` when called directly on a SELECT clause (`clause.py:68-72`), guarding against the single-clause wrong-layer mistake.
- `createClause` actionable validation errors for ANYRECORD+categories, ANYRECORD+min/max, and FILTER-with-no-criteria are thorough and readable (`query_build.py:51-70`).
- `@dataclass(frozen=True)` on both `Clause` and `ClauseGroup` gives good immutability semantics for hashability and defensive use.
- The `Query` type alias (`Clause | ClauseGroup`) is a nice ergonomic touch at the public boundary.
- Test coverage for the serialization path is solid: multi-key OR wrapping, deeply nested groups, SELECT stripping, empty-all-SELECT groups, and `has_phenotypic` recursion are all exercised.

## Issues

### Critical

(None found in the query-build layer. The FILTER-both-categories-and-min-max case is incorrectly accepted locally but rejected by the backend with a clear error, so it's a misleading-error issue rather than wire corruption — reported as Important below.)

### Important

- **`createClause` does not reject FILTER with both `categories` and `min`/`max`** — `src/picsure/_services/query_build.py:65-70` — The backend `PhenotypicFilterValidator.validateFilterFilter` throws `IllegalArgumentException("... cannot have both categorical values and min/max set")` for this combination. The adapter silently accepts it, serializes both sets of fields to the wire, and the user gets a confusing server-side error instead of an actionable client-side one. The validation at line 65 only catches the no-criteria case.

- **`createClause` does not reject REQUIRE with `categories`/`min`/`max`** — `src/picsure/_services/query_build.py:51-70` — Backend `validateRequiredFilter` throws on this combination. The adapter accepts it, stores the fields on the `Clause` instance, then silently discards them in `_make_leaf` (which gates the extra fields on `type == ClauseType.FILTER`, `clause.py:93-99`). Result: user-supplied data is silently dropped with no diagnostic. Likely to mislead users who expect e.g. `REQUIRE` + `categories` to behave like `FILTER`. Should raise a `PicSureValidationError` modeled on the ANYRECORD check.

- **`createClause` does not reject SELECT with `categories`/`min`/`max`** — `src/picsure/_services/query_build.py:51-70` — Same silent-discard pattern as the REQUIRE case. The `Clause` is built with the extra fields, but `to_query_json()` refuses to emit it and the extraction path only retrieves `keys`. A user who passes `categories` to a `SELECT` clause has no way to discover their intent was ignored. Should raise a validation error, symmetric with the ANYRECORD/REQUIRE guard.

- **Misleading `Boolean not` semantics — `not=False` is hard-coded, no way to negate a clause** — `src/picsure/_models/clause.py:80,91`, `src/picsure/_models/clause_group.py:54` — The v3 backend accepts `not` on both `PhenotypicFilter` and `PhenotypicSubquery` (see `PhenotypicSubquery.not` and `PhenotypicFilter.not`). The adapter unconditionally writes `"not": False`, and the docstring on `PhenotypicSubquery` says "Not implemented yet" — but the `Clause` model still advertises `not` in its "Wire format" docstring while providing no public way to set it. The review rubric asks to verify "`not` semantics on both Clause and ClauseGroup"; there are none. Either document explicitly that negation is unsupported (and drop the mention), or expose a `negated: bool` dataclass field on both `Clause` and `ClauseGroup`. The current state is a silent public-API limitation.

- **`ClauseGroup.to_query_json()` silently drops SELECT children, the review rubric explicitly asks for a raise** — `src/picsure/_models/clause_group.py:46-55` — The review contract asks: "Does `to_query_json()` raise `PicSureValidationError` on SELECT at the wrong layer?" — at the `Clause` layer, yes; at the `ClauseGroup` layer, no. Silent stripping is safe because `select_paths()` and `has_phenotypic()` correctly extract paths at the top level, but a user who builds `buildClauseGroup([sex_filter, select_clause], root=OR)` expecting the SELECT to act as an OR-branch will get a different query than they wrote without any warning. Either (a) raise when a SELECT is found inside a group (matching the Clause-level behavior), or (b) loudly document this in the `buildClauseGroup` / `ClauseGroup` docstrings with an example. The current `ClauseGroup.to_query_json` docstring mentions stripping, but the public `buildClauseGroup` docstring does not mention it at all.

- **`buildClauseGroup` accepts a list with a single clause and emits a no-op subquery** — `src/picsure/_services/query_build.py:106-109` — Produces `{"operator": "AND", "phenotypicClauses": [leaf], "not": False}` which the backend accepts but is strictly redundant. More importantly, no validation is performed on the clause list's *contents* — a list of all-SELECTs will construct a group that serializes to an empty-`phenotypicClauses` subquery. The safety net at `query_run.py:108-120` catches this for the primary execution path, but a user who calls `group.to_query_json()` directly (e.g., to inspect the wire body) will see an invalid-per-contract empty subquery. Consider adding a structural precondition.

- **`Clause.keys` / `ClauseGroup.clauses` / `Clause.categories` use mutable `list` inside a frozen dataclass** — `src/picsure/_models/clause.py:50-54`, `src/picsure/_models/clause_group.py:34` — The dataclass is frozen, but `list` is mutable; `clause.keys.append("...")` after construction still works and mutates shared state (since `createClause` promotes the caller's `list[str]` reference without copying — see `query_build.py:46-49`). The `_make_leaf` call at `clause.py:95` wraps values in `list(self.categories)` which is good, but `self.keys` is passed by reference and iterated directly. Recommend either `tuple` for these fields or a defensive `list(...)` copy in `createClause`.

### Minor

- **`ClauseType` enum values are lowercase while everything else on the wire is uppercase** — `src/picsure/_models/clause.py:23-26` — `ClauseType.FILTER.value == "filter"`, but the wire emits via the `_PHENOTYPIC_FILTER_TYPE` map. This is fine because `.value` never reaches the wire, but it's stylistically inconsistent with `GroupOperator` (which does flow `.value` straight to JSON). Risk of future bug if someone assumes `ClauseType.FILTER.value` is wire-safe. Either make the enum values uppercase wire-strings and drop the map, or add a comment.

- **`phenotypicClause` backend field is singular `PhenotypicClause` but `phenotypicClauses` (plural) is used for the subquery list** — not adapter-side issue, but noting that the naming on the wire (`phenotypicClause` at the top level vs. `phenotypicClauses` nested) is subtle. `build_query_body` uses the singular (correct) and `ClauseGroup.to_query_json` uses the plural (correct). Easy to typo; consider a tiny constant or model.

- **No test exercises the `Clause | ClauseGroup` union via `createClause("x", type=ClauseType.FILTER, categories="y")` then direct use in `buildClauseGroup` with nested groups** — `tests/unit/test_query_build.py` covers each layer, but not a single end-to-end test that mixes `createClause` outputs with a literal `ClauseGroup` constructor. Not urgent — the existing coverage is solid — but a smoke test would catch future drift in the `createClause`→`Clause` construction path.

- **`keys: str | list[str]` accepts an empty list silently** — `src/picsure/_services/query_build.py:46-47` — `createClause([], type=ClauseType.FILTER, categories="x")` builds a `Clause` with no keys; `to_query_json` then returns `{"operator": "OR", "phenotypicClauses": [], "not": False}` (len(leaves) == 0 falls through the `if len(leaves) == 1` check). Unlikely in practice but generates an invalid body. Consider a non-empty check.

- **`createClause` docstring example shows `min=40.0` for a FILTER but omits `max`, silently relying on the half-open interval semantics** — `src/picsure/_services/query_build.py:40-44` — Fine per the `PhenotypicFilter` contract (min-only is allowed), but users migrating from the previous SDK may expect both bounds. Could add a sentence noting "min-only / max-only / both all supported".

- **`PhenotypicSubquery.not` is documented as "Not implemented yet" in the backend** — no adapter action needed, just awareness: hard-coding `"not": False` is right even if the adapter exposed a `negated` field, because the backend would ignore it anyway. Ties into the `not`-semantics Important finding above.

- **Redundant `if isinstance(keys, str)` / `if isinstance(categories, str)` normalization is repeated** — `src/picsure/_services/query_build.py:46-49` — Very minor; a `_as_list(x)` helper would DRY this up but is hardly necessary for two lines.

## Verification evidence

**Enum values match the backend verbatim:**
- Java `PhenotypicFilterType`: `REQUIRED`, `FILTER`, `ANY_RECORD_OF` (`PhenotypicFilterType.java:7-13`).
- Python `_PHENOTYPIC_FILTER_TYPE` map: `FILTER→"FILTER"`, `REQUIRE→"REQUIRED"`, `ANYRECORD→"ANY_RECORD_OF"` (`clause.py:29-33`). Exact case-sensitive match.
- Java `Operator`: `AND`, `OR` (`Operator.java:5-9`).
- Python `GroupOperator`: `AND = "AND"`, `OR = "OR"` (`clause_group.py:16-17`). Exact match.

**`PhenotypicFilter` shape matches:**
- Java record: `phenotypicFilterType`, `conceptPath`, `values` (Set<String>), `min` (Double), `max` (Double), `not` (Boolean) (`PhenotypicFilter.java:8-23`).
- Python `_make_leaf` emits `phenotypicFilterType`, `conceptPath`, `not`, optionally `values` / `min` / `max` (`clause.py:87-100`). Jackson handles JSON array → Set<String> automatically. Shape matches.

**`PhenotypicSubquery` shape matches:**
- Java record: `not`, `phenotypicClauses` (List<PhenotypicClause>), `operator` (`PhenotypicSubquery.java:7-14`).
- Python `ClauseGroup.to_query_json`: `operator`, `phenotypicClauses`, `not` (`clause_group.py:51-55`). Field order differs but JSON is order-independent; shape matches.

**Top-level `Query` shape matches:**
- Java record `Query`: `select`, `authorizationFilters`, `phenotypicClause`, `genomicFilters`, `expectedResultType`, `picsureId`, `id` (`Query.java:11-23`).
- Python `build_query_body`: `select`, `phenotypicClause`, `genomicFilters`, `expectedResultType`, `picsureId`, `id` (no `authorizationFilters`, intentionally — see the docstring comment: "PSAMA populates it server-side from the user's token"). Compatible with the Java record which treats `authorizationFilters == null` as `List.of()` (`Query.java:33-35`).

**SELECT isolation is correct at the execution boundary:**
- `build_query_body` calls `query.select_paths()` and only includes `phenotypicClause` for `has_phenotypic()`-positive queries (`query_run.py:93-120`). SELECT concept paths never reach `phenotypicClause`.
- `Clause.to_query_json` refuses to serialize `ClauseType.SELECT`, raising `PicSureValidationError` (`clause.py:68-72`).
- `ClauseGroup.to_query_json` silently strips SELECTs from its children (`clause_group.py:46-50`) — see Important finding above for the symmetry gap.

**Test suite corroborates:**
- `tests/unit/test_clause.py:135-138` — `Clause.to_query_json` raises on SELECT.
- `tests/unit/test_clause.py:140-152` — Multi-key clause → OR subquery of leaves.
- `tests/unit/test_clause_group.py:151-167` — SELECTs stripped from phenotypic; empty-children produced when all-SELECT.
- `tests/unit/test_clause_group.py:131-149` — Three-deep nesting round-trips correctly.
- `tests/unit/test_query_build.py:90-129` — ANYRECORD+categories, ANYRECORD+min, ANYRECORD+max, and FILTER-without-criteria all raise.

**Gaps not covered by tests:**
- No test for `createClause("\\p\\", type=FILTER, categories="x", min=10.0)` (the backend-rejects-locally-accepts case).
- No test for `createClause("\\p\\", type=REQUIRE, categories="x")` (silent-discard).
- No test for `createClause("\\p\\", type=SELECT, categories="x")` (silent-discard).
- No test for `createClause([], ...)` (empty keys).
