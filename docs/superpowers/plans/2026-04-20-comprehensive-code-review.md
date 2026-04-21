# Comprehensive Code Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce six parallel, area-focused code reviews of `pic-sure-python-adapter-hpds` — with a cross-stack UI-parity deep-dive on search — and synthesize findings into a ranked index.

**Architecture:** Controller (the orchestrating Claude) dispatches six sub-agents across two waves. Wave 1 (Connection & Transport, Search) runs in parallel; controller writes a between-wave brief; Wave 2 (Query building, Query execution, Export, Cross-cutting) runs in parallel; controller synthesizes `index.md`. All review output lives under `docs/superpowers/reviews/2026-04-20-comprehensive/`. No source code under `src/` is modified.

**Tech Stack:** Claude Code `Agent` tool (subagent_type: `general-purpose`), `Read` / `Write` / `Bash` / `Grep` for verification, markdown for output.

**Spec:** `docs/superpowers/specs/2026-04-20-comprehensive-code-review-design.md`

---

## File Structure

Files created by this plan (all under the worktree at `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items`):

- `docs/superpowers/reviews/2026-04-20-comprehensive/connection-transport.md` — Agent 1 output.
- `docs/superpowers/reviews/2026-04-20-comprehensive/search.md` — Agent 2 output, deep-dive with diff table.
- `docs/superpowers/reviews/2026-04-20-comprehensive/query-build.md` — Agent 3 output.
- `docs/superpowers/reviews/2026-04-20-comprehensive/query-run.md` — Agent 4 output.
- `docs/superpowers/reviews/2026-04-20-comprehensive/export.md` — Agent 5 output.
- `docs/superpowers/reviews/2026-04-20-comprehensive/cross-cutting.md` — Agent 6 output.
- `docs/superpowers/reviews/2026-04-20-comprehensive/index.md` — Controller-authored synthesis.

Files read (never modified) during this plan:

- Everything under `src/picsure/` (this repo).
- Sibling repos at absolute paths for contract references:
  - `/Users/george/code_workspaces/bdc/pic-sure`
  - `/Users/george/code_workspaces/bdc/pic-sure-hpds`
  - `/Users/george/code_workspaces/bdc/picsure-dictionary`
  - `/Users/george/code_workspaces/bdc/PIC-SURE-Frontend`
- Pre-flight artifacts at:
  - `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-request.har`
  - `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-response.json`

---

## Shared prompt template

Every sub-agent prompt uses this structure. Per-agent prompts below fill in `<AREA>`, `<SCOPE_PATHS>`, `<CONTRACT_PATHS>`, `<METHOD>`, `<OUTPUT_PATH>`, and `<WAVE1_CONTEXT>` (Wave 2 only).

```
You are reviewing <AREA> of the pic-sure-python-adapter-hpds Python library.
Do NOT modify any source file under src/ — review only.

REPO ROOT (this worktree):
  /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items

SCOPE (files you MUST read):
<SCOPE_PATHS>

CONTRACT REFERENCES (read as needed; sibling repos):
<CONTRACT_PATHS>

METHOD:
<METHOD>

SEVERITY RUBRIC:
  - Critical:  wrong-on-the-wire, data corruption, security issue, crashes on normal
               inputs, public API contract broken.
  - Important: incorrect behavior under real-world inputs, misleading errors, missing
               tests for non-trivial logic, docs that would lead a user astray.
  - Minor:     naming, small duplication, stylistic drift, non-actionable observations.

<WAVE1_CONTEXT>

OUTPUT:
  Write your review to <OUTPUT_PATH> using this exact top-level structure:

    # <AREA> — Code Review

    ## Scope
    (Files read. Contracts consulted. Commit SHA at review time if relevant.)

    ## Strengths
    (What's well-built. Be specific — name functions, patterns, design decisions.)

    ## Issues

    ### Critical
    - **<short title>** — `path/to/file.py:LINE` — <one-line explanation>
      (Follow-up lines if the issue needs more context.)

    ### Important
    (Same format.)

    ### Minor
    (Same format.)

    ## Verification evidence
    (What you ran, read, or diffed to reach each finding. Link findings to evidence.)

ESCALATION:
  If you cannot proceed — missing file, ambiguous contract, HAR malformed, etc. —
  STOP and report NEEDS_CONTEXT with the specific blocker. Do NOT guess.

REPORT BACK:
  Status: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT
  Summary: 3-5 sentences naming the most important findings.
  (The full review lives in the file you wrote.)
```

---

### Task 1: Pre-flight verification

**Files:**
- Read: `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-request.har`
- Read: `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-response.json`
- Create: `docs/superpowers/reviews/2026-04-20-comprehensive/` (directory)

- [ ] **Step 1: Verify both artifact files exist and are non-empty**

Run:
```
ls -la /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/
```

Expected: both `ui-search-request.har` and `ui-search-response.json` present, each with a non-zero size. If either is missing or empty, STOP and ask the user to (re-)capture.

- [ ] **Step 2: Sanity-check the HAR structure**

Run:
```
python3 -c "import json,sys; d=json.load(open('/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-request.har')); print(len(d['log']['entries']), 'entries'); print([e['request']['url'] for e in d['log']['entries']][:5])"
```

Expected: prints an entry count ≥ 1 and at least one URL containing `search` or `dictionary`. If the HAR parses but contains no search-related entries, STOP and ask the user which entry is the search request.

- [ ] **Step 3: Sanity-check the response JSON**

Run:
```
python3 -c "import json; d=json.load(open('/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-response.json')); print(type(d).__name__); print(list(d.keys())[:10] if isinstance(d, dict) else f'length={len(d)}')"
```

Expected: parses without error; prints either a dict with search-result-ish keys (e.g., `results`, `hits`, `content`) or a list of result objects.

- [ ] **Step 4: Create the reviews output directory**

Run:
```
mkdir -p /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive
```

Expected: directory exists and is empty.

- [ ] **Step 5: Record the current HEAD commit**

Run:
```
git -C /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items rev-parse HEAD
```

Expected: a SHA. Save it as `HEAD_SHA` for use in each agent's "Scope" section.

---

### Task 2: Dispatch Wave 1 — Connection/Transport and Search agents (parallel)

**Files:**
- Create (by Agent 1): `docs/superpowers/reviews/2026-04-20-comprehensive/connection-transport.md`
- Create (by Agent 2): `docs/superpowers/reviews/2026-04-20-comprehensive/search.md`

- [ ] **Step 1: Dispatch both Wave 1 agents in a single message with two parallel `Agent` tool calls**

Call 1 — Connection & Transport (paste the full shared template with the fill-ins below):

```
<AREA> = "Connection & Transport (auth, HTTP client, platform resolution, error surface)"

<SCOPE_PATHS> =
  - src/picsure/_services/connect.py
  - src/picsure/_services/consents.py
  - src/picsure/_transport/client.py
  - src/picsure/_transport/platforms.py
  - src/picsure/_transport/errors.py
  - src/picsure/errors.py

<CONTRACT_PATHS> =
  - /Users/george/code_workspaces/bdc/pic-sure/pic-sure-api-war  (JWTFilter + proxy endpoint)
  - /Users/george/code_workspaces/bdc/pic-sure/pic-sure-resources (if the filter forwards via resource interfaces — glob around)

<METHOD> =
  1. Read every file under SCOPE and describe each module's responsibility in one sentence.
  2. For each outbound HTTP call in _transport/client.py:
     - List the headers attached (Authorization, request-source, Content-Type, Accept, others).
     - Classify auth modes: anonymous vs bearer token. Verify the whitespace-stripping
       rule (whitespace-only token → anonymous).
     - Check error mapping: which transport errors become which PicSureError subclass.
  3. Read the JWTFilter (grep for "JWTFilter", "doFilter", or similar) in
     pic-sure/pic-sure-api-war and verify:
     - Headers the filter expects.
     - How it rewrites/forwards requests to downstream services (HPDS, dictionary).
     - Any header the filter requires but the Python client does not send.
     - Any header the filter rejects or strips but the Python client sends anyway.
  4. Read platform resolution in _transport/platforms.py and verify the mapping
     (BDC Authorized / BDC Open / Demo / AIM-AHEAD) against what the gateway and
     downstream services accept.
  5. Review the public session/connect surface: does PicSureClient/Session correctly
     surface connection failures, auth failures, and stale-token failures with
     actionable messages?

<OUTPUT_PATH> =
  /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/connection-transport.md

<WAVE1_CONTEXT> = (empty — Wave 1 has no prior context)
```

Call 2 — Search (paste the full shared template with the fill-ins below):

```
<AREA> = "Search — cross-stack UI-parity deep-dive against PIC-SURE-Frontend and picsure-dictionary"

<SCOPE_PATHS> =
  - src/picsure/_services/search.py
  - src/picsure/_models/facet.py
  - src/picsure/_models/dictionary.py

<CONTRACT_PATHS> =
  - /Users/george/code_workspaces/bdc/picsure-dictionary/src  (search controller, DTOs, facet handling, pagination)
  - /Users/george/code_workspaces/bdc/PIC-SURE-Frontend/src   (search component + API client; grep for "search", "dictionary", "facet")

ADDITIONAL ARTIFACTS (read verbatim, outside git):
  - /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-request.har
  - /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-response.json

<METHOD> =
  1. Reconstruct UI request from the HAR. Extract the search entry (the one hitting
     /search or /dictionary/concepts or similar). Record as normalized JSON at the top
     of the report:
       {
         "method": "...",
         "url": "...",
         "query_string": {...},
         "headers": {...},   // keep Authorization redacted; keep everything else
         "body": ...
       }
  2. Reconstruct the Python request. Read search.py and derive, for the SAME search
     term and facet selections as the HAR, what request search.py would produce.
     Record it in the same normalized shape.
  3. Produce a diff table:
       | field | UI value | Python value | divergent? | likely impact |
     Include headers, query-string params, body fields, and the URL path itself.
  4. For each divergent row, classify:
       (a) backend accepts both (cosmetic)
       (b) backend accepts UI but not Python (bug)
       (c) backend accepts Python but semantics differ (subtle bug)
     Back each classification with a pointer to the controller / DTO in
     picsure-dictionary (file:line).
  5. Response parsing: compare the captured response JSON to what search.py parses
     into. Check for:
       - Fields the UI uses that Python ignores.
       - Fields Python reads that the response does not include.
       - Dedup logic (by concept path) — does it match what the UI shows?
       - Facet vs result separation — does the Python shape line up with FacetSet?
  6. Search.showAllFacets + Session.facets — do these hit the same endpoint(s) as the
     UI uses when it populates the facet sidebar? Diff the requests if not.

<OUTPUT_PATH> =
  /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/search.md

<WAVE1_CONTEXT> = (empty — Wave 1 has no prior context)

ADDITIONAL REPORT STRUCTURE (goes before "Strengths"):
  ## Captured UI request (verbatim from HAR)
  ## Python-equivalent request (derived from search.py)
  ## Divergence table
  ## Classification notes per divergence
```

Both calls go in a **single** assistant message so they run concurrently.

- [ ] **Step 2: Wait for both agents to return**

Expected: two reports back, each with `Status` and `Summary` and a file at `<OUTPUT_PATH>`.

- [ ] **Step 3: Verify both output files exist and are non-empty**

Run:
```
ls -la /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/
```

Expected: `connection-transport.md` and `search.md` both present and non-empty.

- [ ] **Step 4: If either agent returned NEEDS_CONTEXT, resolve and re-dispatch**

If `NEEDS_CONTEXT`: read the blocker, resolve it (ask the user if needed), re-dispatch only the blocked agent with the additional context appended to `<WAVE1_CONTEXT>`. Repeat until both return DONE or DONE_WITH_CONCERNS.

---

### Task 3: Write the Wave 1 synthesis brief

**Files:**
- Read: `docs/superpowers/reviews/2026-04-20-comprehensive/connection-transport.md`
- Read: `docs/superpowers/reviews/2026-04-20-comprehensive/search.md`

- [ ] **Step 1: Read both Wave 1 review files in full**

Use the Read tool on both files; do not skim.

- [ ] **Step 2: Extract all Critical and Important findings**

For each finding, note: short title, file:line, one-sentence description, which file reported it.

- [ ] **Step 3: Identify likely root causes relevant to Wave 2**

A finding is "root-cause-relevant" if it describes something upstream of query-building, query-execution, or export — e.g., a transport header bug, a request-shape issue, a response-parsing mismatch. Highlight these.

- [ ] **Step 4: Compose the Wave 1 brief as a single in-conversation note**

The brief must contain:
1. **Critical findings from Wave 1** — bullet list with file:line, one line each.
2. **Likely root causes affecting downstream areas** — bullet list with a one-line rationale per item.
3. **Nothing else.** No speculation, no synthesis commentary.

Keep it under 300 words. This exact brief will be pasted into each Wave 2 agent's `<WAVE1_CONTEXT>`.

---

### Task 4: Dispatch Wave 2 — Query building, Query execution, Export, Cross-cutting (parallel)

**Files:**
- Create (by Agent 3): `docs/superpowers/reviews/2026-04-20-comprehensive/query-build.md`
- Create (by Agent 4): `docs/superpowers/reviews/2026-04-20-comprehensive/query-run.md`
- Create (by Agent 5): `docs/superpowers/reviews/2026-04-20-comprehensive/export.md`
- Create (by Agent 6): `docs/superpowers/reviews/2026-04-20-comprehensive/cross-cutting.md`

- [ ] **Step 1: Dispatch all four Wave 2 agents in a single message with four parallel `Agent` tool calls**

Each prompt uses the shared template with `<WAVE1_CONTEXT>` set to:

```
CONTEXT FROM WAVE 1 (for awareness; do not duplicate findings already captured there):
<paste the Wave 1 brief written in Task 3 verbatim>
```

Call 3 — Query building:

```
<AREA> = "Query building — clauses, groups, and the v3 phenotypic schema"

<SCOPE_PATHS> =
  - src/picsure/_services/query_build.py
  - src/picsure/_models/clause.py
  - src/picsure/_models/clause_group.py
  - src/picsure/_models/query.py

<CONTRACT_PATHS> =
  - /Users/george/code_workspaces/bdc/pic-sure-hpds  (grep for "PhenotypicClause", "PhenotypicSubquery", "phenotypicFilterType")

<METHOD> =
  1. Read every file under SCOPE.
  2. For each ClauseType (FILTER, ANYRECORD, SELECT, REQUIRE):
     - Verify the to_query_json() output matches the v3 PhenotypicClause shape
       documented in CHANGELOG.md and implemented in pic-sure-hpds DTOs.
     - Verify input validation: does the adapter reject invalid combinations
       (e.g., SELECT with values, FILTER without min/max) with actionable messages?
  3. For ClauseGroup:
     - Verify GroupOperator (AND/OR) serialization matches the backend's "operator" enum.
     - Verify "not" semantics on both Clause and ClauseGroup.
     - Verify arbitrary nesting is handled correctly.
  4. Verify the SELECT extraction path (select_paths) — SELECT clauses must be
     split out to the top-level "select" list, never appear inside phenotypicClause.
     Does to_query_json() raise PicSureValidationError on SELECT at the wrong layer?
  5. Check enum correctness: ClauseType and GroupOperator values match what the
     backend expects verbatim (case-sensitive).

<OUTPUT_PATH> =
  /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/query-build.md
```

Call 4 — Query execution & results:

```
<AREA> = "Query execution — sync endpoint, count parsing, cross_count, DataFrame results"

<SCOPE_PATHS> =
  - src/picsure/_services/query_run.py
  - src/picsure/_models/count_result.py

<CONTRACT_PATHS> =
  - /Users/george/code_workspaces/bdc/pic-sure-hpds  (grep for "/query/sync", "ResultType", "COUNT", "CROSS_COUNT", "DATAFRAME")

<METHOD> =
  1. Read every file under SCOPE.
  2. Verify the request body shape against /picsure/v3/query/sync:
     - "query" envelope: select, phenotypicClause, genomicFilters, expectedResultType,
       picsureId, id.
     - "resourceUUID" at the top level.
     - "authorizationFilters" intentionally omitted — verify pic-sure-hpds does not
       reject requests that lack it.
  3. Count-string regex coverage — _COUNT_EXACT, _COUNT_NOISY, _COUNT_SUPPRESSED:
     - Enumerate every count format pic-sure-hpds emits. If any format is not matched
       by the regexes, that is a Critical finding.
     - Verify CountResult fields (value, margin, cap, raw, obfuscated) cover every
       shape without loss.
  4. cross_count:
     - Verify the assumption that every value in the JSON object is a count string.
     - Verify concept-path keys are passed through unmodified.
  5. DataFrame parsing (participant, timestamp):
     - Verify CSV framing assumptions match what the backend emits.
     - Verify empty-response handling (empty DataFrame vs. error).
     - Verify column / dtype expectations against the backend's CSV emitter.
  6. Query type mapping (count → COUNT, etc.) — verify backend accepts each
     expectedResultType string verbatim.
  7. Error handling — TransportError → PicSureConnectionError; malformed responses →
     PicSureQueryError. Is the error message actionable?

<OUTPUT_PATH> =
  /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/query-run.md
```

Call 5 — Export:

```
<AREA> = "Export — PFB, CSV, TSV writers"

<SCOPE_PATHS> =
  - src/picsure/_services/export.py

<CONTRACT_PATHS> =
  - /Users/george/code_workspaces/bdc/pic-sure/pic-sure-api-war  (grep for "pfb", "export")
  - /Users/george/code_workspaces/bdc/pic-sure-hpds             (grep for "pfb", "export")

<METHOD> =
  1. Read export.py in full.
  2. Verify the PFB export endpoint path and method against pic-sure / pic-sure-hpds.
  3. Streaming / IO semantics:
     - Is the response read into memory, or streamed to disk?
     - Is the file handle closed on error paths?
  4. CSV / TSV writer:
     - Verify default pandas writer options (index=False? header=True? separator?).
     - Verify filename / extension handling (does the function trust the caller's
       extension or enforce one?).
  5. Error handling on export failures (disk full, permission denied, network
     interruption mid-stream). Do errors surface as actionable PicSureError subclasses
     or raw OS errors?

<OUTPUT_PATH> =
  /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/export.md
```

Call 6 — Cross-cutting:

```
<AREA> = "Cross-cutting — tests, CI, docs, packaging, public surface"

<SCOPE_PATHS> =
  - tests/ (entire directory)
  - .github/workflows/ (entire directory)
  - docs/ (entire directory — but NOT docs/superpowers/reviews/)
  - pyproject.toml
  - CHANGELOG.md
  - src/picsure/__init__.py

<CONTRACT_PATHS> =
  (none — this agent reviews only this repo)

<METHOD> =
  1. Test coverage:
     - Which modules under src/picsure/ have tests? Which don't?
     - For each test file, do the tests verify behavior or only verify mocked
       behavior (respx, etc. returning exactly the canned response)?
     - Are edge cases covered for count parsing, clause validation, HTTP error paths?
  2. CI health:
     - Read .github/workflows/ and verify the Python 3.10/3.11/3.12 matrix is wired.
     - Are tests, lint, and docs all gated?
  3. Docs:
     - Read docs/ (guides + reference). For each guide page, spot-check that examples
       match the current public surface (function names, arg order, return types).
     - Verify mkdocstrings-generated reference is up to date vs. docstrings.
  4. CHANGELOG:
     - For each line under ## [Unreleased], verify a corresponding symbol / behavior
       exists in the code. Flag any claim that is inaccurate.
  5. Public surface:
     - List every symbol exported by src/picsure/__init__.py.
     - Cross-reference with docs/reference/ — flag anything exported but undocumented,
       or documented but not exported.
  6. Packaging:
     - Verify pyproject.toml version, dependencies, and python_requires are consistent.
     - Flag any dependency pinned loosely enough to cause drift.

<OUTPUT_PATH> =
  /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/cross-cutting.md
```

All four calls go in a **single** assistant message so they run concurrently.

- [ ] **Step 2: Wait for all four agents to return**

Expected: four reports back, each with `Status` and `Summary` and a file at `<OUTPUT_PATH>`.

- [ ] **Step 3: Verify all four output files exist and are non-empty**

Run:
```
ls -la /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/
```

Expected: six files total — two from Wave 1 plus `query-build.md`, `query-run.md`, `export.md`, `cross-cutting.md`.

- [ ] **Step 4: If any agent returned NEEDS_CONTEXT, resolve and re-dispatch only the blocked agent**

Same loop as Task 2 Step 4.

---

### Task 5: Synthesize `index.md`

**Files:**
- Read: all six area files under `docs/superpowers/reviews/2026-04-20-comprehensive/`
- Create: `docs/superpowers/reviews/2026-04-20-comprehensive/index.md`

- [ ] **Step 1: Read all six area files in full**

Use the Read tool on each. Do not skim.

- [ ] **Step 2: Extract every finding into a flat list**

For each finding across all files, record: `{severity, short title, file:line, source_review_file, one-line summary}`.

- [ ] **Step 3: Identify and cross-link duplicates**

Two findings are duplicates if they describe the same underlying issue (even under different framings). For duplicates: pick the most complete one as canonical; note the duplicate in the canonical entry; mention in each duplicate's entry "see also: <canonical>".

- [ ] **Step 4: Write `index.md` with the following structure**

```markdown
# Comprehensive Code Review — 2026-04-20

**Target:** pic-sure-python-adapter-hpds
**Commit reviewed:** <HEAD_SHA from Task 1 Step 5>
**Areas:** Connection & Transport • Search • Query building • Query execution • Export • Cross-cutting
**Trigger:** Search results produced by the Python adapter do not match PIC-SURE-Frontend for equivalent inputs.

## Executive summary

(3-5 sentences. Lead with the search-parity finding if one exists. Name the top 2-3 other critical/important issues. No prose beyond what the reader needs.)

## Findings by severity

### Critical
- **<title>** (`file:line`) — one-sentence summary. → [full entry](<review-file>.md#<anchor-if-available>)

### Important
(Same format.)

### Minor
(Same format — can be grouped more loosely.)

## Cross-links (duplicates across files)

- `<canonical finding title>` appears in:
  - `search.md` — <how framed there>
  - `connection-transport.md` — <how framed there>
  (...etc.)

## Area summaries

(One short paragraph per area file — 2-3 sentences each, just enough to orient the reader. Link to the full file.)

- **[Connection & Transport](connection-transport.md)** — <paragraph>
- **[Search](search.md)** — <paragraph>
- **[Query building](query-build.md)** — <paragraph>
- **[Query execution](query-run.md)** — <paragraph>
- **[Export](export.md)** — <paragraph>
- **[Cross-cutting](cross-cutting.md)** — <paragraph>

## Recommended next actions

(Bulleted short list — NOT a TODO checklist. Items are decisions to make, not tasks to execute. Example: "Decide whether to adopt the UI's search request shape as the canonical form, or have the UI adopt the Python adapter's shape." Triage and follow-up tasks are a separate step the user initiates after reading this index.)
```

- [ ] **Step 5: Verify `index.md` references only real files, real paths, and real findings**

Run:
```
grep -oE "\[.+\]\([^)]+\)" /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items/docs/superpowers/reviews/2026-04-20-comprehensive/index.md
```

Manually check each link target exists. Re-read each `file:line` citation against the source repo; if any cite is wrong, fix it in `index.md` (not in the area file — area files are the agents' work product).

---

### Task 6: Commit all review output

**Files:**
- Add: everything under `docs/superpowers/reviews/2026-04-20-comprehensive/`

- [ ] **Step 1: Stage the review directory**

Run:
```
git -C /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items add docs/superpowers/reviews/2026-04-20-comprehensive/
```

- [ ] **Step 2: Verify staged contents**

Run:
```
git -C /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items status --short
```

Expected: exactly seven new files — `index.md` plus the six area files — and nothing else.

- [ ] **Step 3: Commit**

Run:
```
git -C /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items commit -m "$(cat <<'EOF'
docs: add comprehensive code review 2026-04-20

Six-area review executed via parallel sub-agents (two waves):
  - Wave 1: Connection & Transport, Search (cross-stack UI-parity diff)
  - Wave 2: Query building, Query execution, Export, Cross-cutting

Spec: docs/superpowers/specs/2026-04-20-comprehensive-code-review-design.md
Findings: docs/superpowers/reviews/2026-04-20-comprehensive/index.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify the commit landed**

Run:
```
git -C /Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items log -1 --stat
```

Expected: commit shown with seven files changed.

- [ ] **Step 5: Report completion to the user**

Report:
- Path to `index.md`.
- Count of findings by severity (total Critical / Important / Minor).
- Whether the search-vs-UI divergence was identified (yes / no / partial), with a one-line answer.
- Explicit note: no source under `src/` was modified. Triage is a separate step.
