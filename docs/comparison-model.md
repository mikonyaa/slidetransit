# Comparison model

## Trust and scope

One invocation compares one supposed deck's reference and candidate exports. Matching
order is declared, never cryptographically proven. Page count must match the declared
source slide range. A detected unique exact-text page reorder makes correspondence
unresolved instead of silently remapping. Other reorderings can be undetectable; callers
must provide the agreed order. Identical repeated pages cannot establish identity.

PPTX parsing is for optional attribution, not rendering. Its slide order comes from
presentation relationships. Hidden slides require a concordant explicit export scope.
Notes/handouts are rejected by the manifest format.

## Coordinates and extraction

The displayed page's top-left is (0,0), x increases right and y down, measured in points
(1/72 inch). PDFium renders its effective CropBox with inherited rotation. pdfminer
already applies a MediaBox/rotation CTM; SlideTransit inverts that transform for each
pdfplumber char corner, then invokes that exact bitmap's `FPDF_PageToDevice` transform.
Pixels divided by DPI/72 give display points. PDFium integer conversion quantizes
boxes to one raster pixel. The 0/90/180/270 and nonzero MediaBox/CropBox canaries check
each character against actual ink, not just serialization of expected coordinates.

Original extracted Unicode and character boxes are retained. Matching uses NFC and
whitespace collapse only, preserving punctuation, numeric signs, case and CJK.
Horizontal lines are clustered within 2pt of y, separated at a large horizontal gap;
adjacent lines with consistent start and font size become blocks. Exact unique text
anchors precede bounded mutual geometry matches for duplicates and unique similar-text
matches. Unmatched text means changed content **or unresolved block matching**.
Mixed styles and complex layouts can split blocks; inspect the evidence rather than
assuming a shape has disappeared. Missing/unsupported text layers produce incomplete
required coverage; extracted absence never proves visual absence.

## Independent rules

| Rule | Observation | Limit |
|---|---|---|
| extracted-text-change | Original/normalized strings differ or cannot be matched | Extraction/block matching can be ambiguous |
| line-wrap-change | Unique matched content has different line segmentation | Does not prove font substitution |
| displacement | x/y shift exceeds configured 2pt default | No local alignment cancels motion |
| text-size-change | Average extracted glyph size changes beyond 1.5pt | Not a verified font identity |
| raster-region-change | RGB channel delta reaches 16/255 default | Difference is measured; cause is unknown |
| possible-clipping | Retained glyphs extend outside page or visible ink falls below 45% | Color/occlusion/extraction can also explain ink loss |
| page-geometry-change | Displayed dimensions disagree by more than .25pt | No stretch; raster comparison unavailable |
| page-correspondence-problem | Counts/range disagree or unique exact-text reorder appears | No asserted index pairing |

Both PDFs use pinned pypdfium2/PDFium, identical DPI, RGB conversion, white background,
no annotations/forms and no pixel normalization or spatial alignment. Difference masks
keep actual changed pixels. An 8px grid with 5x5 tile dilation **groups mask components**;
it does not shift/blur the source images or change measured differences. Component
pixel bounds and counts come from the original mask. Parameters and implementation
hashes are captured in `rules`; active thresholds and native/library versions are
included in the comparison fingerprint.

Raster severity uses intensity, not region area: a maximum delta ≤32 is a visible
low-confidence hint; stronger regions are medium. Nothing labels all small regions
safe. A changed numeral/sign can have high-severity text evidence independent of a
small raster region. Threshold calibration is documented in `verification.md` and
does not promise interchangeable antialiasing across arbitrary operating systems.

## Attribution and coverage

Automatic source association requires a unique source/PDF text anchor, an explicitly
supported unrotated direct shape, agreed slide geometry and glyph containment within
3pt of that source box. Duplicate anchors in unsupported groups count against
uniqueness. Inherited/grouped/rotated transforms are not attributed. A shape ID is
reported together with its `slidePart`, labelled Likely source object with conditional
confidence. No proximity-only or confirmed identity claim is made.

Analysis coverage and source attribution confidence are separate. An unattributed
shape does not hide a PDF difference or make complete PDF-channel coverage partial.

## Review and status

Report/findings have stable fingerprints; comparisonId covers input bytes, scope,
mode, settings, versions and rule implementation. Decisions bind to this comparison,
input/rule/renderer records and finding/region hash. All acceptances require a reason;
an optional author is omitted unless provided. Region fingerprints use the page and
four fixed-4-decimal point strings, shared with the viewer's SHA-256 encoding.

Changed bindings remain stale and never suppress evidence. Accepted findings remain
visible, including after CLI application. Regions must fit both pages and cover ≤25%;
they cannot accept structural errors. Parsing errors have no successful report.
Incomplete required coverage can never become exit 0 through reviewer acceptance.
