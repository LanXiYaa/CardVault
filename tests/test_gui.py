"""Offscreen Qt tests: no physical devices or existing user tasks are touched."""
import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
HAS_QT = importlib.util.find_spec('PySide6') is not None
if HAS_QT:
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox
    from cardvault.gui import MainWindow, OptionsDialog, DetailsDialog, HistoryDialog, configure_application, DEFAULTS
    from cardvault.engine import Engine


@unittest.skipUnless(HAS_QT, 'Run with .venv/Scripts/python.exe to test PySide6')
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        configure_application(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.engine = Engine(self.root / 'state')
        self.window = MainWindow(self.engine, start_devices=False)
        self.window.options['notify'] = False
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.engine.shutdown()
        self.window.ready_to_close = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def wait_done(self):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.app.processEvents()
            jobs = self.engine.list_jobs()
            if jobs and jobs[0]['status'] in {'completed', 'failed', 'partial'}:
                self.window.refresh()
                return jobs[0]
            time.sleep(.01)
        self.fail('Desktop backup did not complete')

    def test_start_button_copies_and_checks_two_targets(self):
        source = self.root / 'card'
        source.mkdir()
        (source / 'photo.JPG').write_bytes(b'real file backup test' * 1024)
        self.window.source.edit.setText(str(source))
        self.window.target.edit.setText(str(self.root / 'A'))
        self.window.options.update(dual=True, secondary=str(self.root / 'B'))
        self.window.start_button.click()
        job = self.wait_done()
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual(self.window.progress.value(), 1000)
        self.assertEqual(self.window.status_badge.text(), '校验完成')
        self.assertEqual((self.root / 'B/photo.JPG').read_bytes(), (source / 'photo.JPG').read_bytes())

    def test_main_window_is_simple_and_advanced_options_are_secondary(self):
        self.assertTrue(self.window.source.isVisible())
        self.assertTrue(self.window.target.isVisible())
        self.assertFalse(self.window.resume_button.isVisible())
        options = OptionsDialog(DEFAULTS, self.window)
        self.assertFalse(options.isVisible())
        self.assertEqual(options.filter.currentData(), 'all')
        titles = [action.text() for action in self.window.more.menu().actions()]
        self.assertIn('多卡批量备份…', titles)
        self.assertIn('存储设备与安全弹出…', titles)
        options.deleteLater()

    def test_options_save_custom_and_dual_backup(self):
        dialog = OptionsDialog(DEFAULTS, self.window)
        dialog.filter.setCurrentIndex(dialog.filter.findData('custom'))
        dialog.extensions.setText('jpg, arw')
        dialog.dual.setChecked(True)
        dialog.secondary.edit.setText(str(self.root / 'B'))
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(dialog.options['dual'])
        self.assertEqual(dialog.options['filter'], 'custom')
        dialog.deleteLater()

    def test_native_report_save_dialog_exports_csv(self):
        source = self.root / 'card'
        source.mkdir()
        (source / 'photo.JPG').write_bytes(b'photo')
        self.window.source.edit.setText(str(source))
        self.window.target.edit.setText(str(self.root / 'A'))
        self.window.start_button.click()
        job = self.wait_done()
        output = self.root / 'report.csv'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(output), 'CSV')), patch.object(QMessageBox, 'information'):
            self.window.export_report(job['id'], 'csv')
        self.assertIn('photo.JPG', output.read_text(encoding='utf-8-sig'))
        details = DetailsDialog(self.window, job['id'])
        self.assertIn('校验完成', details.title.text())
        details.deleteLater()
        history = HistoryDialog(self.window)
        self.assertEqual(history.table.rowCount(), 1)
        history.deleteLater()

    def test_minimum_window_does_not_clip_primary_controls(self):
        self.window.resize(710, 650)
        self.app.processEvents()
        corner = self.window.start_button.mapTo(self.window.centralWidget(), self.window.start_button.rect().bottomRight())
        self.assertTrue(self.window.centralWidget().rect().contains(corner))
        self.assertTrue(self.window.source.rect().contains(self.window.source.edit.geometry()))
        self.assertTrue(self.window.target.rect().contains(self.window.target.edit.geometry()))


if __name__ == '__main__':
    unittest.main()
