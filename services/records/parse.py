"""Parse a report PDF into header fields, a title and sections (W2 ingest: 'parse PDF', 'chunk by section').

Text PDFs only (decision 14). The layout this expects is the network's report layout: a header
block of `Key: value` lines ending at `Report ID:`, a title line, then sections whose headings are
short lines without closing punctuation. Anything that does not fit falls back to fixed-size chunks,
so an unfamiliar layout still gets indexed rather than dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

HEADER_KEYS = {"patient", "patient id", "age / sex", "phone", "abha", "mrn", "report date", "report id"}
MAX_CHUNK_CHARS = 1200


@dataclass
class Section:
    heading: str
    body: str
    page: int


@dataclass
class ParsedReport:
    header: dict[str, str]
    title: str
    sections: list[Section] = field(default_factory=list)
    pages: int = 0

    @property
    def report_ref(self) -> str | None:
        return self.header.get("report id")

    @property
    def report_date(self) -> str | None:
        return self.header.get("report date")


def _is_heading(line: str, nxt: str | None) -> bool:
    s = line.strip()
    if not s or nxt is None or len(s) > 60 or len(s.split()) > 9:
        return False
    if s[-1] in ".,;:" or not s[0].isupper():
        return False
    if ":" in s and any(ch.isdigit() for ch in s):     # 'Haemoglobin: 12.1 g/dL' is a value, not a heading
        return False
    return True


VALUE_LINE = re.compile(r"^[A-Z][\w /().,+-]{1,40}:\s*\S")


def _is_value_line(line: str) -> bool:
    s = line.strip()
    return len(s) <= 70 and bool(VALUE_LINE.match(s)) and any(ch.isdigit() for ch in s)


def parse_pdf(path: str | Path) -> ParsedReport:
    reader = PdfReader(str(path))
    lines: list[tuple[int, str]] = []
    for pno, page in enumerate(reader.pages, start=1):
        for ln in (page.extract_text() or "").splitlines():
            if ln.strip():
                lines.append((pno, ln.rstrip()))
    header: dict[str, str] = {}
    i = 0
    # header block: everything up to and including 'Report ID:'
    for j, (_, ln) in enumerate(lines):
        if ":" in ln:
            k, v = ln.split(":", 1)
            if k.strip().lower() in HEADER_KEYS:
                header[k.strip().lower()] = v.strip()
                if k.strip().lower() == "report id":
                    i = j + 1
                    break
    title = lines[i][1].strip() if i < len(lines) else ""
    body = lines[i + 1:] if i else lines
    sections: list[Section] = []
    cur: Section | None = None
    for idx, (pno, ln) in enumerate(body):
        nxt = body[idx + 1][1] if idx + 1 < len(body) else None
        if _is_heading(ln, nxt):
            cur = Section(heading=ln.strip(), body="", page=pno)
            sections.append(cur)
        else:
            if cur is None:
                cur = Section(heading="Report", body="", page=pno)
                sections.append(cur)
            # a 'Name: value' line stays on its own line; wrapped prose is joined back into sentences
            sep = "\n" if _is_value_line(ln) or (cur.body and _is_value_line(cur.body.rsplit("\n", 1)[-1])) else " "
            cur.body = f"{cur.body}{sep}{ln.strip()}".strip()
    # a long title wraps onto a second line, which lands either as an empty 'heading' or as a
    # heading-less first section
    while len(sections) > 1 and not sections[0].body:
        title = f"{title} {sections.pop(0).heading}"
    if sections and sections[0].heading == "Report" and len(sections) > 1 and len(sections[0].body) < 80 \
            and not sections[0].body.endswith("."):
        title = f"{title} {sections.pop(0).body}"
    sections = [s for s in sections if s.body]
    return ParsedReport(header=header, title=title, sections=sections, pages=len(reader.pages))


def split_long(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split on sentence boundaries so no chunk exceeds `limit` characters."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if cur and len(cur) + len(sent) + 1 > limit:
            parts.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return parts
