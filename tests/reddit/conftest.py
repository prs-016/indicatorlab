"""Send log files written during tests to a temp folder, not logs/reddit/."""
import tempfile
from pathlib import Path

from src.reddit import settings

settings.LOGS = Path(tempfile.mkdtemp(prefix="reddit-test-logs-"))
