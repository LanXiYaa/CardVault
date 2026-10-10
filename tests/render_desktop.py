"""Render actual Qt widgets offscreen for layout inspection, without user I/O."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtWidgets import QApplication
from cardvault.engine import Engine
from cardvault.gui import MainWindow, OptionsDialog, configure_application

app = QApplication([])
configure_application(app)
output = Path(__file__).resolve().parent.parent / 'artifacts'
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
    engine = Engine(Path(folder) / 'state')
    window = MainWindow(engine, start_devices=False)
    window.show()
    app.processEvents()
    window.grab().save(str(output / 'desktop-main.png'))
    dialog = OptionsDialog(window.options, window)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(output / 'desktop-options.png'))
    dialog.close()
    window.resize(710, 650)
    app.processEvents()
    window.grab().save(str(output / 'desktop-compact.png'))
    engine.shutdown()
    window.ready_to_close = True
    window.close()
print('Qt previews saved under artifacts')
