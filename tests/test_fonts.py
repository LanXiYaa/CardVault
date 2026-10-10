import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import unittest
from PySide6.QtGui import QFontDatabase, QFontInfo, QRawFont
from PySide6.QtWidgets import QApplication
from cardvault.gui import configure_application, DEFAULT_FONT


class BundledFontTests(unittest.TestCase):
    def test_default_font_resolves_and_covers_interface_languages(self):
        app = QApplication.instance() or QApplication([])
        configure_application(app)
        self.assertEqual(QFontInfo(app.font()).family(), DEFAULT_FONT)
        self.assertIn('Regular', QFontDatabase.styles(DEFAULT_FONT))
        self.assertIn('Bold', QFontDatabase.styles(DEFAULT_FONT))
        font = QRawFont.fromFont(app.font())
        for char in '备份校验備份検証日本語あいうアイウBackup':
            self.assertTrue(font.supportsCharacter(ord(char)), char)
        self.assertIn("font-family:'Source Han Sans SC'", app.styleSheet())

    def test_reapplying_theme_does_not_register_fonts_again(self):
        from unittest.mock import patch
        app = QApplication.instance() or QApplication([])
        configure_application(app)
        with patch.object(QFontDatabase, 'addApplicationFont', side_effect=AssertionError('Duplicate registration')):
            configure_application(app, {'color': '#2563eb', 'font': DEFAULT_FONT})
        self.assertIn('#2563eb', app.styleSheet())
        configure_application(app)
