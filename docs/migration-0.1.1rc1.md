# Local 0.1.1rc1 candidate

This candidate is prepared locally. It does not replace the published 0.1.0 release,
and it has not been pushed, merged or deployed.

Report/manifest/decision `schemaVersion` remains `1.0`. Existing valid reports retain
their comparison and decision identities. No hashes are rewritten during import.
The original 1.0 rule/comparison binding recipe is recomputed to reject inconsistent
input/configuration/renderer declarations under an unchanged identity.
The tightened report schema defines pages, channel states, coverage, summary and
stored decision records; runtime validation also checks their cross references and
derivations. This is internal consistency checking of unsigned JSON, not a signature
or proof that measurements or exporter declarations are authentic.

New producers add optional `pages[].reference/candidate.rasterSize` (`[width,height]`
in native pixels). The required text/geometry/raster extraction channels remain
separate. `coverage[].rasterComparison` now always records one of:

| State | Meaning |
| --- | --- |
| `complete` | Both native pixel grids match and physical dimensions differ by at most 0.25 pt per axis. |
| `unavailable-different-raster-grid` | Physical dimensions pass the tolerance, but native bitmap dimensions differ at this DPI. |
| `unavailable-different-page-size` | Physical dimensions exceed the tolerance. |
| `unavailable-unresolved-correspondence` | Supplied pages cannot be confidently paired in declared order. |

Native rasters are preserved. No resizing, stretching, padding or alignment is used.
When raster comparison is unavailable, the report has no paired diff mask or raster
findings for that page. Independent text/geometry findings and paired crops remain.
The physical-size finding is retained when the tolerance is exceeded. The viewer
shows unavailable channels beside the previews and disables incompatible overlay.

Historical 1.0 reports may omit `rasterSize` and may omit `rasterComparison` only on
unresolved pages; that omission conservatively means unavailable correspondence.
Actual PNG dimensions are checked even when historical metadata is absent.
Malformed pages/coverage/summary or unsupported accepted states are rejected with
exit 2 before any output bundle is committed. They are not silently repaired.
Producer bundles have derived `complete` or `incomplete` status; a fabricated
`analysisStatus:error` bundle without a defined failed-channel contract is rejected.
CLI errors remain a separate JSON error result, exit 2, without a committed report.

Applied decisions must reference current findings/regions and explain each accepted
state. Old mismatched decisions remain `stale`, including historical dangling refs;
they suppress nothing. Acceptance preserves incomplete coverage and exit 3 when no
open finding remains at threshold. Evidence remains visible after acceptance.

Assets must be regular valid PNG files under `assets/*.png`. Every traversed directory
component and the final file is opened with no-follow descriptor operations. Bundle
paths through symlinks (including `/tmp` aliases on some systems) must be supplied
via a regular directory path. File, pixel, aggregate output and HTML bounds apply;
stored JSON limits cannot raise the active loader limits. Copied bytes are unchanged.

New comparisons include the native-grid policy and updated implementation hashes in
their binding. Re-run comparison after upgrading, and review its new identity; old
decisions are expected to be stale against newly measured evidence. Applying old
decisions to their unchanged valid historical report still works.

Python 3.13 and all pinned third-party dependencies remain unchanged. The sole
`uv.lock` package-version edit is this project's `0.1.0` to `0.1.1rc1` metadata.
SIGINT returns one JSON interrupted result (exit 130 with `--json`), stops only the
invocation's worker and cleans only owned staging directories. Rollback checks the
staging inode and preserves a replaced directory belonging to another writer.
The parent crash/interrupt fallback also requires a bounded worker ownership record
with the nonce and matching device/inode. Unregistered or uncertain directories are
preserved. A native crash before registration can leave an uncommitted empty staging
directory; the parent does not delete an uncertain replacement by guessing ownership.

For reproducible package and browser checks, see [verification](verification.md).
Fresh app exports and a real independent review are covered by the
[external pilot runbook](external-pilot.md); passing synthetic probes does not prove
Office rendering compatibility or a 10/10 rating.
