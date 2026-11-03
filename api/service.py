import hashlib
import json
import mimetypes
import re
import secrets
import threading
import time
import uuid
from datetime import UTC, date
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.orm import sessionmaker

from api.config import Settings
from api.models import Base, Chunk, Document, Run
from api.parsing import ParseError, chunk_sections, parse_document, validate_signature
from api.retrieval import (
    bounded_context,
    evidence_relevance,
    explicit_evidence_conflicts,
    public_topic_gap,
    retrieve,
    tokenize,
    unsafe_question,
    validate_claims,
)
from api.schemas import ResearchRequest
from api.storage import EncryptedStorage

SOURCE_KEYS = ("source_id", "title", "publisher", "url", "source_type", "jurisdiction", "version",
               "content_hash", "captured_at", "effective_from", "effective_to", "rights_basis", "scope")
METHODS = {
    "lexical": "BM25 exact-term retrieval (k1=1.5, b=0.75)",
    "dense": "Deterministic local signed hash vectors with fixed synonyms; not Pinecone or a pretrained semantic model",
    "hybrid": "Reciprocal rank fusion of BM25 and local hash vectors (RRF k=60)",
    "rerank": "RRF followed by bounded deterministic term/identifier coverage reranking (30 candidates)",
}
LIMITS = ["Educational source extraction, not a legal opinion or a case-specific determination.",
          "Citation checks validate quotation/source/version identity only. Semantic support is not independently assessed.",
          "Offline execution: no Pinecone or language-model calls were made."]


def iso(value):
    return value.replace(tzinfo=UTC).isoformat()


class BackendService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage = EncryptedStorage(settings.runtime_dir, settings.encryption_key)
        kwargs = {"connect_args": {"check_same_thread": False, "timeout": 20}} if settings.database_url.startswith("sqlite") else {}
        self.engine = create_engine(settings.database_url, **kwargs)
        if settings.database_url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def sqlite_settings(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=20000")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(self.engine, expire_on_commit=False)
        # An external PostgreSQL database may outlive a lost local runtime
        # directory. Verify the key against persisted metadata before serving.
        from api.models import Workspace

        try:
            with self.db() as db:
                workspace = db.scalar(select(Workspace).limit(1))
                if workspace:
                    self.storage.open(workspace.label_cipher)
        except Exception as exc:
            self.engine.dispose()
            raise RuntimeError("Runtime key cannot decrypt existing workspace metadata; restore the original key.") from exc
        self.lock = threading.RLock()
        self.sources, self.public_passages, self.corpus_revision = self.load_corpus(settings.corpus_path)
        self.failure_hook = None  # explicit fault-injection seam, never remotely configurable
        self.recover_interrupted()

    def load_corpus(self, path: Path):
        if not path.exists():
            return {}, [], "unconfigured"
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        sources, passages, identities = {}, [], set()
        for item in manifest["sources"]:
            source = {key: item.get(key) for key in SOURCE_KEYS}
            source["scope"] = "public"
            if not all(source.get(key) for key in ("source_id", "title", "publisher", "url", "version", "rights_basis")):
                raise ValueError("Corpus source metadata is incomplete.")
            if source["source_id"] in sources:
                raise ValueError("Corpus contains duplicate source IDs.")
            file = (path.parent / item["file"]).resolve()
            if not file.is_relative_to(path.parent.resolve()):
                raise ValueError("Corpus file path escapes corpus directory.")
            raw = file.read_bytes()
            if hashlib.sha256(raw).hexdigest() != source["content_hash"]:
                raise ValueError("Corpus snapshot content hash mismatch.")
            snapshot = raw.decode("utf-8-sig")
            sections = item.get("sections") or [{"locator": "text", "title": source["title"], "text": snapshot}]
            for index, section in enumerate(sections):
                if re.sub(r"\s+", " ", section["text"]).strip() not in re.sub(r"\s+", " ", snapshot):
                    raise ValueError("Corpus section is not a whitespace-normalized snapshot excerpt.")
                if section.get("passage_id") and len(section["text"].encode("utf-8")) <= 1000:
                    pieces = [{"passage_id": section["passage_id"], "source_id": source["source_id"],
                               "version": source["version"], "locator": section["locator"], "text": section["text"]}]
                else:
                    pieces = chunk_sections([section], source["source_id"], source["version"])
                for part, piece in enumerate(pieces):
                    explicit = section.get("passage_id")
                    identity = explicit if explicit and len(pieces) == 1 else (f"{explicit}:part-{part+1}" if explicit else piece["passage_id"])
                    if identity in identities:
                        raise ValueError("Corpus contains duplicate passage IDs.")
                    identities.add(identity)
                    passages.append({**piece, "passage_id": identity, "source": source, "score": 0.0})
            sources[source["source_id"]] = source
        return sources, passages, manifest.get("revision", "unknown")

    def corpus(self):
        return {"sources": list(self.sources.values()), "coverage": sorted({item["jurisdiction"] for item in self.sources.values()}),
                "mode": "offline", "limitations": ["A small captured California landlord–tenant statutory corpus; no comprehensive coverage.",
                "Capture timestamps do not establish historical applicability. Sources without validated date bounds cannot answer date-specific questions."]}

    def provider_status(self):
        return {"pinecone": "disabled_offline", "language_model": "disabled_offline",
                "local_vectors": "deterministic_feature_hashing", "semantic_support": "not_assessed"}

    def evaluation_manifest(self, configuration, top_k=10):
        return {"mode": "offline", "configuration": configuration, "embedding_model": "local-signed-sha256-features",
                "embedding_version": "1", "dimensions": 384, "metric": "cosine", "index_schema": "legal-ai-v1",
                "provider": "local", "namespace": "public-v1", "bm25_k1": 1.5, "bm25_b": 0.75,
                "fusion_k": 60, "reranker": "term-identifier-coverage-v1", "rerank_candidate_limit": 30,
                "context_token_budget": self.settings.context_tokens, "top_k": top_k,
                "corpus_revision": self.corpus_revision, "question_guard": "captured-ca-topics-personal-verdict-v1"}

    def readiness(self):
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        # Prove object storage is writable/readable and encryption round-trips.
        self.storage.probe()
        return {"status": "ready", "mode": "offline", "database": "ok", "encrypted_storage": "ok",
                "corpus_sources": len(self.sources), "providers": self.provider_status()}

    def owned(self, db, workspace_id, document_id, *, allow_deleted=False):
        document = db.scalar(select(Document).where(Document.id == document_id, Document.workspace_id == workspace_id))
        if not document or (not allow_deleted and document.status in ("deleted", "deletion_pending")):
            raise HTTPException(404, "Document not found.")
        return document

    def document_json(self, document):
        payload = self.storage.open(document.payload)
        return {"document_id": document.id, "filename": payload["filename"], "media_type": payload["media_type"],
                "status": document.status, "version": document.version, "content_hash": document.content_hash,
                "created_at": iso(document.created_at), "section_count": len(payload.get("sections", [])),
                "passage_count": payload.get("passage_count", 0), "error": payload.get("error"),
                "processing": {"attempts": document.attempts, "current": document.is_current,
                               "parser": "pypdf/python-docx/utf8 isolated process", "chunker": "exact-800-v1",
                               "mode": "offline", "history": payload.get("history", [])}}

    def source_for(self, document):
        payload = self.storage.open(document.payload)
        return {"source_id": document.id, "title": payload["filename"], "publisher": "Workspace upload",
                "url": f"/v1/documents/{document.id}/download", "source_type": "private_document",
                "jurisdiction": "unverified", "version": document.version, "content_hash": document.content_hash,
                "captured_at": iso(document.created_at), "effective_from": None, "effective_to": None,
                "rights_basis": "Private user-provided content, restricted to the owning workspace.", "scope": "private"}

    def private_passages(self, db, workspace_id, document_id=None):
        query = select(Document).where(Document.workspace_id == workspace_id, Document.status == "ready", Document.is_current.is_(True))
        if document_id:
            self.owned(db, workspace_id, document_id)
            query = query.where(Document.id == document_id)
        documents = {document.id: document for document in db.scalars(query)}
        if not documents:
            return []
        chunks = db.scalars(select(Chunk).where(Chunk.workspace_id == workspace_id, Chunk.document_id.in_(documents)))
        return [{**self.storage.open(chunk.payload), "source": self.source_for(documents[chunk.document_id]), "score": 0.0}
                for chunk in chunks if chunk.version == documents[chunk.document_id].version]

    def store_run(self, workspace_id, payload, private=False):
        with self.db.begin() as db:
            db.add(Run(id=payload["run_id"], workspace_id=workspace_id, private=private, payload=self.storage.seal(payload)))

    def search(self, request: ResearchRequest, workspace_id, *, persist=True, locator=None):
        started = time.perf_counter()
        gaps = []
        if request.source_scope == "public" and request.document_id:
            raise HTTPException(422, "document_id requires private source_scope.")
        with self.db() as db:
            candidates = self.public_passages if request.source_scope == "public" else self.private_passages(db, workspace_id, request.document_id)
        if request.source_scope == "public":
            candidates = [item for item in candidates if item["source"]["jurisdiction"] == request.jurisdiction]
        else:
            gaps.append("Private document jurisdiction and legal applicability are unverified; results describe uploaded text only.")
        if locator:
            candidates = [item for item in candidates if item["locator"] == locator]
        if not candidates:
            gaps.append("No authorized ready sources cover the requested jurisdiction and scope.")
        date_requested = request.applicable_on
        date_wording = re.sub(r"\b(?:civil\s+code|code|section)\s+\d{4}(?:\.\d+)?|§\s*\d{4}(?:\.\d+)?", "", request.question, flags=re.I)
        if request.source_scope == "public" and not date_requested and re.search(r"\b(?:19|20)\d{2}\b(?!\.\d)|\b(historic|historical|last year|previous year|today|currently|current law|as of)\b", date_wording, re.I):
            gaps.append("Date-specific wording requires an explicit applicability date and validated source effective-date bounds.")
            candidates = []
        if date_requested:
            selected = []
            for passage in candidates:
                source = passage["source"]
                lower, upper = source["effective_from"], source["effective_to"]
                if lower and upper and date.fromisoformat(lower) <= date_requested <= date.fromisoformat(upper):
                    selected.append(passage)
            if len(selected) < len(candidates):
                gaps.append("Sources with unknown or nonmatching effective-date bounds were excluded; capture date is not applicability evidence.")
            candidates = selected
        unsafe = unsafe_question(request.question, source_scope=request.source_scope)
        if unsafe:
            gaps.append(unsafe)
            candidates = []
        if request.source_scope == "public":
            topic_gap = public_topic_gap(request.question, list(self.sources.values()))
            if topic_gap:
                gaps.append(topic_gap)
                candidates = []
        # Source instructions are never instructions to tools or authentication.
        candidates = [item for item in candidates if not re.search(r"ignore\b.{0,45}\b(instructions|previous)|system prompt|reveal.{0,20}(secret|token)", item["text"], re.I)]
        ranked_candidates = retrieve(request.question, candidates, request.configuration, 30)
        conflicts = explicit_evidence_conflicts(ranked_candidates)
        ranked = ranked_candidates[:request.top_k]
        if conflicts:
            gaps.append("A bounded mechanical check found otherwise-matching passages with explicit opposite/negated wording. The system abstains rather than resolving them; broader legal contradictions are not assessed.")
        if not evidence_relevance(request.question, ranked):
            ranked = []
            gaps.append("The available passages do not provide enough relevant evidence for this question.")
        elapsed = (time.perf_counter() - started) * 1000
        usage = {"search_ms": elapsed, "input_tokens": 0, "output_tokens": 0, "provider_calls": 0,
                 "provider_cost_usd": 0, "cost_basis": "No provider calls; local CPU cost is not estimated."}
        trace = {"mode": "offline", "corpus_revision": self.corpus_revision, "candidate_count": len(candidates),
                 "evidence_conflicts": conflicts,
                 "returned_passage_ids": [item["passage_id"] for item in ranked],
                 "filters": {"scope": request.source_scope, "jurisdiction": request.jurisdiction,
                             "jurisdiction_authority_filter_applied": request.source_scope == "public",
                             "applicable_on": str(request.applicable_on) if request.applicable_on else None,
                             "document_id": request.document_id, "current_versions_only": True},
                 "manifest": {**self.evaluation_manifest(request.configuration, request.top_k),
                     "namespace": "authorized-private" if request.source_scope == "private" else "public-v1"}}
        response = {"run_id": uuid.uuid4().hex, "configuration": request.configuration, "method": METHODS[request.configuration],
                    "passages": ranked, "coverage_gaps": gaps, "trace": trace, "usage": usage}
        if persist:
            self.store_run(workspace_id, response, request.source_scope == "private")
        return response

    def search_public(self, question, configuration, jurisdiction="US-CA", applicable_on=None, top_k=10):
        return self.search(ResearchRequest(question=question, configuration=configuration, jurisdiction=jurisdiction,
                           applicable_on=applicable_on, top_k=top_k), workspace_id=None, persist=False)

    def research(self, request: ResearchRequest, workspace_id, *, persist=True, locator=None):
        started = time.perf_counter()
        searched = self.search(request, workspace_id, persist=False, locator=locator)
        context, context_count = bounded_context(searched["passages"], self.settings.context_tokens)
        gaps = searched["coverage_gaps"][:]
        claims = []
        if searched["passages"] and not context:
            gaps.append("Relevant passages exceeded the bounded context budget; no unsupported answer was generated.")
        terms = set(tokenize(request.question))
        for passage in context:
            if searched["trace"]["evidence_conflicts"]:
                break
            sentences = re.split(r"(?<=[.!?;])\s+|\n+", passage["text"])
            sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
            if not sentences:
                continue
            quote = max(sentences, key=lambda value: (len(terms & set(tokenize(value))), -len(value)))
            quote = quote[:700]
            identity = hashlib.sha256((passage["passage_id"] + quote).encode()).hexdigest()[:16]
            claims.append({"claim_id": identity, "text": quote, "passage_ids": [passage["passage_id"]],
                           "source_ids": [passage["source_id"]], "support_status": "verbatim_quote", "identity_validated": True})
        if not validate_claims(claims, context):
            raise RuntimeError("Internal citation identity validation failed")
        answered = bool(claims)
        answer = "\n\n".join(f'“{claim["text"]}” [{index}]' for index, claim in enumerate(claims, 1)) if answered else "There is insufficient source evidence to answer this question within the available corpus and applicability bounds."
        usage = {**searched["usage"], "answer_ms": (time.perf_counter() - started) * 1000,
                 "context_token_upper_bound": context_count, "semantic_support": "not_assessed"}
        response = {"run_id": searched["run_id"], "status": "answered" if answered else "insufficient_evidence",
                    "question": request.question, "answer": answer, "claims": claims, "passages": context,
                    "coverage_gaps": gaps, "limitations": LIMITS, "method": "Deterministic extractive quotations; " + searched["method"],
                    "configuration": request.configuration, "usage": usage}
        if persist:
            self.store_run(workspace_id, {**response, "trace": searched["trace"]}, request.source_scope == "private")
        return response

    def run(self, workspace_id, run_id):
        with self.db() as db:
            run = db.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == workspace_id))
            if not run:
                raise HTTPException(404, "Run not found.")
            return self.storage.open(run.payload)

    def source(self, workspace_id, source_id):
        if source_id in self.sources:
            return {**self.sources[source_id], "passages": [item for item in self.public_passages if item["source_id"] == source_id]}
        with self.db() as db:
            document = self.owned(db, workspace_id, source_id)
            if document.status != "ready" or not document.is_current:
                raise HTTPException(404, "Source not available.")
            return {**self.source_for(document), "passages": self.private_passages(db, workspace_id, source_id)}

    def list_documents(self, workspace_id):
        with self.db() as db:
            documents = db.scalars(select(Document).where(Document.workspace_id == workspace_id).order_by(Document.created_at.desc()))
            return {"documents": [self.document_json(document) for document in documents]}

    def document(self, workspace_id, document_id):
        with self.db() as db:
            document = self.owned(db, workspace_id, document_id, allow_deleted=True)
            payload = self.storage.open(document.payload)
            ready = document.status == "ready" and document.is_current
            return {**self.document_json(document), "sections": payload.get("sections", []) if ready else [],
                    "passages": self.private_passages(db, workspace_id, document_id) if ready else []}

    def upload(self, workspace_id, filename, raw, replace_document_id=None):
        if not raw or len(raw) > self.settings.upload_max_bytes:
            raise HTTPException(413, "Document is empty or exceeds the 10 MiB upload cap.")
        filename = Path(filename.replace("\\", "/")).name[:160]
        try:
            extension = validate_signature(filename, raw)
        except ParseError as exc:
            raise HTTPException(422, str(exc)) from exc
        digest = hashlib.sha256(raw).hexdigest()
        with self.lock:
            existing_result = None
            with self.db.begin() as db:
                if replace_document_id:
                    previous = self.owned(db, workspace_id, replace_document_id)
                    if previous.status != "ready" or not previous.is_current:
                        raise HTTPException(409, "Only a current ready document can be replaced.")
                document = db.scalar(select(Document).where(Document.workspace_id == workspace_id, Document.content_hash == digest))
                if document and document.status == "ready":
                    existing_result = self.document_json(document)
                    if replace_document_id and replace_document_id != document.id:
                        previous.status, previous.is_current = "deletion_pending", False
                        self._revoke_content(db, workspace_id, previous)
                elif not document:
                    document = Document(id=secrets.token_hex(16), workspace_id=workspace_id, content_hash=digest,
                        version=digest[:16], status="uploaded", is_current=False, replaced_id=replace_document_id,
                        payload=self.storage.seal({"filename": filename, "media_type": mimetypes.types_map.get(extension, "application/octet-stream"),
                            "sections": [], "passage_count": 0, "error": None, "history": ["uploaded"]}))
                    db.add(document)
                    db.flush()
                elif document.status in ("deleted", "deletion_pending"):
                    document.status = "uploaded"
                    document.replaced_id = replace_document_id
                    document.payload = self.storage.seal({"filename": filename,
                        "media_type": mimetypes.types_map.get(extension, "application/octet-stream"), "sections": [],
                        "passage_count": 0, "error": None, "history": ["uploaded"]})
                elif replace_document_id:
                    document.replaced_id = replace_document_id
                document_id = document.id
            if existing_result:
                if replace_document_id and replace_document_id != document_id:
                    self.delete_document(workspace_id, replace_document_id)
                return existing_result
            # DB record is durable before storage, so a crash is an inspectable retryable job.
            try:
                self.storage.put(workspace_id, document_id, raw)
            except Exception:
                self._failed(workspace_id, document_id, "Encrypted object write failed; upload the same content to retry.")
                return self.document(workspace_id, document_id)
            return self.process(workspace_id, document_id)

    def _stage(self, workspace_id, document_id, stage):
        with self.db.begin() as db:
            document = self.owned(db, workspace_id, document_id)
            payload = self.storage.open(document.payload)
            payload.setdefault("history", []).append(stage)
            payload["error"] = None
            document.status = stage
            document.is_current = False
            document.payload = self.storage.seal(payload)
        if self.failure_hook:
            self.failure_hook(stage)

    def _failed(self, workspace_id, document_id, message):
        with self.db.begin() as db:
            document = self.owned(db, workspace_id, document_id)
            payload = self.storage.open(document.payload)
            payload["error"] = message
            document.payload = self.storage.seal(payload)
            document.status, document.is_current = "failed", False
            db.execute(delete(Chunk).where(Chunk.document_id == document_id, Chunk.workspace_id == workspace_id))

    def process(self, workspace_id, document_id):
        with self.lock:
            with self.db.begin() as db:
                document = self.owned(db, workspace_id, document_id)
                if document.status == "ready":
                    return self.document_json(document)
                payload = self.storage.open(document.payload)
                filename, version, replaced_id = payload["filename"], document.version, document.replaced_id
                if replaced_id and replaced_id != document_id:
                    parent = self.owned(db, workspace_id, replaced_id, allow_deleted=True)
                    if parent.status != "ready" or not parent.is_current:
                        raise HTTPException(409, "This replacement is stale because its original version was deleted or superseded. Upload again against the current document.")
                document.attempts += 1
            try:
                self._stage(workspace_id, document_id, "extracting")
                raw = self.storage.get(workspace_id, document_id)
                sections = parse_document(filename, raw, self.settings.parse_timeout_seconds)
                self._stage(workspace_id, document_id, "chunking")
                chunks = chunk_sections(sections, document_id, version)
                self._stage(workspace_id, document_id, "indexing")
                with self.db.begin() as db:
                    db.execute(delete(Chunk).where(Chunk.document_id == document_id, Chunk.workspace_id == workspace_id))
                    db.add_all([Chunk(id=item["passage_id"], document_id=document_id, workspace_id=workspace_id,
                                      version=version, payload=self.storage.seal(item)) for item in chunks])
                self._stage(workspace_id, document_id, "verifying")
                with self.db.begin() as db:
                    document = self.owned(db, workspace_id, document_id)
                    previous = None
                    if replaced_id and replaced_id != document_id:
                        previous = db.scalar(select(Document).where(Document.id == replaced_id,
                            Document.workspace_id == workspace_id).with_for_update())
                        if not previous or previous.status != "ready" or not previous.is_current:
                            raise RuntimeError("Replacement parent was superseded during indexing")
                    stored = list(db.scalars(select(Chunk).where(Chunk.document_id == document_id, Chunk.workspace_id == workspace_id)))
                    if len(stored) != len(chunks) or any(self.storage.open(item.payload)["version"] != version for item in stored):
                        raise RuntimeError("Index verification failed")
                    payload = self.storage.open(document.payload)
                    payload.update(sections=sections, passage_count=len(chunks), error=None)
                    payload["history"].append("ready")
                    document.status, document.is_current = "ready", True
                    document.payload = self.storage.seal(payload)
                    if previous:
                        previous.is_current, previous.status = False, "deletion_pending"
                        self._revoke_content(db, workspace_id, previous)
                if replaced_id and replaced_id != document_id:
                    self.delete_document(workspace_id, replaced_id)
            except Exception as exc:
                message = str(exc) if isinstance(exc, ParseError) else "Processing was interrupted or failed; retry is safe."
                self._failed(workspace_id, document_id, message)
            return self.document(workspace_id, document_id)

    def recover_interrupted(self):
        with self.db() as db:
            interrupted = [(item.workspace_id, item.id, item.status) for item in db.scalars(select(Document).where(
                Document.status.in_(["uploaded", "extracting", "chunking", "indexing", "verifying", "deletion_pending"])))]
        for workspace, identity, status in interrupted:
            if status == "deletion_pending":
                self.delete_document(workspace, identity)
            else:
                self._failed(workspace, identity, "Previous processing was interrupted; retry this durable job.")

    def _revoke_content(self, db, workspace_id, document):
        payload = self.storage.open(document.payload)
        payload.update(sections=[], passage_count=0, error=None)
        document.payload = self.storage.seal(payload)
        db.execute(delete(Chunk).where(Chunk.workspace_id == workspace_id, Chunk.document_id == document.id))
        # Conservative purge of all private workspace runs prevents copied document
        # excerpts from surviving deletion in searches, answers or diagnostics.
        db.execute(delete(Run).where(Run.workspace_id == workspace_id, Run.private.is_(True)))

    def delete_document(self, workspace_id, document_id):
        with self.lock:
            with self.db.begin() as db:
                document = self.owned(db, workspace_id, document_id, allow_deleted=True)
                document.status, document.is_current = "deletion_pending", False
                self._revoke_content(db, workspace_id, document)
            try:
                self.storage.delete(workspace_id, document_id)
            except OSError:
                return {"document_id": document_id, "status": "deletion_pending"}
            with self.db.begin() as db:
                document = self.owned(db, workspace_id, document_id, allow_deleted=True)
                document.status = "deleted"
            return {"document_id": document_id, "status": "deleted"}

    def download(self, workspace_id, document_id):
        with self.db() as db:
            document = self.owned(db, workspace_id, document_id)
            payload = self.storage.open(document.payload)
            try:
                return self.storage.get(workspace_id, document_id), payload["filename"], payload["media_type"]
            except FileNotFoundError as exc:
                raise HTTPException(409, "Encrypted object is unavailable; retry upload.") from exc

    def analyze(self, workspace_id, document_id, question=None, locator=None):
        detail = self.document(workspace_id, document_id)
        if detail["status"] != "ready" or not detail["processing"]["current"]:
            raise HTTPException(409, "Document analysis requires a current ready document.")
        sections = detail["sections"]
        if locator:
            sections = [item for item in sections if item["locator"] == locator]
            if not sections:
                raise HTTPException(404, "Section not found.")
        selected = {item["locator"] for item in sections}
        passages = [item for item in detail["passages"] if item["locator"] in selected]
        findings = []
        for section in sections[:20]:
            refs = [item["passage_id"] for item in passages if item["locator"] == section["locator"]]
            findings.append({"kind": "contract_text", "title": section["title"], "text": section["text"][:700],
                             "locator": section["locator"], "passage_ids": refs, "verified": True,
                             "identity_validated": True, "support_status": "verbatim_quote"})
            for match in list(re.finditer(r"\$\s?\d[\d,]*(?:\.\d{2})?|\b\d{4}-\d{2}-\d{2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b", section["text"], re.I))[:10]:
                literal = match.group()
                findings.append({"kind": "document_fact", "title": "Literal amount or date in document",
                    "text": literal, "locator": section["locator"], "passage_ids": refs, "verified": True,
                    "identity_validated": True, "support_status": "verbatim_quote"})
        all_text = "\n".join(item["text"] for item in sections)
        comparison_topics = []
        for pattern, topic in [(r"deposit|security", "California security deposit deductions return"),
                               (r"repair|heating|plumbing|habitability", "California tenant dwelling repair habitability"),
                               (r"entry|enter|inspection", "California landlord entry notice")]:
            if re.search(pattern, all_text, re.I):
                comparison_topics.append(topic)
        compared = []
        seen = set()
        for topic in comparison_topics:
            result = self.search_public(topic, "hybrid", top_k=2)
            for passage in result["passages"]:
                if passage["passage_id"] not in seen:
                    compared.append(passage)
                    seen.add(passage["passage_id"])
        findings.append({"kind": "consideration", "title": "Compare wording and applicability",
            "text": "Rule-based topic matching found related public excerpts. Compare the quoted wording, jurisdiction and effective dates; this does not establish whether a clause is lawful or enforceable.",
            "locator": None, "passage_ids": [], "verified": False, "identity_validated": False,
            "support_status": "not_assessed"})
        answer = self.research(ResearchRequest(question=question, source_scope="private", document_id=document_id,
                               configuration="hybrid"), workspace_id, locator=locator) if question else None
        # Summary consists of actual opening excerpts, explicitly labelled.
        summary = "Document excerpts: " + " … ".join(item["text"][:240] for item in sections[:3])
        return {"document_id": document_id, "summary": summary, "findings": findings[:60], "answer": answer,
                "comparison": {"passages": compared[:6], "limitations": ["Public-source comparison uses rule-based topic matching, not a legal compliance assessment.",
                    "Document statements are assertions in uploaded text; identity, payment and truth are not independently verified.",
                    "Unknown effective-date bounds prevent a determination of applicable law."]},
                "method": "Deterministic literal extraction, private-passage Q&A and rule-based public-source comparison",
                "limitations": LIMITS + ["The verified field checks literal source identity only; it is not semantic or factual verification."]}
