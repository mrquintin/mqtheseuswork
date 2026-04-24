#!/bin/bash
# =============================================================
# CONTRADICTION GEOMETRY — Run All Experiments
# Tests how logical contradiction manifests as geometric
# structure in embedding space.
# =============================================================

cd "$(dirname "$0")"

echo "═══════════════════════════════════════════════════"
echo "  CONTRADICTION GEOMETRY"
echo "  7 experiments on the geometry of contradiction"
echo "═══════════════════════════════════════════════════"
echo ""

# Check for venv
if [ -d "../Reverse_Marxism/venv/bin" ]; then
  echo "  Using Reverse Marxism venv..."
  source ../Reverse_Marxism/venv/bin/activate
elif [ -d "venv/bin" ]; then
  source venv/bin/activate
else
  echo "  Creating virtual environment..."
  python3 -m venv venv
  source venv/bin/activate
fi

# Install dependencies
echo "  Installing dependencies..."
pip install -r requirements.txt --quiet 2>/dev/null

# Run
echo ""
echo "  Starting experiments (this takes ~15-20 minutes on CPU)..."
echo ""
python3 experiments.py

echo ""
echo "═══════════════════════════════════════════════════"
echo "  DONE!"
echo ""
echo "  Figures: $(pwd)/figures/"
echo "  Results: $(pwd)/results/"
echo "═══════════════════════════════════════════════════"
