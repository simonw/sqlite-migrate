# Run tests and linters
@default: test lint

# Install dependencies and test dependencies
@init:
  uv sync

# Run pytest with supplied options
@test *options:
  uv run pytest {{options}}

# Run linters
@lint:
  echo "Linters..."
  echo "  Black"
  uv run black . --check
  echo "  mypy"
  uv run mypy sqlite_migrate tests
  echo "  ruff"
  uv run ruff check .


# Apply Black
@black:
  uv run black .

# Run automatic fixes
@fix:
  uv run ruff check . --fix
  uv run black .
