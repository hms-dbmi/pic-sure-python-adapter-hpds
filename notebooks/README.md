# Notebooks

Committed Jupyter notebooks live here. Examples, demos, and
walkthroughs that ship with the project belong in this directory.

## Why a dedicated directory?

The project gitignores `*.ipynb` everywhere *except* under
`notebooks/`. That gives you two things:

- **Committed notebooks land in one predictable place.** Reviewers
  don't have to hunt across the tree to find what's user-facing.
- **Scratch experiments stay out of git automatically.** A
  `scratch.ipynb` in the repo root or inside `src/` is invisible to
  `git add`. Use those freely without worrying about accidental
  commits.

## Defaults inside the dev container

`docker compose up notebook` launches JupyterLab with
`--ServerApp.preferred_dir=/workspace/notebooks`, so **File → New
Notebook** lands here by default. You can still navigate elsewhere via
the file browser; new notebooks created outside this directory just
won't be tracked.

## Conventions

- Clear all cell outputs before committing
  (`Kernel → Restart Kernel and Clear Outputs of All Cells`) so diffs
  don't drown in base64 image blobs.
- Keep the notebook self-contained: imports at the top, a brief
  markdown description of what it demonstrates, and inputs that work
  against a published PIC-SURE dataset (e.g. `BDC_PREDEV_OPEN`).
- If a notebook needs credentials, read them from `.env` via
  `os.environ`, never hardcode tokens.
