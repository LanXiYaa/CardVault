import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtGui import QColor,QFont
from PySide6.QtWidgets import QApplication,QDialog
from cardvault.engine import Engine
from cardvault.gui import MainWindow,SettingsDialog,DetailsDialog,configure_application
from cardvault.i18n import set_language

class NewSettingsTests(unittest.TestCase):
    def test_preferences_apply_immediately_and_reports_have_counts(self):
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);engine=Engine(root/'state')
            with patch('cardvault.gui.detect_language',return_value='zh_CN'):
                window=MainWindow(engine,start_devices=False)
            def choose(dialog):
                dialog.verification.setCurrentIndex(dialog.verification.findData('batch'))
                dialog.color=QColor('#2563eb')
                dialog.font_choice.setCurrentFont(QFont('Segoe UI'))
                return QDialog.DialogCode.Accepted
            with patch.object(SettingsDialog,'exec',choose):window.settings()
            saved=json.loads(window.preferences_path.read_text(encoding='utf-8'))
            self.assertEqual(saved['options']['verification'],'batch')
            self.assertEqual(saved['appearance']['color'],'#2563eb')
            self.assertIn('#2563eb',app.styleSheet())
            source=root/'card';source.mkdir();(source/'photo.jpg').write_bytes(b'photo')
            job=engine.create({'source':str(source),'targets':[str(root/'out')],'verification':'batch'},start=False)
            engine.run(engine.jobs[job['id']]);window.refresh();window.show();app.processEvents()
            details=DetailsDialog(window,job['id']);details.show();app.processEvents()
            self.assertEqual(details.result_counts.values['success'].text(),'1')
            self.assertEqual(details.result_counts.values['failed'].text(),'0')
            artifact=Path(__file__).resolve().parents[1]/'artifacts'
            artifact.mkdir(exist_ok=True)
            details.grab().save(str(artifact/'2.2-report.png'))
            window.grab().save(str(artifact/'2.2-main-blue.png'))
            settings=SettingsDialog(window);settings.show();app.processEvents()
            settings.grab().save(str(artifact/'2.2-settings.png'))
            from PySide6.QtWidgets import QTabWidget
            settings.findChild(QTabWidget).setCurrentIndex(2);app.processEvents()
            settings.grab().save(str(artifact/'2.2-update-page.png'))
            settings.close();details.close();window.ready_to_close=True;window.close();engine.shutdown()
        configure_application(app);set_language('zh_CN')
