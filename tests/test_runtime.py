import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from cardvault.runtime import default_data_dir, resource_root


class RuntimePathsTests(unittest.TestCase):
    def test_source_data_remains_in_project(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(default_data_dir(), resource_root() / 'data')

    def test_frozen_data_does_not_use_temporary_bundle(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', 'C:/temporary/unpack', create=True), patch.dict(os.environ, {'LOCALAPPDATA': 'C:/user/local'}):
            self.assertEqual(default_data_dir(), Path('C:/user/local/CardVault'))
            self.assertEqual(resource_root(), Path('C:/temporary/unpack'))
