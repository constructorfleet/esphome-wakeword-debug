"""Test configuration and fixtures."""
import sys
from pathlib import Path

# Add ingest_service to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "ingest_service"))
