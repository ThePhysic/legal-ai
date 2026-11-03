"""CLI: python -m evaluations run --output evaluations/reports/starter.json."""

import argparse
import json
import uuid
from pathlib import Path

from api.config import Settings
from api.models import Workspace
from api.service import BackendService
from evaluations.datasets import list_datasets
from evaluations.service import CONFIGURATIONS, EvaluationService


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reproduce the frozen public benchmark locally, with zero provider budget.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("datasets", help="List frozen public datasets and judgment provenance.")
    run = sub.add_parser("run", help="Measure offline retrieval and extractive research; optionally save a safe public report.")
    run.add_argument("--dataset", default="ca-tenancy-starter-v1")
    run.add_argument("--configurations", nargs="+", choices=CONFIGURATIONS, default=list(CONFIGURATIONS))
    run.add_argument("--runtime", type=Path, default=Path(".local/evaluation-runtime"))
    run.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "datasets":
        print(json.dumps({"datasets": list_datasets()}, indent=2))
        return 0
    settings = Settings(runtime_dir=args.runtime.resolve(), database_url="", offline_only=True)
    backend = BackendService(settings)
    workspace_id = uuid.uuid4().hex
    try:
        with backend.db.begin() as db:
            db.add(Workspace(id=workspace_id, label_cipher=backend.storage.seal("Offline benchmark CLI")))
        report = EvaluationService(backend).create_run(workspace_id, args.dataset, args.configurations)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # The evaluator exports no private question, generated answer,
            # source excerpt, runtime credential, token or workspace identity.
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary = {"evaluation_id": report["evaluation_id"], "dataset_id": report["dataset_id"],
                   "dataset_revision": report["dataset_revision"], "status": report["status"],
                   "judgment_provenance": report["judgment_provenance"],
                   "configurations": [{"configuration": item["configuration"], "metrics": item["metrics"]}
                                      for item in report["configurations"]],
                   "report": str(args.output) if args.output else None}
        print(json.dumps(summary, indent=2))
        return 1 if report["status"] == "completed_with_errors" else 0
    finally:
        backend.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
