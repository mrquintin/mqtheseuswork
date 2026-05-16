.PHONY: install lint typecheck test all ready-to-sync sync

PYTHON ?= python3
PIP = $(PYTHON) -m pip

# Installs dev tools, editable local packages (see pyproject.toml), and Noosphere
# runtime deps so pytest can import the stack.
install:
	$(PIP) install -U pip setuptools wheel
	$(PIP) install -U -e ".[dev]"
	$(PIP) install -U -r noosphere/requirements.txt

lint:
	ruff check noosphere dialectic
	black --check noosphere dialectic

typecheck:
	mypy noosphere dialectic

test:
	pytest

all: lint typecheck test

# Daily-driver gate: runs every Round 19b risk-class check and emits a
# single pass/fail verdict. Pass GATE_ARGS to forward flags, e.g.
# `make ready-to-sync GATE_ARGS="--from 3"`.
ready-to-sync:
	./scripts/ready-to-sync.sh $(GATE_ARGS)

# Daily-driver sync: invokes the gate first; refuses to push on failure.
# `make sync SYNC_ARGS="--ready-to-sync-only"` runs the gate without pushing.
sync:
	./scripts/sync-to-github.sh $(SYNC_ARGS)
