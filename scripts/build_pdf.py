#!/usr/bin/env python3
"""Build the print edition of Inside Globant with no third-party dependencies."""

from __future__ import annotations

import html
import re
import struct
import sys
import textwrap
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "inside-globant.pdf"
PAGE_W, PAGE_H = 612, 792  # US Letter, points
LEFT, RIGHT, TOP, BOTTOM = 66, 66, 62, 56
CONTENT_W = PAGE_W - LEFT - RIGHT


def ascii_text(value: str) -> str:
    replacements = {
        "—": "-", "–": "-", "−": "-", "→": "->", "←": "<-", "↔": "<->",
        "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "·": " | ",
        "×": "x", "≤": "<=", "≥": ">=", "≈": "~=", "®": "(R)", "™": "(TM)",
        "•": "*", "‑": "-", " ": " ", "€": "EUR", "£": "GBP", "¥": "JPY",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value.encode("cp1252", "replace").decode("cp1252")


def pdf_string(value: str) -> str:
    value = ascii_text(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return value.replace("\r", " ").replace("\n", " ")


def clean_inline(value: str) -> tuple[str, list[str]]:
    urls: list[str] = []

    def link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        if url.startswith(("http://", "https://", "mailto:")):
            urls.append(url)
        return label

    value = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\(([^)]+)\)", link, value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"[*_~]", "", value)
    value = html.unescape(value)
    return ascii_text(value.strip()), urls


class PDF:
    def __init__(self) -> None:
        self.pages: list[dict] = []
        self.images: dict[Path, tuple[str, int, int, bytes]] = {}
        self.outline: list[tuple[int, str, int]] = []
        self.chapter_pages: list[tuple[str, int, int]] = []
        self.page(title="")

    @property
    def current(self) -> dict:
        return self.pages[-1]

    def page(self, title: str = "") -> None:
        self.pages.append({"ops": [], "links": [], "title": title})
        self.y = PAGE_H - TOP

    def ensure(self, height: float, title: str = "") -> None:
        if self.y - height < BOTTOM:
            self.page(title)

    def text(self, text: str, x: float, y: float, size: float = 10.5,
             font: str = "R", color: tuple[float, float, float] = (0.12, 0.15, 0.18)) -> None:
        r, g, b = color
        self.current["ops"].append(
            f"BT /F{font} {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x:.2f} {y:.2f} Tm ({pdf_string(text)}) Tj ET"
        )

    def rule(self, y: float, width: float = CONTENT_W) -> None:
        self.current["ops"].append(f"0.18 0.45 0.55 RG 0.8 w {LEFT} {y:.2f} m {LEFT + width} {y:.2f} l S")

    def wrapped(self, text: str, *, x: float = LEFT, width: float = CONTENT_W,
                size: float = 10.5, leading: float = 14.2, font: str = "R",
                before: float = 0, after: float = 6, indent: float = 0,
                color: tuple[float, float, float] = (0.12, 0.15, 0.18), urls: list[str] | None = None) -> None:
        self.y -= before
        # Conservative average glyph width keeps prose inside the right margin.
        chars = max(12, int(width / (size * (0.53 if font != "C" else 0.60))))
        lines = textwrap.wrap(text, width=chars, break_long_words=True, break_on_hyphens=True,
                              replace_whitespace=False, drop_whitespace=True) or [""]
        for index, line in enumerate(lines):
            self.ensure(leading)
            line_x = x + (indent if index == 0 else 0)
            self.text(line, line_x, self.y, size, font, color)
            if urls:
                for url in urls:
                    self.current["links"].append((line_x, self.y - 2, min(width, len(line) * size * .53), leading, url))
            self.y -= leading
        self.y -= after

    def heading(self, text: str, level: int) -> None:
        sizes = {1: 23, 2: 15, 3: 12.5, 4: 11}
        size = sizes.get(level, 11)
        if level == 1:
            self.ensure(74)
            self.y -= 9
        else:
            self.ensure(size * 2.6)
            self.y -= 8
        clean, _ = clean_inline(text)
        self.wrapped(clean, size=size, leading=size * 1.18, font="B", after=7,
                     color=(0.06, 0.25, 0.31))
        if level == 1:
            self.rule(self.y + 3)
            self.y -= 9

    def add_image(self, path: Path) -> None:
        data = path.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Only PNG chapter artwork is supported: {path}")
        width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", data[16:29])
        if (depth, color, interlace) != (8, 2, 0):
            raise ValueError(f"Expected non-interlaced 8-bit RGB PNG: {path}")
        chunks, pos = [], 8
        while pos < len(data):
            length = struct.unpack(">I", data[pos:pos + 4])[0]
            kind = data[pos + 4:pos + 8]
            if kind == b"IDAT":
                chunks.append(data[pos + 8:pos + 8 + length])
            pos += 12 + length
        name = f"Im{len(self.images) + 1}"
        self.images[path] = (name, width, height, b"".join(chunks))
        display_w = min(CONTENT_W, 430)
        display_h = display_w * height / width
        self.ensure(display_h + 14)
        x = (PAGE_W - display_w) / 2
        self.current["ops"].append(f"q {display_w:.2f} 0 0 {display_h:.2f} {x:.2f} {self.y-display_h:.2f} cm /{name} Do Q")
        self.y -= display_h + 13

    def finish(self, output: Path) -> None:
        objects: list[bytes] = [b""]

        def add(data: str | bytes) -> int:
            objects.append(data.encode("cp1252") if isinstance(data, str) else data)
            return len(objects) - 1

        font_r = add("<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman /Encoding /WinAnsiEncoding >>")
        font_b = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        font_i = add("<< /Type /Font /Subtype /Type1 /BaseFont /Times-Italic /Encoding /WinAnsiEncoding >>")
        font_c = add("<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
        image_ids: dict[str, int] = {}
        for name, width, height, stream in self.images.values():
            header = (f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                      f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
                      f"/DecodeParms << /Predictor 15 /Colors 3 /BitsPerComponent 8 /Columns {width} >> /Length {len(stream)} >>\nstream\n").encode()
            image_ids[name] = add(header + stream + b"\nendstream")
        pages_id = add("")
        page_ids: list[int] = []
        for number, page in enumerate(self.pages, 1):
            # Running furniture is intentionally added late so it stays consistent.
            if number > 1:
                title = page["title"] or "Inside Globant"
                self.text_on(page, ascii_text(title)[:72], LEFT, PAGE_H - 35, 8, "R", (.35, .38, .4))
                self.text_on(page, str(number), PAGE_W / 2 - 3, 29, 9, "R", (.3, .33, .35))
            stream = "\n".join(page["ops"]).encode("cp1252")
            content_id = add(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
            annots = []
            for x, y, w, h, url in page["links"]:
                annots.append(add(f"<< /Type /Annot /Subtype /Link /Rect [{x:.2f} {y:.2f} {x+w:.2f} {y+h:.2f}] /Border [0 0 0] /A << /S /URI /URI ({pdf_string(url)}) >> >>"))
            xobjs = " ".join(f"/{name} {oid} 0 R" for name, oid in image_ids.items())
            annots_ref = " /Annots [" + " ".join(f"{a} 0 R" for a in annots) + "]" if annots else ""
            page_ids.append(add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources << /Font << /FR {font_r} 0 R /FB {font_b} 0 R /FI {font_i} 0 R /FC {font_c} 0 R >> /XObject << {xobjs} >> >> /Contents {content_id} 0 R{annots_ref} >>"))
        objects[pages_id] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] >>".encode()
        catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R /PageLayout /OneColumn >>")
        info = add("<< /Title (Inside Globant) /Subject (Print edition) /Creator (Inside Globant reproducible PDF builder) >>")
        output.parent.mkdir(parents=True, exist_ok=True)
        raw = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for i, obj in enumerate(objects[1:], 1):
            offsets.append(len(raw)); raw.extend(f"{i} 0 obj\n".encode()); raw.extend(obj); raw.extend(b"\nendobj\n")
        xref = len(raw)
        raw.extend(f"xref\n0 {len(objects)}\n0000000000 65535 f \n".encode())
        for off in offsets[1:]: raw.extend(f"{off:010d} 00000 n \n".encode())
        raw.extend(f"trailer\n<< /Size {len(objects)} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        output.write_bytes(raw)

    @staticmethod
    def text_on(page: dict, value: str, x: float, y: float, size: float, font: str, color: tuple) -> None:
        r, g, b = color
        page["ops"].append(f"BT /F{font} {size} Tf {r} {g} {b} rg 1 0 0 1 {x} {y} Tm ({pdf_string(value)}) Tj ET")


NAV_RE = re.compile(r"^\s*(?:\*\*)?\[(?:Inside Globant|Previous Chapter|Next Chapter|Table of Contents|Back to Full Contents|Begin with Chapter)[^\n]*$")


def render_markdown(pdf: PDF, path: Path, *, part: bool = False) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if part:
        # The chapter directory and begin/back links are repository navigation; the
        # generated TOC already provides their print equivalent.
        lines = lines[:next((n for n, line in enumerate(lines) if line == "## Chapters"), len(lines))]
    i, paragraph = 0, []

    def flush() -> None:
        if not paragraph: return
        value, urls = clean_inline(" ".join(x.strip() for x in paragraph))
        paragraph.clear()
        if value and not NAV_RE.match(value):
            pdf.wrapped(value, urls=urls)

    while i < len(lines):
        line = lines[i]
        if NAV_RE.match(line) or ("[Inside Globant]" in line and "[Part " in line):
            flush(); i += 1; continue
        image_match = re.match(r"!\[[^]]*\]\(([^)]+)\)", line.strip())
        if image_match:
            flush(); image_path = (path.parent / image_match.group(1)).resolve(); pdf.add_image(image_path); i += 1; continue
        fence = re.match(r"^```(.*)$", line)
        if fence:
            flush(); language, block = fence.group(1).strip(), []; i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            if language == "mermaid": block.insert(0, "MERMAID DIAGRAM")
            for code_line in block or [""]:
                pdf.wrapped(ascii_text(code_line), size=7.1, leading=9.0, font="C", before=0, after=0,
                            x=LEFT + 8, width=CONTENT_W - 16, color=(.12, .18, .2))
            pdf.y -= 7; i += 1; continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush(); level = len(heading.group(1)); title, _ = clean_inline(heading.group(2))
            if level == 1:
                if len(pdf.pages) > 1 or pdf.y < PAGE_H - TOP - 5: pdf.page(title)
                outline_level = 1 if part else (2 if title.startswith("Chapter ") else 1)
                pdf.outline.append((outline_level, title, len(pdf.pages)))
                if title.startswith("Chapter "):
                    pdf.chapter_pages.append((title, len(pdf.pages), int(re.search(r"\d+", title).group())))
            pdf.heading(title, level); i += 1; continue
        if re.match(r"^\s*([-*+] |\d+[.)] )", line):
            flush(); marker, body = re.match(r"^\s*((?:[-*+])|(?:\d+[.)]))\s+(.+)$", line).groups()
            value, urls = clean_inline(body); bullet = "*" if not marker[0].isdigit() else marker
            pdf.wrapped(f"{bullet}  {value}", x=LEFT + 14, width=CONTENT_W - 20, indent=-10, urls=urls, after=3)
            i += 1; continue
        if line.startswith(">"):
            flush(); value, urls = clean_inline(line.lstrip("> "))
            pdf.wrapped(value, x=LEFT + 18, width=CONTENT_W - 36, font="I", before=3, after=7,
                        color=(.20, .27, .30), urls=urls); i += 1; continue
        if line.strip().startswith("|"):
            flush(); rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i]): rows.append(lines[i])
                i += 1
            for ri, row in enumerate(rows):
                value, urls = clean_inline(" | ".join(c.strip() for c in row.strip(" |").split("|")))
                pdf.wrapped(value, size=7.4, leading=9.5, font="B" if ri == 0 else "R", after=2, urls=urls)
            pdf.y -= 5; continue
        if not line.strip(): flush()
        else: paragraph.append(line)
        i += 1
    flush()


def ordered_sources() -> tuple[list[Path], list[tuple[Path, list[Path]]], list[Path]]:
    contents = (ROOT / "CONTENTS.md").read_text(encoding="utf-8")
    chapter_paths = [ROOT / p for p in re.findall(r"\((chapters/[^)]+\.md)\)", contents) if not p.endswith("README.md")]
    # De-duplicate while retaining the editorial order declared by CONTENTS.md.
    chapter_paths = list(dict.fromkeys(chapter_paths))
    if len(chapter_paths) != 70:
        raise RuntimeError(f"CONTENTS.md must declare exactly 70 chapters; found {len(chapter_paths)}")
    if [int(p.name.split("-", 1)[0]) for p in chapter_paths] != list(range(70)):
        raise RuntimeError("Chapter sequence in CONTENTS.md is not 0 through 69")
    parts: list[tuple[Path, list[Path]]] = []
    for readme in sorted((ROOT / "chapters").glob("part-*/README.md"), key=lambda p: int(re.search(r"part-(\d+)", str(p)).group(1))):
        parts.append((readme, [p for p in chapter_paths if p.parent == readme.parent]))
    appendix_paths = [ROOT / p for p in re.findall(r"\(((?:appendix|sources)/[^)]+\.md)\)", contents)]
    return [ROOT / "PREFACE.md", ROOT / "ABOUT-THIS-BOOK.md"], parts, list(dict.fromkeys(appendix_paths))


def main() -> None:
    front, parts, appendices = ordered_sources()
    pdf = PDF()
    # Title page.
    pdf.y = 545; pdf.text("INSIDE GLOBANT", 96, pdf.y, 34, "B", (.05, .25, .31)); pdf.y -= 32
    pdf.rule(pdf.y, 420); pdf.y -= 32
    pdf.wrapped("How a Global Technology Services Company Connects Business Problems with Global Engineering Talent",
                x=96, width=420, size=16, leading=22, font="R", color=(.20, .25, .27))
    pdf.text("PRINT EDITION", 96, 130, 9, "B", (.35, .45, .48))
    # Reserve a compact generated TOC; page references come from deterministic render order.
    toc_pages = []
    for n in range(3):
        pdf.page("Contents")
        if n == 0: pdf.heading("Contents", 1)
        else: pdf.heading("Contents (continued)", 2)
        toc_pages.append(pdf.current)
    toc_entries: list[tuple[int, str, int]] = []
    for source in front: render_markdown(pdf, source)
    for part_path, chapters in parts:
        render_markdown(pdf, part_path, part=True)
        for chapter in chapters: render_markdown(pdf, chapter)
    pdf.page("Appendices"); pdf.heading("Appendices", 1)
    for appendix in appendices: render_markdown(pdf, appendix)
    toc_entries = pdf.outline.copy()
    # Fill the reserved TOC pages after pagination is known.
    toc_index, toc = 0, toc_pages[0]; toc_y = PAGE_H - 108
    for level, title, page_no in toc_entries:
        if level > 2: continue
        if toc_y < 58:
            toc_index += 1
            if toc_index >= len(toc_pages): raise RuntimeError("Reserved table-of-contents pages exhausted")
            toc, toc_y = toc_pages[toc_index], PAGE_H - 92
        indent = 12 if level == 2 else 0; size = 7.5 if level == 2 else 9
        display = title
        max_chars = 78 if level == 2 else 70
        if len(display) > max_chars: display = display[:max_chars - 3] + "..."
        PDF.text_on(toc, display, LEFT + indent, toc_y, size, "R" if level == 2 else "B", (.12, .19, .21))
        PDF.text_on(toc, str(page_no), PAGE_W - RIGHT - 18, toc_y, size, "R", (.12, .19, .21))
        toc_y -= 8.2 if level == 2 else 12
    pdf.finish(OUT)
    image_count = len(pdf.images)
    if image_count != 70: raise RuntimeError(f"Expected 70 unique chapter images, rendered {image_count}")
    print(f"Built {OUT.relative_to(ROOT)}: {len(pdf.pages)} pages, 70 chapters, {image_count} images")


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f"build-pdf: {exc}", file=sys.stderr); raise
