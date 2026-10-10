"""Interface language selection; timezone is consulted only without a saved choice."""
import os
from .catalogs import CATALOGS

LANGUAGES = {'zh_CN': '简体中文', 'zh_TW': '繁體中文', 'en': 'English', 'ja': '日本語'}
_language = 'zh_CN'


def detect_language(zone=None):
    if zone is None:
        from PySide6.QtCore import QTimeZone
        zone = bytes(QTimeZone.systemTimeZoneId()).decode('utf-8', errors='replace')
    zone = zone.lower()
    if zone in {'asia/shanghai', 'asia/chongqing', 'asia/chungking', 'asia/harbin', 'asia/urumqi', 'china standard time', 'prc'}:
        return 'zh_CN'
    if zone in {'asia/taipei', 'asia/hong_kong', 'asia/macau', 'asia/macao', 'taipei standard time', 'hongkong', 'roc'}:
        return 'zh_TW'
    if zone in {'asia/tokyo', 'japan', 'tokyo standard time'}:
        return 'ja'
    return 'en'


def set_language(code):
    global _language
    _language = code if code in LANGUAGES else 'en'


def install_qt_translation():
    from PySide6.QtCore import QLibraryInfo, QTranslator
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    previous = getattr(app, '_cardvault_translator', None)
    if previous:
        app.removeTranslator(previous)
    translator = QTranslator(app)
    translator.load('qtbase_' + _language, QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(translator)
    app._cardvault_translator = translator


def tr(source, **values):
    translated = CATALOGS.get(_language, {}).get(source, source)
    return translated.format(**values) if values else translated


def translate_text(text):
    # Historical messages remain verbatim unless they are a known static label.
    return tr(text)
