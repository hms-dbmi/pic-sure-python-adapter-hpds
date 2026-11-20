# Releasing

## Overview

A Python adapter release is a `vX.Y.Z` tag on `main`, built by CI and published to PyPI as
`picsure`. It goes out right after every production PIC-SURE environment has been upgraded, never
before. This guide is for the developers who cut releases and the product managers who schedule
them.

The flow in one line: merge to `main`, freeze, tag a release candidate (published to TestPyPI), QA
it, wait for the environment releases, tag the final version (published to PyPI). The R adapter
releases after this one, because it wraps a pinned Python build. See the
[R adapter's release guide](https://github.com/hms-dbmi/pic-sure-r-adapter-hpds/blob/main/docs/development/releasing.md).

Rules that hold for every release:

- **Backward compatible, or deprecated first.** Researchers and outside groups run the adapter in
  their own notebooks and pipelines, and they upgrade when we tell them to. A change that breaks
  their code needs a deprecation window (next section).
- **Never ahead of the servers.** A release that calls a route production does not serve yet breaks
  every user who upgrades. The server compatibility gate below catches this.
- **A PyPI version is spent forever.** PyPI never accepts the same version twice, even after a
  delete. A bad upload can be yanked, never replaced.
- **`client_type` is allowlisted.** The adapter sends `X-Client-Type: PYTHON_ADAPTER`, and the
  PIC-SURE gateway rejects any value outside its allowlist with HTTP 400. Changing the default, or
  letting callers pass a new value, needs the gateway allowlist changed and deployed first.

## Versioning and deprecation

Versions follow [semantic versioning](https://semver.org). Pick the bump from the largest change in
the release:

| Bump | When | Example |
| --- | --- | --- |
| Major (`5.0.0`) | Any change that breaks a caller, removes something deprecated, or needs a newer PIC-SURE server than the last release did | Removing a function, changing what a default argument returns |
| Minor (`4.1.0`) | New features that leave existing calls working, including a new deprecation | A new keyword argument with a backward-compatible default |
| Patch (`4.0.1`) | Bug fixes only | Fixing a wrong result type |

The R adapter's major version follows this one: R 4.x wraps Python 4.x. R's minor and patch numbers
move on their own.

The version comes from the git tag through `hatch-vcs`. Never add a `version` field to
`pyproject.toml`: it declares the version `dynamic`, and a static field alongside that fails the
build.

### Deprecating something

A breaking change waits out a six-month deprecation window:

1. Ship the replacement in a minor release. In the same release, make the old behavior warn every
   time it runs: `warnings.warn("...", FutureWarning, stacklevel=2)`. Use `FutureWarning`, not
   `DeprecationWarning`, because Python shows a `DeprecationWarning` only when the calling code is
   `__main__`. A user whose call sits inside their own module or pipeline would never see it.
2. The warning text and the CHANGELOG entry both name the replacement and the earliest release that
   removes the old behavior.
3. Remove it only in a major release, and only once six months have passed since the warning
   shipped.

### When the server forces a break

The window above needs the server to keep the old route alive. The rule: when PIC-SURE replaces a
route the adapter calls, the server keeps the deprecated route for six months after the replacement
ships. The adapter moves to the new route once every production environment serves it, and the old
route can go after that.

The exception: if a server release removes a route with no overlap, the adapter ships a major
release on the day production upgrades, with no window. The release owner records why in the
release notes. Adapter 4.0.0 was this case: PIC-SURE 5.0.0 removed the `/v3` query routes.

## Server compatibility

Each adapter line works with exactly one PIC-SURE line today. Adapter 4.x needs PIC-SURE 5.0.0 or
later, and adapter 3.x works only with PIC-SURE 4.1.x. Check this table before every release and
update it in the release PR.

| Adapter | Minimum PIC-SURE | Last PIC-SURE tested | Why |
| --- | --- | --- | --- |
| 4.0.x | 5.0.0 | Not recorded | Calls the unversioned `/hpds/{backend}/query` routes and polls status and result with GET. PIC-SURE 4.1.x serves neither. |
| 3.0.x | 4.1.0 | 4.1.x | Calls `/hpds/{backend}/v3/query` with POST status and result. PIC-SURE 5.0.0 removed those routes. |

### The gate

Before tagging a release candidate, the release owner checks three things:

1. List every server route the release calls that the previous release did not, or calls
   differently (new method, new body, new path).
2. Confirm BDC and NHANES production serve each of those routes, or will once their scheduled
   upgrade lands. The PIC-SURE release notes and the environment release schedule say which version
   each environment gets.
3. If production cannot serve them, the release waits, or it becomes a major release that ships
   with the upgrade (see "When the server forces a break").

Record the result in this table: the minimum PIC-SURE version, and the version QA ran against in
the "Last PIC-SURE tested" column.

## Release steps

Each step has an owner. Owners are not assigned yet. Until they are, the person cutting the release
owns every step.

1. **Merge the work.** Every change reaches `main` through a reviewed PR, and every user-visible
   change adds a line under `## [Unreleased]` in `CHANGELOG.md`.
   - Owner: to be assigned
2. **Freeze and choose the version.** Announce the code freeze. Nothing else merges to `main` until
   the release ships, so the commit QA tests is the commit that ships. Choose the version from the
   versioning table.
   - Owner: to be assigned
3. **Pass the server gate.** Confirm every route this release calls is served by BDC and NHANES
   production, or will be once their scheduled upgrade lands. Update the compatibility table in this
   guide.
   - Owner: to be assigned
4. **Open the release PR.** Move the `[Unreleased]` entries under a `## [X.Y.Z] - YYYY-MM-DD`
   heading and update the compatibility table. The first release under this guide also splits the
   existing `[Unreleased]` entries into the `[3.0.0]`, `[4.0.0]` and `[4.0.9]` headings they shipped
   in. Run `uv run mkdocs build --strict` locally. Merge it
   after review, with the `CI` and `Docs` workflows green.
   - Owner: to be assigned
5. **Tag the release candidate.** Create a GitHub Release for tag `vX.Y.Zrc1` on the tip of `main`,
   marked as a prerelease. CI publishes it to TestPyPI.
   - Owner: to be assigned
6. **QA the release candidate.** Run the QA checklist below. If anything fails, merge the fix by PR
   and tag `vX.Y.Zrc2`, and so on.
   - Owner: to be assigned
7. **Start the R release candidate.** Hand the rc tag to the R adapter release as soon as it is
   published, so R QA runs alongside Python QA. A later rc after a QA failure is handed over the
   same way. The R guide covers the pin.
   - Owner: to be assigned
8. **Wait for the environment releases.** The adapter ships right after BDC and NHANES production
   are upgraded to the PIC-SURE version it needs.
   - Owner: to be assigned
9. **Publish the final release.** Create a GitHub Release for tag `vX.Y.Z` on the same commit as the
   passing rc. CI publishes it to PyPI.
   - Owner: to be assigned
10. **Verify and hand off.** Install the release in a clean virtualenv
    (`pip install picsure==X.Y.Z`), check that `pip show picsure` reports `Version: vX.Y.Z`, and
    run the quickstart. Tell the R adapter owner to cut the final R release.
    - Owner: to be assigned

## Release candidates and QA

A release candidate is a tag of the form `vX.Y.ZrcN`, numbered from 1: `v4.1.0rc1`, then
`v4.1.0rc2` after a fix. Never push a bare `v4.1.0rc`. CI publishes every rc to
[TestPyPI](https://test.pypi.org/project/picsure/), never to PyPI.

To create one, open **Releases > Draft a new release** on GitHub, type the new tag, target `main`,
and tick **Set as a pre-release**. Publishing that draft creates the tag, and the tag push runs the
release workflow. The prerelease tick keeps the rc from showing as the latest release.

### Installing the release candidate

From TestPyPI, which tests the exact package that will be uploaded:

```bash
pip download --no-deps --index-url https://test.pypi.org/simple/ -d rc picsure==4.1.0rc1
pip install rc/picsure-4.1.0rc1-py3-none-any.whl \
    -c https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/releases/download/v4.1.0rc1/constraints.txt
```

The first command fetches only the picsure wheel from TestPyPI. The second installs that wheel and
resolves its dependencies from PyPI alone, at the versions in `constraints.txt`. The release
workflow exports that file from `uv.lock` at the rc tag and attaches it to the rc's prerelease, so
QA runs against the dependency versions CI tested. Put the rc's own tag in the URL. If the
prerelease has no `constraints.txt`, the rc was tagged without a GitHub Release. Create the
prerelease for the tag and rerun the release workflow's `attach-constraints` job.

Do not install with `--index-url https://test.pypi.org/simple/ --extra-index-url
https://pypi.org/simple/`. Anyone can upload any package name to TestPyPI, and pip takes the highest
version across both indexes for every dependency, not just picsure. That pulled in a
python-dateutil 3.9.0 that exists only on TestPyPI.

### QA checklist

QA runs the notebooks researchers use most: the Python notebooks in `NHLBI_BioData_Catalyst/python/`
on the `release_2026` branch of
[Access-to-Data-using-PIC-SURE-API](https://github.com/hms-dbmi/Access-to-Data-using-PIC-SURE-API/tree/release_2026).
The Python notebooks in the other folders use older client libraries and are not part of this
checklist.

1. **Change the install cells by hand.** Most notebooks install the adapter from `main`
   (`!{sys.executable} -m pip install --upgrade --force-reinstall git+https://github.com/hms-dbmi/pic-sure-python-adapter-hpds.git@main`).
   `0_Open_Access_Data_Dictionary_Search.ipynb` installs the released package
   (`pip install picsure --upgrade`). Before running each one, replace that line with the two
   commands under "Installing the release candidate" above, each prefixed with
   `!{sys.executable} -m`. Nothing in the notebooks does this for you, and a notebook left as it is
   tests the wrong code.
2. **Use a server that already runs the target PIC-SURE version.** The notebooks connect to
   `Platform.BDC_AUTHORIZED` or `Platform.BDC_OPEN`, which are production. If production has not
   been upgraded yet, point them at an environment that has.
3. **Run every notebook in that folder end to end** and note any failure or changed output.
4. **Try each change in the CHANGELOG entry** for this version, including every deprecation warning
   it adds.
5. **Record the result** on the rc's GitHub Release: pass or fail, the PIC-SURE version tested
   against, and who ran it.

If QA fails, merge the fix to `main` by PR, tag the next rc and repeat.

## Publishing the final release

Open **Releases > Draft a new release**, type the tag `vX.Y.Z`, and target the commit the passing rc
was tagged on. During a code freeze that is still the tip of `main`. Leave **Set as a pre-release**
unticked and tick **Set as the latest release**. Write the notes (next section), then publish.

### What the tag push does

`.github/workflows/release.yml` runs on every pushed tag that matches `v*`:

1. Lint (ruff, mypy) and unit tests on Python 3.10, 3.11 and 3.12, with an 80% coverage floor. Any
   failure stops the release before anything is uploaded.
2. Classify the tag. `vX.Y.Z` goes to PyPI. `vX.Y.Z` followed by `a`, `b` or `rc` and a number goes
   to TestPyPI. Any other tag fails the run.
3. Build the package. The version comes from the tag itself, so tag `v4.1.0` builds
   `picsure-4.1.0`. The published metadata currently keeps the tag's `v` prefix
   (`pip show picsure` prints `Version: v4.1.0`), which a workflow change will remove.
4. Upload through [trusted publishing](https://docs.pypi.org/trusted-publishers/), from the `PyPi`
   or `TestPyPi` GitHub environment. No API tokens are stored in the repo. Do not create a
   `PYPI_TOKEN`.

Two things to know:

- **Only tag commits that contain the current workflow.** A tag runs the `release.yml` of the
  commit it points at. Before 4.0.0 the workflow took the version from the nearest older tag, which
  is how `picsure 3.0.4rc0` reached production PyPI. An old commit would bring that behavior back.
  A hotfix branch starts from an older tag, so its fix PR copies in the current workflow first (see
  "Hotfix releases").
- **Only members of the developers team can push `v*` tags.** A tag ruleset enforces this.
  *Pending: the ruleset does not exist yet.*

### If something goes wrong

- **The workflow failed before upload:** open the run in the Actions tab and re-run the failed
  jobs. Nothing was uploaded, so the version is still free. If the fix needs a new commit, do not
  move the tag. Land the fix on `main` and tag the next rc on it. If the tag that failed was the
  final one, delete its Release and tag first, then QA the new rc and publish the final on that
  rc's commit:

  ```bash
  gh release delete vX.Y.Z --cleanup-tag --yes
  ```

- **A wrong build reached PyPI:** yank that version on PyPI (Manage > Releases > Options > Yank) and
  release the next patch version. The yanked number can never be reused.

## Changelog and release notes

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com). Changes collect under
`## [Unreleased]` as they merge. The release PR moves them under `## [X.Y.Z] - YYYY-MM-DD`, using
the planned release date, and leaves an empty `[Unreleased]` above it.

The GitHub Release body starts with three fixed sections, then GitHub's generated PR list
(**Generate release notes**). Write "None" in a section rather than dropping it, so readers can tell
nothing was missed.

```markdown
## Breaking changes
None.

## Requires
PIC-SURE 5.0.0 or later.

## Deprecations
- `oldName()` warns from this release. Use `newName()`. Removed no earlier than 5.0.0 (YYYY-MM).
```

For a release candidate, the body only needs the QA result once QA finishes: pass or fail, the
PIC-SURE version tested, and who ran it.

## Hotfix releases

A hotfix fixes a released version without shipping whatever has merged to `main` since. It is
always a patch release.

1. Branch from the release tag being fixed: `git switch -c hotfix/v4.0.10 v4.0.9`, then push the
   branch. A tag runs the `release.yml` of its own commit, so if the workflow has changed on `main`
   since that tag, copy the current `.github/workflows/release.yml` into the fix PR.
2. Open the fix as a PR into `hotfix/v4.0.10`, with the usual one approving review. Add a
   `## [4.0.10] - YYYY-MM-DD` CHANGELOG entry in the same PR.
3. Tag `v4.0.10rc1` on the hotfix branch as a prerelease and QA the fix. QA covers the fix and the
   notebooks it touches, not the full checklist.
4. Tag `v4.0.10` on the same commit. This is the one case where a release tag is not on `main`.
5. The same day, open a second PR that brings the fix and the CHANGELOG entry into `main`, so the
   next release keeps them.
6. Tell the R adapter owner. R follows with a patch release that only moves its pin to `v4.0.10`.
