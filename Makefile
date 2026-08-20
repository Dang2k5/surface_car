.PHONY: run test lint format typecheck check clean

run:
	uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check agent/ backend/ tests/

format:
	ruff format agent/ backend/ tests/

typecheck:
	mypy agent/ backend/

check: lint format test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
