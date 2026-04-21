# Comprehensive Code Review — Design Spec

**Date:** 2026-04-20
**Target repo:** `pic-sure-python-adapter-hpds`
**Trigger:** Search results produced by this Python adapter do not match the results produced by `PIC-SURE-Frontend` for equivalent inputs; the two should be 1:1. A broader review of connection, query construction, query execution, export, and cross-cutting concerns is warranted at the same time.

---

## Goal

Produce a comprehensive, area-by-area code review of `pic-sure-python-adapter-hpds` executed by six parallel sub-agents. Each area gets its own review file with findings at `file:line` precision. An index synthesizes across all areas and ranks findings by severity. **No source code is modified as part of this review** — triage and fixes are a separate step initiated after the user reads the index.

---

## Scope

### Review boundary

| Area | Boundary |
|---|---|
| Search (Agent 2) | **Full cross-stack.** Reviewer reads this repo + `picsure-dictionary` backend + `PIC-SURE-Frontend` UI, and byte-diffs a captured UI request against what the Python adapter would send. |
| Everything else (Agents 1, 3, 4, 5, 6) | **Python + contract cross-check.** Reviewer reads this repo plus the relevant Java contract in `pic-sure` / `pic-sure-hpds` / `picsure-dictionary` as needed to verify wire shape. UI comparison is not required. |

### Absolute paths to sibling repos (for sub-agent prompts)

- This repo (worktree): `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/.claude/worktrees/fix-code-review-items`
- `/Users/george/code_workspaces/bdc/pic-sure`
- `/Users/george/code_workspaces/bdc/pic-sure-hpds`
- `/Users/george/code_workspaces/bdc/picsure-dictionary`
- `/Users/george/code_workspaces/bdc/PIC-SURE-Frontend`

### Pre-flight artifacts (provided by user, outside git)

- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-request.har`
- `/Users/george/code_workspaces/bdc/pic-sure-python-adapter-hpds/artifacts/ui-search-response.json`

These are referenced by absolute path and are not committed.

---

## Deliverables

All review output lives under the worktree at:

```
docs/superpowers/reviews/2026-04-20-comprehensive/
├── index.md                    # Severity-ranked synthesis + cross-links
├── connection-transport.md     # Agent 1
├── search.md                   # Agent 2
├── query-build.md              # Agent 3
├── query-run.md                # Agent 4
├── export.md                   # Agent 5
└── cross-cutting.md            # Agent 6
```

**Per-area file template** (every agent uses it):

1. **Scope** — files read, contracts consulted.
2. **Strengths** — what's well-built.
3. **Issues** — grouped by severity (Critical / Important / Minor), each with `file:line` and a one-line explanation.
4. **Verification evidence** — what the agent ran, read, or diffed to reach each finding.

**`index.md`** is written by the controller (not by a sub-agent) after all six files exist. It:

- Ranks every finding across every file by severity.
- Cross-links duplicate or related findings between files.
- Ends with a short "Recommended next actions" list — *not* a TODO checklist; triage is a separate step.

---

## Sub-agent roster

Every agent runs with subagent_type `general-purpose` (read-only work; `Explore` is acceptable if the agent only needs Glob/Grep/Read).

### Agent 1 — Connection & Transport

- **In scope:** `src/picsure/_services/connect.py`, `src/picsure/_services/consents.py`, `src/picsure/_transport/client.py`, `src/picsure/_transport/platforms.py`, `src/picsure/_transport/errors.py`, `src/picsure/errors.py`.
- **Contract cross-check:** `pic-sure/pic-sure-api-war` — JWTFilter and proxy endpoint. Verify:
  - Headers the filter expects (`Authorization`, `request-source`) and how the filter rewrites them before forwarding.
  - Anonymous vs. bearer-token modes and whitespace rules on the token.
  - Platform resolution (BDC Authorized / BDC Open / Demo / AIM-AHEAD) vs. what the gateway expects.
  - Error surface: which upstream statuses map to which `PicSureError` subclass.
- **Output:** `connection-transport.md`.

### Agent 2 — Search (UI-parity deep-dive)

- **In scope:** `src/picsure/_services/search.py`, `src/picsure/_models/facet.py`, `src/picsure/_models/dictionary.py`.
- **Cross-stack verification:**
  1. Read `picsure-dictionary/src` — search controller, request/response DTOs, facet handling, pagination.
  2. Read `PIC-SURE-Frontend/src` — the search component(s) and API client that issue the equivalent call.
  3. Byte-diff the captured UI request in `artifacts/ui-search-request.har` against what `search.py` would send for the same inputs.
- **Method (enforced in the prompt):**
  1. **Reconstruct UI request** from the HAR: URL path, method, headers, query string, body. Record as normalized JSON in the report.
  2. **Reconstruct Python request** from `search.py` for the same search term + facets. Record in the same normalized shape.
  3. **Diff table** — `field | UI value | Python value | divergent? | likely impact`.
  4. **Backend verification** — for each divergence, classify: (a) backend accepts both (cosmetic), (b) backend accepts UI but not Python (bug), (c) backend accepts Python but semantics differ (subtle bug).
  5. **Response parsing** — compare captured response to what `search.py` parses. Check for fields the UI uses that Python ignores (or vice versa), dedup logic, facet-vs-result handling.
- **Output:** `search.md` with the diff table up front, classification per row, then standard sections.
- **Escalation:** if the HAR is malformed, under-specified, or the `picsure-dictionary` contract is ambiguous, the agent stops and reports `NEEDS_CONTEXT` with a specific question rather than guessing.

### Agent 3 — Query building

- **In scope:** `src/picsure/_services/query_build.py`, `src/picsure/_models/clause.py`, `src/picsure/_models/clause_group.py`, `src/picsure/_models/query.py`.
- **Contract cross-check:** `pic-sure-hpds` query DTOs for v3 `PhenotypicClause` / `PhenotypicSubquery`. Verify SELECT extraction, `not` semantics on both clauses and groups, enum correctness (`ClauseType`, `GroupOperator`), and whether validation error coverage matches what the backend rejects.
- **Output:** `query-build.md`.

### Agent 4 — Query execution & results

- **In scope:** `src/picsure/_services/query_run.py`, `src/picsure/_models/count_result.py`.
- **Contract cross-check:** `pic-sure-hpds` sync query endpoint response shapes. Verify:
  - Request body shape against `/picsure/v3/query/sync`.
  - Count-string regex coverage for the three known formats (`42`, `11309 ±3`, `< 10`) and whether any shape the backend emits is unrecognized.
  - `cross_count` JSON object handling and the assumption that every value is a count string.
  - DataFrame parsing — CSV framing, empty-response handling, column/type expectations.
  - Query type mapping (`count` → `COUNT`, etc.) vs. what the backend accepts.
- **Output:** `query-run.md`.

### Agent 5 — Export

- **In scope:** `src/picsure/_services/export.py`.
- **Contract cross-check:** PFB export endpoint on the API gateway. Verify streaming/IO semantics, file-handle lifecycle, and CSV/TSV writer correctness against pandas defaults.
- **Output:** `export.md`.

### Agent 6 — Cross-cutting

- **In scope:** `tests/`, `.github/workflows/`, `docs/`, `pyproject.toml`, `CHANGELOG.md`, `src/picsure/__init__.py`.
- **Checks:**
  - Test coverage per module (what's tested, what isn't, meaningful vs. mock-only).
  - CI health across the 3.10/3.11/3.12 matrix.
  - Docstring-vs-docs drift (mkdocstrings-generated reference vs. actual signatures).
  - `CHANGELOG.md [Unreleased]` accuracy vs. actual public surface.
  - Whether any symbol is exported in `__init__.py` but undocumented (or vice versa).
- **Output:** `cross-cutting.md`.

---

## Sequencing

Two waves. Wave 1 runs to completion regardless of what it finds; no early stop.

### Pre-flight (human)

1. User captures a UI search request via browser devtools and saves HAR + response JSON at the absolute paths above. (Already done for this run.)
2. Controller verifies both files exist and are non-empty before Wave 1 dispatch.

### Wave 1 — wire-contract agents (parallel)

Dispatched in a single message with two `Agent` tool calls:

- Agent 1 (Connection & Transport)
- Agent 2 (Search)

Rationale: these two are the most likely to converge on a shared root cause (headers, auth, request shape). Running them together surfaces overlap early and gives Wave 2 useful context.

### Between waves

Controller reads both Wave 1 review files and writes a concise "Wave 1 findings" brief in the conversation — highlights anything that is likely a root cause affecting downstream agents (e.g., a transport-level header bug that would also show up in query execution).

### Wave 2 — downstream agents (parallel)

Dispatched in a single message with four `Agent` tool calls. Each agent's prompt includes the Wave 1 brief as additional context so it can recognize duplicate findings:

- Agent 3 (Query building)
- Agent 4 (Query execution & results)
- Agent 5 (Export)
- Agent 6 (Cross-cutting)

### Synthesis

After Wave 2 returns, controller:

1. Reads all six area files.
2. Writes `index.md` with severity-ranked findings, cross-links between files, and "Recommended next actions."
3. Commits the entire `docs/superpowers/reviews/2026-04-20-comprehensive/` directory as one commit.

---

## Execution mechanics

### Sub-agent prompt skeleton (same structure for all six)

```
You are reviewing <area>. Do NOT modify source code — review only.

SCOPE (files you MUST read):
  <list of absolute paths>

CONTRACT REFERENCES (read as needed):
  <absolute paths into sibling repos, if any>

YOUR TASK:
  1. Understand the code's intent.
  2. Verify against the referenced contract(s).
  3. Classify findings: Critical / Important / Minor.
  4. Cite file:line for every finding.

OUTPUT:
  Write your review to <absolute path into docs/superpowers/reviews/...>.
  Use this template: Scope / Strengths / Issues (by severity with file:line) /
  Verification evidence.

ESCALATION:
  If you cannot proceed (missing file, ambiguous contract, etc.), STOP and report
  NEEDS_CONTEXT with the specific blocker rather than guessing.

REPORT BACK:
  Status (DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT) + 3-5 sentence summary of
  top findings. The full review lives in the file you wrote.
```

### Severity rubric (identical for all agents)

- **Critical** — wrong-on-the-wire, data corruption, security issue, crashes on normal inputs, public API contract broken.
- **Important** — incorrect behavior under real-world inputs, misleading errors, missing tests for non-trivial logic, docs that would lead a user astray.
- **Minor** — naming, small duplication, stylistic drift, non-actionable observations.

### Out of scope (explicit non-goals)

- Fixing findings. Triage and fixes happen after the user reads `index.md`.
- Modifying any source file under `src/`.
- Running the adapter against a live backend.
- Modifying tests other than to note gaps.
- Reviewing sibling repos for their own internal quality — they are consulted only as contracts.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| HAR file is from a different search than we think, producing a misleading diff. | Agent 2 records the URL, query string, and body of the captured request verbatim at the top of `search.md` so the reader can confirm it matches their mental model. |
| Two agents report the same root cause under different framings, inflating the apparent issue count. | Cross-linking in `index.md`; controller explicitly dedupes at synthesis time. |
| An agent's `DONE_WITH_CONCERNS` is ignored and treated as `DONE`. | Controller reads every agent's status line before writing `index.md`; any concern is surfaced in the synthesis. |
| Sibling-repo paths change (e.g., someone renames `pic-sure-api-war`). | Agents are instructed to Glob/Grep for the expected controller/filter class names before hard-depending on paths; failure → `NEEDS_CONTEXT`. |

---

## Success criteria

1. Six review files exist under `docs/superpowers/reviews/2026-04-20-comprehensive/` using the shared template.
2. Every Issue has a `file:line` citation.
3. Agent 2's `search.md` contains a concrete, classified diff between the UI request and the Python request — sufficient to locate the search-vs-UI divergence without further investigation.
4. `index.md` exists and ranks all findings across all files.
5. No source file under `src/` was modified by this review.
