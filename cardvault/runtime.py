"""Separate immutable bundle resources from persistent user data."""
import os
import sys
from pathlib import Path


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))


def default_data_dir():
    if getattr(sys, 'frozen', False):
        local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
        return local / 'CardVault'
    return resource_root() / 'data'
