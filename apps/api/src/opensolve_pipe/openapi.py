"""Print the OpenAPI schema (used to generate the frontend TypeScript types)."""

import json

from .main import app


def main() -> None:
    print(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
