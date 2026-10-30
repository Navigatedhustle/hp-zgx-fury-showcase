import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# isolated data dir + offline model for every test run
_tmp = tempfile.mkdtemp(prefix="deckbuilder-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["LLM_MOCK"] = "true"
os.environ["MOCK_DELAY_S"] = "0"
os.environ["RENDERER"] = "none"

DECKS = ROOT / "evals" / "decks"
