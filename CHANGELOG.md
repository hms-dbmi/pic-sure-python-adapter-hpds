# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `picsure.connect()` to authenticate and connect to a PIC-SURE instance.
- `Session.getResourceID()` to list available resources as a DataFrame.
- Platform name resolution for BDC Authorized, BDC Open, Demo, and AIM-AHEAD.
- Actionable error messages via `PicSureError`.
- Unit test suite with mocked HTTP via respx.
- Integration test scaffold gated by `PICSURE_INTEGRATION` env var.
- GitHub Actions CI with Python 3.10/3.11/3.12 matrix.
- `Session.search()` to search the data dictionary with optional facet filtering.
- `Session.facets()` to retrieve available facet categories as a `FacetSet`.
- `Session.showAllFacets()` to display all facet categories and values as a DataFrame.
- `FacetSet` for building facet selections with validation.
- Search result deduplication by concept path.
- Zero-result searches return empty DataFrames with a stderr note.
