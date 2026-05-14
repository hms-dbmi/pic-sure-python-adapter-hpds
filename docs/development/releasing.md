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
  Adding a method to `Session`, a new `ClauseType`, a new
  `Platform` member.
- **PATCH** (`0.0.Z`) — bug fixes that don't change the contract.
  Tightened input validation that previously accepted invalid input
  is a judgement call — if user code can break, it's a major bump.

The "public surface" is exactly the `__all__` list in
[`src/picsure/__init__.py`](../../src/picsure/__init__.py). Anything
prefixed with `_` (the `_models/`, `_services/`, `_transport/`, and
`_dev/` subpackages) can change without a major bump.

The current version lives in
[`pyproject.toml`](../../pyproject.toml) under `[project].version`.

## Pre-release checklist

1. **Confirm CI is green on `main`.** Both the `CI` and `Docs`
   workflows must be passing on the commit you intend to tag.
2. **Update `CHANGELOG.md`.** The file follows
   [Keep a Changelog](https://keepachangelog.com/) — the current
   `## [Unreleased]` block becomes `## [X.Y.Z] - YYYY-MM-DD`. Sections
   already in use: `### Added`, `### Changed`, `### Removed`, `###
   Fixed`. Keep entries user-focused; internal refactors don't need
   a line unless they shift behaviour.
3. **Bump `version` in `pyproject.toml`** to `X.Y.Z`.
4. **Build the docs locally and skim.**
   ```bash
   uv run mkdocs build --strict
   uv run mkdocs serve   # optional, for live preview
   ```
   Strict mode catches broken cross-references that the CI docs job
   would also catch — running it locally is faster than waiting on
   the PR.
5. **Open a "release X.Y.Z" PR.** The CHANGELOG bump and version bump
   land on `main` via PR like any other change. Merge once CI is
   green.

## Cutting the release

Existing tags follow `vX.Y` (e.g. `v1.0`, `v1.2`). Going forward,
the SemVer convention is to use the full `vX.Y.Z`. (Confirm with
maintainers whether the abbreviated `vX.Y` form should be preserved
for continuity, or whether new tags should standardize on
`vX.Y.Z`.)

```bash
# from a clean main, on the merge commit you want to ship
git checkout main
git pull
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push origin vX.Y.Z
```

There is **no tag-triggered workflow in the repo today**: neither
`ci.yml` nor `docs.yml` includes a `push: tags:` filter. Tagging is
a marker for humans; publishing happens separately. Confirm with
maintainers whether a tag should trigger anything.

## Publishing to PyPI

No automated publish job is wired up — the package is published
manually. Confirm with maintainers whether this is intended to stay
manual or whether the team plans to add a `publish.yml` workflow.

Manual path with `uv`:

```bash
# from a clean checkout at the tagged commit
uv build                                  # writes dist/picsure-X.Y.Z-*.whl and .tar.gz
uv publish                                # uploads to PyPI; requires PYPI_TOKEN
```

`uv publish` reads the `UV_PUBLISH_TOKEN` environment variable (or
`--token`) for the API token. Use a project-scoped PyPI token, not a
personal one — see <https://pypi.org/manage/account/token/>.

A dry run against TestPyPI before the real publish is cheap
insurance:

```bash
uv publish --publish-url https://test.pypi.org/legacy/ --token <test-token>
pip install --index-url https://test.pypi.org/simple/ picsure==X.Y.Z
```

## Publishing the docs

`docs.yml` handles the docs site automatically. On every push to
`main`, it builds with `uv run mkdocs build --strict` and deploys
the `site/` output to the `gh-pages` branch via
`peaceiris/actions-gh-pages`. The site URL follows GitHub Pages'
default for the repo (`mkdocs.yml` does not set a `site_url`;
confirm the published location with maintainers if it isn't visible
under the repo's Pages settings).

Two practical notes:

- A docs-only release does not need a version bump. Pushing to
  `main` republishes.
- Because `docs.yml` runs `mkdocs build --strict`, a broken link in
  a new doc fails CI on the PR that introduces it. Fix relative
  paths before merging; don't expect to fix them after.

## Post-release

1. **Reopen `[Unreleased]` in CHANGELOG.md.** Drop a fresh
   `## [Unreleased]` block above the just-released version, with
   empty `### Added` / `### Changed` / `### Removed` / `### Fixed`
   subsections — easier than adding them ad-hoc later.
2. **Optionally bump to a `-dev` version** in `pyproject.toml` (e.g.
   `X.Y.(Z+1)-dev0`). This is bookkeeping; the next release will
   overwrite it. Confirm with maintainers whether the project uses
   this convention — current tags suggest a plain bump-on-release
   workflow without explicit `-dev` markers.
3. **Verify the install.** `pip install picsure==X.Y.Z` from a fresh
   virtualenv and run the quickstart. Any import-time regression
   (missing dependency, wrong wheel platform, py.typed-related
   issues) shows up here and is hard to find later.
