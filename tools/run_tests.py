"""Run unittest with actionable GitHub annotations when CI cannot open a GUI."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def annotate(title, message):
    text = message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f'::error title={title}::{text}', flush=True)


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        try:
            from native import gui  # CI installs the GUI; silently skipped UI tests are not success.
        except (ImportError, OSError) as error:
            annotate('GUI dependency failure', str(error))
            raise SystemExit(1)
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        for test, failure in result.failures+result.errors:
            annotate(str(test), failure)
    raise SystemExit(0 if result.wasSuccessful() else 1)
