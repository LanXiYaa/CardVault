from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon, QColor
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QSpinBox, QStatusBar, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget, QAbstractItemView, QColorDialog, QFontComboBox
from .engine import Engine, atomic_json, clean_name, under
from .instance import InstanceLock
from .system import drives, eject
from .runtime import resource_root, default_data_dir
from .version import VERSION
from .updater import stage_package, launch_update
from .i18n import tr, translate_text, set_language, detect_language, LANGUAGES, install_qt_translation
ROOT = resource_root()
ACTIVE = {'queued', 'checking', 'scanning', 'copying', 'verifying', 'pausing'}
RECOVERABLE = {'paused', 'partial', 'failed'}
STATUS = {'queued': '排队中', 'checking': '检查目标', 'scanning': '扫描文件', 'copying': '正在拷贝', 'verifying': '正在校验', 'pausing': '保存进度', 'paused': '已暂停', 'failed': '需要处理', 'partial': '部分失败', 'completed': '校验完成'}
DEFAULTS = dict(filter='all', extensions='', organize='original', duplicate='rename', project='', rename=False, retries=2, dual=False, secondary='', sound=False, notify=True, workers=3, verification='per_file')
DEFAULT_FONT = 'Source Han Sans SC'
STYLE = "\nQWidget { color:#293e34; font-family:'Source Han Sans SC'; font-size:13px; }\nQMainWindow,QDialog { background:#f5f7f2; }\nQLabel { background:transparent; }\nQLabel#brand { font-size:23px; font-weight:700; }\nQLabel#title { font-size:26px; font-weight:600; }\nQLabel#muted,QLabel#subtle { color:#7f8e79; }\nQLabel#subtle { font-size:11px; }\nQLabel#section { font-size:15px; font-weight:600; }\nQLabel#badge { background:#e9f0df; color:#607c49; border-radius:5px; padding:5px 10px; font-size:11px; }\nQFrame#card { background:white; border:1px solid #e2e9dc; border-radius:14px; }\nQLineEdit,QComboBox,QSpinBox { background:#fafcf7; border:1px solid #dce5d3; border-radius:7px; padding:10px 12px; min-height:18px; selection-background-color:#dbe8ce; }\nQLineEdit:focus,QComboBox:focus,QSpinBox:focus { border-color:#809e68; }\nQComboBox::drop-down { width:24px; border:none; }\nQComboBox QAbstractItemView { background:white; selection-background-color:#e9f0df; color:#293e34; }\nQPushButton,QToolButton { background:white; border:1px solid #dce5d3; border-radius:7px; padding:9px 16px; min-height:19px; color:#546e42; }\nQPushButton:hover,QToolButton:hover { background:#edf3e5; border-color:#bdcdaa; }\nQPushButton:disabled { color:#a8b19e; background:#f2f5ed; border-color:#e7ecdf; }\nQPushButton#primary { background:#3c634b; color:white; border:none; padding:13px 30px; font-weight:600; }\nQPushButton#primary:hover { background:#2e523c; }\nQPushButton#primary:disabled { background:#a7b7a1; }\nQPushButton#link { background:transparent; border:none; color:#6a8453; padding:6px 0; text-align:left; }\nQToolButton::menu-indicator { image:none; }\nQProgressBar { border:none; background:#edf2e5; border-radius:4px; min-height:8px; max-height:8px; }\nQProgressBar::chunk { background:#7e9e60; border-radius:4px; }\nQTableWidget,QListWidget,QPlainTextEdit { background:white; alternate-background-color:#f6f9f0; border:1px solid #e0e7d7; border-radius:7px; selection-background-color:#e6efd9; selection-color:#2e4831; outline:none; }\nQTableWidget::item { padding:7px; border:none; }\nQHeaderView::section { background:#eef3e6; color:#7c8d6c; padding:10px; border:none; font-size:12px; }\nQMenu { background:white; border:1px solid #dce5d3; border-radius:8px; padding:7px; }\nQMenu::item { padding:9px 28px 9px 16px; border-radius:4px; }\nQMenu::item:selected { background:#eaf1e0; }\nQMenu::separator { height:1px; background:#e6eddd; margin:5px; }\nQTabWidget::pane { background:white; border:1px solid #e0e7d7; border-radius:8px; padding:8px; }\nQTabBar::tab { padding:11px 19px; color:#8b997e; background:transparent; }\nQTabBar::tab:selected { color:#446332; background:#eaf1df; border-radius:6px; }\nQCheckBox { spacing:8px; padding:5px 0; }\nQStatusBar { background:#f5f7f2; color:#8d9b80; border:none; font-size:11px; }\n"

def configure_application(app, appearance=None):
    if not app.property('cardvault_fonts_loaded'):
        for name in ('SourceHanSansSC-Regular.otf', 'SourceHanSansSC-Bold.otf'):
            path = ROOT / 'assets' / 'fonts' / name
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id < 0:
                raise RuntimeError(f'Cannot load bundled Source Han Sans font: {path}')
        app.setProperty('cardvault_fonts_loaded', True)
    appearance = appearance or {}
    family = (appearance.get('font') or DEFAULT_FONT).replace("'", '').replace('\\', '')
    accent = QColor(appearance.get('color', '#3c634b'))
    if not accent.isValid():
        accent = QColor('#3c634b')
    app.setFont(QFont(family, 10))
    app.setStyle('Fusion')
    style = STYLE.replace("'Source Han Sans SC'", "'" + family + "'")
    def tint(amount):
        return QColor(*[round(c * (1 - amount) + 255 * amount) for c in (accent.red(), accent.green(), accent.blue())]).name()
    style = style.replace('#3c634b', accent.name())
    ink = accent.darker(250).name() if accent.lightnessF() > .55 else accent.name()
    for old in ('#546e42', '#6a8453', '#446332', '#607c49'):
        style = style.replace(old, ink)
    style = style.replace('#f5f7f2', tint(.96))
    style = style.replace('#2e523c', accent.darker(120).name())
    for old in ('#7e9e60', '#809e68'):
        style = style.replace(old, accent.name())
    for old in ('#e9f0df', '#eaf1df', '#eaf1e0', '#e6efd9', '#edf3e5'):
        style = style.replace(old, tint(.88))
    if accent.lightnessF() > .65:
        style = style.replace("QPushButton#primary { background:" + accent.name() + "; color:white", "QPushButton#primary { background:" + accent.name() + "; color:#17212b")
    arrow = (ROOT / 'assets' / 'qt-down.svg').as_posix()
    app.setStyleSheet(style + f'QComboBox::down-arrow {{ image: url("{arrow}"); width: 12px; height: 12px; }}')


def label(text='', name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget

def button(text, callback=None, name=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    if callback:
        widget.clicked.connect(callback)
    return widget

def bytes_text(value):
    value = float(value or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024

def configure_table(table, headers):
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(45)
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)

class Bridge(QObject):
    finished = Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='desktop-io')
        self.finished.connect(self.deliver)

    def submit(self, work, callback):
        future = self.pool.submit(work)

        def complete(future):
            try:
                result, error = (future.result(), None)
            except Exception as failure:
                result, error = (None, failure)
            try:
                self.finished.emit(callback, result, error)
            except RuntimeError:
                pass
        future.add_done_callback(complete)

    @Slot(object, object, object)
    def deliver(self, callback, result, error):
        callback(result, error)

class FolderField(QWidget):

    def __init__(self, hint, value='', parent=None):
        super().__init__(parent)
        self.setMinimumHeight(42)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.edit = QLineEdit(value)
        self.edit.setPlaceholderText(hint)
        self.edit.setAccessibleName(hint)
        self.browse = button(tr('浏览…'), self.choose)
        self.browse.setMinimumWidth(84)
        row.addWidget(self.edit, 1)
        row.addWidget(self.browse)

    def choose(self):
        directory = QFileDialog.getExistingDirectory(self, tr('选择文件夹或存储卡'), self.edit.text())
        if directory:
            self.edit.setText(directory)

    def text(self):
        return self.edit.text().strip()

class OptionsDialog(QDialog):

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('拷贝选项'))
        self.resize(590, 490)
        self.options = dict(options)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(17)
        layout.addWidget(label(tr('拷贝选项'), 'section'))
        tabs = QTabWidget()
        layout.addWidget(tabs)
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(20, 24, 20, 20)
        form.setSpacing(15)
        self.filter = self.combo([(tr('全部文件'), 'all'), (tr('仅照片与 RAW'), 'photo'), (tr('仅视频'), 'video'), (tr('自定义扩展名'), 'custom')], 'filter')
        self.extensions = QLineEdit(str(options['extensions']))
        self.extensions.setPlaceholderText(tr('例如 jpg, arw, mp4'))
        self.extensions.setEnabled(self.filter.currentData() == 'custom')
        self.filter.currentIndexChanged.connect(lambda: self.extensions.setEnabled(self.filter.currentData() == 'custom'))
        self.organize = self.combo([(tr('保留原始目录'), 'original'), (tr('文件修改日期'), 'date'), (tr('文件类型'), 'type'), (tr('日期 / 文件类型'), 'date_type'), (tr('设备名称'), 'device')], 'organize')
        self.project = QLineEdit(str(options['project']))
        self.project.setPlaceholderText(tr('例如：秋日山野'))
        self.rename = QCheckBox(tr('按「项目_日期_序号」重命名'))
        self.rename.setChecked(options['rename'])
        for title, field in [(tr('文件范围'), self.filter), (tr('扩展名'), self.extensions), (tr('目录分类'), self.organize), (tr('项目名称'), self.project), ('', self.rename)]:
            form.addRow(title, field)
        form.addRow('', label(tr('日期取文件修改时间；源卡文件名保持不变。'), 'subtle', True))
        tabs.addTab(content, tr('内容与命名'))
        safety = QWidget()
        safe_form = QFormLayout(safety)
        safe_form.setContentsMargins(20, 24, 20, 20)
        safe_form.setSpacing(16)
        self.duplicate = self.combo([(tr('自动改名，保留两个文件'), 'rename'), (tr('大小和 SHA-256 相同才跳过'), 'skip'), (tr('校验成功后覆盖同名文件'), 'overwrite')], 'duplicate')
        self.dual = QCheckBox(tr('启用第二份备份'))
        self.dual.setChecked(options['dual'])
        self.secondary = FolderField(tr('选择第二块硬盘的备份目录'), options['secondary'])
        self.secondary.setEnabled(options['dual'])
        self.dual.toggled.connect(self.secondary.setEnabled)
        self.retries = QSpinBox()
        self.retries.setRange(0, 5)
        self.retries.setValue(options['retries'])
        self.retries.setSuffix(tr(' 次'))
        for title, field in [(tr('同名文件'), self.duplicate), (tr('读取失败重试'), self.retries), ('', self.dual), (tr('第二个目标'), self.secondary)]:
            safe_form.addRow(title, field)
        safe_form.addRow('', label(tr('建议使用两块独立硬盘。每个副本都进行 SHA-256 校验；目标不可写时不会反复重试。'), 'muted', True))
        tabs.addTab(safety, tr('安全与双盘'))
        reminders = QWidget()
        reminder_layout = QVBoxLayout(reminders)
        reminder_layout.setContentsMargins(20, 24, 20, 20)
        self.sound = QCheckBox(tr('完成时播放系统提示音'))
        self.sound.setChecked(options['sound'])
        self.notify = QCheckBox(tr('任务完成或失败时显示桌面通知'))
        self.notify.setChecked(options['notify'])
        reminder_layout.addWidget(self.sound)
        reminder_layout.addWidget(self.notify)
        reminder_layout.addWidget(label(tr('通知使用系统托盘，无需浏览器授权。'), 'muted', True))
        reminder_layout.addStretch()
        tabs.addTab(reminders, tr('完成提醒'))
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText(tr('保存选项'))
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('取消'))
        actions.accepted.connect(self.accept)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

    def combo(self, values, key):
        combo = QComboBox()
        for title, value in values:
            combo.addItem(title, value)
        combo.setCurrentIndex(max(0, combo.findData(self.options[key])))
        return combo

    def accept(self):
        if self.filter.currentData() == 'custom' and (not self.extensions.text().strip()):
            QMessageBox.warning(self, tr('缺少扩展名'), tr('请填写需要复制的扩展名。'))
            return
        if self.dual.isChecked() and (not self.secondary.text()):
            QMessageBox.warning(self, tr('缺少第二个目标'), tr('请为第二份备份选择文件夹。'))
            return
        self.options.update(filter=self.filter.currentData(), extensions=self.extensions.text(), organize=self.organize.currentData(), duplicate=self.duplicate.currentData(), project=self.project.text(), rename=self.rename.isChecked(), retries=self.retries.value(), dual=self.dual.isChecked(), secondary=self.secondary.text(), sound=self.sound.isChecked(), notify=self.notify.isChecked())
        super().accept()

class DetailsDialog(QDialog):

    def __init__(self, main, ident):
        super().__init__(main)
        self.main, self.ident, self.version = (main, ident, None)
        self.setWindowTitle(tr('任务详情与日志'))
        self.resize(800, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 22)
        layout.setSpacing(14)
        self.title = label('', 'section')
        self.summary = label('', None, True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.locations = label('', 'muted', True)
        self.locations.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_counts = ResultCounts()
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(500)
        self.logs.setFont(QApplication.font())
        for widget in (self.title, self.locations, self.summary):
            layout.addWidget(widget)
        layout.addWidget(self.result_counts)
        layout.addWidget(label(tr('成功包含已验证的相同文件跳过；失败按源文件计数。'), 'subtle', True))
        layout.addWidget(self.logs, 1)
        row = QHBoxLayout()
        self.recover = button(tr('继续备份'), self.resume)
        self.export = QToolButton()
        self.export.setText(tr('导出报告 ▾'))
        self.export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        for title, format in [(tr('CSV 文件校验报告'), 'csv'), (tr('JSON 完整任务'), 'json'), (tr('JSONL 完整日志'), 'log')]:
            menu.addAction(title, lambda checked=False, format=format: main.export_report(ident, format, self))
        self.export.setMenu(menu)
        row.addWidget(self.recover)
        row.addWidget(self.export)
        row.addStretch()
        row.addWidget(button(tr('关闭'), self.accept))
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(800)
        self.finished.connect(self.timer.stop)
        self.refresh()

    def refresh(self):
        job = self.main.engine.snapshot(self.main.engine.jobs[self.ident])
        version = (job.get('updated'), job['status'], job['current'], len(job['events']))
        if self.version == version:
            return
        self.version = version
        self.result_counts.update_job(job)
        self.title.setText(f"{job['name']}  ·  {tr(STATUS.get(job['status'], job['status']))}")
        self.locations.setText(tr('来源：') + job['source'] + tr('\n目标：') + '\n          '.join(job['targets']))
        self.summary.setText(tr('{v0} 已复制 · {v1} 已跳过 · {v2} 失败 / 共 {v3} 个文件\n\n{v4}', v0=job['copied'], v1=job['skipped'], v2=job['failed'], v3=job['total_files'], v4=job['message']))
        self.logs.setPlainText('\n'.join((f"{e['time'].replace('T', ' ')}  {e['message']}" for e in job['events'])))
        self.recover.setVisible(job['status'] in RECOVERABLE)

    def resume(self):
        if self.main.resume_job(self.ident):
            self.refresh()

class HistoryDialog(QDialog):

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle(tr('任务与历史'))
        self.resize(900, 530)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(15)
        layout.addWidget(label(tr('任务与历史'), 'section'))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('搜索任务、来源或目标目录'))
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        self.table = QTableWidget()
        configure_table(self.table, [tr('任务'), tr('创建时间'), tr('文件'), tr('状态'), tr('目标目录')])
        self.table.doubleClicked.connect(self.details)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(button(tr('详情与报告'), self.details))
        row.addWidget(button(tr('继续所选任务'), self.resume))
        row.addWidget(button(tr('在主界面显示'), self.show_main))
        row.addStretch()
        row.addWidget(button(tr('关闭'), self.accept))
        layout.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)
        self.finished.connect(self.timer.stop)
        self.refresh()

    def selected(self):
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self):
        selected = self.selected()
        query = self.search.text().lower()
        jobs = [j for j in self.main.engine.list_jobs() if query in ' '.join([j['name'], j['source'], *j['targets']]).lower()]
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            values = [job['name'], job['created'].replace('T', ' '), str(job['total_files']), tr(STATUS.get(job['status'], job['status'])), ' / '.join(job['targets'])]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setData(Qt.ItemDataRole.UserRole, job['id'])
                self.table.setItem(row, column, item)
            if selected == job['id']:
                self.table.selectRow(row)
        if not selected and jobs:
            self.table.selectRow(0)

    def details(self):
        if self.selected():
            DetailsDialog(self.main, self.selected()).exec()

    def resume(self):
        if self.selected():
            self.main.resume_job(self.selected())
            self.refresh()

    def show_main(self):
        if self.selected():
            self.main.current_id = self.selected()
            self.main.refresh()
            self.accept()

class DevicesDialog(QDialog):

    def __init__(self, main):
        super().__init__(main)
        self.main, self.devices = (main, [])
        self.setWindowTitle(tr('存储设备'))
        self.resize(780, 440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(15)
        layout.addWidget(label(tr('存储设备'), 'section'))
        self.table = QTableWidget()
        configure_table(self.table, [tr('名称'), tr('盘符'), tr('类型'), tr('文件系统'), tr('容量'), tr('可用')])
        layout.addWidget(self.table, 1)
        self.message = label(tr('正在识别设备…'), 'muted', True)
        layout.addWidget(self.message)
        row = QHBoxLayout()
        self.refresh_button = button(tr('刷新'), self.refresh)
        for widget in (self.refresh_button, button(tr('用作来源'), self.select_source), button(tr('安全弹出'), self.eject)):
            row.addWidget(widget)
        row.addStretch()
        row.addWidget(button(tr('关闭'), self.accept))
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        self.refresh_button.setEnabled(False)
        self.main.bridge.submit(drives, self.loaded)

    def loaded(self, devices, error):
        self.refresh_button.setEnabled(True)
        if error:
            self.message.setText(str(error))
            return
        self.devices = devices
        self.table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            values = [device['name'], device['path'], tr('可移动') if device['kind'] == 'removable' else tr('本地磁盘'), device['filesystem'], bytes_text(device['size']), bytes_text(device['free'])]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        if devices:
            self.table.selectRow(0)
        self.message.setText(tr('安全弹出由 Windows 处理。请等待系统确认后再拔出。'))

    def selected(self):
        row = self.table.currentRow()
        return self.devices[row] if 0 <= row < len(self.devices) else None

    def select_source(self):
        device = self.selected()
        if device:
            self.main.source.edit.setText(device['path'])
            self.accept()

    def eject(self):
        device = self.selected()
        if not device:
            return
        if device['kind'] != 'removable':
            QMessageBox.information(self, tr('无法弹出'), tr('Windows 未将此卷识别为可弹出设备。'))
            return
        base = Path(device['path']).resolve()
        if not self.update_requested and any((j['status'] in ACTIVE and any((under(Path(p), base) for p in [j['source'], *j['targets']])) for j in self.main.engine.list_jobs())):
            QMessageBox.warning(self, tr('设备正在使用'), tr('请先暂停相关任务，等待进度保存。'))
            return
        if QMessageBox.question(self, tr('安全弹出'), tr('请求 Windows 弹出 {v0}（{v1}）？', v0=device['name'], v1=device['path'])) != QMessageBox.StandardButton.Yes:
            return
        self.main.bridge.submit(lambda: eject(device['path']), lambda result, error: self.message.setText(str(error) if error else result))

class BatchDialog(QDialog):

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle(tr('多卡批量备份'))
        self.resize(600, 410)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(label(tr('多卡批量备份'), 'section'))
        layout.addWidget(label(tr('沿用主界面的目标和拷贝选项。各来源建立独立子目录，最多 3 个任务并行。'), 'muted', True))
        self.sources = QListWidget()
        layout.addWidget(self.sources, 1)
        row = QHBoxLayout()
        row.addWidget(button(tr('添加来源…'), self.add))
        row.addWidget(button(tr('移除'), lambda: self.sources.takeItem(self.sources.currentRow())))
        row.addStretch()
        row.addWidget(button(tr('开始批量备份'), self.start, 'primary'))
        layout.addLayout(row)

    def add(self):
        path = QFileDialog.getExistingDirectory(self, tr('选择存储卡或素材文件夹'))
        if path and path.lower() not in [self.sources.item(i).text().lower() for i in range(self.sources.count())]:
            self.sources.addItem(path)

    def start(self):
        paths = [self.sources.item(i).text() for i in range(self.sources.count())]
        if not paths:
            QMessageBox.information(self, tr('添加来源'), tr('请先添加需要备份的存储卡。'))
        elif self.main.start_jobs(paths):
            self.accept()

class ResultCounts(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.values = {}
        for key, title, foreground, background in [('success', tr('成功'), '#166534', '#e9f7ed'), ('failed', tr('失败'), '#b91c1c', '#fff0ed'), ('skipped', tr('已跳过'), '#475569', '#eef2f6'), ('pending', tr('未完成'), '#6b7280', '#f3f4f6')]:
            tile = QFrame()
            tile.setStyleSheet(f'QFrame {{ background:{background}; border-radius:8px; }}')
            box = QVBoxLayout(tile)
            number = label('0')
            number.setStyleSheet(f'font-size:25px; font-weight:700; color:{foreground};')
            box.addWidget(number)
            box.addWidget(label(title))
            row.addWidget(tile)
            self.values[key] = number

    def update_job(self, job):
        success = job['copied'] + job['skipped']
        for key, value in [('success', success), ('failed', job['failed']), ('skipped', job['skipped']), ('pending', max(0, job['total_files'] - success - job['failed']))]:
            self.values[key].setText(str(value))


class UpdatePage(QWidget):
    def __init__(self, main, dialog):
        super().__init__(dialog)
        self.main, self.dialog, self.package = main, dialog, None
        self.root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.addWidget(label(tr('当前版本：{v0}', v0=VERSION), 'section'))
        self.message = label(tr('将新版 CardVault Setup 安装包拖入这里，或点击选择。'), 'muted', True)
        self.message.setMinimumHeight(100)
        self.message.setStyleSheet('border:2px dashed #b9c8b1; border-radius:12px; padding:20px;')
        layout.addWidget(self.message)
        self.choose_button = button(tr('选择安装包…'), self.choose)
        layout.addWidget(self.choose_button)
        layout.addWidget(label(tr('安装包保存在软件目录的 update 文件夹。开始更新后，任务安全暂停，程序退出；安装完成后自动重新启动。'), 'muted', True))
        self.install_button = button(tr('安装更新并重启'), self.install, 'primary')
        self.install_button.setEnabled(False)
        layout.addWidget(self.install_button)
        layout.addStretch()
        if not getattr(sys, 'frozen', False):
            layout.addWidget(label(tr('源码运行时不能覆盖更新，请使用已安装的 EXE 版本。'), 'muted', True))

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and urls[0].toLocalFile().lower().endswith('.exe') and self.choose_button.isEnabled():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.choose_button.isEnabled():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                self.stage(urls[0].toLocalFile())
                event.acceptProposedAction()

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('选择安装包…'), '', 'CardVault Setup (*.exe)')
        if path:
            self.stage(path)

    def stage(self, path):
        self.package = None
        self.install_button.setEnabled(False)
        self.choose_button.setEnabled(False)
        self.message.setText(tr('正在检查并保存安装包…'))
        self.main.bridge.submit(lambda: stage_package(path, self.root), self.staged)

    def staged(self, result, error):
        self.choose_button.setEnabled(True)
        if error:
            self.message.setText(tr('更新失败：{v0}', v0=str(error)))
            return
        self.package = result
        self.message.setText(tr('新版 {v0} 已就绪\n{v1}', v0=result['version'], v1=result['package']))
        self.install_button.setEnabled(bool(getattr(sys, 'frozen', False)))

    def install(self):
        if not self.package or self.main.closing:
            return
        if QMessageBox.question(self, tr('安装更新并重启'), tr('即将暂停任务并关闭程序，安装所选更新后重新启动。是否继续？')) != QMessageBox.StandardButton.Yes:
            return
        self.main.pending_update = (self.package, self.root)
        self.main.update_requested = True
        self.dialog.reject()
        self.main.close()


class SettingsDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.setWindowTitle(tr('设置'))
        self.resize(680, 520)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        general = QWidget()
        content = QVBoxLayout(general)
        form = QFormLayout()
        self.language = QComboBox()
        for code, title in LANGUAGES.items():
            self.language.addItem(title, code)
        self.language.setCurrentIndex(self.language.findData(main.preferences['language']))
        self.workers = QSpinBox()
        self.workers.setRange(1, 8)
        self.workers.setValue(main.options['workers'])
        self.verification = QComboBox()
        self.verification.addItem(tr('每份拷贝完成立即校验'), 'per_file')
        self.verification.addItem(tr('全部拷贝完成后集中校验'), 'batch')
        self.verification.setCurrentIndex(self.verification.findData(main.options['verification']))
        form.addRow(tr('界面语言'), self.language)
        form.addRow(tr('并发拷贝文件数'), self.workers)
        form.addRow(tr('校验时机'), self.verification)
        content.addLayout(form)
        content.addWidget(label(tr('首次启动按系统时区选择语言；手动选择后始终使用您的设置。语言修改在下次启动时生效。'), 'muted', True))
        content.addWidget(label(tr('并发数用于新任务。建议从 3 开始；机械硬盘或较慢的存储卡可设为 1。每份副本仍独立校验。'), 'muted', True))
        content.addWidget(label(tr('集中校验期间临时文件不会计入成功；仅校验通过的副本才提交。校验设置用于新任务。'), 'muted', True))
        content.addStretch()
        tabs.addTab(general, tr('拷贝与语言'))
        appearance = QWidget()
        appearance_form = QFormLayout(appearance)
        self.font_choice = QFontComboBox()
        self.font_choice.setCurrentFont(QFont(main.preferences.get('appearance', {}).get('font', QApplication.font().family())))
        self.color = QColor(main.preferences.get('appearance', {}).get('color', '#3c634b'))
        self.color_button = button(self.color.name(), self.choose_color)
        appearance_form.addRow(tr('软件字体'), self.font_choice)
        appearance_form.addRow(tr('主题色'), self.color_button)
        appearance_form.addRow(label(tr('保存后立即应用字体与主题色。'), 'muted', True))
        tabs.addTab(appearance, tr('外观'))
        self.update_page = UpdatePage(main, self)
        tabs.addTab(self.update_page, tr('更新'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr('保存设置'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('取消'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_color(self):
        color = QColorDialog.getColor(self.color, self, tr('主题色'))
        if color.isValid():
            self.color = color
            self.color_button.setText(color.name())

class MainWindow(QMainWindow):

    def __init__(self, engine, preferences_path=None, start_devices=True):
        super().__init__()
        self.engine = engine
        self.pending_update = None
        self.update_requested = False
        self.preferences_path = preferences_path or engine.state_dir / 'preferences.json'
        self.options, self.preferences = (dict(DEFAULTS), {})
        try:
            self.preferences = json.loads(self.preferences_path.read_text(encoding='utf-8'))
            self.options.update({k: v for k, v in self.preferences.get('options', {}).items() if k in DEFAULTS})
        except (OSError, ValueError, TypeError):
            pass
        self.preferences['language'] = self.preferences.get('language') if self.preferences.get('language') in LANGUAGES else detect_language()
        set_language(self.preferences['language'])
        install_qt_translation()
        configure_application(QApplication.instance(), self.preferences.get('appearance'))
        self.save_preferences_initial()
        self.current_id, self.previous_status = (None, {})
        self.closing = self.ready_to_close = self.device_pending = False
        self.bridge = Bridge(self)
        self.setWindowTitle(tr('CardVault · 素材安全备份'))
        self.resize(960, 830)
        self.setMinimumSize(710, 800)
        self.setWindowIcon(QIcon(str(ROOT / 'assets' / 'logo.svg')))
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(34, 25, 34, 18)
        layout.setSpacing(20)
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self.windowIcon().pixmap(36, 36))
        header.addWidget(logo)
        header.addSpacing(3)
        header.addWidget(label('CardVault', 'brand'))
        header.addSpacing(5)
        header.addWidget(label(tr('本地安全备份'), 'subtle'))
        header.addStretch()
        header.addWidget(button(tr('任务历史'), self.history))
        self.more = QToolButton()
        self.more.setText(tr('更多  ···'))
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        menu.addAction(tr('拷贝选项…'), self.advanced)
        menu.addAction(tr('多卡批量备份…'), lambda: BatchDialog(self).exec())
        menu.addAction(tr('存储设备与安全弹出…'), lambda: DevicesDialog(self).exec())
        menu.addAction(tr('任务与历史…'), self.history)
        menu.addAction(tr('设置…'), self.settings)
        menu.addSeparator()
        menu.addAction(tr('打开报告文件夹'), self.open_reports)
        menu.addAction(tr('退出应用'), self.close)
        self.more.setMenu(menu)
        header.addWidget(self.more)
        layout.addLayout(header)
        heading = QVBoxLayout()
        heading.setSpacing(6)
        heading.addWidget(label(tr('选择存储卡，开始备份。'), 'title'))
        heading.addWidget(label(tr('源卡只读，每一个副本都经过 SHA-256 校验。'), 'muted'))
        layout.addLayout(heading)
        card = QFrame()
        card.setObjectName('card')
        fields = QVBoxLayout(card)
        fields.setContentsMargins(24, 20, 24, 22)
        fields.setSpacing(10)
        fields.addWidget(label(tr('来源'), 'section'))
        self.source = FolderField(tr('选择存储卡或素材文件夹'), self.preferences.get('source', ''))
        self.source.setObjectName('sourceField')
        fields.addWidget(self.source)
        fields.addSpacing(8)
        fields.addWidget(label(tr('备份到'), 'section'))
        self.target = FolderField(tr('选择电脑或另一块硬盘上的文件夹'), self.preferences.get('target', ''))
        self.target.setObjectName('targetField')
        fields.addWidget(self.target)
        fields.addSpacing(9)
        actions = QHBoxLayout()
        self.options_button = button(tr('拷贝选项…'), self.advanced, 'link')
        actions.addWidget(self.options_button)
        actions.addStretch()
        self.start_button = button(tr('开始安全备份  →'), self.start_backup, 'primary')
        self.start_button.setMinimumWidth(190)
        actions.addWidget(self.start_button)
        fields.addLayout(actions)
        layout.addWidget(card)
        self.progress_card = QFrame()
        self.progress_card.setObjectName('card')
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(24, 19, 24, 18)
        progress_layout.setSpacing(12)
        progress_header = QHBoxLayout()
        self.job_title = label(tr('准备就绪'), 'section')
        progress_header.addWidget(self.job_title, 1)
        self.status_badge = label(tr('等待开始'), 'badge')
        progress_header.addWidget(self.status_badge)
        progress_layout.addLayout(progress_header)
        self.message = label(tr('选择来源和备份位置，即可开始。'), 'muted', True)
        progress_layout.addWidget(self.message)
        self.result_counts = ResultCounts()
        self.result_counts.hide()
        progress_layout.addWidget(self.result_counts)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        progress_layout.addWidget(self.progress)
        self.file_label = label('', 'subtle')
        self.file_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        progress_layout.addWidget(self.file_label)
        bottom = QHBoxLayout()
        self.metrics = label(tr('进度会自动保存，可暂停后继续。'), 'subtle', True)
        bottom.addWidget(self.metrics, 1)
        self.pause_button = button(tr('暂停'), self.pause_current)
        self.resume_button = button(tr('继续备份'), self.resume_current)
        self.details_button = button(tr('详情与日志'), self.details, 'link')
        for widget in (self.pause_button, self.resume_button, self.details_button):
            bottom.addWidget(widget)
        progress_layout.addLayout(bottom)
        layout.addWidget(self.progress_card)
        layout.addStretch(1)
        footer = QHBoxLayout()
        footer.addWidget(label(tr('本地处理  ·  校验后提交  ·  不修改源卡'), 'subtle'))
        footer.addStretch()
        footer.addWidget(label(tr('桌面版 {v0}', v0=VERSION), 'subtle'))
        layout.addLayout(footer)
        self.setStatusBar(QStatusBar())
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(tr('CardVault · 素材安全备份'))
        self.tray.activated.connect(lambda reason: self.activate() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray_menu = QMenu(self)
            tray_menu.addAction(tr('打开 CardVault'), self.activate)
            tray_menu.addAction(tr('退出'), self.close)
            self.tray.setContextMenu(tray_menu)
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)
        self.device_timer = QTimer(self)
        self.device_timer.timeout.connect(self.refresh_devices)
        if start_devices:
            self.device_timer.start(15000)
            self.refresh_devices()
        self.update_options_text()
        self.refresh()

    def activate(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def update_options_text(self):
        scope = {'all': tr('全部文件'), 'photo': tr('仅照片'), 'video': tr('仅视频'), 'custom': tr('自定义类型')}[self.options['filter']]
        copies = tr('双盘备份') if self.options['dual'] else tr('单份备份')
        self.options_button.setText(tr('{v0} · {v1}  |  拷贝选项…', v0=scope, v1=copies))

    def save_preferences(self):
        self.preferences.update(options=self.options, source=self.source.text(), target=self.target.text())
        atomic_json(self.preferences_path, self.preferences)

    def save_preferences_initial(self):
        self.preferences['options'] = self.options
        atomic_json(self.preferences_path, self.preferences)

    def settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.preferences['language'] = dialog.language.currentData()
            self.options['workers'] = dialog.workers.value()
            self.options['verification'] = dialog.verification.currentData()
            self.preferences['appearance'] = {'font': dialog.font_choice.currentFont().family(), 'color': dialog.color.name()}
            configure_application(QApplication.instance(), self.preferences['appearance'])
            self.save_preferences()
            self.update_options_text()

    def advanced(self):
        dialog = OptionsDialog(self.options, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.options = dialog.options
            self.update_options_text()
            self.save_preferences()

    def start_backup(self):
        self.start_jobs([self.source.text()])

    def start_jobs(self, sources):
        if self.closing:
            return False
        if not sources or any((not s for s in sources)) or (not self.target.text()):
            QMessageBox.information(self, tr('选择来源与目标'), tr('请先选择存储卡和备份目录。'))
            return False
        targets = [self.target.text()]
        if self.options['dual']:
            if not self.options['secondary']:
                QMessageBox.warning(self, tr('第二份备份'), tr('请在拷贝选项中选择第二个目标。'))
                return False
            targets.append(self.options['secondary'])
        if self.options['duplicate'] == 'overwrite' and QMessageBox.question(self, tr('确认覆盖'), tr('目标中的同名文件将在新副本校验通过后被替换，旧版本无法从本应用恢复。是否继续？')) != QMessageBox.StandardButton.Yes:
            return False
        created = 0
        try:
            for index, source in enumerate(sources):
                destinations = targets if len(sources) == 1 else [str(Path(t) / f'{clean_name(Path(source).name or Path(source).drive)}_{index + 1}') for t in targets]
                job = self.engine.create({**self.options, 'source': source, 'targets': destinations})
                self.current_id = job['id']
                self.previous_status[job['id']] = 'queued'
                created += 1
            self.save_preferences()
            self.refresh()
            return True
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr('无法开始备份'), (tr('已创建 {v0} 个任务。\n', v0=created) if created else '') + str(error))
            self.refresh()
            return False

    def refresh(self):
        jobs = self.engine.list_jobs()
        for job in jobs:
            previous = self.previous_status.get(job['id'])
            if previous and previous != job['status'] and (job['status'] in {'completed', 'partial', 'failed'}):
                self.completed(job)
            self.previous_status[job['id']] = job['status']
        if self.current_id is None and jobs:
            self.current_id = jobs[0]['id']
        job = next((j for j in jobs if j['id'] == self.current_id), None)
        self.pause_button.setVisible(bool(job and job['status'] in ACTIVE))
        self.resume_button.setVisible(bool(job and job['status'] in RECOVERABLE))
        self.details_button.setVisible(bool(job))
        if not job:
            return
        self.result_counts.show()
        self.result_counts.update_job(job)
        self.job_title.setText(self.job_title.fontMetrics().elidedText(job['name'], Qt.TextElideMode.ElideRight, max(200, self.width() - 340)))
        self.job_title.setToolTip(job['name'])
        self.status_badge.setText(tr(STATUS.get(job['status'], job['status'])))
        self.status_badge.setStyleSheet('background: #fbefdf; color: #9f6e32;' if job['status'] in {'partial', 'failed'} else '')
        self.message.setText(translate_text(job['message']).splitlines()[0])
        self.message.setToolTip(translate_text(job['message']))
        self.pause_button.setEnabled(job['status'] != 'pausing' and (not self.closing))
        if job['status'] in {'checking', 'scanning'}:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            amount = 1000 if job['status'] == 'completed' else min(999, int(job['done_bytes'] / job['total_bytes'] * 1000)) if job['total_bytes'] else 0
            self.progress.setValue(amount)
        current = tr('当前文件：') + job['current'] if job['current'] else tr('目标：') + job['targets'][0]
        self.file_label.setText(self.file_label.fontMetrics().elidedText(current, Qt.TextElideMode.ElideMiddle, max(200, self.width() - 120)))
        self.file_label.setToolTip(current)
        done = job['copied'] + job['skipped']
        metrics = tr('{v0} / {v1} 个文件  ·  {v2} / {v3}', v0=done, v1=job['total_files'], v2=bytes_text(job['done_bytes']), v3=bytes_text(job['total_bytes']))
        if job['failed']:
            metrics += tr('  ·  {v0} 个失败', v0=job['failed'])
        if job['speed'] > 0:
            seconds = max(0, job['total_bytes'] - job['done_bytes']) / job['speed']
            remaining = tr('{v0} 秒', v0=format(seconds, f'.0f')) if seconds < 60 else tr('{v0} 分钟', v0=format(seconds / 60, f'.0f'))
            metrics += tr('\n{v0}/s  ·  复制预计剩余 {v1}（不含校验）', v0=bytes_text(job['speed']), v1=remaining)
        self.metrics.setText(metrics)

    def completed(self, job):
        if self.options['sound']:
            QApplication.beep()
        if self.options['notify'] and self.tray.isVisible():
            icon = QSystemTrayIcon.MessageIcon.Information if job['status'] == 'completed' else QSystemTrayIcon.MessageIcon.Warning
            self.tray.showMessage('CardVault · ' + tr(STATUS[job['status']]), job['name'] + '\n' + translate_text(job['message']).splitlines()[0], icon, 7000)

    def pause_current(self):
        if self.current_id:
            self.engine.pause(self.current_id)
            self.refresh()

    def resume_current(self):
        if self.current_id:
            self.resume_job(self.current_id)

    def resume_job(self, ident):
        if self.closing:
            return False
        try:
            self.engine.resume(ident)
            self.current_id = ident
            self.refresh()
            return True
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, tr('无法继续任务'), str(error))
            return False

    def details(self):
        if self.current_id:
            DetailsDialog(self, self.current_id).exec()

    def history(self):
        HistoryDialog(self).exec()

    def export_report(self, ident, format, parent=None):
        folder = self.engine.state_dir / 'reports'
        folder.mkdir(exist_ok=True)
        suffix = 'jsonl' if format == 'log' else format
        filename, _ = QFileDialog.getSaveFileName(parent or self, tr('导出报告'), str(folder / f'CardVault-{ident}.{suffix}'), tr('{v0} 文件 (*.{v1})', v0=suffix.upper(), v1=suffix))
        if not filename:
            return
        destination = Path(filename).resolve()
        if any((under(destination, Path(j['source'])) for j in self.engine.list_jobs())):
            QMessageBox.warning(parent or self, tr('源卡只读保护'), tr('报告不能写入已登记的素材源目录，请选择电脑上的其他目录。'))
            return
        try:
            payload = (self.engine.state_dir / f'{ident}.jsonl').read_bytes() if format == 'log' else self.engine.report(ident, format)
            temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.tmp')
            try:
                with temporary.open('xb') as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
            QMessageBox.information(parent or self, tr('导出完成'), tr('报告已保存：\n{v0}', v0=destination))
        except OSError as error:
            QMessageBox.warning(parent or self, tr('导出失败'), str(error))

    def open_reports(self):
        folder = self.engine.state_dir / 'reports'
        folder.mkdir(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def refresh_devices(self):
        if self.device_pending or self.closing:
            return
        self.device_pending = True
        self.bridge.submit(drives, self.devices_loaded)

    def devices_loaded(self, result, error):
        self.device_pending = False
        if error:
            self.statusBar().showMessage(tr('设备识别暂不可用，可直接浏览文件夹'))
        else:
            cards = sum((d['kind'] == 'removable' for d in result))
            self.statusBar().showMessage(tr('已识别 {v0} 个存储卷 · {v1} 个可移动设备', v0=len(result), v1=cards))

    def closeEvent(self, event):
        if self.ready_to_close:
            self.timer.stop()
            self.device_timer.stop()
            self.tray.hide()
            self.bridge.pool.shutdown(wait=False, cancel_futures=True)
            event.accept()
            return
        event.ignore()
        if self.closing:
            return
        if any((j['status'] in ACTIVE for j in self.engine.list_jobs())) and QMessageBox.question(self, tr('保存并退出'), tr('正在运行的任务会安全暂停，下次启动后可以继续。是否退出？')) != QMessageBox.StandardButton.Yes:
            return
        self.closing = True
        self.start_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.more.setEnabled(False)
        self.statusBar().showMessage(tr('正在保存进度并退出…'))
        self.bridge.submit(self.engine.shutdown, self.shutdown_done)

    def shutdown_done(self, result, error):
        if error:
            self.closing = False
            self.update_requested = False
            QMessageBox.warning(self, tr('保存任务时出错'), str(error))
            return
        if self.pending_update:
            package, root = self.pending_update
            try:
                launch_update(package, root, self.engine.state_dir)
            except Exception as failure:
                QMessageBox.warning(self, tr('更新'), tr('更新失败：{v0}', v0=str(failure)))
                # The engine has already stopped; leave safely rather than accept new jobs.
        self.ready_to_close = True
        self.close()

def main():
    parser = argparse.ArgumentParser(description=tr('CardVault PySide6 桌面版'))
    parser.add_argument('--data-dir', type=Path, default=default_data_dir())
    parser.add_argument('--self-test', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        from .packaged_test import run
        raise SystemExit(run(args.self_test))
    args.data_dir = args.data_dir.resolve()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('CardVault')
    app.setOrganizationName('CardVault')
    configure_application(app)
    app.setWindowIcon(QIcon(str(ROOT / 'assets' / 'logo.svg')))
    server_name = 'CardVault-' + hashlib.sha256(str(args.data_dir).encode()).hexdigest()[:20]
    client = QLocalSocket()
    client.connectToServer(server_name)
    if client.waitForConnected(300):
        client.write(b'activate')
        client.waitForBytesWritten(300)
        client.disconnectFromServer()
        return
    try:
        guard = InstanceLock(args.data_dir)
    except OSError:
        QMessageBox.information(None, tr('CardVault 已在运行'), tr('请先关闭正在使用此任务目录的 CardVault 窗口，再启动程序。'))
        return
    engine = Engine(args.data_dir)
    window = MainWindow(engine)
    server = QLocalServer()
    QLocalServer.removeServer(server_name)
    server.listen(server_name)

    def activate_existing():
        connection = server.nextPendingConnection()
        if connection:
            connection.close()
            connection.deleteLater()
        window.activate()
    server.newConnection.connect(activate_existing)

    def report_exception(exc_type, error, tb):
        message = ''.join(traceback.format_exception(exc_type, error, tb))
        try:
            with (args.data_dir / 'native-error.log').open('a', encoding='utf-8') as log:
                log.write(message + '\n')
        except OSError:
            pass
        QMessageBox.critical(window, tr('程序错误'), tr('{v0}\n\n错误详情已写入 data/native-error.log。', v0=error))
    sys.excepthook = report_exception
    window.show()
    try:
        app.exec()
    finally:
        engine.shutdown()
        server.close()
        guard.close()
if __name__ == '__main__':
    main()
