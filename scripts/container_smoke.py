"""Exercise the real local container/proxy/PostgreSQL product with synthetic data.

The script creates two isolated demo workspaces; tokens remain in memory. No model
or Pinecone requests are made. It never prints passwords, tokens or document text.
"""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-url", default="http://127.0.0.1:3017")
    parser.add_argument("--api-url", default="http://127.0.0.1:8017")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/container-smoke.json")
    args = parser.parse_args()
    checks = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    def successful(response):
        response.raise_for_status()
        return response.json()

    with httpx.Client(base_url=args.app_url, headers={"Origin": args.app_url}, timeout=90) as owner, \
         httpx.Client(base_url=args.app_url, headers={"Origin": args.app_url}, timeout=90) as other:
        check("Production frontend responds", owner.get("/").status_code == 200)
        ready = successful(httpx.get(args.api_url + "/health/ready", timeout=15))
        check("Container API is ready in offline mode", ready.get("mode") == "offline")
        identity = successful(owner.post("/api/v1/sessions", json={"label": "Container smoke owner"}))
        foreign_identity = successful(other.post("/api/v1/sessions", json={"label": "Container smoke other"}))
        check("Proxy bootstraps distinct private workspaces", identity["workspace_id"] != foreign_identity["workspace_id"])
        check("Session cookie is HttpOnly", any(cookie.has_nonstandard_attr("HttpOnly") for cookie in owner.cookies.jar))
        corpus = successful(owner.get("/api/v1/corpus"))
        check("Actual frozen public sources loaded", len(corpus["sources"]) == 3)
        result = successful(owner.post("/api/v1/research", json={"question": "Find Civil Code 1950.5 security deposit text", "configuration": "lexical"}))
        check("Statute identifier is not misread as historical year", result["status"] == "answered" and bool(result["claims"]))
        check("Claims bind versioned passages", all(c["identity_validated"] and all(any(p["passage_id"] == pid and p["version"] in pid for p in result["passages"]) for pid in c["passage_ids"]) for c in result["claims"]))
        check("Research observes zero provider calls", result["usage"].get("provider_calls") == 0)
        sample = (ROOT / "samples/example-lease.txt").read_bytes()
        document = successful(owner.post("/api/v1/documents", files={"file": ("container-synthetic-lease.txt", sample, "text/plain")}))
        document_id = document["document_id"]
        check("Real private ingestion is ready", document["status"] == "ready" and document["passage_count"] > 0)
        detail = successful(owner.get("/api/v1/documents/" + document_id))
        check("Actual parser exposes sections and private passages", bool(detail["sections"]) and all(p["source"]["scope"] == "private" for p in detail["passages"]))
        check("Foreign workspace cannot read document", other.get("/api/v1/documents/" + document_id).status_code == 404)
        check("Foreign workspace cannot download document", other.get("/api/v1/documents/" + document_id + "/download").status_code == 404)
        source_id = detail["passages"][0]["source_id"]
        check("Foreign workspace cannot read nested private source", other.get("/api/v1/sources/" + source_id).status_code == 404)
        analysis = successful(owner.post("/api/v1/documents/" + document_id + "/analysis", json={"question": "What does this lease say about the security deposit?"}))
        check("Document Q&A uses own actual private text", analysis["answer"] is not None and analysis["answer"]["status"] == "answered" and all(p["source"]["scope"] == "private" for p in analysis["answer"]["passages"]))
        check("Rule-based considerations are not verified legal findings", all(not f["verified"] for f in analysis["findings"] if f["kind"] in {"consideration", "evidence_gap"}))
        replacement = successful(owner.post("/api/v1/documents", data={"replace_document_id": document_id}, files={"file": ("container-synthetic-replacement.txt", sample.replace(b"$350", b"$275"), "text/plain")}))
        check("Replacement publishes a different ready version", replacement["document_id"] != document_id and replacement["status"] == "ready")
        check("Replaced original is no longer downloadable", owner.get("/api/v1/documents/" + document_id + "/download").status_code == 404)
        deleted = successful(owner.delete("/api/v1/documents/" + replacement["document_id"]))
        check("Real deletion cleanup completes", deleted["status"] == "deleted")
        check("Deleted original cannot be downloaded", owner.get("/api/v1/documents/" + replacement["document_id"] + "/download").status_code == 404)
        listing = successful(owner.get("/api/v1/evaluations"))
        run = successful(owner.post("/api/v1/evaluations", json={"dataset_id": listing["datasets"][0]["id"], "configurations": ["lexical", "dense", "hybrid", "rerank"]}))
        check("Measured evaluation completes across four configurations", run["status"] in {"completed", "complete"} and len(run["configurations"]) == 4)
        check("Owner can reload persisted PostgreSQL evaluation", owner.get("/api/v1/evaluations/" + run["evaluation_id"]).status_code == 200)
        check("Foreign workspace cannot load evaluation", other.get("/api/v1/evaluations/" + run["evaluation_id"]).status_code == 404)
    report = {"checked_at": datetime.now(UTC).isoformat(), "app_url": args.app_url, "api_url": args.api_url,
              "scope": "Actual local Docker Compose, PostgreSQL, encrypted storage and production Next.js proxy; synthetic inputs only",
              "passed": len(checks), "failed": 0, "checks": checks,
              "limitations": ["No live provider/model/Pinecone calls", "No public deployment", "No independent legal/semantic assessment"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"passed": len(checks), "failed": 0, "output": str(args.output)}))


if __name__ == "__main__":
    main()
