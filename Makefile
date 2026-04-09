.PHONY: check fmt lint test

check: fmt lint test

fmt:
	black .

lint:
	ruff check .

test:
	pytest
