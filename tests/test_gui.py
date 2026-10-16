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
        (self.engine.state_dir / 'preferences.json').write_text('{"language":"zh_CN"}', encoding='utf-8')
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
        self.window.destinations.add_path(str(self.root / 'B'))
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

    def test_options_save_custom_filter(self):
        dialog = OptionsDialog(DEFAULTS, self.window)
        dialog.filter.setCurrentIndex(dialog.filter.findData('custom'))
        dialog.extensions.setText('jpg, arw')
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
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

    def test_preparation_remembers_destinations_without_starting_a_job(self):
        import json
        self.window.target.edit.setText(str(self.root / 'A'))
        self.window.destinations.add_path(str(self.root / 'B'))
        self.window.destinations.add_path(str(self.root / 'C'))
        self.window.hash_choice.setCurrentIndex(self.window.hash_choice.findData('md5'))
        self.window.verification_choice.setCurrentIndex(self.window.verification_choice.findData('batch'))
        saved = json.loads(self.window.preferences_path.read_text(encoding='utf-8'))
        self.assertEqual(saved['targets'], [str(self.root / p) for p in ('A', 'B', 'C')])
        self.assertEqual(saved['options']['hash_algorithm'], 'md5')
        reopened = MainWindow(self.engine, start_devices=False)
        try:
            self.assertEqual(reopened.destinations.paths(), saved['targets'])
            self.assertEqual(reopened.hash_choice.currentData(), 'md5')
            self.assertFalse(reopened.verify_progress.isHidden())
        finally:
            reopened.ready_to_close = True
            reopened.close()

    def test_forget_destinations_and_remove_rows(self):
        import json
        self.window.target.edit.setText(str(self.root / 'A'))
        field = self.window.destinations.add_path(str(self.root / 'B'))
        self.window.destinations.remove_path(field.parentWidget(), field)
        self.assertEqual(self.window.destinations.paths(), [str(self.root / 'A')])
        self.window.remember_targets.setChecked(False)
        saved = json.loads(self.window.preferences_path.read_text(encoding='utf-8'))
        self.assertEqual(saved['targets'], [])
        self.assertEqual(saved['target'], '')

    def test_batch_bars_show_independent_progress(self):
        source = self.root / 'card'
        source.mkdir()
        (source / 'photo.bin').write_bytes(b'photo')
        record = self.engine.create({'source': str(source), 'targets': [str(self.root / 'A')], 'verification': 'batch'}, start=False)
        job = self.engine.jobs[record['id']]
        job.update(status='verifying', total_bytes=100, done_bytes=100, progress_total=100, copy_progress=100, verify_progress=25)
        self.window.current_id = job['id']
        self.window.refresh()
        self.assertEqual(self.window.progress.value(), 1000)
        self.assertEqual(self.window.verify_progress.value(), 250)
        self.assertTrue(self.window.verify_progress.isVisible())
        self.assertIn('#508ba8', self.window.verify_progress.styleSheet())
        self.assertIn('#5d8a6d', self.window.progress.styleSheet())
        job['verification'] = 'per_file'
        self.window.refresh()
        self.assertTrue(self.window.verify_progress.isHidden())
        self.assertEqual(self.window.progress.value(), 625)

    def test_initial_window_uses_16_to_9_and_fits_available_screen(self):
        from cardvault.gui import initial_window_size
        for width, height in ((1920, 1080), (1366, 728), (800, 600)):
            w, h = initial_window_size(width, height)
            self.assertEqual(w * 9, h * 16)
            self.assertLessEqual(w, width)
            self.assertLessEqual(h + 80, height)
        self.assertEqual(self.window.width() * 9, self.window.height() * 16)

    def test_removable_device_eject_and_active_task_protection(self):
        from cardvault.gui import DevicesDialog
        device = dict(name='test', path=str(self.root), kind='removable', filesystem='test', size=100, free=50)
        with patch.object(self.window.bridge, 'submit') as submit:
            dialog = DevicesDialog(self.window)
            dialog.loaded([device], None)
            submit.reset_mock()
            with patch('cardvault.gui.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), patch('cardvault.gui.eject', return_value='ok') as eject:
                dialog.eject()
                work, callback = submit.call_args.args
                callback(work(), None)
                eject.assert_called_once_with(device['path'])
            submit.reset_mock()
            self.window.update_requested = True
            active = dict(status='pausing', source=str(self.root / 'card'), targets=[])
            with patch.object(self.engine, 'list_jobs', return_value=[active]), patch('cardvault.gui.QMessageBox.warning') as warning:
                dialog.eject()
                warning.assert_called_once()
                submit.assert_not_called()
            dialog.close()

    def test_accent_colors_are_substituted_once(self):
        from PySide6.QtGui import QColor
        for color in ('#2e523c', '#f5f7f2', '#e9f0df', '#809e68'):
            configure_application(self.app, {'color': color})
            style = self.app.styleSheet()
            self.assertIn('QPushButton#primary { background:' + color + ';', style)
            self.assertIn('QPushButton#primary:hover { background:' + QColor(color).darker(120).name(), style)
        configure_application(self.app)



if __name__ == '__main__':
    unittest.main()
