"""Explicit bounded import of selected statutory government edicts, not a crawler.

No network unless --download is supplied. Only statute text is redistributed;
publisher artwork, seals, editorial commentary and the full PDF are excluded.
"""
import argparse
import hashlib
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.dre.ca.gov/files/pdf/relaw/excerpts.pdf"
EDITION_URL = "https://www.dre.ca.gov/Publications/RealEstateLaw.html"
EXPECTED_PDF_SHA256 = "f68f64e547b1836572a39721c060df9cf9cadf02362107bff514ecb75784b5d2"
MAX_PDF_BYTES = 12_000_000
TARGETS = [("1950.5", "1950.6", "Residential security deposits"),
           ("1950.6", "1950.7", "Residential application screening fees"),
           ("1942.5", "1945.5", "Retaliatory conduct in residential tenancies")]


def sha(content):
    return hashlib.sha256(content.encode("utf8") if isinstance(content, str) else content).hexdigest()


def validate_capture_bytes(raw):
    if len(raw) > MAX_PDF_BYTES:
        raise SystemExit("Source PDF exceeds capture limit")
    if sha(raw) != EXPECTED_PDF_SHA256:
        raise SystemExit("Source PDF differs from the reviewed 2026 capture. Review its edition, page bounds and rights before updating the pinned hash; existing corpus files were not changed.")
    return raw


def sections(lines, source_id, version):
    groups, current = [], []
    locator, letter, branch = "(a)", "a", []
    for line, page in lines:
        marker = re.match(r"^((?:\([a-zA-Z0-9]+\)\s*)+)", line)
        if marker:
            if current:
                groups.append((locator, current))
            current = []
            parts = re.findall(r"\(([a-zA-Z0-9]+)\)", marker.group(0))
            first = parts[0]
            if first.islower() and len(first) == 1 and first not in {"i", "v"}:
                letter, branch = first, parts[1:]
            elif first.isdigit():
                branch = parts
            elif first.isupper():
                branch = branch[:1] + parts
            else:
                branch = branch[:2] + parts
            locator = "(" + letter + ")" + "".join("(" + item + ")" for item in branch)
        current.append((line, page))
    if current:
        groups.append((locator, current))
    result = []
    seen = {}
    for group_index, (locator, entries) in enumerate(groups, 1):
        chunks, chunk = [], []
        for word in " ".join(line for line, _ in entries).split():
            if chunk and len((" ".join(chunk) + " " + word).encode("utf8")) > 950:
                chunks.append(" ".join(chunk))
                chunk = []
            chunk.append(word)
        if chunk:
            chunks.append(" ".join(chunk))
        # PDF indentation cannot reliably distinguish a top-level (i) from a
        # nested roman (i). Use exact page/group locators, never guess a legal
        # subdivision hierarchy from flattened extraction.
        label = f"group-{group_index:03d}"
        for text in chunks:
            seen[label] = seen.get(label, 0) + 1
            result.append({"passage_id": f"{source_id}:{version}:{label}:part-{seen[label]}",
                           "locator": f"Civil Code § {source_id[7:].replace('-', '.')}, PDF pp. {entries[0][1]}–{entries[-1][1]}, paragraph group {group_index}, excerpt {seen[label]}",
                           "title": f"Statutory paragraph group {group_index}", "text": text,
                           "page_numbers": sorted({p for _, p in entries}), "content_hash": sha(text)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=ROOT / ".local/capture/excerpts-2026.pdf")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        args.pdf.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(URL, timeout=30) as response:
            raw = validate_capture_bytes(response.read(MAX_PDF_BYTES + 1))
        args.pdf.write_bytes(raw)
    with args.pdf.open("rb") as handle:
        raw = validate_capture_bytes(handle.read(MAX_PDF_BYTES + 1))
    reader = PdfReader(io.BytesIO(raw))
    # Exact bounded pages established against this captured 2026 publication.
    # A changed publication must be independently inspected before changing these.
    lines = []
    for page_no in [128, 129, *range(143, 151)]:
        for line in (reader.pages[page_no - 1].extract_text() or "").splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if line and not re.match(r"^EXCERPTS FROM THE .*CODE\s*\d*$", line) and not line.isdigit():
                lines.append((line, page_no))
    captured_at = datetime.now(UTC).isoformat()
    sources = []
    for section, next_section, title in TARGETS:
        start = next(i for i, (line, _) in enumerate(lines) if re.match(r"^" + re.escape(section) + r"\.\s", line))
        end = next(i for i in range(start + 1, len(lines)) if re.match(r"^" + re.escape(next_section) + r"\.\s", lines[i][0]))
        selected = lines[start:end]
        while selected and not re.search(r'[.!?][”\"]?$', selected[-1][0]):
            selected.pop()  # following editorial heading is not statutory text
        text = "\n".join(line for line, _ in selected) + "\n"
        source_id = "ca-civ-" + section.replace(".", "-")
        version = "dre-2026-" + sha(text)[:12]
        file = ROOT / "corpus/snapshots" / (source_id + ".txt")
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf8", newline="\n")
        sources.append({"source_id": source_id, "title": f"California Civil Code § {section} — {title}",
                        "publisher": "California Legislature; official compilation by California Department of Real Estate",
                        "url": URL, "edition_url": EDITION_URL,
                        "related_authority_url": f"https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum={section}.",
                        "source_type": "statute", "jurisdiction": "US-CA", "scope": "public", "version": version,
                        "content_hash": sha(text), "captured_at": captured_at, "publication_as_of": "2026-01-01",
                        "effective_from": None, "effective_to": None,
                        "applicability_status": "Not independently validated; edition date is not an effective-date interval",
                        "rights_basis": "Selected statutory government-edict text only (U.S. Copyright Office Compendium 313.6(C)(2)); DRE Conditions of Use Ownership distinguishes public-domain text from protected artwork/marks. No commentary, artwork or seals redistributed.",
                        "file": "snapshots/" + file.name, "sections": sections(selected, source_id, version),
                        "source_pdf_sha256": sha(raw), "source_pdf_pages": sorted({p for _, p in selected}),
                        "parser": "pypdf " + __import__("pypdf").__version__,
                        "normalization": "PDF line whitespace normalized; running headers/following editorial titles removed. Chunk boundaries are not new legal subdivisions."})
    manifest = {"schema_version": "1", "corpus_id": "ca-landlord-tenant-starter",
                "revision": "ca-dre-2026-" + sha("pdf-marker-groups-950bytes-v1" + "".join(s["content_hash"] for s in sources))[:16],
                "chunker": "pdf-marker-groups-950bytes-v1",
                "captured_at": captured_at, "sources": sources,
                "limitations": ["Selected sections only, not comprehensive/current coverage.",
                                "Publication date does not establish applicability.",
                                "Legislature section URLs returned 403; actual source is the official DRE compilation.",
                                "No professional legal review or case-specific determination."]}
    (ROOT / "corpus/manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"revision": manifest["revision"], "sources": len(sources), "passages": sum(len(s["sections"]) for s in sources), "pdf_sha256": sha(raw)}))


if __name__ == "__main__":
    main()
