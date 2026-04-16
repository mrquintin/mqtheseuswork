.PHONY: install lint typecheck test all

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
