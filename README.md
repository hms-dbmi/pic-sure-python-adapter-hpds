# picsure

Python client for the PIC-SURE API. Search the data dictionary, build
cohort queries with nested AND/OR filters, and export participant-level
data — all from a Jupyter notebook.

## Installation

### pip

```bash
pip install picsure
```

For PFB export support:

```bash
pip install picsure[pfb]
```

### uv

```bash
uv add picsure
```

For PFB export support:

```bash
uv add picsure[pfb]
```

## Quickstart

```python
import picsure

session = picsure.connect(platform="BDC Authorized", token="your-token")

# Search the data dictionary
results = session.search("blood pressure")

# See your available resources
session.getResourceID()
```

## Documentation

Full documentation including API reference and tutorial notebooks is
available at the project documentation site.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
