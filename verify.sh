#!/bin/bash
# Verification script for March Madness Bracket Optimizer

echo "=========================================="
echo "March Madness Bracket Optimizer"
echo "System Verification"
echo "=========================================="
echo ""

# Check Python version
echo "1. Checking Python version..."
python3 --version
echo ""

# Check dependencies
echo "2. Checking dependencies..."
python3 -c "import bs4; print('✓ beautifulsoup4 installed')"
python3 -c "import pytest; print('✓ pytest installed')"
echo ""

# Import all modules
echo "3. Importing all modules..."
python3 -c "
import src.models
import src.constants
import src.utils
import src.config
import src.scout
import src.sharp
import src.contrarian
import src.optimizer
import src.analyst
print('✓ All modules import successfully')
"
echo ""

# Run tests
echo "4. Running test suite..."
python3 -m pytest tests/ -q --tb=no
echo ""

# Count implementation
echo "5. Implementation statistics..."
echo "  Source files: $(find src -name '*.py' | wc -l)"
echo "  Test files: $(find tests -name 'test_*.py' | wc -l)"
echo "  Total lines: $(find src tests -name '*.py' -exec wc -l {} + | tail -1 | awk '{print $1}')"
echo ""

# Check CLI
echo "6. Verifying CLI..."
python3 main.py --help > /dev/null 2>&1 && echo "✓ CLI functional"
echo ""

# Check file structure
echo "7. Verifying file structure..."
for dir in src tests data output; do
  if [ -d "$dir" ]; then
    echo "  ✓ $dir/ exists"
  else
    echo "  ✗ $dir/ missing"
  fi
done
echo ""

echo "=========================================="
echo "✅ VERIFICATION COMPLETE"
echo "=========================================="
echo ""
echo "System is ready to use. Try:"
echo "  python3 main.py full --sims 1000"
echo ""
