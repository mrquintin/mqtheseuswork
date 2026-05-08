# Replication harness — one command per headline empirical claim.
#
# A researcher who has cloned the repo can run any single target
# without further configuration. The targets that need API keys read
# them from environment variables documented in `replication/README.md`;
# they do not error when keys are missing — they skip the affected
# model with an explicit log line.
#
# Every target writes a per-run directory under `replication/runs/`
# containing:
#   - `replication_envelope.json`  reproducibility record
#   - `metrics_summary.json`       normalised numeric summary
#   - per-runner result/metric JSON
#
# `make verify PRIOR_RUN=<dir>` compares two run directories and
# reports whether their numbers agree within the firm's declared
# tolerance.

.PHONY: help all qh-benchmark cross-model ablation verify install test smoke

# --- Configuration ---------------------------------------------------------

PYTHON ?= python3
REPO_ROOT := $(shell cd .. && pwd)
RUN_ROOT ?= $(REPO_ROOT)/replication/runs
DATASET ?= $(REPO_ROOT)/benchmarks/quintin_hypothesis/v1/dataset.jsonl
SEED ?= 0
DETERMINISTIC ?= 1
EXTRA_ARGS ?=

# `--deterministic` is opt-in via DETERMINISTIC=0 if you specifically
# want stochastic runners (e.g. to estimate run-to-run variance).
ifeq ($(DETERMINISTIC),1)
DET_FLAG := --deterministic
else
DET_FLAG :=
endif

DRIVER := $(PYTHON) $(REPO_ROOT)/replication/run.py
VERIFY := $(PYTHON) -m replication.lib.verify

# --- Help ------------------------------------------------------------------

help:
	@echo "Replication harness targets:"
	@echo "  make qh-benchmark    QH benchmark (prompt 08): random + cosine + contradiction_geometry"
	@echo "  make cross-model     Cross-model QH study (prompt 09); skips models without API keys"
	@echo "  make ablation        Householder ablation (prompt 10)"
	@echo "  make all             qh-benchmark, cross-model, ablation in sequence"
	@echo "  make verify PRIOR_RUN=<dir> [CURRENT_RUN=<dir>]"
	@echo "                       Compare two run directories. CURRENT_RUN defaults to the newest run."
	@echo "  make smoke           Tiny shard run, used by CI to catch silent breakage"
	@echo ""
	@echo "Knobs:"
	@echo "  DETERMINISTIC=1|0    (default 1) sets fixed seeds and single-thread BLAS"
	@echo "  SEED=N               (default 0)"
	@echo "  DATASET=<path>       override the dataset shard"
	@echo "  RUN_ROOT=<path>      override where run dirs are written"
	@echo "  EXTRA_ARGS=...       passed through to the driver"

# --- Targets ---------------------------------------------------------------

install:
	cd $(REPO_ROOT) && $(PYTHON) -m pip install -U pip
	cd $(REPO_ROOT) && $(PYTHON) -m pip install -U -e ".[dev]"
	cd $(REPO_ROOT) && $(PYTHON) -m pip install -U -r noosphere/requirements.txt

qh-benchmark:
	@mkdir -p $(RUN_ROOT)
	cd $(REPO_ROOT) && $(DRIVER) qh-benchmark \
		--dataset $(DATASET) \
		--seed $(SEED) \
		--run-root $(RUN_ROOT) \
		$(DET_FLAG) $(EXTRA_ARGS)

cross-model:
	@mkdir -p $(RUN_ROOT)
	cd $(REPO_ROOT) && $(DRIVER) cross-model \
		--dataset $(DATASET) \
		--seed $(SEED) \
		--run-root $(RUN_ROOT) \
		$(DET_FLAG) $(EXTRA_ARGS)

ablation:
	@mkdir -p $(RUN_ROOT)
	cd $(REPO_ROOT) && $(DRIVER) ablation \
		--dataset $(DATASET) \
		--seed $(SEED) \
		--run-root $(RUN_ROOT) \
		$(DET_FLAG) $(EXTRA_ARGS)

all: qh-benchmark cross-model ablation
	@echo ""
	@echo "[replication] all three targets complete. Run dirs in $(RUN_ROOT):"
	@ls -1t $(RUN_ROOT) | head -3

# Tiny shard for CI: cap cross-model items, run the lightest QH runner
# only. The aim is "did anything import-break overnight?", not a full
# replication.
SMOKE_BUDGET ?= 50
smoke:
	@mkdir -p $(RUN_ROOT)
	cd $(REPO_ROOT) && $(DRIVER) qh-benchmark \
		--dataset $(DATASET) \
		--seed 0 \
		--run-root $(RUN_ROOT) \
		--runners cosine contradiction_geometry \
		--deterministic
	cd $(REPO_ROOT) && THESEUS_CROSS_MODEL_BUDGET=$(SMOKE_BUDGET) $(DRIVER) cross-model \
		--dataset $(DATASET) \
		--seed 0 \
		--run-root $(RUN_ROOT) \
		--budget $(SMOKE_BUDGET) \
		--deterministic

# Verify defaults CURRENT_RUN to the most recent run dir if not given.
# That makes `make verify PRIOR_RUN=<some old dir>` a one-liner.
verify:
ifndef PRIOR_RUN
	@echo "usage: make verify PRIOR_RUN=<dir> [CURRENT_RUN=<dir>]" >&2; exit 2
endif
	@if [ -z "$(CURRENT_RUN)" ]; then \
		current=$$(ls -1td $(RUN_ROOT)/*/ 2>/dev/null | head -1); \
		if [ -z "$$current" ]; then \
			echo "no current run dir found under $(RUN_ROOT); pass CURRENT_RUN=<dir>" >&2; exit 2; \
		fi; \
		echo "[verify] PRIOR=$(PRIOR_RUN) CURRENT=$$current"; \
		cd $(REPO_ROOT) && $(VERIFY) "$(PRIOR_RUN)" "$$current"; \
	else \
		echo "[verify] PRIOR=$(PRIOR_RUN) CURRENT=$(CURRENT_RUN)"; \
		cd $(REPO_ROOT) && $(VERIFY) "$(PRIOR_RUN)" "$(CURRENT_RUN)"; \
	fi

test:
	cd $(REPO_ROOT) && $(PYTHON) -m pytest replication/tests -q
