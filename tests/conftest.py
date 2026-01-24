"""Test configuration file."""
import sys
from pathlib import Path

# Ensure package is importable
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "ingest_service"))
