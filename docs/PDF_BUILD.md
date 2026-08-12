# Building the PDF edition

The PDF edition is generated from the canonical Markdown; no combined book source is maintained.

## Requirements

- Python 3.10 or later
- No Python packages, browser, TeX distribution, or proprietary fonts are required

The dependency-free renderer uses the PDF core fonts (Times, Helvetica, and Courier), embeds the existing RGB PNG chapter artwork without recompressing it, and creates a US Letter document with print margins, running heads, page numbers, and clickable external links. Mermaid source is retained as a compact monospace diagram when no browser-based Mermaid renderer is involved.

## Build

From the repository root, run:

```sh
./scripts/build-pdf.sh
```

The result is written to `dist/inside-globant.pdf`. The script creates `dist/` when needed and replaces the previous PDF after a successful render.

## Source order and validation

`CONTENTS.md` is the editorial authority for ordering. The build reads its chapter links, verifies there are exactly 70 chapters numbered consecutively from 0 through 69, and groups them under the five numerically ordered Part `README.md` files. It includes the Preface and About This Book before the Parts, followed by every appendix and research aid declared in `CONTENTS.md`.

Each chapter starts on a new page. The build also fails unless exactly 70 distinct chapter PNGs were embedded. Repository-only breadcrumbs and previous/next navigation remain in Markdown for GitHub but are filtered from the print edition.

For optional post-build inspection, Poppler tools can report metadata and extract text:

```sh
pdfinfo dist/inside-globant.pdf
pdftotext dist/inside-globant.pdf -
```
