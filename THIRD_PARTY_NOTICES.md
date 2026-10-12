# Third-party notices

SlideTransit code and own fixture artwork/decks: MIT, Meiram Bakhytzhan.

Runtime dependencies are separately installed, pinned in `pyproject.toml` and `uv.lock`:

| Component | License / role |
|---|---|
| pypdfium2 5.3.0 | Apache-2.0 / BSD-3-Clause, Python binding and PDFium distribution |
| PDFium 145.0.7616.0 | BSD-3-Clause plus upstream component notices; no V8/XFA build flags |
| pdfplumber 0.11.9 / pdfminer.six | MIT, character extraction |
| Pillow 12.0.0 | HPND, imaging |
| NumPy 2.2.6 | BSD-3-Clause, raster measurements |
| defusedxml 0.7.1 | PSF, guarded XML parsing |
| jsonschema 4.26.0 | MIT, JSON validation |

Full pypdfium2 and the inspected macOS ARM64 PDFium build notices are included in
`src/slidetransit/licenses/pypdfium2-5.3.0`. Platform-specific dependency wheels also
carry their own native build notices. This project does not bundle the PDFium binary.

The viewer embeds Noto Sans Regular and Liberation Serif Regular, both SIL OFL 1.1.
Genuine fixtures embed subsets of Noto Sans, Noto Sans CJK SC and, for one font test,
Liberation Serif. Full font licenses are in `src/slidetransit/licenses`; no commercial
system font binary is included. Fonts were loaded through a task-owned fontconfig
directory during the recorded LibreOfficeDev exports. The fixture generation script
requires an independently supplied lawful font directory; it does not install fonts
globally. Upstream sources: [Noto fonts](https://github.com/notofonts/noto-fonts),
[Noto CJK](https://github.com/notofonts/noto-cjk),
[Liberation fonts](https://github.com/liberationfonts/liberation-fonts).

Competitor source code is not included or copied. office2pdf and pptxdiff were inspected
under Apache-2.0; PPTLint under MIT. Anthropic's pptx workflow carries a separate
restricted license, so its material is referenced for baseline discussion only and
is not redistributed or used as a component. See `docs/competitive-baseline.md`.
