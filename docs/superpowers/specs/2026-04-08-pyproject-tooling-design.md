# pyproject.toml Tooling Configuration Design

**Date:** 2026-04-08
**Status:** Approved
**Task:** Set up pyproject.toml with ruff, black, and pytest configured

---

## Overview

The existing `pyproject.toml` has a minimal skeleton. This spec covers completing it to a production-ready state for a Python 3.11 application on Raspberry Pi OS Bookworm. No `[project]` section is needed — this is not a library. `requirements.txt` is out of scope.

---

## Final `pyproject.toml`

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "--tb=short"

[tool.black]
line-length = 100
target-version = ["py311"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["."]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["B011"]
```

---

## Changes from Current File

| Setting | Before | After | Reason |
|---------|--------|-------|--------|
| `pytest.testpaths` | absent | `["tests"]` | `pytest` alone finds tests without specifying a path |
| `pytest.addopts` | absent | `"--tb=short"` | Cleaner failure output |
| `black.target-version` | absent | `["py311"]` | Pin to Pi OS Bookworm Python version |
| `ruff.target-version` | absent | `"py311"` | Pin to Pi OS Bookworm Python version |
| `ruff.src` | absent | `["."]` | Allows isort (`I` rules) to correctly resolve project-root modules as first-party imports |
| `ruff.lint.select` | `["E","F","W","I"]` | adds `"B"`, `"UP"` | B = bugbear (catches real bugs); UP = pyupgrade (enforce py311 idioms) |
| `ruff.lint.per-file-ignores` | absent | `"tests/*" = ["B011"]` | B011 flags certain assert patterns common in test code |

---

## Rule Selection Rationale

- **E / F / W** — pycodestyle, pyflakes, warnings. Core correctness.
- **I** — isort import ordering. Consistent import style.
- **B** — flake8-bugbear. Catches common Python bugs and bad patterns. Safe for this codebase — no mutable defaults or other B-flagged patterns in existing code.
- **UP** — pyupgrade. Modernizes syntax to py311. No-op on current code (already using modern syntax), but enforces it going forward.

Rules intentionally excluded:
- **S** (bandit security) — too noisy for this stage
- **ANN** (type annotation enforcement) — conventions require type hints on signatures, but enforcing via linter is too strict during early development
- **D** (docstrings) — conventions require one-line docstrings on public functions, but linter enforcement adds noise to stubs before implementation

---

## Verification

After updating `pyproject.toml`, run the pre-merge gate:

```bash
ruff check . && black --check . && pytest
```

Expected: all pass. If B or UP introduce new findings on existing code, fix them before committing. Current codebase is expected to be clean — no existing patterns that trigger B or UP.

---

## Out of Scope

- `requirements.txt` — separate task; runtime dependencies not part of this tooling setup
- `[project]` section — not needed; this is a Pi application, not a library
- `Makefile` — separate task in the prep list
