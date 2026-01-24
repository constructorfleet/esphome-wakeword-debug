"""Test configuration file."""
import sys
from pathlib import Path

# Ensure package is importable - add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
