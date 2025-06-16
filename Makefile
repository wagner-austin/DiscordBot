# Makefile — Poetry-aware workflow for Discord Bot project
# Run `make help` to see available targets.

.PHONY: install shell lint format test clean run build help

# ---------------------------------------------------------------------------
# Tooling helpers
# ---------------------------------------------------------------------------
POETRY  := poetry             # centralised Poetry command (override with POETRY=…)
RUN     := $(POETRY) run      # prefix to execute inside Poetry venv
PYTHON  := $(RUN) python
PIP     := $(RUN) pip
RUFF    := $(RUN) ruff
MYPY    := $(RUN) mypy
PYTEST  := $(RUN) pytest

# ---------------------------------------------------------------------------
# Meta / docs
# ---------------------------------------------------------------------------
help:               ## show this help message
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	 awk 'BEGIN {FS = ":.*?##"}; {printf " \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Environment / dependencies
# ---------------------------------------------------------------------------
install:            ## resolve & install all dependencies (incl. dev)
	$(POETRY) lock
	$(POETRY) install --with dev --extras dev

shell:              ## activate Poetry shell (interactive)
	$(POETRY) shell

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------
lint: install               ## ruff fix + ruff format + mypy strict type-check
	$(PIP) install --quiet --disable-pip-version-check types-requests types-PyYAML
	$(RUFF) check --fix .
	$(RUFF) format .
	$(MYPY) --strict .

format: install             ## auto-format code base (ruff + black)
	$(RUFF) format .

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test: install                ## run pytest suite
	$(PYTEST)

# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------
run: install                ## launch the Discord bot (sync with pyproject script)
	$(PYTHON) -m bot.core

build: install              ## build wheel / sdist
	$(POETRY) build

clean: install              ## remove Python / tool caches
	@$(RUN) python - <<-'PY'
	import pathlib, shutil, sys
	root = pathlib.Path('.')
	patterns = ["__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "*.egg-info"]
	for pat in patterns:
		for p in root.rglob(pat):
			try:
				shutil.rmtree(p) if p.is_dir() else p.unlink()
			except Exception as e:
				print("cannot delete", p, "->", e, file=sys.stderr)
	PY

# Use savecode to save files
savecode:
	savecode . --skip tests --ext toml py

# Use savecode to save files
savecode-test:
	savecode . --ext toml py