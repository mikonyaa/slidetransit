# Security

For a sensitive vulnerability, use this repository's private GitHub vulnerability
reporting when available; otherwise share a minimal synthetic reproduction with the
maintainer through an agreed private channel. Do not attach confidential decks to
public issues. We do not claim a response-time guarantee.

SlideTransit opens input documents read-only and does not fetch external relationships,
execute PDF actions, initialize PDF forms, run macros, send telemetry or upload files.
Native PDFium is an upstream dependency, invoked in an owned subprocess with a
180-second deadline. This is a resource boundary, **not an OS sandbox**. Update
dependencies when upstream security fixes warrant a new release.

Limits are documented in `docs/limitations.md`; violations return error, not PASS.
Reports contain document text and images and can themselves be confidential. The
offline HTML uses inert JSON, DOM text nodes and a restrictive no-network CSP.
Input paths and unsafe ZIP names are not extracted. Existing output directories are
never replaced. Keep report JSON and its referenced asset directory together.
