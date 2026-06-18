"""Export deterministic FastAPI OpenAPI schema."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings


def main() -> int:
    app = create_app(
        Settings(
            database_url="sqlite:///:memory:",
            redis_url="memory://",
            jwt_secret="openapi-export-secret",
            bootstrap_token="openapi-bootstrap",
            auto_migrate=False,
            cloud_queue_backend="memory",
        )
    )
    schema = app.openapi()
    output = Path("docs/api/openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
