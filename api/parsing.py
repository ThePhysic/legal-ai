"""Capped extraction in a killable child process; input is always untrusted data."""

import io
import multiprocessing
import re
import zipfile
from pathlib import PurePosixPath

MAX_CHARACTERS = 400_000
MAX_SECTIONS = 300
MAX_CHUNKS = 400
MAX_PAGES = 150
MAX_EXPANDED = 25 * 1024 * 1024


class ParseError(ValueError):
    pass


def validate_signature(filename: str, raw: bytes):
    extension = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if extension not in (".pdf", ".docx", ".txt", ".md"):
        raise ParseError("Supported files: PDF, DOCX, UTF-8 text or Markdown.")
    if extension == ".pdf" and not raw.startswith(b"%PDF-"):
        raise ParseError("The file signature does not match PDF.")
    if extension == ".docx" and not raw.startswith(b"PK\x03\x04"):
        raise ParseError("The file signature does not match DOCX.")
    if extension in (".txt", ".md"):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ParseError("Text files must use UTF-8.") from exc
        if "\x00" in text or any(ord(c) < 9 or 13 < ord(c) < 32 for c in text):
            raise ParseError("Binary/control content is not a text document.")
    return extension


def normalize(text):
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _checked_sections(sections):
    result = []
    total = 0
    for section in sections:
        section["text"] = normalize(section["text"])
        if not section["text"]:
            continue
        total += len(section["text"])
        if total > MAX_CHARACTERS or len(result) >= MAX_SECTIONS:
            raise ParseError("Extracted document exceeds the text or section cap.")
        result.append(section)
    if not result:
        raise ParseError("No selectable text was found. Scanned PDFs require OCR, which is not available.")
    return result


def _reject_unsafe_pdf_graph(root):
    """Inspect bounded reachable dictionaries, including annotation/action chains.

    No action is executed. /Next can be an action dictionary/array or an outline
    sibling, so follow it within the same graph budget rather than treating its
    presence alone as active content. Streams remain compressed during traversal.
    """
    from pypdf.generic import IndirectObject

    pending, seen, examined = [(root, 0)], set(), 0
    forbidden_keys = {"/A", "/AA", "/OpenAction", "/JS", "/JavaScript", "/EmbeddedFiles", "/AF",
                      "/AcroForm", "/XFA", "/RichMediaContent", "/RichMediaSettings", "/Collection"}
    forbidden_actions = {"/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/GoToR", "/GoToE",
                         "/Rendition", "/RichMediaExecute", "/URI"}
    while pending:
        value, depth = pending.pop()
        if not isinstance(value, (dict, list, tuple, IndirectObject)):
            continue
        identity = ("ref", value.idnum, value.generation) if isinstance(value, IndirectObject) else ("object", id(value))
        if identity in seen:
            continue
        seen.add(identity)
        examined += 1
        if examined > 20_000 or depth > 60:
            raise ParseError("PDF object graph exceeds the safety traversal cap.")
        if isinstance(value, IndirectObject):
            pending.append((value.get_object(), depth))
        elif isinstance(value, dict):
            if (forbidden_keys.intersection(value) or value.get("/S") in forbidden_actions
                    or value.get("/Type") in ("/EmbeddedFile", "/Filespec")
                    or value.get("/Subtype") == "/FileAttachment"):
                raise ParseError("Active or embedded PDF content is not supported.")
            pending.extend((child, depth + 1) for child in value.values())
        else:
            pending.extend((child, depth + 1) for child in value)


def _parse(raw: bytes, extension: str):
    if extension == ".pdf":
        from pypdf import PdfReader
        from pypdf import filters as pdf_filters

        # Bound decoded streams before the parser allocates their full output.
        # These version-pinned pypdf limits apply only inside the isolated child.
        for limit in ("ZLIB_MAX_OUTPUT_LENGTH", "LZW_MAX_OUTPUT_LENGTH", "RUN_LENGTH_MAX_OUTPUT_LENGTH",
                      "JBIG2_MAX_OUTPUT_LENGTH", "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
                      "MAX_DECLARED_STREAM_LENGTH", "FLATE_MAX_BUFFER_SIZE"):
            setattr(pdf_filters, limit, MAX_EXPANDED)

        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise ParseError("Encrypted PDFs are not supported.")
        root = reader.trailer["/Root"]
        _reject_unsafe_pdf_graph(root)
        if any(key in root for key in ("/OpenAction", "/AA", "/AcroForm", "/Collection", "/AF")):
            raise ParseError("Active PDF content is not supported.")
        names = root.get("/Names", {})
        if hasattr(names, "get_object"):
            names = names.get_object()
        if "/EmbeddedFiles" in names or "/JavaScript" in names:
            raise ParseError("Embedded/active PDF content is not supported.")
        if len(reader.pages) > MAX_PAGES:
            raise ParseError("PDF exceeds the 150-page cap.")
        sections = []
        total = 0
        for number, page in enumerate(reader.pages, 1):
            if "/AA" in page or "/AF" in page:
                raise ParseError("Active PDF content is not supported.")
            for reference in page.get("/Annots", []):
                annotation = reference.get_object()
                if any(key in annotation for key in ("/A", "/AA", "/FS", "/RichMediaContent")) or annotation.get("/Subtype") == "/FileAttachment":
                    raise ParseError("Active or embedded PDF annotations are not supported.")
            content = page.get_contents()
            if content and len(content.get_data()) > MAX_EXPANDED:
                raise ParseError("PDF page stream exceeds the extraction cap.")
            text = page.extract_text() or ""
            total += len(text)
            if total > MAX_CHARACTERS:
                raise ParseError("Extracted document exceeds the text cap.")
            sections.append({"locator": f"page-{number}", "title": f"Page {number}", "text": text})
        return _checked_sections(sections)
    if extension == ".docx":
        from defusedxml.ElementTree import fromstring

        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 500 or sum(item.file_size for item in infos) > MAX_EXPANDED:
                raise ParseError("DOCX exceeds the decompression cap.")
            if len({item.filename for item in infos}) != len(infos):
                raise ParseError("DOCX contains ambiguous duplicate entries.")
            for item in infos:
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in item.filename or item.flag_bits & 1:
                    raise ParseError("Unsafe DOCX archive entry.")
                if item.file_size > max(1, item.compress_size) * 100:
                    raise ParseError("DOCX archive compression ratio exceeds the cap.")
                if item.filename.endswith((".xml", ".rels")):
                    xml = fromstring(archive.read(item), forbid_dtd=True, forbid_entities=True, forbid_external=True)
                    if item.filename.endswith(".rels") and any(
                        element.attrib.get("TargetMode", "").lower() == "external" for element in xml.iter()
                    ):
                        raise ParseError("External DOCX relationships are not supported.")
                if "vbaProject" in item.filename or item.filename.startswith("word/embeddings/"):
                    raise ParseError("Embedded/macro DOCX content is not supported.")
            if "word/document.xml" not in archive.namelist():
                raise ParseError("Not a valid DOCX document.")
        from docx import Document

        doc = Document(io.BytesIO(raw))
        sections = []
        current = {"locator": "section-1", "title": "Document", "text": ""}
        for paragraph in doc.paragraphs:
            if paragraph.style and paragraph.style.name.startswith("Heading") and current["text"]:
                sections.append(current)
                current = {"locator": f"section-{len(sections) + 1}", "title": paragraph.text[:160], "text": ""}
            current["text"] += paragraph.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                current["text"] += " | ".join(cell.text for cell in row.cells) + "\n"
        sections.append(current)
        return _checked_sections(sections)
    text = raw.decode("utf-8-sig")
    sections = []
    current = {"locator": "section-1", "title": "Document", "text": ""}
    for line in text.splitlines():
        if re.match(r"^#{1,6}\s+", line) and current["text"]:
            sections.append(current)
            current = {"locator": f"section-{len(sections) + 1}", "title": line.lstrip("# ")[:160], "text": ""}
        current["text"] += line + "\n"
    sections.append(current)
    return _checked_sections(sections)


def _worker(send, raw, extension):
    try:
        # POSIX deployment also bounds CPU/address space. Windows uses the process
        # boundary and parent-enforced wall timeout, plus format/output caps.
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        except ImportError:
            pass
        send.send((True, _parse(raw, extension)))
    except Exception as exc:
        message = str(exc) if isinstance(exc, ParseError) else "The document could not be safely parsed."
        send.send((False, message))
    finally:
        send.close()


def parse_document(filename: str, raw: bytes, timeout: float = 10):
    extension = validate_signature(filename, raw)
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(send, raw, extension), daemon=True)
    process.start()
    send.close()
    try:
        if not receive.poll(timeout):
            raise ParseError("Document parsing exceeded the time limit.")
        try:
            success, result = receive.recv()
        except EOFError as exc:
            raise ParseError("Document parser stopped before producing safe output.") from exc
        if not success:
            raise ParseError(result)
        return result
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
        receive.close()


def chunk_sections(sections, document_id: str, version: str):
    chunks = []
    for section in sections:
        # Preserve exact text slices and locator/version identity, no invented summary.
        text = section["text"]
        offset = 0
        part = 0
        while offset < len(text):
            end = min(offset + 800, len(text))
            if end < len(text):
                boundary = text.rfind(" ", offset + 500, end)
                if boundary > offset:
                    end = boundary
            value = text[offset:end].strip()
            part += 1
            if value:
                chunks.append({"passage_id": f"{document_id}:{version}:{section['locator']}:{part}",
                               "source_id": document_id, "version": version,
                               "locator": section["locator"], "text": value})
            if len(chunks) > MAX_CHUNKS:
                raise ParseError("Document exceeds the 400-passage cap.")
            offset = end
    return chunks
