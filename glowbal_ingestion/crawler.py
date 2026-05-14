from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .constants import EVIDENCE_COLUMNS, PARSER_VERSION, SOURCE_COLUMNS
from .csv_io import write_csv
from .ids import stable_id


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden_stack: list[str] = []
        self._parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._hidden_stack.append(tag)
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if self._hidden_stack and tag == self._hidden_stack[-1]:
            self._hidden_stack.pop()
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        clean = data.strip()
        if not clean:
            return
        if self._in_title:
            self.title = clean
        if not self._hidden_stack:
            self._parts.append(clean)

    @property
    def text(self) -> str:
        return normalize_text(" ".join(self._parts))


def crawl_sources(source_rows: list[dict[str, str]], out_dir: str | Path, timeout: int = 25) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    now = utc_now()
    normalized_sources: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []

    for source in source_rows:
        source_id = source.get("source_id") or stable_id("src", source.get("university_id"), source.get("source_type"), source.get("url"))
        crawl_method = source.get("crawl_method") or "static"
        status = "pending"
        last_crawled_at = ""

        evidence = {
            "evidence_id": stable_id("ev", source_id, source.get("url"), now),
            "source_id": source_id,
            "university_id": source.get("university_id", ""),
            "url": source.get("url", ""),
            "title": "",
            "language_code": source.get("language_code", ""),
            "content_hash": "",
            "extracted_text": "",
            "retrieved_at": now,
            "parser_version": PARSER_VERSION,
            "status": "failed",
            "error": "",
        }

        if crawl_method == "manual":
            status = "manual"
            evidence["status"] = "manual"
            evidence["error"] = "manual source; crawler skipped"
        elif crawl_method == "playwright":
            evidence["status"] = "playwright_required"
            evidence["error"] = "playwright crawl_method requested; static standard-library crawler skipped"
            status = "skipped"
        elif crawl_method == "pdf" or source.get("url", "").lower().endswith(".pdf"):
            status, last_crawled_at = crawl_pdf_placeholder(source, evidence, timeout, now)
        else:
            status, last_crawled_at = crawl_static(source, evidence, timeout, now)

        normalized_sources.append(
            {
                "source_id": source_id,
                "university_id": source.get("university_id", ""),
                "university_name": source.get("university_name", ""),
                "country": source.get("country", ""),
                "source_type": source.get("source_type", ""),
                "url": source.get("url", ""),
                "priority": source.get("priority", "1") or "1",
                "language_code": source.get("language_code", ""),
                "crawl_method": crawl_method,
                "status": status,
                "last_crawled_at": last_crawled_at,
                "notes": source.get("notes", ""),
            }
        )
        evidence_rows.append(evidence)

    write_csv(Path(out_dir) / "sources.csv", normalized_sources, SOURCE_COLUMNS)
    write_csv(Path(out_dir) / "evidence.csv", evidence_rows, EVIDENCE_COLUMNS)
    return normalized_sources, evidence_rows


def crawl_static(source: dict[str, str], evidence: dict[str, object], timeout: int, now: str) -> tuple[str, str]:
    try:
        body, content_type = fetch_bytes(source.get("url", ""), timeout)
        text, title = extract_text(body, content_type)
        evidence["title"] = title
        evidence["extracted_text"] = text
        evidence["content_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
        evidence["status"] = "ok" if text else "empty"
        return ("fetched" if text else "failed", now)
    except Exception as exc:  # noqa: BLE001 - store crawl failures as evidence rows.
        evidence["status"] = "failed"
        evidence["error"] = str(exc)
        return "failed", now


def crawl_pdf_placeholder(source: dict[str, str], evidence: dict[str, object], timeout: int, now: str) -> tuple[str, str]:
    try:
        body, _content_type = fetch_bytes(source.get("url", ""), timeout)
        evidence["content_hash"] = hashlib.sha256(body).hexdigest()
        evidence["status"] = "unsupported_pdf"
        evidence["error"] = "PDF downloaded but text extraction requires an optional PDF parser"
        return "fetched", now
    except Exception as exc:  # noqa: BLE001
        evidence["status"] = "failed"
        evidence["error"] = str(exc)
        return "failed", now


def fetch_bytes(url: str, timeout: int) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        return path.read_bytes(), guess_content_type(path.name)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GlowbalUniversityIngestion/0.1 (+https://glowbal.example)",
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        return response.read(), content_type


def extract_text(body: bytes, content_type: str) -> tuple[str, str]:
    if "application/pdf" in content_type.lower():
        return "", ""

    decoded = decode_bytes(body, content_type)
    if looks_like_html(decoded):
        parser = _HTMLTextExtractor()
        parser.feed(decoded)
        return parser.text, html.unescape(parser.title)
    return normalize_text(decoded), ""


def decode_bytes(body: bytes, content_type: str) -> str:
    charset_match = re.search(r"charset=([\w.-]+)", content_type, flags=re.I)
    encodings = [charset_match.group(1)] if charset_match else []
    encodings.extend(["utf-8", "utf-16", "latin-1"])
    for encoding in encodings:
        try:
            return body.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


def looks_like_html(value: str) -> bool:
    sample = value[:1000].lower()
    return "<html" in sample or "<body" in sample or "<!doctype html" in sample


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def guess_content_type(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".html") or lowered.endswith(".htm"):
        return "text/html; charset=utf-8"
    if lowered.endswith(".pdf"):
        return "application/pdf"
    return "text/plain; charset=utf-8"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
