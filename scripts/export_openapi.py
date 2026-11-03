"""Export the implemented typed contract with a temporary isolated runtime."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from api.config import Settings
from api.main import create_app

ROOT = Path(__file__).resolve().parents[1]
with TemporaryDirectory(prefix="legal-ai-schema-") as temporary:
    app = create_app(Settings(runtime_dir=Path(temporary)))
    (ROOT / "docs/openapi.json").write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf8", newline="\n")
    app.state.service.engine.dispose()
print("Exported implemented OpenAPI schema to docs/openapi.json")
