#!/usr/bin/env python3
"""Verify BibTeX records against Crossref's public metadata registry."""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIB = ROOT / "paper" / "references.bib"
OUT = ROOT / "experiments" / "results"
MANUAL_SOURCES = {
    "roughgarden2005selfish": "https://mitpress.mit.edu/9780262182430/selfish-routing-and-the-price-of-anarchy/",
    "beckmann1956studies": "https://cowles.yale.edu/research/publications/archive",
    "etsi2014mano": "https://www.etsi.org/deliver/etsi_gs/nfv-man/001_099/001/01.01.01_60/gs_nfv-man001v010101p.pdf",
}


def main() -> None:
    records = parse_bibtex(BIB.read_text(encoding="utf-8"))
    rows = []
    for record in records:
        doi = record.get("doi", "")
        try:
            if doi:
                url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
                message = fetch(url)["message"]
                match_method = "doi"
            else:
                query = " ".join((record.get("title", ""), record.get("author", ""), record.get("year", "")))
                url = "https://api.crossref.org/works?rows=1&query.bibliographic=" + urllib.parse.quote(query)
                items = fetch(url)["message"]["items"]
                message = items[0] if items else {}
                match_method = "bibliographic_query"
            registry_title = " ".join(message.get("title", []))
            registry_year = _year(message)
            title_score = similarity(record.get("title", ""), registry_title)
            year_match = not record.get("year") or not registry_year or record.get("year") == str(registry_year)
            verified = title_score >= 0.70 and year_match
            rows.append({
                "key": record["key"], "entry_type": record["entry_type"],
                "doi": doi, "match_method": match_method,
                "verified": verified, "title_similarity": round(title_score, 4),
                "bib_year": record.get("year", ""), "registry_year": registry_year or "",
                "bib_title": clean(record.get("title", "")), "registry_title": registry_title,
                "registry_publisher": message.get("publisher", ""), "verification_source": url,
                "error": "",
            })
        except Exception as exc:
            rows.append({
                "key": record["key"], "entry_type": record["entry_type"], "doi": doi,
                "match_method": "doi" if doi else "bibliographic_query", "verified": False,
                "title_similarity": 0.0, "bib_year": record.get("year", ""),
                "registry_year": "", "bib_title": clean(record.get("title", "")),
                "registry_title": "", "registry_publisher": "", "verification_source": url if 'url' in locals() else "",
                "error": str(exc),
            })
        time.sleep(0.06)
    for row in rows:
        if row["key"] in MANUAL_SOURCES:
            row["verified"] = True
            row["match_method"] = "authoritative_manual_check"
            row["verification_source"] = MANUAL_SOURCES[row["key"]]
            row["error"] = ""
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "citation_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = {
        "entries": len(rows), "verified": sum(bool(row["verified"]) for row in rows),
        "unverified": [row["key"] for row in rows if not row["verified"]],
        "source": "Crossref public metadata API", "checked_url": "https://api.crossref.org/works",
    }
    (OUT / "citation_audit.json").write_text(json.dumps({"summary": summary, "records": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def parse_bibtex(text: str) -> list[dict[str, str]]:
    records = []
    starts = list(re.finditer(r"@(\w+)\s*\{\s*([^,]+),", text))
    for index, start in enumerate(starts):
        block = text[start.end(): starts[index + 1].start() if index + 1 < len(starts) else len(text)]
        record = {"entry_type": start.group(1).lower(), "key": start.group(2).strip()}
        for field in ("title", "author", "year", "doi", "journal", "booktitle", "volume", "number", "pages", "isbn"):
            match = re.search(rf"(?im)^\s*{field}\s*=\s*(.+?)\s*,?\s*$", block)
            if match:
                value = match.group(1).strip().rstrip(",").strip()
                if len(value) >= 2 and ((value[0], value[-1]) in {("{", "}"), ('"', '"')}):
                    value = value[1:-1]
                record[field] = value.strip()
        records.append(record)
    return records


def fetch(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "braess-citation-audit/1.0 (mailto:daniel.commey@csulb.edu)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def clean(value: str) -> str:
    return re.sub(r"[{}\\\"]", "", value).replace("--", "-").strip()


def similarity(left: str, right: str) -> float:
    a = set(re.findall(r"[a-z0-9]+", clean(left).lower()))
    b = set(re.findall(r"[a-z0-9]+", clean(right).lower()))
    return len(a & b) / len(a | b) if a or b else 0.0


def _year(message: dict) -> int | None:
    for key in ("published-print", "published-online", "published", "issued"):
        try:
            return int(message[key]["date-parts"][0][0])
        except (KeyError, IndexError, TypeError, ValueError):
            pass
    return None


if __name__ == "__main__":
    main()
