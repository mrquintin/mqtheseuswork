"""
Configuration for the Contradiction Geometry experiment.

This experiment investigates how contradictory claims manifest geometrically
in vector embedding spaces — building on findings from both the Reverse Marxism
experiment (Householder reflections, ideological axes) and the Embedding Geometry
Conjecture (difference vector sparsity, contradiction direction).
"""

import os
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"
FIGURES_DIR = PROJECT_ROOT / "figures"

for d in [DATA_DIR, RESULTS_DIR, FIGURES_DIR]:
    d.mkdir(exist_ok=True)

# ─── Model ────────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-mpnet-base-v2"  # 768-dim, same as Reverse Marxism
EMBEDDING_DIM = 768

# ─── Experiment Parameters ────────────────────────────────────────────────────

# Experiment 1: The Cosine Paradox
# How similar are contradictions vs. entailments vs. unrelateds?
EXP1_NUM_PAIRS = 100  # pairs per relationship type

# Experiment 2: Difference Vector Anatomy
# Sparsity, direction, and concentration of the contradiction signal
EXP2_HOYER_THRESHOLD = 0.35  # above this = likely contradiction
EXP2_PCA_VARIANCE_TARGET = 0.90  # how many PCA dims for 90% variance

# Experiment 3: The Negation Blindspot
# How embedding models handle "not X" vs actual opposite of X
EXP3_NEGATION_STYLES = [
    "simple",      # "X is Y" → "X is not Y"
    "antonym",     # "X is hot" → "X is cold"
    "indirect",    # "X is hot" → "X lacks warmth"
    "scalar",      # "X is huge" → "X is tiny"
    "modal",       # "X must happen" → "X cannot happen"
    "quantifier",  # "All X are Y" → "No X are Y"
]

# Experiment 4: Contradiction Subspace Discovery
# Learn the low-dimensional subspace where contradiction lives
EXP4_SUBSPACE_DIMS = [1, 2, 3, 5, 10, 20, 50]  # test these dimensionalities
EXP4_CROSS_VAL_FOLDS = 5

# Experiment 5: Householder Contradiction Reflection
# Can we CONSTRUCT a contradiction by reflecting through the contradiction subspace?
# (Bridges directly to Reverse Marxism methodology)
EXP5_ALPHA_VALUES = [1.0, 2.0, 3.0, 5.0, 8.0]
EXP5_NUM_TEST_SENTENCES = 200

# Experiment 6: Cross-Domain Generalization
# Does the contradiction geometry transfer across:
# a) General → Political (Marx/Smith corpus)
# b) General → Philosophical (abstract claims)
# c) General → Empirical (scientific claims)
EXP6_DOMAINS = ["general", "political", "philosophical", "empirical"]

# Experiment 7: Topology of Opposition
# Map the full landscape: synonymy, antonymy, contradiction, entailment, neutrality
# as geometric configurations
EXP7_RELATIONSHIP_TYPES = [
    "synonym",        # "happy" / "joyful"
    "antonym",        # "happy" / "sad"
    "contradiction",  # "the door is open" / "the door is closed"
    "entailment",     # "the cat is black" / "the cat has a color"
    "neutral",        # "the cat is black" / "the car is fast"
    "negation",       # "it is raining" / "it is not raining"
    "scalar_opposite", # "boiling" / "freezing"
    "pragmatic_contradiction",  # "he's a bachelor" / "his wife called"
]

# Experiment 8: The Contradiction Manifold
# Is contradiction a line (linear) or a surface (nonlinear)?
# Compare linear probe vs MLP to test for curvature
EXP8_MLP_HIDDEN = [64, 32]   # hidden layer sizes for the nonlinear probe
EXP8_MLP_EPOCHS = 200
EXP8_CROSS_VAL_FOLDS = 5

# Experiment 9: Contradiction Intensity
# Does |d · c_hat| correlate with how contradictory humans would rate a pair?
# Uses a graded set of contradictions from "mild disagreement" to "total opposition"
EXP9_INTENSITY_LEVELS = 5  # number of intensity bins
