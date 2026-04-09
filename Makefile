.PHONY: check fmt lint test

check: lint test

fmt:
	black .

lint:
	black --check .
	ruff check .

test:
	pytest
