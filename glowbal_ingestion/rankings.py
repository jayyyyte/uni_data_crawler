from __future__ import annotations

import html
import csv
import json
import re
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .constants import (
    QS_NORMALIZED_COLUMNS,
    QS_RAW_COLUMNS,
    RANKING_IMPORT_COLUMNS,
    RANKING_MATCH_CANDIDATE_COLUMNS,
    RANKING_MATCH_REPORT_COLUMNS,
)
from .csv_io import read_csv, write_csv

QS_RANKING_URL = "https://www.topuniversities.com/world-university-rankings"
QS_RANKING_YEAR = "2026"
QS_OFFICIAL_ENDPOINTS = [
    QS_RANKING_URL,
    "https://www.topuniversities.com/universities/json",
    "https://www.topuniversities.com/universities/api",
    "https://www.topuniversities.com/universities/static/api",
    "https://www.topuniversities.com/universities/qs-world-university-rankings",
]

COUNTRY_ALIASES = {
    "united states": "united states",
    "united states of america": "united states",
    "usa": "united states",
    "us": "united states",
    "united kingdom": "united kingdom",
    "uk": "united kingdom",
    "south korea": "south korea",
    "korea south": "south korea",
    "republic of korea": "south korea",
    "china mainland": "china",
    "mainland china": "china",
    "hong kong sar": "hong kong",
    "hong kong s.a.r.": "hong kong",
    "hong kong sar china": "hong kong",
    "taiwan china": "taiwan",
}

SEED_ALIASES = {
    "mit": ["MIT"],
    "uc-berkeley": ["University of California, Berkeley", "UC Berkeley", "Berkeley"],
    "caltech": ["Caltech"],
    "uchicago": ["The University of Chicago"],
    "upenn": ["Penn", "University of Pennsylvania"],
    "cmu": ["Carnegie Mellon"],
    "ubc": ["The University of British Columbia"],
    "ucl": ["UCL", "University College London"],
    "lse": ["London School of Economics", "The London School of Economics and Political Science"],
    "kcl": ["King's College London", "King’s College London"],
    "eth-zurich": ["ETH Zurich - Swiss Federal Institute of Technology", "ETH Zürich"],
    "epfl": ["Ecole Polytechnique Fédérale de Lausanne", "EPFL"],
    "tum": ["Technical University of Munich", "Technische Universität München"],
    "lmu-munich": ["LMU Munich", "Ludwig-Maximilians-Universität München"],
    "lmumunich": ["LMU Munich", "Ludwig-Maximilians-Universität München"],
    "ku-leuven": ["KU Leuven", "Katholieke Universiteit Leuven"],
    "nus": ["NUS", "National University of Singapore"],
    "ntu-singapore": ["Nanyang Technological University, Singapore", "NTU Singapore"],
    "hku": ["The University of Hong Kong", "University of Hong Kong"],
    "cuhk": ["The Chinese University of Hong Kong", "Chinese University of Hong Kong"],
    "hkust": ["The Hong Kong University of Science and Technology", "HKUST"],
    "tokyo": ["The University of Tokyo", "University of Tokyo"],
    "snu": ["Seoul National University"],
    "kaist": ["Korea Advanced Institute of Science and Technology", "KAIST"],
    "unsw": ["UNSW Sydney", "The University of New South Wales"],
    "jhu": ["Johns Hopkins University"],
    "wustl": ["Washington University in St. Louis"],
    "notredame": ["University of Notre Dame"],
    "umich": ["University of Michigan-Ann Arbor", "University of Michigan"],
    "uva": ["University of Virginia"],
    "unc": ["University of North Carolina at Chapel Hill"],
    "utaustin": ["University of Texas at Austin", "The University of Texas at Austin"],
    "uwmadison": ["University of Wisconsin-Madison", "University of Wisconsin Madison"],
    "uiuc": ["University of Illinois Urbana-Champaign", "University of Illinois at Urbana-Champaign"],
    "ucsd": ["University of California, San Diego", "UC San Diego"],
    "ucsb": ["University of California, Santa Barbara", "UC Santa Barbara"],
    "ucdavis": ["University of California, Davis", "UC Davis"],
    "uci": ["University of California, Irvine", "UC Irvine"],
    "gatech": ["Georgia Institute of Technology", "Georgia Tech"],
    "umontreal": ["Université de Montréal", "University of Montreal"],
    "ualberta": ["University of Alberta"],
    "ucalgary": ["University of Calgary"],
    "kth": ["KTH Royal Institute of Technology"],
    "uzh": ["University of Zurich", "Universität Zürich"],
    "psl": ["Université PSL", "Paris Sciences et Lettres University", "PSL University"],
    "polytechnique": ["École Polytechnique", "Ecole Polytechnique"],
    "polytechnique": ["Ecole Polytechnique", "Institut Polytechnique de Paris"],
    "sjtu": ["Shanghai Jiao Tong University"],
    "ustc": ["University of Science and Technology of China"],
    "sysu": ["Sun Yat-sen University"],
    "cityu": ["City University of Hong Kong"],
    "polyu": ["The Hong Kong Polytechnic University", "Hong Kong Polytechnic University"],
    "ntu_tw": ["National Taiwan University"],
    "uq": ["The University of Queensland", "University of Queensland"],
    "uwa": ["The University of Western Australia", "University of Western Australia"],
    "usc": ["University of Southern California"],
    "psu": ["Pennsylvania State University", "Penn State"],
    "osu": ["The Ohio State University", "Ohio State University"],
    "ucsc": ["University of California, Santa Cruz", "UC Santa Cruz"],
    "umd": ["University of Maryland, College Park", "University of Maryland College Park"],
    "bc": ["Boston College"],
    "osaka": ["Osaka University", "The University of Osaka"],
    "rutgers": ["Rutgers University", "Rutgers University New Brunswick", "Rutgers University - New Brunswick"],
    "tcd": ["Trinity College Dublin", "The University of Dublin, Trinity College", "Trinity College Dublin The University of Dublin"],
    "ucd": ["University College Dublin"],
    "uwashington": ["University of Washington"],
    "postech": ["Pohang University of Science and Technology", "POSTECH"],
    "tamu": ["Texas A&M University"],
}


def fetch_qs_rankings(out_dir: str | Path, use_playwright: bool = True) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    retrieved_at = date.today().isoformat()
    payloads: list[object] = []

    static_errors = []
    for index, endpoint in enumerate(QS_OFFICIAL_ENDPOINTS, start=1):
        try:
            response_text = fetch_url(endpoint)
            (out_path / f"qs_official_response_{index}.txt").write_text(response_text, encoding="utf-8")
            payloads.extend(json_payloads_from_text(response_text))
        except RuntimeError as exc:
            static_errors.append(f"{endpoint}\n{exc}")
    if static_errors:
        (out_path / "fetch_qs_static_error.txt").write_text("\n\n".join(static_errors), encoding="utf-8")

    rows = records_from_payloads(payloads)
    if use_playwright and len(rows) < 100:
        try:
            playwright_payloads = capture_qs_playwright_payloads(out_path)
            payloads.extend(playwright_payloads)
            rows = records_from_payloads(payloads)
        except Exception as exc:
            (out_path / "fetch_qs_playwright_error.txt").write_text(str(exc), encoding="utf-8")

    raw_rows = [raw_row_from_record(row, retrieved_at) for row in rows]
    normalized_rows = [normalize_qs_row(row, retrieved_at) for row in raw_rows]
    normalized_rows = dedupe_normalized_rankings(normalized_rows)

    write_csv(out_path / "qs_raw.csv", raw_rows, QS_RAW_COLUMNS)
    write_csv(out_path / "qs_normalized.csv", normalized_rows, QS_NORMALIZED_COLUMNS)
    return raw_rows, normalized_rows


def normalize_qs_rankings_file(input_path: str | Path, out_dir: str | Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows = read_flexible_qs_csv(input_path)
    retrieved_at = date.today().isoformat()
    raw_rows = [raw_row_from_flexible_csv(row, retrieved_at, str(input_path)) for row in rows]
    raw_rows = [row for row in raw_rows if row.get("institution_name") and row.get("rank_raw")]
    normalized_rows = [normalize_qs_row(row, retrieved_at) for row in raw_rows]
    normalized_rows = dedupe_normalized_rankings(normalized_rows)
    out_path = Path(out_dir)
    write_csv(out_path / "qs_raw.csv", raw_rows, QS_RAW_COLUMNS)
    write_csv(out_path / "qs_normalized.csv", normalized_rows, QS_NORMALIZED_COLUMNS)
    return raw_rows, normalized_rows


def read_flexible_qs_csv(input_path: str | Path) -> list[dict[str, str]]:
    path = Path(input_path)
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        raw_rows = list(csv.reader(handle))
    header_index = find_qs_header_row(raw_rows)
    if header_index is None:
        return read_csv(input_path)
    headers = [normalize_header_cell(value, index) for index, value in enumerate(raw_rows[header_index])]
    rows: list[dict[str, str]] = []
    for raw in raw_rows[header_index + 1:]:
        if not any(cell.strip() for cell in raw):
            continue
        row: dict[str, str] = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            row[header] = raw[index].strip() if index < len(raw) else ""
        rows.append(row)
    return rows


def find_qs_header_row(raw_rows: list[list[str]]) -> int | None:
    for index, row in enumerate(raw_rows[:20]):
        headers = {normalize_header(value) for value in row if value.strip()}
        has_rank = "rank" in headers or "2026 rank" in headers
        has_name = bool(headers & {"name", "institution", "university", "university name", "institution name"})
        has_country = bool(headers & {"country territory", "country", "location"})
        if has_rank and has_name and has_country:
            return index
    return None


def normalize_header_cell(value: str, index: int) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    return f"unnamed_{index}"


def raw_row_from_flexible_csv(row: dict[str, str], retrieved_at: str, source_url: str) -> dict[str, object]:
    rank = flexible_value(row, ["rank", "rank_raw", "rank display", "rank_display", "2026 rank", "overall rank", "world rank"])
    name = flexible_value(row, ["institution_name", "institution", "university", "university name", "name", "title"])
    country = flexible_value(row, ["country", "location", "country/territory", "country territory", "region"])
    city = flexible_value(row, ["city", "city_name"])
    return {
        "ranking_provider": "QS",
        "ranking_year": QS_RANKING_YEAR,
        "source_url": source_url,
        "rank_raw": rank,
        "institution_name": strip_html(name),
        "country": strip_html(country),
        "city": strip_html(city),
        "raw_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
        "retrieved_at": retrieved_at,
    }


def flexible_value(row: dict[str, str], keys: list[str]) -> str:
    normalized = {normalize_header(key): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(normalize_header(key), "")
        if value:
            return value
    for key, value in normalized.items():
        if any(normalize_header(candidate) in key for candidate in keys) and value:
            return value
    return ""


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def fetch_url(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GlowbalRankImporter/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"QS static fetch failed: HTTP {exc.code} {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"QS static fetch failed: {exc.reason}") from exc


def json_payloads_from_text(text: str) -> list[object]:
    stripped = text.strip()
    payloads: list[object] = []
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payloads.append(json.loads(stripped))
            return payloads
        except json.JSONDecodeError:
            pass
    payloads.extend(json_payloads_from_html(text))
    return payloads


def json_payloads_from_html(html_text: str) -> list[object]:
    payloads: list[object] = []
    for match in re.finditer(r"<script[^>]+type=[\"']application/json[\"'][^>]*>(.*?)</script>", html_text, flags=re.I | re.S):
        text = html.unescape(match.group(1)).strip()
        if not text:
            continue
        try:
            payloads.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    for marker in ["__NEXT_DATA__", "drupalSettings"]:
        if marker not in html_text:
            continue
        for candidate in balanced_json_candidates_around(html_text, marker):
            try:
                payloads.append(json.loads(candidate))
            except json.JSONDecodeError:
                continue
    return payloads


def balanced_json_candidates_around(text: str, marker: str) -> list[str]:
    candidates: list[str] = []
    start = text.find(marker)
    while start != -1:
        for char in ["{", "["]:
            json_start = text.find(char, start)
            if json_start != -1:
                candidate = balanced_json(text, json_start)
                if candidate:
                    candidates.append(candidate)
        start = text.find(marker, start + len(marker))
    return candidates


def balanced_json(text: str, start: int) -> str:
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return ""


def capture_qs_playwright_payloads(out_path: Path) -> list[object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run `python -m playwright install chromium`.") from exc

    payloads: list[object] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()

        def handle_response(response: Any) -> None:
            url = response.url
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and not any(part in url.lower() for part in ["ranking", "rankings", "wur", "search"]):
                return
            try:
                payload = response.json()
            except Exception:
                return
            payloads.append(payload)

        page.on("response", handle_response)
        page.goto(QS_RANKING_URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(5000)
        (out_path / "qs_playwright_page.html").write_text(page.content(), encoding="utf-8")
        browser.close()

    with (out_path / "qs_playwright_payloads.json").open("w", encoding="utf-8") as handle:
        json.dump(payloads, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return payloads


def records_from_payloads(payloads: list[object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for payload in payloads:
        records.extend(records_from_any(payload))
    return dedupe_records(records)


def records_from_any(value: object) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if isinstance(value, list):
        for item in value:
            records.extend(records_from_any(item))
    elif isinstance(value, dict):
        record = ranking_record_from_dict(value)
        if record:
            records.append(record)
        for child in value.values():
            if isinstance(child, (dict, list)):
                records.extend(records_from_any(child))
    return records


def ranking_record_from_dict(row: dict[str, object]) -> dict[str, object] | None:
    name = first_present(row, ["institution_name", "university", "title", "name", "uni", "nid_title"])
    rank = first_present(row, ["rank", "rank_display", "overall_rank", "ranking", "rank_2026", "rank_display_rank"])
    if not name or not rank:
        return None
    rank_number = parse_rank_numeric(str(rank))
    if rank_number == "":
        return None
    country = first_present(row, ["country", "location", "country_name", "region_country"])
    city = first_present(row, ["city", "city_name"])
    return {
        "rank_raw": str(rank),
        "institution_name": strip_html(str(name)),
        "country": strip_html(str(country)),
        "city": strip_html(str(city)),
        "raw_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
    }


def first_present(row: dict[str, object], keys: list[str]) -> str:
    lowered = {key.lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in ("", None, [], {}):
            return str(value)
    for key, value in row.items():
        lowered_key = key.lower()
        if any(part in lowered_key for part in keys) and value not in ("", None, [], {}):
            return str(value)
    return ""


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(value)).strip()


def dedupe_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, object]] = []
    for record in records:
        key = (normalize_name(str(record.get("institution_name", ""))), str(record.get("rank_raw", "")))
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def raw_row_from_record(record: dict[str, object], retrieved_at: str) -> dict[str, object]:
    return {
        "ranking_provider": "QS",
        "ranking_year": QS_RANKING_YEAR,
        "source_url": QS_RANKING_URL,
        "rank_raw": record.get("rank_raw", ""),
        "institution_name": record.get("institution_name", ""),
        "country": record.get("country", ""),
        "city": record.get("city", ""),
        "raw_json": record.get("raw_json", ""),
        "retrieved_at": retrieved_at,
    }


def normalize_qs_row(row: dict[str, object], retrieved_at: str) -> dict[str, object]:
    rank_raw = str(row.get("rank_raw", ""))
    rank_numeric = parse_rank_numeric(rank_raw)
    return {
        "ranking_provider": "QS",
        "ranking_year": QS_RANKING_YEAR,
        "institution_name": row.get("institution_name", ""),
        "normalized_name": normalize_name(str(row.get("institution_name", ""))),
        "country": row.get("country", ""),
        "city": row.get("city", ""),
        "rank_raw": rank_raw,
        "rank_numeric": rank_numeric,
        "rank_display": f"QS {QS_RANKING_YEAR} #{rank_raw}" if rank_raw else "",
        "ranking_source_url": row.get("source_url", QS_RANKING_URL),
        "retrieved_at": retrieved_at,
        "review_status": "needs_review" if is_range_rank(rank_raw) else "approved",
        "notes": "QS official ranking import",
    }


def dedupe_normalized_rankings(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_name: dict[str, dict[str, object]] = {}
    for row in rows:
        key = str(row.get("normalized_name", ""))
        if not key:
            continue
        current = by_name.get(key)
        if current is None or int_or_large(row.get("rank_numeric")) < int_or_large(current.get("rank_numeric")):
            by_name[key] = row
    return sorted(by_name.values(), key=lambda row: int_or_large(row.get("rank_numeric")))


def parse_rank_numeric(value: str) -> int | str:
    cleaned = value.strip().replace("#", "").replace("=", "")
    match = re.search(r"\d+", cleaned)
    if not match:
        return ""
    return int(match.group(0))


def is_range_rank(value: str) -> bool:
    return bool(re.search(r"\d+\s*[-+]\s*\d*|\d+\+", value))


def int_or_large(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10_000_000


def match_rankings(
    seed_rows: list[dict[str, str]],
    qs_rows: list[dict[str, str]],
    base_rows: list[dict[str, str]],
    out_path: str | Path,
    report_path: str | Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    base_by_id = {row.get("university_id", ""): row for row in base_rows}
    output_rows: list[dict[str, object]] = []
    report_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []

    for seed in seed_rows:
        university_id = seed.get("university_id", "")
        candidates = rank_candidates(seed, qs_rows)
        candidate_rows.extend(candidate_rows_for_seed(seed, candidates[:5]))
        best = candidates[0] if candidates else None
        base = base_by_id.get(university_id, {})
        if best and best["confidence_score"] >= 0.88 and not is_ambiguous(candidates):
            rank_row = ranking_import_row(seed, best["row"], base, "approved")
            output_rows.append(rank_row)
            report_rows.append(match_report_row(seed, "matched" if not base.get("qs_rank") else "updated", best, rank_row, "QS match auto-approved"))
        elif base.get("qs_rank"):
            rank_row = existing_ranking_row(university_id, base)
            output_rows.append(rank_row)
            status = "existing_preserved"
            report_rows.append(match_report_row(seed, status, best, rank_row, "Existing approved rank preserved; new match not confident enough"))
        else:
            rank_row = blank_ranking_row(university_id)
            output_rows.append(rank_row)
            status = "ambiguous" if candidates else "unmatched"
            report_rows.append(match_report_row(seed, status, best, rank_row, "Needs manual ranking review" if candidates else "No QS match candidate"))

    output_rows.sort(key=lambda row: str(row.get("university_id", "")))
    report_rows.sort(key=lambda row: str(row.get("university_id", "")))
    candidate_rows.sort(key=lambda row: (str(row.get("university_id", "")), -float(row.get("confidence_score", 0) or 0)))
    write_csv(out_path, output_rows, RANKING_IMPORT_COLUMNS)
    write_csv(report_path, report_rows, RANKING_MATCH_REPORT_COLUMNS)
    write_csv(Path(report_path).with_name("ranking_match_candidates.csv"), candidate_rows, RANKING_MATCH_CANDIDATE_COLUMNS)
    return output_rows, report_rows, candidate_rows


def rank_candidates(seed: dict[str, str], qs_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    candidates = []
    seed_names = seed_match_names(seed)
    for row in qs_rows:
        score, reason = score_ranking_candidate(seed, seed_names, row)
        if score >= 0.62:
            candidates.append({"row": row, "confidence_score": score, "match_reason": reason})
    candidates.sort(key=lambda candidate: (-float(candidate["confidence_score"]), int_or_large(candidate["row"].get("rank_numeric"))))
    return candidates


def seed_match_names(seed: dict[str, str]) -> list[str]:
    values = [seed.get("name", ""), seed.get("local_name", "")]
    values.extend(SEED_ALIASES.get(seed.get("university_id", ""), []))
    return [value for value in values if value]


def score_ranking_candidate(seed: dict[str, str], seed_names: list[str], row: dict[str, str]) -> tuple[float, str]:
    candidate_name = row.get("institution_name", "")
    candidate_country = row.get("country", "")
    country_score = 0.12 if countries_match(seed.get("country", ""), candidate_country) else -0.08
    best_name_score = 0.0
    best_reason = "name_similarity"
    for name in seed_names:
        name_score, reason = name_similarity_score(name, candidate_name)
        if name_score > best_name_score:
            best_name_score = name_score
            best_reason = reason
    city_bonus = 0.03 if normalize_name(seed.get("city", "")) and normalize_name(seed.get("city", "")) == normalize_name(row.get("city", "")) else 0.0
    score = max(0.0, min(1.0, best_name_score + country_score + city_bonus))
    return round(score, 3), best_reason


def name_similarity_score(left: str, right: str) -> tuple[float, str]:
    left_norm = normalize_name(left)
    right_norm = normalize_name(right)
    if not left_norm or not right_norm:
        return 0.0, "empty_name"
    if left_norm == right_norm:
        return 0.90, "normalized_exact"
    left_simple = simplify_university_name(left_norm)
    right_simple = simplify_university_name(right_norm)
    if left_simple and left_simple == right_simple:
        return 0.86, "simplified_exact"
    left_tokens = set(left_simple.split())
    right_tokens = set(right_simple.split())
    if left_tokens and right_tokens:
        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        containment = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    else:
        jaccard = 0.0
        containment = 0.0
    sequence = SequenceMatcher(None, left_simple, right_simple).ratio()
    score = max(sequence * 0.76, jaccard * 0.82, containment * 0.78)
    return round(score, 3), "token_similarity"


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower().replace("&", " and ")
    normalized = re.sub(r"\([^)]*\)", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def simplify_university_name(value: str) -> str:
    tokens = [
        token for token in value.split()
        if token not in {"the", "of", "and", "at", "in", "for"}
    ]
    return " ".join(tokens)


def countries_match(seed_country: str, candidate_country: str) -> bool:
    if not candidate_country:
        return True
    return normalize_country(seed_country) == normalize_country(candidate_country)


def normalize_country(value: str) -> str:
    normalized = normalize_name(value)
    return COUNTRY_ALIASES.get(normalized, normalized)


def is_ambiguous(candidates: list[dict[str, object]]) -> bool:
    if len(candidates) < 2:
        return False
    return float(candidates[0]["confidence_score"]) - float(candidates[1]["confidence_score"]) < 0.04


def candidate_rows_for_seed(seed: dict[str, str], candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for candidate in candidates:
        row = candidate["row"]
        rows.append(
            {
                "university_id": seed.get("university_id", ""),
                "seed_name": seed.get("name", ""),
                "seed_country": seed.get("country", ""),
                "candidate_name": row.get("institution_name", ""),
                "candidate_country": row.get("country", ""),
                "rank_raw": row.get("rank_raw", ""),
                "rank_numeric": row.get("rank_numeric", ""),
                "rank_display": row.get("rank_display", ""),
                "confidence_score": f"{float(candidate['confidence_score']):.3f}",
                "match_reason": candidate.get("match_reason", ""),
                "review_status": "approved" if float(candidate["confidence_score"]) >= 0.88 else "needs_review",
                "ranking_source_url": row.get("ranking_source_url", ""),
            }
        )
    return rows


def ranking_import_row(seed: dict[str, str], qs_row: dict[str, str], base: dict[str, str], review_status: str) -> dict[str, object]:
    return {
        "university_id": seed.get("university_id", ""),
        "qs_rank": qs_row.get("rank_numeric", ""),
        "the_rank": base.get("the_rank", ""),
        "arwu_rank": base.get("arwu_rank", ""),
        "rank_display": qs_row.get("rank_display", ""),
        "ranking_source_url": qs_row.get("ranking_source_url", ""),
        "retrieved_at": qs_row.get("retrieved_at", ""),
        "review_status": "needs_review" if qs_row.get("review_status") == "needs_review" else review_status,
        "notes": "QS 2026 official match",
    }


def existing_ranking_row(university_id: str, base: dict[str, str]) -> dict[str, object]:
    row = blank_ranking_row(university_id)
    row.update(base)
    row["university_id"] = university_id
    return row


def blank_ranking_row(university_id: str) -> dict[str, object]:
    return {
        "university_id": university_id,
        "qs_rank": "",
        "the_rank": "",
        "arwu_rank": "",
        "rank_display": "",
        "ranking_source_url": "",
        "retrieved_at": "",
        "review_status": "needs_review",
        "notes": "No ranking match yet",
    }


def match_report_row(
    seed: dict[str, str],
    status: str,
    candidate: dict[str, object] | None,
    rank_row: dict[str, object],
    notes: str,
) -> dict[str, object]:
    matched = candidate["row"] if candidate else {}
    return {
        "university_id": seed.get("university_id", ""),
        "seed_name": seed.get("name", ""),
        "seed_country": seed.get("country", ""),
        "match_status": status,
        "matched_name": matched.get("institution_name", ""),
        "matched_country": matched.get("country", ""),
        "qs_rank": rank_row.get("qs_rank", ""),
        "rank_display": rank_row.get("rank_display", ""),
        "confidence_score": f"{float(candidate['confidence_score']):.3f}" if candidate else "",
        "ranking_source_url": rank_row.get("ranking_source_url", ""),
        "notes": notes,
    }
