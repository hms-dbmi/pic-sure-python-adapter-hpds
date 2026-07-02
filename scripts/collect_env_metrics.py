"""Collect per-route latency metrics against a live PIC-SURE deployment.

Exercises the adapter's route surface (connect/PSAMA, dictionary search,
facets, sync queries, optional participant export and genomic count) N times
each, then aggregates the transport-level dev-mode events into per-route
p50/p95/p99. Failed calls are excluded from percentiles and reported as an
error count per route, so a bad token or an undeployed endpoint can't fake
fast numbers.

Timing is measured inside the adapter's transport, around the actual HTTP
exchange (retries recorded separately) — it excludes pandas parsing and
result post-processing, so numbers are comparable across result types and
across environments.

Configuration mirrors tests/integration (env vars, .env at the repo root,
shell exports win); CLI flags override both. Requires a token — every
supported deployment gates most of this surface behind auth.

Usage:
    uv run python scripts/collect_env_metrics.py --label wildfly-direct
    uv run python scripts/collect_env_metrics.py \
        --platform https://my-env.example.com --n 50 --heavy

Against a local all-in-one with a mkcert certificate, export the CA first
(httpx trusts certifi, not the macOS keychain):
    export SSL_CERT_FILE="$(mkcert -CAROOT)/rootCA.pem"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# A full run is hundreds of HTTP events; the default buffer (1000) can wrap
# and silently drop the earliest samples. Must be set before connect().
os.environ.setdefault("PICSURE_DEV_MAX_EVENTS", "100000")

import pandas as pd
from dotenv import load_dotenv

import picsure
from picsure import PhenotypicFilterType, buildClause, buildGenomicFilter, buildQuery

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# Same nearest-rank formula as pic-sure-all-in-one/baseline-metrics/
# run-baseline.sh, so numbers are directly comparable across the two suites.
_QUANTILES = (0.50, 0.95, 0.99)

_SUMMARY_COLS = [
    "action",
    "route",
    "samples",
    "errors",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "mean_ms",
    "min_ms",
    "max_ms",
]


def _normalize_route(path: str) -> str:
    """Collapse per-request identifiers so samples group by route."""
    return _UUID_RE.sub("{uuid}", path)


def _nearest_rank(sorted_ms: list[float], q: float) -> float:
    return sorted_ms[int(q * (len(sorted_ms) - 1))]


def _resolve_platform(raw: str) -> picsure.Platform | str:
    by_name = {p.name: p for p in picsure.Platform}
    return by_name.get(raw.upper(), raw)


def _connect(args: argparse.Namespace, *, genomic: bool = False) -> picsure.Session:
    return picsure.connect(
        platform=_resolve_platform(args.platform),
        token=args.token,
        resource_uuid=args.resource_uuid or None,
        supports_genomic=genomic or None,
        dev_mode=True,
    )


def _drain(session: picsure.Session, action: str, sink: list[pd.DataFrame]) -> None:
    events = session.dev_events()
    if not events.empty:
        events = events.copy()
        events["action"] = action
        sink.append(events)
    session.dev_clear()


def _run_action(
    name: str,
    call: Callable[[], object],
    n: int,
    warmup: int,
) -> int:
    """Run one action warmup+n times; return how many iterations raised."""
    failures = 0
    for i in range(warmup + n):
        try:
            call()
        except Exception as exc:  # noqa: BLE001 — keep measuring other routes
            failures += 1
            if i == 0:
                print(f"   {name}: first call failed — {exc}", file=sys.stderr)
    if failures:
        print(f"   {name}: {failures}/{warmup + n} calls failed", file=sys.stderr)
    return failures


def _summarize(events: pd.DataFrame, warmup: int) -> pd.DataFrame:
    """Aggregate raw dev events into one row per (action, route).

    ``http`` events are successful exchanges; ``error`` events carry the
    route in ``name`` too and are counted but never enter the percentiles.
    Per group, the first ``warmup`` successful samples are discarded to
    mirror the curl suite's warmup discipline.
    """
    frame = events[events["kind"].isin(["http", "error"])].copy()
    frame["route"] = frame["name"].map(_normalize_route)
    rows: list[dict[str, Any]] = []
    for (action, route), batch in frame.groupby(["action", "route"]):
        ok = batch[batch["kind"] == "http"]["duration_ms"].tolist()[warmup:]
        errors = int((batch["kind"] == "error").sum())
        row: dict[str, Any] = {
            "action": action,
            "route": route,
            "samples": len(ok),
            "errors": errors,
        }
        if ok:
            ok.sort()
            row.update(
                {
                    f"p{int(q * 100)}_ms": round(_nearest_rank(ok, q), 1)
                    for q in _QUANTILES
                }
            )
            row["mean_ms"] = round(sum(ok) / len(ok), 1)
            row["min_ms"] = round(ok[0], 1)
            row["max_ms"] = round(ok[-1], 1)
        rows.append(row)
    return (
        pd.DataFrame(rows, columns=_SUMMARY_COLS)
        .sort_values(["action", "route"])
        .reset_index(drop=True)
    )


def _to_markdown_table(summary: pd.DataFrame) -> str:
    """Render the summary as a GitHub-flavored markdown table.

    Hand-rolled because ``DataFrame.to_markdown`` needs tabulate, which is
    not a project dependency.
    """
    header = "| " + " | ".join(_SUMMARY_COLS) + " |"
    divider = "|" + "|".join("---" for _ in _SUMMARY_COLS) + "|"
    lines = [header, divider]
    for _, row in summary.iterrows():
        cells = ["" if pd.isna(row[c]) else str(row[c]) for c in _SUMMARY_COLS]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _write_outputs(
    out_dir: Path,
    summary: pd.DataFrame,
    raw: pd.DataFrame,
    meta: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw.to_csv(out_dir / "events.csv", index=False)
    summary.to_json(out_dir / "summary.json", orient="records", indent=2)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    lines = [
        f"# Route latency — {meta['label']}",
        "",
        f"- date: {meta['stamp']}  |  platform: {meta['platform']}  |  "
        f"n={meta['n']} per action (warmup {meta['warmup']}, sequential)",
        "- timing: adapter transport (per HTTP exchange; errors excluded "
        "from percentiles, counted separately)",
        "",
        _to_markdown_table(summary),
        "",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--platform",
        default=os.environ.get("PICSURE_TEST_PLATFORM", ""),
        help="Platform enum name or base URL (PICSURE_TEST_PLATFORM)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("PICSURE_TEST_TOKEN", ""),
        help="PIC-SURE token (PICSURE_TEST_TOKEN)",
    )
    parser.add_argument(
        "--token-file",
        default="",
        help="Read the token from a file instead (e.g. notebooks/token.txt)",
    )
    parser.add_argument(
        "--resource-uuid",
        default=os.environ.get("PICSURE_TEST_RESOURCE_UUID", ""),
        help="Resource UUID when the deployment has more than one resource",
    )
    parser.add_argument(
        "--concept-path",
        default=os.environ.get("PICSURE_TEST_CONCEPT_PATH", ""),
        help="Concept path for query actions (PICSURE_TEST_CONCEPT_PATH)",
    )
    parser.add_argument(
        "--search-term",
        default=os.environ.get("PICSURE_TEST_SEARCH_TERM", "age"),
        help="Dictionary search term (PICSURE_TEST_SEARCH_TERM)",
    )
    parser.add_argument(
        "--gene",
        default=os.environ.get("PICSURE_TEST_GENE", ""),
        help="Gene symbol; enables the genomic count action (PICSURE_TEST_GENE)",
    )
    parser.add_argument("--n", type=int, default=int(os.environ.get("METRICS_N", 30)))
    parser.add_argument(
        "--warmup", type=int, default=int(os.environ.get("METRICS_WARMUP", 3))
    )
    parser.add_argument(
        "--label",
        default=os.environ.get("METRICS_LABEL", "env"),
        help="Run label baked into the results dir name (e.g. via-gateway)",
    )
    parser.add_argument(
        "--out",
        default=os.environ.get("METRICS_OUT", str(_REPO_ROOT / "metrics-results")),
        help="Results root directory",
    )
    parser.add_argument(
        "--heavy",
        action="store_true",
        help="Also run the participant DATAFRAME action (moves real data)",
    )
    args = parser.parse_args()

    if args.token_file:
        args.token = Path(args.token_file).read_text().strip()
    if not args.platform:
        parser.error("--platform (or PICSURE_TEST_PLATFORM) is required")
    if not args.token:
        parser.error("--token / --token-file (or PICSURE_TEST_TOKEN) is required")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / f"{stamp}-{args.label}"
    print(f"== PIC-SURE route metrics == label={args.label} platform={args.platform}")
    print(f"n={args.n} warmup={args.warmup} -> {out_dir}")

    frames: list[pd.DataFrame] = []

    # connect() itself is the auth-path probe: each iteration exercises
    # /psama/user/me and /picsure/info/resources on a fresh session.
    print("-- connect (PSAMA profile + resource listing)")

    def do_connect() -> None:
        s = _connect(args)
        _drain(s, "connect", frames)
        s.close()

    _run_action("connect", do_connect, args.n, args.warmup)

    try:
        session = _connect(args)
    except Exception as exc:  # noqa: BLE001
        print(
            f"ERROR: could not establish the measurement session — {exc}",
            file=sys.stderr,
        )
        session = None
    if session is not None:
        session.dev_clear()  # connect events already measured above
        _run_session_actions(session, args, frames)
        session.close()

    if args.gene:
        print("-- genomic gene-filter count")
        try:
            gsession = _connect(args, genomic=True)
        except Exception as exc:  # noqa: BLE001
            print(f"   genomic connect failed — {exc}", file=sys.stderr)
            gsession = None
        if gsession is not None:
            gsession.dev_clear()
            gq = buildQuery(
                genomicFilters=buildGenomicFilter(
                    "Gene_with_variant", values=[args.gene]
                )
            )
            _run_action(
                "genomic-count",
                lambda: gsession.runQuery(gq, type="count"),
                args.n,
                args.warmup,
            )
            _drain(gsession, "genomic-count", frames)
            gsession.close()

    if not frames:
        print("ERROR: no events captured — every action failed?", file=sys.stderr)
        return 1

    raw = pd.concat(frames, ignore_index=True)
    summary = _summarize(raw, args.warmup)
    meta = {
        "stamp": stamp,
        "label": args.label,
        "platform": str(args.platform),
        "n": args.n,
        "warmup": args.warmup,
        "heavy": args.heavy,
    }
    _write_outputs(out_dir, summary, raw, meta)

    print()
    print(summary.to_string(index=False))
    print(f"\n== Done. Results: {out_dir} ==")
    total_errors = int(summary["errors"].sum())
    if total_errors:
        print(f"WARNING: {total_errors} failed calls — see events.csv", file=sys.stderr)
    return 0


def _run_session_actions(
    session: picsure.Session, args: argparse.Namespace, frames: list[pd.DataFrame]
) -> None:
    print("-- dictionary search + facets")
    _run_action(
        "search",
        lambda: session.searchDictionary(args.search_term),
        args.n,
        args.warmup,
    )
    _drain(session, "search", frames)
    _run_action("facets", lambda: session.facets(), args.n, args.warmup)
    _drain(session, "facets", frames)

    if args.concept_path:
        clause = buildClause(args.concept_path, type=PhenotypicFilterType.REQUIRE)

        print("-- count query (deployment-default sync path)")
        _run_action(
            "count", lambda: session.runQuery(clause, type="count"), args.n, args.warmup
        )
        _drain(session, "count", frames)

        # Measure the *other* sync endpoint too: the strangler-fig phases move
        # legacy and v3 at different times, so both need baselines. The flag is
        # private Session state — flipped deliberately here, restored after.
        original = session._use_legacy_query_path
        session._use_legacy_query_path = not original
        which = "legacy" if not original else "v3"
        print(f"-- count query (alternate sync path: {which})")
        _run_action(
            f"count-{which}",
            lambda: session.runQuery(clause, type="count"),
            args.n,
            args.warmup,
        )
        session._use_legacy_query_path = original
        _drain(session, f"count-{which}", frames)

        if args.heavy:
            print("-- participant dataframe (heavy)")
            _run_action(
                "participant",
                lambda: session.runQuery(clause, type="participant"),
                max(args.n // 3, 3),
                args.warmup,
            )
            _drain(session, "participant", frames)
    else:
        print("NOTE: no concept path set — skipping query actions.")


if __name__ == "__main__":
    raise SystemExit(main())
