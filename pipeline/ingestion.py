"""Document ingestion for VisualNote.

Phase 1 supports PDF only. The module is structured so PPTX and DOCX can be
added as additional `ingest_*` functions later without changing the public
`ingest(path)` dispatcher.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

from config import CONFIG

log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_STOPWORDS = {
    "the", "and", "for", "are", "with", "that", "this", "from", "have", "has",
    "was", "were", "but", "not", "you", "your", "into", "such", "than", "then",
    "they", "them", "its", "our", "any", "all", "can", "will", "would", "could",
    "should", "may", "might", "use", "used", "using", "one", "two", "three",
}


def _slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_len] or "untitled"


def _classify_heading_level(size: float, body_size: float) -> int:
    """Map a font size to a heading level relative to the body size."""
    if body_size <= 0:
        return 0
    ratio = size / body_size
    if ratio >= 1.8:
        return 1
    if ratio >= 1.5:
        return 2
    if ratio >= 1.2:
        return 3
    return 0


def _clean_text(text: str) -> str:
    """Normalize whitespace and strip unrepresentable glyphs that PyMuPDF surfaces as U+FFFD."""
    if not text:
        return ""
    text = text.replace("\uFFFD", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _extract_keywords(text: str, max_keywords: int = 25) -> List[str]:
    """Return a list of salient lowercase tokens, deduped, with stopwords removed."""
    if not text:
        return []
    counts = Counter()
    for match in _WORD_RE.finditer(text.lower()):
        word = match.group(0)
        if word in _STOPWORDS:
            continue
        counts[word] += 1
    return [w for w, _ in counts.most_common(max_keywords)]


def _page_body_size(page: fitz.Page) -> float:
    """Return the median text span size on the page; falls back to 11.0."""
    sizes: List[float] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                txt = (span.get("text") or "").strip()
                if not txt:
                    continue
                size = span.get("size")
                if isinstance(size, (int, float)) and size > 0:
                    sizes.append(float(size))
    if not sizes:
        return 11.0
    return statistics.median(sizes)


def _extract_images(
    doc: fitz.Document,
    out_dir: Path,
) -> List[Dict[str, Any]]:
    """Extract every embedded image to disk and return its metadata index."""
    out_dir.mkdir(parents=True, exist_ok=True)
    index: List[Dict[str, Any]] = []
    seen_xrefs: set = set()
    for page_num, page in enumerate(doc, start=1):
        try:
            items = page.get_images(full=True)
        except Exception:
            items = []
        for img_idx, item in enumerate(items):
            xref = item[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                info = doc.extract_image(xref)
            except Exception as exc:
                log.warning("Failed to extract image xref=%s: %s", xref, exc)
                continue
            ext = (info.get("ext") or "png").lower()
            if ext not in {"png", "jpg", "jpeg", "webp"}:
                ext = "png"
            fname = f"img_p{page_num:03d}_n{img_idx:02d}_x{xref}.{ext}"
            fpath = out_dir / fname
            try:
                fpath.write_bytes(info["image"])
            except Exception as exc:
                log.warning("Failed to write image %s: %s", fpath, exc)
                continue
            try:
                bbox = page.get_image_bbox(item)
                bbox_list = [float(bbox.x0), float(bbox.y0), float(bbox.x1), float(bbox.y1)]
            except Exception:
                bbox_list = None
            index.append(
                {
                    "path": str(fpath.relative_to(CONFIG.project_root)),
                    "abs_path": str(fpath),
                    "page": page_num,
                    "xref": xref,
                    "width": info.get("width"),
                    "height": info.get("height"),
                    "bbox": bbox_list,
                    "keywords": [],
                }
            )
    return index


def _extract_page_sections(
    doc: fitz.Document,
) -> List[Dict[str, Any]]:
    """Walk each page; build a flat list of sections keyed by heading size.

    Each pymupdf text block (a paragraph-like unit) is emitted as one block in
    the output. Headings are detected at the line level: a line whose dominant
    font size exceeds the page's body size by the heading ratio thresholds.
    """
    sections: List[Dict[str, Any]] = []
    current = {
        "heading": None,
        "level": 0,
        "page": 1,
        "blocks": [],
    }

    def _flush() -> None:
        if current["blocks"] or current["heading"]:
            sections.append(current)

    for page_num, page in enumerate(doc, start=1):
        body_size = _page_body_size(page)
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            btype = block.get("type")
            if btype != 0:
                continue
            lines = block.get("lines", []) or []
            if not lines:
                continue
            line_records: List[Dict[str, Any]] = []
            for line in lines:
                line_text = _clean_text(
                    "".join((span.get("text") or "") for span in line.get("spans", []))
                )
                if not line_text:
                    continue
                line_size = max(
                    (s.get("size", 0.0) for s in line.get("spans", [])),
                    default=0.0,
                )
                line_records.append({"text": line_text, "size": line_size})
            if not line_records:
                continue

            if len(line_records) == 1:
                # Single-line block — treat as a possible heading.
                rec = line_records[0]
                level = _classify_heading_level(rec["size"], body_size)
                if level >= 1:
                    _flush()
                    current = {
                        "heading": rec["text"],
                        "level": level,
                        "page": page_num,
                        "blocks": [],
                    }
                    continue
            paragraph_text = " ".join(rec["text"] for rec in line_records)
            current["blocks"].append(
                {
                    "type": "text",
                    "text": paragraph_text,
                    "page": page_num,
                }
            )
    _flush()
    return sections


def _attach_image_keywords(
    sections: List[Dict[str, Any]],
    image_index: List[Dict[str, Any]],
) -> None:
    """For each extracted image, attach keywords taken from its page's text."""
    pages_text: Dict[int, str] = {}
    for section in sections:
        for block in section.get("blocks", []):
            if block.get("type") != "text":
                continue
            p = block.get("page", 0)
            pages_text[p] = pages_text.get(p, "") + " " + block.get("text", "")
    pages_text[0] = " ".join(pages_text.values())  # fallback for missing page
    for img in image_index:
        page_text = pages_text.get(img["page"], pages_text[0])
        img["keywords"] = _extract_keywords(page_text)


def ingest_pdf(path: str | Path) -> Dict[str, Any]:
    """Parse a PDF and return the structured `doc_content` payload."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {p}")
    log.info("Opening PDF: %s", p)
    doc = fitz.open(p)
    try:
        title = (doc.metadata or {}).get("title") or p.stem
        log.info(
            "PDF has %d pages; extracting images + sections", doc.page_count
        )
        image_index = _extract_images(doc, CONFIG.extracted_assets_dir)
        sections = _extract_page_sections(doc)
        _attach_image_keywords(sections, image_index)
        raw_text = "\n\n".join(
            block["text"]
            for section in sections
            for block in section.get("blocks", [])
            if block.get("type") == "text"
        )
        doc_content: Dict[str, Any] = {
            "document_title": title,
            "source_path": str(p),
            "page_count": doc.page_count,
            "sections": sections,
            "raw_text": raw_text,
            "image_index": image_index,
        }
    finally:
        doc.close()
    log.info(
        "Ingested PDF: %d sections, %d images, %d raw text chars",
        len(sections),
        len(image_index),
        len(raw_text),
    )
    return doc_content


def save_doc_content(doc_content: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    out_path = out_path or (CONFIG.output_dir / "doc_content.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc_content, fh, ensure_ascii=False, indent=2)
    log.info("Wrote %s", out_path)
    return out_path


def load_doc_content(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Return the cached `doc_content.json` if it exists, else None."""
    path = path or (CONFIG.output_dir / "doc_content.json")
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def ingest(path: str | Path) -> Dict[str, Any]:
    """Dispatcher: route by file extension to the appropriate ingester."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        doc_content = ingest_pdf(p)
    elif suffix == ".pptx":
        raise NotImplementedError("PPTX ingestion is planned for Phase 2 (PRD §12).")
    elif suffix == ".docx":
        raise NotImplementedError("DOCX ingestion is planned for Phase 2 (PRD §12).")
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: .pdf, .pptx, .docx")
    save_doc_content(doc_content)
    return doc_content
