.PHONY: format format-check

format:
	ruff format .

format-check:
	ruff format --check .
