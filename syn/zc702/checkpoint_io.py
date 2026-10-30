"""Replace checkpoints atomically, tolerating short Windows reader/scanner locks."""
import json
import os
from pathlib import Path
import time


def write_checkpoint(path, value, *, attempts=40, delay=.05):
    path = Path(path)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        for attempt in range(attempts):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(delay)
    finally:
        temporary.unlink(missing_ok=True)
