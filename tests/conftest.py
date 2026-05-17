import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Repo root: makes `protocol.*` and `shared.*` importable.
sys.path.insert(0, _ROOT)
# protocol/ dir: orchestrator.py is written to run as a script and does
# `from ledger import ...` / `from verification import ...`, so the package
# dir must be on the path for `import orchestrator` to resolve in tests.
sys.path.insert(0, os.path.join(_ROOT, "protocol"))
