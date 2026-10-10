import ast
import json
import os
import string
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from cardvault.i18n import LANGUAGES, detect_language, set_language, tr
from cardvault.catalogs import CATALOGS
from cardvault.engine import Engine
from cardvault.gui import MainWindow, SettingsDialog, OptionsDialog, configure_application


class LanguageTests(unittest.TestCase):
    def tearDown(self):
        set_language('zh_CN')

    def test_timezone_mapping(self):
        for zone, expected in [('Asia/Shanghai','zh_CN'),('China Standard Time','zh_CN'),('Asia/Taipei','zh_TW'),('Asia/Hong_Kong','zh_TW'),('Asia/Macau','zh_TW'),('Asia/Tokyo','ja'),('Tokyo Standard Time','ja'),('America/New_York','en'),('Asia/Singapore','en'),('UTC','en'),('unknown','en')]:
            self.assertEqual(detect_language(zone), expected)

    def test_catalog_coverage_and_placeholders(self):
        root = Path(__file__).resolve().parents[1]
        keys = set()
        for name in ('gui','engine'):
            tree = ast.parse((root / 'cardvault' / (name + '.py')).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr' and node.args and isinstance(node.args[0], ast.Constant):
                    keys.add(node.args[0].value)
        formatter = string.Formatter()
        for locale, catalog in CATALOGS.items():
            for source in keys - {'，','；'}:
                self.assertIn(source, catalog, (locale, source))
                expected = {field for _, field, _, _ in formatter.parse(source) if field}
                actual = {field for _, field, _, _ in formatter.parse(catalog[source]) if field}
                self.assertEqual(actual, expected, (locale, source))
        set_language('ja')
        self.assertEqual(tr('设置'), '設定')
        set_language('en')
        self.assertEqual(tr('设置'), 'Settings')

    def test_first_start_and_saved_override_with_render(self):
        app = QApplication.instance() or QApplication([])
        configure_application(app)
        root = Path(__file__).resolve().parents[1]
        (root / 'artifacts').mkdir(exist_ok=True)
        for locale in LANGUAGES:
            with self.subTest(locale=locale), tempfile.TemporaryDirectory() as folder:
                engine = Engine(Path(folder))
                with patch('cardvault.gui.detect_language', return_value=locale) as detector:
                    window = MainWindow(engine, start_devices=False)
                    detector.assert_called_once()
                preferences = json.loads(window.preferences_path.read_text(encoding='utf-8'))
                self.assertEqual(preferences['language'], locale)
                window.show(); app.processEvents()
                window.grab().save(str(root / 'artifacts' / f'locale-{locale}.png'))
                options = OptionsDialog(window.options, window)
                options.show(); app.processEvents()
                options.grab().save(str(root / 'artifacts' / f'options-{locale}.png'))
                options.close()
                def save(dialog):
                    dialog.language.setCurrentIndex(dialog.language.findData('ja'))
                    dialog.workers.setValue(6)
                    return QDialog.DialogCode.Accepted
                with patch.object(SettingsDialog, 'exec', save):
                    window.settings()
                saved = json.loads(window.preferences_path.read_text(encoding='utf-8'))
                self.assertEqual(saved['language'], 'ja')
                self.assertEqual(saved['options']['workers'], 6)
                window.ready_to_close = True; window.close()
                with patch('cardvault.gui.detect_language', side_effect=AssertionError('Saved choice must win')):
                    reopened = MainWindow(engine, start_devices=False)
                self.assertEqual(reopened.start_button.text(), 'バックアップ開始  →')
                settings = SettingsDialog(reopened)
                self.assertEqual(settings.workers.value(), 6)
                settings.show(); app.processEvents()
                settings.grab().save(str(root / 'artifacts' / 'settings-ja.png'))
                settings.close()
                reopened.ready_to_close = True; reopened.close()
                engine.shutdown()
