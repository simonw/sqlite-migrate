# Run tests and linters
@default: test lint

# Install dependencies and test dependencies
@init:
  pipenv run pip install -e '.[test]'

# Run pytest with supplied options
@test *options:
  pipenv run pytest {{options}}

# Run linters
@lint:
  echo "Linters..."
  echo "  Black"
  pipenv run black . --check
  echo "  mypy"
  pipenv run mypy sqlite_migrate tests
  echo "  ruff"
  pipenv run ruff .


# Apply Black
@black:
  pipenv run black .

# Run automatic fixes
@fix:
  pipenv run ruff . --fix
  pipenv run black .
