#!/usr/bin/env python3
"""Check a Slidev PDF export for content that runs off the slide.

Two independent signals, because neither alone is enough:

1. GEOMETRY -- anything whose bounding box crosses the page edge. Catches
   content that straddles the boundary (a long unbreakable line, a
   negative margin, an oversized figure).

2. COMPLETENESS -- text present in slides.md but missing from the rendered
   page. This is the important one: when content overflows a Slidev slide,
   Chrome clips it and drops the glyphs from the PDF altogether, so there
   is no bounding box left to measure. A slide that silently loses its last
   nine bullets looks geometrically perfect. Needs --slides.

Usage:
    python3 tools/check_slides.py deck.pdf --slides slides.md
    python3 tools/check_slides.py deck.pdf --slides slides.md --json
    python3 tools/check_slides.py deck.pdf --slides slides.md --annotate /tmp/ov

Exit status is 1 when anything at or above --fail-on is found, so it drops
straight into an edit / export / check loop.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pymupdf
except ImportError:  # pragma: no cover
    sys.exit("pymupdf is required: pip3 install pymupdf")

# Slidev's default canvas width in CSS px; overridden by slides.md frontmatter.
DEFAULT_CANVAS_WIDTH = 980

SEVERITY_ORDER = {"none": 0, "warn": 1, "error": 2}


# --------------------------------------------------------------------------
# slides.md parsing
# --------------------------------------------------------------------------

FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
SEPARATOR_RE = re.compile(r"^-{3,}\s*$")
YAML_KEY_RE = re.compile(r"^[A-Za-z_][\w.\-]*\s*:(\s|$)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)")
SLOT_RE = re.compile(r"^::[\w-]*::\s*$")
TABLE_RULE_RE = re.compile(r"^[\s|:\-]+$")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
TAG_RE = re.compile(r"<[^>\n]*>")
IMPORT_RE = re.compile(r"^<<<")

# Named/numeric entities are markup, not glyphs: "&nbsp;" must not become the
# word "nbsp" in the text we expect to find on the page.
ENTITY_RE = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]{1,10});")
ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": chr(34), "&#39;": "'", "&apos;": "'"}


@dataclass
class Slide:
    index: int  # 1-based
    line: int  # 1-based line in slides.md where the slide starts
    title: str
    body: list[str]  # body lines, frontmatter excluded
    body_start: int  # 1-based line number of body[0]
    frontmatter: str = ""


def _is_frontmatter(body: list[str]) -> bool:
    """True if a chunk between two `---` lines looks like slide frontmatter."""
    keys = 0
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if raw[:1] in " \t" or line.startswith("- "):
            continue  # nested YAML
        if YAML_KEY_RE.match(line):
            keys += 1
            continue
        return False
    return keys > 0


def _title_of(body: list[str]) -> str:
    for raw in body:
        line = raw.strip()
        if not line or line.startswith(("<!--", "<", ":")):
            continue
        heading = HEADING_RE.match(line)
        return (heading.group(1) if heading else line)[:70]
    return "(no title)"


def parse_slides(md_path: Path) -> tuple[list[Slide], int]:
    """Split slides.md into slides. Returns (slides, canvas_width)."""
    lines = md_path.read_text(encoding="utf-8").split("\n")

    fence: str | None = None
    seps: list[int] = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if fence is not None:
            if set(line) <= {fence[0]} and len(line) >= len(fence):
                fence = None
            continue
        opening = FENCE_RE.match(line)
        if opening:
            fence = opening.group(1)
            continue
        if SEPARATOR_RE.match(raw):
            seps.append(i)

    bounds = [-1, *seps, len(lines)]
    chunks = [(a + 1, b) for a, b in zip(bounds, bounds[1:])]

    i = 0
    canvas_width = DEFAULT_CANVAS_WIDTH
    if seps and seps[0] == 0 and len(chunks) > 1:  # deck frontmatter
        for raw in lines[chunks[1][0] : chunks[1][1]]:
            m = re.match(r"^canvasWidth:\s*(\d+)", raw.strip())
            if m:
                canvas_width = int(m.group(1))
        i = 2

    slides: list[Slide] = []
    pending: tuple[int, int] | None = None  # per-slide frontmatter chunk
    while i < len(chunks):
        start, end = chunks[i]
        body = lines[start:end]
        if i + 1 < len(chunks) and _is_frontmatter(body):
            pending = pending or (start, end)
            i += 1
            continue
        slides.append(
            Slide(
                index=len(slides) + 1,
                line=(pending[0] if pending else start) + 1,
                title=_title_of(body),
                body=body,
                body_start=start + 1,
                frontmatter="\n".join(lines[pending[0] : pending[1]]) if pending else "",
            )
        )
        pending = None
        i += 1

    return slides, canvas_width


# --------------------------------------------------------------------------
# Expected-text extraction: what should be visible once slides.md renders
# --------------------------------------------------------------------------


@dataclass
class ExpectedLine:
    lineno: int  # 1-based line in slides.md
    text: str  # normalized, whitespace-free
    words: list[str]  # normalized words worth searching for
    raw: str  # for reporting


def expected_lines(slide: Slide, *, min_word_chars: int) -> list[ExpectedLine]:
    """The text each source line of a slide should contribute to the render.

    Whitespace is dropped because PDF text extraction reflows spaces
    unpredictably; comparison is per source line, which survives the
    repetitive content (tables, near-identical log rows) that defeats a
    character-level diff.
    """
    out: list[ExpectedLine] = []

    # Drop presenter notes and style/script blocks before anything else, but
    # keep line numbering intact so findings point at the right source line.
    blob = "\n".join(slide.body)
    for pattern in (
        r"<!--.*?-->",
        r"<style[^>]*>.*?</style>",
        r"<script[^>]*>.*?</script>",
    ):
        blob = re.sub(
            pattern,
            lambda m: re.sub(r"[^\n]", "", m.group(0)),  # blank it, keep newlines
            blob,
            flags=re.S | re.I,
        )
    body = blob.split("\n")

    fence: str | None = None
    for offset, raw in enumerate(body):
        lineno = slide.body_start + offset
        line = raw.strip()

        if fence is not None:
            if set(line) <= {fence[0]} and len(line) >= len(fence) and line:
                fence = None
                continue
            text = line  # code renders verbatim
        else:
            opening = FENCE_RE.match(line)
            if opening:
                fence = opening.group(1)
                continue
            if not line or SLOT_RE.match(line) or IMPORT_RE.match(line):
                continue
            text = _strip_markdown(line)

        normalized = _normalize(text)
        if not normalized:
            continue
        words = [w for w in (_normalize(t) for t in text.split()) if len(w) >= min_word_chars]
        out.append(ExpectedLine(lineno=lineno, text=normalized, words=words, raw=text.strip()))

    return out


def _strip_markdown(line: str) -> str:
    """Reduce a markdown/HTML source line to the words it should render as."""
    text = line
    for entity, replacement in ENTITIES.items():
        text = text.replace(entity, replacement)
    text = ENTITY_RE.sub(" ", text)  # &nbsp; and friends are markup, not words
    text = IMAGE_RE.sub(" ", text)  # alt text is not rendered
    text = LINK_RE.sub(lambda m: m.group(1), text)  # keep the label, drop the URL
    text = TAG_RE.sub(" ", text)  # HTML/Vue tags, incl. v-click directives
    if TABLE_RULE_RE.match(text) and "|" in text:
        return ""
    text = text.replace("|", " ")
    text = HEADING_RE.sub(r"\1", text)
    text = re.sub(r"^\s*>+\s?", "", text)
    text = LIST_MARKER_RE.sub("", text)
    return text


def _normalize(text: str) -> str:
    """Fold text down to comparable characters: letters and digits only.

    Everything else is dropped on both sides of the comparison -- emphasis
    markers, backticks, table pipes, box-drawing borders, and the curly
    quotes and en-dashes markdown-it's typographer substitutes on the way
    to the page. That keeps `ssl_history` matching ssl_history instead of
    an emphasis-stripped "sslhistory", at the cost of no longer noticing
    punctuation-only content.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(ch for ch in text if ch.isalnum())


def page_text(page: pymupdf.Page) -> str:
    return _normalize(page.get_text())


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass
class Finding:
    page: int
    severity: str
    kind: str
    sides: dict[str, float] = field(default_factory=dict)
    bbox: list[float] = field(default_factory=list)
    text: str = ""
    detail: str = ""
    source_lines: tuple[int, int] | None = None
    slide: int | None = None
    slide_line: int | None = None
    slide_title: str = ""

    def describe(self) -> str:
        parts = [self.kind]
        if self.sides:
            parts.append(", ".join(f"{s} {v:+.1f}px" for s, v in self.sides.items()))
        if self.detail:
            parts.append(self.detail)
        body = ": ".join(parts)
        if self.text:
            body += f'  "{self.text}"'
        return body


def _outside(box: pymupdf.Rect, limit: pymupdf.Rect, tol: float) -> dict[str, float]:
    out = {
        "left": limit.x0 - box.x0,
        "top": limit.y0 - box.y0,
        "right": box.x1 - limit.x1,
        "bottom": box.y1 - limit.y1,
    }
    return {side: amount for side, amount in out.items() if amount > tol}


def _clearance(box: pymupdf.Rect, limit: pymupdf.Rect) -> dict[str, float]:
    return {
        "left": box.x0 - limit.x0,
        "top": box.y0 - limit.y0,
        "right": limit.x1 - box.x1,
        "bottom": limit.y1 - box.y1,
    }


def check_geometry(
    page: pymupdf.Page,
    *,
    scale: float,
    margin_px: float,
    near_px: float,
    tol_px: float,
    check_graphics: bool,
    check_overlap: bool,
    accurate: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    page_box = pymupdf.Rect(page.rect)
    margin_pt = margin_px / scale
    safe = page_box + (margin_pt, margin_pt, -margin_pt, -margin_pt)
    tol_pt = tol_px / scale
    near_pt = near_px / scale
    number = page.number + 1

    def px_box(box: pymupdf.Rect) -> list[float]:
        return [round(v * scale, 1) for v in (box.x0, box.y0, box.x1, box.y1)]

    def px_sides(sides: dict[str, float]) -> dict[str, float]:
        return {s: round(v * scale, 1) for s, v in sides.items()}

    flags = pymupdf.TEXTFLAGS_DICT
    if accurate:
        flags |= pymupdf.TEXT_ACCURATE_BBOXES

    text_lines: list[tuple[pymupdf.Rect, str]] = []
    for block in page.get_text("dict", flags=flags)["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            joined = "".join(s["text"] for s in line["spans"]).strip()
            if not joined:
                continue
            text_lines.append((pymupdf.Rect(line["bbox"]), joined))
            for span in line["spans"]:
                snippet = span["text"].strip()
                if not snippet:
                    continue
                box = pymupdf.Rect(span["bbox"])
                over = _outside(box, safe, tol_pt)
                if over:
                    findings.append(
                        Finding(
                            page=number,
                            severity="error",
                            kind="text-overflow",
                            sides=px_sides(over),
                            bbox=px_box(box),
                            text=snippet[:80],
                        )
                    )
                elif near_px > 0:
                    tight = {s: v for s, v in _clearance(box, safe).items() if v < near_pt}
                    if tight:
                        findings.append(
                            Finding(
                                page=number,
                                severity="warn",
                                kind="text-near-edge",
                                sides=px_sides(tight),
                                bbox=px_box(box),
                                text=snippet[:80],
                            )
                        )

    if check_graphics:
        page_area = page_box.get_area() or 1.0
        for drawing in page.get_drawings():
            box = pymupdf.Rect(drawing["rect"])
            if box.is_empty or box.is_infinite:
                continue
            if (box & page_box).is_empty:
                continue  # Chrome paints scratch rects outside the page box
            if box.get_area() >= 0.9 * page_area and box.contains(safe):
                continue  # legitimate full-bleed background
            over = _outside(box, page_box, tol_pt)
            if over:
                findings.append(
                    Finding(
                        page=number,
                        severity="warn",
                        kind="graphic-overflow",
                        sides=px_sides(over),
                        bbox=px_box(box),
                    )
                )
        for image in page.get_image_info():
            box = pymupdf.Rect(image["bbox"])
            if box.is_empty or box.is_infinite or (box & page_box).is_empty:
                continue
            over = _outside(box, page_box, tol_pt)
            if over:
                findings.append(
                    Finding(
                        page=number,
                        severity="warn",
                        kind="image-overflow",
                        sides=px_sides(over),
                        bbox=px_box(box),
                    )
                )

    if check_overlap:
        for i, (box_a, text_a) in enumerate(text_lines):
            for box_b, text_b in text_lines[i + 1 :]:
                hit = box_a & box_b
                if hit.is_empty:
                    continue
                smaller = min(box_a.get_area(), box_b.get_area()) or 1.0
                if hit.get_area() / smaller < 0.35:
                    continue
                findings.append(
                    Finding(
                        page=number,
                        severity="warn",
                        kind="text-overlap",
                        bbox=px_box(hit),
                        text=f"{text_a[:40]} / {text_b[:40]}",
                    )
                )

    return findings


def check_completeness(
    page: pymupdf.Page,
    slide: Slide,
    *,
    min_line_chars: int,
    min_word_chars: int,
) -> list[Finding]:
    """Report slides.md text that never made it onto the rendered page.

    A whole source line absent from the render is an error -- that is what
    clipped overflow looks like. A line that lost only part of itself is
    graded by how much went missing: mostly gone is an error, a word or two
    is a warning (often a horizontal truncation, sometimes just markup this
    script normalized imperfectly).

    Whole lines are looked up anywhere on the page, so a layout that renders
    content out of source order does not cause a cascade of false positives.
    Individual words are looked up only *after* the last thing that matched,
    because slides repeat themselves -- without that cursor, a dropped
    "line fourteen ..." bullet looks present just because "line" survives
    nine bullets higher up.
    """
    lines = expected_lines(slide, min_word_chars=min_word_chars)
    if not lines:
        return []
    actual = page_text(page)
    number = page.number + 1

    gone: list[ExpectedLine] = []  # fully missing, awaiting grouping
    findings: list[Finding] = []
    last_lineno = lines[-1].lineno
    cursor = 0

    def flush() -> None:
        if not gone:
            return
        first, last = gone[0].lineno, gone[-1].lineno
        where = f"slides.md:{first}" + (f"-{last}" if last != first else "")
        detail = f"{len(gone)} line(s) absent from the render, {where}"
        if last == last_lineno:
            detail += " (runs to the end of the slide — classic bottom overflow)"
        findings.append(
            Finding(
                page=number,
                severity="error",
                kind="missing-text",
                text=gone[0].raw[:70],
                detail=detail,
                source_lines=(first, last),
            )
        )
        gone.clear()

    for line in lines:
        if len(line.text) < min_line_chars:
            continue
        found = actual.find(line.text)
        if found >= 0:
            cursor = max(cursor, found + len(line.text))
            flush()
            continue

        missing: list[str] = []
        missing_chars = present_chars = 0
        probe = cursor
        for word in line.words:
            at = actual.find(word, probe)
            if at >= 0:
                probe = at + len(word)
                present_chars += len(word)
            else:
                missing.append(word)
                missing_chars += len(word)
        cursor = max(cursor, probe)

        if not line.words or not present_chars:
            gone.append(line)
            continue

        flush()
        if not missing:
            continue  # every word is there, just split across elements
        fraction = missing_chars / (missing_chars + present_chars)
        # Missing words that are exactly the tail of the line mean the line
        # was cut off part-way across: a horizontal truncation, not a
        # normalization artifact.
        truncated = missing == line.words[-len(missing) :]
        findings.append(
            Finding(
                page=number,
                severity="error" if truncated or fraction >= 0.5 else "warn",
                kind="line-truncated" if truncated else "partial-text",
                text=line.raw[:70],
                detail=(
                    f"slides.md:{line.lineno} rendered without {len(missing)}/"
                    f"{len(line.words)} word(s) ({fraction:.0%} of the text)"
                    + (", cut off from the end of the line" if truncated else "")
                    + f": {', '.join(w[:24] for w in missing[:4])}"
                ),
                source_lines=(line.lineno, line.lineno),
            )
        )
    flush()
    return findings


def annotate(page: pymupdf.Page, findings: list[Finding], scale: float, out: Path, dpi: int) -> None:
    """Render the page with offending boxes outlined, for eyeballing."""
    colors = {"error": (1, 0, 0), "warn": (1, 0.6, 0)}
    for finding in findings:
        if not finding.bbox:
            continue
        box = pymupdf.Rect(*[v / scale for v in finding.bbox])
        page.draw_rect(box, color=colors.get(finding.severity, (0, 0, 1)), width=0.8)
    page.draw_rect(page.rect + (1, 1, -1, -1), color=(0, 0.5, 1), width=0.5, dashes="[3 3] 0")
    page.get_pixmap(dpi=dpi).save(out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flag Slidev slides whose content runs off the page.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("pdf", type=Path, help="Slidev PDF export")
    parser.add_argument("--slides", type=Path, help="slides.md (enables the completeness check)")
    parser.add_argument("--canvas-width", type=float, help="Slidev canvasWidth px (default: from --slides)")
    parser.add_argument("--margin", type=float, default=0.0, help="safe-area inset from the page edge, px")
    parser.add_argument("--near", type=float, default=6.0, help="warn within this many px of the safe area (0 off)")
    parser.add_argument("--tolerance", type=float, default=1.5, help="ignore overflow smaller than this, px")
    parser.add_argument("--min-line-chars", type=int, default=4, help="ignore source lines shorter than this")
    parser.add_argument("--min-word-chars", type=int, default=4, help="ignore words shorter than this")
    parser.add_argument("--pages", help="only check these pages, e.g. 3,7-9")
    parser.add_argument("--no-geometry", action="store_true", help="skip bounding-box checks")
    parser.add_argument("--no-completeness", action="store_true", help="skip the missing-text check")
    parser.add_argument("--no-graphics", action="store_true", help="skip vector/image bbox checks")
    parser.add_argument("--check-overlap", action="store_true", help="also report colliding text lines")
    parser.add_argument("--fast", action="store_true", help="font-metric bboxes instead of exact glyph bboxes")
    parser.add_argument("--annotate", type=Path, help="write annotated PNGs of flagged pages here")
    parser.add_argument("--annotate-dpi", type=int, default=110, help="DPI for --annotate output")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--quiet", action="store_true", help="only print flagged pages")
    parser.add_argument(
        "--fail-on", choices=("error", "warn", "none"), default="error",
        help="minimum severity that exits non-zero",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        return _die(f"no such PDF: {args.pdf}", args.json)

    slides: list[Slide] = []
    canvas_width = args.canvas_width or DEFAULT_CANVAS_WIDTH
    if args.slides:
        if not args.slides.exists():
            return _die(f"no such slides file: {args.slides}", args.json)
        slides, parsed_width = parse_slides(args.slides)
        if args.canvas_width is None:
            canvas_width = parsed_width

    wanted = _parse_pages(args.pages) if args.pages else None
    doc = pymupdf.open(args.pdf)
    if not doc.page_count:
        return _die("PDF has no pages", args.json)
    scale = canvas_width / doc[0].rect.width

    # PDF page -> slide, 1:1 for a plain export.
    notes: list[str] = []
    page_to_slide: list[Slide] = []
    if slides:
        page_to_slide = slides
        if len(page_to_slide) != doc.page_count:
            notes.append(
                f"{doc.page_count} PDF pages vs {len(page_to_slide)} slides from "
                f"{args.slides.name}; skipping the completeness check "
                "(exported --with-clicks, or a slide paginated?)"
            )
            page_to_slide = []

    if args.annotate:
        args.annotate.mkdir(parents=True, exist_ok=True)

    findings: list[Finding] = []
    for page in doc:
        number = page.number + 1
        if wanted and number not in wanted:
            continue
        page_findings: list[Finding] = []
        if not args.no_geometry:
            page_findings += check_geometry(
                page,
                scale=scale,
                margin_px=args.margin,
                near_px=args.near,
                tol_px=args.tolerance,
                check_graphics=not args.no_graphics,
                check_overlap=args.check_overlap,
                accurate=not args.fast,
            )
        slide = page_to_slide[page.number] if page.number < len(page_to_slide) else None
        if slide and not args.no_completeness:
            page_findings += check_completeness(
                page,
                slide,
                min_line_chars=args.min_line_chars,
                min_word_chars=args.min_word_chars,
            )
        for finding in page_findings:
            if slide:
                finding.slide, finding.slide_line, finding.slide_title = (
                    slide.index, slide.line, slide.title,
                )
        if page_findings and args.annotate:
            annotate(page, page_findings, scale, args.annotate / f"page-{number:03d}.png", args.annotate_dpi)
        findings += page_findings

    errors = sum(1 for f in findings if f.severity == "error")
    warns = sum(1 for f in findings if f.severity == "warn")
    page_px = (round(doc[0].rect.width * scale), round(doc[0].rect.height * scale))

    if args.json:
        print(json.dumps({
            "pdf": str(args.pdf),
            "pages": doc.page_count,
            "canvas": {"width": page_px[0], "height": page_px[1]},
            "errors": errors,
            "warnings": warns,
            "notes": notes,
            "findings": [{
                "page": f.page,
                "slide": f.slide,
                "slides_md_line": f.slide_line,
                "slide_title": f.slide_title,
                "severity": f.severity,
                "kind": f.kind,
                "sides_px": f.sides,
                "bbox_px": f.bbox,
                "source_lines": list(f.source_lines) if f.source_lines else None,
                "detail": f.detail,
                "text": f.text,
            } for f in findings],
        }, indent=2))
    else:
        if not args.quiet:
            print(f"{args.pdf}: {doc.page_count} pages, slide canvas {page_px[0]}x{page_px[1]} px")
            for note in notes:
                print(f"  note: {note}")
        for number in sorted({f.page for f in findings}):
            group = [f for f in findings if f.page == number]
            label = f"page {number}"
            first = group[0]
            if first.slide:
                label += f" (slide {first.slide}, {args.slides}:{first.slide_line} — {first.slide_title})"
            print(f"\n{label}")
            for finding in sorted(group, key=lambda f: f.severity != "error"):
                marker = "ERROR" if finding.severity == "error" else "warn "
                print(f"  {marker} {finding.describe()}")
        print(f"\n{'clean' if not findings else f'{errors} error(s), {warns} warning(s)'}")

    threshold = SEVERITY_ORDER[args.fail_on]
    worst = max((SEVERITY_ORDER[f.severity] for f in findings), default=0)
    return 1 if threshold and worst >= threshold else 0


def _die(message: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"error": message}))
    else:
        print(f"error: {message}", file=sys.stderr)
    return 2


def _parse_pages(spec: str) -> set[int]:
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start), int(end) + 1))
        else:
            pages.add(int(part))
    return pages


if __name__ == "__main__":
    sys.exit(main())
