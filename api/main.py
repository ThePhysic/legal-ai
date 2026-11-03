"""Run: uv run uvicorn api.main:app --host 127.0.0.1 --port 8000."""

import asyncio
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from starlette.formparsers import MultiPartParser
from starlette.types import ASGIApp

from api.config import Settings
from api.models import AuthSession, Workspace, now
from api.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    CorpusResponse,
    DocumentDetail,
    DocumentListing,
    DocumentResponse,
    EvaluationListing,
    EvaluationRequest,
    EvaluationRun,
    ResearchRequest,
    ResearchResponse,
    SearchResponse,
    SessionRequest,
    SourceResponse,
)
from api.service import BackendService, iso

COOKIE = "legal_ai_session"
# Multipart uploads remain in capped memory until encrypted storage writes them.
# Starlette's default 1 MiB spool threshold would write private plaintext to /tmp.
MultiPartParser.spool_max_size = 10 * 1024 * 1024 + 64 * 1024


class BodyTooLarge(Exception):
    pass


class RequestGuard:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app, self.settings = app, settings
        self.upload_gate = asyncio.Semaphore(4)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/v1/documents" and scope["method"] == "POST":
            if self.upload_gate.locked():
                return await JSONResponse({"detail": "Upload concurrency limit reached."}, status_code=429)(scope, receive, send)
            async with self.upload_gate:
                return await self.guarded(scope, receive, send)
        return await self.guarded(scope, receive, send)

    async def guarded(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope["headers"]}
        origin = headers.get("origin")
        mutating = scope["method"] not in ("GET", "HEAD", "OPTIONS")
        if origin and origin not in self.settings.allowed_origins:
            return await JSONResponse({"detail": "Origin is not allowed."}, status_code=403)(scope, receive, send)
        if mutating and COOKIE + "=" in headers.get("cookie", "") and not origin and not headers.get("authorization", "").startswith("Bearer "):
            return await JSONResponse({"detail": "Cookie mutations require an allowed Origin."}, status_code=403)(scope, receive, send)
        cap = self.settings.upload_max_bytes + 64 * 1024 if scope["path"] == "/v1/documents" else 32 * 1024
        try:
            length = int(headers.get("content-length", "0"))
            if length < 0 or length > cap:
                raise BodyTooLarge
        except (ValueError, BodyTooLarge):
            return await JSONResponse({"detail": "Request body exceeds its allowed size."}, status_code=413)(scope, receive, send)
        consumed = 0
        body = bytearray()
        # Enforce aggregate bytes before invoking a JSON/multipart parser, even
        # for chunked requests without Content-Length. The bounded buffer is at
        # most 10 MiB plus multipart overhead and is never persisted unencrypted.
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            piece = message.get("body", b"")
            consumed += len(piece)
            if consumed > cap:
                return await JSONResponse({"detail": "Request body exceeds its allowed size."}, status_code=413)(scope, receive, send)
            body.extend(piece)
            if not message.get("more_body", False):
                break
        delivered = False

        async def capped_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def private_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend([(b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")])
            await send(message)

        try:
            await self.app(scope, capped_receive, private_send)
        except BodyTooLarge:
            await JSONResponse({"detail": "Request body exceeds its allowed size."}, status_code=413)(scope, receive, send)


class Limiter:
    def __init__(self):
        self.buckets = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, category, identity, limit):
        current = time.monotonic()
        with self.lock:
            key = category, identity
            bucket = self.buckets[key]
            while bucket and bucket[0] <= current - 60:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(429, "Rate limit reached. Try again in a minute.", headers={"Retry-After": "60"})
            bucket.append(current)
            # Bound inactive identity bookkeeping as well as requests.
            if len(self.buckets) > 10_000:
                stale = [key for key, values in self.buckets.items() if not values or values[-1] <= current - 60]
                for old_key in stale:
                    del self.buckets[old_key]


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    service = BackendService(settings)
    limiter = Limiter()
    app = FastAPI(title="legal.ai offline grounded API", version="0.1.0", docs_url="/docs", redoc_url=None)
    app.add_middleware(RequestGuard, settings=settings)
    app.state.service = service
    app.state.settings = settings
    app.state.evaluation_service = None
    try:
        from evaluations.service import EvaluationService

        app.state.evaluation_service = EvaluationService(service)
    except ModuleNotFoundError as exc:
        if exc.name not in ("evaluations", "evaluations.service"):
            raise

    def identify(request: Request):
        bearer = request.headers.get("authorization")
        cookie = request.cookies.get(COOKIE)
        tokens = []
        if bearer:
            if not bearer.startswith("Bearer ") or not bearer[7:]:
                raise HTTPException(401, "Invalid authorization.")
            tokens.append(bearer[7:])
        if cookie:
            tokens.append(cookie)
        if not tokens:
            raise HTTPException(401, "A local workspace session is required.")
        identities = []
        with service.db() as db:
            for token in tokens:
                if len(token) > 200:
                    raise HTTPException(401, "Invalid or expired session.")
                session = db.get(AuthSession, token_hash(token))
                if not session or session.expires_at <= now():
                    raise HTTPException(401, "Invalid or expired session.")
                identities.append(session.workspace_id)
        if len(set(identities)) != 1:
            raise HTTPException(401, "Conflicting cookie and bearer identities.")
        limiter.check("requests", identities[0], settings.requests_per_minute)
        return identities[0]

    WorkspaceID = Annotated[str, Depends(identify)]
    app.state.get_workspace = identify

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            return service.readiness()
        except Exception:
            return JSONResponse({"status": "unavailable", "mode": "offline"}, status_code=503)

    @app.post("/v1/sessions", status_code=201)
    def create_session(payload: SessionRequest, request: Request, response: Response):
        if not request.headers.get("origin") and (settings.production or not request.client or request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient")):
            raise HTTPException(403, "Origin-free demo bootstrap is limited to local SDK clients.")
        limiter.check("sessions", request.client.host if request.client else "local", settings.sessions_per_minute)
        token, workspace_id = secrets.token_urlsafe(40), secrets.token_hex(16)
        expires = now() + timedelta(hours=settings.session_hours)
        with service.db.begin() as db:
            db.add(Workspace(id=workspace_id, label_cipher=service.storage.seal(payload.label)))
            db.flush()
            db.add(AuthSession(token_hash=token_hash(token), workspace_id=workspace_id, expires_at=expires))
        response.set_cookie(COOKIE, token, httponly=True, secure=settings.secure_cookies, samesite="lax",
                            max_age=settings.session_hours * 3600, path="/")
        return {"access_token": token, "workspace_id": workspace_id, "expires_at": iso(expires)}

    @app.get("/v1/session")
    def get_session(workspace_id: WorkspaceID):
        with service.db() as db:
            workspace = db.get(Workspace, workspace_id)
            return {"workspace_id": workspace_id, "label": service.storage.open(workspace.label_cipher),
                    "mode": "offline", "provider_status": service.provider_status()}

    @app.delete("/v1/session", status_code=204)
    def revoke_session(workspace_id: WorkspaceID, response: Response):
        with service.db.begin() as db:
            db.execute(delete(AuthSession).where(AuthSession.workspace_id == workspace_id))
        response.delete_cookie(COOKIE, path="/", httponly=True, secure=settings.secure_cookies, samesite="lax")

    @app.get("/v1/corpus", response_model=CorpusResponse)
    def corpus():
        return service.corpus()

    @app.post("/v1/search", response_model=SearchResponse)
    def search(payload: ResearchRequest, workspace_id: WorkspaceID):
        with service.lock:
            return service.search(payload, workspace_id)

    @app.post("/v1/research", response_model=ResearchResponse)
    def research(payload: ResearchRequest, workspace_id: WorkspaceID):
        with service.lock:
            return service.research(payload, workspace_id)

    @app.get("/v1/sources/{source_id}", response_model=SourceResponse)
    def source(source_id: str, workspace_id: WorkspaceID):
        with service.lock:
            return service.source(workspace_id, source_id)

    @app.get("/v1/runs/{run_id}", response_model=SearchResponse | ResearchResponse | EvaluationRun)
    def run(run_id: str, workspace_id: WorkspaceID):
        with service.lock:
            return service.run(workspace_id, run_id)

    @app.get("/v1/documents", response_model=DocumentListing)
    def documents(workspace_id: WorkspaceID):
        return service.list_documents(workspace_id)

    @app.post("/v1/documents", status_code=201, response_model=DocumentResponse)
    async def upload(workspace_id: WorkspaceID, file: UploadFile = File(...), replace_document_id: str | None = Form(default=None)):
        limiter.check("uploads", workspace_id, settings.uploads_per_minute)
        # The ASGI guard bounds aggregate multipart bytes before parser spooling.
        raw = await file.read(settings.upload_max_bytes + 1)
        await file.close()
        # CPU/DB work runs in FastAPI's thread pool, avoiding event-loop blocking.
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(service.upload, workspace_id, file.filename or "document", raw, replace_document_id)

    @app.get("/v1/documents/{document_id}", response_model=DocumentDetail)
    def document(document_id: str, workspace_id: WorkspaceID):
        with service.lock:
            return service.document(workspace_id, document_id)

    @app.post("/v1/documents/{document_id}/retry", response_model=DocumentResponse)
    def retry(document_id: str, workspace_id: WorkspaceID):
        limiter.check("uploads", workspace_id, settings.uploads_per_minute)
        return service.process(workspace_id, document_id)

    @app.get("/v1/documents/{document_id}/download")
    def download(document_id: str, workspace_id: WorkspaceID):
        with service.lock:
            raw, filename, media_type = service.download(workspace_id, document_id)
        return Response(raw, media_type=media_type, headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe="")})

    @app.delete("/v1/documents/{document_id}")
    def remove_document(document_id: str, workspace_id: WorkspaceID):
        return service.delete_document(workspace_id, document_id)

    @app.post("/v1/documents/{document_id}/analysis", response_model=AnalysisResponse)
    def analysis(document_id: str, payload: AnalysisRequest, workspace_id: WorkspaceID):
        with service.lock:
            return service.analyze(workspace_id, document_id, payload.question, payload.locator)

    def evaluator():
        if app.state.evaluation_service is None:
            raise HTTPException(503, "The local evaluation module is not available.")
        return app.state.evaluation_service

    @app.get("/v1/evaluations", response_model=EvaluationListing)
    def evaluations(workspace_id: WorkspaceID):
        return evaluator().list_runs(workspace_id)

    @app.post("/v1/evaluations", status_code=201, response_model=EvaluationRun)
    def evaluate(payload: EvaluationRequest, workspace_id: WorkspaceID):
        limiter.check("evaluations", workspace_id, 10)
        return evaluator().create_run(workspace_id, payload.dataset_id, list(dict.fromkeys(payload.configurations)))

    @app.get("/v1/evaluations/{evaluation_id}", response_model=EvaluationRun)
    def evaluation(evaluation_id: str, workspace_id: WorkspaceID):
        return evaluator().get_run(workspace_id, evaluation_id)

    generated_openapi = app.openapi

    def authenticated_openapi():
        schema = generated_openapi()
        schema.setdefault("components", {}).setdefault("securitySchemes", {}).update({
            "cookieSession": {"type": "apiKey", "in": "cookie", "name": COOKIE},
            "bearerAuth": {"type": "http", "scheme": "bearer"},
        })
        for path, methods in schema["paths"].items():
            if path.startswith("/v1/") and path not in ("/v1/corpus", "/v1/sessions"):
                for operation in methods.values():
                    if isinstance(operation, dict):
                        operation["security"] = [{"cookieSession": []}, {"bearerAuth": []}]
        return schema

    app.openapi = authenticated_openapi

    return app


# Uvicorn factory usage (--factory api.main:create_app) avoids initializing runtime
# data during tooling imports. `api.main:app` remains the simple local entry point.
def __getattr__(name):
    if name == "app":
        global _default_app
        if "_default_app" not in globals():
            _default_app = create_app()
        return _default_app
    raise AttributeError(name)
