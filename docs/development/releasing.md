# Releasing

This page is the maintainer playbook for cutting a release. It
covers versioning, the pre-release checklist, tagging, publishing
to PyPI, the docs site, and post-release housekeeping.

## Versioning policy

`picsure` follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (`X.0.0`) — backward-incompatible change to anything
  re-exported from `picsure/__init__.py`. Renamed functions, removed
  parameters, narrowed types, dropped public errors, changed default
  behaviour all count.
- **MINOR** (`0.Y.0`) — new public surface, additive changes.
  Adding a method to `Session`, a new `PhenotypicFilterType`, a new
  `Platform` member.
- **PATCH** (`0.0.Z`) — bug fixes that don't change the contract.
  Tightened input validation that previously accepted invalid input
  is a judgement call — if user code can break, it's a major bump.

The "public surface" is exactly the `__all__` list in
[`src/picsure/__init__.py`](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/src/picsure/__init__.py). Anything
prefixed with `_` (the `_models/`, `_services/`, `_transport/`, and
`_dev/` subpackages) can change without a major bump.

There is no version field to read or edit. `pyproject.toml` declares
`dynamic = ["version"]` with `[tool.hatch.version] source = "vcs"`, so
`hatch-vcs` derives the version from the git tag at build time. The
tag is the version. Between tags it derives a dev version from the
commit distance (see Post-release).

Every workflow checks out with `fetch-depth: 0` because a shallow
clone does not fail the build, it mislabels it. With no tag in reach,
`hatch-vcs` warns and falls back to `0.1.devN+g<sha>`, and `uv build`
succeeds with a `picsure-0.1.dev1+g<sha>` wheel that a publish job
would upload. Any checkout that builds the package needs full history
and tags: `fetch-depth: 0` in CI, and `git fetch --tags --unshallow`
on a local clone that was made shallow.

## Pre-release checklist

1. **Confirm CI is green on `main`.** Both the `CI` and `Docs`
   workflows must be passing on the commit you intend to tag.
2. **Update `CHANGELOG.md`.** The file follows
   [Keep a Changelog](https://keepachangelog.com/) — the current
   `## [Unreleased]` block becomes `## [X.Y.Z] - YYYY-MM-DD`. Sections
   already in use: `### Added`, `### Changed`, `### Removed`, `###
   Fixed`. Keep entries user-focused; internal refactors don't need
   a line unless they shift behaviour.
3. **Do not add a `version` to `pyproject.toml`.** It declares the
   version `dynamic`; a static field alongside that fails the build.
   The tag you push in the next section sets the version.
4. **Build the docs locally and skim.**
   ```bash
   uv run mkdocs build --strict
   uv run mkdocs serve   # optional, for live preview
   ```
   Strict mode catches broken cross-references that the CI docs job
   would also catch — running it locally is faster than waiting on
   the PR.
5. **Open a "release X.Y.Z" PR.** The CHANGELOG update lands on
   `main` via PR like any other change. Merge once CI is green.

## Cutting the release

The tag format is enforced, not a convention. `release.yml`'s
"Classify tag" step accepts exactly two shapes and fails the workflow
on anything else:

| Tag | Classified | Publishes to |
|---|---|---|
| `vX.Y.Z` (e.g. `v2.0.0`) | final release | PyPI |
| `vX.Y.Z{a,b,rc}[N]` (e.g. `v2.0.0rc1`) | pre-release | TestPyPI |
| anything else (e.g. `v1.0`) | error | nothing, the run fails |

The two-component tags still in the repo (`v1.0`, `v1.2`) predate
this workflow and would be rejected today. Use the full `vX.Y.Z`.
The pre-release number is optional to the pattern (`v2.0.0rc` passes,
and one such tag exists), but always give one: PEP 440 reads a bare
`rc` as `rc0`, and the next candidate needs a name that sorts after
it.

```bash
# from a clean main, on the merge commit you want to ship
git checkout main
git pull
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push origin vX.Y.Z
```

Pushing the tag is the release. `release.yml` triggers on
`push: tags: ["v*"]` and does the whole run itself. `lint` and `test`
(Python 3.10/3.11/3.12) run in parallel. `build` waits for both, then
classifies the tag, runs `uv build`, and validates the metadata with
`uvx twine check`. One of the two publish jobs runs last. A failing
lint or test job stops the release before anything is uploaded. The
tag check sits inside `build`, so a malformed tag such as `v1.3` still
costs a full lint run and test matrix before the workflow fails.

## Publishing to PyPI

Publishing is automated and there is **no API token to manage**. The
`publish-pypi` and `publish-testpypi` jobs in `release.yml` use
`pypa/gh-action-pypi-publish` with `permissions: id-token: write`,
which is [Trusted
Publishing](https://docs.pypi.org/trusted-publishers/). PyPI trusts
a short-lived OIDC token minted for that workflow in that repository.
Do not create a `PYPI_TOKEN` or set `UV_PUBLISH_TOKEN`; a long-lived
token is the thing this setup exists to avoid.

Each publish job is pinned to a GitHub
[environment](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/settings/environments),
`PyPi` for final releases and `TestPyPi` for pre-releases. The
environment is where the trusted-publisher binding and any required
reviewers live.
A first release from a new repository or environment needs the
publisher registered on PyPI first, or the job fails at upload with a
permissions error.

The TestPyPI dry run is not a separate manual step: tag a pre-release
and it routes there automatically.

```bash
git tag -a vX.Y.Zrc1 -m "Release candidate X.Y.Zrc1"
git push origin vX.Y.Zrc1        # -> TestPyPI, via release.yml
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ picsure==X.Y.Zrc1
```

TestPyPI hosts the candidate and nothing it depends on: no `pandas`,
no `httpx`, and a `fastavro` too old to satisfy the pin. The extra
index lets pip take those from PyPI while the candidate itself still
comes from TestPyPI, the only index that has it.

### When a release run fails

There is no manual publish path. `release.yml` has no
`workflow_dispatch` trigger, and the publish jobs authenticate only
with the OIDC token GitHub mints for a tag-triggered run, so nothing
run by hand can upload. Recover inside that model:

**Transient failure** (runner outage, flaky test, PyPI timeout). Open
the run in the Actions tab and re-run the failed jobs. The re-run
keeps the same tag and reuses the `dist` artifact already built in
that run.

**Wrong tag, or the workflow file itself needs a change.** The run
executes the `release.yml` at the tagged commit, so land the fix on
`main`, then move the tag to the new commit and push it again.
Nothing was uploaded, so the version is still free.

```bash
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push origin vX.Y.Z
```

**Publish succeeded and a later step failed.** That version is spent.
PyPI never accepts a file name twice, even after a delete. Fix forward
and cut the next patch version.

## Publishing the docs

`docs.yml` builds the site with `uv run mkdocs build --strict` on
every pull request and every branch push, and **deploys** only from a
published release or a push to the repository's default branch. The
guard compares against `github.event.repository.default_branch`
rather than a hard-coded name, so it cannot go stale if the default
branch is renamed — but it also means the deploy follows whatever
GitHub says the default branch is, not whichever branch the team
treats as mainline.

Three practical notes:

- A docs-only change needs no version bump: a push to the default
  branch republishes.
- Because `docs.yml` runs `mkdocs build --strict`, a broken link
  fails the check on the PR that introduces it. Fix relative paths
  before merging; don't expect to fix them after.
- The deploy writes the `gh-pages` branch via
  `peaceiris/actions-gh-pages`, but GitHub Pages is **not currently
  enabled for this repository** (`has_pages` is false), so nothing is
  served from it yet. `mkdocs.yml` sets no `site_url`. Enabling Pages
  and pointing it at `gh-pages` is a repository-settings change.

## Post-release

1. **Reopen `[Unreleased]` in CHANGELOG.md.** Drop a fresh
   `## [Unreleased]` block above the just-released version, with
   empty `### Added` / `### Changed` / `### Removed` / `### Fixed`
   subsections — easier than adding them ad-hoc later.
2. **Nothing to bump.** `hatch-vcs` already derives a dev version
   from the distance past the tag: N commits after `vX.Y.Z` build as
   `X.Y.(Z+1).devN+g<sha>`, the next patch version, without anyone
   editing a file.
3. **Verify the install.** `pip install picsure==X.Y.Z` from a fresh
   virtualenv and run the quickstart. Any import-time regression
   (missing dependency, wrong wheel platform, py.typed-related
   issues) shows up here and is hard to find later.
