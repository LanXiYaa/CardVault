import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent if ROOT.name.lower() == 'push' else ROOT
OUTPUT = Path(os.environ.get('CARDVAULT_OUTPUT_DIR', WORKSPACE / 'release')).resolve()
PUSH = (WORKSPACE / 'push').resolve()
if OUTPUT == PUSH or PUSH in OUTPUT.parents:
    raise ValueError('Release output must be outside push.')
BUILD = WORKSPACE / 'build/release'
