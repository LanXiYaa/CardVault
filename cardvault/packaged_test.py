"""Opt-in release diagnostic; only writes to its requested result directory."""
import hashlib
import json
import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path


def run(result_file):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    result_file = Path(result_file).resolve()
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False)), 'executable': sys.executable, 'version': __import__('cardvault.version', fromlist=['VERSION']).VERSION}
    engine = window = None
    try:
        from PySide6 import __version__
        from PySide6.QtWidgets import QApplication
        from PySide6.QtNetwork import QLocalServer
        from .engine import Engine
        from .gui import MainWindow, OptionsDialog, configure_application
        from .runtime import resource_root, default_data_dir
        from .i18n import LANGUAGES, set_language, tr, install_qt_translation
        app = QApplication.instance() or QApplication([])
        configure_application(app)
        for locale, expected in [('zh_CN', '设置'), ('zh_TW', '設定'), ('en', 'Settings'), ('ja', '設定')]:
            set_language(locale)
            assert tr('设置') == expected
            install_qt_translation()
            if locale != 'en':
                assert not app._cardvault_translator.isEmpty(), locale
        result['languages'] = list(LANGUAGES)
        result['pyside6'] = __version__
        result['python'] = sys.version
        result['data_dir'] = str(default_data_dir())
        result['bundle_root'] = str(resource_root())
        result['module_search_paths'] = list(sys.path)
        assert (resource_root() / 'assets/logo.svg').is_file()
        assert (resource_root() / 'assets/qt-down.svg').is_file()
        with tempfile.TemporaryDirectory(prefix='release-check-', dir=result_file.parent) as folder:
            root = Path(folder)
            source = root / 'camera'
            source.mkdir()
            payload = b'CardVault standalone integrity test\x00' * 65536
            (source / 'photo.bin').write_bytes(payload)
            (source / 'empty.txt').write_bytes(b'')
            (source / 'video.bin').write_bytes(payload[::-1])
            engine = Engine(root / 'state')
            window = MainWindow(engine, start_devices=False)
            window.options.update(dual=True, secondary=str(root / 'copy-b'), notify=False, verification='batch')
            window.source.edit.setText(str(source))
            window.target.edit.setText(str(root / 'copy-a'))
            window.show()
            app.processEvents()
            assert window.start_jobs([str(source)])
            # The normal GUI starts the normal worker; wait only in this test process.
            engine.pool.shutdown(wait=True)
            app.processEvents()
            window.refresh()
            job = engine.list_jobs()[0]
            assert job['status'] == 'completed', job['message']
            for target in job['targets']:
                assert hashlib.sha256((Path(target) / 'photo.bin').read_bytes()).digest() == hashlib.sha256(payload).digest()
            assert (source / 'photo.bin').read_bytes() == payload
            assert window.progress.value() == 1000
            window.grab().save(str(result_file.with_suffix('.png')))
            options = OptionsDialog(window.options, window)
            assert options.dual.isChecked()
            options.close()
            report = engine.report(job['id'], 'csv')
            assert report.startswith(b'\xef\xbb\xbf')
            for target in job['targets']:
                assert (Path(target) / 'empty.txt').read_bytes() == b''
                assert hashlib.sha256((Path(target) / 'video.bin').read_bytes()).digest() == hashlib.sha256(payload[::-1]).digest()
            result.update(copied_files=job['copied'], verified_copies=6, workers=job['workers'], gui_progress=window.progress.value(), csv_bytes=len(report))
            window.ready_to_close = True
            window.close()
            engine.shutdown()
            window = engine = None
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if engine:
            engine.shutdown()
        if window:
            window.ready_to_close = True
            window.close()
        result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1

