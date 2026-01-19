# OpenSolve Pipe API

FastAPI backend for hydraulic network analysis.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run development server
uvicorn opensolve_pipe.main:app --reload --port 8000

# Run tests
pytest

# Run linter
ruff check .
ruff format .
```

## Endpoints

- `GET /` - API information
- `GET /health` - Health check
- `GET /docs` - OpenAPI documentation
- `GET /redoc` - ReDoc documentation

## Development

### Running Tests

```bash
pytest -v                    # Verbose output
pytest --cov                 # With coverage
pytest -x                    # Stop on first failure
```

### Code Quality

```bash
ruff check .                 # Lint
ruff format .                # Format
mypy src/                    # Type check
```
