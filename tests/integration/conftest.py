from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from picsure._transport.platforms import Platform

# Load a .env file at the repo root if present, so developers can keep
# their integration-test token there instead of exporting it. Shell-
# exported vars still win (override=False).
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env", override=False)

_INTEGRATION_DIR = Path(__file__).resolve().parent

_TOKEN_PLACEHOLDER = "<PICSURE_TEST_TOKEN redacted>"


class OpaqueToken:
    """A bearer token that refuses to render itself.

    pytest reports a failing test by ``saferepr``-ing every fixture value into
    the failure header, so a fixture returning the token as a plain ``str``
    prints token material on any failure in any test that takes it. Wrapping
    it keeps the value out of failure headers, assertion diffs,
    ``--showlocals`` dumps and f-strings.

    The wrapper is deliberately not a ``str`` subclass: a subclass would keep
    working everywhere a token string is expected, which is exactly what makes
    an accidental interpolation silent. Call :meth:`reveal` at the point the
    token is handed to the library, and nowhere else.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """Return the raw token string.

        Call this only where the token is handed to the library, so the value
        never lives in a test-local variable that a traceback could dump.
        """
        return self._value

    def __repr__(self) -> str:
        return _TOKEN_PLACEHOLDER

    def __str__(self) -> str:
        return _TOKEN_PLACEHOLDER

    def __format__(self, format_spec: str) -> str:
        return _TOKEN_PLACEHOLDER

    def __bool__(self) -> bool:
        return bool(self._value)

    def __getattr__(self, name: str) -> object:
        raise AttributeError(
            f"{type(self).__name__} has no attribute {name!r}: it is not a str. "
            "Call .reveal() where the token is passed to the library, e.g. "
            "picsure.connect(platform=test_platform, token=test_token.reveal())."
        )


PICSURE_INTEGRATION = os.environ.get("PICSURE_INTEGRATION", "0") == "1"
PICSURE_TEST_TOKEN = OpaqueToken(os.environ.get("PICSURE_TEST_TOKEN", ""))
PICSURE_TEST_PLATFORM = os.environ.get("PICSURE_TEST_PLATFORM", "")
PICSURE_TEST_CONCEPT_PATH = os.environ.get("PICSURE_TEST_CONCEPT_PATH", "")
PICSURE_TEST_SEARCH_TERM = os.environ.get("PICSURE_TEST_SEARCH_TERM", "age")
PICSURE_TEST_GENE = os.environ.get("PICSURE_TEST_GENE", "")

_PLATFORM_BY_NAME = {p.name: p for p in Platform}

_OPTIONAL_ENV_COVERAGE = {
    "PICSURE_TEST_CONCEPT_PATH": "query and export live tests",
    "PICSURE_TEST_GENE": "genomic live tests",
}

_SKIPPED_INTEGRATION_DISABLED = (
    "Integration tests disabled. Set PICSURE_INTEGRATION=1 to run."
)

_SKIPPED_PLATFORM_UNSET = (
    "PICSURE_TEST_PLATFORM is not set, so there is no deployment to test "
    "against. Set it to a Platform enum name (BDC_AUTHORIZED, BDC_OPEN, "
    "BDC_DEV_AUTHORIZED, BDC_DEV_OPEN, BDC_PREDEV_AUTHORIZED, "
    "BDC_PREDEV_OPEN, NHANES_AUTHORIZED, NHANES_OPEN) or a full "
    "https:// URL, plus PICSURE_TEST_TOKEN for an authorized platform. "
    "See .env.example."
)

_SKIPPED_PLATFORM_UNRECOGNIZED = (
    "PICSURE_TEST_PLATFORM={value!r} is neither a Platform enum name nor an "
    "http(s):// URL, so platform resolution cannot succeed. Set it to one of "
    "{names} or to a full https:// URL. See .env.example."
)

_SKIPPED_TOKEN_UNSET = (
    "PICSURE_TEST_TOKEN is not set and PICSURE_TEST_PLATFORM={value!r} "
    "requires a token. Set PICSURE_TEST_TOKEN, or point "
    "PICSURE_TEST_PLATFORM at an open-access platform (e.g. BDC_OPEN). "
    "See .env.example."
)

_MIN_LEAKED_RUN = 12


def _token_grams() -> frozenset[str]:
    raw = PICSURE_TEST_TOKEN.reveal()
    if len(raw) < _MIN_LEAKED_RUN:
        return frozenset()
    return frozenset(
        raw[index : index + _MIN_LEAKED_RUN]
        for index in range(len(raw) - _MIN_LEAKED_RUN + 1)
    )


_TOKEN_GRAMS = _token_grams()


def scrub_token(text: str) -> str:
    """Replace any run of token characters in ``text`` with the placeholder.

    :class:`OpaqueToken` keeps the token out of the values the harness owns,
    but pytest's default ``--tb=long`` prints the arguments of every frame in a
    traceback, so a failure inside the library still renders the raw token that
    :meth:`OpaqueToken.reveal` handed over. This catches whatever slips
    through, including a truncated ``saferepr`` fragment, which is why it
    matches on runs rather than the whole token.
    """
    if not _TOKEN_GRAMS:
        return text
    raw = PICSURE_TEST_TOKEN.reveal()
    pieces: list[str] = []
    cursor = 0
    index = 0
    last_start = len(text) - _MIN_LEAKED_RUN
    while index <= last_start:
        if text[index : index + _MIN_LEAKED_RUN] in _TOKEN_GRAMS:
            end = index + _MIN_LEAKED_RUN
            while end < len(text) and text[index : end + 1] in raw:
                end += 1
            pieces.append(text[cursor:index])
            pieces.append(_TOKEN_PLACEHOLDER)
            cursor = end
            index = end
        else:
            index += 1
    if not pieces:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Scrub token material out of integration-test failure output.

    Defence in depth behind :class:`OpaqueToken`: it covers the paths the
    fixture type cannot reach, such as a library frame's arguments, a
    ``--showlocals`` dump, or a captured log line. A scrubbed ``longrepr``
    loses pytest's structured formatting, so it is only rewritten when a leak
    is actually present.
    """
    report = yield
    if not _TOKEN_GRAMS or not item.nodeid.startswith(
        _integration_nodeid_prefix(item.config)
    ):
        return report
    if report.longrepr is not None:
        rendered = str(report.longrepr)
        scrubbed = scrub_token(rendered)
        if scrubbed != rendered:
            report.longrepr = (
                f"{scrubbed}\n\n[conftest scrubbed PICSURE_TEST_TOKEN material "
                "from this failure output]"
            )
    report.sections = [
        (name, scrub_token(content)) for name, content in report.sections
    ]
    return report


def requires_auth(test_platform: Platform | str) -> bool:
    """Return True if the given platform needs a bearer token."""
    if isinstance(test_platform, Platform):
        return test_platform.requires_auth
    return True


def _resolve_test_platform() -> Platform | str | None:
    """Resolve PICSURE_TEST_PLATFORM, or ``None`` if it cannot be used.

    ``None`` means the variable is unset or holds a value
    :func:`picsure._transport.platforms.resolve_platform` would reject, so
    the live suite has nothing to connect to. Returning it lets collection
    skip the suite with one actionable message instead of letting every
    test fail inside platform resolution.
    """
    value = PICSURE_TEST_PLATFORM.strip()
    if not value:
        return None
    member = _PLATFORM_BY_NAME.get(value.upper())
    if member is not None:
        return member
    if value.startswith(("http://", "https://")):
        return value
    return None


def _unconfigured_reason() -> str | None:
    """Explain why the live suite cannot run, or ``None`` if it can.

    Checks the two things a live run cannot proceed without: a platform
    that resolves, and a token when that platform requires one. Anything
    beyond those is a per-test concern and belongs in the fixture that
    needs it.
    """
    value = PICSURE_TEST_PLATFORM.strip()
    if not value:
        return _SKIPPED_PLATFORM_UNSET
    platform = _resolve_test_platform()
    if platform is None:
        return _SKIPPED_PLATFORM_UNRECOGNIZED.format(
            value=value, names=", ".join(sorted(_PLATFORM_BY_NAME))
        )
    if requires_auth(platform) and not PICSURE_TEST_TOKEN:
        return _SKIPPED_TOKEN_UNSET.format(value=value)
    return None


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip the whole live suite when it cannot run, before any test starts.

    Two cases, one mechanism: integration is switched off, or it is on but
    unconfigured. Marking at collection means an unconfigured run reports a
    single skip reason rather than the same resolution error once per test.
    """
    reason = (
        _SKIPPED_INTEGRATION_DISABLED
        if not PICSURE_INTEGRATION
        else _unconfigured_reason()
    )
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    integration_dir = str(_INTEGRATION_DIR)
    for item in items:
        if str(item.fspath).startswith(integration_dir):
            item.add_marker(skip)


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Report which integration tests skipped and why, in the run summary.

    A per-test ``s`` mark is invisible at a glance, which is how a whole live
    test file came to contribute no coverage while the run still read as a
    pass. This prints an explicit section next to the pass/fail line, plus the
    unset environment variables responsible, so a configuration gap is visible
    without reading per-test skip marks.
    """
    skipped = [
        report
        for report in terminalreporter.stats.get("skipped", [])
        if report.nodeid.startswith(_integration_nodeid_prefix(config))
    ]
    unset = (
        [name for name in _OPTIONAL_ENV_COVERAGE if not os.environ.get(name)]
        if PICSURE_INTEGRATION
        else []
    )
    if not skipped and not unset:
        return

    terminalreporter.write_sep("=", "integration tests skipped", yellow=True)

    if not PICSURE_INTEGRATION:
        terminalreporter.write_line(
            f"{len(skipped)} integration test(s) skipped: integration is disabled. "
            "Set PICSURE_INTEGRATION=1 to run them."
        )
        return

    unconfigured = _unconfigured_reason()
    if unconfigured is not None:
        # The whole suite skipped for one reason, so the per-test listing
        # below would repeat that reason once per node id. Say it once and
        # drop the optional-variable notes, which cannot matter while
        # nothing can connect.
        terminalreporter.write_line(
            f"{len(skipped)} integration test(s) skipped: {unconfigured}"
        )
        return

    for reason, nodeids in _group_by_skip_reason(skipped).items():
        terminalreporter.write_line(f"{len(nodeids)} skipped: {reason}")
        for nodeid in nodeids:
            terminalreporter.write_line(f"    {nodeid}")

    for name in unset:
        terminalreporter.write_line(
            f"{name} is unset, so {_OPTIONAL_ENV_COVERAGE[name]} contribute no "
            "coverage. See .env.example for a working value."
        )


def _integration_nodeid_prefix(config: pytest.Config) -> str:
    rootpath = getattr(config, "rootpath", None)
    if rootpath is not None:
        try:
            return f"{_INTEGRATION_DIR.relative_to(rootpath).as_posix()}/"
        except ValueError:
            pass
    return f"{_INTEGRATION_DIR.name}/"


def _group_by_skip_reason(
    reports: list[pytest.TestReport],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for report in reports:
        grouped.setdefault(_skip_reason(report), []).append(report.nodeid)
    return grouped


def _skip_reason(report: pytest.TestReport) -> str:
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        reason = str(longrepr[2])
        prefix = "Skipped: "
        return reason[len(prefix) :] if reason.startswith(prefix) else reason
    return "no reason recorded"


@pytest.fixture()
def test_token() -> OpaqueToken:
    """Return the configured token wrapped so it cannot render itself.

    Unwrap it at the point of use with ``test_token.reveal()``; the wrapper
    keeps token material out of pytest failure headers and tracebacks.
    """
    return PICSURE_TEST_TOKEN


@pytest.fixture()
def test_platform() -> Platform | str:
    """Resolve PICSURE_TEST_PLATFORM to a Platform enum or URL string.

    Accepts enum names (e.g. ``BDC_AUTHORIZED``, ``NHANES_OPEN``) or full
    ``http(s)://`` URLs. There is no default: an unset or unrecognized value
    skips rather than failing inside platform resolution, so an unconfigured
    run says what to set instead of reporting a library error.
    """
    reason = _unconfigured_reason()
    if reason is not None:
        pytest.skip(reason)
    platform = _resolve_test_platform()
    assert platform is not None  # guaranteed by _unconfigured_reason above
    return platform


@pytest.fixture()
def test_concept_path() -> str:
    """Concept path used by query/export live tests.

    Platform-specific — set ``PICSURE_TEST_CONCEPT_PATH`` to a path that
    exists on the target deployment. Tests that need it will skip with
    a clear message if unset rather than fail with an opaque server
    error (e.g. a misleading 401 on an invalid path/filter combo).
    """
    if not PICSURE_TEST_CONCEPT_PATH:
        pytest.skip(
            "PICSURE_TEST_CONCEPT_PATH is not set. Add it to your .env "
            "with a concept path valid for PICSURE_TEST_PLATFORM, e.g. "
            r"'\open_access-1000Genomes\SIMULATED AGE\'."
        )
    return PICSURE_TEST_CONCEPT_PATH


@pytest.fixture()
def test_search_term() -> str:
    """Search term used by search live tests. Override via
    ``PICSURE_TEST_SEARCH_TERM``; defaults to ``"age"`` which exists on
    most PIC-SURE deployments."""
    return PICSURE_TEST_SEARCH_TERM


@pytest.fixture()
def test_gene() -> str:
    """A gene symbol valid for the target deployment's variant data.

    Set ``PICSURE_TEST_GENE`` (e.g. ``CHD8``). Genomic tests skip with a
    clear message when unset rather than failing with an opaque server error.
    """
    if not PICSURE_TEST_GENE:
        pytest.skip(
            "PICSURE_TEST_GENE is not set. Add it to your .env with a gene "
            "symbol present in the target deployment's variant data, e.g. "
            "PICSURE_TEST_GENE=CHD8 on BDC. See .env.example."
        )
    return PICSURE_TEST_GENE
