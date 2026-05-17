import os
import sys

# Make the repo root importable so `protocol.*` and `shared.*` resolve when
# pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
